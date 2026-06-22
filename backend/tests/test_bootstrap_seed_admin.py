"""初始管理员播种测试：幂等创建、已存在时跳过、未配置密码时拒绝。"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.bootstrap import seed_initial_admin
from app.config import settings
from app.core.db import Base
from app.models.user import User


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


@pytest.mark.asyncio
async def test_seed_creates_admin_when_none_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "initial_admin_password", "init-pass")
    monkeypatch.setattr(settings, "initial_admin_username", "admin")
    db, engine = await _build_session()
    async with db:
        await seed_initial_admin(db)

        result = await db.execute(select(User).where(User.is_admin.is_(True)))
        admin = result.scalars().one()
        assert admin.username == "admin"
    await engine.dispose()


@pytest.mark.asyncio
async def test_seed_is_idempotent_when_admin_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "initial_admin_password", "init-pass")
    db, engine = await _build_session()
    async with db:
        await seed_initial_admin(db)
        await seed_initial_admin(db)

        result = await db.execute(select(User).where(User.is_admin.is_(True)))
        admins = result.scalars().all()
        assert len(admins) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_seed_raises_when_password_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "initial_admin_password", None)
    db, engine = await _build_session()
    async with db:
        with pytest.raises(RuntimeError):
            await seed_initial_admin(db)
    await engine.dispose()
