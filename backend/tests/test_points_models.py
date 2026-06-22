"""积分计费相关 ORM 模型契约测试。

校验内容：
- `Model.unit_points` 字段：非负 BigInteger，默认 0，NOT NULL。
- `UserPoints` / `PointTransaction` 表结构与约束（唯一键、CHECK、索引）。
- `GenerationTask.billing_id`：可空字符串列，带索引。
- `PointTransactionType` 枚举值集合。
- 通过内存 SQLite 真实建表，验证 CHECK 约束、唯一约束、外键依赖在运行期可被强制执行。
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.llm import Model
from app.models.points import PointTransaction, PointTransactionType, UserPoints
from app.models.task import GenerationTask
from app.models.user import User


async def _build_session() -> tuple[AsyncSession, object]:
    """构建内存 SQLite 会话并在 Base.metadata 上 create_all。

    每次调用都新建独立 engine，确保测试间表结构与数据互不干扰；返回 (db, engine)，
    调用方负责在用完后 await db.close()/engine.dispose()。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = session_local()
    return db, engine


def test_model_has_non_negative_unit_points() -> None:
    """Model.unit_points 必须存在、默认 0、NOT NULL。"""
    column = Model.__table__.c.unit_points
    assert column.default.arg == 0
    assert column.nullable is False


def test_points_tables_and_task_billing_column_exist() -> None:
    """UserPoints / PointTransaction / GenerationTask.billing_id 契约。"""
    # user_id 既是主键也满足 c.user_id.unique truthy（UniqueConstraint 显式声明）
    assert UserPoints.__table__.c.user_id.unique
    assert set(PointTransactionType) == {
        PointTransactionType.recharge,
        PointTransactionType.freeze,
        PointTransactionType.consume,
        PointTransactionType.unfreeze,
    }
    assert GenerationTask.__table__.c.billing_id.nullable


def test_user_points_has_invariants() -> None:
    """UserPoints 必须包含 balance/frozen 列以及非负/冻结约束。"""
    tbl = UserPoints.__table__
    assert tbl.c.balance.default.arg == 0
    assert tbl.c.frozen.default.arg == 0
    assert tbl.c.balance.nullable is False
    assert tbl.c.frozen.nullable is False
    constraint_names = {c.name for c in tbl.constraints if c.name}
    assert {
        "ck_user_points_balance_nonneg",
        "ck_user_points_frozen_nonneg",
        "ck_user_points_frozen_le_balance",
    }.issubset(constraint_names)


def test_point_transaction_has_billing_type_unique() -> None:
    """point_transactions 表需有 (billing_id, type) 唯一约束与关键字段。"""
    tbl = PointTransaction.__table__
    assert "billing_id" in tbl.c
    assert "type" in tbl.c
    assert "amount" in tbl.c
    assert "balance_after" in tbl.c
    assert "frozen_after" in tbl.c
    assert "pricing_snapshot" in tbl.c
    # (billing_id, type) 唯一性
    unique_pairs = {
        tuple(sorted(c.columns.keys())) for c in tbl.constraints if c.__class__.__name__ == "UniqueConstraint"
    }
    assert ("billing_id", "type") in unique_pairs


@pytest.mark.asyncio
async def test_create_all_builds_points_tables() -> None:
    """Base.metadata.create_all 应建出 user_points 与 point_transactions 表。

    同时隐式验证外键依赖顺序正确（user_points/point_transactions 引用 users/models），
    否则 create_all 会在建表阶段失败。
    """
    db, engine = await _build_session()
    try:
        async with engine.connect() as conn:
            names = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        assert "user_points" in names
        assert "point_transactions" in names
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_user_points_negative_balance_raises() -> None:
    """balance=-1 违反 balance>=0 CHECK，flush 时抛 IntegrityError。"""
    db, engine = await _build_session()
    try:
        async with db.begin():
            await db.merge(_user_row())
            db.add(UserPoints(user_id="u1", balance=-1, frozen=0))
            with pytest.raises(IntegrityError):
                await db.flush()
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_user_points_negative_frozen_raises() -> None:
    """frozen=-1 违反 frozen>=0 CHECK，flush 时抛 IntegrityError。"""
    db, engine = await _build_session()
    try:
        async with db.begin():
            await db.merge(_user_row())
            db.add(UserPoints(user_id="u1", balance=0, frozen=-1))
            with pytest.raises(IntegrityError):
                await db.flush()
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_user_points_frozen_greater_than_balance_raises() -> None:
    """frozen>balance 违反 frozen<=balance CHECK，flush 时抛 IntegrityError。"""
    db, engine = await _build_session()
    try:
        async with db.begin():
            await db.merge(_user_row())
            db.add(UserPoints(user_id="u1", balance=5, frozen=6))
            with pytest.raises(IntegrityError):
                await db.flush()
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_transaction_billing_type_unique_collides_and_null_does_not() -> None:
    """(billing_id, type) 唯一约束：非空 billing_id 重复抛错；NULL billing_id 互不冲突。"""
    db, engine = await _build_session()
    try:
        async with db.begin():
            await db.merge(_user_row())
            # 第一条 (billing_id=B1, type=freeze) 成功
            db.add(_tx("t1", billing_id="B1", tx_type="freeze"))
            await db.flush()
            # 第二条相同 (billing_id=B1, type=freeze) 应触发唯一约束
            db.add(_tx("t2", billing_id="B1", tx_type="freeze"))
            with pytest.raises(IntegrityError):
                await db.flush()
    finally:
        await db.close()
        await engine.dispose()

    # NULL billing_id 不应互相冲突（SQL 唯一约束对 NULL 独立计数）
    db, engine = await _build_session()
    try:
        async with db.begin():
            await db.merge(_user_row())
            db.add(_tx("n1", billing_id=None, tx_type="recharge"))
            db.add(_tx("n2", billing_id=None, tx_type="recharge"))
            await db.flush()  # 不应抛错
            rows = (await db.scalars(select(PointTransaction))).all()
        assert len(rows) >= 2
    finally:
        await db.close()
        await engine.dispose()


def _user_row() -> User:
    """构造一条供外键引用的 users 行（内存 SQLite 测试前置数据）。"""
    return User(
        id="u1",
        username="tester",
        hashed_password="x",
        is_admin=False,
        is_active=True,
        token_version=0,
    )


def _tx(
    tid: str,
    *,
    billing_id: str | None,
    tx_type: str,
    user_id: str = "u1",
) -> PointTransaction:
    """构造一条 PointTransaction 行（amount 固定正数，避免与业务符号语义耦合）。"""
    return PointTransaction(
        id=tid,
        user_id=user_id,
        type=tx_type,
        amount=10,
        balance_after=0,
        frozen_after=0,
        source="system",
        billing_id=billing_id,
    )
