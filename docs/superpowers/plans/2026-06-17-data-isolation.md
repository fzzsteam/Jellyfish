# 数据隔离（后端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 11 类业务表加 `user_id` 归属，并在 service 层按 `user_id` 严格过滤，使每个登录用户只能看到/操作自己的数据；`model_settings` 从全局单例改为每用户一行；历史数据通过幂等 SQL 迁移归属初始管理员。

**Architecture:** 在 `app/models/base.py` 新增 `UserOwnedMixin`（提供 `user_id` FK 列），让 9 张"直接归属"表（projects/actors/scenes/props/costumes/prompt_templates/files/providers/models）与 `generation_tasks` 继承它；`model_settings` 单独把主键语义从"单行 id=1"改为"每 `user_id` 一行"。service 层所有查询/创建增加 `user_id` 参数并在 `where` 中过滤，路由层新增 `current_user: User = Depends(get_current_user)` 并把 `current_user.id` 透传给 service（不在路由层写隔离逻辑）。`characters`/`shots` 等子表通过 `project_id → projects.user_id` 间接隔离，不单独加列。新表结构由 `init_db()` 的 `create_all` 负责；存量库由 `backend/sql/009-add-users-and-user-isolation.sql`（幂等）加列 + 回填 + 收紧为 NOT NULL。

**Tech Stack:** FastAPI + SQLAlchemy(async) + SQLite(测试)/MySQL；pytest。前置依赖：`2026-06-10-user-auth-foundation.md` 已完成（`User` 模型、`get_current_user`、初始管理员播种均已存在）。

**本计划范围（含）：** 11 类业务表 `user_id` 归属、service 层隔离过滤、`model_settings` 每用户化、`sql/009` 迁移、受影响测试夹具修复、`pnpm run openapi:update` 同步客户端。

**本计划范围（不含）：** 管理员用户管理 API（`/api/v1/admin/users`）、前端管理员页面与 `AdminRoute`、导航栏"用户管理"入口 —— 这些在后续计划 B「管理员管理」中实现。完成本计划后，**管理员与普通用户一样只能看到自己的数据**（管理员跨用户查看能力属计划 B）。

参考设计文档：`docs/superpowers/specs/2026-06-09-user-management-design.md`（Section 1、Section 3、Section 5）。

> **与 spec 的差异（实现时以本计划为准）：**
> 1. spec 写的 `file_items` 表，实际表名是 **`files`**（`FileItem.__tablename__ = "files"`）。
> 2. `prompt_templates.is_system=True` 是系统预置模板，**全用户共享**，隔离查询须放行（`user_id == me OR is_system == True`）；系统模板回填时 `user_id` 设为 NULL 允许。
> 3. `actors`/`scenes`/`props`/`costumes` 上的 `UniqueConstraint(name)` 需改为 `(user_id, name)` 每用户唯一。
> 4. `user_id` 主键类型为 `String(64)`（与 `users.id` 一致），spec 示例里的 `user_id: int` 是笔误。

---

## File Structure

**修改（后端 models）：**
- `backend/app/models/base.py` — 新增 `UserOwnedMixin`
- `backend/app/models/studio_projects.py` — `Project` 加 `user_id`
- `backend/app/models/studio_assets.py` — `Actor`/`Scene`/`Prop`/`Costume` 加 `user_id`，唯一约束改 `(user_id, name)`
- `backend/app/models/studio_prompts_files_timeline.py` — `PromptTemplate`/`FileItem` 加 `user_id`
- `backend/app/models/llm.py` — `Provider`/`Model` 加 `user_id`；`ModelSettings` 改为每用户一行
- `backend/app/models/task.py` — `GenerationTask` 加 `user_id`

**修改（后端 service）：**
- `backend/app/services/studio/entity_crud.py` — 资产 CRUD 加 `user_id`（含 `_ensure_global_name_available` 改为按用户）
- `backend/app/services/studio/entities.py` — `StudioEntitiesService` 透传 `user_id`
- `backend/app/services/studio/files.py` — 文件 CRUD 加 `user_id`
- `backend/app/services/studio/projects.py`（或项目所在 service，见 Task 6 Step 1 定位）— 项目 CRUD 加 `user_id`
- `backend/app/services/studio/prompts*.py` — 模板查询加 `user_id`（放行 `is_system`）
- `backend/app/services/llm/manage.py` — providers/models 查询加 `user_id`；settings 改为按 `user_id` upsert
- 任务查询 service（见 Task 11 Step 1 定位）— `generation_tasks` 列表/详情按 `user_id`

**修改（后端 routes）：** 对应各 service 的路由文件，新增 `current_user` 依赖并透传 `current_user.id`：
- `backend/app/api/v1/routes/studio/projects.py`、`entities.py`、`files.py`、`prompts.py`
- `backend/app/api/v1/routes/llm.py`（或其子路由）
- 任务相关路由

**新增（后端迁移）：**
- `backend/sql/009-add-users-and-user-isolation.sql`

**新增（后端测试）：**
- `backend/tests/test_user_owned_mixin.py`
- `backend/tests/test_model_settings_per_user.py`
- `backend/tests/test_isolation_projects.py`
- `backend/tests/test_isolation_assets.py`
- `backend/tests/test_isolation_prompts.py`
- `backend/tests/test_isolation_files.py`
- `backend/tests/test_isolation_llm.py`
- `backend/tests/test_isolation_tasks.py`

**修改（后端测试夹具）：** 现有创建 project/asset/file/provider 等记录的测试需补 `user_id`（见 Task 5）。

**重新生成（前端）：** `front/src/services/generated/**`、`front/openapi.json`（service 签名新增 `user_id` 来源于 `current_user`，不进入请求参数，但响应/路由变化需同步，见 Task 12）。

---

## Task 1: `UserOwnedMixin` 与各表 `user_id` 列

**Files:**
- Modify: `backend/app/models/base.py`
- Modify: `backend/app/models/studio_projects.py`、`studio_assets.py`、`studio_prompts_files_timeline.py`、`llm.py`、`task.py`
- Test: `backend/tests/test_user_owned_mixin.py`

- [ ] **Step 1: 编写失败测试**

创建 `backend/tests/test_user_owned_mixin.py`：

```python
"""验证业务表均带 user_id 列且为 NOT NULL（新建库语义）。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.studio_projects import Project
from app.models.studio_assets import Actor, Costume, Prop, Scene
from app.models.studio_prompts_files_timeline import FileItem, PromptTemplate
from app.models.llm import Model, Provider
from app.models.task import GenerationTask

OWNED_MODELS = [Project, Actor, Scene, Prop, Costume, PromptTemplate, FileItem, Provider, Model, GenerationTask]


@pytest.mark.parametrize("model", OWNED_MODELS)
def test_model_has_user_id_column(model: type) -> None:
    column = model.__table__.columns.get("user_id")
    assert column is not None, f"{model.__name__} 缺少 user_id 列"
    assert column.nullable is False
    assert len(column.foreign_keys) == 1
    fk = next(iter(column.foreign_keys))
    assert fk.column.table.name == "users"


@pytest.mark.asyncio
async def test_create_all_builds_user_id() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_local() as db:
        project = Project(id="p1", name="n", style="urban", user_id="u1")
        db.add(project)
        await db.flush()
        assert project.user_id == "u1"
    await engine.dispose()
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend
uv run pytest tests/test_user_owned_mixin.py -q
```

Expected: FAIL，`Project` 等模型无 `user_id` 列（`column is None`）。

- [ ] **Step 3: 在 base.py 新增 `UserOwnedMixin`**

打开 `backend/app/models/base.py`，在文件末尾新增（保留现有 `TimestampMixin`）：

```python
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import declared_attr


class UserOwnedMixin:
    """为业务表提供 `user_id` 归属外键。

    存在意义：项目要求项目/资产/配置/任务等按用户严格隔离，所有归属表统一通过本混入
    携带指向 `users.id` 的外键，避免在每个模型里重复声明。`ondelete="CASCADE"` 保证
    删除用户时其全部业务数据级联清除。新建库 `create_all` 直接生成 NOT NULL 列；存量库
    由 sql/009 先加 NULL 列回填后再收紧为 NOT NULL。
    """

    @declared_attr
    def user_id(cls) -> Mapped[str]:  # noqa: N805
        return mapped_column(
            String(64),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
            comment="归属用户 ID",
        )
```

> `base.py` 顶部已 `from sqlalchemy.orm import Mapped, mapped_column`；只需补充 `ForeignKey, String` 与 `declared_attr` 的导入。

- [ ] **Step 4: 给 9 张表挂上混入**

在以下每个模型类的基类列表加入 `UserOwnedMixin`（放在 `Base` 之后、`TimestampMixin` 之前/之后均可），并在文件顶部 `from app.models.base import TimestampMixin` 改为 `from app.models.base import TimestampMixin, UserOwnedMixin`：

- `studio_projects.py`：`class Project(Base, UserOwnedMixin, TimestampMixin):`
- `studio_assets.py`：`Actor` / `Scene` / `Prop` / `Costume` 四个类
- `studio_prompts_files_timeline.py`：`PromptTemplate` / `FileItem`（注意 `FileItem.__tablename__ == "files"`）
- `llm.py`：`Provider` / `Model`
- `task.py`：`GenerationTask`

> `ModelSettings` **不挂**本混入（它走每用户单行改造，见 Task 2）。`Character`/`Shot`/`Chapter`/各 `*_links`/`timeline_clips`/`ActorImage` 等子表**不加** `user_id`（通过父实体间接隔离）。

- [ ] **Step 5: 运行测试，确认通过**

```bash
cd backend
uv run pytest tests/test_user_owned_mixin.py -q
```

Expected: PASS（11 参数化 + 1 建表用例全过）。

- [ ] **Step 6: Commit**

```bash
cd backend
git add app/models/base.py app/models/studio_projects.py app/models/studio_assets.py app/models/studio_prompts_files_timeline.py app/models/llm.py app/models/task.py tests/test_user_owned_mixin.py
git commit -m "feat: add user_id ownership column to business tables"
```

---

## Task 2: `model_settings` 单例 → 每用户一行

**Files:**
- Modify: `backend/app/models/llm.py`（`ModelSettings`）
- Modify: `backend/app/services/llm/manage.py`（`get_or_create_settings` / `get_model_settings` / `update_model_settings`）
- Test: `backend/tests/test_model_settings_per_user.py`

- [ ] **Step 1: 阅读现状**

```bash
cd backend
sed -n '258,330p' app/services/llm/manage.py
grep -rn "get_or_create_settings\|get_model_settings\|update_model_settings\|ModelSettings" app/services/llm/ app/api/v1/routes/
```

记录：当前 `get_or_create_settings` 如何定位 id=1、有哪些调用方（runtime/resolver/路由）。

- [ ] **Step 2: 编写失败测试**

创建 `backend/tests/test_model_settings_per_user.py`：

```python
"""model_settings 每用户一行语义测试。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.user import User
from app.services.llm import manage as llm_manage


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = session_local()
    db.add(User(id="u1", username="a", hashed_password="h"))
    db.add(User(id="u2", username="b", hashed_password="h"))
    await db.flush()
    return db, engine


@pytest.mark.asyncio
async def test_get_or_create_settings_is_per_user() -> None:
    db, engine = await _build_session()
    async with db:
        s1 = await llm_manage.get_or_create_settings(db, user_id="u1")
        s1_again = await llm_manage.get_or_create_settings(db, user_id="u1")
        s2 = await llm_manage.get_or_create_settings(db, user_id="u2")

        assert s1.user_id == "u1"
        assert s1.id == s1_again.id  # 幂等：同用户拿到同一行
        assert s2.user_id == "u2"
        assert s1.id != s2.id  # 不同用户不同行
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_model_settings_isolated() -> None:
    db, engine = await _build_session()
    async with db:
        await llm_manage.update_model_settings(db, user_id="u1", api_timeout=99)
        s1 = await llm_manage.get_model_settings(db, user_id="u1")
        s2 = await llm_manage.get_model_settings(db, user_id="u2")

        assert s1.api_timeout == 99
        assert s2.api_timeout == 30  # 默认值，未被 u1 的修改影响
    await engine.dispose()
```

> 若 `update_model_settings` 实际签名用 schema 对象而非关键字参数，按实际签名调整测试与下方实现的入参，保持"按 `user_id` upsert"语义不变。

- [ ] **Step 3: 运行测试，确认失败**

```bash
cd backend
uv run pytest tests/test_model_settings_per_user.py -q
```

Expected: FAIL（`get_or_create_settings` 不接受 `user_id`，或 `ModelSettings` 无 `user_id`）。

- [ ] **Step 4: 改造 `ModelSettings` 模型**

打开 `backend/app/models/llm.py`，将 `ModelSettings` 改为带 `user_id` 唯一列（保留自增主键，便于 FK 关系），并加 `user_id` 唯一约束：

```python
from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint  # 顶部补 UniqueConstraint


class ModelSettings(Base):
    """模型管理设置（每用户一行）。

    说明：
    - 由"单表单行 id=1 全局设置"改为"每 user_id 一行"；读写均按 user_id 定位。
    - 外键使用 SET NULL，避免删除模型时导致设置行不可更新。
    """

    __tablename__ = "model_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="设置行 ID")
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="归属用户 ID（每用户一行）",
    )
    default_text_model_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("models.id", ondelete="SET NULL"), nullable=True, comment="默认文本模型 ID"
    )
    default_image_model_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("models.id", ondelete="SET NULL"), nullable=True, comment="默认图片模型 ID"
    )
    default_video_model_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("models.id", ondelete="SET NULL"), nullable=True, comment="默认视频模型 ID"
    )
    api_timeout: Mapped[int] = mapped_column(Integer, nullable=False, default=30, comment="API 超时（秒）")
    log_level: Mapped[LogLevel] = mapped_column(String(16), nullable=False, default=LogLevel.info, comment="日志级别")

    default_text_model: Mapped["Model | None"] = relationship(foreign_keys=[default_text_model_id])
    default_image_model: Mapped["Model | None"] = relationship(foreign_keys=[default_image_model_id])
    default_video_model: Mapped["Model | None"] = relationship(foreign_keys=[default_video_model_id])

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_model_settings_user"),
    )
```

- [ ] **Step 5: 改造 `manage.py` 的 settings 读写**

打开 `backend/app/services/llm/manage.py`，把三个函数改为按 `user_id`：

```python
async def get_or_create_settings(db: AsyncSession, *, user_id: str) -> ModelSettings:
    """按 user_id 获取设置行；不存在则惰性创建（每用户一行，幂等）。"""
    result = await db.execute(select(ModelSettings).where(ModelSettings.user_id == user_id))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = ModelSettings(user_id=user_id)
        db.add(settings)
        await db.flush()
    return settings


async def get_model_settings(db: AsyncSession, *, user_id: str) -> ModelSettings:
    """读取某用户的模型设置（不存在则惰性创建默认值）。"""
    return await get_or_create_settings(db, user_id=user_id)


async def update_model_settings(db: AsyncSession, *, user_id: str, **fields: object) -> ModelSettings:
    """按 user_id upsert 模型设置；只更新传入的字段。"""
    settings = await get_or_create_settings(db, user_id=user_id)
    for key, value in fields.items():
        if value is not None:
            setattr(settings, key, value)
    await db.flush()
    return settings
```

> 保持与现有实现一致的签名风格（若原本接收 `ModelSettingsUpdate` schema，则改为 `(db, *, user_id, body)` 并在函数内取字段）。同步更新 `runtime.py` / `resolver.py` 中调用 settings 的地方，传入对应 `user_id`（这些运行时调用所需的 `user_id` 来自任务/请求上下文，见 Task 11 对任务上下文的处理）。

- [ ] **Step 6: 运行测试，确认通过**

```bash
cd backend
uv run pytest tests/test_model_settings_per_user.py -q
```

Expected: PASS（2 passed）。

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/models/llm.py app/services/llm/manage.py tests/test_model_settings_per_user.py
git commit -m "feat: make model_settings per-user instead of singleton"
```

---

## Task 3: 资产唯一约束改为按用户

**Files:**
- Modify: `backend/app/models/studio_assets.py`
- Modify: `backend/app/services/studio/entity_crud.py`（`_ensure_global_name_available`）
- Test: 复用 `tests/test_isolation_assets.py`（Task 7 写入；本任务先改约束）

- [ ] **Step 1: 修改 `Actor` 唯一约束**

打开 `backend/app/models/studio_assets.py`，把 `Actor` 的：

```python
    __table_args__ = (
        Index("ix_actors_name", "name"),
        UniqueConstraint("name", name="uq_actors_name"),
    )
```

改为：

```python
    __table_args__ = (
        Index("ix_actors_name", "name"),
        UniqueConstraint("user_id", "name", name="uq_actors_user_name"),
    )
```

- [ ] **Step 2: 对 `Scene` / `Prop` / `Costume` 做相同处理**

对这三个模型，若存在 `UniqueConstraint("name", ...)`，一律改为 `UniqueConstraint("user_id", "name", name="uq_<table>_user_name")`；若原本没有 name 唯一约束则不新增。

```bash
cd backend
grep -n "UniqueConstraint" app/models/studio_assets.py
```

- [ ] **Step 3: 改 `_ensure_global_name_available` 为按用户判重**

打开 `backend/app/services/studio/entity_crud.py`，阅读 `_ensure_global_name_available`（约 38-58 行）：

```bash
cd backend
sed -n '38,58p' app/services/studio/entity_crud.py
```

将其 name 唯一性查询从"全局判重"改为"当前用户内判重"，新增 `user_id` 入参并在 `where` 加 `Model.user_id == user_id`。函数重命名为 `_ensure_user_name_available`（同步更新 `create_entity`/`update_entity` 调用处）。具体改造在 Task 7 与服务过滤一起落地、一起测试。

- [ ] **Step 4: 语法校验 + Commit**

```bash
cd backend
python -m py_compile app/models/studio_assets.py
git add app/models/studio_assets.py
git commit -m "feat: scope asset name uniqueness to user"
```

---

## Task 4: 迁移脚本 `sql/009`

**Files:**
- Create: `backend/sql/009-add-users-and-user-isolation.sql`

- [ ] **Step 1: 编写幂等迁移脚本**

创建 `backend/sql/009-add-users-and-user-isolation.sql`。沿用 `sql/005` 的 `information_schema` + `PREPARE/EXECUTE` 幂等写法。对以下 11 张表（注意 file 表名是 `files`）：`projects, actors, scenes, props, costumes, prompt_templates, files, providers, models, model_settings, generation_tasks`，每张表执行三步：①加 `user_id VARCHAR(64) NULL`；②回填；③收紧为 NOT NULL。回填规则：

- 一般表：`UPDATE <t> SET user_id = @admin_id WHERE user_id IS NULL`
- `prompt_templates`：仅回填非系统模板，系统模板保持 NULL：`UPDATE prompt_templates SET user_id = @admin_id WHERE user_id IS NULL AND is_system = 0`，且该表 `user_id` 收紧时用 `NULL`（系统模板共享）—— 即 `prompt_templates.user_id` 保持 NULLABLE，不收紧。
- `model_settings`：原有单行（id=1）回填为管理员；若原本无行则跳过。

脚本开头先取管理员 ID：

```sql
-- 009-add-users-and-user-isolation.sql
-- 为 11 类业务表添加 user_id 归属并将历史数据归属初始管理员（幂等）。
-- 前置：users 表已由 init_db() 建出，且 seed_initial_admin() 已播种管理员。

SET @admin_id = (SELECT id FROM users WHERE is_admin = 1 ORDER BY created_at LIMIT 1);

-- ============ projects ============
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'projects' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col = 0,
  "ALTER TABLE projects ADD COLUMN user_id VARCHAR(64) NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

UPDATE projects SET user_id = @admin_id WHERE user_id IS NULL;

SET @is_null = (SELECT IS_NULLABLE FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'projects' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@is_null = 'YES',
  "ALTER TABLE projects MODIFY COLUMN user_id VARCHAR(64) NOT NULL COMMENT '归属用户 ID'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_fk = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'projects' AND CONSTRAINT_NAME = 'fk_projects_user');
SET @sql = IF(@has_fk = 0,
  "ALTER TABLE projects ADD CONSTRAINT fk_projects_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE, ADD INDEX ix_projects_user_id (user_id)",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ============ 其余表：actors / scenes / props / costumes / files / providers / models / generation_tasks ============
-- 对每张表重复上述 4 个语句块（替换表名与约束/索引名）。

-- ============ prompt_templates（系统模板共享，user_id 保持 NULLABLE）============
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'prompt_templates' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col = 0,
  "ALTER TABLE prompt_templates ADD COLUMN user_id VARCHAR(64) NULL COMMENT '归属用户 ID（系统模板为 NULL，全用户共享）'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

UPDATE prompt_templates SET user_id = @admin_id WHERE user_id IS NULL AND is_system = 0;
-- 不收紧为 NOT NULL；不加 FK（保持系统模板 NULL 语义）。仅加索引便于过滤。
SET @has_idx = (SELECT COUNT(*) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'prompt_templates' AND INDEX_NAME = 'ix_prompt_templates_user_id');
SET @sql = IF(@has_idx = 0,
  "ALTER TABLE prompt_templates ADD INDEX ix_prompt_templates_user_id (user_id)",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ============ model_settings ============
SET @has_col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'model_settings' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@has_col = 0,
  "ALTER TABLE model_settings ADD COLUMN user_id VARCHAR(64) NULL COMMENT '归属用户 ID（每用户一行）'",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

UPDATE model_settings SET user_id = @admin_id WHERE user_id IS NULL;
SET @is_null = (SELECT IS_NULLABLE FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'model_settings' AND COLUMN_NAME = 'user_id');
SET @sql = IF(@is_null = 'YES',
  "ALTER TABLE model_settings MODIFY COLUMN user_id VARCHAR(64) NOT NULL COMMENT '归属用户 ID', ADD UNIQUE KEY uq_model_settings_user (user_id), ADD CONSTRAINT fk_model_settings_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
```

> 注意：`prompt_templates.user_id` 保持 NULLABLE 与 ORM `UserOwnedMixin`（NOT NULL）冲突 —— **`PromptTemplate` 不挂 `UserOwnedMixin`**，改为单独声明 `user_id: Mapped[str | None]`（nullable=True）。**回到 Task 1 Step 4 时已将 `PromptTemplate` 排除出混入清单，改为本任务的单独可空列声明**（见下方修正）。

- [ ] **Step 2: 修正 `PromptTemplate` 的 `user_id` 为可空（系统模板共享）**

打开 `backend/app/models/studio_prompts_files_timeline.py`，`PromptTemplate` **不使用** `UserOwnedMixin`，单独声明：

```python
    user_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="归属用户 ID；系统预置模板为 NULL，全用户共享",
    )
```

> 顶部补充 `from sqlalchemy import ForeignKey, String`（若未导入）。同步把 Task 1 的 `test_user_owned_mixin.py` 中 `PromptTemplate` 从 `OWNED_MODELS`（要求 NOT NULL）移除，单独断言它有可空 `user_id` 列。

- [ ] **Step 3: 语法校验 + Commit**

```bash
cd backend
python -m py_compile app/models/studio_prompts_files_timeline.py
git add sql/009-add-users-and-user-isolation.sql app/models/studio_prompts_files_timeline.py tests/test_user_owned_mixin.py
git commit -m "feat: add sql/009 user_id migration and nullable user_id for system prompts"
```

---

## Task 5: 修复受影响的现有测试夹具

**Files:**
- Modify: 现有创建 project/asset/file/provider/model/generation_task 记录但未传 `user_id` 的测试

- [ ] **Step 1: 找出因 NOT NULL `user_id` 而新失败的测试**

```bash
cd backend
uv run pytest -q 2>&1 | grep -iE "IntegrityError|NOT NULL|user_id|FAILED" | head -40
```

记录失败清单（预期是直接 `db.add(Project(...))` / `Actor(...)` 等未带 `user_id` 的测试夹具）。

- [ ] **Step 2: 给这些夹具补 `user_id`**

在相关测试的建数据处统一补 `user_id="<test-user-id>"`，并确保先插入一条对应 `User`（满足 FK）。对使用 `_FakeStudioDB` 等内存桩的测试，给桩补充对 `user_id` 字段的存储与过滤（按桩实际结构最小改动）。

> 这是机械修复，逐个文件按 Step 1 清单处理。每修一批跑一次 `uv run pytest <file> -q` 确认。

- [ ] **Step 3: 全量回归**

```bash
cd backend
uv run pytest -q
```

Expected: 因 `user_id` NOT NULL 引入的失败全部消除（与本计划无关的既有失败不在本任务范围）。

- [ ] **Step 4: Commit**

```bash
cd backend
git add tests/
git commit -m "test: backfill user_id in fixtures for ownership columns"
```

---

## Task 6: projects service + route 加 `user_id`

**Files:**
- Modify: 项目 service（先定位）、`backend/app/api/v1/routes/studio/projects.py`
- Test: `backend/tests/test_isolation_projects.py`

- [ ] **Step 1: 定位项目 service 与现有签名**

```bash
cd backend
grep -rn "select(Project)\|def .*project" app/services/studio/ | grep -iv link | head -30
grep -nE "current_user|get_current_user|Depends|async def" app/api/v1/routes/studio/projects.py
```

记录：项目的 list/create/get/update/delete 在哪个 service 文件、函数签名，以及路由如何调用。

- [ ] **Step 2: 编写失败测试**

创建 `backend/tests/test_isolation_projects.py`：

```python
"""项目按 user_id 隔离测试。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.user import User
# from app.services.studio.<项目service> import list_projects, create_project  # 按 Step 1 定位填入


async def _session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = sm()
    db.add_all([User(id="u1", username="a", hashed_password="h"), User(id="u2", username="b", hashed_password="h")])
    await db.flush()
    return db, engine


@pytest.mark.asyncio
async def test_list_projects_only_returns_own() -> None:
    db, engine = await _session()
    async with db:
        await create_project(db, user_id="u1", name="P1", style="urban")
        await create_project(db, user_id="u2", name="P2", style="urban")

        u1_projects = await list_projects(db, user_id="u1")
        assert {p.name for p in u1_projects} == {"P1"}
    await engine.dispose()
```

> import 与函数签名按 Step 1 实际结果填写；若 create 走 schema 入参，按实际签名构造。

- [ ] **Step 3: 运行测试，确认失败**

```bash
cd backend
uv run pytest tests/test_isolation_projects.py -q
```

Expected: FAIL（`list_projects`/`create_project` 不接受 `user_id`，或返回了别人的项目）。

- [ ] **Step 4: service 加 `user_id`**

对项目 service 的每个查询/创建函数：

- list/get/update/delete：函数签名加 `*, user_id: str`，查询 `where(Project.user_id == user_id)`；get/update/delete 对单条记录额外校验 `obj.user_id == user_id`，不符按"未找到"处理（`entity_not_found`）。
- create：写入时 `Project(..., user_id=user_id)`。

改造模式（以 list 为例，与设计文档 Section 3 一致）：

```python
# 改造前
async def list_projects(db: AsyncSession) -> list[Project]:
    result = await db.execute(select(Project))
    return list(result.scalars().all())

# 改造后
async def list_projects(db: AsyncSession, *, user_id: str) -> list[Project]:
    result = await db.execute(select(Project).where(Project.user_id == user_id))
    return list(result.scalars().all())
```

- [ ] **Step 5: 路由透传 `current_user.id`**

打开 `backend/app/api/v1/routes/studio/projects.py`，为每个端点新增依赖并透传：

```python
from app.dependencies import get_current_user
from app.models.user import User

@router.get("/projects", ...)
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return paginated_response(await project_service.list_projects(db, user_id=current_user.id))
```

对 create/get/update/delete 同理传 `user_id=current_user.id`。

- [ ] **Step 6: 运行测试，确认通过 + 回归**

```bash
cd backend
uv run pytest tests/test_isolation_projects.py -q
uv run pytest tests/ -k project -q
```

Expected: 隔离测试 PASS；项目相关既有测试在补全 `current_user` override 后通过（测试可用 `app.dependency_overrides[get_current_user]` 注入一个固定测试用户）。

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/services/studio app/api/v1/routes/studio/projects.py tests/test_isolation_projects.py
git commit -m "feat: isolate projects by user_id"
```

---

## Task 7: 资产 service + route 加 `user_id`

**Files:**
- Modify: `backend/app/services/studio/entity_crud.py`、`entities.py`、`backend/app/api/v1/routes/studio/entities.py`
- Test: `backend/tests/test_isolation_assets.py`

- [ ] **Step 1: 阅读 entity_crud 现有函数**

```bash
cd backend
sed -n '38,330p' app/services/studio/entity_crud.py
grep -nE "current_user|Depends|async def|StudioEntitiesService" app/api/v1/routes/studio/entities.py
```

- [ ] **Step 2: 编写失败测试**

创建 `backend/tests/test_isolation_assets.py`，覆盖：
1. 用户只能列出/获取自己的资产；
2. 同名资产在不同用户间互不冲突（验证 Task 3 的 `(user_id, name)` 约束）。

```python
"""资产按 user_id 隔离 + 同名跨用户不冲突测试。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.user import User
from app.services.studio.entity_crud import create_entity, list_entities_paginated


async def _session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = sm()
    db.add_all([User(id="u1", username="a", hashed_password="h"), User(id="u2", username="b", hashed_password="h")])
    await db.flush()
    return db, engine


@pytest.mark.asyncio
async def test_same_actor_name_allowed_across_users() -> None:
    db, engine = await _session()
    async with db:
        await create_entity(db, kind="actor", user_id="u1", name="主角", style="urban")
        # 不同用户同名应成功，不触发唯一约束
        await create_entity(db, kind="actor", user_id="u2", name="主角", style="urban")
        await db.flush()

        u1_actors = await list_entities_paginated(db, kind="actor", user_id="u1")
        assert all(a.user_id == "u1" for a in u1_actors.items)
    await engine.dispose()
```

> 函数名/入参（`kind` 还是分函数、是否 schema 入参、分页返回结构）按 Step 1 实际签名调整。

- [ ] **Step 3: 运行测试，确认失败**

```bash
cd backend
uv run pytest tests/test_isolation_assets.py -q
```

Expected: FAIL。

- [ ] **Step 4: 改造 entity_crud + entities**

- `_ensure_global_name_available` → `_ensure_user_name_available(db, *, user_id, ...)`，查询加 `.where(Model.user_id == user_id)`。
- `list_entities_paginated` / `get_entity` / `update_entity` / `delete_entity`：加 `*, user_id: str`，查询/单条校验过滤 `user_id`。
- `create_entity`：实体写入 `user_id=user_id`。
- `StudioEntitiesService`（`entities.py`）：构造时或方法上接收 `user_id` 并透传给 `entity_crud`。建议在 `__init__(self, db, *, user_id)` 注入，方法内部使用 `self._user_id`。

- [ ] **Step 5: 路由透传**

打开 `backend/app/api/v1/routes/studio/entities.py`，端点新增 `current_user` 依赖；构造 `StudioEntitiesService(db, user_id=current_user.id)`。

- [ ] **Step 6: 运行测试 + 回归 + Commit**

```bash
cd backend
uv run pytest tests/test_isolation_assets.py -q
uv run pytest tests/ -k "asset or entit" -q
git add app/services/studio/entity_crud.py app/services/studio/entities.py app/api/v1/routes/studio/entities.py tests/test_isolation_assets.py
git commit -m "feat: isolate assets by user_id with per-user name uniqueness"
```

---

## Task 8: prompts service + route 加 `user_id`（放行系统模板）

**Files:**
- Modify: prompts service（`app/services/studio/` 下，先定位）、`backend/app/api/v1/routes/studio/prompts.py`
- Test: `backend/tests/test_isolation_prompts.py`

- [ ] **Step 1: 定位 prompts service**

```bash
cd backend
grep -rln "select(PromptTemplate)\|PromptTemplate" app/services/studio/ | head
grep -nE "current_user|Depends|async def" app/api/v1/routes/studio/prompts.py
```

- [ ] **Step 2: 编写失败测试**

创建 `backend/tests/test_isolation_prompts.py`，核心断言：**用户能看到"自己的模板 + 系统模板"，但看不到别人的模板**。

```python
@pytest.mark.asyncio
async def test_list_returns_own_and_system_not_others() -> None:
    db, engine = await _session()
    async with db:
        db.add_all([
            PromptTemplate(id="t1", category="role", name="mine", content="c", user_id="u1"),
            PromptTemplate(id="t2", category="role", name="other", content="c", user_id="u2"),
            PromptTemplate(id="t3", category="role", name="sys", content="c", user_id=None, is_system=True),
        ])
        await db.flush()
        items = await list_prompt_templates(db, user_id="u1")
        assert {t.name for t in items} == {"mine", "sys"}
    await engine.dispose()
```

- [ ] **Step 3: 运行测试，确认失败**

```bash
cd backend
uv run pytest tests/test_isolation_prompts.py -q
```

Expected: FAIL。

- [ ] **Step 4: service 过滤（含系统模板放行）**

查询条件为 `(PromptTemplate.user_id == user_id) | (PromptTemplate.is_system.is_(True))`：

```python
from sqlalchemy import or_

async def list_prompt_templates(db: AsyncSession, *, user_id: str) -> list[PromptTemplate]:
    result = await db.execute(
        select(PromptTemplate).where(
            or_(PromptTemplate.user_id == user_id, PromptTemplate.is_system.is_(True))
        )
    )
    return list(result.scalars().all())
```

- create：写入 `user_id=user_id`、`is_system=False`。
- update/delete：先取记录，若 `is_system` 为真 → 维持既有"禁止删改系统模板"逻辑；否则校验 `user_id == 当前用户`，不符按未找到处理。

- [ ] **Step 5: 路由透传 + 测试 + Commit**

```bash
cd backend
uv run pytest tests/test_isolation_prompts.py -q
uv run pytest tests/ -k prompt -q
git add app/services/studio app/api/v1/routes/studio/prompts.py tests/test_isolation_prompts.py
git commit -m "feat: isolate prompt templates by user_id while sharing system presets"
```

---

## Task 9: files service + route 加 `user_id`

**Files:**
- Modify: `backend/app/services/studio/files.py`、`backend/app/api/v1/routes/studio/files.py`
- Test: `backend/tests/test_isolation_files.py`

- [ ] **Step 1: 阅读 files.py 查询函数**

```bash
cd backend
sed -n '62,230p' app/services/studio/files.py
grep -nE "current_user|Depends|async def" app/api/v1/routes/studio/files.py
```

- [ ] **Step 2: 编写失败测试**

创建 `backend/tests/test_isolation_files.py`：用户 `list_files_paginated` / `get_file_detail` / `delete_file` 仅命中自己的文件；访问他人文件按未找到处理。

- [ ] **Step 3: 运行确认失败 → service 加 `user_id` → 路由透传**

- `list_files_paginated`：加 `*, user_id`，`where(FileItem.user_id == user_id)`。
- `get_file_detail` / `update_file_meta` / `delete_file` / `build_download_response`：取记录后校验 `user_id`，不符 `entity_not_found`。
- `upload_file`：写入 `FileItem(..., user_id=user_id)`。
- 路由各端点加 `current_user` 并透传。

- [ ] **Step 4: 测试 + 回归 + Commit**

```bash
cd backend
uv run pytest tests/test_isolation_files.py -q
uv run pytest tests/ -k file -q
git add app/services/studio/files.py app/api/v1/routes/studio/files.py tests/test_isolation_files.py
git commit -m "feat: isolate files by user_id"
```

---

## Task 10: llm providers/models service + route 加 `user_id`

**Files:**
- Modify: `backend/app/services/llm/manage.py`、`backend/app/api/v1/routes/llm.py`（及其子路由）
- Test: `backend/tests/test_isolation_llm.py`

- [ ] **Step 1: 阅读 manage.py provider/model 函数 + 路由**

```bash
cd backend
sed -n '48,257p' app/services/llm/manage.py
grep -rnE "current_user|Depends|async def" app/api/v1/routes/llm.py app/api/v1/routes/llm/ 2>/dev/null | head -40
```

- [ ] **Step 2: 编写失败测试**

创建 `backend/tests/test_isolation_llm.py`：provider/model 列表与详情按 `user_id` 隔离；`get_or_create_settings` 已在 Task 2 覆盖，这里验证 provider/model。

- [ ] **Step 3: 确认失败 → service 加 `user_id`**

- `list_providers_paginated` / `get_provider` / `update_provider` / `delete_provider`：加 `*, user_id`，过滤/校验 `Provider.user_id == user_id`。
- `create_provider`：写入 `user_id=user_id`，并保持 `created_by=用户名`（审计字段，见 spec Section 1）。
- `list_models_paginated` / `get_model` / `update_model` / `delete_model` / `create_model`：同理按 `Model.user_id` 处理。

- [ ] **Step 4: 路由透传 `current_user.id`**

`llm` 路由各端点加 `current_user` 依赖，settings 端点改为调用 `get_model_settings(db, user_id=current_user.id)` / `update_model_settings(db, user_id=current_user.id, ...)`。

- [ ] **Step 5: 处理运行时解析路径的 `user_id`**

`runtime.py` / `resolver.py` / `provider_resolver.py` 在执行生成时需要"某用户的 provider/model/settings"。它们的 `user_id` 来源是触发生成的任务上下文（见 Task 11：`generation_tasks.user_id`）。在这些 resolver 函数签名补 `user_id` 并由调用方（任务执行器）透传任务的 `user_id`。

```bash
cd backend
grep -rn "get_or_create_settings\|get_model_settings\|select(Provider)\|select(Model)" app/services/llm/runtime.py app/services/llm/resolver.py app/services/llm/provider_resolver.py
```

- [ ] **Step 6: 测试 + 回归 + Commit**

```bash
cd backend
uv run pytest tests/test_isolation_llm.py tests/test_model_settings_per_user.py -q
uv run pytest tests/ -k "llm or provider or model" -q
git add app/services/llm app/api/v1/routes/llm* tests/test_isolation_llm.py
git commit -m "feat: isolate llm providers/models/settings by user_id"
```

---

## Task 11: generation_tasks 查询按 `user_id` 过滤

**Files:**
- Modify: 任务查询 service（先定位）、任务相关路由、任务创建处（写入 `user_id`）
- Test: `backend/tests/test_isolation_tasks.py`

- [ ] **Step 1: 定位任务列表/详情/创建**

```bash
cd backend
grep -rln "select(GenerationTask)\|GenerationTask(" app/services/ app/core/ | head
grep -rnE "current_user|Depends|async def" app/api/v1/routes/ | grep -i task | head
```

记录：任务在哪里被创建（需在创建处带上发起用户的 `user_id`）、列表/详情查询在哪。

- [ ] **Step 2: 编写失败测试**

创建 `backend/tests/test_isolation_tasks.py`：用户任务列表只含自己发起的任务；访问他人任务详情按未找到处理。

- [ ] **Step 3: 确认失败 → 改造**

- 任务创建：所有 `GenerationTask(...)` 处补 `user_id=<发起用户>`。发起用户来自触发该任务的路由的 `current_user.id`，需将 `user_id` 沿任务创建调用链透传到任务封装层（`app/core/task_manager/` / `tasks/`）。
- 任务列表/详情 service：加 `*, user_id`，过滤 `GenerationTask.user_id == user_id`。
- 任务相关路由：加 `current_user` 依赖并透传。

> 这是本计划穿透链最长的一处。若任务创建发生在深层执行器、当前无法直接拿到 `current_user`，在任务封装入口（路由→service→task_manager）逐层补 `user_id` 参数。Step 1 的定位结果决定具体改哪几个签名。

- [ ] **Step 4: 测试 + 回归 + Commit**

```bash
cd backend
uv run pytest tests/test_isolation_tasks.py -q
uv run pytest tests/ -k task -q
git add app/ tests/test_isolation_tasks.py
git commit -m "feat: isolate generation tasks by user_id"
```

---

## Task 12: 全量回归、迁移演练与客户端同步

**Files:** 无新增；校验 Task 1-11 整体。

- [ ] **Step 1: 后端全量测试**

```bash
cd backend
uv run pytest -q
```

Expected: 全绿（与本计划无关的既有失败若仍存在，单独记录，不在本计划范围）。

- [ ] **Step 2: pylint 关键模块**

```bash
cd backend
uv run pylint app/models/base.py app/models/llm.py app/services/llm/manage.py app/services/studio/entity_crud.py app/services/studio/files.py
```

Expected: 无 error 级别问题。

- [ ] **Step 3: MySQL 迁移演练（如有本地 MySQL）**

在一份带存量数据的 MySQL 库上执行 `sql/009`，确认：①幂等可重复执行无报错；②历史数据 `user_id` 均为初始管理员；③系统模板 `user_id` 仍为 NULL。

```bash
# 示例（按本地连接参数调整）
mysql -u root -p jellyfish < sql/009-add-users-and-user-isolation.sql
mysql -u root -p jellyfish < sql/009-add-users-and-user-isolation.sql  # 第二次应幂等无报错
```

- [ ] **Step 4: 重新生成前端客户端并类型检查**

```bash
# 终端 1：后端
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# 终端 2：前端
cd front
pnpm run openapi:update
pnpm exec tsc --noEmit
```

Expected: 客户端重新生成成功；`tsc` 不因本计划新增类型错误（`user_id` 由后端从 token 推断，不进入请求体，前端调用签名通常不变）。

- [ ] **Step 5: 更新架构文档**

更新 `site/content/docs/architecture/`：记录"业务数据按 `user_id` 隔离、`model_settings` 每用户一行、系统提示词模板共享"的现行实现。

- [ ] **Step 6: Commit**

```bash
cd backend && git add -A && git commit -m "chore: regenerate client and docs for user data isolation"
```

---

## Self-Review Notes

- **Spec 覆盖（Section 1/3/5）**：
  - Section 1 数据模型：Task 1（11 表 `user_id`）、Task 2（`model_settings` 每用户）、Task 3（资产唯一约束）、Task 4（`PromptTemplate` 可空 `user_id` 共享系统模板、`created_by` 保留）。
  - Section 3 service 层过滤：Task 6-11 覆盖 projects/assets/prompts/files/llm/tasks，路由仅透传 `current_user.id`、不写隔离逻辑（符合"核心原则"）。管理员绕过隔离（传目标 `user_id`）属计划 B。
  - Section 5 迁移与初始化：Task 4（`sql/009` 幂等 + 历史归属管理员）；`seed_initial_admin` 与启动顺序已在 auth-foundation 计划完成。
- **占位符扫描**：Task 6-11 的 service/route 改造给出了统一改造模式 + 代表性完整示例 + 逐函数清单，未用 "TODO/TBD"；少数函数签名标注"按 Step 1 定位结果填写"是因实际 service 文件名/签名与 spec 不一致，已附定位命令，不属遗留占位。
- **类型一致性**：`user_id: str`（String(64)，对齐 `users.id`）贯穿模型、service、迁移；`get_or_create_settings(db, *, user_id)` 在 Task 2 定义、Task 10 Step 4 复用一致；`_ensure_user_name_available` 在 Task 3 重命名、Task 7 使用一致。
- **已知风险点**：Task 11（任务 `user_id` 穿透）链路最长，执行时以 Step 1 定位结果为准逐层补参；Task 5（测试夹具回填）工作量取决于现有测试规模，建议按文件分批提交。
```