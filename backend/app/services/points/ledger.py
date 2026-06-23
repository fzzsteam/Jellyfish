"""积分账本服务：账户读改写的核心实现。

为什么存在：
    封装 `UserPoints` / `PointTransaction` 的状态机变更，对外提供稳定、幂等、并发安全的
    接口（冻结 / 扣减 / 解冻 / 充值）。所有写操作都先抢 Redis 用户锁、再走 `FOR UPDATE`
    行锁、最后 `commit()`，双重互斥避免超扣。

余额模型（务必理解）：
    - `balance` = 账户总额（**包含**已冻结部分）。
    - `frozen` = 当前已冻结额。
    - `available = balance - frozen` = 用户当下可新下单的额度。
    - 不变量（由表 CHECK 约束兜底）：`balance >= 0`、`frozen >= 0`、`frozen <= balance`。

各动作对账户的影响：
    - freeze(a):   balance 不变, frozen += a         （要求 available >= a）
    - consume(a):  balance -= a, frozen -= a         （从冻结额结算，available 不变）
    - unfreeze(a): balance 不变, frozen -= a         （冻结退回可用）
    - recharge(a): balance += a                      （a 可正可负；负要求备注且不得侵蚀 frozen）

幂等与互斥：
    - `(billing_id, type)` 唯一约束保证每个计费单据同一动作只能入账一次；重复调用返回既有流水。
    - consume 与 unfreeze 基于同一 billing_id 互斥：已扣减不可再解冻，反之亦然。
    - 充值每次生成独立 billing_id（UUID），不做幂等去重——每次充值都是独立事件。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.points import PointTransaction, PointTransactionType, UserPoints
from app.services.points.locks import PointsOperationBusyError, RedisUserLock


# ---------------------------------------------------------------------------
# 异常类型
# ---------------------------------------------------------------------------


class InsufficientPointsError(Exception):
    """余额不足：冻结或负充值所需积分超出当前可用额度。

    携带 `available` / `required` / `shortfall`，Task 4 的 API 层会据此构造错误响应。
    """

    def __init__(self, *, available: int, required: int, shortfall: int) -> None:
        self.available = available
        self.required = required
        self.shortfall = shortfall
        super().__init__(
            f"insufficient points: available={available}, required={required}, shortfall={shortfall}"
        )


class BillingStateError(Exception):
    """计费单据状态非法：例如无冻结流水却要扣减、已扣减却要解冻。"""


# ---------------------------------------------------------------------------
# Redis 工厂：可被测试 monkeypatch 替换为 fakeredis
# ---------------------------------------------------------------------------


def _default_redis_factory() -> aioredis.Redis:
    """默认 Redis 客户端工厂：按 settings.celery_broker_url 建立连接。

    放在模块级而非配置里，便于测试用 monkeypatch 替换为共享的 fakeredis 客户端，
    从而让账户变更在测试中真正互斥。
    """
    return aioredis.Redis.from_url(settings.celery_broker_url)


# 测试通过 monkeypatch 替换此符号即可注入 fakeredis。
_redis_factory = _default_redis_factory


@asynccontextmanager
async def _with_user_lock(user_id: str) -> AsyncIterator[None]:
    """获取用户锁的统一上下文：保证所有账户变更都在锁内完成。

    使用后负责关闭 Redis 连接，避免连接泄漏（fakeredis 同样优雅处理）。
    """
    client = _redis_factory()
    try:
        async with RedisUserLock(client, user_id):
            yield
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# 内部辅助：UUID / 查询
# ---------------------------------------------------------------------------


def _new_tx_id() -> str:
    """生成流水主键（uuid4 hex），避免业务层猜测 ID 格式。"""
    return uuid.uuid4().hex


async def _get_or_create_user_points(db: AsyncSession, *, user_id: str) -> UserPoints:
    """读取或初始化用户积分账户（余额/冻结默认 0）。

    get_or_create 语义，但这里不加 Redis 锁（读多写少且仅初始化一次）；
    并发初始化由 user_points 主键唯一约束兜底，重复创建会抛 IntegrityError。
    """
    existing = (
        await db.execute(select(UserPoints).where(UserPoints.user_id == user_id))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    pts = UserPoints(user_id=user_id, balance=0, frozen=0)
    db.add(pts)
    try:
        await db.flush()
    except IntegrityError:
        # 并发初始化：回滚并重读既有行
        await db.rollback()
        pts = (
            await db.execute(select(UserPoints).where(UserPoints.user_id == user_id))
        ).scalar_one()
    return pts


async def _find_tx_by_billing(
    db: AsyncSession, *, billing_id: str, tx_type: PointTransactionType, lock: bool = False
) -> PointTransaction | None:
    """按 billing_id + type 查询流水；lock=True 时对单行加 FOR UPDATE。"""
    stmt = select(PointTransaction).where(
        PointTransaction.billing_id == billing_id,
        PointTransaction.type == tx_type,
    )
    if lock:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# 对外接口
# ---------------------------------------------------------------------------


async def get_points(db: AsyncSession, *, user_id: str) -> UserPoints:
    """读取（或自动初始化）用户积分账户。

    纯读取语义，不抢 Redis 锁；返回的行可供调用方查看余额/冻结/可用额度。
    """
    return await _get_or_create_user_points(db, user_id=user_id)


async def freeze_points(
    db: AsyncSession,
    *,
    user_id: str,
    billing_id: str,
    amount: int,
    model_id: str | None,
    business_type: str,
    business_id: str | None,
    snapshot: dict[str, Any] | None,
    created_by: str | None = None,
    cascade_group_id: str | None = None,
) -> PointTransaction:
    """冻结积分：下单时预占额度，余额不变，冻结额增加。

    要求 `available = balance - frozen >= amount`，否则抛 InsufficientPointsError。
    幂等：同一 billing_id 重复冻结返回既有 freeze 流水。
    """
    if amount <= 0:
        raise ValueError("freeze amount must be positive")

    async with _with_user_lock(user_id):
        # 幂等：已存在则直接返回
        existing = await _find_tx_by_billing(db, billing_id=billing_id, tx_type=PointTransactionType.freeze)
        if existing is not None:
            return existing

        # 行锁锁定账户行
        pts = (
            await db.execute(
                select(UserPoints).where(UserPoints.user_id == user_id).with_for_update()
            )
        ).scalar_one_or_none()
        if pts is None:
            # 兜底初始化（一般 get_points 已建好）
            pts = UserPoints(user_id=user_id, balance=0, frozen=0)
            db.add(pts)
            await db.flush()

        available = pts.balance - pts.frozen
        if available < amount:
            raise InsufficientPointsError(
                available=available, required=amount, shortfall=amount - available
            )

        new_frozen = pts.frozen + amount
        # 未显式指定 cascade_group_id 时默认为自己 root（freeze_points 只服务于 billing 源；
        # 充值/管理员调整走独立的 recharge() 函数，不会走到这里，故无需区分 source）。
        if cascade_group_id is None:
            cascade_group_id = billing_id
        tx = PointTransaction(
            id=_new_tx_id(),
            user_id=user_id,
            type=PointTransactionType.freeze,
            amount=amount,
            balance_after=pts.balance,  # 余额不变
            frozen_after=new_frozen,
            source="billing",
            billing_id=billing_id,
            business_type=business_type,
            business_id=business_id,
            model_id=model_id,
            pricing_snapshot=snapshot,
            cascade_group_id=cascade_group_id,
            created_by=created_by,
        )
        db.add(tx)
        pts.frozen = new_frozen
        try:
            await db.commit()
        except IntegrityError:
            # 并发导致 (billing_id, freeze) 唯一冲突：回滚并返回既有流水
            await db.rollback()
            existing = await _find_tx_by_billing(
                db, billing_id=billing_id, tx_type=PointTransactionType.freeze
            )
            # 幂等回读必须命中；若返回 None 说明冲突并非该唯一约束造成，绝不能静默当作成功。
            assert existing is not None, (
                f"freeze 幂等回读未找到 billing_id={billing_id} 的 freeze 流水"
            )
            return existing  # type: ignore[return-value]
        await db.refresh(tx)
        return tx


async def consume_frozen(
    db: AsyncSession, *, user_id: str, billing_id: str, created_by: str | None = None
) -> PointTransaction:
    """扣减冻结额：任务成功后从冻结额度结算扣出，余额与冻结额同步减少。

    幂等：同一 billing_id 已扣减则返回既有 consume 流水。
    状态校验：必须有 freeze 流水且尚未 unfreeze；否则抛 BillingStateError。
    """
    async with _with_user_lock(user_id):
        # 幂等
        existing_consume = await _find_tx_by_billing(
            db, billing_id=billing_id, tx_type=PointTransactionType.consume
        )
        if existing_consume is not None:
            return existing_consume

        # 锁定 freeze 流水行
        freeze_tx = await _find_tx_by_billing(
            db, billing_id=billing_id, tx_type=PointTransactionType.freeze, lock=True
        )
        if freeze_tx is None:
            raise BillingStateError(
                f"cannot consume billing_id={billing_id}: no freeze transaction"
            )
        # 互斥：已解冻则不能扣减
        already_unfrozen = await _find_tx_by_billing(
            db, billing_id=billing_id, tx_type=PointTransactionType.unfreeze
        )
        if already_unfrozen is not None:
            raise BillingStateError(
                f"cannot consume billing_id={billing_id}: already unfrozen"
            )

        amount = freeze_tx.amount
        # 锁定账户行
        pts = (
            await db.execute(
                select(UserPoints).where(UserPoints.user_id == user_id).with_for_update()
            )
        ).scalar_one()
        new_balance = pts.balance - amount
        new_frozen = pts.frozen - amount
        tx = PointTransaction(
            id=_new_tx_id(),
            user_id=user_id,
            type=PointTransactionType.consume,
            amount=amount,
            balance_after=new_balance,
            frozen_after=new_frozen,
            source="billing",
            billing_id=billing_id,
            business_type=freeze_tx.business_type,
            business_id=freeze_tx.business_id,
            model_id=freeze_tx.model_id,
            pricing_snapshot=freeze_tx.pricing_snapshot,
            cascade_group_id=freeze_tx.cascade_group_id,
            created_by=created_by,
        )
        db.add(tx)
        pts.balance = new_balance
        pts.frozen = new_frozen
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await _find_tx_by_billing(
                db, billing_id=billing_id, tx_type=PointTransactionType.consume
            )
            # 幂等回读必须命中；返回 None 说明冲突源不是 (billing_id, consume) 唯一约束，禁止当成功处理。
            assert existing is not None, (
                f"consume 幂等回读未找到 billing_id={billing_id} 的 consume 流水"
            )
            return existing  # type: ignore[return-value]
        await db.refresh(tx)
        return tx


async def unfreeze_frozen(
    db: AsyncSession,
    *,
    user_id: str,
    billing_id: str,
    remark: str | None = None,
    created_by: str | None = None,
) -> PointTransaction:
    """解冻：任务失败/取消时把冻结额度退回可用，余额不变。

    幂等：同一 billing_id 已解冻则返回既有 unfreeze 流水。
    互斥：已扣减则不能解冻，抛 BillingStateError。
    """
    async with _with_user_lock(user_id):
        # 幂等
        existing_unfreeze = await _find_tx_by_billing(
            db, billing_id=billing_id, tx_type=PointTransactionType.unfreeze
        )
        if existing_unfreeze is not None:
            return existing_unfreeze

        # 互斥：已扣减则不能解冻
        already_consumed = await _find_tx_by_billing(
            db, billing_id=billing_id, tx_type=PointTransactionType.consume
        )
        if already_consumed is not None:
            raise BillingStateError(
                f"cannot unfreeze billing_id={billing_id}: already consumed"
            )

        # 锁定 freeze 流水行
        freeze_tx = await _find_tx_by_billing(
            db, billing_id=billing_id, tx_type=PointTransactionType.freeze, lock=True
        )
        if freeze_tx is None:
            raise BillingStateError(
                f"cannot unfreeze billing_id={billing_id}: no freeze transaction"
            )

        amount = freeze_tx.amount
        pts = (
            await db.execute(
                select(UserPoints).where(UserPoints.user_id == user_id).with_for_update()
            )
        ).scalar_one()
        new_frozen = pts.frozen - amount
        tx = PointTransaction(
            id=_new_tx_id(),
            user_id=user_id,
            type=PointTransactionType.unfreeze,
            amount=amount,
            balance_after=pts.balance,  # 余额不变
            frozen_after=new_frozen,
            source="billing",
            billing_id=billing_id,
            business_type=freeze_tx.business_type,
            business_id=freeze_tx.business_id,
            model_id=freeze_tx.model_id,
            pricing_snapshot=freeze_tx.pricing_snapshot,
            cascade_group_id=freeze_tx.cascade_group_id,
            remark=remark,
            created_by=created_by,
        )
        db.add(tx)
        pts.frozen = new_frozen
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await _find_tx_by_billing(
                db, billing_id=billing_id, tx_type=PointTransactionType.unfreeze
            )
            # 幂等回读必须命中；返回 None 说明冲突源不是 (billing_id, unfreeze) 唯一约束，禁止当成功处理。
            assert existing is not None, (
                f"unfreeze 幂等回读未找到 billing_id={billing_id} 的 unfreeze 流水"
            )
            return existing  # type: ignore[return-value]
        await db.refresh(tx)
        return tx


async def recharge(
    db: AsyncSession,
    *,
    user_id: str,
    amount: int,
    created_by: str | None,
    remark: str | None = None,
) -> PointTransaction:
    """充值：amount 可正可负。

    - 正数：增加余额。
    - 负数：扣减余额，必须带 remark；且不得使 balance 跌破当前 frozen（不能侵蚀已冻结积分）。
    每次充值生成独立 billing_id（UUID），不做幂等去重。
    """
    if amount == 0:
        raise ValueError("recharge amount must be non-zero")
    if amount < 0 and not remark:
        raise ValueError("negative recharge requires a remark")

    async with _with_user_lock(user_id):
        pts = (
            await db.execute(
                select(UserPoints).where(UserPoints.user_id == user_id).with_for_update()
            )
        ).scalar_one_or_none()
        if pts is None:
            pts = UserPoints(user_id=user_id, balance=0, frozen=0)
            db.add(pts)
            await db.flush()

        new_balance = pts.balance + amount
        if amount < 0 and new_balance < pts.frozen:
            # 负充值不得侵蚀冻结额
            raise InsufficientPointsError(
                available=pts.balance - pts.frozen,
                required=-amount,
                shortfall=pts.frozen - new_balance,
            )

        tx = PointTransaction(
            id=_new_tx_id(),
            user_id=user_id,
            type=PointTransactionType.recharge,
            amount=amount,
            balance_after=new_balance,
            frozen_after=pts.frozen,
            source="admin",
            billing_id=_new_tx_id(),  # 每次充值独立，不去重
            remark=remark,
            created_by=created_by,
        )
        db.add(tx)
        pts.balance = new_balance
        await db.commit()
        # commit 后属性过期，refresh 拿回 server_default 时间戳（避免 model_validate 触发懒加载）
        await db.refresh(tx)
        return tx


# 便于上层捕获锁繁忙异常而无需直接 import locks 模块。
__all__ = [
    "BillingStateError",
    "InsufficientPointsError",
    "PointsOperationBusyError",
    "consume_frozen",
    "freeze_points",
    "get_points",
    "recharge",
    "unfreeze_frozen",
]
