"""资产按 user_id 隔离 + 同名跨用户不冲突测试。

验证两件事：
1. 用户只能列出自己的资产（actor/scene/prop/costume），看不到别人的；
2. 同名资产在不同用户间互不冲突（验证 `(user_id, name)` 每用户唯一约束）。
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.user import User
from app.services.studio.entity_crud import create_entity, list_entities_paginated


async def _session() -> tuple[AsyncSession, object]:
    """构造内存库会话并预置两个用户，满足 user_id 外键。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = sm()
    db.add_all(
        [
            User(id="u1", username="a", hashed_password="h"),
            User(id="u2", username="b", hashed_password="h"),
        ]
    )
    await db.flush()
    return db, engine


@pytest.mark.asyncio
async def test_list_assets_only_returns_own() -> None:
    """列表只返回当前用户自己的资产。"""
    db, engine = await _session()
    async with db:
        await create_entity(db, entity_type="actor", user_id="u1", body={"id": "a1", "name": "甲", "style": "真人都市"})
        await create_entity(db, entity_type="actor", user_id="u2", body={"id": "a2", "name": "乙", "style": "真人都市"})
        await db.flush()

        u1_items, u1_total = await list_entities_paginated(
            db,
            entity_type="actor",
            user_id="u1",
            q=None,
            style=None,
            visual_style=None,
            order=None,
            is_desc=False,
            page=1,
            page_size=10,
        )
        assert u1_total == 1
        assert {item["id"] for item in u1_items} == {"a1"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_same_actor_name_allowed_across_users() -> None:
    """不同用户可使用同名资产，不触发唯一约束。"""
    db, engine = await _session()
    async with db:
        await create_entity(db, entity_type="actor", user_id="u1", body={"id": "a1", "name": "主角", "style": "真人都市"})
        # 不同用户同名应成功
        await create_entity(db, entity_type="actor", user_id="u2", body={"id": "a2", "name": "主角", "style": "真人都市"})
        await db.flush()

        u1_items, _ = await list_entities_paginated(
            db,
            entity_type="actor",
            user_id="u1",
            q=None,
            style=None,
            visual_style=None,
            order=None,
            is_desc=False,
            page=1,
            page_size=10,
        )
        assert {item["id"] for item in u1_items} == {"a1"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_same_user_duplicate_name_rejected() -> None:
    """同一用户内重名仍被拒绝（按用户判重）。"""
    from fastapi import HTTPException

    db, engine = await _session()
    async with db:
        await create_entity(db, entity_type="scene", user_id="u1", body={"id": "s1", "name": "客厅", "style": "真人都市"})
        with pytest.raises(HTTPException):
            await create_entity(
                db, entity_type="scene", user_id="u1", body={"id": "s2", "name": "客厅", "style": "真人都市"}
            )
    await engine.dispose()
