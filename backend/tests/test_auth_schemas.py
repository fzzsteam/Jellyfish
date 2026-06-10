"""认证 Schema 校验测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RefreshRequest, TokenPairRead, UserRead


def test_login_request_accepts_valid_payload() -> None:
    req = LoginRequest(username="admin", password="secret")

    assert req.username == "admin"
    assert req.password == "secret"


def test_login_request_rejects_empty_username() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(username="", password="secret")


def test_refresh_request_requires_token() -> None:
    with pytest.raises(ValidationError):
        RefreshRequest()  # type: ignore[call-arg]


def test_token_pair_read_defaults_token_type_to_bearer() -> None:
    pair = TokenPairRead(access_token="a", refresh_token="b")

    assert pair.token_type == "bearer"


def test_user_read_from_attributes() -> None:
    class _FakeUser:
        id = "u1"
        username = "alice"
        is_admin = False
        is_active = True

    data = UserRead.model_validate(_FakeUser())

    assert data.id == "u1"
    assert data.username == "alice"
    assert data.is_admin is False
    assert data.is_active is True
