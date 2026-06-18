# Storage SDK Migration: oss2 → boto3

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将对象存储 SDK 从 `oss2` 换成 `boto3`，使本地 RustFS 和生产阿里云 OSS 均可正常使用同一套代码。

**Architecture:** 只替换 `storage.py` 内部实现，对外接口签名不变，调用方零改动。`boto3` 使用 path-style 寻址兼容 RustFS，通过 `endpoint_url` 配置区分本地与生产环境。

**Tech Stack:** Python 3.12, boto3, botocore, anyio（线程池桥接同步 boto3 到 async）

---

## 文件改动一览

| 文件 | 操作 |
|------|------|
| `backend/pyproject.toml` | 移除 `oss2`，添加 `boto3` |
| `backend/app/core/storage.py` | 完全重写，oss2 → boto3 |
| `backend/app/services/studio/files.py` | `thumbnail=info.url` → `thumbnail=""` |
| `backend/app/utils/files.py` | `thumbnail=info.url` → `thumbnail=""` |
| `backend/.env.example` | 更新注释，删除 S3_PUBLIC_BASE_URL 说明 |

---

## Task 1: 更新依赖

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: 确认当前测试基线通过**

```bash
cd backend
uv run pytest tests/test_studio_files_service.py tests/test_files_api_responses.py -q
```

预期：全部 PASS（建立基线，后续可对比）

- [ ] **Step 2: 替换依赖**

将 `pyproject.toml` 中：
```toml
"oss2>=2.18.0",                # 阿里云 OSS 原生 SDK（对象存储，替代 boto3 S3 兼容模式）
```
替换为：
```toml
"boto3>=1.34.0",               # S3 兼容对象存储（支持 RustFS 本地 + 阿里云 OSS 生产）
```

- [ ] **Step 3: 同步依赖**

```bash
cd backend
uv sync
```

预期：oss2 被卸载，boto3 及 botocore、s3transfer 被安装，无报错

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock
git commit -m "chore: replace oss2 with boto3 for S3-compatible storage"
```

---

## Task 2: 重写 storage.py

**Files:**
- Modify: `backend/app/core/storage.py`

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_storage.py`：

```python
"""storage.py 单元测试（mock boto3）。"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from app.core.storage import StoredFileInfo, _normalize_key, _build_client


def test_normalize_key_strips_leading_slash():
    from app.config import settings
    original = settings.s3_base_path
    settings.s3_base_path = ""
    assert _normalize_key("/files/a.png") == "files/a.png"
    settings.s3_base_path = original


def test_normalize_key_prepends_base_path():
    from app.config import settings
    original = settings.s3_base_path
    settings.s3_base_path = "jellyfish/test"
    assert _normalize_key("files/a.png") == "jellyfish/test/files/a.png"
    settings.s3_base_path = original


def test_build_client_raises_without_credentials(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "s3_access_key_id", None)
    monkeypatch.setattr(settings, "s3_secret_access_key", None)
    with pytest.raises(RuntimeError, match="S3_ACCESS_KEY_ID"):
        _build_client()


def test_build_client_raises_without_endpoint(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "s3_access_key_id", "key")
    monkeypatch.setattr(settings, "s3_secret_access_key", "secret")
    monkeypatch.setattr(settings, "s3_endpoint_url", None)
    with pytest.raises(RuntimeError, match="S3_ENDPOINT_URL"):
        _build_client()


@pytest.mark.asyncio
async def test_upload_file_returns_empty_url(monkeypatch):
    from app.core import storage
    from app.config import settings

    monkeypatch.setattr(settings, "s3_access_key_id", "key")
    monkeypatch.setattr(settings, "s3_secret_access_key", "secret")
    monkeypatch.setattr(settings, "s3_endpoint_url", "http://localhost:9000")
    monkeypatch.setattr(settings, "s3_bucket_name", "test-bucket")
    monkeypatch.setattr(settings, "s3_base_path", "")

    mock_client = MagicMock()
    mock_client.put_object.return_value = {"ETag": '"abc123"'}
    monkeypatch.setattr(storage, "_build_client", lambda: mock_client)

    result = await storage.upload_file(key="files/test.png", data=b"fake-image-data", content_type="image/png")

    assert result.url == ""
    assert result.key == "files/test.png"
    assert result.etag == "abc123"
    assert result.size == 16
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend
uv run pytest tests/test_storage.py -v
```

预期：FAIL（`_build_client` 等函数不存在或导入 oss2 报错）

- [ ] **Step 3: 重写 storage.py**

将 `backend/app/core/storage.py` 完整替换为：

```python
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
```

- [ ] **Step 4: 运行新测试，确认通过**

```bash
cd backend
uv run pytest tests/test_storage.py -v
```

预期：全部 PASS

- [ ] **Step 5: 运行既有测试，确认未破坏**

```bash
cd backend
uv run pytest tests/test_studio_files_service.py tests/test_files_api_responses.py -q
```

预期：全部 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/storage.py backend/tests/test_storage.py
git commit -m "feat: migrate storage.py from oss2 to boto3 (S3-compatible)"
```

---

## Task 3: 更新 thumbnail 赋值

**Files:**
- Modify: `backend/app/services/studio/files.py:164`
- Modify: `backend/app/utils/files.py:124`

- [ ] **Step 1: 修改 files.py**

将 `backend/app/services/studio/files.py` 第 164 行：
```python
thumbnail=info.url,
```
改为：
```python
thumbnail="",
```

- [ ] **Step 2: 修改 utils/files.py**

将 `backend/app/utils/files.py` 第 124 行：
```python
thumbnail=info.url,
```
改为：
```python
thumbnail="",
```

- [ ] **Step 3: 运行全量测试**

```bash
cd backend
uv run pytest -q
```

预期：全部 PASS，无新增失败

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/studio/files.py backend/app/utils/files.py
git commit -m "fix: store empty string for FileItem.thumbnail (field unused by frontend)"
```

---

## Task 4: 更新 .env.example

**Files:**
- Modify: `backend/.env.example`

- [ ] **Step 1: 更新 .env.example**

将 S3 相关注释块替换为：

```env
# S3 / 对象存储（boto3，兼容 RustFS 本地 + 阿里云 OSS 生产）
# S3_ENDPOINT_URL=http://localhost:9000          # 本地 RustFS
# S3_ENDPOINT_URL=https://oss-cn-shenzhen-internal.aliyuncs.com  # 线上 OSS 内网
# S3_REGION_NAME=cn-shenzhen                    # 线上填写；本地不填，fallback cn-shenzhen
# S3_ACCESS_KEY_ID=your-access-key-id
# S3_SECRET_ACCESS_KEY=your-secret-key
# S3_BUCKET_NAME=jellyfish-assets
# 可选统一前缀，方便按环境/项目隔离，如 jellyfish/dev
# S3_BASE_PATH=jellyfish/dev
```

- [ ] **Step 2: Commit**

```bash
git add backend/.env.example
git commit -m "docs: update .env.example for boto3 S3 config"
```

---

## 完成验证

- [ ] 启动本地 RustFS（`docker compose -f deploy/compose/docker-compose.infra.yml up -d`）
- [ ] 启动后端（`cd backend && uv run uvicorn app.main:app --reload --port 8000`）
- [ ] 启动 Celery Worker（`cd backend && uv run celery -A app.core.celery_app:celery_app worker --loglevel=info`）
- [ ] 触发一次图片生成任务，确认 Celery 日志中不再出现 `invalid header: authorization`
