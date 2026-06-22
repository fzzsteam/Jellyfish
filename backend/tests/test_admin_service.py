"""管理员用户 CRUD service 测试。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.core.security import verify_password
from app.models.user import User
from app.services import admin as admin_service


async def _session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = sm()
    db.add(User(id="admin-1", username="admin", hashed_password="h", is_admin=True))
    await db.flush()
    return db, engine


@pytest.mark.asyncio
async def test_create_user_hashes_password() -> None:
    db, engine = await _session()
    async with db:
        user = await admin_service.create_user(db, username="bob", password="secret123", is_admin=False)
        assert user.username == "bob"
        assert user.hashed_password != "secret123"
        assert verify_password("secret123", user.hashed_password)
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_user_duplicate_username_raises() -> None:
    db, engine = await _session()
    async with db:
        await admin_service.create_user(db, username="bob", password="secret123", is_admin=False)
        with pytest.raises(admin_service.UsernameExistsError):
            await admin_service.create_user(db, username="bob", password="other123", is_admin=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_user_reset_password_bumps_token_version() -> None:
    db, engine = await _session()
    async with db:
        user = await admin_service.create_user(db, username="bob", password="secret123", is_admin=False)
        before = user.token_version
        updated = await admin_service.update_user(db, user.id, password="newpass123")
        assert verify_password("newpass123", updated.hashed_password)
        assert updated.token_version == before + 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_user_disable_bumps_token_version() -> None:
    db, engine = await _session()
    async with db:
        user = await admin_service.create_user(db, username="bob", password="secret123", is_admin=False)
        before = user.token_version
        updated = await admin_service.update_user(db, user.id, is_active=False)
        assert updated.is_active is False
        assert updated.token_version == before + 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_unknown_user_raises() -> None:
    db, engine = await _session()
    async with db:
        with pytest.raises(admin_service.UserNotFoundError):
            await admin_service.update_user(db, "nope", is_active=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_cannot_disable_last_admin() -> None:
    db, engine = await _session()
    async with db:
        with pytest.raises(admin_service.LastAdminError):
            await admin_service.update_user(db, "admin-1", is_active=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_users_paginated() -> None:
    db, engine = await _session()
    async with db:
        await admin_service.create_user(db, username="bob", password="secret123", is_admin=False)
        items, total = await admin_service.list_users(db, page=1, page_size=10)
        assert total == 2  # admin + bob
        assert {u.username for u in items} == {"admin", "bob"}
    await engine.dispose()
