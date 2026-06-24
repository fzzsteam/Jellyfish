"""积分账本服务（冻结/扣减/解冻/充值）的契约测试。

校验内容：
- 自动初始化用户积分账户（首次访问余额与冻结额均为 0）。
- 余额模型：`balance`=总额（含冻结），`frozen`=已冻结，`available=balance-frozen`。
- 余额不足抛 `InsufficientPointsError`（携带 available/required/shortfall）。
- 冻结/扣减/解冻的状态机与 balance/frozen 快照正确。
- 同一 billing_id 的 consume/unfreeze 幂等；二者互斥。
- 充值支持正负，负充值需备注且不得侵蚀冻结额。
- 幂等：重复 settle 返回既有流水。
"""

from __future__ import annotations

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.points import PointTransaction, PointTransactionType, UserPoints
from app.models.user import User
from app.services.points import ledger
from app.services.points.ledger import (
    BillingStateError,
    InsufficientPointsError,
    consume_frozen,
    freeze_points,
    get_points,
    recharge,
    unfreeze_frozen,
)


async def _build_session() -> tuple[AsyncSession, object]:
    """构建内存 SQLite 会话并在 Base.metadata 上 create_all。

    每次调用新建独立 engine，保证测试间表结构与数据互不干扰。
    返回 (db, engine)，调用方负责 close/dispose。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = session_local()
    # 预置外键所需的 users 行
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
    """将账本的 Redis 工厂替换为 fakeredis，使所有账户变更在测试中互斥可验。"""
    client = FakeRedis()

    def _factory():  # noqa: ANN202 - 测试桩，返回共享 fakeredis 客户端
        return client

    monkeypatch.setattr(ledger, "_redis_factory", _factory)
    yield client


# ---------------------------------------------------------------------------
# get_points：自动初始化
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_points_auto_initializes_zero_account() -> None:
    """首次访问应创建余额/冻结均为 0 的账户并返回。"""
    db, engine = await _build_session()
    try:
        pts = await get_points(db, user_id="u1")
        assert pts.user_id == "u1"
        assert pts.balance == 0
        assert pts.frozen == 0
        # 落库存在
        await db.commit()
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_points_idempotent_returns_same_row() -> None:
    """重复 get_points 返回同一行而非重复创建。"""
    db, engine = await _build_session()
    try:
        p1 = await get_points(db, user_id="u1")
        p2 = await get_points(db, user_id="u1")
        assert p1.user_id == p2.user_id
        await db.commit()
        rows = (await db.scalars(select(UserPoints))).all()
        assert len(rows) == 1
    finally:
        await db.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# freeze_points：余额不足、快照、幂等
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_freeze_insufficient_balance_raises_with_details() -> None:
    """余额不足冻结时抛 InsufficientPointsError，并携带 available/required/shortfall。"""
    db, engine = await _build_session()
    try:
        with pytest.raises(InsufficientPointsError) as exc_info:
            await freeze_points(
                db,
                user_id="u1",
                billing_id="B1",
                amount=50,
                model_id="m1",
                business_type="image_generation",
                business_id="task-1",
                snapshot={"points": 50},
            )
        err = exc_info.value
        assert err.available == 0
        assert err.required == 50
        assert err.shortfall == 50
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_freeze_after_recharge_snapshots_balance_frozen() -> None:
    """充值后冻结：balance 不变，frozen 增加，available 减少。"""
    db, engine = await _build_session()
    try:
        await recharge(db, user_id="u1", amount=100, created_by="admin", remark="init")
        tx = await freeze_points(
            db,
            user_id="u1",
            billing_id="B2",
            amount=30,
            model_id="m1",
            business_type="image_generation",
            business_id="task-2",
            snapshot={"points": 30},
        )
        assert tx.type == PointTransactionType.freeze
        assert tx.amount == 30
        assert tx.balance_after == 100  # balance 不变
        assert tx.frozen_after == 30  # frozen +30
        # 账户快照一致
        pts = await get_points(db, user_id="u1")
        assert pts.balance == 100
        assert pts.frozen == 30
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_freeze_duplicate_billing_is_idempotent() -> None:
    """同一 billing_id 重复 freeze 返回既有流水，不重复扣冻结。"""
    db, engine = await _build_session()
    try:
        await recharge(db, user_id="u1", amount=100, created_by="admin", remark="init")
        tx1 = await freeze_points(
            db,
            user_id="u1",
            billing_id="B3",
            amount=20,
            model_id="m1",
            business_type="image_generation",
            business_id="task-3",
            snapshot={"points": 20},
        )
        tx2 = await freeze_points(
            db,
            user_id="u1",
            billing_id="B3",
            amount=20,
            model_id="m1",
            business_type="image_generation",
            business_id="task-3",
            snapshot={"points": 20},
        )
        assert tx1.id == tx2.id  # 幂等：返回同一行
        pts = await get_points(db, user_id="u1")
        assert pts.frozen == 20  # 仅一次冻结
    finally:
        await db.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# consume_frozen：扣减、幂等、状态校验
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consume_frozen_reduces_balance_and_frozen() -> None:
    """扣减冻结额：balance 与 frozen 同步减少，available 不变。"""
    db, engine = await _build_session()
    try:
        await recharge(db, user_id="u1", amount=100, created_by="admin", remark="init")
        await freeze_points(
            db,
            user_id="u1",
            billing_id="B4",
            amount=40,
            model_id="m1",
            business_type="image_generation",
            business_id="task-4",
            snapshot={"points": 40},
        )
        tx = await consume_frozen(db, user_id="u1", billing_id="B4")
        assert tx.type == PointTransactionType.consume
        assert tx.amount == 40
        assert tx.balance_after == 60  # 100 - 40
        assert tx.frozen_after == 0  # 40 - 40
        pts = await get_points(db, user_id="u1")
        assert pts.balance == 60
        assert pts.frozen == 0
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_consume_frozen_idempotent() -> None:
    """重复 consume 同一 billing_id 返回同一行。"""
    db, engine = await _build_session()
    try:
        await recharge(db, user_id="u1", amount=100, created_by="admin", remark="init")
        await freeze_points(
            db,
            user_id="u1",
            billing_id="B5",
            amount=25,
            model_id="m1",
            business_type="image_generation",
            business_id="task-5",
            snapshot={"points": 25},
        )
        tx1 = await consume_frozen(db, user_id="u1", billing_id="B5")
        tx2 = await consume_frozen(db, user_id="u1", billing_id="B5")
        assert tx1.id == tx2.id
        pts = await get_points(db, user_id="u1")
        assert pts.balance == 75
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_consume_without_freeze_raises_billing_state() -> None:
    """无冻结流水直接扣减抛 BillingStateError。"""
    db, engine = await _build_session()
    try:
        with pytest.raises(BillingStateError):
            await consume_frozen(db, user_id="u1", billing_id="B6")
    finally:
        await db.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# unfreeze_frozen：解冻、幂等、互斥
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unfreeze_returns_frozen_to_available() -> None:
    """解冻：frozen 减少，balance 不变，available 恢复。"""
    db, engine = await _build_session()
    try:
        await recharge(db, user_id="u1", amount=100, created_by="admin", remark="init")
        await freeze_points(
            db,
            user_id="u1",
            billing_id="B7",
            amount=40,
            model_id="m1",
            business_type="image_generation",
            business_id="task-7",
            snapshot={"points": 40},
        )
        tx = await unfreeze_frozen(db, user_id="u1", billing_id="B7", remark="task failed")
        assert tx.type == PointTransactionType.unfreeze
        assert tx.amount == 40
        assert tx.balance_after == 100  # 不变
        assert tx.frozen_after == 0  # 解冻
        pts = await get_points(db, user_id="u1")
        assert pts.balance == 100
        assert pts.frozen == 0
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_unfreeze_idempotent() -> None:
    """重复 unfreeze 同一 billing_id 返回同一行。"""
    db, engine = await _build_session()
    try:
        await recharge(db, user_id="u1", amount=100, created_by="admin", remark="init")
        await freeze_points(
            db,
            user_id="u1",
            billing_id="B8",
            amount=40,
            model_id="m1",
            business_type="image_generation",
            business_id="task-8",
            snapshot={"points": 40},
        )
        tx1 = await unfreeze_frozen(db, user_id="u1", billing_id="B8")
        tx2 = await unfreeze_frozen(db, user_id="u1", billing_id="B8")
        assert tx1.id == tx2.id
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_consume_then_unfreeze_raises_mutex() -> None:
    """已扣减的流水不能再解冻（互斥）。"""
    db, engine = await _build_session()
    try:
        await recharge(db, user_id="u1", amount=100, created_by="admin", remark="init")
        await freeze_points(
            db,
            user_id="u1",
            billing_id="B9",
            amount=40,
            model_id="m1",
            business_type="image_generation",
            business_id="task-9",
            snapshot={"points": 40},
        )
        await consume_frozen(db, user_id="u1", billing_id="B9")
        with pytest.raises(BillingStateError):
            await unfreeze_frozen(db, user_id="u1", billing_id="B9")
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_unfreeze_then_consume_raises_mutex() -> None:
    """已解冻的流水不能再扣减（互斥）。"""
    db, engine = await _build_session()
    try:
        await recharge(db, user_id="u1", amount=100, created_by="admin", remark="init")
        await freeze_points(
            db,
            user_id="u1",
            billing_id="B10",
            amount=40,
            model_id="m1",
            business_type="image_generation",
            business_id="task-10",
            snapshot={"points": 40},
        )
        await unfreeze_frozen(db, user_id="u1", billing_id="B10")
        with pytest.raises(BillingStateError):
            await consume_frozen(db, user_id="u1", billing_id="B10")
    finally:
        await db.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# recharge：正负、备注、侵蚀冻结
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recharge_positive_increases_balance() -> None:
    """正充值增加余额，不影响冻结。"""
    db, engine = await _build_session()
    try:
        tx = await recharge(db, user_id="u1", amount=50, created_by="admin", remark="gift")
        assert tx.type == PointTransactionType.recharge
        assert tx.amount == 50
        assert tx.balance_after == 50
        assert tx.frozen_after == 0
        assert tx.source == "admin"
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_recharge_negative_with_remark_decreases_balance() -> None:
    """带备注的负充值扣减余额（不触及冻结时）。"""
    db, engine = await _build_session()
    try:
        await recharge(db, user_id="u1", amount=100, created_by="admin", remark="init")
        tx = await recharge(db, user_id="u1", amount=-20, created_by="admin", remark="adjust")
        assert tx.amount == -20
        assert tx.balance_after == 80
        assert tx.frozen_after == 0
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_recharge_negative_without_remark_raises() -> None:
    """负充值必须带备注，否则报错。"""
    db, engine = await _build_session()
    try:
        await recharge(db, user_id="u1", amount=100, created_by="admin", remark="init")
        with pytest.raises(ValueError):
            await recharge(db, user_id="u1", amount=-20, created_by="admin", remark=None)
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_recharge_negative_cannot_erode_frozen() -> None:
    """负充值不得使余额低于当前冻结额（不能侵蚀已冻结的积分）。"""
    db, engine = await _build_session()
    try:
        await recharge(db, user_id="u1", amount=100, created_by="admin", remark="init")
        await freeze_points(
            db,
            user_id="u1",
            billing_id="B11",
            amount=40,
            model_id="m1",
            business_type="image_generation",
            business_id="task-11",
            snapshot={"points": 40},
        )
        # 余额 100，冻结 40，可用 60；扣 70 会使余额=30 < 冻结 40
        with pytest.raises(InsufficientPointsError):
            await recharge(db, user_id="u1", amount=-70, created_by="admin", remark="too much")
        # 余额与冻结未被破坏
        pts = await get_points(db, user_id="u1")
        assert pts.balance == 100
        assert pts.frozen == 40
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_recharge_not_deduped_each_call_new_transaction() -> None:
    """每次充值都是独立事件，不做幂等去重（内部生成独立 billing_id）。"""
    db, engine = await _build_session()
    try:
        await recharge(db, user_id="u1", amount=50, created_by="admin", remark="a")
        await recharge(db, user_id="u1", amount=50, created_by="admin", remark="b")
        pts = await get_points(db, user_id="u1")
        assert pts.balance == 100
        # 两笔充值流水
        charges = (
            await db.scalars(
                select(PointTransaction).where(
                    PointTransaction.type == PointTransactionType.recharge
                )
            )
        ).all()
        assert len(charges) == 2
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_recharge_does_not_set_cascade_group_id() -> None:
    """充值/调整是单笔流水，不应写入 cascade_group_id。"""
    db, engine = await _build_session()
    try:
        tx = await recharge(db, user_id="u1", amount=100, created_by="admin-1", remark="top up")
        assert tx.type == PointTransactionType.recharge
        assert tx.billing_id is not None
        assert tx.cascade_group_id is None
    finally:
        await db.close()
        await engine.dispose()
