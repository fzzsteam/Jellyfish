"""User 模型基础测试：建表、字段默认值与唯一约束。"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.user import User


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


@pytest.mark.asyncio
async def test_user_model_defaults() -> None:
    db, engine = await _build_session()
    async with db:
        user = User(id="u1", username="alice", hashed_password="hashed")
        db.add(user)
        await db.flush()
        await db.refresh(user)

        assert user.is_admin is False
        assert user.is_active is True
        assert user.token_version == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_username_unique_constraint() -> None:
    db, engine = await _build_session()
    async with db:
        db.add(User(id="u1", username="alice", hashed_password="hashed"))
        await db.flush()

        db.add(User(id="u2", username="alice", hashed_password="hashed2"))
        with pytest.raises(IntegrityError):
            await db.flush()
    await engine.dispose()
