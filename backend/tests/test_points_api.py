"""Task 4: 积分试算/余额/流水/管理员充值 API 测试。

覆盖：
- GET /points/me 返回当前用户余额/冻结/可用额度。
- GET /points/transactions 按类型/业务类型过滤；非法 type → 422。
- POST /points/quote：model_id=null 解析为默认模型并返回 required_points/quote_token/sufficient；
  显式 model_id 归属当前用户 → ok；归属他人 → 403；视频缺 duration/resolution → 422。
- 管理员 POST recharge 正/负充值；负充值无备注 → 400；负充值透支 → 402；负充值侵蚀冻结 → 402（INSUFFICIENT_POINTS）。
- 非管理员调用管理员充值端点 → 403。
- PointsDomainError(POINTS_QUOTE_CHANGED) 经 main.py 处理器序列化保留 data.error_code。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.core.security import hash_password
from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.llm import Model, ModelCategoryKey, ModelSettings, Provider
from app.models.points import UserPoints
from app.models.user import User
from app.services.points import ledger as ledger_module


def _seed_provider_and_models(s: AsyncSession, user_id: str) -> tuple[Model, Model, Model]:
    """为一个用户预置 provider + text/image/video 三个模型，并写入 ModelSettings 默认值。

    返回 (text_model, image_model, video_model)。模型按用户隔离（user_id 指向归属用户）。
    """
    provider = Provider(
        id="prov-1",
        user_id=user_id,
        name="p",
        base_url="http://x",
        api_key="k",
    )
    s.add(provider)
    text_model = Model(
        id="m-text",
        user_id=user_id,
        name="text-model",
        category=ModelCategoryKey.text,
        provider_id="prov-1",
        unit_points=5,
    )
    image_model = Model(
        id="m-image",
        user_id=user_id,
        name="image-model",
        category=ModelCategoryKey.image,
        provider_id="prov-1",
        unit_points=10,
    )
    video_model = Model(
        id="m-video",
        user_id=user_id,
        name="video-model",
        category=ModelCategoryKey.video,
        provider_id="prov-1",
        unit_points=2,
    )
    s.add_all([text_model, image_model, video_model])
    s.add(
        ModelSettings(
            user_id=user_id,
            default_text_model_id="m-text",
            default_image_model_id="m-image",
            default_video_model_id="m-video",
        )
    )
    return text_model, image_model, video_model


@pytest.fixture
def points_client(monkeypatch) -> TestClient:
    """构建带初始数据的 TestClient：admin + 普通用户 + 模型/默认设置 + 初始积分。

    默认 get_current_user 返回普通用户 user-1。测试需要切换身份时覆盖该依赖即可。
    """
    # fakeredis：让 ledger 的 Redis 锁在测试中互斥可验。
    from fakeredis.aioredis import FakeRedis

    fake = FakeRedis()
    monkeypatch.setattr(ledger_module, "_redis_factory", lambda: fake)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sm() as s:
            s.add(
                User(
                    id="admin-1",
                    username="admin",
                    hashed_password=hash_password("pw"),
                    is_admin=True,
                )
            )
            s.add(
                User(
                    id="user-1",
                    username="bob",
                    hashed_password=hash_password("pw"),
                    is_admin=False,
                )
            )
            await s.flush()
            _seed_provider_and_models(s, "user-1")
            # 为 admin 预置一个属于 admin 的文本模型，用于跨用户归属测试。
            admin_provider = Provider(
                id="prov-admin",
                user_id="admin-1",
                name="admin-p",
                base_url="http://y",
                api_key="k2",
            )
            s.add(admin_provider)
            s.add(
                Model(
                    id="m-admin-text",
                    user_id="admin-1",
                    name="admin-text-model",
                    category=ModelCategoryKey.text,
                    provider_id="prov-admin",
                    unit_points=3,
                )
            )
            # 给普通用户预置 100 余额，0 冻结。
            s.add(UserPoints(user_id="user-1", balance=100, frozen=0))
            await s.commit()

    asyncio.run(_setup())

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        async with sm() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    async def _normal_user() -> User:
        return User(
            id="user-1",
            username="bob",
            hashed_password="x",
            is_admin=False,
            is_active=True,
        )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _normal_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


# ---------------------------------------------------------------------------
# GET /points/me
# ---------------------------------------------------------------------------


def test_get_points_me_returns_summary(points_client: TestClient) -> None:
    resp = points_client.get("/api/v1/points/me")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["balance"] == 100
    assert data["frozen"] == 0
    assert data["available"] == 100


# ---------------------------------------------------------------------------
# POST /points/quote
# ---------------------------------------------------------------------------


def test_quote_default_model_resolves_and_returns_token(points_client: TestClient) -> None:
    """model_id=null 时解析为默认模型并返回 required_points/quote_token/sufficient。"""
    resp = points_client.post(
        "/api/v1/points/quote",
        json={"business_type": "text_generation", "category": "text"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    # 默认文本模型单价 5
    assert data["resolved_model_id"] == "m-text"
    assert data["resolved_model_name"] == "text-model"
    assert data["using_default_model"] is True
    assert data["required_points"] == 5
    assert data["available_points"] == 100
    assert data["sufficient"] is True
    assert data["quote_token"]
    # 解码 quote_token，断言其 claims 与响应字段一致（防签名不一致）。
    from app.services.points import decode_quote_token

    claims = decode_quote_token(data["quote_token"], expected_user_id="user-1")
    assert claims.required_points == data["required_points"]
    assert claims.model_id == data["resolved_model_id"]
    assert claims.business_type == "text_generation"


def test_quote_image_model_required_points(points_client: TestClient) -> None:
    resp = points_client.post(
        "/api/v1/points/quote",
        json={"business_type": "image_generation", "category": "image"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["resolved_model_id"] == "m-image"
    assert data["required_points"] == 10


def test_quote_video_with_duration_resolution(points_client: TestClient) -> None:
    resp = points_client.post(
        "/api/v1/points/quote",
        json={
            "business_type": "video_generation",
            "category": "video",
            "duration_seconds": 5,
            "resolution": "1080p",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    # 2 单价 * 5 秒 * 2.0(1080p) = 20
    assert data["required_points"] == 20


def test_quote_video_missing_resolution_returns_422(points_client: TestClient) -> None:
    """视频类别缺 resolution → schema 层 422（不应进入计价逻辑导致 500）。"""
    resp = points_client.post(
        "/api/v1/points/quote",
        json={
            "business_type": "video_generation",
            "category": "video",
            "duration_seconds": 5,
        },
    )
    assert resp.status_code == 422


def test_quote_video_missing_duration_returns_422(points_client: TestClient) -> None:
    """视频类别缺 duration_seconds → schema 层 422。"""
    resp = points_client.post(
        "/api/v1/points/quote",
        json={
            "business_type": "video_generation",
            "category": "video",
            "resolution": "720p",
        },
    )
    assert resp.status_code == 422


def test_quote_unsupported_resolution_returns_400(points_client: TestClient) -> None:
    # schema Literal["720p","1080p"] 在校验阶段拦截未知分辨率（422），避免进入计价逻辑。
    resp = points_client.post(
        "/api/v1/points/quote",
        json={
            "business_type": "video_generation",
            "category": "video",
            "duration_seconds": 5,
            "resolution": "4k",
        },
    )
    assert resp.status_code == 422


def test_quote_explicit_model_owned_by_user_ok(points_client: TestClient) -> None:
    resp = points_client.post(
        "/api/v1/points/quote",
        json={
            "business_type": "text_generation",
            "category": "text",
            "model_id": "m-text",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["resolved_model_id"] == "m-text"
    assert data["using_default_model"] is False
    # 解码 quote_token，断言其 claims 与响应字段一致（防签名不一致）。
    from app.services.points import decode_quote_token

    claims = decode_quote_token(data["quote_token"], expected_user_id="user-1")
    assert claims.required_points == data["required_points"]
    assert claims.model_id == data["resolved_model_id"]
    assert claims.business_type == "text_generation"


def test_quote_explicit_model_owned_by_other_user_forbidden(points_client: TestClient) -> None:
    """显式 model_id 归属另一用户时拒绝（403），避免借用他人模型计价。

    fixture 已为 admin-1 预置模型 m-admin-text（user_id=admin-1）。普通用户 user-1 引用
    该 model_id 时，quote_points 的归属校验应抛 PointsDomainError(MODEL_NOT_OWNED, 403)。
    """
    resp = points_client.post(
        "/api/v1/points/quote",
        json={
            "business_type": "text_generation",
            "category": "text",
            "model_id": "m-admin-text",
        },
    )
    assert resp.status_code == 403
    data = resp.json()["data"]
    assert data["error_code"] == "MODEL_NOT_OWNED"


# ---------------------------------------------------------------------------
# GET /points/transactions
# ---------------------------------------------------------------------------


def test_list_transactions_filter_by_type(points_client: TestClient) -> None:
    # 先用 admin 充值产生流水
    async def _admin_user() -> User:
        return User(
            id="admin-1",
            username="admin",
            hashed_password="x",
            is_admin=True,
            is_active=True,
        )

    app.dependency_overrides[get_current_user] = _admin_user
    points_client.post("/api/v1/admin/users/user-1/points/recharge", json={"amount": 50})
    # 切回普通用户查看流水
    async def _normal_user() -> User:
        return User(
            id="user-1",
            username="bob",
            hashed_password="x",
            is_admin=False,
            is_active=True,
        )

    app.dependency_overrides[get_current_user] = _normal_user
    resp = points_client.get("/api/v1/points/transactions", params={"type": "recharge"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["pagination"]["total"] >= 1
    assert all(item["type"] == "recharge" for item in data["items"])


def test_list_transactions_invalid_type_returns_422(points_client: TestClient) -> None:
    """非法 type 值 → 422，不再静默退化成空结果。"""
    resp = points_client.get(
        "/api/v1/points/transactions", params={"type": "not_a_real_type"}
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 管理员充值
# ---------------------------------------------------------------------------


def test_admin_recharge_positive_increases_balance(points_client: TestClient) -> None:
    async def _admin_user() -> User:
        return User(
            id="admin-1",
            username="admin",
            hashed_password="x",
            is_admin=True,
            is_active=True,
        )

    app.dependency_overrides[get_current_user] = _admin_user
    resp = points_client.post(
        "/api/v1/admin/users/user-1/points/recharge", json={"amount": 100, "remark": "topup"}
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["amount"] == 100
    # 余额 100 + 100 = 200
    assert body["balance_after"] == 200

    summary = points_client.get("/api/v1/admin/users/user-1/points").json()["data"]
    assert summary["balance"] == 200


def test_admin_recharge_negative_with_remark_decreases_balance(points_client: TestClient) -> None:
    async def _admin_user() -> User:
        return User(
            id="admin-1",
            username="admin",
            hashed_password="x",
            is_admin=True,
            is_active=True,
        )

    app.dependency_overrides[get_current_user] = _admin_user
    resp = points_client.post(
        "/api/v1/admin/users/user-1/points/recharge", json={"amount": -50, "remark": "deduct"}
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["amount"] == -50
    assert body["balance_after"] == 50  # 100 - 50


def test_admin_recharge_negative_without_remark_returns_400(points_client: TestClient) -> None:
    async def _admin_user() -> User:
        return User(
            id="admin-1",
            username="admin",
            hashed_password="x",
            is_admin=True,
            is_active=True,
        )

    app.dependency_overrides[get_current_user] = _admin_user
    resp = points_client.post(
        "/api/v1/admin/users/user-1/points/recharge", json={"amount": -10}
    )
    assert resp.status_code == 400


def test_admin_recharge_overdraft_returns_402(points_client: TestClient) -> None:
    """负充值金额远超余额（透支）→ 402 INSUFFICIENT_POINTS，data 带 available/required/shortfall。

    原名 eroding_frozen 不准确：负充值 -100000 远大于 balance=100，
    实际触发的是透支守卫（new_balance < 0），frozen 始终为 0，与冻结侵蚀无关。
    冻结侵蚀场景见 `test_admin_recharge_negative_eroding_frozen_returns_402`。
    """
    async def _admin_user() -> User:
        return User(
            id="admin-1",
            username="admin",
            hashed_password="x",
            is_admin=True,
            is_active=True,
        )

    app.dependency_overrides[get_current_user] = _admin_user
    resp = points_client.post(
        "/api/v1/admin/users/user-1/points/recharge",
        json={"amount": -100000, "remark": "over-deduct"},
    )
    assert resp.status_code == 402
    data = resp.json()["data"]
    assert data["error_code"] == "INSUFFICIENT_POINTS"
    assert "available" in data
    assert "required" in data
    assert "shortfall" in data


def test_admin_recharge_negative_eroding_frozen_returns_402(points_client: TestClient) -> None:
    """负充值侵蚀冻结额 → 402 INSUFFICIENT_POINTS。

    场景：账户 balance=100, frozen=60（available=40）。负充值 -50 使 new_balance=50，
    而 50 < frozen=60，ledger 的冻结保护守卫 `amount < 0 and new_balance < pts.frozen`
    必须拒绝，否则冻结额将失去足额覆盖。直接通过 DB 种入 balance=100/frozen=60
    的 UserPoints 行（CHECK 约束只要求 frozen<=balance，此 seed 合法）。
    """
    # 直接写一个 frozen=60 的初始账户状态（覆盖 fixture 默认 balance=100/frozen=0）。
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.db import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sm() as s:
            s.add(
                User(
                    id="admin-1",
                    username="admin",
                    hashed_password=hash_password("pw"),
                    is_admin=True,
                )
            )
            s.add(
                User(
                    id="user-1",
                    username="bob",
                    hashed_password=hash_password("pw"),
                    is_admin=False,
                )
            )
            # 种入 balance=100, frozen=60 的账户（frozen<=balance 满足 CHECK）。
            s.add(UserPoints(user_id="user-1", balance=100, frozen=60))
            await s.commit()

    asyncio.run(_setup())

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        async with sm() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    async def _admin_user() -> User:
        return User(
            id="admin-1",
            username="admin",
            hashed_password="x",
            is_admin=True,
            is_active=True,
        )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _admin_user
    try:
        resp = points_client.post(
            "/api/v1/admin/users/user-1/points/recharge",
            json={"amount": -50, "remark": "erode-frozen"},
        )
        assert resp.status_code == 402
        data = resp.json()["data"]
        assert data["error_code"] == "INSUFFICIENT_POINTS"
        # available = balance - frozen = 100 - 60 = 40
        assert data["available"] == 40
        # required = -amount = 50
        assert data["required"] == 50
        # shortfall = frozen - new_balance = 60 - 50 = 10
        assert data["shortfall"] == 10
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_non_admin_recharge_returns_403(points_client: TestClient) -> None:
    """非管理员调用管理员充值端点 → 403（require_admin 拒绝）。"""
    async def _normal_user() -> User:
        return User(
            id="user-1",
            username="bob",
            hashed_password="x",
            is_admin=False,
            is_active=True,
        )

    app.dependency_overrides[get_current_user] = _normal_user
    resp = points_client.post(
        "/api/v1/admin/users/user-1/points/recharge", json={"amount": 10}
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PointsDomainError 结构化错误：POINTS_QUOTE_CHANGED 序列化
# ---------------------------------------------------------------------------


def test_points_domain_error_handler_preserves_error_code(points_client: TestClient) -> None:
    """构造 PointsDomainError(POINTS_QUOTE_CHANGED) 触发处理器，断言 data.error_code 保留。"""
    from app.services.points.billing import PointsDomainError, build_quote_changed_error

    # 直接断言错误对象携带的字段；处理器逻辑在 main.py，这里单独验处理器序列化。
    from app.main import points_domain_error_handler

    class _FakeRequest:
        pass

    err = build_quote_changed_error(
        new_quote={
            "resolved_model_id": "m-text",
            "resolved_model_name": "text-model",
            "using_default_model": True,
            "required_points": 7,
            "available_points": 100,
            "sufficient": True,
            "quote_token": "tok",
        }
    )
    import asyncio

    response = asyncio.run(points_domain_error_handler(_FakeRequest(), err))
    assert response.status_code == 409
    import json

    body = json.loads(response.body)
    assert body["code"] == 409
    assert body["data"]["error_code"] == "POINTS_QUOTE_CHANGED"
    assert body["data"]["required_points"] == 7
    assert body["data"]["quote_token"] == "tok"


# ---------------------------------------------------------------------------
# GET /points/transactions/grouped 搜索
# ---------------------------------------------------------------------------

import uuid as _uuid
from datetime import datetime, timezone as _tz
from app.models.points import PointTransaction as _PTx, PointTransactionType as _PTxType


def _seed_cascade_group(sm, user_id: str) -> tuple[str, str, str, str]:
    """向 DB 插入一次完整的 cascade 生命周期（freeze → consume），返回
    (cascade_group_id, billing_id, tx_freeze_id, tx_consume_id)。
    """
    import asyncio as _asyncio
    cgid = "cgid-search-test"
    bid  = "bid-search-test"
    fid  = "txid-freeze-1"
    cid  = "txid-consume-1"

    async def _insert():
        async with sm() as s:
            now = datetime.now(_tz.utc)
            s.add(_PTx(id=fid, user_id=user_id, type=_PTxType.freeze,
                        amount=10, balance_after=100, frozen_after=10,
                        source="billing", billing_id=bid, cascade_group_id=cgid, created_at=now))
            s.add(_PTx(id=cid, user_id=user_id, type=_PTxType.consume,
                        amount=10, balance_after=90, frozen_after=0,
                        source="billing", billing_id=bid, cascade_group_id=cgid, created_at=now))
            await s.commit()

    _asyncio.run(_insert())
    return cgid, bid, fid, cid


@pytest.fixture
def grouped_search_client(monkeypatch):
    """带 cascade 分组数据的 points TestClient。"""
    from fakeredis.aioredis import FakeRedis
    fake = FakeRedis()
    monkeypatch.setattr(ledger_module, "_redis_factory", lambda: fake)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sm() as s:
            s.add(User(id="user-1", username="bob", hashed_password="x",
                       is_admin=False, is_active=True))
            s.add(UserPoints(user_id="user-1", balance=90, frozen=0))
            await s.commit()

    asyncio.run(_setup())
    cgid, bid, fid, cid = _seed_cascade_group(sm, "user-1")

    async def _override_db():
        async with sm() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    async def _normal_user():
        return User(id="user-1", username="bob", hashed_password="x",
                    is_admin=False, is_active=True)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _normal_user
    try:
        yield TestClient(app), cgid, bid, fid
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_grouped_search_by_cascade_group_id(grouped_search_client):
    client, cgid, bid, fid = grouped_search_client
    resp = client.get("/api/v1/points/transactions/grouped",
                      params={"cascade_group_id": cgid})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["pagination"]["total"] == 1
    assert data["items"][0]["cascade_group_id"] == cgid
    assert data["matched_transaction_id"] is None


def test_grouped_search_by_billing_id(grouped_search_client):
    client, cgid, bid, fid = grouped_search_client
    resp = client.get("/api/v1/points/transactions/grouped",
                      params={"billing_id": bid})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["items"][0]["cascade_group_id"] == cgid
    assert data["matched_transaction_id"] is None


def test_grouped_search_by_transaction_id(grouped_search_client):
    client, cgid, bid, fid = grouped_search_client
    resp = client.get("/api/v1/points/transactions/grouped",
                      params={"transaction_id": fid})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["items"][0]["cascade_group_id"] == cgid
    assert data["matched_transaction_id"] == fid


def test_grouped_search_unknown_id_returns_empty(grouped_search_client):
    client, _, _, _ = grouped_search_client
    resp = client.get("/api/v1/points/transactions/grouped",
                      params={"transaction_id": "nonexistent-id"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["pagination"]["total"] == 0
    assert data["items"] == []


def test_grouped_transactions_returns_recharge_in_simple_txns(points_client: TestClient) -> None:
    """充值/调整应进入 simple_txns，而不是 cascade 分组 items。"""
    async def _admin_user() -> User:
        return User(id="admin-1", username="admin", hashed_password="x", is_admin=True, is_active=True)

    app.dependency_overrides[get_current_user] = _admin_user
    recharge_resp = points_client.post(
        "/api/v1/admin/users/user-1/points/recharge",
        json={"amount": 25, "remark": "manual top up"},
    )
    assert recharge_resp.status_code == 200
    tx_id = recharge_resp.json()["data"]["id"]

    async def _normal_user() -> User:
        return User(id="user-1", username="bob", hashed_password="x", is_admin=False, is_active=True)

    app.dependency_overrides[get_current_user] = _normal_user
    resp = points_client.get("/api/v1/points/transactions/grouped")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "simple_txns" in data
    assert any(tx["id"] == tx_id for tx in data["simple_txns"])
    assert all(
        g["cascade_group_id"] != recharge_resp.json()["data"]["billing_id"]
        for g in data["items"]
    )
