"""LLM 接口响应壳测试：聚焦 Provider CRUD 与生成能力选项。"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.models.llm import Model, ModelCategoryKey, ModelSettings, Provider, ProviderStatus
from app.models.user import User
from tests.support.llm_api_app import build_llm_only_app

# 仅挂载 /api/v1/llm，避免导入 app.main 时连带加载 film 路由与 Celery。
llm_app = build_llm_only_app()

# 测试统一以该用户身份发起请求；隔离改造后所有 provider/model/settings 端点需注入 current_user。
_TEST_USER_ID = "test-user"


async def _override_current_user() -> User:
    return User(id=_TEST_USER_ID, username=_TEST_USER_ID, hashed_password="h", is_admin=True)


@pytest.fixture(autouse=True)
def _auth_override() -> Iterator[None]:
    llm_app.dependency_overrides[get_current_user] = _override_current_user
    try:
        yield
    finally:
        llm_app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(llm_app) as c:
        yield c


class _FakeLlmDB:
    """最小 DB 替身：仅覆盖 Provider 路由测试所需行为。"""

    def __init__(self) -> None:
        self.providers: dict[str, Provider] = {}
        self.models: dict[str, Model] = {}
        self.model_settings: dict[int, ModelSettings] = {}

    async def get(self, model: type, entity_id: str) -> Provider | None:  # noqa: ANN401
        if model is Provider:
            return self.providers.get(entity_id)
        if model is Model:
            return self.models.get(entity_id)
        if model is ModelSettings:
            return self.model_settings.get(int(entity_id))
        return None

    async def execute(self, _stmt: object) -> object:  # noqa: ANN401
        """最小 execute 替身：仅服务于"按 user_id 取 ModelSettings"的隔离查询。

        本替身不解析 SQL，直接返回唯一一行 ModelSettings（测试场景每库至多一行）。
        """
        rows = list(self.model_settings.values())
        first = rows[0] if rows else None

        class _Result:
            def scalar_one_or_none(self_inner) -> object:  # noqa: ANN001
                return first

        return _Result()

    def add(self, obj: Provider | Model | ModelSettings) -> None:
        if isinstance(obj, Provider):
            self.providers[obj.id] = obj
            return
        if isinstance(obj, Model):
            self.models[obj.id] = obj
            return
        if isinstance(obj, ModelSettings):
            self.model_settings[obj.id] = obj
            return
        raise TypeError(f"Unsupported object type: {type(obj)!r}")

    async def flush(self) -> None:
        return None

    async def refresh(self, obj: Provider) -> None:
        now = datetime.now(UTC)
        if getattr(obj, "created_at", None) is None:
            obj.created_at = now
        obj.updated_at = now

    async def delete(self, obj: Provider) -> None:
        self.providers.pop(obj.id, None)


def _seed_provider(db: _FakeLlmDB, provider_id: str = "p-1") -> Provider:
    now = datetime.now(UTC)
    obj = Provider(
        id=provider_id,
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key="secret",
        api_secret="",
        description="说明",
        status=ProviderStatus.testing,
        created_by="tester",
    )
    obj.created_at = now
    obj.updated_at = now
    db.providers[obj.id] = obj
    return obj


def _seed_video_model(db: _FakeLlmDB, *, provider_id: str = "p-video", model_id: str = "m-video") -> None:
    provider = _seed_provider(db, provider_id)
    provider.name = "OpenAI"
    db.models[model_id] = Model(
        id=model_id,
        name="sora-mini",
        category=ModelCategoryKey.video,
        provider_id=provider.id,
    )
    db.model_settings[1] = ModelSettings(id=1, default_video_model_id=model_id)


def _seed_image_model(db: _FakeLlmDB, *, provider_id: str = "p-image", model_id: str = "m-image") -> None:
    provider = _seed_provider(db, provider_id)
    provider.name = "火山引擎"
    db.models[model_id] = Model(
        id=model_id,
        name="seedream-4.0",
        category=ModelCategoryKey.image,
        provider_id=provider.id,
    )
    db.model_settings[1] = ModelSettings(id=1, default_image_model_id=model_id)


def _override_db(db: _FakeLlmDB):
    async def _get_db() -> AsyncGenerator[_FakeLlmDB, None]:
        yield db

    return _get_db


def test_create_provider_returns_created_envelope(client: TestClient) -> None:
    db = _FakeLlmDB()
    llm_app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.post(
            "/api/v1/llm/providers",
            json={
                "id": "p-create",
                "name": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "api_key": "secret",
                "api_secret": "",
                "description": "说明",
                "status": "testing",
                "created_by": "tester",
            },
        )
    finally:
        llm_app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == 201
    assert body["message"] == "success"
    assert body["data"]["id"] == "p-create"
    assert body["data"]["name"] == "OpenAI"
    assert body["data"]["base_url"] == "https://api.openai.com/v1"
    assert "api_key" not in body["data"]


def test_get_provider_not_found_returns_api_response(client: TestClient) -> None:
    db = _FakeLlmDB()
    llm_app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.get("/api/v1/llm/providers/missing")
    finally:
        llm_app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {
        "code": 404,
        "message": "Provider not found",
        "data": None,
        "meta": None,
    }


def test_delete_provider_returns_empty_envelope(client: TestClient) -> None:
    db = _FakeLlmDB()
    _seed_provider(db, "p-delete")
    llm_app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.delete("/api/v1/llm/providers/p-delete")
    finally:
        llm_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"code": 200, "message": "success", "data": None, "meta": None}
    assert "p-delete" not in db.providers


def test_create_provider_validation_error_returns_api_response(client: TestClient) -> None:
    db = _FakeLlmDB()
    llm_app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.post(
            "/api/v1/llm/providers",
            json={
                "id": "p-invalid",
                "name": "OpenAI",
            },
        )
    finally:
        llm_app.dependency_overrides.clear()

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 422
    assert body["data"] is None
    assert "base_url" in body["message"]


def test_list_supported_providers_returns_capability_matrix(client: TestClient) -> None:
    response = client.get("/api/v1/llm/providers/supported")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert isinstance(body["data"], list)
    keys = {item["key"] for item in body["data"]}
    assert "openai" in keys
    assert "volcengine" in keys
    assert "aliyun_bailian" in keys
    assert "vidu" in keys


def test_list_supported_providers_text_contains_aliyun_bailian(client: TestClient) -> None:
    response = client.get("/api/v1/llm/providers/supported", params={"category": "text"})
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    keys = {item["key"] for item in (body["data"] or [])}
    assert "aliyun_bailian" in keys


def test_list_supported_providers_can_filter_by_category(client: TestClient) -> None:
    response = client.get("/api/v1/llm/providers/supported", params={"category": "video"})
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert isinstance(body["data"], list)
    keys = {item["key"] for item in body["data"]}
    assert "vidu" in keys
    for item in body["data"]:
        assert "video" in item["supported_categories"]


def test_get_video_generation_options_returns_ratio_capability(client: TestClient) -> None:
    db = _FakeLlmDB()
    _seed_video_model(db)
    llm_app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.get("/api/v1/llm/video-generation-options")
    finally:
        llm_app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["provider"] == "openai"
    assert body["data"]["model_id"] == "m-video"
    assert body["data"]["model_name"] == "sora-mini"
    assert "16:9" in body["data"]["allowed_ratios"]
    assert body["data"]["default_ratio"] == "16:9"


def test_get_image_generation_options_returns_ratio_size_profiles(client: TestClient) -> None:
    db = _FakeLlmDB()
    _seed_image_model(db)
    llm_app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.get("/api/v1/llm/image-generation-options")
    finally:
        llm_app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["provider"] == "volcengine"
    assert body["data"]["model_id"] == "m-image"
    assert body["data"]["model_name"] == "seedream-4.0"
    assert body["data"]["default_resolution_profile"] == "standard"
    assert body["data"]["ratio_size_profiles"]["16:9"]["standard"] == "2848x1600"
    assert body["data"]["ratio_size_profiles"]["16:9"]["high"] == "4096x2304"


def test_create_provider_requires_admin(client: TestClient) -> None:
    """非管理员调用写操作应返回 403。"""
    db = _FakeLlmDB()
    llm_app.dependency_overrides[get_db] = _override_db(db)

    async def _non_admin() -> User:
        return User(id="non-admin", username="non-admin", hashed_password="h", is_admin=False)

    llm_app.dependency_overrides[get_current_user] = _non_admin
    try:
        response = client.post(
            "/api/v1/llm/providers",
            json={
                "id": "p-forbidden",
                "name": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "api_key": "secret",
                "api_secret": "",
                "description": "",
                "status": "testing",
                "created_by": "tester",
            },
        )
    finally:
        llm_app.dependency_overrides.clear()

    assert response.status_code == 403
