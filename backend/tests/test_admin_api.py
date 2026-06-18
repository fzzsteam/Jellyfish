"""管理员 API 测试：鉴权、用户 CRUD、查看某用户项目。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.core.security import hash_password
from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.user import User


@pytest.fixture
def admin_client() -> TestClient:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sm() as s:
            s.add(User(id="admin-1", username="admin", hashed_password=hash_password("pw"), is_admin=True))
            s.add(User(id="user-1", username="bob", hashed_password=hash_password("pw"), is_admin=False))
            await s.commit()

    asyncio.run(_setup())

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        async with sm() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    async def _admin_user() -> User:
        return User(id="admin-1", username="admin", hashed_password="x", is_admin=True, is_active=True)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _admin_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_list_users(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/v1/admin/users")
    assert resp.status_code == 200
    assert resp.json()["data"]["pagination"]["total"] == 2


def test_create_user(admin_client: TestClient) -> None:
    resp = admin_client.post("/api/v1/admin/users", json={"username": "carol", "password": "secret123"})
    assert resp.status_code == 201
    assert resp.json()["data"]["username"] == "carol"


def test_create_duplicate_user_returns_409(admin_client: TestClient) -> None:
    resp = admin_client.post("/api/v1/admin/users", json={"username": "bob", "password": "secret123"})
    assert resp.status_code == 409


def test_get_user_detail(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/v1/admin/users/user-1")
    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "bob"


def test_patch_user_disable(admin_client: TestClient) -> None:
    resp = admin_client.patch("/api/v1/admin/users/user-1", json={"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["data"]["is_active"] is False


def test_list_user_projects_empty(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/v1/admin/users/user-1/projects")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_non_admin_forbidden() -> None:
    # 覆盖：require_admin 对非管理员返回 403（用独立的 override）
    async def _normal_user() -> User:
        return User(id="user-1", username="bob", hashed_password="x", is_admin=False, is_active=True)

    app.dependency_overrides[get_current_user] = _normal_user
    try:
        client = TestClient(app)
        resp = client.get("/api/v1/admin/users")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
