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


def test_settle_succeeded_consumes_frozen(monkeypatch) -> None:
    """succeeded → consume：balance 与 frozen 同步减少。

    注意：本测试不在 asyncio 事件循环中运行（settle_task_billing_sync 内部用 asyncio.run
    启动循环，与 Celery worker 同步上下文一致），故不能用 @pytest.mark.asyncio。
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

    sync_session_local, sync_engine, task_id = _build_sync_db_with_task(
        billing_id=billing_id, status=GenerationTaskStatus.succeeded
    )
    monkeypatch.setattr("app.services.points.billing.sync_session_maker", sync_session_local)
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
    sync_engine.dispose()


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

    sync_session_local, sync_engine, task_id = _build_sync_db_with_task(
        billing_id=billing_id, status=GenerationTaskStatus.failed
    )
    monkeypatch.setattr("app.services.points.billing.sync_session_maker", sync_session_local)
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
    sync_engine.dispose()


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
    sync_session_local, sync_engine, task_id = _build_sync_db_with_task(
        billing_id=billing_id, status=GenerationTaskStatus.cancelled
    )
    monkeypatch.setattr("app.services.points.billing.sync_session_maker", sync_session_local)
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
    sync_engine.dispose()


def test_settle_non_terminal_is_noop(monkeypatch) -> None:
    """running（非终态）→ 不结算。"""
    import asyncio

    sync_session_local, sync_engine, task_id = _build_sync_db_with_task(
        billing_id="b-running", status=GenerationTaskStatus.running
    )
    # async_session_maker 不应被实际触达（终态判断会先返回），但为安全用空库
    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.services.points.billing.sync_session_maker", sync_session_local)
    monkeypatch.setattr("app.services.points.billing.async_session_maker", async_session_local)

    # 不应抛错，也不应有副作用
    settle_task_billing_sync(task_id)

    sync_engine.dispose()
    asyncio.run(async_engine.dispose())


def test_settle_billing_id_none_is_noop(monkeypatch) -> None:
    """billing_id=None → 直接跳过（存量任务零行为变更）。"""
    import asyncio

    sync_session_local, sync_engine, task_id = _build_sync_db_with_task(
        billing_id=None, status=GenerationTaskStatus.succeeded
    )
    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async_session_local = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.services.points.billing.sync_session_maker", sync_session_local)
    monkeypatch.setattr("app.services.points.billing.async_session_maker", async_session_local)

    settle_task_billing_sync(task_id)

    sync_engine.dispose()
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
    sync_session_local, sync_engine, task_id = _build_sync_db_with_task(
        billing_id=billing_id, status=GenerationTaskStatus.succeeded
    )
    monkeypatch.setattr("app.services.points.billing.sync_session_maker", sync_session_local)
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
    sync_engine.dispose()


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
    - 用真实的 sync SessionMaker(含一个 failed 状态的 GenerationTask + billing_id)替换
      billing 模块引用的 sync_session_maker,使 run_task_celery 能读到任务行;
    - 同时让 execute_task 模块引用同一个 SessionMaker(它内部也用 sync_session_maker 读任务);
    - monkeypatch task_executor_registry.resolve 返回一个 .run 会抛 RuntimeError 的假执行器
      (模拟 worker 执行失败);
    - 预先用 async 引擎冻结积分,调用 `run_task_celery.run(task_id)`(Celery 装饰器下未装饰
      的可调用对象,直接同步调用),断言:即便执行器抛异常,frozen 仍被解冻(balance 不变、
      frozen 归零),证明 finally 结算钩子确实触发。
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

    # 2. sync 侧:建一个 failed 终态的任务行(模拟 executor 失败后已回写状态)
    sync_session_local, sync_engine, task_id = _build_sync_db_with_task(
        billing_id=billing_id, status=GenerationTaskStatus.failed
    )
    monkeypatch.setattr("app.services.points.billing.sync_session_maker", sync_session_local)
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
