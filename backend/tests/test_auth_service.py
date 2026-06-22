"""认证 Service 测试：登录校验与令牌刷新。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.core.security import hash_password
from app.models.user import User
from app.services import auth as auth_service


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


async def _seed_user(db: AsyncSession, **overrides: object) -> User:
    defaults: dict[str, object] = dict(
        id="user-1",
        username="alice",
        hashed_password=hash_password("s3cr3t"),
        is_admin=False,
        is_active=True,
        token_version=0,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


def test_authenticate_success_returns_token_pair() -> None:
    async def _run() -> None:
        db, engine = await _build_session()
        async with db:
            await _seed_user(db)

            tokens = await auth_service.authenticate(db, username="alice", password="s3cr3t")

            assert tokens.access_token
            assert tokens.refresh_token
        await engine.dispose()

    import asyncio
    asyncio.run(_run())


def test_authenticate_wrong_password_raises() -> None:
    async def _run() -> None:
        db, engine = await _build_session()
        async with db:
            await _seed_user(db)

            with pytest.raises(auth_service.InvalidCredentialsError):
                await auth_service.authenticate(db, username="alice", password="wrong")
        await engine.dispose()

    import asyncio
    asyncio.run(_run())


def test_authenticate_unknown_username_raises() -> None:
    async def _run() -> None:
        db, engine = await _build_session()
        async with db:
            with pytest.raises(auth_service.InvalidCredentialsError):
                await auth_service.authenticate(db, username="nobody", password="s3cr3t")
        await engine.dispose()

    import asyncio
    asyncio.run(_run())


def test_authenticate_inactive_user_raises() -> None:
    async def _run() -> None:
        db, engine = await _build_session()
        async with db:
            await _seed_user(db, is_active=False)

            with pytest.raises(auth_service.InvalidCredentialsError):
                await auth_service.authenticate(db, username="alice", password="s3cr3t")
        await engine.dispose()

    import asyncio
    asyncio.run(_run())


def test_refresh_access_token_success() -> None:
    async def _run() -> None:
        db, engine = await _build_session()
        async with db:
            await _seed_user(db)
            tokens = await auth_service.authenticate(db, username="alice", password="s3cr3t")

            result = await auth_service.refresh_access_token(db, refresh_token=tokens.refresh_token)

            assert result.access_token
        await engine.dispose()

    import asyncio
    asyncio.run(_run())


def test_refresh_access_token_revoked_raises() -> None:
    async def _run() -> None:
        db, engine = await _build_session()
        async with db:
            user = await _seed_user(db)
            tokens = await auth_service.authenticate(db, username="alice", password="s3cr3t")

            user.token_version += 1
            await db.flush()

            with pytest.raises(auth_service.InvalidTokenError):
                await auth_service.refresh_access_token(db, refresh_token=tokens.refresh_token)
        await engine.dispose()

    import asyncio
    asyncio.run(_run())


def test_refresh_access_token_invalid_token_raises() -> None:
    async def _run() -> None:
        db, engine = await _build_session()
        async with db:
            with pytest.raises(auth_service.InvalidTokenError):
                await auth_service.refresh_access_token(db, refresh_token="not-a-token")
        await engine.dispose()

    import asyncio
    asyncio.run(_run())
