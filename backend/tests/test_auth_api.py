"""认证 API 测试：登录、刷新、当前用户信息，以及全局鉴权挂载。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.core.security import hash_password
from app.dependencies import get_db
from app.main import app
from app.models.user import User


@pytest.fixture
def auth_client() -> TestClient:
    """用内存数据库创建 FastAPI TestClient 并注入依赖覆盖。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _setup() -> None:
        """初始化 DB schema 并创建测试用户。"""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_local() as session:
            session.add(
                User(
                    id="admin-1",
                    username="admin",
                    hashed_password=hash_password("admin-pass"),
                    is_admin=True,
                    is_active=True,
                    token_version=0,
                )
            )
            await session.commit()

    asyncio.run(_setup())

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        """依赖覆盖：用测试 DB session 替代生产 DB session。"""
        async with session_local() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_login_success_returns_token_pair(auth_client: TestClient) -> None:
    """POST /api/v1/auth/login 成功返回令牌对。"""
    resp = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-pass"})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["access_token"]
    assert data["refresh_token"]


def test_login_wrong_password_returns_401(auth_client: TestClient) -> None:
    """POST /api/v1/auth/login 密码错误返回 401。"""
    resp = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})

    assert resp.status_code == 401


def test_me_with_valid_token_returns_user(auth_client: TestClient) -> None:
    """GET /api/v1/auth/me 用有效令牌返回当前用户信息。"""
    login_resp = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-pass"})
    access_token = login_resp.json()["data"]["access_token"]

    resp = auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})

    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "admin"


def test_refresh_returns_new_access_token(auth_client: TestClient) -> None:
    """POST /api/v1/auth/refresh 用 refresh_token 返回新 access_token。"""
    login_resp = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-pass"})
    refresh_token = login_resp.json()["data"]["refresh_token"]

    resp = auth_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

    assert resp.status_code == 200
    assert resp.json()["data"]["access_token"]


def test_protected_route_without_token_returns_401(auth_client: TestClient) -> None:
    """受保护路由（/api/v1/studio/projects）没有令牌返回 401。"""
    resp = auth_client.get("/api/v1/studio/projects")

    assert resp.status_code == 401


def test_protected_route_with_valid_token_succeeds(auth_client: TestClient) -> None:
    """受保护路由（/api/v1/studio/projects）用有效令牌返回 200。"""
    login_resp = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-pass"})
    access_token = login_resp.json()["data"]["access_token"]

    resp = auth_client.get("/api/v1/studio/projects", headers={"Authorization": f"Bearer {access_token}"})

    assert resp.status_code == 200
