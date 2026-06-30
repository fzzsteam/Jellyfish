"""Auto-cascade 计费修复测试（Task 8b：auto-prepare 图片 + auto-extract 文本）。

覆盖 divide/extract 异步任务 ``apply_result`` 级联中两类此前漏费的场景：

Part A — auto-prepare 图片任务（``_schedule_image_task_sync``）：
- 正常：每张图片在创建 GenerationTask 行之前冻结积分，billing_id 写入任务行。
- 余额不足：该图片跳过（不建任务、不冻结），级联继续，其它图片仍处理。
- 任务行创建失败：已冻结的积分被解冻，不泄漏。

Part B — auto-extract 文本（``apply_auto_extraction_after_division``）：
- 缓存未命中：冻结 → LLM 调用 → consume。
- 缓存命中：冻结 → LLM 未调用 → unfreeze（用户免费）。
- 余额不足：跳过提取，auto-prep 仍执行。

测试策略：
- 内存 SQLite（同步 + 异步引擎指向同一库是不现实的，因此分别构造；
  异步账本调用通过 monkeypatch ``app.core.db.async_session_maker`` 指向异步引擎）。
- fakeredis 替换 ``ledger._redis_factory``。
- 直接构造 Session 调用被测函数，绕开 Celery。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base
import app.core.db as core_db
from app.models.llm import Model, ModelCategoryKey, ModelSettings, Provider
from app.models.points import PointTransaction, PointTransactionType
from app.models.studio import (
    Chapter,
    Project,
    ProjectStyle,
    ProjectVisualStyle,
    Shot,
    ShotDetail,
    ShotStatus,
)
from app.models.task import GenerationTask, GenerationTaskStatus
from app.models.user import User
from app.services.points import ledger
from app.services.points.ledger import recharge
from app.services.studio.shot_auto_preparation import (
    AutoPreparationSummary,
    _schedule_image_task_sync,
)


USER_ID = "u1"
IMAGE_UNIT_POINTS = 5
TEXT_UNIT_POINTS = 7


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    """将账本 Redis 工厂替换为 fakeredis。"""
    client = FakeRedis()

    def _factory():
        return client

    monkeypatch.setattr(ledger, "_redis_factory", _factory)
    yield client


def _import_all_models() -> None:
    """触发所有相关 ORM 模块注册到 Base.metadata。"""
    import app.models.llm  # noqa: F401
    import app.models.points  # noqa: F401
    import app.models.task  # noqa: F401
    import app.models.task_links  # noqa: F401
    import app.models.studio  # noqa: F401


def _build_engines() -> tuple[Any, Any, Any, Any]:
    """构造指向同一内存库的同步与异步引擎 + session 工厂。

    SQLite 内存库每个连接独立，因此用单一连接桥接同步/异步：异步引擎开
    ``StaticPool``，同步引擎也用 ``StaticPool`` 共享同一文件库。
    """
    from sqlalchemy.pool import StaticPool

    # 异步引擎（账本用）
    async_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    # 同步引擎（业务用）——独立内存库；测试在异步库建表+种子，同步库仅读 task 行
    # （task 行在同步库内创建，异步账本只读写 points 表，两库表结构相同即可）
    sync_engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    sync_session_local = sessionmaker(sync_engine, class_=Session, expire_on_commit=False)

    _import_all_models()
    Base.metadata.create_all(sync_engine)
    return async_engine, async_session_local, sync_engine, sync_session_local


def _seed_sync(db: Session) -> None:
    """在同步库中预置 user/provider/model/settings/project/chapter。"""
    db.add(User(id=USER_ID, username="u1", hashed_password="x", is_active=True, token_version=0))
    db.add(Provider(id="p1", name="prov", base_url="http://x", api_key="k"))
    db.add(
        Model(
            id="m_img",
            name="img-model",
            category=ModelCategoryKey.image,
            provider_id="p1",
            unit_points=IMAGE_UNIT_POINTS,
        )
    )
    db.add(
        ModelSettings(
            user_id=USER_ID,
            default_image_model_id="m_img",
            default_text_model_id="m_text",
        )
    )
    db.add(
        Project(
            id="proj-1",
            name="P",
            style=ProjectStyle.real_people_city,
            visual_style=ProjectVisualStyle.live_action,
            user_id=USER_ID,
        )
    )
    db.add(Chapter(id="ch-1", project_id="proj-1", index=1, title="第一章"))
    db.flush()


async def _seed_async(async_session_local) -> None:
    """在异步库中建表并预置 user/provider/model/settings（账本冻结需要 user_points 行）。"""
    from app.core.db import Base as _Base

    # 取底层 engine 建表
    async with async_session_local().bind.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
    async with async_session_local() as db:
        db.add(User(id=USER_ID, username="u1", hashed_password="x", is_active=True, token_version=0))
        db.add(Provider(id="p1", name="prov", base_url="http://x", api_key="k"))
        db.add(
            Model(
                id="m_img",
                name="img-model",
                category=ModelCategoryKey.image,
                provider_id="p1",
                unit_points=IMAGE_UNIT_POINTS,
            )
        )
        db.add(
            Model(
                id="m_text",
                name="text-model",
                category=ModelCategoryKey.text,
                provider_id="p1",
                unit_points=TEXT_UNIT_POINTS,
            )
        )
        db.add(
            ModelSettings(
                user_id=USER_ID,
                default_image_model_id="m_img",
                default_text_model_id="m_text",
            )
        )
        await db.commit()
        # 充值保证余额充足
        await recharge(db, user_id=USER_ID, amount=1000, created_by="admin", remark="seed")
        await db.commit()


async def _seed_async_empty(async_session_local) -> None:
    """异步库建表 + 仅建 user（无充值），用于余额不足场景。"""
    from app.core.db import Base as _Base

    async with async_session_local().bind.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
    async with async_session_local() as db:
        db.add(User(id=USER_ID, username="u1", hashed_password="x", is_active=True, token_version=0))
        await db.commit()


def _patch_async_session_maker(monkeypatch, async_session_local) -> None:
    """把 app.core.db.async_session_maker 指向测试的异步 session 工厂。"""
    monkeypatch.setattr(core_db, "async_session_maker", async_session_local)
    # 桥接函数内部 from app.core.db import async_session_maker 是模块级导入，
    # 因此 patch 模块属性即可生效（函数体内每次 import 读取最新模块属性）。


# ---------------------------------------------------------------------------
# Part A：auto-prepare 图片任务计费
# ---------------------------------------------------------------------------


def test_image_task_freeze_and_billing_id(monkeypatch) -> None:
    """创建图片任务前应冻结积分，且 billing_id 写入 GenerationTask 行。"""
    async_engine, async_session_local, sync_engine, sync_session_local = _build_engines()
    import asyncio

    asyncio.run(_seed_async(async_session_local))
    _patch_async_session_maker(monkeypatch, async_session_local)

    db = sync_session_local()
    try:
        _seed_sync(db)
        summary = AutoPreparationSummary()
        run_args = {
            "provider": "openai",
            "api_key": "k",
            "base_url": "http://x",
            "relation_type": "scene_image",
            "relation_entity_id": "ent-1",
            "input": {"prompt": "p", "model": "img-model", "purpose": "generic"},
        }
        _schedule_image_task_sync(
            db,
            user_id=USER_ID,
            run_args=run_args,
            summary=summary,
            model_id="m_img",
            unit_points=IMAGE_UNIT_POINTS,
        )
        db.commit()

        # 任务行已创建且携带 billing_id
        assert len(summary.image_task_ids) == 1
        task_id = summary.image_task_ids[0]
        task = db.get(GenerationTask, task_id)
        assert task is not None
        assert task.billing_id is not None
        assert task.task_kind == "image_generation"

        # 异步库存在对应 freeze 流水
        async def _check():
            async with async_session_local() as adb:
                frz = (
                    await adb.execute(
                        select(PointTransaction).where(
                            PointTransaction.billing_id == task.billing_id,
                            PointTransaction.type == PointTransactionType.freeze,
                        )
                    )
                ).scalar_one_or_none()
                assert frz is not None
                assert frz.amount == IMAGE_UNIT_POINTS

        asyncio.run(_check())
    finally:
        db.close()
        sync_engine.dispose()


def test_image_task_insufficient_balance_skipped(monkeypatch) -> None:
    """余额不足时该图片被跳过：无任务、无冻结，summary 不增加。"""
    async_engine, async_session_local, sync_engine, sync_session_local = _build_engines()
    import asyncio

    # 异步库不充值 → 余额为 0
    asyncio.run(_seed_async_empty(async_session_local))
    _patch_async_session_maker(monkeypatch, async_session_local)

    db = sync_session_local()
    try:
        summary = AutoPreparationSummary()
        run_args = {
            "provider": "openai",
            "api_key": "k",
            "base_url": "http://x",
            "relation_type": "scene_image",
            "relation_entity_id": "ent-2",
            "input": {"prompt": "p", "model": "img-model", "purpose": "generic"},
        }
        _schedule_image_task_sync(
            db,
            user_id=USER_ID,
            run_args=run_args,
            summary=summary,
            model_id="m_img",
            unit_points=IMAGE_UNIT_POINTS,
        )
        db.commit()

        # 无任务、无冻结
        assert summary.image_task_ids == []
        tasks = db.execute(select(GenerationTask)).scalars().all()
        assert len(tasks) == 0
    finally:
        db.close()
        sync_engine.dispose()


def test_image_task_creation_failure_unfreezes(monkeypatch) -> None:
    """任务行创建失败（begin_nested 抛错）时应解冻已落库的冻结，不泄漏。"""
    async_engine, async_session_local, sync_engine, sync_session_local = _build_engines()
    import asyncio

    asyncio.run(_seed_async(async_session_local))
    _patch_async_session_maker(monkeypatch, async_session_local)

    db = sync_session_local()
    try:
        _seed_sync(db)
        summary = AutoPreparationSummary()
        run_args = {
            "relation_type": "scene_image",
            "relation_entity_id": "ent-3",
        }

        # 让 begin_nested 抛错模拟任务行创建失败
        import contextlib

        class _Boom:
            def __enter__(self):
                raise RuntimeError("injected boom")

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(db, "begin_nested", lambda: _Boom())

        _schedule_image_task_sync(
            db,
            user_id=USER_ID,
            run_args=run_args,
            summary=summary,
            model_id="m_img",
            unit_points=IMAGE_UNIT_POINTS,
        )

        # 无任务被记录
        assert summary.image_task_ids == []

        # 冻结已被解冻：异步库无悬挂 freeze（freeze + unfreeze 成对）
        async def _check():
            async with async_session_local() as adb:
                freezes = (
                    await adb.execute(
                        select(PointTransaction).where(
                            PointTransaction.type == PointTransactionType.freeze
                        )
                    )
                ).scalars().all()
                unfreezes = (
                    await adb.execute(
                        select(PointTransaction).where(
                            PointTransaction.type == PointTransactionType.unfreeze
                        )
                    )
                ).scalars().all()
                assert len(freezes) == 1
                assert len(unfreezes) == 1
                assert freezes[0].billing_id == unfreezes[0].billing_id

        asyncio.run(_check())
    finally:
        db.close()
        sync_engine.dispose()


# ---------------------------------------------------------------------------
# Part B：auto-extract 文本计费（cache-aware）
# ---------------------------------------------------------------------------


def test_auto_extract_cache_miss_consumes(monkeypatch) -> None:
    """缓存未命中（LLM 已调用）→ 冻结随后消费。"""
    import asyncio
    from app.services import script_processing_worker as worker
    from app.schemas.skills.script_processing import ScriptDivisionResult

    async_engine, async_session_local, sync_engine, sync_session_local = _build_engines()
    asyncio.run(_seed_async(async_session_local))
    _patch_async_session_maker(monkeypatch, async_session_local)

    # 同步库也要建 m_text 模型行（_require_provider_and_model_sync 会读）
    db = sync_session_local()
    try:
        _seed_sync(db)
        db.add(
            Model(
                id="m_text",
                name="text-model",
                category=ModelCategoryKey.text,
                provider_id="p1",
                unit_points=TEXT_UNIT_POINTS,
            )
        )
        db.flush()

        # stub generate_extraction_result 返回 from_cache=False
        from app.schemas.skills.script_processing import StudioScriptExtractionDraft

        draft = StudioScriptExtractionDraft(
            project_id="proj-1", chapter_id="ch-1", script_text="", shots=[]
        )
        monkeypatch.setattr(
            worker,
            "generate_extraction_result",
            lambda **kw: (draft, False),
        )
        # stub apply_extraction_result 与 auto_prepare_chapter_shots_sync 为 no-op
        monkeypatch.setattr(worker, "apply_extraction_result", lambda *a, **kw: None)
        monkeypatch.setattr(
            worker,
            "auto_prepare_chapter_shots_sync",
            lambda *a, **kw: AutoPreparationSummary(),
        )

        result = ScriptDivisionResult(shots=[], total_shots=0)
        worker.apply_auto_extraction_after_division(
            db, user_id=USER_ID, chapter_id="ch-1", result=result
        )

        # 异步库：1 freeze + 1 consume，0 unfreeze
        async def _check():
            async with async_session_local() as adb:
                freezes = (await adb.execute(
                    select(PointTransaction).where(PointTransaction.type == PointTransactionType.freeze)
                )).scalars().all()
                consumes = (await adb.execute(
                    select(PointTransaction).where(PointTransaction.type == PointTransactionType.consume)
                )).scalars().all()
                unfreezes = (await adb.execute(
                    select(PointTransaction).where(PointTransaction.type == PointTransactionType.unfreeze)
                )).scalars().all()
                assert len(freezes) == 1
                assert len(consumes) == 1
                assert len(unfreezes) == 0
                assert freezes[0].billing_id == consumes[0].billing_id
                assert freezes[0].amount == TEXT_UNIT_POINTS

        asyncio.run(_check())
    finally:
        db.close()
        sync_engine.dispose()


def test_auto_extract_cache_hit_unfreezes(monkeypatch) -> None:
    """缓存命中（LLM 未调用）→ 冻结随后解冻（用户免费）。"""
    import asyncio
    from app.services import script_processing_worker as worker
    from app.schemas.skills.script_processing import ScriptDivisionResult, StudioScriptExtractionDraft

    async_engine, async_session_local, sync_engine, sync_session_local = _build_engines()
    asyncio.run(_seed_async(async_session_local))
    _patch_async_session_maker(monkeypatch, async_session_local)

    db = sync_session_local()
    try:
        _seed_sync(db)
        db.add(
            Model(
                id="m_text",
                name="text-model",
                category=ModelCategoryKey.text,
                provider_id="p1",
                unit_points=TEXT_UNIT_POINTS,
            )
        )
        db.flush()

        draft = StudioScriptExtractionDraft(
            project_id="proj-1", chapter_id="ch-1", script_text="", shots=[]
        )
        monkeypatch.setattr(
            worker,
            "generate_extraction_result",
            lambda **kw: (draft, True),  # from_cache=True
        )
        monkeypatch.setattr(worker, "apply_extraction_result", lambda *a, **kw: None)
        monkeypatch.setattr(
            worker,
            "auto_prepare_chapter_shots_sync",
            lambda *a, **kw: AutoPreparationSummary(),
        )

        worker.apply_auto_extraction_after_division(
            db, user_id=USER_ID, chapter_id="ch-1", result=ScriptDivisionResult(shots=[], total_shots=0)
        )

        async def _check():
            async with async_session_local() as adb:
                freezes = (await adb.execute(
                    select(PointTransaction).where(PointTransaction.type == PointTransactionType.freeze)
                )).scalars().all()
                unfreezes = (await adb.execute(
                    select(PointTransaction).where(PointTransaction.type == PointTransactionType.unfreeze)
                )).scalars().all()
                consumes = (await adb.execute(
                    select(PointTransaction).where(PointTransaction.type == PointTransactionType.consume)
                )).scalars().all()
                assert len(freezes) == 1
                assert len(unfreezes) == 1
                assert len(consumes) == 0
                assert freezes[0].billing_id == unfreezes[0].billing_id

        asyncio.run(_check())
    finally:
        db.close()
        sync_engine.dispose()


def test_auto_extract_empty_draft_does_not_mark_shot_extracted(monkeypatch) -> None:
    """整章空提取草稿不应写 last_extracted_at，避免前端误显示“已提取无结果”。"""
    import asyncio
    from app.services import script_processing_worker as worker
    from app.schemas.skills.script_processing import ScriptDivisionResult, ShotDivision, StudioScriptExtractionDraft

    async_engine, async_session_local, sync_engine, sync_session_local = _build_engines()
    asyncio.run(_seed_async(async_session_local))
    _patch_async_session_maker(monkeypatch, async_session_local)

    db = sync_session_local()
    try:
        _seed_sync(db)
        db.add(
            Model(
                id="m_text",
                name="text-model",
                category=ModelCategoryKey.text,
                provider_id="p1",
                unit_points=TEXT_UNIT_POINTS,
            )
        )
        db.add(
            Shot(
                id="shot-empty",
                chapter_id="ch-1",
                index=1,
                title="空提取镜头",
                script_excerpt="朝云端茶入室，苏东坡颔首。",
                status=ShotStatus.pending,
            )
        )
        db.flush()

        draft = StudioScriptExtractionDraft(
            project_id="proj-1",
            chapter_id="ch-1",
            script_text="朝云端茶入室，苏东坡颔首。",
            shots=[],
        )
        monkeypatch.setattr(worker, "generate_extraction_result", lambda **kw: (draft, True))

        result = ScriptDivisionResult(
            shots=[
                ShotDivision(
                    index=1,
                    start_line=1,
                    end_line=1,
                    script_excerpt="朝云端茶入室，苏东坡颔首。",
                    shot_name="朝云端茶",
                )
            ],
            total_shots=1,
        )
        worker.apply_auto_extraction_after_division(
            db,
            user_id=USER_ID,
            chapter_id="ch-1",
            result=result,
        )

        shot = db.get(Shot, "shot-empty")
        assert shot is not None
        assert shot.last_extracted_at is None
        assert shot.status == ShotStatus.pending
    finally:
        db.close()
        sync_engine.dispose()


def test_auto_extract_insufficient_balance_skips_extraction(monkeypatch) -> None:
    """余额不足 → 跳过 auto-extract，但 auto-prep 仍执行。"""
    import asyncio
    from app.services import script_processing_worker as worker
    from app.schemas.skills.script_processing import ScriptDivisionResult

    async_engine, async_session_local, sync_engine, sync_session_local = _build_engines()
    # 异步库不充值 → 余额 0
    asyncio.run(_seed_async_empty(async_session_local))
    _patch_async_session_maker(monkeypatch, async_session_local)

    db = sync_session_local()
    try:
        _seed_sync(db)
        db.add(
            Model(
                id="m_text",
                name="text-model",
                category=ModelCategoryKey.text,
                provider_id="p1",
                unit_points=TEXT_UNIT_POINTS,
            )
        )
        db.flush()

        called = {"extract": 0, "prep": 0}
        from app.schemas.skills.script_processing import StudioScriptExtractionDraft

        def _fake_extract(**kw):
            called["extract"] += 1
            return (StudioScriptExtractionDraft(
                project_id="proj-1", chapter_id="ch-1", script_text="", shots=[]
            ), False)

        def _fake_prep(*a, **kw):
            called["prep"] += 1
            return AutoPreparationSummary()

        monkeypatch.setattr(worker, "generate_extraction_result", _fake_extract)
        monkeypatch.setattr(worker, "apply_extraction_result", lambda *a, **kw: None)
        monkeypatch.setattr(worker, "auto_prepare_chapter_shots_sync", _fake_prep)

        worker.apply_auto_extraction_after_division(
            db, user_id=USER_ID, chapter_id="ch-1", result=ScriptDivisionResult(shots=[], total_shots=0)
        )

        # 提取被跳过，auto-prep 仍执行
        assert called["extract"] == 0
        assert called["prep"] == 1

        # 无任何积分流水
        async def _check():
            async with async_session_local() as adb:
                txs = (await adb.execute(select(PointTransaction))).scalars().all()
                assert len(txs) == 0

        asyncio.run(_check())
    finally:
        db.close()
        sync_engine.dispose()
