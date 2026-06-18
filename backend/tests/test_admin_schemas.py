"""管理员用户 Schema 校验测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.auth import UserAdminRead, UserCreate, UserUpdate


def test_user_create_requires_username_and_password() -> None:
    req = UserCreate(username="bob", password="secret123")
    assert req.username == "bob"
    assert req.is_admin is False


def test_user_create_rejects_short_password() -> None:
    with pytest.raises(ValidationError):
        UserCreate(username="bob", password="x")


def test_user_update_all_optional() -> None:
    upd = UserUpdate()
    assert upd.password is None
    assert upd.is_active is None
    assert upd.is_admin is None


def test_user_admin_read_from_attributes() -> None:
    class _U:
        id = "u1"
        username = "bob"
        is_admin = False
        is_active = True

    data = UserAdminRead.model_validate(_U())
    assert data.id == "u1"
    assert data.is_active is True
