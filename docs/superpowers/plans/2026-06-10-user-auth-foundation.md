# 用户认证闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Jellyfish 引入 JWT 双令牌认证：后端新增 `User` 模型与登录/刷新/当前用户接口，所有现有业务路由要求登录；前端新增登录页、认证状态管理、路由守卫与导航栏退出登录。

**Architecture:** 后端在 `app/models/user.py` 新增 `User` 表（含 `token_version` 用于即时吊销），`app/core/security.py` 提供密码哈希与 JWT 编解码，`app/services/auth.py` 封装登录/刷新业务逻辑，`app/dependencies.py` 新增 `get_current_user`/`require_admin` 依赖并在 `app/api/v1/__init__.py` 以 `dependencies=[...]` 方式挂到除 `/auth/*` 与 `/health` 外的所有路由组。应用启动时通过 `app/bootstrap.py` 的 `seed_initial_admin()` 幂等播种初始管理员。前端新增 `useAuthStore`（Zustand）管理 token/用户态，`services/openapi.ts` 注入 `Authorization` 头并在收到 401 时自动用 refresh_token 重试一次，新增 `LoginPage` 与 `PrivateRoute`，`MainLayout` 改为展示真实登录用户并接入退出登录。

**Tech Stack:** FastAPI + SQLAlchemy(async) + SQLite(测试)/MySQL；`pyjwt` + `bcrypt`；React + Zustand + Ant Design + react-router-dom；OpenAPI 生成客户端（`openapi-typescript-codegen`）。

**本计划范围（不含）：** 11 张业务表的 `user_id` 隔离、service 层按用户过滤、`model_settings` 单例改造、管理员用户管理 API 与前端管理页面 —— 这些在后续的「数据隔离与管理员管理」计划中实现。完成本计划后，**所有登录用户仍能看到全部数据**（尚未隔离），但访问任意业务接口都必须携带有效 `access_token`。

参考设计文档：`docs/superpowers/specs/2026-06-09-user-management-design.md`

---

## File Structure

**新增（后端）：**
- `backend/app/models/user.py` — `User` ORM 模型
- `backend/app/core/security.py` — 密码哈希、JWT 生成/校验
- `backend/app/schemas/auth.py` — 登录/刷新/当前用户的 Pydantic Schema
- `backend/app/services/auth.py` — 认证业务逻辑（登录校验、刷新令牌）
- `backend/app/api/v1/routes/auth.py` — `/auth/login` `/auth/refresh` `/auth/me`
- `backend/tests/test_user_model.py`
- `backend/tests/test_security.py`
- `backend/tests/test_auth_schemas.py`
- `backend/tests/test_auth_service.py`
- `backend/tests/test_auth_dependencies.py`
- `backend/tests/test_auth_api.py`
- `backend/tests/test_bootstrap_seed_admin.py`

**修改（后端）：**
- `backend/pyproject.toml` — 新增 `pyjwt`、`bcrypt` 依赖
- `backend/.env.example` — 新增 JWT / 初始管理员环境变量说明
- `backend/app/config.py` — 新增 JWT 与初始管理员配置项
- `backend/app/models/__init__.py` — 注册 `User`
- `backend/app/core/db.py` — `init_db()` 中导入 `app.models.user`
- `backend/app/dependencies.py` — 新增 `get_current_user` / `require_admin`
- `backend/app/api/v1/__init__.py` — 注册 `auth` 路由 + 给其余路由组加鉴权依赖
- `backend/app/bootstrap.py` — 新增 `seed_initial_admin()`
- `backend/app/main.py` — lifespan 中调用 `seed_initial_admin()`

**新增（前端）：**
- `front/src/store/useAuthStore.ts` — 认证状态（token/用户/登录/登出/刷新/初始化）
- `front/src/pages/auth/LoginPage.tsx` — 登录页
- `front/src/components/PrivateRoute.tsx` — 路由守卫

**修改（前端）：**
- `front/src/services/openapi.ts` — 注入 `Authorization` 头 + 401 自动刷新重试
- `front/src/App.tsx` — 新增 `/login` 路由 + `PrivateRoute` 包裹现有路由
- `front/src/layouts/MainLayout.tsx` — 展示真实登录用户、接入退出登录
- `front/src/services/generated/**` — 由 `pnpm run openapi:update` 重新生成

---

## Task 1: 新增 JWT / 密码哈希依赖

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: 在依赖列表中新增 pyjwt 与 bcrypt**

打开 `backend/pyproject.toml`，找到 `dependencies = [...]` 数组中的最后一项 `"jinja2",`，在其后新增两行：

```toml
    "jinja2",
    "pyjwt>=2.9.0",
    "bcrypt>=4.2.0",
]
```

- [ ] **Step 2: 同步依赖**

```bash
cd backend
uv sync
```

Expected: 安装成功，无报错。

- [ ] **Step 3: 验证可导入**

```bash
uv run python -c "import jwt, bcrypt; print('ok')"
```

Expected: 输出 `ok`。

- [ ] **Step 4: Commit**

```bash
cd backend
git add pyproject.toml uv.lock
git commit -m "chore: add pyjwt and bcrypt dependencies for auth"
```

---

## Task 2: 新增认证相关配置项

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: 在 Settings 中新增 JWT 与初始管理员配置**

打开 `backend/app/config.py`，在以下代码：

```python
    # Database
    database_url: str = "sqlite+aiosqlite:///./jellyfish.db"

    # Redis / Celery Broker
```

中间插入新字段，改为：

```python
    # Database
    database_url: str = "sqlite+aiosqlite:///./jellyfish.db"

    # JWT 认证
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # 初始管理员账号（仅在 users 表为空时用于播种）
    initial_admin_username: str = "admin"
    initial_admin_password: str | None = None

    # Redis / Celery Broker
```

- [ ] **Step 2: 更新 `.env.example`**

打开 `backend/.env.example`，在 `# 数据库（默认 SQLite 异步）` 小节之后新增：

```
# JWT 认证（生产环境务必修改 JWT_SECRET_KEY 为随机字符串）
JWT_SECRET_KEY=please-change-me-to-a-random-secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# 初始管理员账号（仅在 users 表为空时用于首次播种，必须设置密码，否则应用拒绝启动）
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=please-change-me
```

- [ ] **Step 3: 验证配置可读取**

```bash
cd backend
uv run python -c "from app.config import settings; print(settings.jwt_algorithm, settings.access_token_expire_minutes, settings.initial_admin_username)"
```

Expected: 输出 `HS256 15 admin`。

- [ ] **Step 4: Commit**

```bash
cd backend
git add app/config.py .env.example
git commit -m "feat: add JWT and initial admin configuration settings"
```

---

## Task 3: User ORM 模型

**Files:**
- Create: `backend/app/models/user.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/core/db.py`
- Test: `backend/tests/test_user_model.py`

- [ ] **Step 1: 编写失败测试**

创建 `backend/tests/test_user_model.py`：

```python
"""User 模型基础测试：建表、字段默认值与唯一约束。"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.user import User


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


@pytest.mark.asyncio
async def test_user_model_defaults() -> None:
    db, engine = await _build_session()
    async with db:
        user = User(id="u1", username="alice", hashed_password="hashed")
        db.add(user)
        await db.flush()
        await db.refresh(user)

        assert user.is_admin is False
        assert user.is_active is True
        assert user.token_version == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_username_unique_constraint() -> None:
    db, engine = await _build_session()
    async with db:
        db.add(User(id="u1", username="alice", hashed_password="hashed"))
        await db.flush()

        db.add(User(id="u2", username="alice", hashed_password="hashed2"))
        with pytest.raises(IntegrityError):
            await db.flush()
    await engine.dispose()
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend
uv run pytest tests/test_user_model.py -q
```

Expected: FAIL，提示 `ModuleNotFoundError: No module named 'app.models.user'`。

- [ ] **Step 3: 创建 User 模型**

创建 `backend/app/models/user.py`：

```python
"""用户账号模型。"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin


class User(Base, TimestampMixin):
    """用户账号。

    `token_version` 用于使已签发的 JWT 立即失效：管理员重置密码或禁用账号时递增该值，
    `get_current_user` 会校验 token 中的 `token_version` 与数据库当前值是否一致，
    不一致即视为该 token 已被吊销。
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="用户 ID")
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True, comment="用户名")
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False, comment="bcrypt 密码哈希")
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否管理员")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="令牌版本号，递增可使已签发 token 失效"
    )
```

- [ ] **Step 4: 注册到 `app/models/__init__.py`**

打开 `backend/app/models/__init__.py`，在：

```python
from app.models.task_links import GenerationTaskLink
from app.models.types import FileUsageKind
```

之后新增：

```python
from app.models.user import User
```

并在 `__all__` 列表末尾（`"GenerationTaskLink",` 之后）新增：

```python
    "User",
```

- [ ] **Step 5: 在 `init_db()` 中导入新模型**

打开 `backend/app/core/db.py`，找到：

```python
    import app.models.llm  # noqa: F401  # pylint: disable=unused-import
    import app.models.studio  # noqa: F401
    import app.models.task  # noqa: F401
    import app.models.task_links  # noqa: F401
```

新增一行：

```python
    import app.models.llm  # noqa: F401  # pylint: disable=unused-import
    import app.models.studio  # noqa: F401
    import app.models.task  # noqa: F401
    import app.models.task_links  # noqa: F401
    import app.models.user  # noqa: F401
```

- [ ] **Step 6: 运行测试，确认通过**

```bash
cd backend
uv run pytest tests/test_user_model.py -q
```

Expected: PASS（2 passed）。

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/models/user.py app/models/__init__.py app/core/db.py tests/test_user_model.py
git commit -m "feat: add User model"
```

---

## Task 4: 密码哈希与 JWT 工具

**Files:**
- Create: `backend/app/core/security.py`
- Test: `backend/tests/test_security.py`

- [ ] **Step 1: 编写失败测试**

创建 `backend/tests/test_security.py`：

```python
"""密码哈希与 JWT 编解码测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import settings
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_password_roundtrip() -> None:
    hashed = hash_password("s3cr3t")

    assert hashed != "s3cr3t"
    assert verify_password("s3cr3t", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_create_and_decode_access_token_roundtrip() -> None:
    token = create_access_token(user_id="user-1", token_version=2)

    payload = decode_token(token, expected_type="access")

    assert payload["sub"] == "user-1"
    assert payload["token_version"] == 2
    assert payload["type"] == "access"


def test_create_and_decode_refresh_token_roundtrip() -> None:
    token = create_refresh_token(user_id="user-1", token_version=0)

    payload = decode_token(token, expected_type="refresh")

    assert payload["sub"] == "user-1"
    assert payload["type"] == "refresh"


def test_decode_token_rejects_wrong_type() -> None:
    token = create_refresh_token(user_id="user-1", token_version=0)

    with pytest.raises(TokenError):
        decode_token(token, expected_type="access")


def test_decode_token_rejects_expired_token() -> None:
    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": "user-1",
        "token_version": 0,
        "type": "access",
        "iat": now - timedelta(hours=1),
        "exp": now - timedelta(minutes=1),
    }
    token = jwt.encode(expired_payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    with pytest.raises(TokenError):
        decode_token(token, expected_type="access")


def test_decode_token_rejects_tampered_token() -> None:
    token = create_access_token(user_id="user-1", token_version=0)

    with pytest.raises(TokenError):
        decode_token(token + "tampered", expected_type="access")
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend
uv run pytest tests/test_security.py -q
```

Expected: FAIL，提示 `ModuleNotFoundError: No module named 'app.core.security'`。

- [ ] **Step 3: 实现 security.py**

创建 `backend/app/core/security.py`：

```python
"""密码哈希与 JWT 令牌的生成、校验。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt

from app.config import settings

TokenType = Literal["access", "refresh"]


class TokenError(Exception):
    """JWT 解析或校验失败（签名无效、已过期、类型不匹配等）。"""


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """校验明文密码与已存储哈希是否匹配。"""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _create_token(*, user_id: str, token_version: int, token_type: TokenType, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "token_version": token_version,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(*, user_id: str, token_version: int) -> str:
    """生成短期 access token（默认 15 分钟）。"""
    return _create_token(
        user_id=user_id,
        token_version=token_version,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(*, user_id: str, token_version: int) -> str:
    """生成长期 refresh token（默认 7 天）。"""
    return _create_token(
        user_id=user_id,
        token_version=token_version,
        token_type="refresh",
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """解析并校验 JWT，类型不匹配或签名/过期校验失败均抛出 `TokenError`。"""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if payload.get("type") != expected_type:
        raise TokenError(f"unexpected token type: {payload.get('type')!r}")
    return payload
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend
uv run pytest tests/test_security.py -q
```

Expected: PASS（6 passed）。

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/core/security.py tests/test_security.py
git commit -m "feat: add password hashing and JWT helpers"
```

---

## Task 5: 认证 Schema

**Files:**
- Create: `backend/app/schemas/auth.py`
- Test: `backend/tests/test_auth_schemas.py`

- [ ] **Step 1: 编写失败测试**

创建 `backend/tests/test_auth_schemas.py`：

```python
"""认证 Schema 校验测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RefreshRequest, TokenPairRead, UserRead


def test_login_request_accepts_valid_payload() -> None:
    req = LoginRequest(username="admin", password="secret")

    assert req.username == "admin"
    assert req.password == "secret"


def test_login_request_rejects_empty_username() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(username="", password="secret")


def test_refresh_request_requires_token() -> None:
    with pytest.raises(ValidationError):
        RefreshRequest()  # type: ignore[call-arg]


def test_token_pair_read_defaults_token_type_to_bearer() -> None:
    pair = TokenPairRead(access_token="a", refresh_token="b")

    assert pair.token_type == "bearer"


def test_user_read_from_attributes() -> None:
    class _FakeUser:
        id = "u1"
        username = "alice"
        is_admin = False
        is_active = True

    data = UserRead.model_validate(_FakeUser())

    assert data.id == "u1"
    assert data.username == "alice"
    assert data.is_admin is False
    assert data.is_active is True
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend
uv run pytest tests/test_auth_schemas.py -q
```

Expected: FAIL，提示 `ModuleNotFoundError: No module named 'app.schemas.auth'`。

- [ ] **Step 3: 创建 Schema**

创建 `backend/app/schemas/auth.py`：

```python
"""认证相关请求/响应 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """登录请求体。"""

    username: str = Field(..., min_length=1, description="用户名")
    password: str = Field(..., min_length=1, description="密码")


class RefreshRequest(BaseModel):
    """刷新令牌请求体。"""

    refresh_token: str = Field(..., min_length=1, description="刷新令牌")


class TokenPairRead(BaseModel):
    """登录成功返回的令牌对。"""

    access_token: str = Field(..., description="短期访问令牌")
    refresh_token: str = Field(..., description="长期刷新令牌")
    token_type: str = Field("bearer", description="令牌类型")


class AccessTokenRead(BaseModel):
    """刷新接口返回的新 access token。"""

    access_token: str = Field(..., description="新的访问令牌")
    token_type: str = Field("bearer", description="令牌类型")


class UserRead(BaseModel):
    """当前用户信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")
    is_admin: bool = Field(..., description="是否管理员")
    is_active: bool = Field(..., description="是否启用")
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend
uv run pytest tests/test_auth_schemas.py -q
```

Expected: PASS（5 passed）。

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/schemas/auth.py tests/test_auth_schemas.py
git commit -m "feat: add auth request/response schemas"
```

---

## Task 6: 认证 Service

**Files:**
- Create: `backend/app/services/auth.py`
- Test: `backend/tests/test_auth_service.py`

- [ ] **Step 1: 编写失败测试**

创建 `backend/tests/test_auth_service.py`：

```python
"""认证 Service 测试：登录校验与令牌刷新。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.core.security import hash_password
from app.models.user import User
from app.services import auth as auth_service


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


async def _seed_user(db: AsyncSession, **overrides: object) -> User:
    defaults: dict[str, object] = dict(
        id="user-1",
        username="alice",
        hashed_password=hash_password("s3cr3t"),
        is_admin=False,
        is_active=True,
        token_version=0,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_authenticate_success_returns_token_pair() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_user(db)

        tokens = await auth_service.authenticate(db, username="alice", password="s3cr3t")

        assert tokens.access_token
        assert tokens.refresh_token
    await engine.dispose()


@pytest.mark.asyncio
async def test_authenticate_wrong_password_raises() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_user(db)

        with pytest.raises(auth_service.InvalidCredentialsError):
            await auth_service.authenticate(db, username="alice", password="wrong")
    await engine.dispose()


@pytest.mark.asyncio
async def test_authenticate_unknown_username_raises() -> None:
    db, engine = await _build_session()
    async with db:
        with pytest.raises(auth_service.InvalidCredentialsError):
            await auth_service.authenticate(db, username="nobody", password="s3cr3t")
    await engine.dispose()


@pytest.mark.asyncio
async def test_authenticate_inactive_user_raises() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_user(db, is_active=False)

        with pytest.raises(auth_service.InvalidCredentialsError):
            await auth_service.authenticate(db, username="alice", password="s3cr3t")
    await engine.dispose()


@pytest.mark.asyncio
async def test_refresh_access_token_success() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_user(db)
        tokens = await auth_service.authenticate(db, username="alice", password="s3cr3t")

        result = await auth_service.refresh_access_token(db, refresh_token=tokens.refresh_token)

        assert result.access_token
    await engine.dispose()


@pytest.mark.asyncio
async def test_refresh_access_token_revoked_raises() -> None:
    db, engine = await _build_session()
    async with db:
        user = await _seed_user(db)
        tokens = await auth_service.authenticate(db, username="alice", password="s3cr3t")

        user.token_version += 1
        await db.flush()

        with pytest.raises(auth_service.InvalidTokenError):
            await auth_service.refresh_access_token(db, refresh_token=tokens.refresh_token)
    await engine.dispose()


@pytest.mark.asyncio
async def test_refresh_access_token_invalid_token_raises() -> None:
    db, engine = await _build_session()
    async with db:
        with pytest.raises(auth_service.InvalidTokenError):
            await auth_service.refresh_access_token(db, refresh_token="not-a-token")
    await engine.dispose()
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend
uv run pytest tests/test_auth_service.py -q
```

Expected: FAIL，提示 `ModuleNotFoundError: No module named 'app.services.auth'`。

- [ ] **Step 3: 实现 auth service**

创建 `backend/app/services/auth.py`：

```python
"""认证业务逻辑：登录校验、令牌签发与刷新。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import AccessTokenRead, TokenPairRead


class InvalidCredentialsError(Exception):
    """用户名或密码错误，或账号已被禁用。"""


class InvalidTokenError(Exception):
    """令牌无效、已过期或已被吊销。"""


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    """按 ID 查询用户。"""
    return await db.get(User, user_id)


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    """按用户名查询用户。"""
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def authenticate(db: AsyncSession, *, username: str, password: str) -> TokenPairRead:
    """校验用户名密码并签发令牌对；用户不存在/密码错误/账号禁用均报 `InvalidCredentialsError`。"""
    user = await get_user_by_username(db, username)
    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        raise InvalidCredentialsError("invalid username or password")
    return TokenPairRead(
        access_token=create_access_token(user_id=user.id, token_version=user.token_version),
        refresh_token=create_refresh_token(user_id=user.id, token_version=user.token_version),
    )


async def refresh_access_token(db: AsyncSession, *, refresh_token: str) -> AccessTokenRead:
    """用 refresh token 换取新的 access token；token 失效/已吊销均报 `InvalidTokenError`。"""
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise InvalidTokenError(str(exc)) from exc

    user = await get_user_by_id(db, payload["sub"])
    if user is None or not user.is_active or user.token_version != payload["token_version"]:
        raise InvalidTokenError("user inactive or token revoked")

    return AccessTokenRead(access_token=create_access_token(user_id=user.id, token_version=user.token_version))
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend
uv run pytest tests/test_auth_service.py -q
```

Expected: PASS（7 passed）。

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/services/auth.py tests/test_auth_service.py
git commit -m "feat: add auth service for login and token refresh"
```

---

## Task 7: `get_current_user` / `require_admin` 依赖

**Files:**
- Modify: `backend/app/dependencies.py`
- Test: `backend/tests/test_auth_dependencies.py`

- [ ] **Step 1: 编写失败测试**

创建 `backend/tests/test_auth_dependencies.py`：

```python
"""get_current_user / require_admin 依赖测试。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.core.security import create_access_token, hash_password
from app.dependencies import get_current_user, get_db, require_admin
from app.models.user import User


def _build_test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    async def protected(current_user: User = Depends(get_current_user)) -> dict[str, str]:
        return {"user_id": current_user.id}

    @app.get("/admin-only")
    async def admin_only(current_user: User = Depends(require_admin)) -> dict[str, str]:
        return {"user_id": current_user.id}

    return app


@pytest.fixture
def auth_test_client() -> TestClient:
    app = _build_test_app()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_local() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_local() as session:
            session.add(
                User(id="u1", username="alice", hashed_password=hash_password("pw"), is_admin=False, is_active=True, token_version=0)
            )
            session.add(
                User(id="u2", username="bob", hashed_password=hash_password("pw"), is_admin=True, is_active=True, token_version=0)
            )
            session.add(
                User(id="u3", username="carol", hashed_password=hash_password("pw"), is_admin=False, is_active=False, token_version=5)
            )
            await session.commit()

    asyncio.run(_setup())

    return TestClient(app)


def test_protected_without_token_returns_401(auth_test_client: TestClient) -> None:
    resp = auth_test_client.get("/protected")

    assert resp.status_code == 401


def test_protected_with_invalid_token_returns_401(auth_test_client: TestClient) -> None:
    resp = auth_test_client.get("/protected", headers={"Authorization": "Bearer not-a-token"})

    assert resp.status_code == 401


def test_protected_with_valid_token_returns_user(auth_test_client: TestClient) -> None:
    token = create_access_token(user_id="u1", token_version=0)

    resp = auth_test_client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json()["user_id"] == "u1"


def test_protected_with_inactive_user_returns_401(auth_test_client: TestClient) -> None:
    token = create_access_token(user_id="u3", token_version=5)

    resp = auth_test_client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401


def test_admin_only_rejects_non_admin(auth_test_client: TestClient) -> None:
    token = create_access_token(user_id="u1", token_version=0)

    resp = auth_test_client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 403


def test_admin_only_allows_admin(auth_test_client: TestClient) -> None:
    token = create_access_token(user_id="u2", token_version=0)

    resp = auth_test_client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend
uv run pytest tests/test_auth_dependencies.py -q
```

Expected: FAIL，提示 `ImportError: cannot import name 'get_current_user' from 'app.dependencies'`。

- [ ] **Step 3: 实现依赖**

打开 `backend/app/dependencies.py`，将顶部导入：

```python
from fastapi import Depends, HTTPException
```

改为：

```python
from fastapi import Depends, Header, HTTPException, status
```

并新增：

```python
from app.core.security import TokenError, decode_token
from app.models.user import User
```

在 `get_db` 函数之后（`get_llm` 之前）新增：

```python
async def get_current_user(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 `Authorization: Bearer <token>` 解析并校验当前登录用户。

    校验项：access token 签名/类型/未过期，以及 DB 中 `is_active` 与 `token_version`
    与 token 一致（不一致代表账号已被禁用或密码已重置，旧 token 视为吊销）。
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token, expected_type="access")
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token") from exc

    user = await db.get(User, payload["sub"])
    if user is None or not user.is_active or user.token_version != payload["token_version"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user inactive or token revoked")
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """要求当前用户具备管理员权限，否则返回 403。"""
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin privileges required")
    return current_user
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend
uv run pytest tests/test_auth_dependencies.py -q
```

Expected: PASS（6 passed）。

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/dependencies.py tests/test_auth_dependencies.py
git commit -m "feat: add get_current_user and require_admin dependencies"
```

---

## Task 8: 认证路由 + 全局鉴权挂载

**Files:**
- Create: `backend/app/api/v1/routes/auth.py`
- Modify: `backend/app/api/v1/__init__.py`
- Test: `backend/tests/test_auth_api.py`

- [ ] **Step 1: 编写失败测试**

创建 `backend/tests/test_auth_api.py`：

```python
"""认证 API 测试：登录、刷新、当前用户信息，以及全局鉴权挂载。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.core.security import hash_password
from app.dependencies import get_db
from app.main import app
from app.models.user import User


@pytest.fixture
def auth_client() -> TestClient:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_local() as session:
            session.add(
                User(
                    id="admin-1",
                    username="admin",
                    hashed_password=hash_password("admin-pass"),
                    is_admin=True,
                    is_active=True,
                    token_version=0,
                )
            )
            await session.commit()

    asyncio.run(_setup())

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_local() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_login_success_returns_token_pair(auth_client: TestClient) -> None:
    resp = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-pass"})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["access_token"]
    assert data["refresh_token"]


def test_login_wrong_password_returns_401(auth_client: TestClient) -> None:
    resp = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})

    assert resp.status_code == 401


def test_me_with_valid_token_returns_user(auth_client: TestClient) -> None:
    login_resp = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-pass"})
    access_token = login_resp.json()["data"]["access_token"]

    resp = auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})

    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "admin"


def test_refresh_returns_new_access_token(auth_client: TestClient) -> None:
    login_resp = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-pass"})
    refresh_token = login_resp.json()["data"]["refresh_token"]

    resp = auth_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

    assert resp.status_code == 200
    assert resp.json()["data"]["access_token"]


def test_protected_route_without_token_returns_401(auth_client: TestClient) -> None:
    resp = auth_client.get("/api/v1/studio/projects")

    assert resp.status_code == 401


def test_protected_route_with_valid_token_succeeds(auth_client: TestClient) -> None:
    login_resp = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-pass"})
    access_token = login_resp.json()["data"]["access_token"]

    resp = auth_client.get("/api/v1/studio/projects", headers={"Authorization": f"Bearer {access_token}"})

    assert resp.status_code == 200
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend
uv run pytest tests/test_auth_api.py -q
```

Expected: FAIL —— `/api/v1/auth/login` 返回 404（路由不存在），且 `/api/v1/studio/projects` 无 token 时返回 200 而非 401。

- [ ] **Step 3: 创建认证路由**

创建 `backend/app/api/v1/routes/auth.py`：

```python
"""认证相关端点：登录、刷新令牌、获取当前用户信息。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import AccessTokenRead, LoginRequest, RefreshRequest, TokenPairRead, UserRead
from app.schemas.common import ApiResponse, success_response
from app.services import auth as auth_service

router = APIRouter()


@router.post("/login", response_model=ApiResponse[TokenPairRead], summary="登录")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> ApiResponse[TokenPairRead]:
    try:
        tokens = await auth_service.authenticate(db, username=body.username, password=body.password)
    except auth_service.InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid username or password") from exc
    return success_response(tokens)


@router.post("/refresh", response_model=ApiResponse[AccessTokenRead], summary="刷新 access token")
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> ApiResponse[AccessTokenRead]:
    try:
        token = await auth_service.refresh_access_token(db, refresh_token=body.refresh_token)
    except auth_service.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired refresh token") from exc
    return success_response(token)


@router.get("/me", response_model=ApiResponse[UserRead], summary="获取当前用户信息")
async def get_me(current_user: User = Depends(get_current_user)) -> ApiResponse[UserRead]:
    return success_response(UserRead.model_validate(current_user))
```

- [ ] **Step 4: 注册路由并为其余路由组挂上鉴权依赖**

打开 `backend/app/api/v1/__init__.py`，整体替换为：

```python
"""API v1 路由聚合。"""

from fastapi import APIRouter, Depends

from app.api.v1.routes import auth, film, health, llm, studio, script_processing
from app.dependencies import get_current_user

router = APIRouter()

router.include_router(health.router, tags=["health"])
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(film.router, prefix="/film", tags=["film"], dependencies=[Depends(get_current_user)])
router.include_router(llm.router, prefix="/llm", tags=["llm"], dependencies=[Depends(get_current_user)])
router.include_router(studio.router, prefix="/studio", dependencies=[Depends(get_current_user)])
router.include_router(script_processing.router, dependencies=[Depends(get_current_user)])
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
cd backend
uv run pytest tests/test_auth_api.py -q
```

Expected: PASS（6 passed）。

- [ ] **Step 6: 运行已有测试套件，确认未破坏现有接口**

```bash
cd backend
uv run pytest -q
```

Expected: 全部通过。如有既有测试因新增鉴权而 401（直接调用 `app.main.app` 且未走 `get_db` override 的测试一般不受影响，因为它们也未携带 token——若出现因 401 失败的既有测试，逐个检查是否需要在该测试里补充 `Authorization` 头或 `app.dependency_overrides[get_current_user]`）。

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/api/v1/routes/auth.py app/api/v1/__init__.py tests/test_auth_api.py
git commit -m "feat: add auth endpoints and require login on all business routes"
```

---

## Task 9: 初始管理员播种

**Files:**
- Modify: `backend/app/bootstrap.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_bootstrap_seed_admin.py`

- [ ] **Step 1: 编写失败测试**

创建 `backend/tests/test_bootstrap_seed_admin.py`：

```python
"""初始管理员播种测试：幂等创建、已存在时跳过、未配置密码时拒绝。"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.bootstrap import seed_initial_admin
from app.config import settings
from app.core.db import Base
from app.models.user import User


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


@pytest.mark.asyncio
async def test_seed_creates_admin_when_none_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "initial_admin_password", "init-pass")
    monkeypatch.setattr(settings, "initial_admin_username", "admin")
    db, engine = await _build_session()
    async with db:
        await seed_initial_admin(db)

        result = await db.execute(select(User).where(User.is_admin.is_(True)))
        admin = result.scalars().one()
        assert admin.username == "admin"
    await engine.dispose()


@pytest.mark.asyncio
async def test_seed_is_idempotent_when_admin_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "initial_admin_password", "init-pass")
    db, engine = await _build_session()
    async with db:
        await seed_initial_admin(db)
        await seed_initial_admin(db)

        result = await db.execute(select(User).where(User.is_admin.is_(True)))
        admins = result.scalars().all()
        assert len(admins) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_seed_raises_when_password_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "initial_admin_password", None)
    db, engine = await _build_session()
    async with db:
        with pytest.raises(RuntimeError):
            await seed_initial_admin(db)
    await engine.dispose()
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend
uv run pytest tests/test_bootstrap_seed_admin.py -q
```

Expected: FAIL，提示 `ImportError: cannot import name 'seed_initial_admin' from 'app.bootstrap'`。

- [ ] **Step 3: 实现 seed_initial_admin**

打开 `backend/app/bootstrap.py`，整体替换为：

```python
"""应用级注册入口：统一初始化供应商能力、任务执行器与初始管理员账号（均幂等）。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import hash_password
from app.models.user import User


def bootstrap_all_registries() -> None:
    """启动时或惰性路径中调用一次即可；顺序固定为 provider 先于 task adapter。"""
    from app.core.tasks.bootstrap import bootstrap_task_adapters
    from app.services.llm.provider_bootstrap import bootstrap_builtin_providers

    bootstrap_builtin_providers()
    bootstrap_task_adapters()


async def seed_initial_admin(db: AsyncSession) -> None:
    """若数据库中尚无管理员账号，按配置创建初始管理员（幂等）。

    `INITIAL_ADMIN_PASSWORD` 未设置时抛出 `RuntimeError`，阻止应用在缺少初始密码的
    情况下启动，避免生产环境出现默认弱密码账号。
    """
    existing = await db.execute(select(User).where(User.is_admin.is_(True)))
    if existing.scalars().first() is not None:
        return

    if not settings.initial_admin_password:
        raise RuntimeError(
            "INITIAL_ADMIN_PASSWORD is not set; refusing to start without an initial admin account"
        )

    admin = User(
        id=str(uuid.uuid4()),
        username=settings.initial_admin_username,
        hashed_password=hash_password(settings.initial_admin_password),
        is_admin=True,
        is_active=True,
    )
    db.add(admin)
    await db.commit()
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend
uv run pytest tests/test_bootstrap_seed_admin.py -q
```

Expected: PASS（3 passed）。

- [ ] **Step 5: 接入应用启动流程**

打开 `backend/app/main.py`，将：

```python
from app.api.v1 import router as api_v1_router
from app.bootstrap import bootstrap_all_registries
from app.config import settings
from app.core.db import close_db, init_db
from app.schemas.common import ApiResponse
```

改为：

```python
from app.api.v1 import router as api_v1_router
from app.bootstrap import bootstrap_all_registries, seed_initial_admin
from app.config import settings
from app.core.db import async_session_maker, close_db, init_db
from app.schemas.common import ApiResponse
```

并将 `lifespan` 函数：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化，关闭时清理。"""
    await init_db()
    bootstrap_all_registries()
    yield
    await close_db()
```

改为：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化，关闭时清理。"""
    await init_db()
    async with async_session_maker() as db:
        await seed_initial_admin(db)
    bootstrap_all_registries()
    yield
    await close_db()
```

- [ ] **Step 6: 在本地 `.env` 中配置初始管理员密码与 JWT 密钥**

后续启动开发服务器（`uv run uvicorn app.main:app --reload ...`）会触发上面的 `seed_initial_admin`，若 `INITIAL_ADMIN_PASSWORD` 未设置会直接抛错导致启动失败。在 `backend/.env`（如不存在则从 `.env.example` 复制）中设置：

```
JWT_SECRET_KEY=<任意随机字符串，本地开发可用 dev-secret-key>
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=<本地开发密码，例如 admin123456>
```

- [ ] **Step 7: 运行完整测试套件**

```bash
cd backend
uv run pytest -q
```

Expected: 全部通过。

- [ ] **Step 8: Commit**

```bash
cd backend
git add app/bootstrap.py app/main.py tests/test_bootstrap_seed_admin.py
git commit -m "feat: seed initial admin user on application startup"
```

> 注意：不要提交本地 `backend/.env`（该文件已在 `.gitignore` 中）。

---

## Task 10: 后端语法与 Lint 检查

**Files:** 无新增/修改，仅校验 Task 1-9 的产出。

- [ ] **Step 1: 运行完整测试套件**

```bash
cd backend
uv run pytest -q
```

Expected: 全部通过。

- [ ] **Step 2: 对新增/修改的模块运行 pylint**

```bash
cd backend
uv run pylint app/models/user.py app/core/security.py app/schemas/auth.py app/services/auth.py app/api/v1/routes/auth.py app/dependencies.py app/bootstrap.py app/main.py app/config.py app/api/v1/__init__.py app/core/db.py app/models/__init__.py
```

Expected: 无 error 级别问题（warning/convention 若与既有代码风格一致可接受）。若有问题，按既有代码风格修复后重新运行 Step 1 确认未破坏测试。

---

## Task 11: 重新生成前端 OpenAPI 客户端

**Files:**
- Regenerate: `front/src/services/generated/**`
- Regenerate: `front/openapi.json`

- [ ] **Step 1: 启动后端开发服务器**

新开一个终端：

```bash
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Expected: 日志显示 `Application startup complete`，无 `RuntimeError: INITIAL_ADMIN_PASSWORD is not set` 报错（若报错，回到 Task 9 Step 6 检查 `.env`）。

- [ ] **Step 2: 重新生成客户端**

```bash
cd front
pnpm run openapi:update
```

- [ ] **Step 3: 验证生成了 AuthService**

```bash
cd front
ls src/services/generated/services/ | grep -i auth
grep -E "public static (login|refresh|getMe)" src/services/generated/services/AuthService.ts
```

Expected: 存在 `AuthService.ts`，且包含三个方法，方法名分别为
`loginApiV1AuthLoginPost`、`refreshApiV1AuthRefreshPost`、`getMeApiV1AuthMeGet`
（若实际生成的方法名与此不同，以生成结果为准，并相应调整 Task 12 中 `useAuthStore.ts` 的方法名）。

- [ ] **Step 4: 类型检查**

```bash
cd front
pnpm exec tsc --noEmit
```

Expected: 通过（无新增类型错误）。

- [ ] **Step 5: Commit**

```bash
cd front
git add openapi.json src/services/generated
git commit -m "chore: regenerate OpenAPI client with auth endpoints"
```

---

## Task 12: 前端认证状态管理 `useAuthStore`

**Files:**
- Create: `front/src/store/useAuthStore.ts`

- [ ] **Step 1: 创建 useAuthStore**

创建 `front/src/store/useAuthStore.ts`：

```ts
import { create } from 'zustand'
import { AuthService } from '../services/generated'
import type { UserRead } from '../services/generated'

const REFRESH_TOKEN_KEY = 'jellyfish_refresh_token'

type AuthStatus = 'idle' | 'authenticated' | 'unauthenticated'

interface AuthState {
  status: AuthStatus
  user: UserRead | null
  accessToken: string | null
  refreshToken: string | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  refreshAccessToken: () => Promise<string | null>
  initialize: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set, get) => ({
  status: 'idle',
  user: null,
  accessToken: null,
  refreshToken: localStorage.getItem(REFRESH_TOKEN_KEY),

  login: async (username, password) => {
    const res = await AuthService.loginApiV1AuthLoginPost({ requestBody: { username, password } })
    const tokens = res.data
    if (!tokens) {
      throw new Error('登录响应缺少令牌')
    }
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
    set({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token })

    const me = await AuthService.getMeApiV1AuthMeGet()
    set({ user: me.data ?? null, status: 'authenticated' })
  },

  logout: () => {
    localStorage.removeItem(REFRESH_TOKEN_KEY)
    set({ user: null, accessToken: null, refreshToken: null, status: 'unauthenticated' })
  },

  refreshAccessToken: async () => {
    const refreshToken = get().refreshToken
    if (!refreshToken) {
      get().logout()
      return null
    }
    try {
      const res = await AuthService.refreshApiV1AuthRefreshPost({ requestBody: { refresh_token: refreshToken } })
      const accessToken = res.data?.access_token
      if (!accessToken) {
        throw new Error('刷新响应缺少 access_token')
      }
      set({ accessToken })
      return accessToken
    } catch {
      get().logout()
      return null
    }
  },

  initialize: async () => {
    const refreshToken = get().refreshToken
    if (!refreshToken) {
      set({ status: 'unauthenticated' })
      return
    }
    const accessToken = await get().refreshAccessToken()
    if (!accessToken) {
      return
    }
    try {
      const me = await AuthService.getMeApiV1AuthMeGet()
      set({ user: me.data ?? null, status: 'authenticated' })
    } catch {
      get().logout()
    }
  },
}))
```

> 若 Task 11 Step 3 中实际生成的方法名与 `loginApiV1AuthLoginPost` / `refreshApiV1AuthRefreshPost` / `getMeApiV1AuthMeGet` 不同，请用实际名称替换上述三处调用。

- [ ] **Step 2: 类型检查**

```bash
cd front
pnpm exec tsc --noEmit
```

Expected: 通过。

- [ ] **Step 3: Commit**

```bash
cd front
git add src/store/useAuthStore.ts
git commit -m "feat: add useAuthStore for token and user session management"
```

---

## Task 13: OpenAPI 客户端注入 token 与 401 自动刷新

**Files:**
- Modify: `front/src/services/openapi.ts`

- [ ] **Step 1: 改写 openapi.ts**

打开 `front/src/services/openapi.ts`，整体替换为：

```ts
import { OpenAPI } from './generated'
import { useAuthStore } from '../store/useAuthStore'

declare global {
  interface Window {
    __ENV?: {
      BACKEND_URL?: string
    }
  }
}

/**
 * 初始化由 OpenAPI 生成的请求客户端。
 *
 * 说明：
 * - 生成接口的路径已包含 `/api/v1/...`，因此 BASE 默认应为空串（同源）或完整后端地址。
 * - 本地开发默认直连 `http://localhost:8000`。
 * - TOKEN 配置为 resolver，每次请求时从 useAuthStore 读取当前 access token。
 */
export function initOpenAPI(base: string = '') {
  OpenAPI.BASE = base
  OpenAPI.TOKEN = async () => useAuthStore.getState().accessToken ?? ''
}

const AUTH_PATH_SEGMENT = '/api/v1/auth/'

/**
 * 全局拦截 fetch：access token 过期（401）时，先用 refresh token 换取新 access token
 * 并重试一次；刷新失败则维持原始 401（由路由守卫跳转登录页）。
 * 不拦截 /api/v1/auth/* 自身的请求，避免刷新接口失败时递归重试。
 */
function installFetchInterceptor() {
  const originalFetch = window.fetch.bind(window)

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await originalFetch(input, init)

    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
    if (response.status === 401 && !url.includes(AUTH_PATH_SEGMENT)) {
      const newToken = await useAuthStore.getState().refreshAccessToken()
      if (newToken) {
        const retryHeaders = new Headers(init?.headers)
        retryHeaders.set('Authorization', `Bearer ${newToken}`)
        return originalFetch(input, { ...init, headers: retryHeaders })
      }
    }

    return response
  }
}

const runtimeBackendUrl = window.__ENV?.BACKEND_URL
const buildtimeBackendUrl = import.meta.env.VITE_BACKEND_URL
const defaultBackendUrl = 'http://localhost:8000'

initOpenAPI(runtimeBackendUrl ?? buildtimeBackendUrl ?? defaultBackendUrl)
installFetchInterceptor()
```

- [ ] **Step 2: 类型检查**

```bash
cd front
pnpm exec tsc --noEmit
```

Expected: 通过。

- [ ] **Step 3: Commit**

```bash
cd front
git add src/services/openapi.ts
git commit -m "feat: inject auth token into API client and auto-refresh on 401"
```

---

## Task 14: 登录页 `LoginPage`

**Files:**
- Create: `front/src/pages/auth/LoginPage.tsx`

- [ ] **Step 1: 创建 LoginPage**

创建 `front/src/pages/auth/LoginPage.tsx`：

```tsx
import { useState } from 'react'
import type React from 'react'
import { Button, Card, Form, Input, message } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { useLocation, useNavigate, type Location } from 'react-router-dom'
import { useAuthStore } from '../../store/useAuthStore'

interface LoginFormValues {
  username: string
  password: string
}

const LoginPage: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const login = useAuthStore((state) => state.login)
  const [submitting, setSubmitting] = useState(false)

  const handleFinish = async (values: LoginFormValues) => {
    setSubmitting(true)
    try {
      await login(values.username, values.password)
      const from = (location.state as { from?: Location } | null)?.from?.pathname ?? '/projects'
      navigate(from, { replace: true })
    } catch {
      message.error('用户名或密码错误')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex items-center justify-center h-screen bg-gray-50">
      <Card title="Jellyfish 登录" style={{ width: 360 }}>
        <Form layout="vertical" onFinish={handleFinish}>
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" autoComplete="current-password" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={submitting}>
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}

export default LoginPage
```

- [ ] **Step 2: 类型检查**

```bash
cd front
pnpm exec tsc --noEmit
```

Expected: 通过。

- [ ] **Step 3: Commit**

```bash
cd front
git add src/pages/auth/LoginPage.tsx
git commit -m "feat: add login page"
```

---

## Task 15: 路由守卫 `PrivateRoute` 并接入 `App.tsx`

**Files:**
- Create: `front/src/components/PrivateRoute.tsx`
- Modify: `front/src/App.tsx`

- [ ] **Step 1: 创建 PrivateRoute**

创建 `front/src/components/PrivateRoute.tsx`：

```tsx
import type React from 'react'
import { useEffect } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { Spin } from 'antd'
import { useAuthStore } from '../store/useAuthStore'

/**
 * 路由守卫：
 * - status === 'idle' 时调用 initialize() 尝试用本地 refresh token 恢复会话，期间展示 loading
 * - status === 'unauthenticated' 时跳转登录页，并记录来源路径用于登录后跳回
 * - status === 'authenticated' 时渲染子路由
 */
const PrivateRoute: React.FC = () => {
  const status = useAuthStore((state) => state.status)
  const initialize = useAuthStore((state) => state.initialize)
  const location = useLocation()

  useEffect(() => {
    if (status === 'idle') {
      void initialize()
    }
  }, [status, initialize])

  if (status === 'idle') {
    return (
      <div className="flex items-center justify-center h-screen">
        <Spin size="large" />
      </div>
    )
  }

  if (status === 'unauthenticated') {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <Outlet />
}

export default PrivateRoute
```

- [ ] **Step 2: 接入 App.tsx**

打开 `front/src/App.tsx`，新增导入：

```tsx
import LoginPage from './pages/auth/LoginPage'
import PrivateRoute from './components/PrivateRoute'
```

将：

```tsx
      <Routes>
        <Route path="/" element={<MainLayout />}>
```

到对应 `</Route>` 结束的整段路由树，用 `PrivateRoute` 包裹，并在同级新增 `/login`。即把：

```tsx
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Navigate to="/projects" replace />} />
          ...（其余现有 Route 不变）...
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
```

改为：

```tsx
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<PrivateRoute />}>
          <Route path="/" element={<MainLayout />}>
            <Route index element={<Navigate to="/projects" replace />} />
            ...（其余现有 Route 不变）...
            <Route path="*" element={<NotFound />} />
          </Route>
        </Route>
      </Routes>
```

只需新增 `/login` 路由和一层 `<Route element={<PrivateRoute />}>` 包裹，原有 `<Route path="/" element={<MainLayout />}>` 内部的所有子路由保持不变。

- [ ] **Step 3: 类型检查**

```bash
cd front
pnpm exec tsc --noEmit
```

Expected: 通过。

- [ ] **Step 4: Commit**

```bash
cd front
git add src/components/PrivateRoute.tsx src/App.tsx
git commit -m "feat: add route guard and wire login page into routing"
```

---

## Task 16: `MainLayout` 展示真实登录用户并接入退出登录

**Files:**
- Modify: `front/src/layouts/MainLayout.tsx`

- [ ] **Step 1: 替换用户信息来源并接入登出**

打开 `front/src/layouts/MainLayout.tsx`。

新增导入：

```tsx
import { useAuthStore } from '../store/useAuthStore'
```

将：

```tsx
  const user = useAppStore((state) => state.user)
```

改为：

```tsx
  const authUser = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)
```

将顶部用户信息展示区域：

```tsx
                <div className="hidden md:flex flex-col leading-tight">
                  <span className="text-sm font-medium text-gray-800">{user.name}</span>
                  <span className="text-xs text-gray-500">{user.role}</span>
                </div>
```

改为：

```tsx
                <div className="hidden md:flex flex-col leading-tight">
                  <span className="text-sm font-medium text-gray-800">{authUser?.username}</span>
                  <span className="text-xs text-gray-500">{authUser?.is_admin ? '管理员' : '成员'}</span>
                </div>
```

将 `userMenuItems` 中的退出登录项：

```tsx
    {
      key: 'logout',
      label: t('user.logout'),
      onClick: () => {
        // 这里保留占位，实际项目中可接入登录逻辑
      },
    },
```

改为：

```tsx
    {
      key: 'logout',
      label: t('user.logout'),
      onClick: () => {
        logout()
        navigate('/login')
      },
    },
```

- [ ] **Step 2: 类型检查**

```bash
cd front
pnpm exec tsc --noEmit
```

Expected: 通过。若 `useAppStore` 的 import 因不再使用 `user` 字段而报未使用变量（`siderCollapsed`/`toggleSider`/`language` 等仍在使用，`useAppStore` import 本身应仍需要），确认 `useAppStore` import 语句仍被其他用法引用，无需删除。

- [ ] **Step 3: Commit**

```bash
cd front
git add src/layouts/MainLayout.tsx
git commit -m "feat: show authenticated user and wire logout in main layout"
```

---

## Task 17: 端到端验证

**Files:** 无新增/修改，验证 Task 1-16 的整体效果。

- [ ] **Step 1: 类型检查**

```bash
cd front
pnpm exec tsc --noEmit
```

Expected: 通过。

- [ ] **Step 2: 启动前后端**

```bash
# 终端 1
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 终端 2
cd front
pnpm dev
```

- [ ] **Step 3: 浏览器手动验证登录闭环**

1. 打开前端地址（默认 `http://localhost:5173`），未登录状态下应自动跳转到 `/login`。
2. 输入错误密码，应提示"用户名或密码错误"。
3. 输入 `.env` 中配置的 `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD`（如 `admin` / `admin123456`），登录成功后应跳转到 `/projects`。
4. 打开浏览器开发者工具 Network 面板，确认对 `/api/v1/studio/projects` 等接口的请求携带 `Authorization: Bearer <token>` 请求头。
5. 顶部导航栏头像旁应显示用户名 `admin` 与角色"管理员"。
6. 点击头像菜单中的"退出登录"，应跳回 `/login`，且再次访问 `/projects` 也应跳回 `/login`。
7. 重新登录后，刷新浏览器页面（F5），应保持登录状态（依赖 `localStorage` 中的 refresh token 通过 `initialize()` 自动恢复会话），而不是跳回登录页。

Expected: 以上 7 项均符合预期。如有偏差，记录具体现象后排查（常见问题：CORS 未放行 `Authorization` 头、`OpenAPI.TOKEN` resolver 未生效、`PrivateRoute` 状态判断逻辑）。

---

## Self-Review Notes

- **Spec 覆盖**：本计划覆盖设计文档 Section 1（`users` 表）、Section 2（认证流程、端点、依赖、公开路径白名单）、Section 4（认证状态管理、OpenAPI 拦截、登录页、路由守卫、导航栏，管理员页面除外）、Section 5（JWT/初始管理员配置与播种，SQL 迁移文件部分因不涉及现有表改动而不在本计划中）。Section 3（service 层 `user_id` 过滤）、管理员 API/页面、11 张表的 `user_id` 迁移留给后续「数据隔离与管理员管理」计划。
- **占位符扫描**：已确认无 TBD/TODO；Task 11/12 中关于生成方法名的"若不同则替换"是因为 OpenAPI 生成方法名依赖运行时生成结果，已给出推导依据（`v1_health_api_v1_health_get` → `v1HealthApiV1HealthGet` 的命名规律）和验证命令，不属于遗留占位。
- **类型一致性**：`useAuthStore` 暴露的 `status/user/accessToken/refreshToken/login/logout/refreshAccessToken/initialize` 在 Task 13/14/15/16 中的引用均一致；`UserRead` 字段（`id/username/is_admin/is_active`）与 Task 16 中 `authUser?.username`/`authUser?.is_admin` 一致。
