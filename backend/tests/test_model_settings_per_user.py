"""model_settings 每用户一行语义测试。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.user import User
from app.services.llm import manage as llm_manage


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = session_local()
    db.add(User(id="u1", username="a", hashed_password="h"))
    db.add(User(id="u2", username="b", hashed_password="h"))
    await db.flush()
    return db, engine


@pytest.mark.asyncio
async def test_get_or_create_settings_is_per_user() -> None:
    db, engine = await _build_session()
    async with db:
        s1 = await llm_manage.get_or_create_settings(db, user_id="u1")
        s1_again = await llm_manage.get_or_create_settings(db, user_id="u1")
        s2 = await llm_manage.get_or_create_settings(db, user_id="u2")

        assert s1.user_id == "u1"
        assert s1.id == s1_again.id  # 幂等：同用户拿到同一行
        assert s2.user_id == "u2"
        assert s1.id != s2.id  # 不同用户不同行
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_model_settings_isolated() -> None:
    db, engine = await _build_session()
    async with db:
        await llm_manage.update_model_settings(db, user_id="u1", api_timeout=99)
        s1 = await llm_manage.get_model_settings(db, user_id="u1")
        s2 = await llm_manage.get_model_settings(db, user_id="u2")

        assert s1.api_timeout == 99
        assert s2.api_timeout == 30  # 默认值，未被 u1 的修改影响
    await engine.dispose()
