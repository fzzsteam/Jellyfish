---
title: "用户积分计费"
description: "当前真实生效的积分账户、流水、定价、报价令牌、并发账本与任务计费闭环。"
weight: 40
---

本文记录当前真实生效的用户积分计费实现。所有生成类操作（文本 / 图片 / 视频）在调用 provider 之前都必须先冻结积分，结束后按任务结局结算为扣减或解冻；同步文本操作则在单次请求内完成"冻结 → 执行 → 扣减/解冻"。

## 数据模型

涉及三张表与两处既有表的扩展列，迁移脚本为 `backend/sql/010-add-points-billing.sql`（幂等 MySQL，沿用 `sql/009` 的 `information_schema` + `PREPARE/EXECUTE` 写法；新建库由 `create_all` 直接生成，存量库执行 `010` 回填）。

### `user_points` —— 用户积分账户（每用户一行）

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `user_id` | VARCHAR(64) PK，FK `users.id` ON DELETE CASCADE | 与用户一一对应 |
| `balance` | BIGINT | **总余额，包含被冻结的部分** |
| `frozen` | BIGINT | 当前被冻结的部分 |

派生量：`available = balance - frozen`。

CHECK 约束：

- `balance >= 0`
- `frozen >= 0`
- `frozen <= balance`（冻结不能超过总余额，从而保证 `available >= 0`）

> 关键语义：`balance` 是"含冻结"的总余额。冻结 / 解冻只移动 `frozen`，不动 `balance`；只有消费才扣 `balance`，只有充值才加 `balance`。这样流水可以始终用 `(balance_after, frozen_after)` 还原任意时刻的账户快照。

### `point_transactions` —— 积分流水（只追加）

| 列 | 说明 |
| --- | --- |
| `id` | 主键 |
| `user_id` | FK `users.id` |
| `type` | `PointTransactionType`：`recharge` / `freeze` / `consume` / `unfreeze` |
| `amount` | 该笔涉及的积分数量。`freeze` / `consume` / `unfreeze` 始终为正；`recharge` 可正可负（负向扣减余额） |
| `balance_after` | 该笔落地后的 `balance` 快照 |
| `frozen_after` | 该笔落地后的 `frozen` 快照 |
| `source` | 来源标记 |
| `billing_id` | 计费单据 ID，用于幂等 |
| `business_type` / `business_id` | 业务上下文 |
| `model_id` | FK `models.id` ON DELETE SET NULL |
| `pricing_snapshot` | JSON，冻结时的定价快照 |
| `cascade_group_id` | `VARCHAR(64) NULL`，带索引 `ix_point_transactions_cascade_group_id`。级联分组键：同一次操作的 root `billing_id`；充值/手动调整为 NULL（见下文"级联计费与分组视图"） |
| `remark` / `created_by` / `created_at` | 审计字段 |

幂等保证：`UniqueConstraint(billing_id, type)`。同一 `billing_id` 的 `freeze` 只能落一次，`consume` 与 `unfreeze` 互斥（同一 `billing_id` 只能命中其一）。

### `models.unit_points` —— 每模型积分单价

`BIGINT NOT NULL DEFAULT 0`。`010` 先加可空列 → 回填 0 → 收紧为 `NOT NULL DEFAULT 0`（默认 0 = 免费模型）。

### `generation_tasks.billing_id` —— 任务计费单据列

`VARCHAR(64) NULL`，带索引 `ix_generation_tasks_billing_id`。可空表示未计费；非空表示该任务挂在某个冻结单据上。

## 定价

`app/services/points/pricing.py` 提供统一定价入口 `compute_required_points(...)`，返回 `int`。

- 文本 / 图片：`required = unit_points`（图片分辨率当前不参与计价，`IMAGE_RESOLUTION_FACTOR = 1.0`）。
- 视频：`required = unit_points × duration_seconds × resolution_factor`。
  - 分辨率因子：`{"720p": 1.0, "1080p": 2.0}`。
  - 未登记的分辨率 → `UnsupportedResolutionError`。
- 统一用 `Decimal` + `ROUND_CEILING` 向上取整为整数积分，避免小数截断导致少扣。
- `generation_count` 当前必须为 `1`（多轮生成能力后续再放开，否则 `ValueError`）。

视频分辨率从契约层到 provider 适配器端到端标准化（720p / 1080p），**计费分辨率 == 实际生成分辨率**，不存在"按低分辨率报价、按高分辨率生成"的缝隙。

## 报价令牌

`app/services/points/quote_tokens.py` 负责签发 / 校验报价令牌，独立于登录鉴权令牌（使用独立异常 `QuoteTokenError`，不复用认证异常体系）。

- 算法：JWT，`type = points_quote`。
- 有效期：`POINTS_QUOTE_EXPIRE_SECONDS`（默认 300 秒 = 5 分钟）。
- Claims：`sub`（用户）、`business_type`、`model_id`、`params_hash`、`required_points`、`iat`、`exp`。
- `params_hash` 由 `hash_quote_params` 生成：对参数做排序后 JSON 序列化，再 SHA-256。排序保证相同参数哈希稳定。

报价令牌的作用是把"前端展示给用户的积分预估"与"后端真正冻结的积分"绑定：冻结时后端会用同一份参数重新计算 `required_points` 与 `params_hash`，与令牌中的声明比对，不一致即视为报价已变化（`POINTS_QUOTE_CHANGED`）。

## 账本与并发模型

`app/services/points/ledger.py` 实现账户变更，采用"Redis 用户锁 + 行锁"双层互斥。

### 余额模型

| 动作 | 对账户的影响 |
| --- | --- |
| `freeze(amount)` | `frozen += amount`；要求 `available >= amount` |
| `consume(amount)` | `balance -= amount` 且 `frozen -= amount`（把先前冻结的部分确认为实扣） |
| `unfreeze(amount)` | `frozen -= amount`（把先前冻结的部分退还为可用） |
| `recharge(amount)` | `balance += amount`；允许 `amount` 为负（扣减充值），但负向充值不能侵蚀到已冻结部分（即不能让 `frozen > balance`），且必须填写 `remark` |

每次变更后都写入一条 `point_transactions`，记录 `balance_after` / `frozen_after`。

### 并发控制：锁顺序

每次账户变更按以下顺序执行：

```text
1. 获取 Redis 用户锁（key = points:user:{user_id}，SET NX PX，带 token）
2. SELECT ... FOR UPDATE  user_points 行
3. SELECT ... FOR UPDATE  对应的 freeze 流水行（consume / unfreeze 时）
4. 变更余额并写入流水
5. db.commit()               ← 必须在释放锁之前提交
6. 释放 Redis 用户锁（Lua compare-token 释放，避免误删别人的锁）
```

- Redis 锁 TTL = `POINTS_LOCK_TTL_MS`（默认 30000ms），覆盖一次完整的账户变更。
- 抢锁等待上限 = `POINTS_LOCK_WAIT_MS`（默认 3000ms），超时抛 `PointsOperationBusyError`，**绝不降级为无锁**。
- 指数退避上限 = `POINTS_LOCK_RETRY_MAX_BACKOFF_MS`（默认 250ms）。
- `commit()` 必须在释放 Redis 锁之前完成，否则会出现"锁已释放但事务未落库"的窗口。

### 幂等

- `(billing_id, type)` 唯一约束保证同一单据同一动作只会落库一次；重复触发会抛 `IntegrityError`，账本捕获后重新读取已存在的流水返回。
- `consume` 与 `unfreeze` 对同一 `billing_id` 互斥：只能命中其中之一。

### 异常

- `InsufficientPointsError`：带 `available` / `required` / `shortfall`，便于前端提示差额。
- `BillingStateError`：账户 / 单据状态非法（如对已 consume 的单据再次 unfreeze）。
- `PointsOperationBusyError`：Redis 抢锁超时，前端应提示用户稍后重试，不自动重试。

## 接口

| 方法 & 路径 | 说明 |
| --- | --- |
| `POST /api/v1/points/quote` | 报价；解析模型（显式传入否则取用户默认模型，做归属校验），返回 `required_points` / `available_points` / `sufficient` / `quote_token` |
| `GET /api/v1/points/me` | 当前用户积分摘要 |
| `GET /api/v1/points/transactions` | 当前用户流水，支持过滤与分页（扁平视图） |
| `GET /api/v1/points/transactions/grouped` | 当前用户流水，按 `cascade_group_id` 聚合为操作组，组内按 `billing_id` 折叠为单据生命周期，按组分页 |
| `GET /api/v1/admin/users/{id}/points` | 管理员查看指定用户积分摘要 |
| `GET /api/v1/admin/users/{id}/points/transactions` | 管理员查看指定用户流水 |
| `POST /api/v1/admin/users/{id}/points/recharge` | 管理员充值 |

### `PointsDomainError` → 错误码

积分域异常统一经由 `PointsDomainError` 暴露稳定的 `error_code`，供前端按码处理：

- `INSUFFICIENT_POINTS`
- `POINTS_QUOTE_CHANGED`
- `POINTS_OPERATION_BUSY`
- `MODEL_NOT_OWNED`
- 其它（令牌无效 / 单据状态非法 等）

`main.py` 注册了专用 handler，确保 `ApiResponse` 信封内 `data.error_code` 结构化保留，前端不会因异常丢失错误码。

### 用户初始化

管理员创建用户（`admin.create_user`）时同步初始化 `UserPoints(balance=0, frozen=0)`。

## 异步任务计费闭环

图片 / 视频 / 脚本类异步任务的计费采用"先冻结、后结算"。

### 冻结（`freeze_for_task`）

在 `tm.create(billing_id=...)` **之前**调用：

1. 解码报价令牌。
2. 用当前模型 + 当前参数重新解析模型并重算价格。
3. 校验报价一致性（`required_points` 与 `params_hash` 与令牌声明一致，否则 `POINTS_QUOTE_CHANGED`）。
4. 执行冻结，返回 `FrozenBilling`（携带 `billing_id`）。

### 结算

任务执行在 `run_task_celery` 的 `finally` 中统一结算（**结算 chokepoint**：所有异步任务都从此处进入结算，避免散落多处）：

- 成功 → `consume`。
- 失败 / 取消 → `unfreeze`。
- 幂等：重复结算命中唯一约束即安全返回。

两套结算入口按执行环境区分：

- Celery 同步 worker 执行链 → `settle_task_billing_sync`。
- 进程内 asyncio 执行的 merge / variant 任务 → `settle_task_billing_async`（避免在已有 event loop 中再起 `asyncio.run` 的陷阱）。

### 立即取消

取消路由在能立即取消时直接 `unfreeze`，不等待 worker 结算。

### 视频分辨率一致性

视频的分辨率（720p / 1080p）从契约层 → `build_run_args` → provider 适配器端到端标准化，**计费分辨率 == 实际生成分辨率**。

## 同步文本计费

`run_billed_text_operation` 在单次请求内完成"冻结 → 执行业务操作 → 结算"：

- 成功 → `consume`。
- 失败（含 `CancelledError`）→ `unfreeze`。

当前共 **11 个同步端点**与 **11 个异步端点**携带 `quote_token`。

## 异步任务级联计费（auto-extract / auto-prepare）

divide（`write_to_db=true`）与 extract 两个异步任务在 `apply_result` 阶段会自动触发两类**此前漏费**的下游调用，必须在级联中补冻结/结算：

### auto-prepare 图片任务（N 张图片）

`auto_prepare_chapter_shots_sync` 循环为每个无图资产调用 `_schedule_image_task_sync` 创建 `GenerationTask(image_generation)` 行。修复后每张图片在创建任务行**之前**：

1. 按用户默认图片模型单价冻结积分（`calculate_points(category="image", ...)`）。
2. 生成 `billing_id` 并写入 `GenerationTask.billing_id`。
3. 后续 `run_task_celery` 的 `finally → settle_task_billing_sync` 在图片任务终态时自动 consume / unfreeze——无需额外结算代码。

容错：

- **余额不足**（`InsufficientPointsError`）：auto-prep 是 best-effort 级联，仅跳过该张图片（不建任务、不冻结），级联继续，divide/extract 主流程不受影响。
- **任务行创建失败**（`begin_nested` 抛错）：解冻已落库的冻结，避免悬挂。
- **桥接方式**：Celery worker 同步上下文通过 `asyncio.run(...)` 调用异步账本（与 `settle_task_billing_sync` 同款），账本内部自行 COMMIT。

### auto-extract 文本（1 次文本调用，缓存感知）

`apply_auto_extraction_after_division` 在 divide 写库后串行调用 `generate_extraction_result`，该调用可能命中缓存也可能真正调用 LLM。修复后采用**乐观冻结 + 缓存感知结算**：

1. 按用户默认文本模型单价冻结积分。
2. 调用 `generate_extraction_result`。
3. `from_cache=True`（LLM 未调用）→ **解冻**（用户免费）；`from_cache=False`（LLM 已调用）→ **消费**。
4. 余额不足 → 跳过 auto-extract（仍执行 auto-prep），divide 主流程不受影响。
5. 提取异常 → 解冻已落库的冻结后上抛。

默认文本模型未配置时跳过计费但仍尝试提取（可能命中缓存）；缓存未命中则提取在 LLM 构建处抛 503，与历史行为一致。

### 级联分组键 `cascade_group_id`

上述级联会让一次"一键提取分镜"产生多个互不关联的 `billing_id`（divide 文本 + auto-extract 文本 + N 张图片），用户在扁平流水里无法看出"这次操作总共花了多少"。`cascade_group_id` 把它们归到一组：

- **写入规则**：`freeze_points` 默认把 `cascade_group_id` 设为自身的 `billing_id`（root 任务自动成组）。级联调用方显式传入 root 的 `billing_id`，让子单据归入父组。
  - divide / extract 自身冻结 → `cascade_group_id = 自己的 billing_id`（root）。
  - auto-extract 文本冻结 → `cascade_group_id = divide 的 billing_id`。
  - auto-prep 图片冻结 → `cascade_group_id = 当前操作 root billing_id`（divide 或 extract）。
  - 充值 / 管理员调整 → `NULL`（`recharge()` 不经过 `freeze_points`）。
- **复制规则**：`consume_frozen` / `unfreeze_frozen` 从对应 freeze 行复制 `cascade_group_id`（与复制 `business_type` 同款），保证同一单据生命周期的 freeze/consume/unfreeze 始终同组。
- **透传链路**：`auto_prepare_chapter_shots_sync` / `_schedule_image_task_sync` / `apply_auto_extraction_after_division` 均新增 `cascade_root_billing_id` 参数；两个 executor（`DivideTaskExecutor` / `ExtractTaskExecutor`）在 `apply_result` 传入 `ctx.task.billing_id` 作为 root。

### 分组查询 `GET /transactions/grouped`

`list_grouped_transactions` 按 `cascade_group_id` 聚合，**按组分页**（组时间 = 组内最早 `created_at`），避免组跨页切断。返回结构：

- `OperationGroup`：一个操作组，含 `cascade_group_id` / `business_type` / `created_at` / `total_net`（= 组内 Σ consume，反映对余额的实际净消耗）/ `billings[]`。
- `BillingLifecycle`：按 `billing_id` 折叠的单据生命周期，`status` 由该 `billing_id` 下的事件推断（有 consume → `settled`；有 unfreeze → `refunded`；仅 freeze → `frozen`），`net_amount` = consume 金额。
- `cascade_group_id IS NULL` 的流水（充值等）按 `billing_id` 兜底成单成员组。

前端积分流水页提供"明细 / 按操作"视图切换：明细视图走扁平 `/transactions`，按操作视图走 `/transactions/grouped`，单据生命周期可展开查看 freeze/consume/unfreeze 明细。`total_net` 天然揭示"预估总额 vs 实际净消耗"的差额（部分子任务因积分不足被跳过时净消耗会小于预估）。



## Celery Beat 对账

`points.reconcile_stale_freezes` 由 Celery Beat 调度，周期 **300 秒**，兜底处理因 worker 崩溃 / 网络中断等原因停留在"已冻结但未结算"状态的单据：

- 扫描条件：冻结年龄 > `POINTS_RECONCILE_MIN_AGE_SECONDS`（默认 1800 秒 = 30 分钟）。
- 批大小：`POINTS_RECONCILE_BATCH_SIZE`（默认 100），控制单次 Beat tick 的 DB 负载。
- 结算规则：
  - 对应任务成功 → `consume`。
  - 对应任务失败 / 取消 → `unfreeze`。
  - 对应任务未到终态 → 保留冻结，等下一轮。
  - 找不到对应任务（孤儿单据）→ `unfreeze`。
- 逐行容错：单条异常不中断整批；全部操作幂等。

## 前端职责

- `usePointsQuote` hook：防抖、防竞态地拉取报价；`quote_token` 一路透传到提交请求。
- `PointsCostHint` 组件：展示预估积分与余额是否充足。
- 接入文本 / 图片 / 视频生成 UI，带 `canSubmit` 门控（积分不足时禁用提交）。
- 错误处理：遇到 `POINTS_QUOTE_CHANGED` 刷新报价（不自动重试）；遇到 `INSUFFICIENT_POINTS` 引导充值（不自动重试）。
- `PointsPage`：积分摘要 + 分页 / 可过滤的流水列表。
- 主布局导航加"可用 X"徽标。
- 管理员用户页：积分摘要列 + 充值 + 查看流水。
- `ModelsTab`：`unit_points` 编辑器（按模型类别后缀区分）。

## 配置项

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `POINTS_QUOTE_EXPIRE_SECONDS` | `300` | 报价令牌有效期（秒） |
| `POINTS_LOCK_TTL_MS` | `30000` | Redis 用户锁 TTL（毫秒） |
| `POINTS_LOCK_WAIT_MS` | `3000` | 抢锁等待上限（毫秒），超时抛 `PointsOperationBusyError` |
| `POINTS_LOCK_RETRY_MAX_BACKOFF_MS` | `250` | 抢锁指数退避上限（毫秒） |
| `POINTS_RECONCILE_MIN_AGE_SECONDS` | `1800` | 对账扫描的最小冻结年龄（秒） |
| `POINTS_RECONCILE_BATCH_SIZE` | `100` | 对账单批扫描上限 |

> 生产环境要求部署 Redis：积分账户锁依赖 Redis，**Redis 不可用时锁层不会降级为无操作**，抢锁会直接失败。本地开发使用 Docker Compose 提供的 Redis 即可。

## 迁移与回填

- 迁移脚本：`backend/sql/010-add-points-billing.sql`，幂等，可在 `009` 之后任意时机执行。
- 回填：为存量用户补 `user_points(balance=0, frozen=0)` 行；`models.unit_points` 回填为 `0`（即所有存量模型默认免费，由管理员按需调价）。
- 新建库由 `create_all` 直接生成完整表结构，`010` 仅用于存量库升级。
