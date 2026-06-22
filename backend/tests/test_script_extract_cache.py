"""script-processing extract 缓存测试。"""

from __future__ import annotations

import pytest

from app.api.v1.routes import script_processing as route
from app.schemas.skills.script_processing import StudioScriptExtractionDraft
from app.services.script_extraction_cache import (
    build_script_extract_cache_key,
    clear_script_extract_cache,
)


def _build_result() -> StudioScriptExtractionDraft:
    return StudioScriptExtractionDraft(
        project_id="project-1",
        chapter_id="chapter-1",
        script_text="测试文本",
        characters=[],
        scenes=[],
        props=[],
        costumes=[],
        shots=[],
    )


class _FakeDB:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


async def _async_noop(*_args, **_kwargs) -> None:
    return None


async def _passthrough_billed_operation(_db, *, user_id, quote_token, business_type, operation):
    """绕过积分冻结/消费基础设施，直接执行 operation 并返回其结果。

    为什么需要：extract 缓存测试聚焦缓存命中/未命中行为，不关心计费；Task 6 为 extract
    LLM 路径接入 run_billed_text_operation 后，这些单元测试必须绕过冻结基础设施
    （需要真实 sqlite + fakeredis + ModelSettings），否则被计费细节淹没。
    """
    return await operation()


class _FakeUser:
    id = "test-user"


@pytest.mark.asyncio
async def test_extract_script_uses_cache_by_default(monkeypatch):
    clear_script_extract_cache()
    calls: list[str] = []
    db = _FakeDB()

    class _FakeAgent:
        def __init__(self, _llm):
            pass

        def extract(self, **_kwargs):
            calls.append("extract")
            return _build_result()

    monkeypatch.setattr(route, "ElementExtractorAgent", _FakeAgent)
    monkeypatch.setattr(route, "sync_shot_extracted_candidates_from_draft", _async_noop)
    monkeypatch.setattr(route, "sync_shot_extracted_dialogue_candidates_from_draft", _async_noop)
    monkeypatch.setattr(route, "apply_shot_semantic_defaults_from_draft", _async_noop)
    # 绕过计费基础设施：直接执行 operation。
    monkeypatch.setattr(route, "run_billed_text_operation", _passthrough_billed_operation)

    request = route.ScriptExtractRequest(
        project_id="project-1",
        chapter_id="chapter-1",
        script_division={"total_shots": 1, "shots": [{"index": 1, "script_excerpt": "a", "shot_name": "s"}]},
        consistency=None,
        refresh_cache=False,
        quote_token="qt-test",
    )

    first = await route.extract_script(request, llm=None, db=db, current_user=_FakeUser())
    second = await route.extract_script(request, llm=None, db=db, current_user=_FakeUser())

    assert first.data is not None
    assert second.data is not None
    assert first.meta == {"from_cache": False}
    assert second.meta == {"from_cache": True}
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_extract_script_refresh_cache_forces_recompute(monkeypatch):
    clear_script_extract_cache()
    calls: list[str] = []
    db = _FakeDB()

    class _FakeAgent:
        def __init__(self, _llm):
            pass

        def extract(self, **_kwargs):
            calls.append("extract")
            return _build_result()

    monkeypatch.setattr(route, "ElementExtractorAgent", _FakeAgent)
    monkeypatch.setattr(route, "sync_shot_extracted_candidates_from_draft", _async_noop)
    monkeypatch.setattr(route, "sync_shot_extracted_dialogue_candidates_from_draft", _async_noop)
    monkeypatch.setattr(route, "apply_shot_semantic_defaults_from_draft", _async_noop)
    monkeypatch.setattr(route, "run_billed_text_operation", _passthrough_billed_operation)

    request = route.ScriptExtractRequest(
        project_id="project-1",
        chapter_id="chapter-1",
        script_division={"total_shots": 1, "shots": [{"index": 1, "script_excerpt": "a", "shot_name": "s"}]},
        consistency=None,
        refresh_cache=False,
        quote_token="qt-test",
    )
    refresh_request = request.model_copy(update={"refresh_cache": True})

    await route.extract_script(request, llm=None, db=db, current_user=_FakeUser())
    refreshed = await route.extract_script(refresh_request, llm=None, db=db, current_user=_FakeUser())

    assert refreshed.meta == {"from_cache": False}
    assert len(calls) == 2


def test_build_script_extract_cache_key_changes_when_payload_changes():
    key1 = build_script_extract_cache_key(
        project_id="project-1",
        chapter_id="chapter-1",
        script_division={"total_shots": 1, "shots": [{"index": 1}]},
        consistency=None,
    )
    key2 = build_script_extract_cache_key(
        project_id="project-1",
        chapter_id="chapter-1",
        script_division={"total_shots": 2, "shots": [{"index": 1}, {"index": 2}]},
        consistency=None,
    )

    assert key1 != key2
