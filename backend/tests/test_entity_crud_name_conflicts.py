"""Studio 实体名称冲突校验测试。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.studio import ProjectStyle, ProjectVisualStyle, Scene
from app.models.user import User
from app.services.studio.entity_crud import create_entity, update_entity

# 资产已按 user_id 隔离，测试统一归属同一个用户以验证"同用户内"的重名校验。
TEST_USER_ID = "test-user"


async def _build_session() -> tuple[AsyncSession, object]:
    """创建内存数据库会话，用于验证 service 层在 flush 前拦截重名。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = session_local()
    # 资产 user_id 是 NOT NULL 外键，先插入对应用户行满足约束。
    db.add(User(id=TEST_USER_ID, username="test-user", hashed_password="h"))
    await db.flush()
    return db, engine


def _scene(scene_id: str, name: str) -> Scene:
    """构造最小场景资产，减少测试用例中与重名校验无关的字段噪声。"""
    return Scene(
        id=scene_id,
        name=name,
        description="",
        tags=[],
        prompt_template_id=None,
        view_count=1,
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
        user_id=TEST_USER_ID,
    )


@pytest.mark.asyncio
async def test_create_scene_duplicate_name_returns_conflict() -> None:
    db, engine = await _build_session()
    try:
        db.add(_scene("scene-existing", "合江楼外景"))
        await db.flush()

        with pytest.raises(HTTPException) as exc:
            await create_entity(
                db,
                entity_type="scene",
                user_id=TEST_USER_ID,
                body={
                    "id": "scene-new",
                    "name": "合江楼外景",
                    "description": "",
                    "tags": [],
                    "prompt_template_id": None,
                    "view_count": 1,
                    "style": ProjectStyle.real_people_city.value,
                    "visual_style": ProjectVisualStyle.live_action.value,
                },
            )

        assert exc.value.status_code == 409
        assert "Scene name already exists" in str(exc.value.detail)
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_update_scene_duplicate_name_returns_conflict_before_flush() -> None:
    db, engine = await _build_session()
    try:
        db.add_all([_scene("scene-existing", "合江楼外景"), _scene("scene-draft", "未命名场景-a1")])
        await db.flush()

        with pytest.raises(HTTPException) as exc:
            await update_entity(
                db,
                entity_type="scene",
                user_id=TEST_USER_ID,
                entity_id="scene-draft",
                body={
                    "name": "合江楼外景",
                    "description": "新的场景描述",
                },
            )

        assert exc.value.status_code == 409
        assert "Scene name already exists" in str(exc.value.detail)
    finally:
        await db.close()
        await engine.dispose()
