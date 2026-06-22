"""生成任务（GenerationTask）按 user_id 隔离测试。

验证 SqlAlchemyTaskStore 的 create 写入 user_id，list/get/get_status_view 按 user_id 过滤：
- 任务列表只含本人发起的任务；
- 访问他人任务详情/状态按"未找到"（None）处理；
- 不传 user_id（worker 内部调用）时不做过滤，仍可取到任务（执行器需读取任务）。
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.core.task_manager import DeliveryMode, SqlAlchemyTaskStore
from app.models.user import User


async def _session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = sm()
    db.add_all([
        User(id="u1", username="a", hashed_password="h"),
        User(id="u2", username="b", hashed_password="h"),
    ])
    await db.flush()
    return db, engine


@pytest.mark.asyncio
async def test_task_list_only_includes_own() -> None:
    db, engine = await _session()
    async with db:
        store = SqlAlchemyTaskStore(db)
        t1 = await store.create({"run_args": {}}, DeliveryMode.async_polling, "image_generation", user_id="u1")
        t2 = await store.create({"run_args": {}}, DeliveryMode.async_polling, "image_generation", user_id="u2")
        await db.flush()

        items_u1, total_u1 = await store.list_task_views(user_id="u1", recent_seconds=None)
        assert total_u1 == 1
        assert {item.id for item in items_u1} == {t1.id}

        items_u2, total_u2 = await store.list_task_views(user_id="u2", recent_seconds=None)
        assert {item.id for item in items_u2} == {t2.id}
    await engine.dispose()


@pytest.mark.asyncio
async def test_task_get_rejects_other_user() -> None:
    db, engine = await _session()
    async with db:
        store = SqlAlchemyTaskStore(db)
        t1 = await store.create({"run_args": {}}, DeliveryMode.async_polling, "video_generation", user_id="u1")
        await db.flush()

        assert (await store.get(t1.id, user_id="u1")) is not None
        # 他人访问按未找到处理
        assert (await store.get(t1.id, user_id="u2")) is None
        # worker 内部调用（不传 user_id）不过滤，仍可取到
        assert (await store.get(t1.id)) is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_task_status_view_rejects_other_user() -> None:
    db, engine = await _session()
    async with db:
        store = SqlAlchemyTaskStore(db)
        t1 = await store.create({"run_args": {}}, DeliveryMode.async_polling, "image_generation", user_id="u1")
        await db.flush()

        assert (await store.get_status_view(t1.id, user_id="u1")) is not None
        assert (await store.get_status_view(t1.id, user_id="u2")) is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_writes_user_id() -> None:
    db, engine = await _session()
    async with db:
        store = SqlAlchemyTaskStore(db)
        rec = await store.create({"run_args": {}}, DeliveryMode.async_polling, "image_generation", user_id="u1")
        assert rec.user_id == "u1"
    await engine.dispose()
