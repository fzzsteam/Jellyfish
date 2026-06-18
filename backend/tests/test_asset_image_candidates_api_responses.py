"""资产图片候选接口响应壳测试。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.dependencies import get_db
from app.main import app


class _FakeDB:
    async def commit(self) -> None:
        return None


def _override_db(db: _FakeDB):
    async def _get_db() -> AsyncGenerator[_FakeDB, None]:
        yield db

    return _get_db


def _candidate(candidate_id: int, file_id: str = "file-1") -> SimpleNamespace:
    return SimpleNamespace(
        id=candidate_id,
        target_type="scene_image",
        target_id=10,
        file_id=file_id,
        source_type="upload",
        source_ref="manual",
    )


def test_list_entity_image_candidates_returns_success_envelope(client: TestClient, monkeypatch) -> None:
    async def _fake_load_target(_db, *, target_type: str, target_id: int):
        return SimpleNamespace(file_id="file-1")

    async def _fake_list(_db, *, target_type: str, target_id: int):
        return [_candidate(1)]

    from app.api.v1.routes.studio import entities as route

    monkeypatch.setattr(route, "load_asset_image_target", _fake_load_target)
    monkeypatch.setattr(route, "list_asset_image_candidates", _fake_list)

    app.dependency_overrides[get_db] = _override_db(_FakeDB())
    try:
        response = client.get("/api/v1/studio/entities/scene/scene-1/images/10/candidates")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"][0]["file_id"] == "file-1"
    assert body["data"][0]["is_adopted"] is True


def test_attach_entity_image_candidates_returns_created_envelope(client: TestClient, monkeypatch) -> None:
    async def _fake_attach(_db, **kwargs):
        return _candidate(2, file_id=kwargs["file_id"])

    async def _fake_load_target(_db, *, target_type: str, target_id: int):
        return SimpleNamespace(file_id=None)

    from app.api.v1.routes.studio import entities as route

    monkeypatch.setattr(route, "attach_asset_image_candidate", _fake_attach)
    monkeypatch.setattr(route, "load_asset_image_target", _fake_load_target)

    app.dependency_overrides[get_db] = _override_db(_FakeDB())
    try:
        response = client.post(
            "/api/v1/studio/entities/scene/scene-1/images/10/candidates",
            json={"file_ids": ["file-a", "file-b"], "source_type": "upload", "source_ref": "batch-1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == 201
    assert [item["file_id"] for item in body["data"]] == ["file-a", "file-b"]


def test_adopt_entity_image_candidate_returns_success_envelope(client: TestClient, monkeypatch) -> None:
    async def _fake_adopt(_db, *, candidate_id: int):
        return _candidate(candidate_id, file_id="file-adopted")

    from app.api.v1.routes.studio import entities as route

    monkeypatch.setattr(route, "adopt_asset_image_candidate", _fake_adopt)

    app.dependency_overrides[get_db] = _override_db(_FakeDB())
    try:
        response = client.post("/api/v1/studio/entities/scene/scene-1/images/10/candidates/3/adopt")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["id"] == 3
    assert body["data"]["is_adopted"] is True


def test_delete_entity_image_candidate_returns_empty_envelope(client: TestClient, monkeypatch) -> None:
    async def _fake_delete(_db, *, candidate_id: int):
        return None

    from app.api.v1.routes.studio import entities as route

    monkeypatch.setattr(route, "delete_asset_image_candidate", _fake_delete)

    app.dependency_overrides[get_db] = _override_db(_FakeDB())
    try:
        response = client.delete("/api/v1/studio/entities/scene/scene-1/images/10/candidates/3")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "success"
    assert body["data"] is None
