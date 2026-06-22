# 用户积分计费 Implementation Plan

> **状态：已落地。** 当前真实生效的实现见 [architecture/points-billing.md](/docs/architecture/points-billing/)。本文件为原始任务计划，保留用于追溯决策与拆分。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为所有真实模型调用增加按用户积分试算、冻结、成功消费、失败解冻、管理员充值、流水审计和前端费用提示。

**Architecture:** 使用 `user_points` 保存用户积分物化状态，使用只追加的 `point_transactions` 保存审计流水；所有余额变更由集中式 points service 在 Redis 用户锁和数据库行锁内完成。图片、视频和异步文本任务在创建时冻结并通过统一任务终态结算，同步文本接口使用统一执行器包裹业务调用；Celery Beat 定期补偿未结算冻结记录。

**Tech Stack:** FastAPI、SQLAlchemy async/sync、MySQL/SQLite、Redis、Celery/Beat、PyJWT、React 18、TypeScript、Ant Design、OpenAPI generated client、pytest。

---

## 文件结构

### 后端新增

- `backend/app/models/points.py`：用户积分状态与积分流水 ORM。
- `backend/app/schemas/points.py`：积分、流水、试算和充值 DTO。
- `backend/app/services/points/pricing.py`：文本、图片、视频统一计价器。
- `backend/app/services/points/quote_tokens.py`：5 分钟有效的签名试算凭证。
- `backend/app/services/points/locks.py`：Redis 用户级原子锁。
- `backend/app/services/points/ledger.py`：冻结、消费、解冻、充值和查询。
- `backend/app/services/points/billing.py`：模型解析、试算、正式复算和业务执行编排。
- `backend/app/services/points/reconciliation.py`：未结算冻结补偿逻辑。
- `backend/app/services/points/__init__.py`：points service 稳定导出。
- `backend/app/api/v1/routes/points.py`：当前用户积分和试算 API。
- `backend/app/tasks/points.py`：Celery Beat 补偿任务入口。
- `backend/sql/010-add-points-billing.sql`：幂等 MySQL 迁移。
- `backend/tests/test_points_models.py`：模型与约束测试。
- `backend/tests/test_points_pricing.py`：计价测试。
- `backend/tests/test_points_quote_tokens.py`：试算凭证测试。
- `backend/tests/test_points_locks.py`：Redis 锁 token 与释放测试。
- `backend/tests/test_points_ledger.py`：账本状态与幂等测试。
- `backend/tests/test_points_api.py`：用户和管理员 API 测试。
- `backend/tests/test_points_task_billing.py`：异步任务冻结与结算测试。
- `backend/tests/test_points_sync_billing.py`：同步文本成功/失败测试。
- `backend/tests/test_points_reconciliation.py`：补偿规则测试。

### 后端修改

- `backend/app/models/llm.py`：`Model.unit_points`。
- `backend/app/models/task.py`：`GenerationTask.billing_id`。
- `backend/app/core/db.py`：注册 points ORM。
- `backend/app/config.py`：锁超时、试算有效期和补偿阈值配置。
- `backend/app/core/security.py`：不修改认证 token 语义；试算 token 独立实现。
- `backend/app/schemas/llm.py`：模型 DTO 增加 `unit_points`。
- `backend/app/core/contracts/video_generation.py`：标准化 `720p/1080p` 分辨率。
- `backend/app/api/v1/routes/film/video_request.py`：视频请求增加 `resolution` 与 `quote_token`。
- `backend/app/api/v1/routes/studio/image_tasks.py`：图片生成请求增加 `quote_token`。
- `backend/app/api/v1/routes/script_processing.py`：同步/异步文本请求携带 `quote_token` 并接入统一计费执行器。
- `backend/app/api/v1/routes/film/generated_video.py`：视频任务创建前冻结。
- `backend/app/api/v1/routes/film/task_status.py`：立即取消时解冻。
- `backend/app/services/film/generated_video.py`：分辨率进入最终供应商输入。
- `backend/app/services/studio/image_task_runner.py`：图片任务创建前冻结。
- `backend/app/services/script_processing_tasks.py`：异步文本任务统一冻结。
- `backend/app/services/worker/task_executor.py`：任务终态结算钩子。
- `backend/app/tasks/execute_task.py`：Celery 执行完成后统一结算。
- `backend/app/core/celery_app.py`：注册 points task 与 Beat schedule。
- `backend/app/api/v1/routes/admin/users.py`：管理员积分查看、流水和充值。
- `backend/app/api/v1/__init__.py`：挂载 points 路由。
- `backend/app/main.py`：结构化积分领域错误响应。
- `deploy/compose/docker-compose.yml`：新增单实例 `celery-beat` 服务。
- `deploy/docker/supervisord.conf`：单容器部署增加 Beat 进程。

### 前端新增

- `front/src/hooks/usePointsQuote.ts`：防抖试算、加载、余额不足和 quote token 状态。
- `front/src/components/points/PointsCostHint.tsx`：统一“将消耗 X 积分”提示。
- `front/src/pages/points/PointsPage.tsx`：用户积分摘要和流水页。

### 前端修改

- `front/src/pages/aiStudio/models/ModelsTab.tsx`：模型积分单价编辑与展示。
- `front/src/pages/admin/AdminUserListPage.tsx`：用户积分摘要列。
- `front/src/pages/admin/AdminUserDetailPage.tsx`：积分摘要、充值和流水。
- `front/src/pages/aiStudio/chapter/ChapterStudio.tsx`：图片、视频、分镜提示词任务试算及 quote token。
- `front/src/pages/aiStudio/chapter/components/ChapterRawTextEditorModal.tsx`：文本操作试算。
- `front/src/pages/aiStudio/project/ProjectWorkbench/tabs/ChaptersTab.tsx`：章节提取试算。
- `front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx`：镜头提取试算。
- `front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx`：资产分析和图片生成试算。
- `front/src/pages/aiStudio/assets/assetAdapters.ts`：图片任务透传 quote token。
- `front/src/layouts/MainLayout.tsx`：积分明细入口与可用积分摘要。
- `front/src/App.tsx`：积分页路由。
- `front/src/services/generated/**`：OpenAPI 自动生成，不手工修改。

### 文档修改

- `site/content/docs/architecture/points-billing.md`：落地后的当前架构与状态流转。
- `site/content/docs/architecture/_index.md`：架构文档入口。
- `README.md`：迁移编号、Celery Beat 启动和部署命令。

---

### Task 1: 积分持久化模型与迁移

**Files:**
- Create: `backend/app/models/points.py`
- Create: `backend/sql/010-add-points-billing.sql`
- Create: `backend/tests/test_points_models.py`
- Modify: `backend/app/models/llm.py`
- Modify: `backend/app/models/task.py`
- Modify: `backend/app/core/db.py`
- Modify: `backend/app/schemas/llm.py`
- Modify: `backend/tests/test_llm_manage.py`

- [ ] **Step 1: 写失败测试，固定 ORM 字段和 DTO 契约**

```python
def test_model_has_non_negative_unit_points():
    column = Model.__table__.c.unit_points
    assert column.default.arg == 0
    assert column.nullable is False

def test_points_tables_and_task_billing_column_exist():
    assert UserPoints.__table__.c.user_id.unique
    assert set(PointTransactionType) == {
        PointTransactionType.recharge,
        PointTransactionType.freeze,
        PointTransactionType.consume,
        PointTransactionType.unfreeze,
    }
    assert GenerationTask.__table__.c.billing_id.nullable
```

- [ ] **Step 2: 运行测试并确认因模型缺失失败**

Run: `cd backend && uv run pytest tests/test_points_models.py tests/test_llm_manage.py -q`

Expected: FAIL，错误包含 `No module named 'app.models.points'` 或 `unit_points` 不存在。

- [ ] **Step 3: 实现 ORM 与 Schema**

`Model.unit_points` 使用 `BigInteger`、`nullable=False`、`default=0`。新增：

```python
class PointTransactionType(str, Enum):
    recharge = "recharge"
    freeze = "freeze"
    consume = "consume"
    unfreeze = "unfreeze"

class UserPoints(Base, TimestampMixin):
    __tablename__ = "user_points"
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    frozen: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

class PointTransaction(Base):
    __tablename__ = "point_transactions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[PointTransactionType] = mapped_column(String(32), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    frozen_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    business_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    business_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("models.id", ondelete="SET NULL"), nullable=True)
    pricing_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
```

增加 `CheckConstraint` 保证 `balance >= 0`、`frozen >= 0`、`frozen <= balance`，增加 `UniqueConstraint("billing_id", "type")`。`GenerationTask.billing_id` 为可空、索引字符串。

- [ ] **Step 4: 编写幂等 MySQL 迁移**

`010` 必须使用 `information_schema` 检查后再创建字段、表、索引和约束；为所有现有用户插入 `balance=0, frozen=0`，并为 `models.unit_points` 回填 `0` 后收紧非空。

- [ ] **Step 5: 运行模型测试**

Run: `cd backend && uv run pytest tests/test_points_models.py tests/test_llm_manage.py -q`

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add backend/app/models/points.py backend/app/models/llm.py backend/app/models/task.py backend/app/core/db.py backend/app/schemas/llm.py backend/sql/010-add-points-billing.sql backend/tests/test_points_models.py backend/tests/test_llm_manage.py
git commit -m "feat: add points billing persistence"
```

### Task 2: 计价器与试算凭证

**Files:**
- Create: `backend/app/services/points/pricing.py`
- Create: `backend/app/services/points/quote_tokens.py`
- Create: `backend/app/services/points/__init__.py`
- Create: `backend/tests/test_points_pricing.py`
- Create: `backend/tests/test_points_quote_tokens.py`
- Modify: `backend/app/config.py`

- [ ] **Step 1: 写计价失败测试**

```python
@pytest.mark.parametrize(
    ("category", "unit_points", "duration", "resolution", "expected"),
    [
        ("text", 12, None, None, 12),
        ("image", 20, None, None, 20),
        ("video", 10, 5, "720p", 50),
        ("video", 10, 5, "1080p", 100),
    ],
)
def test_calculate_points(category, unit_points, duration, resolution, expected):
    assert calculate_points(
        category=category,
        unit_points=unit_points,
        duration_seconds=duration,
        resolution=resolution,
        generation_count=1,
    ) == expected

def test_unknown_video_resolution_is_rejected():
    with pytest.raises(UnsupportedResolutionError):
        calculate_points(category="video", unit_points=10, duration_seconds=5, resolution="4k")
```

- [ ] **Step 2: 运行并确认 RED**

Run: `cd backend && uv run pytest tests/test_points_pricing.py -q`

Expected: FAIL，`pricing` 模块不存在。

- [ ] **Step 3: 实现纯计价器**

定义常量：

```python
IMAGE_RESOLUTION_FACTOR = Decimal("1.0")
VIDEO_RESOLUTION_FACTORS = {"720p": Decimal("1.0"), "1080p": Decimal("2.0")}
```

`calculate_points()` 校验非负整数 `unit_points`、`generation_count == 1`；视频要求正整数时长并规范化分辨率大小写；使用 `Decimal` 和 `ROUND_CEILING` 返回整数。

- [ ] **Step 4: 写试算 token 失败测试**

```python
def test_quote_token_round_trip_and_expiry(monkeypatch):
    claims = QuoteClaims(
        user_id="u1",
        business_type="video_generation",
        model_id="video-model",
        params_hash=hash_quote_params({"duration_seconds": 5, "resolution": "1080p"}),
        required_points=100,
    )
    token = create_quote_token(claims)
    assert decode_quote_token(token, expected_user_id="u1").required_points == 100
    with pytest.raises(QuoteTokenError):
        decode_quote_token(token, expected_user_id="u2")
```

- [ ] **Step 5: 实现独立试算 token**

签名 payload 类型固定为 `points_quote`，包含 `sub`、`business_type`、`model_id`、`params_hash`、`required_points`、`iat`、`exp`。有效期读取 `settings.points_quote_expire_seconds`，默认 `300`。参数哈希对排序后的 JSON 使用 SHA-256。

- [ ] **Step 6: 运行测试并提交**

Run: `cd backend && uv run pytest tests/test_points_pricing.py tests/test_points_quote_tokens.py -q`

Expected: PASS。

```bash
git add backend/app/services/points backend/app/config.py backend/tests/test_points_pricing.py backend/tests/test_points_quote_tokens.py
git commit -m "feat: add points pricing and quote tokens"
```

### Task 3: Redis 原子锁与积分账本

**Files:**
- Create: `backend/app/services/points/locks.py`
- Create: `backend/app/services/points/ledger.py`
- Create: `backend/tests/test_points_locks.py`
- Create: `backend/tests/test_points_ledger.py`
- Modify: `backend/app/config.py`

- [ ] **Step 1: 写 Redis 锁失败测试**

测试必须验证：锁 key 为 `points:user:{user_id}`；`SET NX PX`；释放使用 Lua 比较 token 后删除；获取超时抛 `PointsOperationBusyError`，不能绕过 Redis 继续。

- [ ] **Step 2: 运行锁测试确认 RED**

Run: `cd backend && uv run pytest tests/test_points_locks.py -q`

Expected: FAIL，`locks` 模块不存在。

- [ ] **Step 3: 实现 RedisUserLock**

使用 `redis.asyncio.Redis.from_url(settings.celery_broker_url)`；token 使用 `secrets.token_urlsafe(24)`；默认锁 TTL `30_000ms`、最多等待 `3_000ms`、指数退避上限 `250ms`。释放脚本：

```lua
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
```

- [ ] **Step 4: 写账本失败测试**

覆盖：自动初始化用户积分；余额不足返回 available/required/shortfall；冻结、消费、解冻状态；重复结算幂等；消费与解冻互斥；正负充值；负充值不能侵占冻结积分；负充值备注必填。

- [ ] **Step 5: 运行账本测试确认 RED**

Run: `cd backend && uv run pytest tests/test_points_ledger.py -q`

Expected: FAIL，账本函数不存在。

- [ ] **Step 6: 实现账本服务**

稳定接口：

```python
async def get_points(db, *, user_id: str) -> UserPoints
async def freeze_points(db, *, user_id: str, billing_id: str, amount: int, model_id: str, business_type: str, business_id: str | None, snapshot: dict) -> PointTransaction
async def consume_frozen(db, *, user_id: str, billing_id: str) -> PointTransaction
async def unfreeze_frozen(db, *, user_id: str, billing_id: str, remark: str | None = None) -> PointTransaction
async def recharge(db, *, user_id: str, amount: int, created_by: str, remark: str | None) -> PointTransaction
```

每个变更函数必须先获取 Redis 用户锁，再分别使用带 `FOR UPDATE` 的 SQLAlchemy `select(UserPoints)` 和 `select(PointTransaction)` 锁定用户积分与对应冻结流水，在锁释放前 `await db.commit()`。数据库唯一约束冲突时回读已有流水作为幂等结果。

- [ ] **Step 7: 运行测试并提交**

Run: `cd backend && uv run pytest tests/test_points_locks.py tests/test_points_ledger.py -q`

Expected: PASS。

```bash
git add backend/app/services/points/locks.py backend/app/services/points/ledger.py backend/app/config.py backend/tests/test_points_locks.py backend/tests/test_points_ledger.py
git commit -m "feat: add concurrent points ledger"
```

### Task 4: 试算、余额、流水和管理员充值 API

**Files:**
- Create: `backend/app/schemas/points.py`
- Create: `backend/app/services/points/billing.py`
- Create: `backend/app/api/v1/routes/points.py`
- Create: `backend/tests/test_points_api.py`
- Modify: `backend/app/api/v1/routes/admin/users.py`
- Modify: `backend/app/api/v1/__init__.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/admin.py`

- [ ] **Step 1: 写 API 失败测试**

覆盖：`GET /points/me`；流水筛选；默认模型 `model_id=null` 试算返回 `resolved_model_id`；显式模型归属校验；管理员正负充值；非管理员 403；结构化 `INSUFFICIENT_POINTS`、`POINTS_QUOTE_CHANGED`、`POINTS_OPERATION_BUSY` 错误数据。

- [ ] **Step 2: 运行并确认 RED**

Run: `cd backend && uv run pytest tests/test_points_api.py -q`

Expected: FAIL，points 路由不存在。

- [ ] **Step 3: 实现模型解析与 quote**

`quote_points()` 复用现有 `get_model_by_category()`：显式 `model_id` 优先，否则读取用户默认模型。请求 DTO：

```python
class PointsQuoteRequest(BaseModel):
    business_type: str
    category: ModelCategoryKey
    model_id: str | None = None
    duration_seconds: int | None = Field(None, ge=1)
    resolution: Literal["720p", "1080p"] | None = None
    generation_count: Literal[1] = 1
```

响应包含 `resolved_model_id/name`、`using_default_model`、`required_points`、`available_points`、`sufficient`、`quote_token`。

- [ ] **Step 4: 实现 API 与领域错误处理**

新增 `PointsDomainError`，携带稳定字符串 `code`、HTTP status 和 `data`。`main.py` 注册专用 handler，返回现有 `ApiResponse` envelope，`data` 保存 available/required/shortfall 或新 quote；不能让通用 HTTP handler丢失结构化字段。

- [ ] **Step 5: 创建用户时初始化积分**

`admin.create_user()` 在同一事务中追加 `UserPoints(user_id=user.id, balance=0, frozen=0)`。

- [ ] **Step 6: 运行测试并提交**

Run: `cd backend && uv run pytest tests/test_points_api.py tests/test_admin_service.py tests/test_admin_api.py -q`

Expected: PASS。

```bash
git add backend/app/schemas/points.py backend/app/services/points/billing.py backend/app/api/v1/routes/points.py backend/app/api/v1/routes/admin/users.py backend/app/api/v1/__init__.py backend/app/main.py backend/app/services/admin.py backend/tests/test_points_api.py
git commit -m "feat: expose points billing APIs"
```

### Task 5: 异步任务冻结与终态结算

**Files:**
- Create: `backend/tests/test_points_task_billing.py`
- Modify: `backend/app/core/task_manager/manager.py`
- Modify: `backend/app/core/task_manager/stores.py`
- Modify: `backend/app/services/script_processing_tasks.py`
- Modify: `backend/app/services/studio/image_task_runner.py`
- Modify: `backend/app/api/v1/routes/studio/image_tasks.py`
- Modify: `backend/app/services/film/generated_video.py`
- Modify: `backend/app/api/v1/routes/film/video_request.py`
- Modify: `backend/app/api/v1/routes/film/generated_video.py`
- Modify: `backend/app/api/v1/routes/film/task_status.py`
- Modify: `backend/app/tasks/execute_task.py`

- [ ] **Step 1: 写任务计费失败测试**

覆盖：图片/视频/文本任务在创建前验证 quote；冻结成功后任务保存 `billing_id`；积分不足不创建任务、不入队；任务创建异常立即解冻；Celery 最终 `succeeded` 消费、`failed/cancelled` 解冻；立即 revoke 取消也解冻；重复终态结算幂等；复用已有活动任务不再次冻结。

- [ ] **Step 2: 运行并确认 RED**

Run: `cd backend && uv run pytest tests/test_points_task_billing.py -q`

Expected: FAIL，任务请求没有 `quote_token` 或任务无 `billing_id`。

- [ ] **Step 3: 增加任务 billing_id 持久化通道**

`TaskManager.create()` 和 store `create()` 增加可选 `billing_id`，写入 `GenerationTask.billing_id`，不把它藏在 payload JSON 中。

- [ ] **Step 4: 实现统一任务冻结助手**

```python
async def freeze_for_task(
    db: AsyncSession,
    *, user_id: str, quote_token: str, business_type: str,
    category: ModelCategoryKey, model_id: str | None,
    duration_seconds: int | None = None, resolution: str | None = None,
) -> FrozenBilling:
    # 重新解析模型和价格，校验 quote 后生成 billing_id 并冻结
```

图片所有创建请求、视频请求和 script processing 异步请求增加必填 `quote_token`。先检查活动任务复用，再冻结；创建失败捕获异常并调用 `unfreeze_frozen()` 后重新抛出。

- [ ] **Step 5: 标准化视频分辨率**

新增 `VideoResolution = Literal["720p", "1080p"]`；视频请求必须传 `resolution`，`build_run_args()` 写入 `VideoGenerationInput.resolution`。所有视频供应商适配器使用该标准值生成实际 payload；不支持时在供应商调用前拒绝，不能按 1080p 收费却生成 720p。

- [ ] **Step 6: 实现统一终态结算**

`run_task_celery()` 在 executor 返回后的 `finally` 中查询任务最终状态并调用 `settle_task_billing_sync(task_id)`：成功消费，失败/取消解冻，非终态不处理。取消 API 立即把任务标为 cancelled 时调用 async 结算。

- [ ] **Step 7: 运行相关测试并提交**

Run: `cd backend && uv run pytest tests/test_points_task_billing.py tests/test_task_execute.py tests/test_image_task_services.py tests/test_generated_video_service.py tests/test_task_status_api_responses.py -q`

Expected: PASS。

```bash
git add backend/app/core/task_manager backend/app/services/script_processing_tasks.py backend/app/services/studio/image_task_runner.py backend/app/api/v1/routes/studio/image_tasks.py backend/app/services/film/generated_video.py backend/app/api/v1/routes/film/video_request.py backend/app/api/v1/routes/film/generated_video.py backend/app/api/v1/routes/film/task_status.py backend/app/tasks/execute_task.py backend/tests/test_points_task_billing.py
git commit -m "feat: bill asynchronous model tasks"
```

### Task 6: 同步文本调用统一计费

**Files:**
- Create: `backend/tests/test_points_sync_billing.py`
- Modify: `backend/app/services/points/billing.py`
- Modify: `backend/app/api/v1/routes/script_processing.py`
- Modify: `backend/app/schemas/skills/script_processing.py`

- [ ] **Step 1: 写同步文本失败测试**

对每个同步真实 LLM 端点参数化测试：`divide`、`merge-entities`、`analyze-variants`、`check-consistency`、角色/道具/场景/服装分析、`optimize-script`、`simplify-script`、`extract`。验证成功消费、LLM 异常解冻、余额不足时 LLM mock 未调用、quote 变化时未调用。

- [ ] **Step 2: 运行并确认 RED**

Run: `cd backend && uv run pytest tests/test_points_sync_billing.py -q`

Expected: FAIL，请求 DTO 无 `quote_token` 或没有账本流水。

- [ ] **Step 3: 实现统一同步执行器**

```python
async def run_billed_text_operation(
    db: AsyncSession,
    *, user_id: str, quote_token: str, business_type: str,
    operation: Callable[[], Awaitable[T]],
) -> T:
    frozen = await freeze_for_call(
        db,
        user_id=user_id,
        quote_token=quote_token,
        business_type=business_type,
        category=ModelCategoryKey.text,
        model_id=None,
        duration_seconds=None,
        resolution=None,
    )
    try:
        result = await operation()
    except BaseException:
        await unfreeze_frozen(db, user_id=user_id, billing_id=frozen.billing_id)
        raise
    await consume_frozen(db, user_id=user_id, billing_id=frozen.billing_id)
    return result
```

同步 operation 若内部是同步 agent 调用，使用现有执行方式，不把阻塞调用迁移到 API 层。每个端点显式传稳定 `business_type`，提示词预览和不调用 LLM 的接口不接入。

- [ ] **Step 4: 运行测试并提交**

Run: `cd backend && uv run pytest tests/test_points_sync_billing.py tests/test_script_division.py tests/test_script_processing_agents.py -q`

Expected: PASS。

```bash
git add backend/app/services/points/billing.py backend/app/api/v1/routes/script_processing.py backend/app/schemas/skills/script_processing.py backend/tests/test_points_sync_billing.py
git commit -m "feat: bill synchronous text operations"
```

### Task 7: Celery Beat 补偿任务与部署

**Files:**
- Create: `backend/app/services/points/reconciliation.py`
- Create: `backend/app/tasks/points.py`
- Create: `backend/tests/test_points_reconciliation.py`
- Modify: `backend/app/core/celery_app.py`
- Modify: `backend/app/config.py`
- Modify: `deploy/compose/docker-compose.yml`
- Modify: `deploy/docker/supervisord.conf`

- [ ] **Step 1: 写补偿失败测试**

测试成功任务补消费、失败/取消补解冻、`pending/running/streaming` 保持冻结、任务不存在超过 30 分钟解冻、同步冻结超过 30 分钟解冻、未超过阈值不处理、重复扫描幂等。

- [ ] **Step 2: 运行并确认 RED**

Run: `cd backend && uv run pytest tests/test_points_reconciliation.py -q`

Expected: FAIL，reconciliation 模块不存在。

- [ ] **Step 3: 实现批量补偿**

按 `freeze.created_at < now - points_reconcile_min_age_seconds` 分页扫描，每批默认 `100`。对每条调用正常 `consume_frozen/unfreeze_frozen`；单条失败记录日志并继续，避免一条坏数据阻断全批。

- [ ] **Step 4: 注册 Celery Beat**

```python
celery_app.conf.beat_schedule = {
    "reconcile-stale-point-freezes": {
        "task": "points.reconcile_stale_freezes",
        "schedule": 300.0,
    }
}
```

`include` 同时包含 `app.tasks.execute_task` 与 `app.tasks.points`。

- [ ] **Step 5: 增加单 Beat 部署**

Compose 新增 `celery-beat`，命令为 `uv run celery -A app.core.celery_app:celery_app beat -l info`；supervisord 新增同一命令的 `[program:beat]`。文档明确生产环境只允许一个 Beat 调度器。

- [ ] **Step 6: 运行测试并提交**

Run: `cd backend && uv run pytest tests/test_points_reconciliation.py tests/test_task_execute.py -q`

Expected: PASS。

```bash
git add backend/app/services/points/reconciliation.py backend/app/tasks/points.py backend/app/core/celery_app.py backend/app/config.py deploy/compose/docker-compose.yml deploy/docker/supervisord.conf backend/tests/test_points_reconciliation.py
git commit -m "feat: reconcile stale point freezes"
```

### Task 8: OpenAPI 与 generated client 同步

**Files:**
- Modify: `front/openapi.json`
- Regenerate: `front/src/services/generated/**`

- [ ] **Step 1: 启动后端并生成 OpenAPI**

Run: `cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`

在另一终端运行：`cd front && pnpm run openapi:update`

Expected: `front/openapi.json` 和 generated client 出现 `PointsService`、管理员积分接口、`unit_points`、`quote_token`、视频 `resolution`。

- [ ] **Step 2: 检查 generated client**

Run: `rg -n "unit_points|quote_token|PointsQuote|recharge" front/src/services/generated front/openapi.json`

Expected: 所有字段与后端 Schema 一致，无手写 service。

- [ ] **Step 3: 提交**

```bash
git add front/openapi.json front/src/services/generated
git commit -m "chore: regenerate points billing client"
```

### Task 9: 模型价格、用户积分和充值界面

**Files:**
- Create: `front/src/pages/points/PointsPage.tsx`
- Modify: `front/src/pages/aiStudio/models/ModelsTab.tsx`
- Modify: `front/src/pages/admin/AdminUserListPage.tsx`
- Modify: `front/src/pages/admin/AdminUserDetailPage.tsx`
- Modify: `front/src/layouts/MainLayout.tsx`
- Modify: `front/src/App.tsx`

- [ ] **Step 1: 模型管理增加积分单价**

模型表单使用 `InputNumber min={0} precision={0}`，字段名 `unit_points`。单位提示按类别动态显示“积分/次”“积分/张”“积分/秒”；列表和详情同步展示，创建和更新通过 `LlmService` generated client 提交。

- [ ] **Step 2: 管理员用户页增加积分能力**

用户列表加载管理员积分摘要并展示可用/冻结；详情页展示总积分、冻结、可用，提供正负整数充值。负数时备注必填，提交后刷新摘要和流水。流水表包含时间、类型、金额、模型、业务类型、余额和备注。

- [ ] **Step 3: 用户积分页面与导航**

`/points` 展示当前用户摘要与可分页筛选流水。主导航增加“积分明细”，并在现有用户区域显示紧凑的“可用 X”摘要；不得把积分业务详情塞进任务中心。

- [ ] **Step 4: TypeScript 验证**

Run: `cd front && pnpm exec tsc --noEmit`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add front/src/pages/points/PointsPage.tsx front/src/pages/aiStudio/models/ModelsTab.tsx front/src/pages/admin/AdminUserListPage.tsx front/src/pages/admin/AdminUserDetailPage.tsx front/src/layouts/MainLayout.tsx front/src/App.tsx
git commit -m "feat: add points management interfaces"
```

### Task 10: 所有模型调用界面的费用提示与 quote token

**Files:**
- Create: `front/src/hooks/usePointsQuote.ts`
- Create: `front/src/components/points/PointsCostHint.tsx`
- Modify: `front/src/pages/aiStudio/chapter/ChapterStudio.tsx`
- Modify: `front/src/pages/aiStudio/chapter/components/ChapterRawTextEditorModal.tsx`
- Modify: `front/src/pages/aiStudio/project/ProjectWorkbench/tabs/ChaptersTab.tsx`
- Modify: `front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx`
- Modify: `front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx`
- Modify: `front/src/pages/aiStudio/assets/assetAdapters.ts`

- [ ] **Step 1: 实现共享试算 hook**

`usePointsQuote` 接受 `{ businessType, category, modelId, durationSeconds, resolution, enabled }`，参数变化后防抖调用 generated `PointsService`。返回 `quote`、`quoteToken`、`loading`、`error`、`canSubmit`、`refresh()`；组件卸载或参数变化时忽略旧响应，避免竞态覆盖新价格。

- [ ] **Step 2: 实现共享费用提示**

`PointsCostHint` 固定显示：加载中“正在计算积分”；充足“将消耗 X 积分”；不足“可用 X，本次需要 Y”；错误“暂时无法计算积分”。不足、加载和错误状态均阻止执行。

- [ ] **Step 3: 接入图片与视频生成**

ChapterStudio 的图片、视频生成按钮附近展示提示。图片按最终 `model_id` 试算；视频按最终 `model_id + shot.duration + resolution` 试算，并提供 `720p/1080p` 选择。提交时传当前 quote token；参数变化后旧 token 立即失效。资产图片生成通过 `AssetEditPageBase -> assetAdapters` 透传 token。

- [ ] **Step 4: 接入文本操作**

章节提取、镜头提取、资产信息分析、分镜提示词、脚本优化/简化/一致性检查均使用 `category=text` 获取默认模型报价，并把 token 传给对应 generated request。提示词预览、普通 CRUD 和任务查询不展示、不请求 quote。

- [ ] **Step 5: 处理价格变化与积分不足错误**

API 返回 `POINTS_QUOTE_CHANGED` 时更新 hook 中的新 quote，提示“积分价格已更新，请重新确认”且不自动重试。`INSUFFICIENT_POINTS` 使用响应 data 更新提示，不调用生成接口第二次。

- [ ] **Step 6: TypeScript 验证并提交**

Run: `cd front && pnpm exec tsc --noEmit`

Expected: PASS。

```bash
git add front/src/hooks/usePointsQuote.ts front/src/components/points/PointsCostHint.tsx front/src/pages/aiStudio/chapter/ChapterStudio.tsx front/src/pages/aiStudio/chapter/components/ChapterRawTextEditorModal.tsx front/src/pages/aiStudio/project/ProjectWorkbench/tabs/ChaptersTab.tsx front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx front/src/pages/aiStudio/assets/components/AssetEditPageBase.tsx front/src/pages/aiStudio/assets/assetAdapters.ts
git commit -m "feat: show points cost before model calls"
```

### Task 11: 架构文档、回归验证与最终审查

**Files:**
- Create: `site/content/docs/architecture/points-billing.md`
- Modify: `site/content/docs/architecture/_index.md`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-06-22-points-billing.md`

- [ ] **Step 1: 更新当前架构文档**

记录当前已落地的数据表、四种流水、计价公式、图片系数 `1.0`、视频 `720p=1.0/1080p=2.0`、默认模型解析、Redis+DB 锁顺序、任务终态结算、Celery Beat 补偿和前端职责。只写已实现事实，不混入未来自助充值方案。

- [ ] **Step 2: 更新部署与迁移说明**

README 的迁移范围更新至 `010`；增加 worker 与单实例 Beat 启动命令；说明 `POINTS_*` 配置默认值和生产环境 Redis 要求。

- [ ] **Step 3: 运行后端积分测试集**

Run:

```bash
cd backend && uv run pytest \
  tests/test_points_models.py \
  tests/test_points_pricing.py \
  tests/test_points_quote_tokens.py \
  tests/test_points_locks.py \
  tests/test_points_ledger.py \
  tests/test_points_api.py \
  tests/test_points_task_billing.py \
  tests/test_points_sync_billing.py \
  tests/test_points_reconciliation.py -q
```

Expected: PASS。

- [ ] **Step 4: 运行后端回归测试**

Run: `cd backend && uv run pytest -q`

Expected: PASS；若存在与本次无关的既有失败，记录完整测试名和原因，不能静默忽略。

- [ ] **Step 5: 运行前端类型和构建验证**

Run:

```bash
cd front && pnpm exec tsc --noEmit
cd front && pnpm run build
```

Expected: PASS。

- [ ] **Step 6: 验证迁移和部署配置**

Run:

```bash
rg -n "010-add-points-billing|celery-beat|points.reconcile_stale_freezes" README.md deploy backend/app/core/celery_app.py
git diff --check
```

Expected: 所有入口存在且 `git diff --check` 无输出。

- [ ] **Step 7: 提交**

```bash
git add site/content/docs/architecture/points-billing.md site/content/docs/architecture/_index.md README.md docs/superpowers/plans/2026-06-22-points-billing.md
git commit -m "docs: document points billing architecture"
```
