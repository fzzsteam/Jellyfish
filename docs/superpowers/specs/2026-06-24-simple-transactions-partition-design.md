# 单笔流水分区与充值调整展示设计

**日期**：2026-06-24  
**范围**：后端 ledger 改造、grouped 端点双列表返回、前端双 Tab 展示、Level 3 列精简  
**前置**：已在 2026-06-24 的「积分流水页面重设计」实现的三层展开基础上叠加

---

## 背景

当前 grouped 视图将充值（recharge）也纳入了「操作→账单→流水」三层结构，但充值属于单笔操作，没有 billing 生命周期（无 freeze/consume/unfreeze 流程），导致：
- 状态被误判为「冻结中」（实际上充值没有状态）
- 三层展开结构对充值产生一层空壳（操作ID=账单ID）
- `cascade_group_id` 设为 `billing_id` 导致充值数据混入 cascade 分组

本次设计：
1. 充值不再设 `cascade_group_id`，彻底隔离
2. grouped 端点同时返回「操作组」和「单笔流水」两个列表
3. 前端分两 Tab 展示
4. Level 3 流水明细列精简

---

## 一、后端改动

### 1.1 Recharge `cascade_group_id` = NULL

文件：`backend/app/services/points/ledger.py:450`

```python
# 改前
cascade_group_id=billing_id,  # 充值为单笔操作，cascade_group_id = billing_id
# 改后
cascade_group_id=None,  # 充值/调整为单笔操作，不参与级联分组
```

影响：仅影响 `recharge()` 函数。freeze/consume/unfreeze 的 cascade_group_id 继承逻辑不变。

### 1.2 Schema

文件：`backend/app/schemas/points.py`

`GroupedTransactionResponse` 新增字段：

```python
class GroupedTransactionResponse(BaseModel):
    items: list[OperationGroupRead]       # cascade 分组（同现有）
    pagination: Pagination                # cascade 分组的分页
    simple_txns: list[PointTransactionRead] = []  # 单笔流水
    matched_transaction_id: str | None = None
```

`PointTransactionRead` 各字段已满足单笔流水展示所需（`id` / `type` / `amount` / `balance_after` / `created_at` / `remark` / `created_by_username`），无需新增字段。

### 1.3 Service

文件：`backend/app/services/points/billing.py`

`list_grouped_transactions` 在返回 grouped 数据后，追加查询 `source="admin"` 的单笔流水：

```python
# ── 查询单笔流水（source="admin" 的充值/调整记录）─────
simple_txns: list[PointTransaction] = []
if user_id:
    rows = (await db.execute(
        select(PointTransaction)
        .where(
            PointTransaction.user_id == user_id,
            PointTransaction.source == "admin",
        )
        .order_by(PointTransaction.created_at.desc())
        .limit(50)  # 固定最多 50 条，不分页
    )).scalars().all()
    simple_txns = list(rows)

return result, total, matched_transaction_id, simple_txns
```

返回类型变为：
```python
) -> tuple[list[dict], int, str | None, list[PointTransaction]]:
```

单笔流水不分页，最多返回最近 50 条（充值频率远低于计费操作，50 条足够）。

### 1.4 路由层

两个路由文件各需：
- service 调用解包新增一个返回值（`groups, total, matched_tx_id, simple_txns =`）
- 将 `simple_txns` 序列化后传入 `GroupedTransactionResponse`

```python
return success_response(
    GroupedTransactionResponse(
        items=[OperationGroupRead(**g) for g in groups],
        pagination=pagination,
        matched_transaction_id=matched_transaction_id,
        simple_txns=[PointTransactionRead.model_validate(tx).model_copy(
            update={"created_by_username": user_map.get(tx.created_by) if tx.created_by else None}
        ) for tx in simple_txns],
    )
)
```

### 1.5 搜索不影响

搜索（`cascade_group_id` / `billing_id` / `transaction_id`）只作用于 `items`（cascade groups），不影响 `simple_txns`。

### 1.6 SQL 迁移

文件：`backend/sql/014-clear-recharge-cascade-group-id.sql`

```sql
-- 清空已有充值记录的 cascade_group_id，确保存量数据与新的 NULL 语义一致
UPDATE point_transactions
SET cascade_group_id = NULL
WHERE type = 'recharge' AND cascade_group_id IS NOT NULL;
```

---

## 二、前端改动

### 2.1 新增 `SimplePointTransactionTable` 通用组件

文件：`front/src/components/points/SimplePointTransactionTable.tsx`

为什么需要：PointsPage 与 AdminUserDetailPage 都要展示充值/调整流水，抽出通用组件避免列定义、金额格式、ID 复制逻辑重复。

Props：
```ts
interface SimplePointTransactionTableProps {
  dataSource: PointTransactionRead[]
  loading?: boolean
}
```

表格列：

| 列 | 数据源 | 渲染 |
|---|---|---|
| ID | `id` | [流水] Tag + CopyableId |
| 金额 | `amount` | 正数绿色+前缀，负数红色−前缀 |
| 余额 | `balance_after` | PointsBadge |
| 时间 | `created_at` | formatTxTime |
| 备注 | `remark` | 截断显示 |
| 操作人 | `created_by_username` | 或默认值 |

### 2.2 `PointsPage.tsx`

积分流水 Card 内改为两个 Tabs（Ant Design `Tabs` 组件），或若当前 Card 已在一个大 Tabs 内，用 `Radio.Group` 做子切换。推荐用 `Tabs`：

```
积分流水
├── 操作记录 tab（默认）  ← 搜索框 + PointTransactionTable（三层展开）
└── 充值/调整 tab         ← 简单平铺表格（一列一条充值/调整）
```

「充值/调整」Tab 的表格列：

| 列 | 数据源 | 渲染 |
|---|---|---|
| ID | `id` | [流水] Tag + CopyableId |
| 金额 | `amount` | 正数绿色+前缀，负数红色−前缀 |
| 余额 | `balance_after` | PointsBadge |
| 时间 | `created_at` | formatTxTime |
| 备注 | `remark` | 截断显示 |
| 操作人 | `created_by_username` | 或默认值 |

「充值/调整」Tab 不需要搜索框，不需要展开。

### 2.2 `AdminUserDetailPage.tsx`

与 PointsPage 同步，积分流水 Tab 内再加两个子 Tab（或 Radio 切换）。

### 2.3 `PointTransactionTable.tsx`

**Level 3 列精简** —— 参照设计第二段，删除「冻结后」列：

- 原：ID / 类型 / 金额 / 时间 / 余额后 / 冻结后
- 改：ID / 类型 / 金额 / 时间 / 余额

「余额后」列标题改名为「余额」（简洁，不言自明）。

### 2.4 数据接入

`loadGrouped` 返回数据中包含 `simple_txns`（响应字段 `data.simple_txns`），存入独立 state。Tab 切换时切换渲染组件。

---

## 三、完成检查清单

- [ ] `ledger.py` recharge `cascade_group_id` 改为 `None`
- [ ] Schema `GroupedTransactionResponse` 新增 `simple_txns: list[PointTransactionRead]`
- [ ] `list_grouped_transactions` 返回四元组，追加简单流水查询
- [ ] 用户端路由 + 管理员端路由解包四元组并序列化 `simple_txns`
- [ ] SQL 迁移文件清理存量数据
- [ ] 后端测试：recharge 后 cascade_group_id 为 NULL；grouped 端点返回 `simple_txns`
- [ ] `pnpm run openapi:update`
- [ ] `PointsPage` 分出两个子 Tab（操作记录 / 充值调整）
- [ ] `AdminUserDetailPage` 同步分出子 Tab
- [ ] `PointTransactionTable` Level 3 删除「冻结后」列，「余额后」改为「余额」
- [ ] `pnpm exec tsc --noEmit`
- [ ] pnpm lint 零 error（改动文件）
- [ ] 后端测试全绿