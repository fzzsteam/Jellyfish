"""Pytest 共享 fixture：FastAPI 应用与 TestClient。"""

from __future__ import annotations

import asyncio
import inspect
import os

import pytest
from fastapi.testclient import TestClient

# 为测试环境设置必需的环境变量
os.environ.setdefault("INITIAL_ADMIN_PASSWORD", "test-admin-password")

try:
    from app.main import app  # type: ignore
except Exception:  # noqa: BLE001
    # 测试环境里有些可选依赖（例如 langgraph）可能未安装。
    # 不要让整个测试套件在导入 conftest 时直接失败；仅在需要 client 的测试里跳过。
    app = None


@pytest.fixture
def _auth_user_bypass() -> None:
    """为非认证测试提供 get_current_user 绕过。

    这样旧测试不需要修改；认证测试使用 auth_client fixture（不应用此绕过）。
    """
    if app is None:
        return

    from app.core.security import hash_password
    from app.dependencies import get_current_user
    from app.models.user import User

    async def _mock_get_current_user():
        """返回测试用户，无需真实令牌。"""
        return User(
            id="test-user",
            username="test-user",
            hashed_password=hash_password("test-pass"),
            is_admin=True,
            is_active=True,
            token_version=0,
        )

    app.dependency_overrides[get_current_user] = _mock_get_current_user
    yield
    # 测试完成后清理
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(autouse=True)
def _auto_auth_bypass(request: pytest.FixtureRequest) -> None:
    """除认证相关测试外自动应用 auth 绕过。"""
    # 跳过 auth 相关测试文件
    if "test_auth" not in request.node.nodeid and app is not None:
        from app.core.security import hash_password
        from app.dependencies import get_current_user
        from app.models.user import User

        async def _mock_get_current_user():
            return User(
                id="test-user",
                username="test-user",
                hashed_password=hash_password("test-pass"),
                is_admin=True,
                is_active=True,
                token_version=0,
            )

        app.dependency_overrides[get_current_user] = _mock_get_current_user
        yield
        app.dependency_overrides.pop(get_current_user, None)
    else:
        yield


@pytest.fixture
def client() -> TestClient:
    """FastAPI 应用 TestClient，用于集成测试。"""
    if app is None:
        pytest.skip("FastAPI app 依赖未满足（例如缺少 langgraph），跳过需要 client 的集成测试。")
    return TestClient(app)


def pytest_configure(config: pytest.Config) -> None:
    """为轻量测试环境补齐 asyncio marker。"""
    config.addinivalue_line("markers", "asyncio: mark test as asyncio coroutine")


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """在未安装 pytest-asyncio 的环境中兜底执行 async 测试。"""

    if not inspect.iscoroutinefunction(pyfuncitem.obj):
        return None

    funcargs = {
        arg: pyfuncitem.funcargs[arg]
        for arg in pyfuncitem._fixtureinfo.argnames
        if arg in pyfuncitem.funcargs
    }
    asyncio.run(pyfuncitem.obj(**funcargs))
    return True
