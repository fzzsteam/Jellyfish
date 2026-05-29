"""统一的对象存储封装（阿里云 OSS 原生 SDK）。

使用阿里云 oss2 SDK（非 boto3 S3 兼容模式），
确保与阿里云 OSS 的权限模型、ACL 设置完全兼容。

设计目标：
|- 提供上传 / 下载 / 列表 / 详情 等基础能力；
|- 使用 oss2 阿里原生 SDK，避免 boto3 S3 兼容层的 ACL 问题；
|- 在 FastAPI 异步环境下，避免阻塞事件循环：通过 anyio 在线程池中调用 oss2。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, BinaryIO

from anyio import to_thread
import oss2
from oss2.exceptions import NoSuchBucket, NoSuchKey, OssError

from app.config import settings


@dataclass
class StoredFileInfo:
    """文件基础信息（供调用方在路由层自行封装为 Pydantic schema）。"""

    key: str
    url: str
    size: int | None = None
    content_type: str | None = None
    etag: str | None = None
    extra: dict[str, Any] | None = None


def _build_auth() -> oss2.Auth:
    """构建 OSS 认证对象。"""
    if not settings.s3_access_key_id or not settings.s3_secret_access_key:
        raise RuntimeError(
            "OSS 未配置：请在环境变量中设置 s3_access_key_id 和 s3_secret_access_key"
        )
    return oss2.Auth(
        settings.s3_access_key_id,
        settings.s3_secret_access_key,
    )


def _build_bucket() -> oss2.Bucket:
    """构建 OSS Bucket 操作对象。"""
    if not settings.s3_bucket_name:
        raise RuntimeError("OSS 未配置：请在配置中设置 s3_bucket_name")

    endpoint = settings.s3_endpoint_url
    if not endpoint:
        raise RuntimeError("OSS 未配置：请在配置中设置 s3_endpoint_url")

    auth = _build_auth()
    return oss2.Bucket(auth, endpoint, settings.s3_bucket_name)


def _normalize_key(key: str) -> str:
    """标准化 object key，自动拼接 base_path。"""
    key = key.lstrip("/")
    base = settings.s3_base_path.strip().strip("/")
    if base:
        return f"{base}/{key}"
    return key


def _build_public_url(key: str) -> str:
    """构建文件的公开访问 URL。"""
    normalized_key = _normalize_key(key)
    if settings.s3_public_base_url:
        base = settings.s3_public_base_url.rstrip("/")
        return f"{base}/{normalized_key}"

    # fallback: 使用 endpoint + bucket 拼接
    endpoint = settings.s3_endpoint_url.rstrip("/") if settings.s3_endpoint_url else ""
    if endpoint and settings.s3_bucket_name:
        return f"{endpoint}/{settings.s3_bucket_name}/{normalized_key}"
    return f"/{settings.s3_bucket_name}/{normalized_key}"


def init_storage() -> None:
    """初始化对象存储（检查 Bucket 是否存在且可访问）。"""
    bucket = _build_bucket()

    try:
        # 检查 Bucket 是否存在且可访问
        bucket.get_bucket_info()
        return
    except OssError as e:
        code = getattr(e, "code", "")
        # NoSuchBucket 表示不存在
        if code != "NoSuchBucket":
            raise RuntimeError(f"OSS Bucket 访问失败: {e}") from e

    # Bucket 不存在，尝试创建
    try:
        # oss2 创建 Bucket
        service = oss2.Service(_build_auth(), settings.s3_endpoint_url)
        service.create_bucket(settings.s3_bucket_name)  # type: ignore[call-arg]
    except OssError as e:
        code = getattr(e, "code", "")
        if code in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
            return
        raise

    # 再次确认可用
    try:
        bucket.get_bucket_info()
    except OssError as e:
        raise RuntimeError(f"OSS Bucket 创建/访问失败: {e}") from e


async def upload_file(
    *,
    key: str,
    data: bytes | BinaryIO,
    content_type: str | None = None,
    extra_args: dict[str, Any] | None = None,
) -> StoredFileInfo:
    """上传文件到 OSS。

    参数：
    - key：逻辑 key（不需要带 base_path，会自动拼接）
    - data：字节内容或类文件对象
    - content_type：MIME 类型，例如 image/png
    - extra_args：额外参数，如 {"ACL": "public-read"} 会映射为 x-oss-object-acl header
    """

    bucket = _build_bucket()
    s3_key = _normalize_key(key)

    # 构建请求头
    headers: dict[str, Any] = {}
    if content_type:
        headers["Content-Type"] = content_type

    # 处理 ACL 参数：从 extra_args 映射到 OSS header
    extra = extra_args.copy() if extra_args else {}
    acl_value = extra.pop("ACL", None) or extra.pop("acl", None)
    if acl_value:
        headers["x-oss-object-acl"] = acl_value  # 如 "public-read"

    def _upload():
        result = bucket.put_object(s3_key, data, headers=headers)
        return result

    result = await to_thread.run_sync(_upload)

    etag: str | None = None
    if hasattr(result, "etag"):
        etag = result.etag

    url = _build_public_url(key)

    # 尝试获取 size（bytes 数据可以直接取 len）
    file_size: int | None = None
    if isinstance(data, (bytes, bytearray)):
        file_size = len(data)

    return StoredFileInfo(key=s3_key, url=url, etag=etag, size=file_size)


async def download_file(*, key: str) -> bytes:
    """下载文件内容（整个对象读入内存）。"""
    bucket = _build_bucket()
    s3_key = _normalize_key(key)

    def _download() -> bytes:
        try:
            result = bucket.get_object(s3_key)
            return result.read()
        except NoSuchKey:
            raise FileNotFoundError(f"OSS 文件不存在: {s3_key}")

    return await to_thread.run_sync(_download)


async def get_file_info(*, key: str) -> StoredFileInfo:
    """获取文件元信息（不下载内容）。"""
    bucket = _build_bucket()
    s3_key = _normalize_key(key)

    def _head() -> tuple[int | None, str | None, str | None]:
        try:
            meta = bucket.head_object(s3_key)
            return (
                getattr(meta, "content_length", None),
                getattr(meta, "content-type", None),
                getattr(meta, "etag", None),
            )
        except NoSuchKey:
            raise FileNotFoundError(f"OSS 文件不存在: {s3_key}")

    size, ct, etag = await to_thread.run_sync(_head)

    url = _build_public_url(key)
    return StoredFileInfo(
        key=s3_key,
        url=url,
        size=size,
        content_type=ct,
        etag=etag,
    )


async def list_files(*, prefix: str = "") -> list[StoredFileInfo]:
    """根据前缀列出文件（最多一页，若需翻页可扩展）。"""
    bucket = _build_bucket()
    normalized_prefix = (
        _normalize_key(prefix) if prefix
        else settings.s3_base_path.strip().strip("/") or ""
    )

    def _list() -> list[tuple[str, int | None]]:
        results = []
        try:
            for obj in oss2.ObjectIterator(bucket, prefix=normalized_prefix or ""):
                results.append((obj.key, obj.size))
        except OssError:
            pass
        return results

    contents = await to_thread.run_sync(_list)

    out: list[StoredFileInfo] = []
    for obj_key, size in contents:
        url = _build_public_url(obj_key)
        out.append(StoredFileInfo(key=obj_key, url=url, size=size))

    return out


async def delete_file(*, key: str) -> None:
    """删除文件。"""
    bucket = _build_bucket()
    s3_key = _normalize_key(key)

    def _delete():
        try:
            bucket.delete_object(s3_key)
        except NoSuchKey:
            pass  # 已删除或不存在则忽略

    await to_thread.run_sync(_delete)


# ====== 可选：生成签名 URL（用于私有 Bucket 场景）======

def generate_signed_url(*, key: str, expires: int = 3600) -> str:
    """生成带签名的临时访问 URL（同步方法，可在非异步上下文使用）。

    用于私有 Bucket 或需要临时授权的场景，
    返回的 URL 在 expires 秒内有效。

    参数：
    - key: 文件逻辑 key
    - expires: 有效期（秒），默认 1 小时
    """
    bucket = _build_bucket()
    s3_key = _normalize_key(key)
    return bucket.sign_url("GET", s3_key, expires)  # type: ignore[no-any-return]


async def signed_download_url(*, key: str, expires: int = 3600) -> str:
    """异步版本：生成签名下载 URL。"""
    def _sign():
        return generate_signed_url(key=key, expires=expires)
    return await to_thread.run_sync(_sign)
