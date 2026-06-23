---
title: "积分流水可读性与级联消费透明化"
description: "让一键提取分镜的级联消费（文本+图片）在预估与流水中可见、可归组、可对账，并解决流水乱、对不上的体验问题。"
weight: 50
---

# 积分流水可读性与级联消费透明化

## 背景与问题

章节列表"一键提取分镜与自动准备"（`divideScriptAsync`，`write_to_db=true`）实际触发一条**级联链**，但前端积分展示只反映了其中第一步：

```
预估提示 PointsCostHint "将消耗 X 积分"   ← 只按 script_divide 文本单价试算
   ↓ 实际执行
1. script_divide：1 次文本 LLM          ← 预估只算了这一笔
2. 级联 script_extract：1 次文本 LLM     ← 预估未计（独立冻结/消费，无关联）
3. auto-prep：N 个图片生成任务           ← 预估未计，且 N 运行时才知
```

由此产生三类问题：

1. **预估不准**：用户看到的"消耗1积分"只覆盖第1步，级联的文本+图片消费完全缺失。
2. **流水对不上**：`point_transactions` 是 append-only，同一 `billing_id` 的 freeze/consume/unfreeze 是分散的多行，用户看不出"哪条解冻对应哪条冻结"；一次操作产生的多个 `billing_id` 也互不关联，看不出"这次操作总共花了多少"。
3. **积分不足静默跳过**：子任务（级联 extract、图片）积分不足时被 best-effort 跳过（只 log warning），用户不知道，导致"分镜拆出来了但资产/图缺失"且原因不可见。

> 覆盖范围：`script_divide`（一键提取）与 `script_extract`（独立提取）这两个**有级联**的操作。其他单次 LLM 操作（一致性检查、各类资产分析、剧本优化/精简）无级联，不受影响。

## 目标

- 操作前预估能体现真实级联消耗（文本精确 + 图片单价说明）。
- 流水按"计费单据生命周期"（同 `billing_id`）折叠，状态清晰。
- 同一次操作的多个 `billing_id` 归并为一组，显示总净消耗。
- 业务类型在展示层统一中文化。
- 积分不足以覆盖资产图时，操作入口有文案提示，用户理解"部分跳过"。

## 现状诊断（保留行为，不改）

### 级联计费链路

| 层级 | 触发点 | 冻结时机 | billing_id 来源 |
| --- | --- | --- | --- |
| divide 主任务 | `create_divide_task`（quote_token） | 任务创建前 | 任务行 `billing_id` |
| 级联 extract 文本 | `apply_auto_extraction_after_division` | divide 写库后同步执行 | 临时 uuid（**无任务行**） |
| auto-prep 图片 | `_schedule_image_task_sync` | auto-prep 每个新建/无图资产 | 每张图独立 uuid（有任务行） |

- divide 组 = divide文本 + extract文本 + N图片。
- extract 组（独立 `script_extract`）= extract文本 + N图片（无 divide）。

### 积分不足 = 静默跳过（best-effort）

- **divide 主任务**：积分在创建时经 quote_token 预冻结，前端 `canSubmit` 门控，不会中途不足。
- **级联 extract 文本**（`apply_auto_extraction_after_division`）：`InsufficientPointsError` → 跳过提取，仍跑 auto-prep（worker:416-430）。
- **auto-prep 图片**（`_schedule_image_task_sync`）：`InsufficientPointsError` → 跳过该图、不建任务，但资产实体仍建档+关联（auto_prep:866-876）。

> 预冻结模式保证：已冻结的任务执行时不再检查余额（`consume_frozen` 消费已冻结额度）。故"积分不足"只发生在冻结阶段，不在执行中途。

## 设计

### 5.1 数据层：`point_transactions.cascade_group_id`

`PointTransaction` 新增带索引列，不改 append-only 语义：

```python
cascade_group_id: Mapped[str | None] = mapped_column(
    String(64),
    nullable=True,
    index=True,
    comment="级联分组键：同一次操作的 root billing_id；充值/手动调整为 NULL",
)
```

赋值规则：
- divide 自己的冻结流水 → `cascade_group_id = 自己的 billing_id`（它即 root）。
- 级联 extract 冻结流水 → `cascade_group_id = divide 的 billing_id`。
- 级联图片冻结流水 → `cascade_group_id = 当前操作 root billing_id`（divide 或 extract）。
- 充值 / 手动调整 / 非级联操作 → `NULL`（聚合时各自成组）。

迁移：`backend/sql/013-add-point-transactions-cascade-group-id.sql`，加列 + 索引（沿用既有 `information_schema` 幂等写法）。存量行 `NULL`，不影响历史流水展示（旧流水按 `billing_id` 生命周期仍可折叠，仅无操作级归组）。

### 5.2 计费链路：cascade_group_id 写入与透传

利用既有"consume/unfreeze 从 freeze 行复制字段"的模式（`consume_frozen` 行288-291 已复制 business_type/model_id 等）：

- `freeze_points` 新增可选参数 `cascade_group_id: str | None`，写入 freeze 流水。
- `consume_frozen` / `unfreeze_frozen`：从 `freeze_tx` 复制 `cascade_group_id` 到新流水（与复制 business_type 完全同款）。
- `freeze_for_task`：透传调用方的 `cascade_group_id`。

**3 个冻结点填 root**：

1. `create_divide_task` / `create_extract_task`（`_freeze_for_script_task` → `freeze_for_task`）→ 传 `cascade_group_id = 该任务 billing_id`（自身即 root）。
2. `apply_auto_extraction_after_division` 内 extract 冻结（`_freeze_text_call_async` → `freeze_points`）→ 传 divide 的 billing_id。需让 `DivideTaskExecutor` 把 divide billing_id 传入此函数（`ctx.task.billing_id`）。
3. `_schedule_image_task_sync` → `_freeze_image_task_async` → `freeze_points` → 传 root billing_id。需 `auto_prepare_chapter_shots_sync` 与 `_schedule_image_task_sync` 新增参数 `cascade_root_billing_id`，两个调用点透传：
   - `DivideTaskExecutor` 链路：root = divide billing_id。
   - `ExtractTaskExecutor` 链路：root = extract billing_id。

> 充值、管理员调整等非级联冻结点不传 `cascade_group_id`（默认 NULL）。

### 5.3 操作前预估（前端组合，后端 quote 端点不改）

`usePointsQuote` 对分镜操作发两次试算（1 次 text + 1 次 image）拿单价后组合：
- 文本部分：text quote 得到的单价 **×2**（divide + 级联 extract 同模型同价；独立 extract 入口仅 ×1）。
- 图片部分：image quote（`generation_count=1`）得到的单价 Z。

`PointsCostHint` 渲染：

```
将消耗 [2×文本单价] + 每张资产图 [Z]（按实际新建数量另计）
```

降级：用户未配默认图片模型时，图片部分显示"图片模型未配置，另计"，不阻断文本预估。

### 5.4 流水展示层：分组接口 + 分组视图

**新增** `GET /points/transactions/grouped`，按 `cascade_group_id` 聚合，**按组分页**（组时间 = 组内最早流水 created_at），避免组跨页切断：

```
OperationGroup {
  cascade_group_id: str | null,      // NULL 组按 billing_id 兜底成组（充值等）
  business_type: str,                 // root 单据的业务类型
  created_at: datetime,               // 组起始时间
  total_net: int,                     // 该操作对余额的实际净消耗 = Σ consume（freeze/unfreeze 不动余额）
  billings: [ BillingLifecycle {      // 按 billing_id 的单据生命周期
      billing_id, model_id, business_type,
      status,                          // frozen / settled / refunded
      frozen_amount, net_amount,       // net_amount = consume 金额（无 consume 即 0，如已退回）
      events: [ PointTransactionRead ] // freeze/consume/unfreeze 明细（可折叠）
  } ]
}
```

- `total_net` 反映实际扣减（成功消费 − 失败退回），天然揭示"没花完 = 部分跳过"。
- 旧扁平接口 `GET /points/transactions` 保留（管理员页等仍用），其 `PointTransactionRead` 增补 `cascade_group_id` 字段。

前端：`PointTransactionTable` 增加分组视图（操作组为行，展开看单据生命周期，再展开看明细事件）。`PointsPage` 切换"分组视图 / 明细视图"。

### 5.5 业务类型中文化（前端映射表）

前端维护 `business_type` → 中文名映射，展示层统一翻译，后端枚举标识符保持英文稳定：

| business_type | 中文 |
| --- | --- |
| `script_divide` | 分镜拆解 |
| `script_extract` | 分镜提取 |
| `script_merge` | 实体合并 |
| `script_consistency` | 一致性检查 |
| `script_variant` | 变体分析 |
| `script_character_portrait` | 角色形象分析 |
| `script_prop_info` | 道具信息分析 |
| `script_scene_info` | 场景信息分析 |
| `script_costume_info` | 服装信息分析 |
| `script_optimize` | 剧本优化 |
| `script_simplify` | 剧本精简 |
| `image_generation` | 图片生成 |
| `video_generation` | 视频生成 |

> 实施时以代码中实际出现的 `business_type` 全集为准补全；未命中的 key 回退显示原英文。

### 5.6 积分不足提示文案（仅前端，最小方案）

在"一键提取"操作入口（`PointsCostHint` 下方）加一行小字说明，不做后端跳过记录收集：

```
分镜拆解为必执行项；若积分不足以覆盖资产图生成，对应资产将建档但不生成图片。
```

配合预估（显示总额）与汇总（`total_net` 揭示差额），用户可理解"为什么有的资产没图"。

## 改动清单

### 后端

- `app/models/points.py`：`PointTransaction` 加 `cascade_group_id` 列。
- `backend/sql/013-add-point-transactions-cascade-group-id.sql`：迁移。
- `app/services/points/ledger.py`：`freeze_points` 加参数；`consume_frozen`/`unfreeze_frozen` 复制 `cascade_group_id`；`freeze_for_task` 透传。
- `app/services/script_processing_tasks.py`：`_freeze_for_script_task` 透传 `cascade_group_id = 任务 billing_id`。
- `app/services/script_processing_worker.py`：`apply_auto_extraction_after_division` extract 冻结填 root；`DivideTaskExecutor`/`ExtractTaskExecutor.apply_result` 把 root billing_id 传入 `auto_prepare_chapter_shots_sync`。
- `app/services/studio/shot_auto_preparation.py`：`auto_prepare_chapter_shots_sync`、`_schedule_image_task_sync`、`_freeze_image_task_async` 新增 `cascade_root_billing_id` 参数透传。
- `app/services/points/billing.py`：`list_user_transactions` 增补返回 `cascade_group_id`；新增 grouped 查询逻辑。
- `app/api/v1/routes/points.py`：新增 `GET /transactions/grouped`。
- `app/schemas/points.py`：`PointTransactionRead` 加 `cascade_group_id`；新增 grouped 响应 schema。

### 前端

- `front/src/components/points/PointsCostHint.tsx`：支持文本×N + 图片单价组合展示 + 积分不足提示文案。
- `front/src/pages/aiStudio/project/ProjectWorkbench/tabs/ChaptersTab.tsx`：`usePointsQuote` 组合 text×2 + image 单价。
- `front/src/components/points/PointTransactionTable.tsx`：分组视图（操作组 → 单据生命周期 → 明细）。
- `front/src/pages/points/PointsPage.tsx`：视图切换；接入 grouped 接口。
- 新增 `business_type` 中英映射表（如 `front/src/components/points/businessTypeLabel.ts`）。
- OpenAPI 客户端重新生成（`pnpm run openapi:update`）。

## 验收标准

1. "一键提取分镜"预估显示 `2×文本单价 + 每张资产图 Z`（用户配图片模型时）。
2. 一次"一键提取"产生的所有流水（divide + extract + N图片）在 grouped 接口归为同一操作组，`total_net` = 实际净消耗。
3. 流水分组视图：同一 `billing_id` 的 freeze/consume/unfreeze 折叠为一条单据，状态（冻结/已结算/已退回）清晰。
4. 业务类型在流水页显示中文。
5. 积分不足以覆盖图片时，资产建档但无图，操作入口有文案说明该行为。
6. 后端测试覆盖：cascade_group_id 写入、consume/unfreeze 复制、grouped 聚合、total_net 计算。
7. `pnpm exec tsc --noEmit` 通过；后端相关测试通过。

## 不纳入范围 / 后续

- **跳过记录的结构化收集与展示**（标注"N个子任务因积分不足被跳过"）本次不做，仅用 `total_net` 差额 + 入口文案提示。后续若需精确跳过可见性，可在任务结果中持久化跳过清单。
- 历史存量流水（迁移前）`cascade_group_id` 为 NULL，仅支持按 `billing_id` 生命周期折叠，不支持操作级归组（可接受，历史不回填）。
- 独立 merge/variant/analysis 等无级联操作的预估与展示维持现状。
- 实施完成后，更新 `site/content/docs/architecture/points-billing.md` 记录 `cascade_group_id` 列与 grouped 接口（架构文档反映真实生效实现）。
