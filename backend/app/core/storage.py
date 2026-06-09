"""统一的对象存储封装（boto3 S3 兼容模式）。

适配任何 S3 兼容存储（RustFS、MinIO、AWS S3、阿里云 OSS S3 兼容模式）。
在 FastAPI 异步环境下，通过 anyio 在线程池中调用 boto3 同步接口。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, BinaryIO

import boto3
from anyio import to_thread
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import settings


@dataclass
class StoredFileInfo:
    """文件基础信息。"""

    key: str
    url: str
    size: int | None = None
    content_type: str | None = None
    etag: str | None = None
    extra: dict[str, Any] | None = None


def _build_client():
    """构建 boto3 S3 客户端。"""
    if not settings.s3_access_key_id or not settings.s3_secret_access_key:
        raise RuntimeError(
            "S3 未配置：请在环境变量中设置 S3_ACCESS_KEY_ID 和 S3_SECRET_ACCESS_KEY"
        )
    if not settings.s3_endpoint_url:
        raise RuntimeError("S3 未配置：请在环境变量中设置 S3_ENDPOINT_URL")

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region_name or "cn-shenzhen",
        config=Config(s3={"addressing_style": "path"}),
    )


def _normalize_key(key: str) -> str:
    """标准化 object key，自动拼接 base_path。"""
    key = key.lstrip("/")
    base = settings.s3_base_path.strip().strip("/")
    if base:
        return f"{base}/{key}"
    return key


def init_storage() -> None:
    """初始化对象存储（检查 Bucket 是否存在，不存在则创建）。"""
    if not settings.s3_bucket_name:
        raise RuntimeError("S3 未配置：请在配置中设置 S3_BUCKET_NAME")

    client = _build_client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket_name)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("404", "NoSuchBucket"):
            client.create_bucket(Bucket=settings.s3_bucket_name)
        else:
            raise RuntimeError(f"S3 Bucket 访问失败: {e}") from e


async def upload_file(
    *,
    key: str,
    data: bytes | BinaryIO,
    content_type: str | None = None,
    extra_args: dict[str, Any] | None = None,
) -> StoredFileInfo:
    """上传文件到 S3。"""
    client = _build_client()
    s3_key = _normalize_key(key)

    put_kwargs: dict[str, Any] = {
        "Bucket": settings.s3_bucket_name,
        "Key": s3_key,
        "Body": data,
    }
    if content_type:
        put_kwargs["ContentType"] = content_type
    if extra_args:
        put_kwargs.update(extra_args)

    def _upload():
        return client.put_object(**put_kwargs)

    result = await to_thread.run_sync(_upload)

    etag: str | None = result.get("ETag", "").strip('"') or None
    file_size: int | None = None
    if isinstance(data, (bytes, bytearray)):
        file_size = len(data)

    return StoredFileInfo(key=s3_key, url="", etag=etag, size=file_size)


async def download_file(*, key: str) -> bytes:
    """下载文件内容（整个对象读入内存）。"""
    client = _build_client()
    s3_key = _normalize_key(key)

    def _download() -> bytes:
        try:
            resp = client.get_object(Bucket=settings.s3_bucket_name, Key=s3_key)
            return resp["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
                raise FileNotFoundError(f"S3 文件不存在: {s3_key}")
            raise

    return await to_thread.run_sync(_download)


async def get_file_info(*, key: str) -> StoredFileInfo:
    """获取文件元信息（不下载内容）。"""
    client = _build_client()
    s3_key = _normalize_key(key)

    def _head():
        try:
            return client.head_object(Bucket=settings.s3_bucket_name, Key=s3_key)
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
                raise FileNotFoundError(f"S3 文件不存在: {s3_key}")
            raise

    meta = await to_thread.run_sync(_head)
    return StoredFileInfo(
        key=s3_key,
        url="",
        size=meta.get("ContentLength"),
        content_type=meta.get("ContentType"),
        etag=meta.get("ETag", "").strip('"') or None,
    )


async def list_files(*, prefix: str = "") -> list[StoredFileInfo]:
    """根据前缀列出文件（最多 1000 个）。"""
    client = _build_client()
    normalized_prefix = (
        _normalize_key(prefix) if prefix
        else settings.s3_base_path.strip().strip("/") or ""
    )

    def _list() -> list[tuple[str, int | None]]:
        try:
            resp = client.list_objects_v2(
                Bucket=settings.s3_bucket_name, Prefix=normalized_prefix
            )
            return [(obj["Key"], obj.get("Size")) for obj in resp.get("Contents", [])]
        except ClientError:
            return []

    contents = await to_thread.run_sync(_list)
    return [
        StoredFileInfo(key=obj_key, url="", size=size)
        for obj_key, size in contents
    ]


async def delete_file(*, key: str) -> None:
    """删除文件。"""
    client = _build_client()
    s3_key = _normalize_key(key)

    def _delete():
        try:
            client.delete_object(Bucket=settings.s3_bucket_name, Key=s3_key)
        except ClientError as e:
            if e.response["Error"]["Code"] not in ("404", "NoSuchKey"):
                raise

    await to_thread.run_sync(_delete)


def generate_signed_url(*, key: str, expires: int = 3600) -> str:
    """生成带签名的临时访问 URL（同步）。"""
    client = _build_client()
    s3_key = _normalize_key(key)
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket_name, "Key": s3_key},
        ExpiresIn=expires,
    )


async def signed_download_url(*, key: str, expires: int = 3600) -> str:
    """异步版本：生成签名下载 URL。"""
    def _sign():
        return generate_signed_url(key=key, expires=expires)
    return await to_thread.run_sync(_sign)
