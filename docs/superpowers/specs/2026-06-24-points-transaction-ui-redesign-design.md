# 积分流水页面重设计

**日期**：2026-06-24  
**范围**：`PointTransactionTable` 组件、`PointsPage`、`AdminUserDetailPage`、后端 grouped 端点

---

## 背景

当前积分流水页有「明细」与「按操作」两种视图切换，且「按操作」只展开到 billing 卡片一层，无法继续查看底层流水事件。ID 展示没有类型标签，用户难以区分操作ID / 账单ID / 流水ID。搜索只在明细模式下支持流水ID。

本次重设计：
1. 移除明细模式，只保留「按操作」三层展开视图
2. 所有 ID 加类型标签，明确区分三种 ID
3. 统一搜索栏支持按三种 ID 类型搜索，流水ID搜索时自动展开并高亮目标行

---

## 一、后端改动

### 1.1 `list_grouped_transactions` service

文件：`backend/app/services/points/billing.py`

新增三个可选参数：

| 参数 | 类型 | 过滤逻辑 |
|---|---|---|
| `cascade_group_id` | `str \| None` | 直接 WHERE cascade_group_id = ? |
| `billing_id` | `str \| None` | 先查该 billing 所属 cascade_group_id，再按组返回 |
| `transaction_id` | `str \| None` | 先查该流水所属 cascade_group_id，再按组返回 |

返回值新增 `matched_transaction_id: str | None`，在 `transaction_id` 搜索时回传，供前端定位自动展开目标。

### 1.2 Schema

文件：`backend/app/schemas/points.py`

`GroupedTransactionResponse` 新增字段：

```python
matched_transaction_id: str | None = None
```

### 1.3 路由层

以下两个端点各新增三个 Query 参数，收参后透传 service：

- `GET /api/v1/points/transactions/grouped`（用户端）
- `GET /api/v1/admin/users/{user_id}/points/transactions/grouped`（管理员端）

### 1.4 OpenAPI 同步

后端改完后运行：
```bash
cd front && pnpm run openapi:update
```

---

## 二、前端组件：`PointTransactionTable`

文件：`front/src/components/points/PointTransactionTable.tsx`

### 2.1 移除内容

- `viewMode` prop 及所有 `flat` 分支代码
- `columns`（明细列定义）、flat 渲染路径
- modelMap 的 flat 分支逻辑
- `PointTransactionRead` 相关 import

### 2.2 新 Props

```ts
interface PointTransactionTableProps {
  dataSource: OperationGroupRead[]
  loading?: boolean
  total?: number
  page?: number
  pageSize?: number
  onChange?: (page: number, pageSize: number) => void
  highlightTransactionId?: string  // 流水ID搜索时传入，驱动自动展开+高亮
}
```

`dataSource` 类型从 `PointTransactionRead[] | OperationGroupRead[]` 收窄为 `OperationGroupRead[]`。

### 2.3 三层展开结构

```
Level 1 — 操作行（Ant Table，expandable）
  │  [操作] abc123…  |  业务类型  |  时间  |  净消耗  |  X 笔账单
  │
  └─ Level 2 — 账单行（嵌套 Table，expandable）
       │  [账单] def456…  |  状态Tag  |  冻结额  |  扣减额  |  时间
       │
       └─ Level 3 — 流水明细（再嵌套迷你 Table）
              [流水] ghi789…  |  类型Tag  |  金额  |  时间  |  余额后  |  冻结后
```

各层 ID 前加类型标签（Ant `Tag`），颜色固定：

| ID 类型 | 标签文字 | Tag color |
|---|---|---|
| cascade_group_id | 操作 | default（灰）|
| billing_id | 账单 | purple |
| 流水 id | 流水 | cyan |

### 2.4 展开可见性提示

- Level 1 / Level 2 行左侧显式展开图标列（右箭头，展开后旋转 90°）
- `expandRowByClick: true`（整行可点击展开）
- 行 hover 时背景浅蓝，`cursor: pointer`
- Level 2 所在嵌套区域背景比 Level 1 深一档（`bg-slate-50` → `bg-slate-100`）

### 2.5 State

组件内维护三套独立展开 key：

```ts
const [expandedOpKeys, setExpandedOpKeys] = useState<string[]>([])
const [expandedBillKeys, setExpandedBillKeys] = useState<string[]>([])
```

Level 3 无需 state（迷你 Table 默认全量展示）。

### 2.6 自动展开逻辑（`highlightTransactionId`）

数据加载后（`useEffect` 监听 `dataSource + highlightTransactionId`）：

1. 遍历 `dataSource`，找到包含目标流水的操作组 → 预置 `expandedOpKeys`
2. 在该组 `billings` 中找到包含目标流水的账单 → 预置 `expandedBillKeys`
3. Level 3 迷你 Table 中，匹配行加 `bg-amber-50 ring-1 ring-amber-300` 样式高亮

---

## 三、页面层改动

### 3.1 `PointsPage`

文件：`front/src/pages/points/PointsPage.tsx`

**删除**：
- `Radio.Group`（明细/按操作切换）
- `transactions`、`txLoading`、`total`、`typeFilter`、`idSearch` 等明细 state
- `loadTransactions` 函数
- 类型筛选 `Select` 和旧 `Input.Search`

**新增**：
- `searchIdType: 'cascade_group_id' | 'billing_id' | 'transaction_id'`（默认 `cascade_group_id`）
- `searchIdValue: string | undefined`
- `highlightTransactionId: string | undefined`（从响应 `matched_transaction_id` 取）

**搜索 UI**（Card extra 区域）：

```
[ 操作ID ▼ ]  [ 输入搜索值... 🔍 ]
```

下拉选项：操作ID / 账单ID / 流水ID。`allowClear` 清除后恢复无过滤分页。

### 3.2 `AdminUserDetailPage`

文件：`front/src/pages/admin/AdminUserDetailPage.tsx`

与 PointsPage 对齐：
- 删除 `txGroupedView` toggle、`transactions`、`txLoading`、`txTotal`、`txIdSearch`、`loadTransactions`
- Tab 内搜索 UI 换成下拉+输入组合
- `highlightTransactionId` 透传给 `PointTransactionTable`

---

## 四、完成检查清单

- [ ] 后端 service 新增三种搜索参数 + 返回 `matched_transaction_id`
- [ ] 后端 schema `GroupedTransactionResponse` 新增字段
- [ ] 用户端路由 + 管理员端路由各加三个 Query 参数
- [ ] `pnpm run openapi:update` 同步前端类型
- [ ] `PointTransactionTable` 重构：移除 flat 模式，实现三层展开
- [ ] ID 类型标签渲染（操作/账单/流水）
- [ ] 展开可见性提示（图标 + hover + 层级背景）
- [ ] 自动展开 + 高亮逻辑（`highlightTransactionId`）
- [ ] `PointsPage` 清理 + 新搜索 UI
- [ ] `AdminUserDetailPage` 清理 + 新搜索 UI
- [ ] `pnpm exec tsc --noEmit` 通过
- [ ] 后端相关测试或语法校验通过
