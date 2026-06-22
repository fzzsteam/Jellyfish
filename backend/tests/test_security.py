"""密码哈希与 JWT 编解码测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import settings
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_password_roundtrip() -> None:
    hashed = hash_password("s3cr3t")

    assert hashed != "s3cr3t"
    assert verify_password("s3cr3t", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_create_and_decode_access_token_roundtrip() -> None:
    token = create_access_token(user_id="user-1", token_version=2)

    payload = decode_token(token, expected_type="access")

    assert payload["sub"] == "user-1"
    assert payload["token_version"] == 2
    assert payload["type"] == "access"


def test_create_and_decode_refresh_token_roundtrip() -> None:
    token = create_refresh_token(user_id="user-1", token_version=0)

    payload = decode_token(token, expected_type="refresh")

    assert payload["sub"] == "user-1"
    assert payload["type"] == "refresh"


def test_decode_token_rejects_wrong_type() -> None:
    token = create_refresh_token(user_id="user-1", token_version=0)

    with pytest.raises(TokenError):
        decode_token(token, expected_type="access")


def test_decode_token_rejects_expired_token() -> None:
    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": "user-1",
        "token_version": 0,
        "type": "access",
        "iat": now - timedelta(hours=1),
        "exp": now - timedelta(minutes=1),
    }
    token = jwt.encode(expired_payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    with pytest.raises(TokenError):
        decode_token(token, expected_type="access")


def test_decode_token_rejects_tampered_token() -> None:
    token = create_access_token(user_id="user-1", token_version=0)

    with pytest.raises(TokenError):
        decode_token(token + "tampered", expected_type="access")
