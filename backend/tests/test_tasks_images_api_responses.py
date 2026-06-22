"""film/tasks_images 接口响应壳测试。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v1.routes.film import tasks_images as route
from app.dependencies import get_db
from app.main import app


class _FakeTaskRecord:
    def __init__(self, task_id: str) -> None:
        self.id = task_id


class _FakeTaskManager:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def create(self, *_args, **_kwargs) -> _FakeTaskRecord:
        return _FakeTaskRecord("prompt-task-1")


class _FakeDB:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.committed = False

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True


async def _async_noop(*_args, **_kwargs) -> None:
    return None


async def _fake_freeze_for_task(*_args, **_kwargs):
    """桩：返回带 billing_id 的冻结句柄，绕开真实积分落账。"""
    from app.services.points.billing import FrozenBilling

    return FrozenBilling(
        billing_id="bill-test-1",
        required_points=7,
        model_id="m_text",
        business_type="shot_frame_prompt",
        snapshot={},
    )


def _override_db(db: _FakeDB):
    async def _get_db() -> AsyncGenerator[_FakeDB, None]:
        yield db

    return _get_db


def test_create_shot_frame_prompt_task_returns_created_envelope(client: TestClient, monkeypatch) -> None:
    db = _FakeDB()

    async def _fake_build(*_args, **_kwargs):
        return {"shot_id": "shot-1", "frame_type": "first"}

    monkeypatch.setattr(route, "build_shot_frame_prompt_run_args", _fake_build)
    monkeypatch.setattr(route, "TaskManager", _FakeTaskManager)
    monkeypatch.setattr(route, "enqueue_task_execution", lambda task_id: SimpleNamespace(id=f"celery-{task_id}"))
    monkeypatch.setattr(route, "mark_shot_generating", _async_noop)
    # 绕开真实积分冻结/解冻：路由内 freeze_for_task 已计费，此处用桩返回 billing_id。
    monkeypatch.setattr(route, "freeze_for_task", _fake_freeze_for_task)
    monkeypatch.setattr(route, "unfreeze_frozen", _async_noop)
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.post(
            "/api/v1/film/tasks/shot-frame-prompts",
            json={"shot_id": "shot-1", "frame_type": "first", "quote_token": "tok-1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == 201
    assert body["message"] == "success"
    assert body["data"]["task_id"] == "prompt-task-1"
    assert body["meta"] is None
    assert db.committed is True
    assert len(db.added) == 1


def test_create_shot_frame_prompt_task_invalid_frame_type_returns_api_response(
    client: TestClient, monkeypatch
) -> None:
    db = _FakeDB()

    def _fake_normalize(_frame_type: str) -> str:
        raise HTTPException(status_code=400, detail="frame_type must be one of: first/last/key")

    monkeypatch.setattr(route, "normalize_frame_type", _fake_normalize)
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.post(
            "/api/v1/film/tasks/shot-frame-prompts",
            json={"shot_id": "shot-1", "frame_type": "middle", "quote_token": "tok-1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {
        "code": 400,
        "message": "frame_type must be one of: first/last/key",
        "data": None,
        "meta": None,
    }


def test_create_shot_frame_prompt_task_missing_shot_detail_returns_api_response(
    client: TestClient, monkeypatch
) -> None:
    db = _FakeDB()

    async def _fake_build(*_args, **_kwargs):
        raise HTTPException(status_code=404, detail="ShotDetail not found")

    monkeypatch.setattr(route, "build_shot_frame_prompt_run_args", _fake_build)
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.post(
            "/api/v1/film/tasks/shot-frame-prompts",
            json={"shot_id": "shot-1", "frame_type": "first", "quote_token": "tok-1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"code": 404, "message": "ShotDetail not found", "data": None, "meta": None}


def test_create_shot_frame_prompt_task_validation_error_returns_api_response(client: TestClient) -> None:
    db = _FakeDB()
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.post(
            "/api/v1/film/tasks/shot-frame-prompts",
            json={"frame_type": "first"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 422
    assert body["data"] is None
    assert "shot_id" in body["message"]
