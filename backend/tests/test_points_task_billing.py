"""Task 5a：积分任务计费基础设施测试。

覆盖：
- `freeze_for_task`：成功冻结、quote token 用户不符、价格变更、参数篡改、余额不足、模型归属不符。
- `settle_task_billing_sync`：succeeded→consume、failed→unfreeze、cancelled→unfreeze、
  非终态跳过、billing_id=None 跳过、幂等。
- `billing_id` 通道：`TaskManager.create(billing_id=...)` 落到 GenerationTask 与 TaskRecord。

测试策略：
- 内存 SQLite（async + sync 引擎）+ fakeredis（替换 ledger._redis_factory）。
- 直接构造 GenerationTask 行调用 `settle_task_billing_sync`，绕开 Celery。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base
from app.core.task_manager import DeliveryMode, SqlAlchemyTaskStore, TaskManager
from app.core.task_manager.types import TaskStatus
from app.models.llm import Model, ModelCategoryKey, Provider
from app.models.task import GenerationTask, GenerationTaskStatus
from app.models.user import User
from app.services.points import (
    create_quote_token,
    hash_quote_params,
    ledger,
)
from app.services.points.billing import (
    FrozenBilling,
    PointsDomainError,
    freeze_for_task,
    settle_task_billing_sync,
)
from app.services.points.quote_tokens import QuoteClaims


USER_ID = "u1"
OTHER_USER_ID = "u2"


# ---------------------------------------------------------------------------
# 公共夹具：fakeredis 注入 + 数据库表与种子数据
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    """将账本的 Redis 工厂替换为 fakeredis，使账户变更在测试中互斥可验。"""
    client = FakeRedis()

    def _factory():  # noqa: ANN202 - 测试桩
        return client

    monkeypatch.setattr(ledger, "_redis_factory", _factory)
    yield client


async def _seed_async(db: AsyncSession) -> None:
    """在 async 会话里建表并预置 user/provider/model。"""
    import app.models.task  # noqa: F401
    import app.models.points  # noqa: F401

    async with db.begin():
        db.add(User(id=USER_ID, username="u1", hashed_password="x", is_admin=False, is_active=True, token_version=0))
        db.add(User(id=OTHER_USER_ID, username="u2", hashed_password="x", is_admin=False, is_active=True, token_version=0))
        db.add(
            Provider(
                id="p1",
                user_id=USER_ID,
                name="prov",
                base_url="http://x",
                api_key="k",
            )
        )
        db.add(
            Model(
                id="m1",
                user_id=USER_ID,
                name="vid-model",
                category=ModelCategoryKey.video,
                provider_id="p1",
                unit_points=10,
            )
        )


async def _build_async_db() -> tuple[AsyncSession, object]:
    """构建内存 SQLite 异步会话并建表 + 种子。返回 (db, engine)。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = session_local()
    await _seed_async(db)
    return db, engine


def _make_quote_token(
    *,
    user_id: str = USER_ID,
    business_type: str = "video_generation",
    model_id: str = "m1",
    required_points: int = 20,
    duration_seconds: int = 5,
    resolution: str = "1080p",
) -> str:
    """构造一个合法的 quote_token。

    计价基准（与 m1 一致）：unit_points=10、video、1080p(×2.0)、generation_count=1。
    因此 duration_seconds=5 → required_points = 10 * 5 * 2.0 = 100。`required_points`
    由调用方显式传入，用于构造 token 内的 claims.required_points（重算一致时通过校验）。
    """
    params_hash = hash_quote_params(
        {
            "category": str(ModelCategoryKey.video),
            "duration_seconds": duration_seconds,
            "resolution": resolution,
            "generation_count": 1,
        }
    )
    return create_quote_token(
        QuoteClaims(
            user_id=user_id,
            business_type=business_type,
            model_id=model_id,
            params_hash=params_hash,
            required_points=required_points,
        )
    )


# ---------------------------------------------------------------------------
# freeze_for_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_freeze_for_task_success_freezes_points() -> None:
    """正常冻结：返回 FrozenBilling 且账户 frozen 增加、balance 不变。"""
    from app.services.points import freeze_points  # noqa: F401  (ensure import path valid)
    from app.services.points.ledger import recharge

    db, engine = await _build_async_db()
    try:
        # 充值 100，可用 100
        await recharge(db, user_id=USER_ID, amount=100, created_by="tester", remark="seed")
        # 1080p*5s：10 单价 * 5s * 2.0(1080p) = 100
        token = _make_quote_token(required_points=100, duration_seconds=5, resolution="1080p")
        frozen = await freeze_for_task(
            db,
            user_id=USER_ID,
            quote_token=token,
            business_type="video_generation",
            category=ModelCategoryKey.video,
            model_id="m1",
            duration_seconds=5,
            resolution="1080p",
        )
        assert isinstance(frozen, FrozenBilling)
        assert frozen.required_points == 100
        assert frozen.model_id == "m1"
        assert frozen.business_type == "video_generation"
        assert frozen.billing_id
        # snapshot 携带计价上下文
        assert frozen.snapshot["category"] == str(ModelCategoryKey.video)
        assert frozen.snapshot["required_points"] == 100
        assert frozen.snapshot["unit_points"] == 10
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_freeze_for_task_wrong_user_raises() -> None:
    """quote token 绑定的 user 与当前 user 不符 → POINTS_QUOTE_INVALID。"""
    db, engine = await _build_async_db()
    try:
        token = _make_quote_token(user_id=OTHER_USER_ID, required_points=10)
        with pytest.raises(PointsDomainError) as exc_info:
            await freeze_for_task(
                db,
                user_id=USER_ID,
                quote_token=token,
                business_type="video_generation",
                category=ModelCategoryKey.video,
                model_id="m1",
                duration_seconds=5,
                resolution="1080p",
            )
        assert exc_info.value.code == "POINTS_QUOTE_INVALID"
        assert exc_info.value.status_code == 400
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_freeze_for_task_price_changed_raises() -> None:
    """重算 required_points 与 token 中不一致 → POINTS_QUOTE_CHANGED（409）。"""
    db, engine = await _build_async_db()
    try:
        # token 声称 5 积分，但实际重算=100
        token = _make_quote_token(required_points=5, duration_seconds=5, resolution="1080p")
        with pytest.raises(PointsDomainError) as exc_info:
            await freeze_for_task(
                db,
                user_id=USER_ID,
                quote_token=token,
                business_type="video_generation",
                category=ModelCategoryKey.video,
                model_id="m1",
                duration_seconds=5,
                resolution="1080p",
            )
        assert exc_info.value.code == "POINTS_QUOTE_CHANGED"
        assert exc_info.value.status_code == 409
        # data 携带最新试算结果
        assert exc_info.value.data.get("required_points") == 100
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_freeze_for_task_params_tampered_raises() -> None:
    """参数被篡改（duration 与 token params_hash 不符）→ POINTS_QUOTE_CHANGED。"""
    db, engine = await _build_async_db()
    try:
        # token 绑定 5s/1080p（required=100 匹配），但调用方传 10s → params_hash 不一致
        token = _make_quote_token(required_points=100, duration_seconds=5, resolution="1080p")
        with pytest.raises(PointsDomainError) as exc_info:
            await freeze_for_task(
                db,
                user_id=USER_ID,
                quote_token=token,
                business_type="video_generation",
                category=ModelCategoryKey.video,
                model_id="m1",
                duration_seconds=10,
                resolution="1080p",
            )
        assert exc_info.value.code == "POINTS_QUOTE_CHANGED"
        assert exc_info.value.status_code == 409
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_freeze_for_task_insufficient_raises() -> None:
    """余额不足 → INSUFFICIENT_POINTS（402）。"""
    db, engine = await _build_async_db()
    try:
        # 未充值，可用 0；required=100
        token = _make_quote_token(required_points=100, duration_seconds=5, resolution="1080p")
        with pytest.raises(PointsDomainError) as exc_info:
            await freeze_for_task(
                db,
                user_id=USER_ID,
                quote_token=token,
                business_type="video_generation",
                category=ModelCategoryKey.video,
                model_id="m1",
                duration_seconds=5,
                resolution="1080p",
            )
        assert exc_info.value.code == "INSUFFICIENT_POINTS"
        assert exc_info.value.status_code == 402
        assert exc_info.value.data.get("required") == 100
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_freeze_for_task_model_not_owned_raises() -> None:
    """quote token 中 model_id 不归属当前 user → MODEL_NOT_OWNED（403）。

    构造一个属于 OTHER_USER 的模型，user=u1 持其 token 冻结 → 拒绝。
    """
    db, engine = await _build_async_db()
    try:
        # 给 OTHER_USER 建一个 provider+model
        async with db.begin():
            db.add(
                Provider(
                    id="p2",
                    user_id=OTHER_USER_ID,
                    name="prov2",
                    base_url="http://x",
                    api_key="k",
                )
            )
            db.add(
                Model(
                    id="m2",
                    user_id=OTHER_USER_ID,
                    name="other-model",
                    category=ModelCategoryKey.video,
                    provider_id="p2",
                    unit_points=10,
                )
            )
        # token 用 m2（属 OTHER_USER），required=100 匹配 m2
        token = _make_quote_token(model_id="m2", required_points=100, duration_seconds=5, resolution="1080p")
        with pytest.raises(PointsDomainError) as exc_info:
            await freeze_for_task(
                db,
                user_id=USER_ID,
                quote_token=token,
                business_type="video_generation",
                category=ModelCategoryKey.video,
                model_id="m2",
                duration_seconds=5,
                resolution="1080p",
            )
        assert exc_info.value.code == "MODEL_NOT_OWNED"
        assert exc_info.value.status_code == 403
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_freeze_for_task_model_id_mismatch_raises_quote_changed() -> None:
    """显式 model_id 与 quote token 绑定的 model_id 不符 → POINTS_QUOTE_CHANGED(409)。

    场景:客户端持 m1 的报价单据,却试图用 m2 的 model_id 下单计费 → 拒绝,避免绕过报价
    用任意模型计费。m2 同属 USER_ID(归属校验会通过),故错误由 model_id 不一致校验先触发。
    """
    db, engine = await _build_async_db()
    try:
        async with db.begin():
            db.add(
                Model(
                    id="m2",
                    user_id=USER_ID,
                    name="another-own-model",
                    category=ModelCategoryKey.video,
                    provider_id="p1",
                    unit_points=10,
                )
            )
        # token 绑定 m1,调用方传 m2
        token = _make_quote_token(model_id="m1", required_points=100, duration_seconds=5, resolution="1080p")
        with pytest.raises(PointsDomainError) as exc_info:
            await freeze_for_task(
                db,
                user_id=USER_ID,
                quote_token=token,
                business_type="video_generation",
                category=ModelCategoryKey.video,
                model_id="m2",
                duration_seconds=5,
                resolution="1080p",
            )
        assert exc_info.value.code == "POINTS_QUOTE_CHANGED"
        assert exc_info.value.status_code == 409
        assert exc_info.value.data.get("requested_model_id") == "m2"
        assert exc_info.value.data.get("quoted_model_id") == "m1"
    finally:
        await db.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# settle_task_billing_sync
# ---------------------------------------------------------------------------


def _build_sync_db_with_task(
    *, billing_id: str | None, status: GenerationTaskStatus, user_id: str = USER_ID
) -> tuple[Session, object, str]:
    """构造同步 SQLite 库并插入一个 GenerationTask 行。返回 (db_session_factory_engine, engine, task_id)。

    注意：返回的 sessionmaker 用于替换 billing 模块的 sync_session_maker。
    """
    engine = create_engine("sqlite:///:memory:", future=True)
    session_local = sessionmaker(engine, class_=Session, expire_on_commit=False)
    import app.models.task  # noqa: F401
    import app.models.points  # noqa: F401
    import app.models.user  # noqa: F401

    Base.metadata.create_all(engine)
    task_id = "task-" + uuid4().hex[:8]
    with session_local() as db:
        db.add(User(id=user_id, username=user_id, hashed_password="x", is_admin=False, is_active=True, token_version=0))
        db.add(
            GenerationTask(
                id=task_id,
                user_id=user_id,
                mode="async_polling",
                task_kind="video_generation",
                status=status.value,
                progress=0,
                payload={"task_kind": "video_generation"},
                result=None,
                error="",
                billing_id=billing_id,
            )
        )
        db.commit()
    return session_local, engine, task_id


async def _seed_task_row_async(
    db_factory,
    *,
    task_id: str,
    billing_id: str | None,
    status: GenerationTaskStatus,
    user_id: str = USER_ID,
) -> None:
    """在 async 库内插入一个 GenerationTask 行（供 settle_task_billing_async 读取）。

    为什么需要：Task 5a/5b 重构后 settle_task_billing_async 直接从 async_session_maker
    读任务终态；测试必须把任务行落到 async 库（与冻结/充值流水同库），settle 才能命中。
    """
    async with db_factory() as db:
        db.add(
            GenerationTask(
                id=task_id,
                user_id=user_id,
                mode="async_polling",
                task_kind="video_generation",
                status=status.value,
                progress=0,
                payload={"task_kind": "video_generation"},
                result=None,
                error="",
                billing_id=billing_id,
            )
        )
        await db.commit()


def test_settle_succeeded_consumes_frozen(monkeypatch) -> None:
    """succeeded → consume：balance 与 frozen 同步减少。

    注意：本测试不在 asyncio 事件循环中运行（settle_task_billing_sync 内部用 asyncio.run
    启动循环驱动 settle_task_billing_async，与 Celery worker 同步上下文一致），故不能用
    @pytest.mark.asyncio。任务行落在 async 库（settle_task_billing_async 的读取侧）。
    """
    import asyncio

    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.task  # noqa: F401
    import app.models.points  # noqa: F401

    async def _seed() -> str:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session_local() as db:
            db.add(User(id=USER_ID, username="u1", hashed_password="x", is_admin=False, is_active=True, token_version=0))
            await db.commit()
            from app.services.points.ledger import recharge, freeze_points, get_points

            await recharge(db, user_id=USER_ID, amount=100, created_by="tester", remark="seed")
            billing_id = uuid4().hex
            await freeze_points(
                db,
                user_id=USER_ID,
                billing_id=billing_id,
                amount=40,
                model_id="m1",
                business_type="video_generation",
                business_id=None,
                snapshot={"required_points": 40},
            )
            before = await get_points(db, user_id=USER_ID)
            assert before.balance == 100 and before.frozen == 40
            return billing_id

    billing_id = asyncio.run(_seed())
    task_id = "task-" + uuid4().hex[:8]
    asyncio.run(
        _seed_task_row_async(
            async_session_local,
            task_id=task_id,
            billing_id=billing_id,
            status=GenerationTaskStatus.succeeded,
        )
    )
    monkeypatch.setattr("app.services.points.billing.async_session_maker", async_session_local)

    settle_task_billing_sync(task_id)

    async def _check():
        from app.services.points.ledger import get_points

        async with async_session_local() as db:
            after = await get_points(db, user_id=USER_ID)
            assert after.balance == 60
            assert after.frozen == 0

    asyncio.run(_check())
    asyncio.run(async_engine.dispose())


def test_settle_failed_unfreezes(monkeypatch) -> None:
    """failed → unfreeze：balance 不变，frozen 减少。"""
    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.task  # noqa: F401
    import app.models.points  # noqa: F401

    import asyncio

    async def _seed() -> str:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session_local() as db:
            db.add(User(id=USER_ID, username="u1", hashed_password="x", is_admin=False, is_active=True, token_version=0))
            await db.commit()
            from app.services.points.ledger import recharge, freeze_points

            await recharge(db, user_id=USER_ID, amount=100, created_by="tester", remark="seed")
            billing_id = uuid4().hex
            await freeze_points(
                db,
                user_id=USER_ID,
                billing_id=billing_id,
                amount=40,
                model_id="m1",
                business_type="video_generation",
                business_id=None,
                snapshot={"required_points": 40},
            )
            return billing_id

    billing_id = asyncio.run(_seed())
    task_id = "task-" + uuid4().hex[:8]
    asyncio.run(
        _seed_task_row_async(
            async_session_local,
            task_id=task_id,
            billing_id=billing_id,
            status=GenerationTaskStatus.failed,
        )
    )
    monkeypatch.setattr("app.services.points.billing.async_session_maker", async_session_local)

    settle_task_billing_sync(task_id)

    async def _check():
        from app.services.points.ledger import get_points

        async with async_session_local() as db:
            after = await get_points(db, user_id=USER_ID)
            assert after.balance == 100  # 解冻不扣
            assert after.frozen == 0

    asyncio.run(_check())
    asyncio.run(async_engine.dispose())


def test_settle_cancelled_unfreezes(monkeypatch) -> None:
    """cancelled → unfreeze（与 failed 同语义）。"""
    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.task  # noqa: F401
    import app.models.points  # noqa: F401

    import asyncio

    async def _seed() -> str:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session_local() as db:
            db.add(User(id=USER_ID, username="u1", hashed_password="x", is_admin=False, is_active=True, token_version=0))
            await db.commit()
            from app.services.points.ledger import recharge, freeze_points

            await recharge(db, user_id=USER_ID, amount=100, created_by="tester", remark="seed")
            billing_id = uuid4().hex
            await freeze_points(
                db,
                user_id=USER_ID,
                billing_id=billing_id,
                amount=30,
                model_id="m1",
                business_type="video_generation",
                business_id=None,
                snapshot={"required_points": 30},
            )
            return billing_id

    billing_id = asyncio.run(_seed())
    task_id = "task-" + uuid4().hex[:8]
    asyncio.run(
        _seed_task_row_async(
            async_session_local,
            task_id=task_id,
            billing_id=billing_id,
            status=GenerationTaskStatus.cancelled,
        )
    )
    monkeypatch.setattr("app.services.points.billing.async_session_maker", async_session_local)

    settle_task_billing_sync(task_id)

    async def _check():
        from app.services.points.ledger import get_points

        async with async_session_local() as db:
            after = await get_points(db, user_id=USER_ID)
            assert after.balance == 100
            assert after.frozen == 0

    asyncio.run(_check())
    asyncio.run(async_engine.dispose())


def test_settle_non_terminal_is_noop(monkeypatch) -> None:
    """running（非终态）→ 不结算。"""
    import asyncio

    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.task  # noqa: F401
    import app.models.points  # noqa: F401

    task_id = "task-" + uuid4().hex[:8]

    async def _seed():
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await _seed_task_row_async(
            async_session_local,
            task_id=task_id,
            billing_id="b-running",
            status=GenerationTaskStatus.running,
        )

    asyncio.run(_seed())
    monkeypatch.setattr("app.services.points.billing.async_session_maker", async_session_local)

    # 不应抛错，也不应有副作用
    settle_task_billing_sync(task_id)

    asyncio.run(async_engine.dispose())


def test_settle_billing_id_none_is_noop(monkeypatch) -> None:
    """billing_id=None → 直接跳过（存量任务零行为变更）。"""
    import asyncio

    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.task  # noqa: F401
    import app.models.points  # noqa: F401

    task_id = "task-" + uuid4().hex[:8]

    async def _seed():
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await _seed_task_row_async(
            async_session_local,
            task_id=task_id,
            billing_id=None,
            status=GenerationTaskStatus.succeeded,
        )

    asyncio.run(_seed())
    monkeypatch.setattr("app.services.points.billing.async_session_maker", async_session_local)

    settle_task_billing_sync(task_id)

    asyncio.run(async_engine.dispose())


def test_settle_idempotent(monkeypatch) -> None:
    """调用两次只产生一次 consume（账本幂等保证）。"""
    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.task  # noqa: F401
    import app.models.points  # noqa: F401
    import asyncio

    async def _seed() -> str:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session_local() as db:
            db.add(User(id=USER_ID, username="u1", hashed_password="x", is_admin=False, is_active=True, token_version=0))
            await db.commit()
            from app.services.points.ledger import recharge, freeze_points

            await recharge(db, user_id=USER_ID, amount=100, created_by="tester", remark="seed")
            billing_id = uuid4().hex
            await freeze_points(
                db,
                user_id=USER_ID,
                billing_id=billing_id,
                amount=40,
                model_id="m1",
                business_type="video_generation",
                business_id=None,
                snapshot={"required_points": 40},
            )
            return billing_id

    billing_id = asyncio.run(_seed())
    task_id = "task-" + uuid4().hex[:8]
    asyncio.run(
        _seed_task_row_async(
            async_session_local,
            task_id=task_id,
            billing_id=billing_id,
            status=GenerationTaskStatus.succeeded,
        )
    )
    monkeypatch.setattr("app.services.points.billing.async_session_maker", async_session_local)

    settle_task_billing_sync(task_id)
    settle_task_billing_sync(task_id)  # 第二次必须幂等

    async def _check():
        from app.services.points.ledger import get_points

        async with async_session_local() as db:
            after = await get_points(db, user_id=USER_ID)
            # 只扣一次：balance=60, frozen=0
            assert after.balance == 60
            assert after.frozen == 0

    asyncio.run(_check())
    asyncio.run(async_engine.dispose())


# ---------------------------------------------------------------------------
# billing_id 通道：TaskManager.create → GenerationTask / TaskRecord
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_manager_create_persists_billing_id() -> None:
    """billing_id 经 TaskManager.create 落到 GenerationTask 与 TaskRecord。"""
    import app.models.task  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    class _NoopTask:
        async def run(self, *a, **k):
            return None

        async def status(self):
            return {}

        async def is_done(self):
            return False

        async def get_result(self):
            return None

    try:
        async with session_local() as db:
            store = SqlAlchemyTaskStore(db)
            tm = TaskManager(store=store, strategies={})
            rec = await tm.create(
                task=_NoopTask(),
                mode=DeliveryMode.async_polling,
                user_id="test-user",
                task_kind="script_divide",
                run_args={},
                billing_id="b1",
            )
            assert rec.billing_id == "b1"
            row = await db.get(GenerationTask, rec.id)
            assert row is not None
            assert row.billing_id == "b1"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_task_manager_create_default_billing_id_none() -> None:
    """不传 billing_id（默认 None）保持现有行为：列为 NULL。"""
    import app.models.task  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    class _NoopTask:
        async def run(self, *a, **k):
            return None

        async def status(self):
            return {}

        async def is_done(self):
            return False

        async def get_result(self):
            return None

    try:
        async with session_local() as db:
            store = SqlAlchemyTaskStore(db)
            tm = TaskManager(store=store, strategies={})
            rec = await tm.create(
                task=_NoopTask(),
                mode=DeliveryMode.async_polling,
                user_id="test-user",
                task_kind="script_divide",
                run_args={},
            )
            assert rec.billing_id is None
            row = await db.get(GenerationTask, rec.id)
            assert row is not None
            assert row.billing_id is None
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Minor 5：run_task_celery finally 结算钩子(executor 抛异常仍触发结算)
# ---------------------------------------------------------------------------


def test_run_task_celery_finally_settles_on_executor_exception(monkeypatch) -> None:
    """executor.run 抛异常时,run_task_celery 的 finally 仍触发结算 → 冻结积分被解冻。

    策略:
    - sync 侧:用真实 sync SessionMaker(含一个 failed 状态的 GenerationTask + billing_id)
      替换 execute_task 模块引用的 sync_session_maker,使 run_task_celery 能读到任务行并解析
      task_kind → 解析到 crashing executor;
    - async 侧:同一 task_id + billing_id 的 GenerationTask 行 + 冻结积分,落在 async 库
      (settle_task_billing_async 的读取侧);finally 钩子委托 asyncio.run(settle_task_billing_async)
      命中 async 任务行 → unfreeze;
    - monkeypatch task_executor_registry.resolve 返回一个 .run 会抛 RuntimeError 的假执行器
      (模拟 worker 执行失败);
    - 调用 `run_task_celery.run(task_id)`(Celery 装饰器下未装饰的可调用对象,直接同步调用),
      断言:即便执行器抛异常,frozen 仍被解冻(balance 不变、frozen 归零),证明 finally 结算钩子
      确实触发且走通新的 async 结算核心。
    """
    import asyncio

    from app.tasks import execute_task

    # 1. async 侧:建库 + 充值 + 冻结(与 settle 测试同款 seed)
    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.task  # noqa: F401
    import app.models.points  # noqa: F401

    async def _seed() -> str:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session_local() as db:
            db.add(User(id=USER_ID, username="u1", hashed_password="x", is_admin=False, is_active=True, token_version=0))
            await db.commit()
            from app.services.points.ledger import freeze_points, recharge

            await recharge(db, user_id=USER_ID, amount=100, created_by="tester", remark="seed")
            billing_id = uuid4().hex
            await freeze_points(
                db,
                user_id=USER_ID,
                billing_id=billing_id,
                amount=40,
                model_id="m1",
                business_type="video_generation",
                business_id=None,
                snapshot={"required_points": 40},
            )
            return billing_id

    billing_id = asyncio.run(_seed())

    # 2. sync 侧:建一个 failed 终态的任务行(模拟 executor 失败后已回写状态),
    #    供 run_task_celery 解析 task_kind。
    sync_session_local, sync_engine, task_id = _build_sync_db_with_task(
        billing_id=billing_id, status=GenerationTaskStatus.failed
    )
    # async 侧也插入同一任务行(settle_task_billing_async 的读取侧)
    asyncio.run(
        _seed_task_row_async(
            async_session_local,
            task_id=task_id,
            billing_id=billing_id,
            status=GenerationTaskStatus.failed,
        )
    )
    monkeypatch.setattr("app.services.points.billing.async_session_maker", async_session_local)
    # execute_task 内部用同一 SessionMaker 读任务行
    monkeypatch.setattr("app.tasks.execute_task.sync_session_maker", sync_session_local)

    # 3. 假执行器:run 抛异常(模拟 worker 执行崩溃)。resolve 返回它。
    class _CrashingExecutor:
        def run(self, task_id: str) -> None:  # noqa: ANN001
            raise RuntimeError("simulated executor failure")

    monkeypatch.setattr(
        "app.tasks.execute_task.task_executor_registry.resolve",
        lambda task_kind: _CrashingExecutor(),
    )

    # 4. 调用未装饰的可调用对象(Celery task 的 .run 即原始函数体),应抛 RuntimeError,
    #    但 finally 必须先触发结算。
    with pytest.raises(RuntimeError, match="simulated executor failure"):
        execute_task.run_task_celery.run(task_id)

    # 5. 断言:尽管执行器抛异常,冻结积分已被 finally 钩子解冻。
    async def _check():
        from app.services.points.ledger import get_points

        async with async_session_local() as db:
            after = await get_points(db, user_id=USER_ID)
            assert after.balance == 100  # 解冻不扣
            assert after.frozen == 0  # 冻结被释放

    asyncio.run(_check())
    asyncio.run(async_engine.dispose())
    sync_engine.dispose()


# ---------------------------------------------------------------------------
# Task 5b：image / async-text 任务冻结集成 + cancel-unfreeze + merge/variant 结算
# ---------------------------------------------------------------------------


async def _seed_async_with_text_and_image_models(db: AsyncSession) -> None:
    """建表并预置 user/provider + 文本模型 m_text 与图片模型 m_img。

    文本：unit_points=7（category=text → required = unit_points * 1 = 7）。
    图片：unit_points=5（category=image → required = unit_points * 1 = 5）。
    """
    import app.models.task  # noqa: F401
    import app.models.points  # noqa: F401
    import app.models.task_links  # noqa: F401

    async with db.begin():
        db.add(User(id=USER_ID, username="u1", hashed_password="x", is_admin=False, is_active=True, token_version=0))
        db.add(Provider(id="p1", user_id=USER_ID, name="prov", base_url="http://x", api_key="k"))
        db.add(
            Model(
                id="m_text",
                user_id=USER_ID,
                name="text-model",
                category=ModelCategoryKey.text,
                provider_id="p1",
                unit_points=7,
            )
        )
        db.add(
            Model(
                id="m_img",
                user_id=USER_ID,
                name="img-model",
                category=ModelCategoryKey.image,
                provider_id="p1",
                unit_points=5,
            )
        )


def _make_text_quote_token(*, required_points: int = 7, model_id: str = "m_text") -> str:
    """构造合法的文本任务 quote_token（category=text，generation_count=1）。"""
    params_hash = hash_quote_params(
        {
            "category": str(ModelCategoryKey.text),
            "duration_seconds": None,
            "resolution": None,
            "generation_count": 1,
        }
    )
    return create_quote_token(
        QuoteClaims(
            user_id=USER_ID,
            business_type="script_divide",
            model_id=model_id,
            params_hash=params_hash,
            required_points=required_points,
        )
    )


def _make_image_quote_token(*, required_points: int = 5, model_id: str = "m_img") -> str:
    """构造合法的图片任务 quote_token（category=image，generation_count=1）。"""
    params_hash = hash_quote_params(
        {
            "category": str(ModelCategoryKey.image),
            "duration_seconds": None,
            "resolution": None,
            "generation_count": 1,
        }
    )
    return create_quote_token(
        QuoteClaims(
            user_id=USER_ID,
            business_type="image_generation",
            model_id=model_id,
            params_hash=params_hash,
            required_points=required_points,
        )
    )


@pytest.mark.asyncio
async def test_create_divide_task_freezes_points_on_fresh_create() -> None:
    """文本异步任务（divide）首次创建冻结积分；business_type=script_divide。"""
    from app.services.points.ledger import get_points, recharge
    from app.services.script_processing_tasks import create_divide_task

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = session_local()
    try:
        await _seed_async_with_text_and_image_models(db)
        await recharge(db, user_id=USER_ID, amount=100, created_by="tester", remark="seed")

        token = _make_text_quote_token(required_points=7)
        result = await create_divide_task(
            db,
            user_id=USER_ID,
            chapter_id="chapter-1",
            script_text="剧本",
            write_to_db=False,
            quote_token=token,
        )
        assert result.reused is False
        pts = await get_points(db, user_id=USER_ID)
        assert pts.balance == 100
        assert pts.frozen == 7
        # 任务行携带 billing_id（非空）
        row = await db.get(GenerationTask, result.task_id)
        assert row is not None and row.billing_id
        # business_type 落到冻结流水
        from app.models.points import PointTransaction, PointTransactionType
        from sqlalchemy import select

        freeze_tx = (
            await db.execute(
                select(PointTransaction).where(
                    PointTransaction.user_id == USER_ID,
                    PointTransaction.type == PointTransactionType.freeze,
                )
            )
        ).scalars().first()
        assert freeze_tx is not None
        assert freeze_tx.business_type == "script_divide"
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_divide_task_reuse_skips_freeze() -> None:
    """复用进行中文本任务时不冻结（第二次调用 reused=True，frozen 不增加）。"""
    from app.services.points.ledger import get_points, recharge
    from app.services.script_processing_tasks import create_divide_task

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = session_local()
    try:
        await _seed_async_with_text_and_image_models(db)
        await recharge(db, user_id=USER_ID, amount=100, created_by="tester", remark="seed")

        token = _make_text_quote_token(required_points=7)
        first = await create_divide_task(
            db,
            user_id=USER_ID,
            chapter_id="chapter-1",
            script_text="第一版",
            write_to_db=False,
            quote_token=token,
        )
        # 第二次：同一 chapter_id，任务仍在 pending → 复用，不冻结
        second = await create_divide_task(
            db,
            user_id=USER_ID,
            chapter_id="chapter-1",
            script_text="第二版",
            write_to_db=False,
            quote_token=_make_text_quote_token(required_points=7),
        )
        assert second.reused is True
        assert second.task_id == first.task_id
        pts = await get_points(db, user_id=USER_ID)
        assert pts.frozen == 7  # 只冻结一次
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_divide_task_insufficient_raises_no_task() -> None:
    """余额不足：PointsDomainError 上抛，任务不被创建。"""
    from app.services.points.billing import PointsDomainError
    from app.services.script_processing_tasks import create_divide_task

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = session_local()
    try:
        await _seed_async_with_text_and_image_models(db)
        # 未充值，可用 0
        token = _make_text_quote_token(required_points=7)
        with pytest.raises(PointsDomainError) as exc_info:
            await create_divide_task(
                db,
                user_id=USER_ID,
                chapter_id="chapter-1",
                script_text="剧本",
                write_to_db=False,
                quote_token=token,
            )
        assert exc_info.value.code == "INSUFFICIENT_POINTS"
        # 无任务行
        from sqlalchemy import select

        rows = (await db.execute(select(GenerationTask))).scalars().all()
        assert rows == []
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_analysis_task_freezes_with_correct_business_type() -> None:
    """分析类任务（以 character_portrait 为例）冻结且 business_type 正确。"""
    from app.models.points import PointTransaction, PointTransactionType
    from app.services.points.ledger import get_points, recharge
    from app.services.script_processing_tasks import (
        CHARACTER_PORTRAIT_ANALYSIS_RELATION_TYPE,
        create_character_portrait_task,
    )
    from sqlalchemy import select

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = session_local()
    try:
        await _seed_async_with_text_and_image_models(db)
        await recharge(db, user_id=USER_ID, amount=100, created_by="tester", remark="seed")

        token = _make_text_quote_token(required_points=7)
        result = await create_character_portrait_task(
            db,
            user_id=USER_ID,
            relation_entity_id="char-1",
            character_context=None,
            character_description="主角",
            quote_token=token,
        )
        assert result.reused is False
        assert result.relation_type == CHARACTER_PORTRAIT_ANALYSIS_RELATION_TYPE
        pts = await get_points(db, user_id=USER_ID)
        assert pts.frozen == 7
        freeze_tx = (
            await db.execute(
                select(PointTransaction).where(
                    PointTransaction.user_id == USER_ID,
                    PointTransaction.type == PointTransactionType.freeze,
                )
            )
        ).scalars().first()
        assert freeze_tx is not None
        assert freeze_tx.business_type == "script_character_portrait"
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_image_task_and_link_freezes_then_reuses() -> None:
    """图片任务：首次冻结；复用进行中任务不重复冻结。"""
    from app.services.points.ledger import get_points, recharge
    from app.services.studio.image_task_runner import create_image_task_and_link

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = session_local()
    try:
        await _seed_async_with_text_and_image_models(db)
        await recharge(db, user_id=USER_ID, amount=100, created_by="tester", remark="seed")
        # monkeypatch resolve_image_model / load_provider_config，避免外部依赖
        import app.services.studio.image_task_runner as runner

        original_resolve = runner.resolve_image_model
        original_load = runner.load_provider_config

        async def _fake_resolve(_db, _model_id, *, user_id):
            return type("M", (), {"id": "m_img", "name": "img-model", "provider_id": "p1"})()

        async def _fake_load(_db, _provider_id):
            return type("PC", (), {"provider": "openai", "api_key": "k", "base_url": None})()

        runner.resolve_image_model = _fake_resolve  # type: ignore[assignment]
        runner.load_provider_config = _fake_load  # type: ignore[assignment]
        # 关闭任务派发（避免触发 Celery）
        import app.tasks.execute_task as exec_mod

        original_enqueue = exec_mod.enqueue_task_execution
        exec_mod.enqueue_task_execution = lambda _tid: None  # type: ignore[assignment]
        try:
            token = _make_image_quote_token(required_points=5)
            first_id = await create_image_task_and_link(
                db=db,
                user_id=USER_ID,
                model_id="m_img",
                relation_type="actor_image",
                relation_entity_id="1",
                prompt="演员形象",
                quote_token=token,
            )
            pts_after_first = await get_points(db, user_id=USER_ID)
            assert pts_after_first.frozen == 5
            row = await db.get(GenerationTask, first_id)
            assert row is not None and row.billing_id

            # 第二次：同一 (relation_type, relation_entity_id)，任务 pending → 复用，不冻结
            second_id = await create_image_task_and_link(
                db=db,
                user_id=USER_ID,
                model_id="m_img",
                relation_type="actor_image",
                relation_entity_id="1",
                prompt="再来一次",
                quote_token=_make_image_quote_token(required_points=5),
            )
            assert second_id == first_id
            pts_after_second = await get_points(db, user_id=USER_ID)
            assert pts_after_second.frozen == 5  # 仍只冻结一次
        finally:
            runner.resolve_image_model = original_resolve  # type: ignore[assignment]
            runner.load_provider_config = original_load  # type: ignore[assignment]
            exec_mod.enqueue_task_execution = original_enqueue  # type: ignore[assignment]
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_image_task_insufficient_raises_and_no_task() -> None:
    """图片任务余额不足：PointsDomainError 上抛，任务不被创建。"""
    from app.services.points.billing import PointsDomainError
    from app.services.studio.image_task_runner import create_image_task_and_link

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = session_local()
    try:
        await _seed_async_with_text_and_image_models(db)
        # 未充值
        token = _make_image_quote_token(required_points=5)
        with pytest.raises(PointsDomainError) as exc_info:
            await create_image_task_and_link(
                db=db,
                user_id=USER_ID,
                model_id="m_img",
                relation_type="actor_image",
                relation_entity_id="1",
                prompt="演员形象",
                quote_token=token,
            )
        assert exc_info.value.code == "INSUFFICIENT_POINTS"
        from sqlalchemy import select

        rows = (await db.execute(select(GenerationTask))).scalars().all()
        assert rows == []
    finally:
        await db.close()
        await engine.dispose()


def test_cancel_task_unfreezes_billing(monkeypatch) -> None:
    """取消立即生效时，cancel_task 解冻冻结积分（frozen 回退、balance 不变）。

    策略：构造一个带 billing_id 的 pending 任务行 + 已冻结的积分账户，调用
    cancel_task 路由（revoke_task_execution 成功 → effective_immediately=True），
    断言路由内 unfreeze_frozen 被触发，frozen 归零。
    """
    import asyncio

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1.routes.film import task_status as cancel_route
    from app.dependencies import get_current_user, get_db
    from app.services.points.ledger import freeze_points, get_points, recharge

    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.task  # noqa: F401
    import app.models.points  # noqa: F401
    import app.models.task_links  # noqa: F401

    async def _seed() -> str:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session_local() as db:
            db.add(User(id=USER_ID, username="u1", hashed_password="x", is_admin=False, is_active=True, token_version=0))
            await db.commit()
            await recharge(db, user_id=USER_ID, amount=100, created_by="tester", remark="seed")
            billing_id = uuid4().hex
            await freeze_points(
                db,
                user_id=USER_ID,
                billing_id=billing_id,
                amount=30,
                model_id="m_text",
                business_type="script_divide",
                business_id=None,
                snapshot={"required_points": 30},
            )
            # 插入一个 pending 任务（cancel_task 会把它标记为 cancelled → effective）
            task_id = "task-" + uuid4().hex[:8]
            db.add(
                GenerationTask(
                    id=task_id,
                    user_id=USER_ID,
                    mode="async_polling",
                    task_kind="script_divide",
                    status=GenerationTaskStatus.pending.value,
                    progress=0,
                    payload={"task_kind": "script_divide"},
                    result=None,
                    error="",
                    billing_id=billing_id,
                )
            )
            await db.commit()
            return task_id

    task_id = asyncio.run(_seed())

    # 让 revoke_task_execution 始终返回 True（→ effective_immediately=True）
    monkeypatch.setattr(cancel_route, "revoke_task_execution", lambda _tid: True)

    async def _override_db():
        async with async_session_local() as db:
            yield db

    class _FakeUser:
        id = USER_ID

    async def _override_user():
        return _FakeUser()

    app_obj = FastAPI()
    app_obj.include_router(cancel_route.router, prefix="/api/v1/film")
    app_obj.dependency_overrides[get_db] = _override_db
    app_obj.dependency_overrides[get_current_user] = _override_user

    client = TestClient(app_obj)
    resp = client.post(f"/api/v1/film/tasks/{task_id}/cancel", json={"reason": "user aborted"})
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["effective_immediately"] is True

    async def _check():
        async with async_session_local() as db:
            after = await get_points(db, user_id=USER_ID)
            assert after.balance == 100
            assert after.frozen == 0

    asyncio.run(_check())
    asyncio.run(async_engine.dispose())


def test_cancel_task_without_billing_id_is_noop(monkeypatch) -> None:
    """取消 billing_id 为空的任务（存量/未计费）→ 不触达账本，正常返回。"""
    import asyncio

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1.routes.film import task_status as cancel_route
    from app.dependencies import get_current_user, get_db

    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.task  # noqa: F401
    import app.models.task_links  # noqa: F401

    async def _seed() -> str:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session_local() as db:
            db.add(User(id=USER_ID, username="u1", hashed_password="x", is_admin=False, is_active=True, token_version=0))
            await db.commit()
            task_id = "task-" + uuid4().hex[:8]
            db.add(
                GenerationTask(
                    id=task_id,
                    user_id=USER_ID,
                    mode="async_polling",
                    task_kind="script_divide",
                    status=GenerationTaskStatus.pending.value,
                    progress=0,
                    payload={"task_kind": "script_divide"},
                    result=None,
                    error="",
                    billing_id=None,
                )
            )
            await db.commit()
            return task_id

    task_id = asyncio.run(_seed())
    monkeypatch.setattr(cancel_route, "revoke_task_execution", lambda _tid: True)

    async def _override_db():
        async with async_session_local() as db:
            yield db

    class _FakeUser:
        id = USER_ID

    async def _override_user():
        return _FakeUser()

    app_obj = FastAPI()
    app_obj.include_router(cancel_route.router, prefix="/api/v1/film")
    app_obj.dependency_overrides[get_db] = _override_db
    app_obj.dependency_overrides[get_current_user] = _override_user

    client = TestClient(app_obj)
    resp = client.post(f"/api/v1/film/tasks/{task_id}/cancel", json={"reason": "noop"})
    assert resp.status_code == 200
    asyncio.run(async_engine.dispose())


@pytest.mark.asyncio
async def test_in_process_merge_task_settles_on_success_and_failure(monkeypatch) -> None:
    """进程内 merge/variant 任务（不走 Celery）在成功/失败分支触发 settle。

    为什么是 async 测试：`_settle_billing` 重构后是 async（直接 `await settle_task_billing_async`），
    与 run_merge_task/run_variant_task 终态点的真实调用形态一致。本测试直接 `await` 它，
    同时也证明 `settle_task_billing_async` 在已运行的事件循环内可被直接调用（生产 merge/variant 场景）。

    策略：在 async 库内 seed User + 冻结 + 终态任务行，monkeypatch billing 模块的
    async_session_maker，直接 `await _settle_billing(task_id)`，断言账本状态变化
    （成功→consume：balance 60、frozen 0；失败→unfreeze：balance 不变、frozen 0）。
    """
    from app.services.points.ledger import freeze_points, get_points, recharge
    from app.services.script_processing_tasks import _settle_billing

    # ---- 成功路径 ----
    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.task  # noqa: F401
    import app.models.points  # noqa: F401

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_local() as db:
        db.add(User(id=USER_ID, username="u1", hashed_password="x", is_admin=False, is_active=True, token_version=0))
        await db.commit()
        await recharge(db, user_id=USER_ID, amount=100, created_by="tester", remark="seed")
        billing_id_ok = uuid4().hex
        await freeze_points(
            db,
            user_id=USER_ID,
            billing_id=billing_id_ok,
            amount=40,
            model_id="m_text",
            business_type="script_merge",
            business_id=None,
            snapshot={"required_points": 40},
        )
        success_task_id = "merge-ok-" + uuid4().hex[:8]
        db.add(
            GenerationTask(
                id=success_task_id,
                user_id=USER_ID,
                mode="async_polling",
                task_kind="script_merge",
                status=GenerationTaskStatus.succeeded.value,
                progress=100,
                payload={"task_kind": "script_merge"},
                result={"ok": True},
                error="",
                billing_id=billing_id_ok,
            )
        )
        await db.commit()

    monkeypatch.setattr("app.services.points.billing.async_session_maker", async_session_local)

    # 成功 → consume（balance 60、frozen 0）
    await _settle_billing(success_task_id)

    async with async_session_local() as db:
        after = await get_points(db, user_id=USER_ID)
        assert after.balance == 60
        assert after.frozen == 0
    await async_engine.dispose()

    # ---- 失败路径 ----
    async_engine2 = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local2 = async_sessionmaker(async_engine2, class_=AsyncSession, expire_on_commit=False)

    async with async_engine2.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_local2() as db:
        db.add(User(id=USER_ID, username="u1", hashed_password="x", is_admin=False, is_active=True, token_version=0))
        await db.commit()
        await recharge(db, user_id=USER_ID, amount=80, created_by="tester", remark="seed2")
        billing_id_fail = uuid4().hex
        await freeze_points(
            db,
            user_id=USER_ID,
            billing_id=billing_id_fail,
            amount=30,
            model_id="m_text",
            business_type="script_variant",
            business_id=None,
            snapshot={"required_points": 30},
        )
        fail_task_id = "variant-fail-" + uuid4().hex[:8]
        db.add(
            GenerationTask(
                id=fail_task_id,
                user_id=USER_ID,
                mode="async_polling",
                task_kind="script_variant",
                status=GenerationTaskStatus.failed.value,
                progress=0,
                payload={"task_kind": "script_variant"},
                result=None,
                error="boom",
                billing_id=billing_id_fail,
            )
        )
        await db.commit()

    monkeypatch.setattr("app.services.points.billing.async_session_maker", async_session_local2)

    # 失败 → unfreeze（balance 不变、frozen 0）
    await _settle_billing(fail_task_id)

    async with async_session_local2() as db:
        after = await get_points(db, user_id=USER_ID)
        assert after.balance == 80  # 解冻不扣
        assert after.frozen == 0
    await async_engine2.dispose()


# ---------------------------------------------------------------------------
# Bug fix：run_merge_task / run_variant_task 的「早期取消」分支必须结算
#
# 背景：merge/variant 经 asyncio.create_task 执行（不走 Celery），且每个函数有三个
# `_cancel_if_requested` 取消分支——entry、try-start、result-after。原先只有 result-after
# 分支调用 `_settle_billing`，导致 entry / try-start 取消时冻结积分永不结算 → 永久泄漏。
#
# 二次修复（本批）：原 `_settle_billing` 委托 `settle_task_billing_sync`（内部 asyncio.run），
# 在 asyncio.create_task 启动的事件循环里会抛 RuntimeError 被静默吞掉 → 所有分支结算实际失效。
# 现已改为 `await settle_task_billing_async(task_id)`（直接在已运行循环内结算）。
#
# 测试策略：
# - 直接驱动 `run_merge_task` / `run_variant_task`；
# - monkeypatch 模块内 `async_session_maker`（任务体读写）与 billing 模块的
#   `async_session_maker`（settle_task_billing_async 读取）→ 同一测试 async 会话工厂；
# - monkeypatch `_cancel_if_requested` → 控制命中 entry / try-start 早期取消分支；
# - 不再 stub `_settle_billing`：让真实的 `settle_task_billing_async` 跑通，断言账本状态变化
#   （cancelled → unfreeze：balance 不变、frozen 归零），证明 async 结算路径在生产中确实生效。
# ---------------------------------------------------------------------------


async def _build_cancel_test_db(
    *, task_kind: str, business_type: str, amount: int, balance: int
) -> tuple[object, object, str, str, str]:
    """构造 cancel 测试所需 DB：user + 冻结 + pending 任务行。

    返回 (engine, async_session_local, task_id, billing_id, USER_ID)。
    """
    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.task  # noqa: F401
    import app.models.points  # noqa: F401
    import app.models.task_links  # noqa: F401

    from app.services.points.ledger import freeze_points, recharge

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_local() as db:
        db.add(User(id=USER_ID, username="u1", hashed_password="x", is_admin=False, is_active=True, token_version=0))
        await db.commit()
        await recharge(db, user_id=USER_ID, amount=balance, created_by="tester", remark="seed")
        billing_id = uuid4().hex
        await freeze_points(
            db,
            user_id=USER_ID,
            billing_id=billing_id,
            amount=amount,
            model_id="m_text",
            business_type=business_type,
            business_id=None,
            snapshot={"required_points": amount},
        )
        task_id = f"{task_kind}-cancel-" + uuid4().hex[:8]
        db.add(
            GenerationTask(
                id=task_id,
                user_id=USER_ID,
                mode="async_polling",
                task_kind=task_kind,
                status=GenerationTaskStatus.pending.value,
                progress=0,
                payload={"task_kind": task_kind, "run_args": {}},
                result=None,
                error="",
                billing_id=billing_id,
            )
        )
        await db.commit()
    return async_engine, async_session_local, task_id, billing_id, USER_ID


def _wire_async_session(monkeypatch, async_session_local) -> None:
    """把任务体与 billing 结算核心指向同一测试 async 会话工厂。

    - `script_processing_tasks.async_session_maker`：run_merge_task/run_variant_task 体内读写；
    - `app.services.points.billing.async_session_maker`：settle_task_billing_async 读任务终态 + 账本操作。
    """
    from app.services import script_processing_tasks as spt

    monkeypatch.setattr(spt, "async_session_maker", async_session_local)
    monkeypatch.setattr("app.services.points.billing.async_session_maker", async_session_local)


def _make_cancel_stub(*, cancel_on_call: int = 1):
    """构造 `_cancel_if_requested` 的测试替身：命中第 `cancel_on_call` 次及之后返回 True，
    且在命中时**真正调用 `store.mark_cancelled` + `db.commit`**（与生产实现一致）。

    为什么必须真正 mark_cancelled：现在跑的是真实 `settle_task_billing_async`，它读任务终态；
    若只返回 True 不落库，任务行仍停留在 pending/running → 非终态 → settle no-op → 冻结不释放。
    旧 spy 测试因为 stub 了 _settle_billing 直接解冻，绕过了终态读取，故不需要真正 mark_cancelled。
    """
    state = {"n": 0}

    async def _stub(store, task_id, db):  # noqa: ANN001 - test stub
        state["n"] += 1
        if state["n"] < cancel_on_call:
            return False
        await store.mark_cancelled(task_id)
        await db.commit()
        return True

    return _stub


@pytest.mark.asyncio
async def test_run_merge_task_settles_on_entry_cancel(monkeypatch) -> None:
    """merge 入口取消（首次 `_cancel_if_requested` 即 True）→ 真实 async 结算释放冻结。

    覆盖 run_merge_task entry-cancel 分支：修复前直接 return 不结算 → 冻结泄漏；
    二次修复前 `_settle_billing` 委托 sync 桥在运行循环中静默失败；现在 `await
    settle_task_billing_async` 在事件循环内直接解冻 → frozen 归零。
    """
    from app.services.points.ledger import get_points

    async_engine, async_session_local, task_id, _bid, _uid = await _build_cancel_test_db(
        task_kind="script_merge", business_type="script_merge", amount=40, balance=100
    )
    _wire_async_session(monkeypatch, async_session_local)

    monkeypatch.setattr(
        "app.services.script_processing_tasks._cancel_if_requested",
        _make_cancel_stub(cancel_on_call=1),
    )

    await _run_merge_task_via_public_api(task_id)

    async with async_session_local() as db:
        after = await get_points(db, user_id=USER_ID)
        assert after.balance == 100  # 解冻不扣
        assert after.frozen == 0  # 冻结释放
    await async_engine.dispose()


@pytest.mark.asyncio
async def test_run_merge_task_settles_on_try_start_cancel(monkeypatch) -> None:
    """merge try-start 取消（第二次 `_cancel_if_requested` True）→ 真实 async 结算释放冻结。

    覆盖 run_merge_task try-start-cancel 分支。首次调用（entry）返回 False 让函数进入
    running；第二次（try-start）返回 True → 取消 → 结算。
    """
    from app.services.points.ledger import get_points

    async_engine, async_session_local, task_id, _bid, _uid = await _build_cancel_test_db(
        task_kind="script_merge", business_type="script_merge", amount=40, balance=100
    )
    _wire_async_session(monkeypatch, async_session_local)

    monkeypatch.setattr(
        "app.services.script_processing_tasks._cancel_if_requested",
        _make_cancel_stub(cancel_on_call=2),
    )

    await _run_merge_task_via_public_api(task_id)

    async with async_session_local() as db:
        after = await get_points(db, user_id=USER_ID)
        assert after.balance == 100
        assert after.frozen == 0
    await async_engine.dispose()


@pytest.mark.asyncio
async def test_run_variant_task_settles_on_entry_cancel(monkeypatch) -> None:
    """variant 入口取消 → 真实 async 结算释放冻结。覆盖 run_variant_task entry-cancel 分支。"""
    from app.services.points.ledger import get_points

    async_engine, async_session_local, task_id, _bid, _uid = await _build_cancel_test_db(
        task_kind="script_variant", business_type="script_variant", amount=30, balance=90
    )
    _wire_async_session(monkeypatch, async_session_local)

    monkeypatch.setattr(
        "app.services.script_processing_tasks._cancel_if_requested",
        _make_cancel_stub(cancel_on_call=1),
    )

    await _run_variant_task_via_public_api(task_id)

    async with async_session_local() as db:
        after = await get_points(db, user_id=USER_ID)
        assert after.balance == 90
        assert after.frozen == 0
    await async_engine.dispose()


@pytest.mark.asyncio
async def test_run_variant_task_settles_on_try_start_cancel(monkeypatch) -> None:
    """variant try-start 取消 → 真实 async 结算释放冻结。覆盖 run_variant_task try-start 分支。"""
    from app.services.points.ledger import get_points

    async_engine, async_session_local, task_id, _bid, _uid = await _build_cancel_test_db(
        task_kind="script_variant", business_type="script_variant", amount=30, balance=90
    )
    _wire_async_session(monkeypatch, async_session_local)

    monkeypatch.setattr(
        "app.services.script_processing_tasks._cancel_if_requested",
        _make_cancel_stub(cancel_on_call=2),
    )

    await _run_variant_task_via_public_api(task_id)

    async with async_session_local() as db:
        after = await get_points(db, user_id=USER_ID)
        assert after.balance == 90
        assert after.frozen == 0
    await async_engine.dispose()


async def _run_merge_task_via_public_api(task_id: str) -> None:
    """直接 await run_merge_task（与 asyncio.create_task 启动后等价的执行路径）。"""
    from app.services.script_processing_tasks import run_merge_task

    await run_merge_task(task_id)


async def _run_variant_task_via_public_api(task_id: str) -> None:
    """直接 await run_variant_task（与 asyncio.create_task 启动后等价的执行路径）。"""
    from app.services.script_processing_tasks import run_variant_task

    await run_variant_task(task_id)


# ---------------------------------------------------------------------------
# Task 5c：视频分辨率标准化 + 视频任务冻结
#
# 覆盖：
# - 契约：VideoGenerationInput 接受 resolution；extra="forbid" 下不声明会拒绝。
# - build_run_args：resolution 透传进 input_dict。
# - 路由冻结：freeze_for_task 在 tm.create 之前；tm.create 失败回滚；billing_id 落任务行。
# - 720p vs 1080p 冻结金额不同（factor 1.0 vs 2.0）。
# - 报价篡改（resolution 不符）→ POINTS_QUOTE_CHANGED。
# - 适配器：openai 按 resolution 映射 size；bailian 1080p 拒绝；vidu 透传 resolution。
# - 视频任务终态结算（succeeded→consume / failed→unfreeze）：由 run_task_celery finally
#   的 settle_task_billing_sync 覆盖（5a 已实现），此处直接构造 GenerationTask 行验证。
# ---------------------------------------------------------------------------


def test_video_generation_input_accepts_resolution_field() -> None:
    """契约层：VideoGenerationInput 接受 resolution 字段（720p/1080p），None 兼容存量。"""
    from app.core.contracts.video_generation import VideoGenerationInput

    # 720p
    inp_720 = VideoGenerationInput.model_validate({"prompt": "x", "ratio": "16:9", "resolution": "720p"})
    assert inp_720.resolution == "720p"
    # 1080p
    inp_1080 = VideoGenerationInput.model_validate({"prompt": "x", "ratio": "16:9", "resolution": "1080p"})
    assert inp_1080.resolution == "1080p"
    # None（兼容存量/未计费）
    inp_none = VideoGenerationInput.model_validate({"prompt": "x", "ratio": "16:9"})
    assert inp_none.resolution is None
    # 非法值拒绝（Literal 校验）
    import pytest as _pytest

    with _pytest.raises(Exception):
        VideoGenerationInput.model_validate({"prompt": "x", "ratio": "16:9", "resolution": "4k"})


@pytest.mark.asyncio
async def test_build_run_args_passes_resolution_into_input_dict(monkeypatch) -> None:
    """build_run_args 将 resolution 透传到 input_dict；VideoGenerationInput 能校验通过。"""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.contracts.video_generation import VideoGenerationInput
    from app.core.db import Base
    from app.models.llm import Model, ModelCategoryKey, ModelSettings, Provider
    from app.models.studio import (
        CameraAngle,
        CameraMovement,
        CameraShotType,
        Chapter,
        Project,
        ProjectStyle,
        ProjectVisualStyle,
        Shot,
        ShotDetail,
        VFXType,
    )
    from app.services.film.generated_video import build_run_args

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        async with session_local() as db:
            db.add(User(id="tu", username="tu", hashed_password="x", is_active=True, token_version=0))
            db.add(Project(id="proj-1", name="p", style=ProjectStyle.real_people_city, visual_style=ProjectVisualStyle.live_action, user_id="tu"))
            db.add(Chapter(id="ch-1", project_id="proj-1", index=1, title="ch"))
            db.add(Shot(id="sh-1", chapter_id="ch-1", index=1, title="sh", script_excerpt="..."))
            db.add(ShotDetail(
                id="sh-1",
                camera_shot=CameraShotType.ms,
                angle=CameraAngle.eye_level,
                movement=CameraMovement.static,
                duration=5,
                description="x",
                vfx_type=VFXType.none,
            ))
            db.add(Provider(id="pv1", user_id="tu", name="openai", base_url="http://x", api_key="k"))
            db.add(Model(id="mv1", user_id="tu", name="sora-mini", category=ModelCategoryKey.video, provider_id="pv1", unit_points=10))
            db.add(ModelSettings(id=1, default_video_model_id="mv1", user_id="tu"))
            await db.commit()

            run_args = await build_run_args(
                db,
                user_id="tu",
                shot_id="sh-1",
                reference_mode="text_only",
                prompt="提示词",
                images=[],
                ratio="16:9",
                resolution="1080p",
            )
            # resolution 落进 input_dict
            assert run_args["input"]["resolution"] == "1080p"
            assert run_args["input"]["seconds"] == 5
            # VideoGenerationInput 能校验通过（含 resolution 字段）
            inp = VideoGenerationInput.model_validate(run_args["input"])
            assert inp.resolution == "1080p"
            assert inp.seconds == 5
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_video_freeze_720p_vs_1080p_factor_differs() -> None:
    """720p(factor 1.0) 与 1080p(factor 2.0) 冻结金额不同；同 duration 下 1080p = 2 × 720p。

    计价基准：m1 unit_points=10，5s。720p → 10*5*1.0=50；1080p → 10*5*2.0=100。
    """
    from app.services.points.ledger import get_points, recharge

    # ---- 720p ----
    db1, engine1 = await _build_async_db()
    try:
        await recharge(db1, user_id=USER_ID, amount=200, created_by="t", remark="seed")
        token_720 = _make_quote_token(required_points=50, duration_seconds=5, resolution="720p")
        frozen_720 = await freeze_for_task(
            db1,
            user_id=USER_ID,
            quote_token=token_720,
            business_type="video_generation",
            category=ModelCategoryKey.video,
            model_id="m1",
            duration_seconds=5,
            resolution="720p",
        )
        assert frozen_720.required_points == 50
        pts_720 = await get_points(db1, user_id=USER_ID)
        assert pts_720.frozen == 50
    finally:
        await db1.close()
        await engine1.dispose()

    # ---- 1080p ----
    db2, engine2 = await _build_async_db()
    try:
        await recharge(db2, user_id=USER_ID, amount=200, created_by="t", remark="seed")
        token_1080 = _make_quote_token(required_points=100, duration_seconds=5, resolution="1080p")
        frozen_1080 = await freeze_for_task(
            db2,
            user_id=USER_ID,
            quote_token=token_1080,
            business_type="video_generation",
            category=ModelCategoryKey.video,
            model_id="m1",
            duration_seconds=5,
            resolution="1080p",
        )
        assert frozen_1080.required_points == 100
        assert frozen_1080.required_points == 2 * frozen_720.required_points
    finally:
        await db2.close()
        await engine2.dispose()


@pytest.mark.asyncio
async def test_video_freeze_resolution_mismatch_raises_quote_changed() -> None:
    """quote_token 绑定 720p，但请求传 1080p → POINTS_QUOTE_CHANGED（防篡改）。"""
    db, engine = await _build_async_db()
    try:
        # token 绑定 720p（required=50），调用方传 1080p（重算=100，价格变更）
        token = _make_quote_token(required_points=50, duration_seconds=5, resolution="720p")
        with pytest.raises(PointsDomainError) as exc_info:
            await freeze_for_task(
                db,
                user_id=USER_ID,
                quote_token=token,
                business_type="video_generation",
                category=ModelCategoryKey.video,
                model_id="m1",
                duration_seconds=5,
                resolution="1080p",
            )
        assert exc_info.value.code == "POINTS_QUOTE_CHANGED"
    finally:
        await db.close()
        await engine.dispose()


def test_openai_video_payload_resolution_drives_size() -> None:
    """OpenAI 适配器：resolution 决定 body["size"]（720p→1280x720，1080p→1920x1080）。"""
    from app.core.contracts.video_generation import VideoGenerationInput
    from app.core.integrations.openai.video_payload import build_create_video_body

    # 1080p
    inp_1080 = VideoGenerationInput.model_validate(
        {"prompt": "a cat", "ratio": "16:9", "resolution": "1080p"}
    )
    body_1080 = build_create_video_body(inp_1080)
    assert body_1080["size"] == "1920x1080"
    # 720p
    inp_720 = VideoGenerationInput.model_validate(
        {"prompt": "a cat", "ratio": "16:9", "resolution": "720p"}
    )
    body_720 = build_create_video_body(inp_720)
    assert body_720["size"] == "1280x720"
    # 未指定 → 回退到 ratio mapping（16:9 → 1280x720）
    inp_none = VideoGenerationInput.model_validate({"prompt": "a cat", "ratio": "16:9"})
    body_none = build_create_video_body(inp_none)
    assert body_none["size"] == "1280x720"


def test_bailian_video_payload_rejects_1080p_before_vendor_call() -> None:
    """百炼不支持 1080p：resolution=1080p → _build_payload 在调用前抛 ValueError。

    保证不变式「不能按 1080p 收费却生成 720p」——百炼只支持 480P/720P，必须拒绝。
    """
    from app.core.contracts.video_generation import VideoGenerationInput
    from app.core.integrations.bailian.video import BailianVideoApiAdapter
    from app.core.contracts.provider import ProviderConfig

    adapter = BailianVideoApiAdapter(
        provider_config=ProviderConfig(provider="aliyun_bailian", api_key="k"),
    )
    inp = VideoGenerationInput.model_validate(
        {"model": "happyhorse-1.0-t2v", "prompt": "x", "ratio": "16:9", "resolution": "1080p"}
    )
    with pytest.raises(ValueError, match="1080p"):
        adapter._build_payload(inp)

    # 720p 通过，parameters.resolution = "720P"
    inp_720 = VideoGenerationInput.model_validate(
        {"model": "happyhorse-1.0-t2v", "prompt": "x", "ratio": "16:9", "resolution": "720p"}
    )
    payload = adapter._build_payload(inp_720)
    assert payload["parameters"]["resolution"] == "720P"


def test_vidu_video_payload_resolution_is_passed_through() -> None:
    """Vidu 适配器：业务层 resolution 透传到 body["resolution"]（720p/1080p）。"""
    from app.core.contracts.video_generation import VideoGenerationInput
    from app.core.contracts.provider import ProviderConfig
    from app.core.integrations.vidu.video import ViduVideoApiAdapter

    adapter = ViduVideoApiAdapter()
    inp_720 = VideoGenerationInput.model_validate(
        {
            "model": "viduq3",
            "prompt": "@subject_1 抱团",
            "ratio": "3:4",
            "seconds": 5,
            "resolution": "720p",
            "first_frame_base64": "https://cdn.example.com/a.png",
        }
    )
    body_720 = adapter._build_request_body(inp_720)
    assert body_720["resolution"] == "720p"

    inp_1080 = VideoGenerationInput.model_validate(
        {
            "model": "viduq3",
            "prompt": "@subject_1 抱团",
            "ratio": "3:4",
            "seconds": 5,
            "resolution": "1080p",
            "first_frame_base64": "https://cdn.example.com/a.png",
        }
    )
    body_1080 = adapter._build_request_body(inp_1080)
    assert body_1080["resolution"] == "1080p"


def test_video_route_freezes_before_task_create(monkeypatch) -> None:
    """路由层：freeze_for_task 在 tm.create 之前；billing_id 落到任务行。

    策略：构造带 video model + shot 的库，monkeypatch build_run_args 避免外部依赖，
    关闭 enqueue，用 TestClient 调 POST /tasks/video，断言冻结积分 + 任务行 billing_id 非空。
    """
    import asyncio

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1.routes.film import generated_video as video_route
    from app.dependencies import get_current_user, get_db
    from app.services.points.ledger import get_points, recharge

    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.task  # noqa: F401
    import app.models.points  # noqa: F401
    import app.models.task_links  # noqa: F401

    async def _seed():
        from app.models.studio import (
            Chapter,
            Project,
            ProjectStyle,
            ProjectVisualStyle,
            Shot,
        )

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session_local() as db:
            db.add(User(id=USER_ID, username="u1", hashed_password="x", is_active=True, token_version=0))
            db.add(Provider(id="p1", user_id=USER_ID, name="openai", base_url="http://x", api_key="k"))
            db.add(Model(id="m1", user_id=USER_ID, name="sora-mini", category=ModelCategoryKey.video, provider_id="p1", unit_points=10))
            # Shot 图：mark_shot_generating → recompute_shot_status 需要 Shot 行
            db.add(Project(id="proj-1", name="p", style=ProjectStyle.real_people_city, visual_style=ProjectVisualStyle.live_action, user_id=USER_ID))
            db.add(Chapter(id="ch-1", project_id="proj-1", index=1, title="ch"))
            db.add(Shot(id="sh-1", chapter_id="ch-1", index=1, title="sh", script_excerpt="x"))
            await db.commit()
            await recharge(db, user_id=USER_ID, amount=200, created_by="t", remark="seed")

    asyncio.run(_seed())

    # monkeypatch build_run_args：避免文件解析等外部依赖，直接返回包含 seconds 的 run_args
    async def _fake_build_run_args(_db, **kwargs):
        return {
            "shot_id": kwargs["shot_id"],
            "provider": "openai",
            "api_key": "k",
            "base_url": None,
            "input": {
                "prompt": "p",
                "first_frame_base64": None,
                "last_frame_base64": None,
                "key_frame_base64": None,
                "model": "sora-mini",
                "ratio": kwargs.get("ratio", "16:9"),
                "seconds": 5,
                "resolution": kwargs.get("resolution", "1080p"),
            },
        }

    # 替换 video_route 模块内导入的 build_run_args（路由内 `from ... import build_run_args`）
    monkeypatch.setattr(video_route, "build_run_args", _fake_build_run_args)
    # 关闭 enqueue
    monkeypatch.setattr(video_route, "enqueue_task_execution", lambda _tid: None)

    async def _override_db():
        async with async_session_local() as db:
            yield db

    class _FakeUser:
        id = USER_ID

    async def _override_user():
        return _FakeUser()

    app_obj = FastAPI()
    app_obj.include_router(video_route.router, prefix="/api/v1/film")
    app_obj.dependency_overrides[get_db] = _override_db
    app_obj.dependency_overrides[get_current_user] = _override_user

    token = _make_quote_token(required_points=100, duration_seconds=5, resolution="1080p")
    client = TestClient(app_obj)
    resp = client.post(
        "/api/v1/film/tasks/video",
        json={
            "shot_id": "sh-1",
            "reference_mode": "text_only",
            "prompt": "x",
            "images": [],
            "ratio": "16:9",
            "resolution": "1080p",
            "quote_token": token,
        },
    )
    assert resp.status_code == 201, resp.text
    task_id = resp.json()["data"]["task_id"]

    async def _check():
        from app.models.task import GenerationTask

        async with async_session_local() as db:
            pts = await get_points(db, user_id=USER_ID)
            # 1080p*5s：10*5*2.0=100 → frozen=100，balance=200
            assert pts.balance == 200
            assert pts.frozen == 100
            row = await db.get(GenerationTask, task_id)
            assert row is not None
            assert row.billing_id  # 非空

    asyncio.run(_check())
    asyncio.run(async_engine.dispose())


def test_video_route_insufficient_points_no_task(monkeypatch) -> None:
    """路由层：余额不足 → PointsDomainError 上抛，任务不被创建。"""
    import asyncio

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1.routes.film import generated_video as video_route
    from app.dependencies import get_current_user, get_db

    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.task  # noqa: F401
    import app.models.points  # noqa: F401
    import app.models.task_links  # noqa: F401

    async def _seed():
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session_local() as db:
            db.add(User(id=USER_ID, username="u1", hashed_password="x", is_active=True, token_version=0))
            db.add(Provider(id="p1", user_id=USER_ID, name="openai", base_url="http://x", api_key="k"))
            db.add(Model(id="m1", user_id=USER_ID, name="sora-mini", category=ModelCategoryKey.video, provider_id="p1", unit_points=10))
            await db.commit()
            # 未充值 → 可用 0

    asyncio.run(_seed())

    async def _fake_build_run_args(_db, **kwargs):
        return {
            "shot_id": kwargs["shot_id"],
            "provider": "openai",
            "api_key": "k",
            "base_url": None,
            "input": {"prompt": "p", "first_frame_base64": None, "last_frame_base64": None, "key_frame_base64": None, "model": "sora-mini", "ratio": "16:9", "seconds": 5, "resolution": "1080p"},
        }

    monkeypatch.setattr(video_route, "build_run_args", _fake_build_run_args)
    monkeypatch.setattr(video_route, "enqueue_task_execution", lambda _tid: None)

    async def _override_db():
        async with async_session_local() as db:
            yield db

    class _FakeUser:
        id = USER_ID

    async def _override_user():
        return _FakeUser()

    app_obj = FastAPI()
    app_obj.include_router(video_route.router, prefix="/api/v1/film")
    app_obj.dependency_overrides[get_db] = _override_db
    app_obj.dependency_overrides[get_current_user] = _override_user
    # 注册 PointsDomainError 处理器（与 main.py 一致），使 TestClient 拿到结构化响应而非抛出
    from app.services.points.billing import PointsDomainError, build_insufficient_error

    def _handler(_request, exc: PointsDomainError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=exc.status_code, content={"data": exc.data, "error_code": exc.code})

    app_obj.add_exception_handler(PointsDomainError, _handler)

    token = _make_quote_token(required_points=100, duration_seconds=5, resolution="1080p")
    client = TestClient(app_obj)
    resp = client.post(
        "/api/v1/film/tasks/video",
        json={
            "shot_id": "sh-1",
            "reference_mode": "text_only",
            "prompt": "x",
            "images": [],
            "ratio": "16:9",
            "resolution": "1080p",
            "quote_token": token,
        },
    )
    # PointsDomainError(INSUFFICIENT_POINTS) → 402
    assert resp.status_code == 402

    async def _check():
        from app.models.task import GenerationTask
        from sqlalchemy import select

        async with async_session_local() as db:
            rows = (await db.execute(select(GenerationTask))).scalars().all()
            assert rows == []

    asyncio.run(_check())
    asyncio.run(async_engine.dispose())


def test_video_task_terminal_settlement_succeeded_consumes() -> None:
    """视频任务 succeeded → run_task_celery finally 的 settle_task_billing_sync 消费冻结积分。

    直接构造带 billing_id 的 succeeded 任务行 + 冻结积分，调用 settle_task_billing_sync，
    断言 balance 扣减、frozen 归零。证明视频任务的结算路径由 5a finally 钩子覆盖。

    注意：settle_task_billing_sync 内部用 asyncio.run，必须在同步上下文调用（与 Celery worker
    一致）；故本测试不在 asyncio 事件循环中运行，用 asyncio.run 驱动 seed/check。
    """
    import asyncio

    import app.services.points.billing as billing_mod

    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.task  # noqa: F401
    import app.models.points  # noqa: F401

    async def _seed():
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session_local() as db:
            from app.services.points.ledger import freeze_points, recharge

            db.add(User(id=USER_ID, username="u1", hashed_password="x", is_active=True, token_version=0))
            await db.commit()
            await recharge(db, user_id=USER_ID, amount=200, created_by="t", remark="seed")
            billing_id = uuid4().hex
            await freeze_points(
                db,
                user_id=USER_ID,
                billing_id=billing_id,
                amount=100,
                model_id="m1",
                business_type="video_generation",
                business_id=None,
                snapshot={"required_points": 100, "resolution": "1080p"},
            )
            return billing_id

    billing_id = asyncio.run(_seed())
    task_id = "video-" + uuid4().hex[:8]
    asyncio.run(
        _seed_task_row_async(
            async_session_local,
            task_id=task_id,
            billing_id=billing_id,
            status=GenerationTaskStatus.succeeded,
        )
    )
    original = billing_mod.async_session_maker
    billing_mod.async_session_maker = async_session_local
    try:
        settle_task_billing_sync(task_id)
    finally:
        billing_mod.async_session_maker = original

    async def _check():
        from app.services.points.ledger import get_points

        async with async_session_local() as db:
            after = await get_points(db, user_id=USER_ID)
            # 成功 → 消费 100：balance=100, frozen=0
            assert after.balance == 100
            assert after.frozen == 0

    asyncio.run(_check())
    asyncio.run(async_engine.dispose())


def test_video_task_terminal_settlement_failed_unfreezes() -> None:
    """视频任务 failed → run_task_celery finally 的 settle_task_billing_sync 解冻。

    注意：settle_task_billing_sync 内部用 asyncio.run，必须在同步上下文调用（与 Celery worker
    一致）；故本测试不在 asyncio 事件循环中运行，用 asyncio.run 驱动 seed/check。
    """
    import asyncio

    import app.services.points.billing as billing_mod

    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.task  # noqa: F401
    import app.models.points  # noqa: F401

    async def _seed():
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session_local() as db:
            from app.services.points.ledger import freeze_points, recharge

            db.add(User(id=USER_ID, username="u1", hashed_password="x", is_active=True, token_version=0))
            await db.commit()
            await recharge(db, user_id=USER_ID, amount=200, created_by="t", remark="seed")
            billing_id = uuid4().hex
            await freeze_points(
                db,
                user_id=USER_ID,
                billing_id=billing_id,
                amount=100,
                model_id="m1",
                business_type="video_generation",
                business_id=None,
                snapshot={"required_points": 100, "resolution": "1080p"},
            )
            return billing_id

    billing_id = asyncio.run(_seed())
    task_id = "video-fail-" + uuid4().hex[:8]
    asyncio.run(
        _seed_task_row_async(
            async_session_local,
            task_id=task_id,
            billing_id=billing_id,
            status=GenerationTaskStatus.failed,
        )
    )
    original = billing_mod.async_session_maker
    billing_mod.async_session_maker = async_session_local
    try:
        settle_task_billing_sync(task_id)
    finally:
        billing_mod.async_session_maker = original

    async def _check():
        from app.services.points.ledger import get_points

        async with async_session_local() as db:
            after = await get_points(db, user_id=USER_ID)
            # 失败 → 解冻：balance=200 不扣，frozen=0
            assert after.balance == 200
            assert after.frozen == 0

    asyncio.run(_check())
    asyncio.run(async_engine.dispose())


# ---------------------------------------------------------------------------
# shot_frame_prompt 路由计费：冻结 + billing_id + 余额不足/报价变更拦截
# （镜像 Task 5c 视频路由测试，类别换成 text、business_type=shot_frame_prompt）
# ---------------------------------------------------------------------------


def _make_shot_frame_prompt_quote_token(*, required_points: int = 7, model_id: str = "m_text") -> str:
    """构造合法的 shot_frame_prompt（文本类）quote_token，generation_count=1。"""
    params_hash = hash_quote_params(
        {
            "category": str(ModelCategoryKey.text),
            "duration_seconds": None,
            "resolution": None,
            "generation_count": 1,
        }
    )
    return create_quote_token(
        QuoteClaims(
            user_id=USER_ID,
            business_type="shot_frame_prompt",
            model_id=model_id,
            params_hash=params_hash,
            required_points=required_points,
        )
    )


def _seed_shot_frame_prompt_db(async_engine, async_session_local) -> None:
    """建表并预置 user/provider/文本模型 + 一个 Shot（供 mark_shot_generating 写状态用）。"""
    import asyncio

    from app.models.studio import Chapter, Project, ProjectStyle, ProjectVisualStyle, Shot

    async def _seed():
        import app.models.task  # noqa: F401
        import app.models.points  # noqa: F401
        import app.models.task_links  # noqa: F401

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session_local() as db:
            db.add(User(id=USER_ID, username="u1", hashed_password="x", is_active=True, token_version=0))
            db.add(Provider(id="p1", user_id=USER_ID, name="openai", base_url="http://x", api_key="k"))
            db.add(
                Model(
                    id="m_text",
                    user_id=USER_ID,
                    name="text-model",
                    category=ModelCategoryKey.text,
                    provider_id="p1",
                    unit_points=7,
                )
            )
            # mark_shot_generating → recompute_shot_status 需要 Shot 行
            db.add(
                Project(
                    id="proj-1",
                    name="p",
                    style=ProjectStyle.real_people_city,
                    visual_style=ProjectVisualStyle.live_action,
                    user_id=USER_ID,
                )
            )
            db.add(Chapter(id="ch-1", project_id="proj-1", index=1, title="ch"))
            db.add(Shot(id="sh-1", chapter_id="ch-1", index=1, title="sh", script_excerpt="x"))
            await db.commit()
            from app.services.points.ledger import recharge

            await recharge(db, user_id=USER_ID, amount=200, created_by="t", remark="seed")

    asyncio.run(_seed())


def _build_test_app(monkeypatch, async_session_local):
    """构造挂载 shot-frame-prompt 路由的 FastAPI app，并注入依赖覆盖 + PointsDomainError 处理器。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1.routes.film import tasks_images as sfp_route
    from app.dependencies import get_current_user, get_db
    from app.services.points.billing import PointsDomainError

    # build_shot_frame_prompt_run_args 内部做了大量 Shot 预加载与文件解析，测试里用桩绕开
    async def _fake_build_run_args(_db, **kwargs):
        return {
            "shot_id": kwargs["shot_id"],
            "frame_type": kwargs["frame_type"],
        }

    monkeypatch.setattr(sfp_route, "build_shot_frame_prompt_run_args", _fake_build_run_args)
    monkeypatch.setattr(sfp_route, "enqueue_task_execution", lambda _tid: None)

    async def _override_db():
        async with async_session_local() as db:
            yield db

    class _FakeUser:
        id = USER_ID

    async def _override_user():
        return _FakeUser()

    app_obj = FastAPI()
    app_obj.include_router(sfp_route.router, prefix="/api/v1/film")
    app_obj.dependency_overrides[get_db] = _override_db
    app_obj.dependency_overrides[get_current_user] = _override_user

    def _handler(_request, exc: PointsDomainError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=exc.status_code, content={"data": exc.data, "error_code": exc.code})

    app_obj.add_exception_handler(PointsDomainError, _handler)
    return app_obj


def test_shot_frame_prompt_route_freezes_before_task_create(monkeypatch) -> None:
    """路由层：POST /tasks/shot-frame-prompts 在创建任务前冻结积分，billing_id 落到任务行。"""
    import asyncio

    from fastapi.testclient import TestClient

    from app.services.points.ledger import get_points

    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    _seed_shot_frame_prompt_db(async_engine, async_session_local)

    app_obj = _build_test_app(monkeypatch, async_session_local)
    token = _make_shot_frame_prompt_quote_token(required_points=7)
    client = TestClient(app_obj)
    resp = client.post(
        "/api/v1/film/tasks/shot-frame-prompts",
        json={"shot_id": "sh-1", "frame_type": "key", "quote_token": token},
    )
    assert resp.status_code == 201, resp.text
    task_id = resp.json()["data"]["task_id"]

    async def _check():
        from app.models.task import GenerationTask

        async with async_session_local() as db:
            pts = await get_points(db, user_id=USER_ID)
            # 文本单价 7、generation_count=1 → 冻结 7，余额 200-... 仅校验 frozen
            assert pts.frozen == 7
            row = await db.get(GenerationTask, task_id)
            assert row is not None
            assert row.billing_id  # 非空：run_task_celery finally 可据此结算

    asyncio.run(_check())
    asyncio.run(async_engine.dispose())


def test_shot_frame_prompt_route_insufficient_points_no_task(monkeypatch) -> None:
    """路由层：余额不足 → PointsDomainError(INSUFFICIENT_POINTS) 上抛为 402，任务不被创建。"""
    import asyncio

    from fastapi.testclient import TestClient

    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    # 种子但不充值 → 可用 0
    import app.models.task  # noqa: F401
    import app.models.points  # noqa: F401
    import app.models.task_links  # noqa: F401
    from app.models.studio import Chapter, Project, ProjectStyle, ProjectVisualStyle, Shot

    async def _seed():
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session_local() as db:
            db.add(User(id=USER_ID, username="u1", hashed_password="x", is_active=True, token_version=0))
            db.add(Provider(id="p1", user_id=USER_ID, name="openai", base_url="http://x", api_key="k"))
            db.add(
                Model(
                    id="m_text",
                    user_id=USER_ID,
                    name="text-model",
                    category=ModelCategoryKey.text,
                    provider_id="p1",
                    unit_points=7,
                )
            )
            db.add(
                Project(
                    id="proj-1",
                    name="p",
                    style=ProjectStyle.real_people_city,
                    visual_style=ProjectVisualStyle.live_action,
                    user_id=USER_ID,
                )
            )
            db.add(Chapter(id="ch-1", project_id="proj-1", index=1, title="ch"))
            db.add(Shot(id="sh-1", chapter_id="ch-1", index=1, title="sh", script_excerpt="x"))
            await db.commit()
            # 故意不 recharge

    asyncio.run(_seed())

    app_obj = _build_test_app(monkeypatch, async_session_local)
    token = _make_shot_frame_prompt_quote_token(required_points=7)
    client = TestClient(app_obj)
    resp = client.post(
        "/api/v1/film/tasks/shot-frame-prompts",
        json={"shot_id": "sh-1", "frame_type": "key", "quote_token": token},
    )
    assert resp.status_code == 402, resp.text
    assert resp.json()["error_code"] == "INSUFFICIENT_POINTS"

    async def _check():
        from app.models.task import GenerationTask
        from sqlalchemy import select

        async with async_session_local() as db:
            rows = (await db.execute(select(GenerationTask))).scalars().all()
            assert rows == []  # 任务未被创建

    asyncio.run(_check())
    asyncio.run(async_engine.dispose())


def test_shot_frame_prompt_route_quote_changed_no_task(monkeypatch) -> None:
    """路由层：报价与当前单价不一致 → PointsDomainError(POINTS_QUOTE_CHANGED) 上抛为 409。"""
    import asyncio

    from fastapi.testclient import TestClient

    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    _seed_shot_frame_prompt_db(async_engine, async_session_local)

    app_obj = _build_test_app(monkeypatch, async_session_local)
    # token 内 required_points=1 与重算（unit_points=7）不符 → POINTS_QUOTE_CHANGED
    token = _make_shot_frame_prompt_quote_token(required_points=1)
    client = TestClient(app_obj)
    resp = client.post(
        "/api/v1/film/tasks/shot-frame-prompts",
        json={"shot_id": "sh-1", "frame_type": "key", "quote_token": token},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error_code"] == "POINTS_QUOTE_CHANGED"

    async def _check():
        from app.models.task import GenerationTask
        from sqlalchemy import select

        async with async_session_local() as db:
            rows = (await db.execute(select(GenerationTask))).scalars().all()
            assert rows == []  # 任务未被创建

    asyncio.run(_check())
    asyncio.run(async_engine.dispose())
