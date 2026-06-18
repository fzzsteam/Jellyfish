# 管理员管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让管理员能创建用户、重置密码、禁用/启用账号、查看任意用户的数据：后端新增 `/api/v1/admin/users` 端点（仅 `is_admin` 可访问），前端新增 `AdminRoute` 守卫、用户列表页、用户详情页与导航入口。

**Architecture:** 后端在 `app/schemas/auth.py` 扩展管理员相关 Schema，新增 `app/services/admin.py` 承载用户 CRUD（创建查重、重置密码、启用/禁用时递增 `token_version` 即时吊销旧 token），新增 `app/api/v1/routes/admin/users.py` 并在 `app/api/v1/__init__.py` 以 `dependencies=[Depends(require_admin)]` 挂载；"查看某用户项目"直接复用数据隔离计划的 `project_service.list_projects(db, user_id=目标用户)`，不开特权查询路径。前端新增 `AdminRoute`（认证 + `is_admin` 双重校验），`AdminUserListPage`（Ant Table + 创建/启停）、`AdminUserDetailPage`（详情 + 重置密码 + 该用户项目列表），`MainLayout` 在 `is_admin` 时显示"用户管理"入口，`App.tsx` 在 `AdminRoute` 下挂 `/admin/users` 与 `/admin/users/:id`。

**Tech Stack:** FastAPI + SQLAlchemy(async)；`app.core.security.hash_password`；React + Zustand + Ant Design + react-router-dom；OpenAPI 生成客户端。

**前置依赖（均已完成）：**
- `2026-06-10-user-auth-foundation.md`：`User` 模型、`get_current_user`、`require_admin`、`UserRead`、`useAuthStore`、`PrivateRoute`、`LoginPage` 均已存在。
- `2026-06-17-data-isolation.md`：业务数据按 `user_id` 隔离，`app/services/studio/projects.py` 的 `list_projects(db, *, user_id)` 已就绪（管理员查看某用户项目直接传目标 `user_id`）。

**本计划范围（不含）：** 管理员修改/删除某用户的具体业务资源（除查看项目外的深度管理）、操作审计日志、用户自助修改密码 —— 暂不实现。

参考设计文档：`docs/superpowers/specs/2026-06-09-user-management-design.md`（Section 2 管理员端点、Section 4 前端）。

---

## File Structure

**修改（后端）：**
- `backend/app/schemas/auth.py` — 新增 `UserCreate`/`UserUpdate`/`UserAdminRead`
- `backend/app/api/v1/__init__.py` — 注册 admin 路由（挂 `require_admin`）

**新增（后端）：**
- `backend/app/services/admin.py` — 用户 CRUD 业务逻辑
- `backend/app/api/v1/routes/admin/__init__.py` — 空包标识
- `backend/app/api/v1/routes/admin/users.py` — 管理员端点
- `backend/tests/test_admin_service.py`
- `backend/tests/test_admin_api.py`

**新增（前端）：**
- `front/src/components/AdminRoute.tsx`
- `front/src/pages/admin/AdminUserListPage.tsx`
- `front/src/pages/admin/AdminUserDetailPage.tsx`

**修改（前端）：**
- `front/src/App.tsx` — 新增 admin 路由
- `front/src/layouts/MainLayout.tsx` — `is_admin` 时显示"用户管理"入口
- `front/src/services/generated/**` — `pnpm run openapi:update` 重新生成

---

## Task 1: 管理员用户 Schema

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Test: `backend/tests/test_admin_schemas.py`

- [ ] **Step 1: 编写失败测试**

创建 `backend/tests/test_admin_schemas.py`：

```python
"""管理员用户 Schema 校验测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.auth import UserAdminRead, UserCreate, UserUpdate


def test_user_create_requires_username_and_password() -> None:
    req = UserCreate(username="bob", password="secret123")
    assert req.username == "bob"
    assert req.is_admin is False


def test_user_create_rejects_short_password() -> None:
    with pytest.raises(ValidationError):
        UserCreate(username="bob", password="x")


def test_user_update_all_optional() -> None:
    upd = UserUpdate()
    assert upd.password is None
    assert upd.is_active is None
    assert upd.is_admin is None


def test_user_admin_read_from_attributes() -> None:
    class _U:
        id = "u1"
        username = "bob"
        is_admin = False
        is_active = True

    data = UserAdminRead.model_validate(_U())
    assert data.id == "u1"
    assert data.is_active is True
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend
uv run pytest tests/test_admin_schemas.py -q
```

Expected: FAIL（`ImportError: cannot import name 'UserCreate'`）。

- [ ] **Step 3: 新增 Schema**

打开 `backend/app/schemas/auth.py`，在末尾新增（保留现有 `UserRead`）：

```python
class UserCreate(BaseModel):
    """管理员创建用户的请求体。"""

    username: str = Field(..., min_length=1, max_length=64, description="用户名")
    password: str = Field(..., min_length=6, description="初始密码")
    is_admin: bool = Field(False, description="是否管理员")


class UserUpdate(BaseModel):
    """管理员修改用户的请求体（字段均可选，仅更新传入项）。"""

    password: str | None = Field(None, min_length=6, description="重置后的新密码")
    is_active: bool | None = Field(None, description="启用/禁用")
    is_admin: bool | None = Field(None, description="是否管理员")


class UserAdminRead(BaseModel):
    """管理员视角的用户信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")
    is_admin: bool = Field(..., description="是否管理员")
    is_active: bool = Field(..., description="是否启用")
```

> `ConfigDict`/`Field`/`BaseModel` 已在文件顶部导入；如缺 `ConfigDict` 则补 `from pydantic import BaseModel, ConfigDict, Field`。

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend
uv run pytest tests/test_admin_schemas.py -q
```

Expected: PASS（4 passed）。

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/schemas/auth.py tests/test_admin_schemas.py
git commit -m "feat: add admin user management schemas

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: 管理员用户 Service

**Files:**
- Create: `backend/app/services/admin.py`
- Test: `backend/tests/test_admin_service.py`

- [ ] **Step 1: 编写失败测试**

创建 `backend/tests/test_admin_service.py`：

```python
"""管理员用户 CRUD service 测试。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.core.security import verify_password
from app.models.user import User
from app.services import admin as admin_service


async def _session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = sm()
    db.add(User(id="admin-1", username="admin", hashed_password="h", is_admin=True))
    await db.flush()
    return db, engine


@pytest.mark.asyncio
async def test_create_user_hashes_password() -> None:
    db, engine = await _session()
    async with db:
        user = await admin_service.create_user(db, username="bob", password="secret123", is_admin=False)
        assert user.username == "bob"
        assert user.hashed_password != "secret123"
        assert verify_password("secret123", user.hashed_password)
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_user_duplicate_username_raises() -> None:
    db, engine = await _session()
    async with db:
        await admin_service.create_user(db, username="bob", password="secret123", is_admin=False)
        with pytest.raises(admin_service.UsernameExistsError):
            await admin_service.create_user(db, username="bob", password="other123", is_admin=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_user_reset_password_bumps_token_version() -> None:
    db, engine = await _session()
    async with db:
        user = await admin_service.create_user(db, username="bob", password="secret123", is_admin=False)
        before = user.token_version
        updated = await admin_service.update_user(db, user.id, password="newpass123")
        assert verify_password("newpass123", updated.hashed_password)
        assert updated.token_version == before + 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_user_disable_bumps_token_version() -> None:
    db, engine = await _session()
    async with db:
        user = await admin_service.create_user(db, username="bob", password="secret123", is_admin=False)
        before = user.token_version
        updated = await admin_service.update_user(db, user.id, is_active=False)
        assert updated.is_active is False
        assert updated.token_version == before + 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_unknown_user_raises() -> None:
    db, engine = await _session()
    async with db:
        with pytest.raises(admin_service.UserNotFoundError):
            await admin_service.update_user(db, "nope", is_active=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_cannot_disable_last_admin() -> None:
    db, engine = await _session()
    async with db:
        with pytest.raises(admin_service.LastAdminError):
            await admin_service.update_user(db, "admin-1", is_active=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_users_paginated() -> None:
    db, engine = await _session()
    async with db:
        await admin_service.create_user(db, username="bob", password="secret123", is_admin=False)
        items, total = await admin_service.list_users(db, page=1, page_size=10)
        assert total == 2  # admin + bob
        assert {u.username for u in items} == {"admin", "bob"}
    await engine.dispose()
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend
uv run pytest tests/test_admin_service.py -q
```

Expected: FAIL（`ModuleNotFoundError: No module named 'app.services.admin'`）。

- [ ] **Step 3: 实现 admin service**

创建 `backend/app/services/admin.py`：

```python
"""管理员用户管理业务逻辑：创建、列表、查询、修改（重置密码/启停/角色）。

存在意义：把用户 CRUD 与隔离/审计相关的不变量（用户名唯一、改密或禁用时递增
token_version 以即时吊销旧 token、不允许禁用/降级最后一个管理员）收敛到 service，
路由层只收参鉴权。
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User


class UsernameExistsError(Exception):
    """用户名已存在。"""


class UserNotFoundError(Exception):
    """目标用户不存在。"""


class LastAdminError(Exception):
    """不允许禁用或降级最后一个启用中的管理员（避免系统失去管理员）。"""


async def create_user(db: AsyncSession, *, username: str, password: str, is_admin: bool) -> User:
    """创建用户；用户名重复抛 `UsernameExistsError`。"""
    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none() is not None:
        raise UsernameExistsError(username)
    user = User(
        id=str(uuid.uuid4()),
        username=username,
        hashed_password=hash_password(password),
        is_admin=is_admin,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def list_users(db: AsyncSession, *, page: int, page_size: int) -> tuple[list[User], int]:
    """分页列出全部用户（按创建时间倒序）。"""
    total = await db.scalar(select(func.count()).select_from(User))
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return list(result.scalars().all()), int(total or 0)


async def get_user(db: AsyncSession, user_id: str) -> User:
    """按 ID 查询用户；不存在抛 `UserNotFoundError`。"""
    user = await db.get(User, user_id)
    if user is None:
        raise UserNotFoundError(user_id)
    return user


async def _active_admin_count(db: AsyncSession) -> int:
    return int(
        await db.scalar(
            select(func.count()).select_from(User).where(User.is_admin.is_(True), User.is_active.is_(True))
        )
        or 0
    )


async def update_user(
    db: AsyncSession,
    user_id: str,
    *,
    password: str | None = None,
    is_active: bool | None = None,
    is_admin: bool | None = None,
) -> User:
    """修改用户：重置密码 / 启停 / 角色。

    - 重置密码或禁用账号时递增 `token_version`，使该用户已签发的 token 立即失效。
    - 不允许把最后一个启用中的管理员禁用或降级（`LastAdminError`），避免系统失去管理员。
    """
    user = await get_user(db, user_id)

    removing_last_admin = (
        user.is_admin
        and user.is_active
        and await _active_admin_count(db) <= 1
        and (is_active is False or is_admin is False)
    )
    if removing_last_admin:
        raise LastAdminError(user_id)

    bump = False
    if password is not None:
        user.hashed_password = hash_password(password)
        bump = True
    if is_active is not None:
        if user.is_active and not is_active:
            bump = True
        user.is_active = is_active
    if is_admin is not None:
        user.is_admin = is_admin
    if bump:
        user.token_version += 1

    await db.flush()
    await db.refresh(user)
    return user
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend
uv run pytest tests/test_admin_service.py -q
```

Expected: PASS（7 passed）。

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/services/admin.py tests/test_admin_service.py
git commit -m "feat: add admin user CRUD service with token revocation guards

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 管理员路由

**Files:**
- Create: `backend/app/api/v1/routes/admin/__init__.py`
- Create: `backend/app/api/v1/routes/admin/users.py`
- Modify: `backend/app/api/v1/__init__.py`
- Test: `backend/tests/test_admin_api.py`

- [ ] **Step 1: 编写失败测试**

创建 `backend/tests/test_admin_api.py`：

```python
"""管理员 API 测试：鉴权、用户 CRUD、查看某用户项目。"""

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
from app.models.user import User


@pytest.fixture
def admin_client() -> TestClient:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sm() as s:
            s.add(User(id="admin-1", username="admin", hashed_password=hash_password("pw"), is_admin=True))
            s.add(User(id="user-1", username="bob", hashed_password=hash_password("pw"), is_admin=False))
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
        return User(id="admin-1", username="admin", hashed_password="x", is_admin=True, is_active=True)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _admin_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_list_users(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/v1/admin/users")
    assert resp.status_code == 200
    assert resp.json()["data"]["pagination"]["total"] == 2


def test_create_user(admin_client: TestClient) -> None:
    resp = admin_client.post("/api/v1/admin/users", json={"username": "carol", "password": "secret123"})
    assert resp.status_code == 201
    assert resp.json()["data"]["username"] == "carol"


def test_create_duplicate_user_returns_409(admin_client: TestClient) -> None:
    resp = admin_client.post("/api/v1/admin/users", json={"username": "bob", "password": "secret123"})
    assert resp.status_code == 409


def test_get_user_detail(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/v1/admin/users/user-1")
    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "bob"


def test_patch_user_disable(admin_client: TestClient) -> None:
    resp = admin_client.patch("/api/v1/admin/users/user-1", json={"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["data"]["is_active"] is False


def test_list_user_projects_empty(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/v1/admin/users/user-1/projects")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_non_admin_forbidden() -> None:
    # 覆盖：require_admin 对非管理员返回 403（用独立的 override）
    async def _normal_user() -> User:
        return User(id="user-1", username="bob", hashed_password="x", is_admin=False, is_active=True)

    app.dependency_overrides[get_current_user] = _normal_user
    try:
        client = TestClient(app)
        resp = client.get("/api/v1/admin/users")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend
uv run pytest tests/test_admin_api.py -q
```

Expected: FAIL（`/api/v1/admin/users` 404，路由不存在）。

- [ ] **Step 3: 创建 admin 路由包**

创建空文件 `backend/app/api/v1/routes/admin/__init__.py`：

```python
"""管理员相关路由包。"""
```

创建 `backend/app/api/v1/routes/admin/users.py`：

```python
"""管理员用户管理端点：创建、列表、详情、修改、查看某用户项目。

挂载时整体注入 `require_admin`（见 app/api/v1/__init__.py），故此处不重复鉴权。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.schemas.auth import UserAdminRead, UserCreate, UserUpdate
from app.schemas.common import ApiResponse, created_response, paginated_response, success_response
from app.services import admin as admin_service
from app.services.common import entity_already_exists, entity_not_found
from app.services.studio import projects as project_service

router = APIRouter()


@router.get("", response_model=ApiResponse, summary="用户列表")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    items, total = await admin_service.list_users(db, page=page, page_size=page_size)
    return paginated_response(
        [UserAdminRead.model_validate(u) for u in items], total=total, page=page, page_size=page_size
    )


@router.post("", response_model=ApiResponse[UserAdminRead], status_code=status.HTTP_201_CREATED, summary="创建用户")
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db)):
    try:
        user = await admin_service.create_user(
            db, username=body.username, password=body.password, is_admin=body.is_admin
        )
    except admin_service.UsernameExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=entity_already_exists("User")) from exc
    return created_response(UserAdminRead.model_validate(user))


@router.get("/{user_id}", response_model=ApiResponse[UserAdminRead], summary="用户详情")
async def get_user(user_id: str, db: AsyncSession = Depends(get_db)):
    try:
        user = await admin_service.get_user(db, user_id)
    except admin_service.UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("User")) from exc
    return success_response(UserAdminRead.model_validate(user))


@router.patch("/{user_id}", response_model=ApiResponse[UserAdminRead], summary="修改用户")
async def update_user(user_id: str, body: UserUpdate, db: AsyncSession = Depends(get_db)):
    try:
        user = await admin_service.update_user(
            db, user_id, password=body.password, is_active=body.is_active, is_admin=body.is_admin
        )
    except admin_service.UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("User")) from exc
    except admin_service.LastAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="cannot disable or demote the last active admin"
        ) from exc
    return success_response(UserAdminRead.model_validate(user))


@router.get("/{user_id}/projects", response_model=ApiResponse, summary="查看某用户的项目")
async def list_user_projects(user_id: str, db: AsyncSession = Depends(get_db)):
    # 管理员以目标 user_id 走与普通用户同一套隔离 service，不开特权查询路径。
    projects = await project_service.list_projects(db, user_id=user_id)
    return success_response([{"id": p.id, "name": p.name} for p in projects])
```

> `project_service.list_projects` 的返回与字段以数据隔离计划落地的实现为准；若其已返回 Pydantic 读模型，则直接 `success_response(projects)`。`paginated_response`/`created_response`/`entity_already_exists` 的签名以 `app/schemas/common.py` 实际为准，按需微调。

- [ ] **Step 4: 注册路由（挂 require_admin）**

打开 `backend/app/api/v1/__init__.py`，在 import 区加入：

```python
from app.api.v1.routes.admin import users as admin_users
from app.dependencies import get_current_user, require_admin
```

在 auth 路由注册之后新增：

```python
router.include_router(
    admin_users.router,
    prefix="/admin/users",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)
```

> `require_admin` 内部已依赖 `get_current_user`，故 admin 路由同时要求登录 + 管理员。

- [ ] **Step 5: 运行测试，确认通过**

```bash
cd backend
uv run pytest tests/test_admin_api.py -q
```

Expected: PASS（7 passed）。

- [ ] **Step 6: 回归（确保未破坏既有）**

```bash
cd backend
uv run pytest tests/test_auth_api.py tests/test_admin_service.py tests/test_admin_api.py -q
```

Expected: 全部通过。

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/api/v1/routes/admin app/api/v1/__init__.py tests/test_admin_api.py
git commit -m "feat: add admin user management endpoints

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 重新生成前端客户端

**Files:**
- Regenerate: `front/src/services/generated/**`、`front/openapi.json`

- [ ] **Step 1: 启动后端（用临时 sqlite，不动用户 .env）**

```bash
cd backend
rm -f jellyfish_admin_tmp.db
DATABASE_URL="sqlite+aiosqlite:///./jellyfish_admin_tmp.db" \
INITIAL_ADMIN_PASSWORD="admin123456" JWT_SECRET_KEY="dev" REDIS_HOST="" \
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- [ ] **Step 2: 重新生成客户端**

```bash
cd front
pnpm run openapi:update
```

- [ ] **Step 3: 确认生成了 admin 方法**

```bash
cd front
grep -rl "AdminUsers\|admin/users\|adminUsers" src/services/generated/services/ | head
```

Expected: 存在带 admin 用户管理方法的 Service 文件（具体类名/方法名以生成结果为准，供后续前端任务调用）。

- [ ] **Step 4: 类型检查 + 停后端 + 清理**

```bash
cd front && pnpm exec tsc --noEmit
# 停掉后端（Ctrl-C），然后：
cd backend && rm -f jellyfish_admin_tmp.db
```

Expected: `tsc` 通过。

- [ ] **Step 5: Commit**

```bash
cd front
git add openapi.json src/services/generated
git commit -m "chore: regenerate OpenAPI client with admin endpoints

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 前端 `AdminRoute` 守卫

**Files:**
- Create: `front/src/components/AdminRoute.tsx`

- [ ] **Step 1: 创建 AdminRoute**

参照 `front/src/components/PrivateRoute.tsx`（先读它了解 `useAuthStore` 的 `status` 取值与 loading 处理），创建 `front/src/components/AdminRoute.tsx`：

```tsx
import type React from 'react'
import { useEffect } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { Spin } from 'antd'
import { useAuthStore } from '../store/useAuthStore'

/**
 * 管理员路由守卫：在 PrivateRoute 已保证登录的基础上，进一步要求 is_admin。
 * - status === 'idle' 时尝试恢复会话，期间 loading
 * - 未登录跳 /login；已登录但非管理员跳首页 /projects
 */
const AdminRoute: React.FC = () => {
  const status = useAuthStore((state) => state.status)
  const user = useAuthStore((state) => state.user)
  const initialize = useAuthStore((state) => state.initialize)

  useEffect(() => {
    if (status === 'idle') void initialize()
  }, [status, initialize])

  if (status === 'idle') {
    return (
      <div className="flex items-center justify-center h-screen">
        <Spin size="large" />
      </div>
    )
  }
  if (status === 'unauthenticated') {
    return <Navigate to="/login" replace />
  }
  if (!user?.is_admin) {
    return <Navigate to="/projects" replace />
  }
  return <Outlet />
}

export default AdminRoute
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
git add src/components/AdminRoute.tsx
git commit -m "feat: add AdminRoute guard requiring is_admin

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: 用户列表页 `AdminUserListPage`

**Files:**
- Create: `front/src/pages/admin/AdminUserListPage.tsx`

- [ ] **Step 1: 确认生成客户端的 admin 方法名**

```bash
cd front
grep -rnE "public static .*(listUsers|createUser|UpdateUser|AdminUsers)" src/services/generated/services/
```

记录列表/创建/修改方法的精确名字，用于下方组件（占位名 `AdminUsersService.listUsers...` 等按实际替换）。

- [ ] **Step 2: 创建页面**

创建 `front/src/pages/admin/AdminUserListPage.tsx`（参照 `src/pages/aiStudio/models/ProvidersTab.tsx` 的 Table + Modal 模式）：

```tsx
import { useEffect, useState } from 'react'
import type React from 'react'
import { Button, Card, Form, Input, Modal, Switch, Table, Tag, message } from 'antd'
import { Link } from 'react-router-dom'
import { AdminUsersService } from '../../services/generated'
import type { UserAdminRead } from '../../services/generated'

/** 管理员用户列表页：展示全部用户，支持创建与启用/禁用。 */
const AdminUserListPage: React.FC = () => {
  const [users, setUsers] = useState<UserAdminRead[]>([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const res = await AdminUsersService.listUsersApiV1AdminUsersGet({ page: 1, pageSize: 100 })
      setUsers(res.data?.items ?? [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const handleCreate = async () => {
    const values = await form.validateFields()
    try {
      await AdminUsersService.createUserApiV1AdminUsersPost({ requestBody: values })
      message.success('用户已创建')
      setCreating(false)
      form.resetFields()
      void load()
    } catch {
      message.error('创建失败（用户名可能已存在）')
    }
  }

  const toggleActive = async (user: UserAdminRead) => {
    try {
      await AdminUsersService.updateUserApiV1AdminUsersUserIdPatch({
        userId: user.id,
        requestBody: { is_active: !user.is_active },
      })
      void load()
    } catch {
      message.error('操作失败')
    }
  }

  const columns = [
    {
      title: '用户名',
      dataIndex: 'username',
      render: (_: string, u: UserAdminRead) => <Link to={`/admin/users/${u.id}`}>{u.username}</Link>,
    },
    { title: '角色', dataIndex: 'is_admin', render: (v: boolean) => (v ? <Tag color="gold">管理员</Tag> : <Tag>成员</Tag>) },
    {
      title: '状态',
      dataIndex: 'is_active',
      render: (v: boolean) => (v ? <Tag color="green">启用</Tag> : <Tag color="red">禁用</Tag>),
    },
    {
      title: '操作',
      render: (_: unknown, u: UserAdminRead) => (
        <Switch checked={u.is_active} onChange={() => void toggleActive(u)} checkedChildren="启用" unCheckedChildren="禁用" />
      ),
    },
  ]

  return (
    <Card
      title="用户管理"
      extra={<Button type="primary" onClick={() => setCreating(true)}>创建用户</Button>}
    >
      <Table rowKey="id" loading={loading} columns={columns} dataSource={users} />
      <Modal title="创建用户" open={creating} onOk={() => void handleCreate()} onCancel={() => setCreating(false)} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="password" label="初始密码" rules={[{ required: true, min: 6, message: '至少 6 位' }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="is_admin" label="管理员" valuePropName="checked" initialValue={false}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}

export default AdminUserListPage
```

> 方法名（`listUsersApiV1AdminUsersGet` 等）、分页返回结构（`res.data.items`）以 Task 4 生成客户端的实际为准，对照 Step 1 调整。

- [ ] **Step 3: 类型检查**

```bash
cd front
pnpm exec tsc --noEmit
```

Expected: 通过。

- [ ] **Step 4: Commit**

```bash
cd front
git add src/pages/admin/AdminUserListPage.tsx
git commit -m "feat: add admin user list page

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: 用户详情页 `AdminUserDetailPage`

**Files:**
- Create: `front/src/pages/admin/AdminUserDetailPage.tsx`

- [ ] **Step 1: 创建页面**

创建 `front/src/pages/admin/AdminUserDetailPage.tsx`：

```tsx
import { useEffect, useState } from 'react'
import type React from 'react'
import { Button, Card, Descriptions, Form, Input, Table, Tag, message } from 'antd'
import { useParams } from 'react-router-dom'
import { AdminUsersService } from '../../services/generated'
import type { UserAdminRead } from '../../services/generated'

/** 管理员用户详情页：展示用户信息、重置密码、查看其项目列表。 */
const AdminUserDetailPage: React.FC = () => {
  const { id = '' } = useParams()
  const [user, setUser] = useState<UserAdminRead | null>(null)
  const [projects, setProjects] = useState<Array<{ id: string; name: string }>>([])
  const [form] = Form.useForm()

  const load = async () => {
    const [u, p] = await Promise.all([
      AdminUsersService.getUserApiV1AdminUsersUserIdGet({ userId: id }),
      AdminUsersService.listUserProjectsApiV1AdminUsersUserIdProjectsGet({ userId: id }),
    ])
    setUser(u.data ?? null)
    setProjects(p.data ?? [])
  }

  useEffect(() => {
    if (id) void load()
  }, [id])

  const resetPassword = async () => {
    const { password } = await form.validateFields()
    try {
      await AdminUsersService.updateUserApiV1AdminUsersUserIdPatch({ userId: id, requestBody: { password } })
      message.success('密码已重置，该用户需重新登录')
      form.resetFields()
    } catch {
      message.error('重置失败')
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card title="用户信息">
        <Descriptions column={2}>
          <Descriptions.Item label="用户名">{user?.username}</Descriptions.Item>
          <Descriptions.Item label="角色">{user?.is_admin ? <Tag color="gold">管理员</Tag> : <Tag>成员</Tag>}</Descriptions.Item>
          <Descriptions.Item label="状态">{user?.is_active ? <Tag color="green">启用</Tag> : <Tag color="red">禁用</Tag>}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="重置密码">
        <Form form={form} layout="inline" onFinish={() => void resetPassword()}>
          <Form.Item name="password" rules={[{ required: true, min: 6, message: '至少 6 位' }]}>
            <Input.Password placeholder="新密码" />
          </Form.Item>
          <Button type="primary" htmlType="submit">重置</Button>
        </Form>
      </Card>

      <Card title="该用户的项目">
        <Table
          rowKey="id"
          dataSource={projects}
          pagination={false}
          columns={[
            { title: '项目 ID', dataIndex: 'id' },
            { title: '项目名', dataIndex: 'name' },
          ]}
        />
      </Card>
    </div>
  )
}

export default AdminUserDetailPage
```

> 方法名以生成客户端实际为准。

- [ ] **Step 2: 类型检查 + Commit**

```bash
cd front
pnpm exec tsc --noEmit
git add src/pages/admin/AdminUserDetailPage.tsx
git commit -m "feat: add admin user detail page with password reset and project list

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: 接入路由与导航入口

**Files:**
- Modify: `front/src/App.tsx`
- Modify: `front/src/layouts/MainLayout.tsx`

- [ ] **Step 1: App.tsx 新增 admin 路由**

打开 `front/src/App.tsx`，新增导入：

```tsx
import AdminRoute from './components/AdminRoute'
import AdminUserListPage from './pages/admin/AdminUserListPage'
import AdminUserDetailPage from './pages/admin/AdminUserDetailPage'
```

在 `<Route path="/" element={<MainLayout />}>` 内部（与 `settings` 等同级），新增一层 `AdminRoute` 包裹的 admin 路由：

```tsx
          <Route element={<AdminRoute />}>
            <Route path="admin/users" element={<AdminUserListPage />} />
            <Route path="admin/users/:id" element={<AdminUserDetailPage />} />
          </Route>
```

> 放在 `MainLayout` 内、`PrivateRoute` 内，确保管理页也使用主框架布局；`AdminRoute` 再加 `is_admin` 校验。

- [ ] **Step 2: MainLayout 导航条件显示"用户管理"**

打开 `front/src/layouts/MainLayout.tsx`。`authUser` 已存在（`const authUser = useAuthStore((state) => state.user)`）。在 `menuItems` 数组定义后，根据 `authUser?.is_admin` 追加入口（保持现有数组不变，末尾条件追加）：

```tsx
  const menuItems = [
    // ...现有项保持不变...
  ]

  if (authUser?.is_admin) {
    menuItems.push({
      key: 'admin-users',
      icon: <TeamOutlined />,
      label: <Link to="/admin/users">用户管理</Link>,
    })
  }
```

并在文件顶部的 antd 图标导入中加入 `TeamOutlined`（与现有 `FolderOutlined` 等同处导入）。同时在 `selectedKeys` 的 `useMemo` 里补一条高亮规则：

```tsx
    if (location.pathname.startsWith('/admin')) return ['admin-users']
```

- [ ] **Step 3: 类型检查**

```bash
cd front
pnpm exec tsc --noEmit
```

Expected: 通过。

- [ ] **Step 4: Commit**

```bash
cd front
git add src/App.tsx src/layouts/MainLayout.tsx
git commit -m "feat: wire admin routes and nav entry for admins

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: 端到端验证

**Files:** 无新增；验证 Task 1-8 整体。

- [ ] **Step 1: 后端相关测试**

```bash
cd backend
uv run pytest tests/test_admin_schemas.py tests/test_admin_service.py tests/test_admin_api.py tests/test_auth_api.py -q
```

Expected: 全绿。

- [ ] **Step 2: 前端类型检查与构建**

```bash
cd front
pnpm exec tsc --noEmit
pnpm run build
```

Expected: `tsc` 与 `build` 均通过。

- [ ] **Step 3: 手动验证管理员闭环（用临时 sqlite 起后端 + 前端 dev）**

```bash
# 终端 1
cd backend
DATABASE_URL="sqlite+aiosqlite:///./jellyfish_e2e.db" \
INITIAL_ADMIN_PASSWORD="admin123456" JWT_SECRET_KEY="dev" REDIS_HOST="" \
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# 终端 2
cd front && pnpm dev
```

逐项确认：
1. 用 `admin/admin123456` 登录，导航栏出现"用户管理"入口；普通成员账号无此入口。
2. 进入 `/admin/users`，创建一个普通用户 `bob`。
3. 用 `bob` 登录（隐身窗口），只能看到自己的（空）数据，访问 `/admin/users` 被重定向回 `/projects`。
4. 管理员在 `bob` 详情页重置密码 → `bob` 旧 token 失效、需重新登录（401 触发刷新失败 → 跳登录页）。
5. 管理员禁用 `bob` → `bob` 无法登录。
6. 管理员在 `bob` 详情页能看到 `bob` 的项目列表（管理员以目标 user_id 走同一隔离 service）。

```bash
# 验证后清理
cd backend && rm -f jellyfish_e2e.db
```

Expected: 6 项全部符合。

---

## Self-Review Notes

- **Spec 覆盖（Section 2 管理员端点 / Section 4 前端）**：
  - Section 2：Task 1-3 覆盖 `POST/GET/GET{id}/PATCH{id}/GET{id}/projects` 五个端点，统一挂 `require_admin`；"查看某用户项目"复用隔离 `list_projects(db, user_id=目标)`，未开特权路径（符合设计"管理员绕过隔离=传目标 user_id 走同一 service"）。
  - Section 4：Task 5 `AdminRoute`、Task 6 列表页、Task 7 详情页、Task 8 导航入口与路由。
- **token 即时吊销**：重置密码 / 禁用账号在 service 层递增 `token_version`（Task 2），与 auth-foundation 的 `get_current_user`/refresh 校验联动，旧 token 立即失效。
- **防锁死**：`LastAdminError` 阻止禁用/降级最后一个启用中的管理员（spec 未明确要求，作为安全兜底加入；e2e Step 3.4 不受影响，因操作对象是普通用户）。
- **占位符扫描**：前端方法名（`listUsersApiV1AdminUsersGet` 等）标注"以生成客户端实际为准"，因 OpenAPI 方法名由后端 operation_id 运行时生成，已给出 Task 4 Step 3 / Task 6 Step 1 的核对命令，不属遗留占位。
- **类型一致性**：`UserAdminRead`(id/username/is_admin/is_active) 在 service、路由、前端三处一致；`update_user(db, user_id, *, password, is_active, is_admin)` 在 Task 2 定义、Task 3 路由调用一致。
```