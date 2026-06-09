"""storage.py 单元测试（mock boto3）。"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from botocore.exceptions import ClientError


def _make_client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "op")


def test_normalize_key_strips_leading_slash(monkeypatch):
    from app.config import settings
    from app.core.storage import _normalize_key
    monkeypatch.setattr(settings, "s3_base_path", "")
    assert _normalize_key("/files/a.png") == "files/a.png"


def test_normalize_key_prepends_base_path(monkeypatch):
    from app.config import settings
    from app.core.storage import _normalize_key
    monkeypatch.setattr(settings, "s3_base_path", "jellyfish/test")
    assert _normalize_key("files/a.png") == "jellyfish/test/files/a.png"


def test_build_client_raises_without_credentials(monkeypatch):
    from app.config import settings
    from app.core.storage import _build_client
    monkeypatch.setattr(settings, "s3_access_key_id", None)
    monkeypatch.setattr(settings, "s3_secret_access_key", None)
    with pytest.raises(RuntimeError, match="S3_ACCESS_KEY_ID"):
        _build_client()


def test_build_client_raises_without_endpoint(monkeypatch):
    from app.config import settings
    from app.core.storage import _build_client
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

    assert result.url == ""  # url 字段设计上不填充，前端通过 /download 接口访问
    assert result.key == "files/test.png"
    assert result.etag == "abc123"
    assert result.size == 15


@pytest.mark.asyncio
async def test_download_file_raises_file_not_found(monkeypatch):
    from app.core import storage
    from app.config import settings

    monkeypatch.setattr(settings, "s3_bucket_name", "test-bucket")
    monkeypatch.setattr(settings, "s3_base_path", "")

    mock_client = MagicMock()
    mock_client.get_object.side_effect = _make_client_error("NoSuchKey")
    monkeypatch.setattr(storage, "_build_client", lambda: mock_client)

    with pytest.raises(FileNotFoundError):
        await storage.download_file(key="files/missing.png")


@pytest.mark.asyncio
async def test_delete_file_ignores_404(monkeypatch):
    from app.core import storage
    from app.config import settings

    monkeypatch.setattr(settings, "s3_bucket_name", "test-bucket")
    monkeypatch.setattr(settings, "s3_base_path", "")

    mock_client = MagicMock()
    mock_client.delete_object.side_effect = _make_client_error("NoSuchKey")
    monkeypatch.setattr(storage, "_build_client", lambda: mock_client)

    # 不抛异常
    await storage.delete_file(key="files/missing.png")


@pytest.mark.asyncio
async def test_list_files_reraises_non_404_client_error(monkeypatch):
    from app.core import storage
    from app.config import settings

    monkeypatch.setattr(settings, "s3_bucket_name", "test-bucket")
    monkeypatch.setattr(settings, "s3_base_path", "")

    mock_client = MagicMock()
    mock_client.list_objects_v2.side_effect = _make_client_error("AccessDenied")
    monkeypatch.setattr(storage, "_build_client", lambda: mock_client)

    with pytest.raises(ClientError):
        await storage.list_files(prefix="files/")
