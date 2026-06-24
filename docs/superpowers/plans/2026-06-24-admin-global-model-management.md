# 管理员统一模型管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Provider/Model 从按用户隔离改为全局资源，写操作限管理员，读操作对所有登录用户开放，前端普通用户只看到"设置"Tab。

**Architecture:** 去掉 `Provider` / `Model` 的 `UserOwnedMixin`，service 层移除 `user_id` 过滤，路由层写操作改用 `require_admin` 依赖；`ModelSettings` 每用户一行保持不变，用户从全局模型池中选默认模型；前端 `ModelManagement.tsx` 根据 `useAuthStore` 中 `user.is_admin` 动态显示 Tab。

**Tech Stack:** Python/FastAPI/SQLAlchemy（后端），React/TypeScript/Ant Design（前端），MySQL（生产迁移），SQLite in-memory（测试）

---

## 文件改动清单

| 操作 | 文件 |
|------|------|
| Create | `backend/sql/015-admin-global-model-management.sql` |
| Modify | `backend/app/models/llm.py` |
| Modify | `backend/app/services/llm/manage.py` |
| Modify | `backend/app/api/v1/routes/llm.py` |
| Modify | `backend/tests/test_isolation_llm.py` |
| Modify | `backend/tests/test_llm_manage.py` |
| Modify | `backend/tests/test_llm_api_responses.py` |
| Modify | `front/src/pages/aiStudio/models/ModelManagement.tsx` |

---

## Task 1: 编写数据库迁移 SQL

**Files:**
- Create: `backend/sql/015-admin-global-model-management.sql`

- [ ] **Step 1: 创建迁移文件**

```sql
-- 015-admin-global-model-management.sql
-- Provider/Model 全局化：清理非管理员数据、修复悬空外键、删除 user_id 列。
-- 幂等策略：用 information_schema 探测列是否存在，再决定执行真正的 DDL 或空操作。

-- ============================================================
-- 1. 清理非管理员用户的 model_settings（按外键依赖顺序先删）
-- ============================================================
DELETE FROM model_settings
WHERE user_id NOT IN (SELECT id FROM users WHERE is_admin = 1);

-- ============================================================
-- 2. 清理非管理员用户的 models
-- ============================================================
DELETE FROM models
WHERE user_id NOT IN (SELECT id FROM users WHERE is_admin = 1);

-- ============================================================
-- 3. 清理非管理员用户的 providers
-- ============================================================
DELETE FROM providers
WHERE user_id NOT IN (SELECT id FROM users WHERE is_admin = 1);

-- ============================================================
-- 4. 修复管理员 model_settings 中悬空的外键引用（置 NULL）
-- ============================================================
UPDATE model_settings
SET default_text_model_id = NULL
WHERE default_text_model_id IS NOT NULL
  AND default_text_model_id NOT IN (SELECT id FROM models);

UPDATE model_settings
SET default_image_model_id = NULL
WHERE default_image_model_id IS NOT NULL
  AND default_image_model_id NOT IN (SELECT id FROM models);

UPDATE model_settings
SET default_video_model_id = NULL
WHERE default_video_model_id IS NOT NULL
  AND default_video_model_id NOT IN (SELECT id FROM models);

-- ============================================================
-- 5. 删除 providers.user_id 列（先删 FK 与索引）
-- ============================================================
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'providers' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col > 0,
  "ALTER TABLE providers DROP FOREIGN KEY fk_providers_user, DROP INDEX ix_providers_user_id, DROP COLUMN user_id",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ============================================================
-- 6. 删除 models.user_id 列（先删 FK 与索引）
-- ============================================================
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'models' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col > 0,
  "ALTER TABLE models DROP FOREIGN KEY fk_models_user, DROP INDEX ix_models_user_id, DROP COLUMN user_id",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
```

- [ ] **Step 2: 验证文件存在**

```bash
ls backend/sql/015-admin-global-model-management.sql
```

Expected: 文件存在，无错误。

- [ ] **Step 3: Commit**

```bash
git add backend/sql/015-admin-global-model-management.sql
git commit -m "feat(db): 015 迁移 - Provider/Model 全局化，清理非管理员数据并删除 user_id 列"
```

---

## Task 2: 改造 ORM 模型层

**Files:**
- Modify: `backend/app/models/llm.py`

- [ ] **Step 1: 去掉 Provider 和 Model 的 UserOwnedMixin**

将 `backend/app/models/llm.py` 中的 `Provider` 和 `Model` 类定义修改如下（去掉 `UserOwnedMixin` 继承，`user_id` 列不再声明）：

```python
class Provider(Base, TimestampMixin):
    """模型供应商配置（全局共享，仅管理员可写）。

    安全提示：
    - `api_key` / `api_secret` 属敏感信息；如后续接入审计/日志，避免明文输出。
    """

    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="供应商 ID")
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True, comment="供应商名称")
    base_url: Mapped[str] = mapped_column(String(1024), nullable=False, comment="文本/通用 API Base URL")
    image_base_url: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        default=None,
        comment="图片能力 API Base URL（可选覆盖）",
    )
    video_base_url: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        default=None,
        comment="视频能力 API Base URL（可选覆盖）",
    )
    api_key: Mapped[str] = mapped_column(String(4096), nullable=False, default="", comment="API Key（敏感）")
    api_secret: Mapped[str] = mapped_column(String(4096), nullable=False, default="", comment="API Secret（敏感）")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="说明")
    status: Mapped[ProviderStatus] = mapped_column(
        String(32),
        nullable=False,
        default=ProviderStatus.testing,
        comment="状态",
    )
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="创建人")

    models: Mapped[list["Model"]] = relationship(
        back_populates="provider",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_providers_updated_at", "updated_at"),
        Index("ix_providers_status", "status"),
    )


class Model(Base, TimestampMixin):
    """具体模型实例（绑定供应商、类别与参数，全局共享，仅管理员可写）。"""

    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="模型 ID")
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True, comment="模型名称")
    category: Mapped[ModelCategoryKey] = mapped_column(String(16), nullable=False, index=True, comment="模型类别")
    provider_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属供应商 ID",
    )
    params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, comment="模型参数（JSON）")
    unit_points: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="积分单价（单次调用消耗的积分数量，0 表示免费）",
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="说明")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="创建人")

    provider: Mapped["Provider"] = relationship(back_populates="models")

    __table_args__ = (
        Index("ix_models_updated_at", "updated_at"),
    )
```

同时在文件顶部 import 中移除 `UserOwnedMixin`（如果 `Provider` 和 `Model` 是仅有的使用者）。

- [ ] **Step 2: 语法检查**

```bash
cd backend && python -m py_compile app/models/llm.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/llm.py
git commit -m "feat(models): Provider/Model 去掉 UserOwnedMixin，变为全局共享资源"
```

---

## Task 3: 改造 Service 层

**Files:**
- Modify: `backend/app/services/llm/manage.py`

- [ ] **Step 1: 重写 manage.py 中的 Provider CRUD 相关函数**

用以下版本替换对应函数（只需改这些，`get_or_create_settings`/`update_model_settings`/`get_image_generation_options`/`get_video_generation_options` 等不动）：

```python
async def list_providers_paginated(
    db: AsyncSession,
    *,
    q: str | None,
    order: str | None,
    is_desc: bool,
    page: int,
    page_size: int,
    allow_fields: set[str],
) -> ApiResponse[PaginatedData[ProviderRead]]:
    """分页查询全局供应商列表（无用户隔离）。"""
    stmt = select(Provider)
    stmt = apply_keyword_filter(stmt, q=q, fields=[Provider.name, Provider.description])
    stmt = apply_order(
        stmt,
        model=Provider,
        order=order,
        is_desc=is_desc,
        allow_fields=allow_fields,
        default="created_at",
    )
    items, total = await paginate(db, stmt=stmt, page=page, page_size=page_size)
    return paginated_response(
        [ProviderRead.model_validate(x) for x in items],
        page=page,
        page_size=page_size,
        total=total,
    )


async def create_provider(
    db: AsyncSession,
    *,
    body: ProviderCreate,
) -> Provider:
    """创建全局供应商（仅管理员路由调用）。"""
    await ensure_not_exists(
        db,
        Provider,
        body.id,
        detail=entity_already_exists("Provider"),
        status_code=400,
    )
    return await create_and_refresh(
        db,
        Provider(
            id=body.id,
            name=body.name,
            base_url=body.base_url,
            image_base_url=body.image_base_url,
            video_base_url=body.video_base_url,
            api_key=body.api_key,
            api_secret=body.api_secret,
            description=body.description,
            status=body.status,
            created_by=body.created_by,
        ),
    )


async def _get_provider(db: AsyncSession, *, provider_id: str) -> Provider:
    """按 ID 获取供应商；不存在时 404。"""
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=entity_not_found("Provider"),
        )
    return provider


async def get_provider(
    db: AsyncSession,
    *,
    provider_id: str,
) -> Provider:
    """获取单个供应商（全局可见）。"""
    return await _get_provider(db, provider_id=provider_id)


async def update_provider(
    db: AsyncSession,
    *,
    provider_id: str,
    body: ProviderUpdate,
) -> Provider:
    """更新供应商（仅管理员路由调用）。"""
    provider = await _get_provider(db, provider_id=provider_id)
    patch_model(provider, body.model_dump(exclude_unset=True))
    return await flush_and_refresh(db, provider)


async def delete_provider(
    db: AsyncSession,
    *,
    provider_id: str,
) -> None:
    """删除供应商（仅管理员路由调用；不存在时静默忽略）。"""
    provider = await db.get(Provider, provider_id)
    if provider is None:
        return
    await db.delete(provider)
    await db.flush()
```

- [ ] **Step 2: 重写 Model CRUD 相关函数**

```python
async def list_models_paginated(
    db: AsyncSession,
    *,
    provider_id: str | None,
    category: ModelCategoryKey | None,
    q: str | None,
    order: str | None,
    is_desc: bool,
    page: int,
    page_size: int,
    allow_fields: set[str],
) -> ApiResponse[PaginatedData[ModelRead]]:
    """分页查询全局模型列表（无用户隔离）。"""
    stmt = select(Model)
    if provider_id is not None:
        stmt = stmt.where(Model.provider_id == provider_id)
    if category is not None:
        stmt = stmt.where(Model.category == category)
    stmt = apply_keyword_filter(stmt, q=q, fields=[Model.name, Model.description])
    stmt = apply_order(
        stmt,
        model=Model,
        order=order,
        is_desc=is_desc,
        allow_fields=allow_fields,
        default="created_at",
    )
    items, total = await paginate(db, stmt=stmt, page=page, page_size=page_size)
    return paginated_response(
        [ModelRead.model_validate(x) for x in items],
        page=page,
        page_size=page_size,
        total=total,
    )


async def _require_provider(db: AsyncSession, *, provider_id: str) -> Provider:
    """创建/更新模型时校验 provider 存在且 category 支持；不存在按 400 处理。"""
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=entity_not_found("Provider"),
        )
    return provider


async def create_model(
    db: AsyncSession,
    *,
    body: ModelCreate,
) -> Model:
    """创建全局模型（仅管理员路由调用）。"""
    await ensure_not_exists(
        db,
        Model,
        body.id,
        detail=entity_already_exists("Model"),
        status_code=400,
    )
    provider = await _require_provider(db, provider_id=body.provider_id)
    _ensure_provider_supports_category(provider=provider, category=body.category)
    return await create_and_refresh(
        db,
        Model(
            id=body.id,
            name=body.name,
            category=body.category,
            provider_id=body.provider_id,
            params=body.params,
            unit_points=body.unit_points,
            description=body.description,
            created_by=body.created_by,
        ),
    )


async def _get_model(db: AsyncSession, *, model_id: str) -> Model:
    """按 ID 获取模型；不存在时 404。"""
    model = await db.get(Model, model_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=entity_not_found("Model"),
        )
    return model


async def get_model(
    db: AsyncSession,
    *,
    model_id: str,
) -> Model:
    """获取单个模型（全局可见）。"""
    return await _get_model(db, model_id=model_id)


async def update_model(
    db: AsyncSession,
    *,
    model_id: str,
    body: ModelUpdate,
) -> Model:
    """更新模型（仅管理员路由调用）。"""
    model = await _get_model(db, model_id=model_id)
    update_data = body.model_dump(exclude_unset=True)
    target_category = update_data.get("category", model.category)
    target_provider_id = update_data.get("provider_id", model.provider_id)
    target_provider = await _require_provider(db, provider_id=target_provider_id)
    _ensure_provider_supports_category(provider=target_provider, category=target_category)
    patch_model(model, update_data)
    return await flush_and_refresh(db, model)


async def delete_model(
    db: AsyncSession,
    *,
    model_id: str,
) -> None:
    """删除模型（仅管理员路由调用；不存在时静默忽略）。"""
    model = await db.get(Model, model_id)
    if model is None:
        return
    await db.delete(model)
    await db.flush()
```

- [ ] **Step 3: 语法检查**

```bash
cd backend && python -m py_compile app/services/llm/manage.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/llm/manage.py
git commit -m "feat(service): manage.py - Provider/Model CRUD 移除 user_id 隔离，变为全局操作"
```

---

## Task 4: 改造路由层

**Files:**
- Modify: `backend/app/api/v1/routes/llm.py`

- [ ] **Step 1: 更新 import，加入 require_admin**

在文件顶部 import 区域，确保从 `app.dependencies` 导入 `require_admin`：

```python
from app.dependencies import get_current_user, get_db, require_admin
```

- [ ] **Step 2: 更新 Provider 写操作路由**

将以下三个路由函数替换为（使用 `require_admin` 依赖，调用 service 时去掉 `user_id`）：

```python
@router.post(
    "/providers",
    response_model=ApiResponse[ProviderRead],
    status_code=status.HTTP_201_CREATED,
    summary="创建模型供应商（仅管理员）",
)
async def create_provider(
    body: ProviderCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> ApiResponse[ProviderRead]:
    provider = await create_provider_service(db, body=body)
    return created_response(ProviderRead.model_validate(provider))


@router.patch(
    "/providers/{provider_id}",
    response_model=ApiResponse[ProviderRead],
    summary="更新模型供应商（仅管理员）",
)
async def update_provider(
    provider_id: str,
    body: ProviderUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> ApiResponse[ProviderRead]:
    provider = await update_provider_service(db, provider_id=provider_id, body=body)
    return success_response(ProviderRead.model_validate(provider))


@router.delete(
    "/providers/{provider_id}",
    response_model=ApiResponse[None],
    status_code=status.HTTP_200_OK,
    summary="删除模型供应商（仅管理员）",
)
async def delete_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> ApiResponse[None]:
    await delete_provider_service(db, provider_id=provider_id)
    return empty_response()
```

- [ ] **Step 3: 更新 Provider 读操作路由**

```python
@router.get(
    "/providers",
    response_model=ApiResponse[PaginatedData[ProviderRead]],
    summary="列出模型供应商（分页）",
)
async def list_providers(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    q: str | None = Query(None, description="关键字，过滤 name/description"),
    order: str | None = Query(None, description="排序字段：name, created_at, updated_at"),
    is_desc: bool = Query(False, description="是否倒序"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
) -> ApiResponse[PaginatedData[ProviderRead]]:
    return await list_providers_paginated(
        db,
        q=q,
        order=order,
        is_desc=is_desc,
        page=page,
        page_size=page_size,
        allow_fields=PROVIDER_ORDER_FIELDS,
    )


@router.get(
    "/providers/{provider_id}",
    response_model=ApiResponse[ProviderRead],
    summary="获取单个模型供应商",
)
async def get_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ApiResponse[ProviderRead]:
    provider = await get_provider_service(db, provider_id=provider_id)
    return success_response(ProviderRead.model_validate(provider))
```

- [ ] **Step 4: 更新 Model 写操作路由**

```python
@router.post(
    "/models",
    response_model=ApiResponse[ModelRead],
    status_code=status.HTTP_201_CREATED,
    summary="创建模型（仅管理员）",
)
async def create_model(
    body: ModelCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> ApiResponse[ModelRead]:
    model = await create_model_service(db, body=body)
    return created_response(ModelRead.model_validate(model))


@router.patch(
    "/models/{model_id}",
    response_model=ApiResponse[ModelRead],
    summary="更新模型（仅管理员）",
)
async def update_model(
    model_id: str,
    body: ModelUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> ApiResponse[ModelRead]:
    model = await update_model_service(db, model_id=model_id, body=body)
    return success_response(ModelRead.model_validate(model))


@router.delete(
    "/models/{model_id}",
    response_model=ApiResponse[None],
    status_code=status.HTTP_200_OK,
    summary="删除模型（仅管理员）",
)
async def delete_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> ApiResponse[None]:
    await delete_model_service(db, model_id=model_id)
    return empty_response()
```

- [ ] **Step 5: 更新 Model 读操作路由**

```python
@router.get(
    "/models",
    response_model=ApiResponse[PaginatedData[ModelRead]],
    summary="列出模型（分页）",
)
async def list_models(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    provider_id: str | None = Query(None, description="按供应商过滤"),
    category: ModelCategoryKey | None = Query(None, description="按模型类别过滤"),
    q: str | None = Query(None, description="关键字，过滤 name/description"),
    order: str | None = Query(None, description="排序字段：name, category, created_at, updated_at"),
    is_desc: bool = Query(False, description="是否倒序"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
) -> ApiResponse[PaginatedData[ModelRead]]:
    return await list_models_paginated(
        db,
        provider_id=provider_id,
        category=category,
        q=q,
        order=order,
        is_desc=is_desc,
        page=page,
        page_size=page_size,
        allow_fields=MODEL_ORDER_FIELDS,
    )


@router.get(
    "/models/{model_id}",
    response_model=ApiResponse[ModelRead],
    summary="获取单个模型",
)
async def get_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ApiResponse[ModelRead]:
    model = await get_model_service(db, model_id=model_id)
    return success_response(ModelRead.model_validate(model))
```

- [ ] **Step 6: 语法检查**

```bash
cd backend && python -m py_compile app/api/v1/routes/llm.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/v1/routes/llm.py
git commit -m "feat(routes): llm 写操作改用 require_admin，读操作去掉 user_id 隔离"
```

---

## Task 5: 更新后端测试

**Files:**
- Modify: `backend/tests/test_isolation_llm.py`
- Modify: `backend/tests/test_llm_manage.py`
- Modify: `backend/tests/test_llm_api_responses.py`

### 5a: 重写 test_isolation_llm.py

旧测试验证"用户间隔离"，现在语义相反——验证"模型全局可见"。

- [ ] **Step 1: 完整替换 test_isolation_llm.py**

```python
"""Provider/Model 全局可见性测试。

验证 manage.py 的 provider/model CRUD 是全局操作（不按 user_id 隔离）：
- 列表返回所有记录（不区分创建者）；
- 任意合法 ID 均可获取单条；
- delete 无需归属校验，直接删除；
- ModelSettings 仍然每用户一行（不变）。
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.user import User
from app.schemas.llm import ModelCreate, ProviderCreate, ProviderUpdate
from app.services.llm.manage import (
    create_model,
    create_provider,
    delete_provider,
    get_model,
    get_provider,
    list_models_paginated,
    list_providers_paginated,
    update_provider,
)


async def _session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = sm()
    db.add_all([
        User(id="u1", username="a", hashed_password="h"),
        User(id="u2", username="b", hashed_password="h"),
    ])
    await db.flush()
    return db, engine


def _provider_body(provider_id: str) -> ProviderCreate:
    return ProviderCreate(
        id=provider_id,
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key="k",
    )


async def _list_providers(db: AsyncSession) -> set[str]:
    resp = await list_providers_paginated(
        db,
        q=None,
        order=None,
        is_desc=False,
        page=1,
        page_size=50,
        allow_fields={"name", "created_at", "updated_at"},
    )
    return {item.id for item in resp.data.items}


@pytest.mark.asyncio
async def test_list_providers_returns_all() -> None:
    """两个不同 created_by 创建的供应商，列表均可见。"""
    db, engine = await _session()
    async with db:
        await create_provider(db, body=_provider_body("p1"))
        await create_provider(db, body=ProviderCreate(
            id="p2", name="AliCloud", base_url="https://api.ali.com/v1", api_key="k2",
        ))

        result = await _list_providers(db)
        assert result == {"p1", "p2"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_provider_globally_visible() -> None:
    """任何合法 provider_id 均可获取，不需要归属校验。"""
    db, engine = await _session()
    async with db:
        await create_provider(db, body=_provider_body("p1"))

        provider = await get_provider(db, provider_id="p1")
        assert provider.id == "p1"
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_provider_not_found_raises_404() -> None:
    db, engine = await _session()
    async with db:
        with pytest.raises(HTTPException) as exc:
            await get_provider(db, provider_id="nonexistent")
        assert exc.value.status_code == 404
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_and_delete_provider_global() -> None:
    """更新和删除不需要归属校验，直接操作。"""
    db, engine = await _session()
    async with db:
        await create_provider(db, body=_provider_body("p1"))

        updated = await update_provider(db, provider_id="p1", body=ProviderUpdate(description="new"))
        assert updated.description == "new"

        await delete_provider(db, provider_id="p1")
        with pytest.raises(HTTPException):
            await get_provider(db, provider_id="p1")
    await engine.dispose()


@pytest.mark.asyncio
async def test_models_globally_visible() -> None:
    """两个不同 created_by 创建的模型，列表均可见。"""
    db, engine = await _session()
    async with db:
        await create_provider(db, body=_provider_body("p1"))
        await create_model(
            db,
            body=ModelCreate(id="m1", name="gpt-4o-mini", category="text", provider_id="p1"),
        )
        await create_model(
            db,
            body=ModelCreate(id="m2", name="gpt-4o", category="text", provider_id="p1"),
        )

        resp = await list_models_paginated(
            db,
            provider_id=None,
            category=None,
            q=None,
            order=None,
            is_desc=False,
            page=1,
            page_size=50,
            allow_fields={"name", "category", "created_at", "updated_at"},
        )
        assert {item.id for item in resp.data.items} == {"m1", "m2"}

        model = await get_model(db, model_id="m1")
        assert model.id == "m1"
    await engine.dispose()
```

### 5b: 更新 test_llm_manage.py

- [ ] **Step 2: 更新 test_llm_manage.py 中所有 user_id 传参**

在 `test_llm_manage.py` 中，将所有 `create_provider(db, user_id="u1", body=...)` 改为 `create_provider(db, body=...)`，将所有 `create_model(db, user_id="u1", body=...)` 改为 `create_model(db, body=...)`，并在 `_build_session` 中可去掉创建 User 的步骤（如果其他函数不需要）。具体改动：

```python
# _build_session 不再需要创建 User（Provider/Model 无 user_id 外键）
async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = session_local()
    return db, engine
```

并将所有测试中的 `create_provider(db, user_id="u1", body=...)` 替换为 `create_provider(db, body=...)`，`create_model(db, user_id="u1", body=...)` 替换为 `create_model(db, body=...)`，`update_model(db, user_id="u1", ...)` 替换为 `update_model(db, ...)`。

注意：`get_image_generation_options` 仍然接受 `user_id` 参数（用于 ModelSettings 查询），测试里需要先建 User 再用该函数的测试需要保留 User 创建。具体地，凡是调用了 `get_image_generation_options` 或 `get_or_create_settings` 的测试，`_build_session` 需要保留 User 创建。可以分开两个 helper：一个无 User，一个有 User。

### 5c: 更新 test_llm_api_responses.py

- [ ] **Step 3: 更新 test_llm_api_responses.py**

修改 `_override_current_user` 让测试用户是管理员（写操作才能通过 `require_admin`）：

```python
async def _override_current_user() -> User:
    return User(id=_TEST_USER_ID, username=_TEST_USER_ID, hashed_password="h", is_admin=True)
```

修改 `_seed_provider` 去掉 `user_id` 参数：

```python
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
```

新增一个测试验证非管理员无法创建供应商：

```python
def test_create_provider_requires_admin(client: TestClient) -> None:
    """非管理员调用写操作应返回 403。"""
    db = _FakeLlmDB()
    llm_app.dependency_overrides[get_db] = _override_db(db)
    # 临时覆盖为非管理员用户
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
        # 恢复默认管理员覆盖
        llm_app.dependency_overrides[get_current_user] = _override_current_user

    assert response.status_code == 403
```

- [ ] **Step 4: 运行测试**

```bash
cd backend && uv run pytest tests/test_isolation_llm.py tests/test_llm_manage.py tests/test_llm_api_responses.py tests/test_model_settings_per_user.py -q
```

Expected: 全部 PASS，无 FAIL/ERROR。

- [ ] **Step 5: 运行完整快速测试**

```bash
cd backend && uv run pytest tests/test_common_services.py tests/test_studio_api_responses.py -q
```

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_isolation_llm.py backend/tests/test_llm_manage.py backend/tests/test_llm_api_responses.py
git commit -m "test: 更新 LLM 测试 - 隔离测试改为全局可见性测试，写操作要求管理员"
```

---

## Task 6: 同步 OpenAPI 客户端

**Files:**
- Modify: `front/src/services/generated/`（自动生成）
- Modify: `front/openapi.json`（自动生成）

> **前置条件：** 后端服务需在 `http://127.0.0.1:8000` 运行。

- [ ] **Step 1: 启动后端开发服务器（后台）**

```bash
cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
sleep 3
```

- [ ] **Step 2: 执行 openapi:update**

```bash
cd front && pnpm run openapi:update
```

Expected: 命令成功，`front/src/services/generated/` 中文件更新。

- [ ] **Step 3: 停止后台后端服务器**

```bash
kill %1 2>/dev/null || pkill -f "uvicorn app.main:app" 2>/dev/null; true
```

- [ ] **Step 4: TypeScript 类型检查**

```bash
cd front && pnpm exec tsc --noEmit
```

Expected: 无类型错误。

- [ ] **Step 5: Commit**

```bash
git add front/src/services/generated/ front/openapi.json
git commit -m "chore(front): 同步 OpenAPI 客户端（Provider/Model 接口去掉 user_id 隔离）"
```

---

## Task 7: 前端 ModelManagement.tsx Tab 控制

**Files:**
- Modify: `front/src/pages/aiStudio/models/ModelManagement.tsx`

- [ ] **Step 1: 改写 ModelManagement.tsx**

```tsx
import { useState } from 'react'
import { Layout, Tabs } from 'antd'
import ProvidersTab from './ProvidersTab'
import ModelsTab from './ModelsTab'
import SettingsTab from './SettingsTab'
import { useAuthStore } from '../../../store/useAuthStore'

export default function ModelManagement() {
  const user = useAuthStore((s) => s.user)
  const isAdmin = user?.is_admin ?? false

  const tabItems = isAdmin
    ? [
        { key: 'providers', label: '供应商' },
        { key: 'models', label: '模型' },
        { key: 'settings', label: '设置' },
      ]
    : [{ key: 'settings', label: '设置' }]

  const [activeTab, setActiveTab] = useState<string>(isAdmin ? 'providers' : 'settings')

  return (
    <Layout className="h-full flex flex-col" style={{ minHeight: 0 }}>
      <div className="flex-shrink-0 px-4 py-3 border-b border-gray-200 bg-white space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-semibold text-gray-800">模型管理</span>
        </div>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          size="small"
          items={tabItems}
        />
      </div>

      <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
        {activeTab === 'providers' && <ProvidersTab />}
        {activeTab === 'models' && <ModelsTab />}
        {activeTab === 'settings' && <SettingsTab />}
      </div>
    </Layout>
  )
}
```

- [ ] **Step 2: TypeScript 类型检查**

```bash
cd front && pnpm exec tsc --noEmit
```

Expected: 无类型错误。

- [ ] **Step 3: Commit**

```bash
git add front/src/pages/aiStudio/models/ModelManagement.tsx
git commit -m "feat(front): ModelManagement - 普通用户只显示设置 Tab，供应商/模型 Tab 仅管理员可见"
```

---

## 完成验证

- [ ] 所有后端测试通过：`cd backend && uv run pytest tests/test_isolation_llm.py tests/test_llm_manage.py tests/test_llm_api_responses.py tests/test_model_settings_per_user.py -q`
- [ ] 前端类型检查通过：`cd front && pnpm exec tsc --noEmit`
- [ ] 迁移文件 `backend/sql/015-admin-global-model-management.sql` 已提交
- [ ] Provider/Model ORM 无 `UserOwnedMixin`
- [ ] 写操作路由使用 `require_admin`
- [ ] 读操作去掉 `user_id` 过滤
- [ ] 前端非管理员只见"设置"Tab
