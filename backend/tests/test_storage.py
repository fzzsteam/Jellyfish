"""storage.py 单元测试（mock boto3）。"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

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
    assert result.size == 15
