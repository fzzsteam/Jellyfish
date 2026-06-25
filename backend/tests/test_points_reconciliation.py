"""积分冻结补偿（reconciliation）的契约测试。

校验内容（对应 Task 7 设计的 7 类场景 + 幂等/容错）：
- succeeded 任务 + 过期 freeze → 补 consume，余额下降。
- failed 任务 + 过期 freeze → 补 unfreeze，余额恢复。
- cancelled 任务 + 过期 freeze → 补 unfreeze。
- pending/running/streaming 任务 + 过期 freeze → 保持冻结，不处理。
- 孤儿 freeze（无对应 GenerationTask，含同步调用崩溃场景）+ 过期 → 补 unfreeze。
- 新鲜 freeze（created_at 未过阈值）→ 不处理。
- 已结算 freeze（已有 consume）→ 不重复处理（幂等）。
- 重复扫描幂等：第二次运行不再处理已结算条目。
- 单条处理抛错（注入坏数据）→ 记录日志并继续，其余条目仍被处理。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.points import PointTransaction, PointTransactionType, UserPoints
from app.models.task import GenerationTask, GenerationTaskStatus
from app.models.user import User
from app.services.points import ledger
from app.services.points.ledger import (
    consume_frozen,
    freeze_points,
    get_points,
    recharge,
    unfreeze_frozen,
)
from app.services.points.reconciliation import reconcile_stale_freezes


async def _build_session() -> tuple[AsyncSession, object]:
    """构建内存 SQLite 会话并在 Base.metadata 上 create_all。

    返回 (db, engine)，调用方负责 close/dispose。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = session_local()
    async with db.begin():
        db.add(
            User(
                id="u1",
                username="tester",
                hashed_password="x",
                is_admin=False,
                is_active=True,
                token_version=0,
            )
        )
    return db, engine


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    """将账本的 Redis 工厂替换为 fakeredis，使账户变更在测试中互斥可验。"""
    client = FakeRedis()

    def _factory():  # noqa: ANN202 - 测试桩，返回共享 fakeredis 客户端
        return client

    monkeypatch.setattr(ledger, "_redis_factory", _factory)
    yield client


async def _stale_freeze(
    db: AsyncSession,
    *,
    billing_id: str,
    amount: int = 30,
    business_id: str | None = None,
) -> None:
    """创建一笔已过阈值（created_at = now - 31min）的冻结流水。

    先充值保证余额充足，再冻结，最后把 created_at 直接改写为过期时间并提交。
    """
    await recharge(db, user_id="u1", amount=amount, created_by="admin", remark="seed")
    await freeze_points(
        db,
        user_id="u1",
        billing_id=billing_id,
        amount=amount,
        model_id="m1",
        business_type="image_generation",
        business_id=business_id or billing_id,
        snapshot={"points": amount},
    )
    # 改写 created_at 为 31 分钟前，越过默认 30min 阈值
    stale_at = datetime.now(timezone.utc) - timedelta(minutes=31)
    frz = (
        await db.execute(
            select(PointTransaction).where(
                PointTransaction.billing_id == billing_id,
                PointTransaction.type == PointTransactionType.freeze,
            )
        )
    ).scalar_one()
    frz.created_at = stale_at
    await db.commit()


async def _seed_task(
    db: AsyncSession,
    *,
    billing_id: str,
    status: GenerationTaskStatus,
    task_id: str | None = None,
) -> GenerationTask:
    """插入一条 GenerationTask 并提交。"""
    task = GenerationTask(
        id=task_id or f"task-{billing_id}",
        user_id="u1",
        mode="async_polling",
        task_kind="image_generation",
        status=status,
        progress=0,
        payload={},
        billing_id=billing_id,
    )
    db.add(task)
    await db.commit()
    return task


# ---------------------------------------------------------------------------
# succeeded → 补 consume
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_succeeded_task_freeze_reconciled_as_consume() -> None:
    """成功任务的过期冻结应在补偿后转为 consume，余额下降。"""
    db, engine = await _build_session()
    try:
        await _stale_freeze(db, billing_id="S1", amount=30)
        await _seed_task(db, billing_id="S1", status=GenerationTaskStatus.succeeded)

        processed = await reconcile_stale_freezes(db)
        assert processed == 1

        consume_tx = (
            await db.execute(
                select(PointTransaction).where(
                    PointTransaction.billing_id == "S1",
                    PointTransaction.type == PointTransactionType.consume,
                )
            )
        ).scalar_one_or_none()
        assert consume_tx is not None
        pts = await get_points(db, user_id="u1")
        # 初始 recharge 30 全部冻结；consume 后余额=0，冻结=0
        assert pts.balance == 0
        assert pts.frozen == 0
    finally:
        await db.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# failed → 补 unfreeze
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_task_freeze_reconciled_as_unfreeze() -> None:
    """失败任务的过期冻结应解冻，余额恢复。"""
    db, engine = await _build_session()
    try:
        await _stale_freeze(db, billing_id="F1", amount=40)
        await _seed_task(db, billing_id="F1", status=GenerationTaskStatus.failed)

        processed = await reconcile_stale_freezes(db)
        assert processed == 1

        unfreeze_tx = (
            await db.execute(
                select(PointTransaction).where(
                    PointTransaction.billing_id == "F1",
                    PointTransaction.type == PointTransactionType.unfreeze,
                )
            )
        ).scalar_one_or_none()
        assert unfreeze_tx is not None
        pts = await get_points(db, user_id="u1")
        assert pts.balance == 40
        assert pts.frozen == 0
    finally:
        await db.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# cancelled → 补 unfreeze
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancelled_task_freeze_reconciled_as_unfreeze() -> None:
    """取消任务的过期冻结应解冻。"""
    db, engine = await _build_session()
    try:
        await _stale_freeze(db, billing_id="C1", amount=25)
        await _seed_task(db, billing_id="C1", status=GenerationTaskStatus.cancelled)

        processed = await reconcile_stale_freezes(db)
        assert processed == 1

        unfreeze_tx = (
            await db.execute(
                select(PointTransaction).where(
                    PointTransaction.billing_id == "C1",
                    PointTransaction.type == PointTransactionType.unfreeze,
                )
            )
        ).scalar_one_or_none()
        assert unfreeze_tx is not None
        pts = await get_points(db, user_id="u1")
        assert pts.balance == 25
        assert pts.frozen == 0
    finally:
        await db.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# pending / running / streaming → 保持冻结
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inflight_task_freeze_preserved() -> None:
    """任务仍在进行中（pending/running/streaming）的冻结不应被补偿处理。"""
    db, engine = await _build_session()
    try:
        for idx, status in enumerate(
            [
                GenerationTaskStatus.pending,
                GenerationTaskStatus.running,
                GenerationTaskStatus.streaming,
            ]
        ):
            bid = f"PR{idx}"
            await _stale_freeze(db, billing_id=bid, amount=10)
            await _seed_task(db, billing_id=bid, status=status)

        processed = await reconcile_stale_freezes(db)
        assert processed == 0

        # 三笔冻结流水仍在，无 consume/unfreeze
        settled = (
            await db.execute(
                select(PointTransaction).where(
                    PointTransaction.type.in_(
                        [PointTransactionType.consume, PointTransactionType.unfreeze]
                    )
                )
            )
        ).scalars().all()
        assert len(settled) == 0
        pts = await get_points(db, user_id="u1")
        assert pts.frozen == 30
    finally:
        await db.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# 孤儿冻结（无对应任务，含同步调用崩溃场景）→ 补 unfreeze
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orphan_freeze_reconciled_as_unfreeze() -> None:
    """无对应 GenerationTask 的孤儿冻结（同步调用崩溃残留）应被解冻。"""
    db, engine = await _build_session()
    try:
        await _stale_freeze(db, billing_id="OR1", amount=35)
        # 故意不创建 GenerationTask

        processed = await reconcile_stale_freezes(db)
        assert processed == 1

        unfreeze_tx = (
            await db.execute(
                select(PointTransaction).where(
                    PointTransaction.billing_id == "OR1",
                    PointTransaction.type == PointTransactionType.unfreeze,
                )
            )
        ).scalar_one_or_none()
        assert unfreeze_tx is not None
        pts = await get_points(db, user_id="u1")
        assert pts.balance == 35
        assert pts.frozen == 0
    finally:
        await db.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# 新鲜冻结（未过阈值）→ 不处理
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_freeze_not_processed() -> None:
    """新鲜冻结（created_at 在阈值内）不应被补偿扫描命中。"""
    db, engine = await _build_session()
    try:
        await recharge(db, user_id="u1", amount=50, created_by="admin", remark="seed")
        await freeze_points(
            db,
            user_id="u1",
            billing_id="FR1",
            amount=50,
            model_id="m1",
            business_type="image_generation",
            business_id="FR1",
            snapshot={"points": 50},
        )
        await _seed_task(db, billing_id="FR1", status=GenerationTaskStatus.succeeded)
        # created_at 保持为 now（由 freeze_points 写入），未过 30min 阈值

        processed = await reconcile_stale_freezes(db)
        assert processed == 0

        settled = (
            await db.execute(
                select(PointTransaction).where(
                    PointTransaction.type.in_(
                        [PointTransactionType.consume, PointTransactionType.unfreeze]
                    )
                )
            )
        ).scalars().all()
        assert len(settled) == 0
        pts = await get_points(db, user_id="u1")
        assert pts.frozen == 50
    finally:
        await db.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# 已结算（已有 consume）→ 幂等不重复处理
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_already_settled_freeze_not_reprocessed() -> None:
    """已有 consume 流水的过期冻结不应被重复处理。"""
    db, engine = await _build_session()
    try:
        await _stale_freeze(db, billing_id="SET1", amount=30)
        await _seed_task(db, billing_id="SET1", status=GenerationTaskStatus.succeeded)
        # 正常结算先消费
        await consume_frozen(db, user_id="u1", billing_id="SET1")

        processed = await reconcile_stale_freezes(db)
        assert processed == 0

        # 仍只有一笔 consume
        consumes = (
            await db.execute(
                select(PointTransaction).where(
                    PointTransaction.billing_id == "SET1",
                    PointTransaction.type == PointTransactionType.consume,
                )
            )
        ).scalars().all()
        assert len(consumes) == 1
    finally:
        await db.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# 重复扫描幂等
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repeat_scan_is_idempotent() -> None:
    """连续运行两次：第一次处理，第二次无新增。"""
    db, engine = await _build_session()
    try:
        await _stale_freeze(db, billing_id="ID1", amount=20)
        await _seed_task(db, billing_id="ID1", status=GenerationTaskStatus.failed)

        first = await reconcile_stale_freezes(db)
        assert first == 1
        second = await reconcile_stale_freezes(db)
        assert second == 0

        unfreezes = (
            await db.execute(
                select(PointTransaction).where(
                    PointTransaction.billing_id == "ID1",
                    PointTransaction.type == PointTransactionType.unfreeze,
                )
            )
        ).scalars().all()
        assert len(unfreezes) == 1
    finally:
        await db.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# 单条失败不阻断全批
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_row_failure_does_not_block_batch(monkeypatch) -> None:
    """一条坏数据（注入异常）应被记录并跳过，其余条目仍正常处理。"""
    db, engine = await _build_session()
    try:
        # 两条过期冻结 + 成功任务
        await _stale_freeze(db, billing_id="OK1", amount=15)
        await _seed_task(db, billing_id="OK1", status=GenerationTaskStatus.succeeded)
        await _stale_freeze(db, billing_id="BAD1", amount=15)
        await _seed_task(db, billing_id="BAD1", status=GenerationTaskStatus.succeeded)

        from app.services.points import reconciliation as recon_mod

        real_consume = consume_frozen
        call_count = {"n": 0}

        async def _flaky_consume(session, *, user_id, billing_id, created_by=None):  # noqa: ANN001
            call_count["n"] += 1
            if billing_id == "BAD1":
                raise RuntimeError("injected failure")
            return await real_consume(session, user_id=user_id, billing_id=billing_id, created_by=created_by)

        monkeypatch.setattr(recon_mod, "consume_frozen", _flaky_consume)

        processed = await reconcile_stale_freezes(db)
        # OK1 被处理，BAD1 抛错被跳过
        assert processed == 1

        ok_consume = (
            await db.execute(
                select(PointTransaction).where(
                    PointTransaction.billing_id == "OK1",
                    PointTransaction.type == PointTransactionType.consume,
                )
            )
        ).scalar_one_or_none()
        assert ok_consume is not None
        bad_consume = (
            await db.execute(
                select(PointTransaction).where(
                    PointTransaction.billing_id == "BAD1",
                    PointTransaction.type == PointTransactionType.consume,
                )
            )
        ).scalar_one_or_none()
        assert bad_consume is None
    finally:
        await db.close()
        await engine.dispose()
