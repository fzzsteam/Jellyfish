"""get_current_user / require_admin 依赖测试。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.core.security import create_access_token, hash_password
from app.dependencies import get_current_user, get_db, require_admin
from app.models.user import User


def _build_test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    async def protected(current_user: User = Depends(get_current_user)) -> dict[str, str]:
        return {"user_id": current_user.id}

    @app.get("/admin-only")
    async def admin_only(current_user: User = Depends(require_admin)) -> dict[str, str]:
        return {"user_id": current_user.id}

    return app


@pytest.fixture
def auth_test_client() -> TestClient:
    app = _build_test_app()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_local() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_local() as session:
            session.add(
                User(id="u1", username="alice", hashed_password=hash_password("pw"), is_admin=False, is_active=True, token_version=0)
            )
            session.add(
                User(id="u2", username="bob", hashed_password=hash_password("pw"), is_admin=True, is_active=True, token_version=0)
            )
            session.add(
                User(id="u3", username="carol", hashed_password=hash_password("pw"), is_admin=False, is_active=False, token_version=5)
            )
            await session.commit()

    asyncio.run(_setup())

    return TestClient(app)


def test_protected_without_token_returns_401(auth_test_client: TestClient) -> None:
    resp = auth_test_client.get("/protected")

    assert resp.status_code == 401


def test_protected_with_invalid_token_returns_401(auth_test_client: TestClient) -> None:
    resp = auth_test_client.get("/protected", headers={"Authorization": "Bearer not-a-token"})

    assert resp.status_code == 401


def test_protected_with_valid_token_returns_user(auth_test_client: TestClient) -> None:
    token = create_access_token(user_id="u1", token_version=0)

    resp = auth_test_client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json()["user_id"] == "u1"


def test_protected_with_inactive_user_returns_401(auth_test_client: TestClient) -> None:
    token = create_access_token(user_id="u3", token_version=5)

    resp = auth_test_client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401


def test_admin_only_rejects_non_admin(auth_test_client: TestClient) -> None:
    token = create_access_token(user_id="u1", token_version=0)

    resp = auth_test_client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 403


def test_admin_only_allows_admin(auth_test_client: TestClient) -> None:
    token = create_access_token(user_id="u2", token_version=0)

    resp = auth_test_client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
