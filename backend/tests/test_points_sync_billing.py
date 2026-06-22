"""Task 6：同步文本操作统一计费测试。

覆盖 11 个同步 real-LLM 端点（divide / merge-entities / analyze-variants /
check-consistency / analyze-character-portrait / analyze-prop-info / analyze-scene-info /
analyze-costume-info / optimize-script / simplify-script / extract）：

- 成功 → consume：产生 consume 流水，余额按 required_points 扣减。
- LLM 异常 → unfreeze：产生 unfreeze 流水，余额恢复、无 consume。
- 余额不足 → LLM 未被调用：返回 INSUFFICIENT_POINTS(402)，agent 调用计数为 0。
- 报价变更 → LLM 未被调用：返回 POINTS_QUOTE_CHANGED(409)，agent 调用计数为 0。

测试策略：
- 内存 SQLite + fakeredis（替换 ledger._redis_factory）。
- 每个 endpoint 参数替换对应 Agent 类，记录调用次数 + 控制成功/抛异常。
- 用 FastAPI TestClient 驱动真实路由层（依赖注入替换 get_db/get_current_user）。
- extract 端点带缓存路径：refresh_cache=True 强制走 LLM 分支。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1.routes import script_processing as sp_route
from app.core.db import Base
from app.dependencies import get_current_user, get_db, get_llm, get_nothinking_llm
from app.models.llm import Model, ModelCategoryKey, ModelSettings, Provider
from app.models.points import PointTransaction, PointTransactionType
from app.models.user import User
from app.services.points import create_quote_token, hash_quote_params, ledger
from app.services.points.billing import PointsDomainError
from app.services.points.quote_tokens import QuoteClaims

USER_ID = "u1"


class _StubLLM:
    """占位 LLM：测试中 agent 类已被整体替换，LLM 参数不被真正使用。

    为什么不用 langchain BaseChatModel 子类：路由的 Depends(get_llm/get_nothinking_llm)
    会尝试按 ModelSettings 解析真实 provider 配置（遇到测试 provider 名即抛
    'Unsupported provider name'）。直接用依赖覆盖返回本占位即可绕过解析，
    让请求进入路由体；agent 调用由 _make_fake_agent 替身接管。
    """

# 文本模型单价：unit_points=7 → text 计价 required = 7 * 1 = 7。
UNIT_POINTS = 7
REQUIRED_POINTS = UNIT_POINTS


# ---------------------------------------------------------------------------
# 公共夹具
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    """将账本的 Redis 工厂替换为 fakeredis，使账户变更在测试中互斥可验。"""
    client = FakeRedis()

    def _factory():
        return client

    monkeypatch.setattr(ledger, "_redis_factory", _factory)
    yield client


def _make_text_quote_token(*, required_points: int = REQUIRED_POINTS) -> str:
    """构造一个合法的文本 quote_token（category=text, generation_count=1）。

    required_points 默认与 m_text unit_points=7 一致，重算通过一致性校验。
    """
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
            business_type="script_divide",  # business_type 不参与 token 校验
            model_id="m_text",
            params_hash=params_hash,
            required_points=required_points,
        )
    )


def _build_app_and_db(monkeypatch) -> tuple[FastAPI, object, object]:
    """构造内存 SQLite + 种子数据 + 挂载 script_processing 路由的 FastAPI app。

    返回 (app_obj, async_engine, async_session_local)。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 触发所有相关模型注册。
    import app.models.llm  # noqa: F401
    import app.models.points  # noqa: F401
    import app.models.task  # noqa: F401
    import app.models.task_links  # noqa: F401
    import app.models.studio  # noqa: F401

    async def _seed():
        from app.models.studio import Chapter, Project, ProjectStyle, ProjectVisualStyle

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_local() as db:
            db.add(User(id=USER_ID, username="u1", hashed_password="x", is_active=True, token_version=0))
            db.add(Provider(id="p1", user_id=USER_ID, name="prov", base_url="http://x", api_key="k"))
            db.add(
                Model(
                    id="m_text",
                    user_id=USER_ID,
                    name="text-model",
                    category=ModelCategoryKey.text,
                    provider_id="p1",
                    unit_points=UNIT_POINTS,
                )
            )
            db.add(ModelSettings(id=1, default_text_model_id="m_text", user_id=USER_ID))
            # extract 端点的 LLM 路径会 sync_shot_extracted_candidates_from_draft(chapter_id)，
            # 需要库内存在 Project + Chapter 行；预置以免各测试重复构造。
            db.add(
                Project(
                    id="proj-1",
                    name="项目",
                    style=ProjectStyle.real_people_city,
                    visual_style=ProjectVisualStyle.live_action,
                    user_id=USER_ID,
                )
            )
            db.add(Chapter(id="ch-1", project_id="proj-1", index=1, title="第一章"))
            await db.commit()

    asyncio.run(_seed())

    app_obj = FastAPI()
    app_obj.include_router(sp_route.router, prefix="/api/v1")

    async def _override_db():
        async with session_local() as db:
            yield db

    class _FakeUser:
        id = USER_ID

    async def _override_user():
        return _FakeUser()

    app_obj.dependency_overrides[get_db] = _override_db
    app_obj.dependency_overrides[get_current_user] = _override_user
    # LLM 依赖覆盖：agent 类已被整体替换，LLM 参数无需真实；占位绕过 provider 解析。
    app_obj.dependency_overrides[get_nothinking_llm] = lambda: _StubLLM()
    app_obj.dependency_overrides[get_llm] = lambda: _StubLLM()

    # 注册 PointsDomainError 处理器（与 main.py 一致），使 TestClient 拿到结构化响应。
    def _handler(_request, exc: PointsDomainError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=exc.status_code, content={"data": exc.data, "error_code": exc.code})

    app_obj.add_exception_handler(PointsDomainError, _handler)

    return app_obj, engine, session_local


def _recharge(session_local, amount: int) -> None:
    """给 USER_ID 充值（同步入口驱动异步 seed）。"""
    from app.services.points.ledger import recharge

    async def _do():
        async with session_local() as db:
            await recharge(db, user_id=USER_ID, amount=amount, created_by="t", remark="seed")

    asyncio.run(_do())


def _get_balance(session_local) -> tuple[int, int]:
    """返回 (balance, frozen)。"""
    from app.services.points.ledger import get_points

    async def _do():
        async with session_local() as db:
            pts = await get_points(db, user_id=USER_ID)
            return pts.balance, pts.frozen

    return asyncio.run(_do())


def _count_tx(session_local, tx_type: PointTransactionType) -> int:
    """统计某类型流水数量。"""
    from sqlalchemy import select

    async def _do():
        async with session_local() as db:
            rows = (
                await db.execute(
                    select(PointTransaction).where(
                        PointTransaction.user_id == USER_ID,
                        PointTransaction.type == tx_type,
                    )
                )
            ).scalars().all()
            return len(rows)

    return asyncio.run(_do())


# ---------------------------------------------------------------------------
# 参数化：11 个端点的元数据
# ---------------------------------------------------------------------------


def _factory_results() -> dict[str, Any]:
    """每个端点成功时 agent 返回的合法结果对象。"""
    from app.chains.agents.script_processing_agents import (
        EntityMergeResult,
        ScriptConsistencyCheckResult,
        ScriptDivisionResult,
        ScriptOptimizationResult,
        ScriptSimplificationResult,
        StudioScriptExtractionDraft,
        VariantAnalysisResult,
    )
    from app.schemas.skills.character_portrait import CharacterPortraitAnalysisResult
    from app.schemas.skills.costume_info_analysis import CostumeInfoAnalysisResult
    from app.schemas.skills.prop_info_analysis import PropInfoAnalysisResult
    from app.schemas.skills.scene_info_analysis import SceneInfoAnalysisResult

    return {
        "divide": ScriptDivisionResult(shots=[], total_shots=0),
        "merge-entities": EntityMergeResult(merged_library={"total_entries": 0}),
        "analyze-variants": VariantAnalysisResult(),
        "check-consistency": ScriptConsistencyCheckResult(has_issues=False),
        "analyze-character-portrait": CharacterPortraitAnalysisResult(issues=[], optimized_description="x"),
        "analyze-prop-info": PropInfoAnalysisResult(issues=[], optimized_description="x"),
        "analyze-scene-info": SceneInfoAnalysisResult(issues=[], optimized_description="x"),
        "analyze-costume-info": CostumeInfoAnalysisResult(issues=[], optimized_description="x"),
        "optimize-script": ScriptOptimizationResult(
            optimized_script_text="优化后", change_summary="摘要"
        ),
        "simplify-script": ScriptSimplificationResult(
            simplified_script_text="精简后", simplification_summary="摘要"
        ),
        # extract 走 refresh_cache=True 强制 LLM 分支；StudioScriptExtractionDraft 需 project_id/chapter_id/script_text
        "extract": StudioScriptExtractionDraft(
            project_id="proj-1", chapter_id="ch-1", script_text="剧本"
        ),
    }


def _payloads() -> dict[str, dict[str, Any]]:
    """每个端点最小合法请求体（不含 quote_token，由测试运行时注入）。"""
    return {
        "divide": {"script_text": "一段剧本", "write_to_db": False},
        "merge-entities": {"all_shot_extractions": []},
        "analyze-variants": {"merged_library": {}, "all_shot_extractions": []},
        "check-consistency": {"script_text": "完整剧本"},
        "analyze-character-portrait": {"character_description": "人物描述"},
        "analyze-prop-info": {"prop_description": "道具描述"},
        "analyze-scene-info": {"scene_description": "场景描述"},
        "analyze-costume-info": {"costume_description": "服装描述"},
        "optimize-script": {"script_text": "原文", "consistency": {"has_issues": True}},
        "simplify-script": {"script_text": "原文"},
        "extract": {
            "project_id": "proj-1",
            "chapter_id": "ch-1",
            "script_division": {"shots": []},
            "refresh_cache": True,
        },
    }


def _agent_classes() -> dict[str, str]:
    """每个端点在 script_processing 路由模块内引用的 Agent 类名。"""
    return {
        "divide": "ScriptDividerAgent",
        "merge-entities": "EntityMergerAgent",
        "analyze-variants": "VariantAnalyzerAgent",
        "check-consistency": "ConsistencyCheckerAgent",
        "analyze-character-portrait": "CharacterPortraitAnalysisAgent",
        "analyze-prop-info": "PropInfoAnalysisAgent",
        "analyze-scene-info": "SceneInfoAnalysisAgent",
        "analyze-costume-info": "CostumeInfoAnalysisAgent",
        "optimize-script": "ScriptOptimizerAgent",
        "simplify-script": "ScriptSimplifierAgent",
        "extract": "ElementExtractorAgent",
    }


def _make_fake_agent(monkeypatch, *, raise_on_call: bool = False) -> dict[str, int]:
    """替换路由模块内所有 11 个 Agent 类为可控 fake。

    - raise_on_call=False：返回预设成功结果，并记录调用次数到 call_state["n"]。
    - raise_on_call=True：agent 方法抛 RuntimeError，模拟 LLM 失败。

    返回 call_state dict（"n" 字段记录调用次数），供断言 agent 是否被调用。
    """
    results = _factory_results()
    agent_classes = _agent_classes()
    call_state = {"n": 0}

    def _build(cls_name: str, endpoint_key: str):
        class _FakeAgent:
            def __init__(self, llm):
                pass

            # 覆盖各 agent 使用的不同方法名：divide_script / extract / analyze_*。
            def divide_script(self, **kw):
                call_state["n"] += 1
                if raise_on_call:
                    raise RuntimeError("llm boom")
                return results[endpoint_key]

            def extract(self, **kw):
                call_state["n"] += 1
                if raise_on_call:
                    raise RuntimeError("llm boom")
                return results[endpoint_key]

            def analyze_character_description(self, **kw):
                call_state["n"] += 1
                if raise_on_call:
                    raise RuntimeError("llm boom")
                return results[endpoint_key]

            def analyze_prop_description(self, **kw):
                call_state["n"] += 1
                if raise_on_call:
                    raise RuntimeError("llm boom")
                return results[endpoint_key]

            def analyze_scene_description(self, **kw):
                call_state["n"] += 1
                if raise_on_call:
                    raise RuntimeError("llm boom")
                return results[endpoint_key]

            def analyze_costume_description(self, **kw):
                call_state["n"] += 1
                if raise_on_call:
                    raise RuntimeError("llm boom")
                return results[endpoint_key]

        _FakeAgent.__name__ = cls_name
        return _FakeAgent

    for endpoint_key, cls_name in agent_classes.items():
        monkeypatch.setattr(sp_route, cls_name, _build(cls_name, endpoint_key))

    return call_state


ENDPOINTS = list(_payloads().keys())


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_sync_success_consumes_points(monkeypatch, endpoint: str) -> None:
    """成功 → 产生 consume 流水，余额扣减 required_points。"""
    call_state = _make_fake_agent(monkeypatch, raise_on_call=False)
    app_obj, engine, session_local = _build_app_and_db(monkeypatch)
    _recharge(session_local, 100)

    token = _make_text_quote_token(required_points=REQUIRED_POINTS)
    payload = {**_payloads()[endpoint], "quote_token": token}

    client = TestClient(app_obj)
    resp = client.post(f"/api/v1/script-processing/{endpoint}", json=payload)
    assert resp.status_code == 200, resp.text

    # agent 被调用一次
    assert call_state["n"] == 1
    # 余额扣减、冻结归零
    balance, frozen = _get_balance(session_local)
    assert balance == 100 - REQUIRED_POINTS
    assert frozen == 0
    # 产生 consume 流水（recharge 是 source=billing 之外的，但 type=recharge，不计入 consume 计数）
    assert _count_tx(session_local, PointTransactionType.consume) == 1
    assert _count_tx(session_local, PointTransactionType.unfreeze) == 0

    asyncio.run(engine.dispose())


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_sync_llm_exception_unfreezes(monkeypatch, endpoint: str) -> None:
    """LLM 异常 → 产生 unfreeze 流水，余额恢复、无 consume。"""
    call_state = _make_fake_agent(monkeypatch, raise_on_call=True)
    app_obj, engine, session_local = _build_app_and_db(monkeypatch)
    _recharge(session_local, 100)

    token = _make_text_quote_token(required_points=REQUIRED_POINTS)
    payload = {**_payloads()[endpoint], "quote_token": token}

    client = TestClient(app_obj)
    resp = client.post(f"/api/v1/script-processing/{endpoint}", json=payload)
    # 同步 agent 抛 RuntimeError → 路由 except 分支 → 500
    assert resp.status_code == 500
    # agent 确实被调用一次（LLM 失败发生在调用后）
    assert call_state["n"] == 1
    # 余额恢复、冻结归零
    balance, frozen = _get_balance(session_local)
    assert balance == 100
    assert frozen == 0
    # 产生 unfreeze 流水，无 consume
    assert _count_tx(session_local, PointTransactionType.unfreeze) == 1
    assert _count_tx(session_local, PointTransactionType.consume) == 0

    asyncio.run(engine.dispose())


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_sync_insufficient_balance_skips_llm(monkeypatch, endpoint: str) -> None:
    """余额不足 → LLM 未被调用，返回 INSUFFICIENT_POINTS(402)。"""
    call_state = _make_fake_agent(monkeypatch, raise_on_call=False)
    app_obj, engine, session_local = _build_app_and_db(monkeypatch)
    # 不充值 → 可用 0

    token = _make_text_quote_token(required_points=REQUIRED_POINTS)
    payload = {**_payloads()[endpoint], "quote_token": token}

    client = TestClient(app_obj)
    resp = client.post(f"/api/v1/script-processing/{endpoint}", json=payload)
    assert resp.status_code == 402
    body = resp.json()
    assert body["error_code"] == "INSUFFICIENT_POINTS"
    # agent 从未被调用
    assert call_state["n"] == 0
    # 无冻结、无 consume
    balance, frozen = _get_balance(session_local)
    assert balance == 0
    assert frozen == 0
    assert _count_tx(session_local, PointTransactionType.freeze) == 0
    assert _count_tx(session_local, PointTransactionType.consume) == 0

    asyncio.run(engine.dispose())


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_sync_quote_changed_skips_llm(monkeypatch, endpoint: str) -> None:
    """报价变更 → LLM 未被调用，返回 POINTS_QUOTE_CHANGED(409)。

    构造：quote_token 声称 required_points=1，但 m_text unit_points=7 → 重算=7，不一致。
    """
    call_state = _make_fake_agent(monkeypatch, raise_on_call=False)
    app_obj, engine, session_local = _build_app_and_db(monkeypatch)
    _recharge(session_local, 100)

    # token 声称 1 分，实际重算 7 分 → POINTS_QUOTE_CHANGED
    token = _make_text_quote_token(required_points=1)
    payload = {**_payloads()[endpoint], "quote_token": token}

    client = TestClient(app_obj)
    resp = client.post(f"/api/v1/script-processing/{endpoint}", json=payload)
    assert resp.status_code == 409
    body = resp.json()
    assert body["error_code"] == "POINTS_QUOTE_CHANGED"
    # agent 从未被调用
    assert call_state["n"] == 0
    # 余额未变、无冻结
    balance, frozen = _get_balance(session_local)
    assert balance == 100
    assert frozen == 0

    asyncio.run(engine.dispose())


def test_sync_missing_quote_token_returns_400(monkeypatch) -> None:
    """未传 quote_token → 400（同步端点强制要求）。"""
    _make_fake_agent(monkeypatch, raise_on_call=False)
    app_obj, engine, session_local = _build_app_and_db(monkeypatch)
    _recharge(session_local, 100)

    client = TestClient(app_obj)
    resp = client.post(
        "/api/v1/script-processing/divide",
        json={"script_text": "一段剧本", "write_to_db": False},
    )
    assert resp.status_code == 400
    assert "quote_token" in resp.json()["detail"]

    asyncio.run(engine.dispose())


def test_extract_cache_hit_does_not_bill(monkeypatch) -> None:
    """extract 命中缓存 → 不调用 LLM，不计费（与预览端点同语义）。

    策略：先写入缓存（fake agent 产出一次结果），第二次请求 refresh_cache=False
    命中缓存 → 不计费、无 consume。验证缓存路径不触发冻结/消费。
    """
    call_state = _make_fake_agent(monkeypatch, raise_on_call=False)
    app_obj, engine, session_local = _build_app_and_db(monkeypatch)
    _recharge(session_local, 100)

    token = _make_text_quote_token(required_points=REQUIRED_POINTS)
    client = TestClient(app_obj)

    # 第一次：refresh_cache=True → 走 LLM 分支，计费。
    resp1 = client.post(
        "/api/v1/script-processing/extract",
        json={
            "project_id": "proj-1",
            "chapter_id": "ch-1",
            "script_division": {"shots": []},
            "refresh_cache": True,
            "quote_token": token,
        },
    )
    assert resp1.status_code == 200, resp1.text
    assert call_state["n"] == 1
    balance1, frozen1 = _get_balance(session_local)
    assert balance1 == 100 - REQUIRED_POINTS
    assert frozen1 == 0

    # 第二次：refresh_cache=False，缓存命中 → 不计费、agent 不被调用。
    # 缓存命中无需 quote_token（路由在缓存检查之后才校验 quote_token）。
    resp2 = client.post(
        "/api/v1/script-processing/extract",
        json={
            "project_id": "proj-1",
            "chapter_id": "ch-1",
            "script_division": {"shots": []},
            "refresh_cache": False,
        },
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["meta"]["from_cache"] is True
    # agent 调用次数不变（仍为 1）
    assert call_state["n"] == 1
    # 余额未进一步扣减
    balance2, _ = _get_balance(session_local)
    assert balance2 == 100 - REQUIRED_POINTS

    asyncio.run(engine.dispose())


# ---------------------------------------------------------------------------
# I2：post-LLM 业务失败 → unfreeze（证明 operation 内部后置异步步骤抛错也会解冻）
# ---------------------------------------------------------------------------


def test_divide_post_llm_write_to_db_failure_unfreezes(monkeypatch) -> None:
    """divide 端点：agent 成功返回，但 write_division_result_to_chapter 抛错 → unfreeze。

    覆盖场景：post-LLM 业务失败（write_to_db=True 时入库失败）。
    关键断言：
    - agent 被调用且成功（call_state["n"] == 1）——证明 LLM 确实跑完了。
    - 产生 unfreeze 流水、无 consume ——证明 operation 抛错后走了 unfreeze 分支。
    - 余额恢复原始值、冻结归零。
    """
    call_state = _make_fake_agent(monkeypatch, raise_on_call=False)
    app_obj, engine, session_local = _build_app_and_db(monkeypatch)
    _recharge(session_local, 100)

    # write_to_db=True + 有效 chapter_id（ch-1 在 _build_app_and_db 种子数据中预置）。
    # monkeypatch write_division_result_to_chapter 抛错，模拟 LLM 成功后入库失败。
    async def _boom_write(*args, **kwargs):
        raise RuntimeError("db write boom")

    monkeypatch.setattr(sp_route, "write_division_result_to_chapter", _boom_write)

    token = _make_text_quote_token(required_points=REQUIRED_POINTS)
    payload = {
        "script_text": "一段剧本",
        "write_to_db": True,
        "chapter_id": "ch-1",
        "quote_token": token,
    }

    client = TestClient(app_obj)
    resp = client.post("/api/v1/script-processing/divide", json=payload)
    # 后置入库失败 → 路由 except Exception 分支 → 500
    assert resp.status_code == 500, resp.text

    # agent 已被调用且成功（LLM 确实跑完，失败发生在后置 write_to_db）
    assert call_state["n"] == 1
    # 产生 unfreeze 流水、无 consume
    assert _count_tx(session_local, PointTransactionType.unfreeze) == 1
    assert _count_tx(session_local, PointTransactionType.consume) == 0
    # 余额恢复、冻结归零
    balance, frozen = _get_balance(session_local)
    assert balance == 100
    assert frozen == 0

    asyncio.run(engine.dispose())


def test_extract_post_llm_sync_candidates_failure_unfreezes(monkeypatch) -> None:
    """extract 端点：agent 成功返回，但 sync_shot_extracted_candidates_from_draft 抛错 → unfreeze。

    覆盖场景：post-LLM 业务失败（草稿候选同步失败）。
    关键断言：
    - agent 被调用且成功（call_state["n"] == 1）——证明 LLM 确实跑完了。
    - 产生 unfreeze 流水、无 consume ——证明 operation 抛错后走了 unfreeze 分支。
    - 余额恢复原始值、冻结归零。
    """
    call_state = _make_fake_agent(monkeypatch, raise_on_call=False)
    app_obj, engine, session_local = _build_app_and_db(monkeypatch)
    _recharge(session_local, 100)

    # monkeypatch sync_shot_extracted_candidates_from_draft 抛错，模拟 LLM 成功后候选同步失败。
    async def _boom_sync(*args, **kwargs):
        raise RuntimeError("candidate sync boom")

    monkeypatch.setattr(sp_route, "sync_shot_extracted_candidates_from_draft", _boom_sync)

    token = _make_text_quote_token(required_points=REQUIRED_POINTS)
    payload = {
        "project_id": "proj-1",
        "chapter_id": "ch-1",
        "script_division": {"shots": []},
        "refresh_cache": True,
        "quote_token": token,
    }

    client = TestClient(app_obj)
    resp = client.post("/api/v1/script-processing/extract", json=payload)
    # 后置同步失败 → 路由 except Exception 分支 → 500
    assert resp.status_code == 500, resp.text

    # agent 已被调用且成功（LLM 确实跑完，失败发生在后置候选同步）
    assert call_state["n"] == 1
    # 产生 unfreeze 流水、无 consume
    assert _count_tx(session_local, PointTransactionType.unfreeze) == 1
    assert _count_tx(session_local, PointTransactionType.consume) == 0
    # 余额恢复、冻结归零
    balance, frozen = _get_balance(session_local)
    assert balance == 100
    assert frozen == 0

    asyncio.run(engine.dispose())
