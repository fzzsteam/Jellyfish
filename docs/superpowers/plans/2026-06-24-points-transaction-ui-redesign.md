# 积分流水页面重设计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把积分流水页改为「三层展开（操作→账单→流水事件）」唯一视图，移除明细模式，新增按三种 ID 类型搜索，流水ID搜索时自动展开并高亮目标行。

**Architecture:** 后端在 `list_grouped_transactions` service 层新增三种搜索参数（cascade_group_id / billing_id / transaction_id），路由透传；前端 `PointTransactionTable` 重写为纯 grouped 三层嵌套 Ant Table，`PointsPage` 与 `AdminUserDetailPage` 同步清理。

**Tech Stack:** Python / FastAPI / SQLAlchemy（后端），TypeScript / React / Ant Design / Tailwind（前端）

---

## 文件变更地图

| 文件 | 动作 |
|------|------|
| `backend/app/schemas/points.py` | 修改：`GroupedTransactionResponse` 新增 `matched_transaction_id` |
| `backend/app/services/points/billing.py` | 修改：`list_grouped_transactions` 新增搜索参数，返回三元组 |
| `backend/app/api/v1/routes/points.py` | 修改：grouped 端点加 3 个 Query 参数 |
| `backend/app/api/v1/routes/admin/users.py` | 修改：admin grouped 端点加 3 个 Query 参数 |
| `backend/tests/test_points_api.py` | 修改：新增 grouped 搜索测试 |
| `front/openapi.json` + `front/src/services/generated/` | 重新生成（`pnpm run openapi:update`） |
| `front/src/components/points/PointTransactionTable.tsx` | 重写：移除 flat 模式，实现三层展开 |
| `front/src/pages/points/PointsPage.tsx` | 修改：移除 flat 状态，新增搜索 UI |
| `front/src/pages/admin/AdminUserDetailPage.tsx` | 修改：同上 |

---

## Task 1：更新 Schema 与 Service 函数签名

**Files:**
- Modify: `backend/app/schemas/points.py:154-157`
- Modify: `backend/app/services/points/billing.py:667-673`（函数签名行）

- [ ] **Step 1：在 `GroupedTransactionResponse` 新增 `matched_transaction_id` 字段**

打开 `backend/app/schemas/points.py`，找到 `GroupedTransactionResponse` 类（约第 154 行），改为：

```python
class GroupedTransactionResponse(BaseModel):
    items: list[OperationGroupRead]
    pagination: Pagination
    matched_transaction_id: str | None = None
```

- [ ] **Step 2：更新 `list_grouped_transactions` 函数签名**

打开 `backend/app/services/points/billing.py`，找到 `list_grouped_transactions`（约第 667 行），更新签名与返回类型：

```python
async def list_grouped_transactions(
    db: AsyncSession,
    *,
    user_id: str,
    page: int = 1,
    page_size: int = 20,
    cascade_group_id: str | None = None,
    billing_id: str | None = None,
    transaction_id: str | None = None,
) -> tuple[list[dict], int, str | None]:
```

函数末尾 `return result, total` 暂改为 `return result, total, None`（下一个 Task 再实现逻辑）。

- [ ] **Step 3：语法检查**

```bash
cd backend && python -m py_compile app/schemas/points.py app/services/points/billing.py
```

期望：无输出（无语法错误）。

- [ ] **Step 4：修复被破坏的两个路由层调用**

两处路由仍用 `groups, total =` 解包，会在运行时出错。先临时修复（Task 3 再完整修改）：

`backend/app/api/v1/routes/points.py` 约第 121 行：
```python
groups, total, _ = await list_grouped_transactions(
    db,
    user_id=current_user.id,
    page=page,
    page_size=page_size,
)
```

`backend/app/api/v1/routes/admin/users.py` 约第 248 行：
```python
groups, total, _ = await list_grouped_transactions(
    db,
    user_id=user_id,
    page=page,
    page_size=page_size,
)
```

- [ ] **Step 5：语法检查路由文件**

```bash
cd backend && python -m py_compile app/api/v1/routes/points.py app/api/v1/routes/admin/users.py
```

期望：无输出。

- [ ] **Step 6：提交**

```bash
git add backend/app/schemas/points.py backend/app/services/points/billing.py \
        backend/app/api/v1/routes/points.py backend/app/api/v1/routes/admin/users.py
git commit -m "refactor(points): grouped 端点 schema + service 签名支持三种搜索参数"
```

---

## Task 2：实现 list_grouped_transactions 搜索逻辑

**Files:**
- Modify: `backend/app/services/points/billing.py`（`list_grouped_transactions` 函数体）
- Test: `backend/tests/test_points_api.py`

- [ ] **Step 1：先写失败测试**

在 `backend/tests/test_points_api.py` 末尾追加：

```python
# ---------------------------------------------------------------------------
# GET /points/transactions/grouped 搜索
# ---------------------------------------------------------------------------

import uuid as _uuid
from datetime import datetime, timezone as _tz
from app.models.points import PointTransaction as _PTx, PointTransactionType as _PTxType


def _seed_cascade_group(sm, user_id: str) -> tuple[str, str, str, str]:
    """向 DB 插入一次完整的 cascade 生命周期（freeze → consume），返回
    (cascade_group_id, billing_id, tx_freeze_id, tx_consume_id)。
    """
    import asyncio as _asyncio
    cgid = "cgid-search-test"
    bid  = "bid-search-test"
    fid  = "txid-freeze-1"
    cid  = "txid-consume-1"

    async def _insert():
        async with sm() as s:
            now = datetime.now(_tz.utc)
            s.add(_PTx(id=fid, user_id=user_id, type=_PTxType.freeze,
                        amount=10, balance_after=100, frozen_after=10,
                        source="billing", billing_id=bid, cascade_group_id=cgid, created_at=now))
            s.add(_PTx(id=cid, user_id=user_id, type=_PTxType.consume,
                        amount=10, balance_after=90, frozen_after=0,
                        source="billing", billing_id=bid, cascade_group_id=cgid, created_at=now))
            await s.commit()

    _asyncio.run(_insert())
    return cgid, bid, fid, cid


@pytest.fixture
def grouped_search_client(monkeypatch):
    """带 cascade 分组数据的 points TestClient。"""
    from fakeredis.aioredis import FakeRedis
    fake = FakeRedis()
    monkeypatch.setattr(ledger_module, "_redis_factory", lambda: fake)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sm() as s:
            s.add(User(id="user-1", username="bob", hashed_password="x",
                       is_admin=False, is_active=True))
            s.add(UserPoints(user_id="user-1", balance=90, frozen=0))
            await s.commit()

    asyncio.run(_setup())
    cgid, bid, fid, cid = _seed_cascade_group(sm, "user-1")

    async def _override_db():
        async with sm() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    async def _normal_user():
        return User(id="user-1", username="bob", hashed_password="x",
                    is_admin=False, is_active=True)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _normal_user
    try:
        yield TestClient(app), cgid, bid, fid
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_grouped_search_by_cascade_group_id(grouped_search_client):
    client, cgid, bid, fid = grouped_search_client
    resp = client.get("/api/v1/points/transactions/grouped",
                      params={"cascade_group_id": cgid})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["pagination"]["total"] == 1
    assert data["items"][0]["cascade_group_id"] == cgid
    assert data["matched_transaction_id"] is None


def test_grouped_search_by_billing_id(grouped_search_client):
    client, cgid, bid, fid = grouped_search_client
    resp = client.get("/api/v1/points/transactions/grouped",
                      params={"billing_id": bid})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["items"][0]["cascade_group_id"] == cgid
    assert data["matched_transaction_id"] is None


def test_grouped_search_by_transaction_id(grouped_search_client):
    client, cgid, bid, fid = grouped_search_client
    resp = client.get("/api/v1/points/transactions/grouped",
                      params={"transaction_id": fid})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["items"][0]["cascade_group_id"] == cgid
    assert data["matched_transaction_id"] == fid


def test_grouped_search_unknown_id_returns_empty(grouped_search_client):
    client, _, _, _ = grouped_search_client
    resp = client.get("/api/v1/points/transactions/grouped",
                      params={"transaction_id": "nonexistent-id"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["pagination"]["total"] == 0
    assert data["items"] == []
```

- [ ] **Step 2：运行，确认测试失败（预期行为：函数没有搜索逻辑）**

```bash
cd backend && uv run pytest tests/test_points_api.py::test_grouped_search_by_cascade_group_id -v
```

期望：FAIL，提示 `total != 1` 或接口逻辑不匹配。

- [ ] **Step 3：实现搜索逻辑**

打开 `backend/app/services/points/billing.py`，在 `list_grouped_transactions` 的函数体**最开始**（`# 1) 查询当前页` 注释之前）插入搜索解析逻辑：

```python
    # ── 搜索参数解析：将 billing_id / transaction_id 解析为 cascade_group_id ──────
    matched_transaction_id: str | None = None
    resolved_cascade_group_id: str | None = cascade_group_id

    if transaction_id is not None:
        row = (await db.execute(
            select(PointTransaction.cascade_group_id, PointTransaction.id)
            .where(
                PointTransaction.id == transaction_id,
                PointTransaction.user_id == user_id,
            )
            .limit(1)
        )).first()
        if row is None or row[0] is None:
            return [], 0, None
        resolved_cascade_group_id = row[0]
        matched_transaction_id = row[1]

    elif billing_id is not None:
        resolved_cascade_group_id = await db.scalar(
            select(PointTransaction.cascade_group_id)
            .where(
                PointTransaction.billing_id == billing_id,
                PointTransaction.user_id == user_id,
            )
            .limit(1)
        )
        if resolved_cascade_group_id is None:
            return [], 0, None
```

然后在 `group_subq` 和 count 查询中加入 `resolved_cascade_group_id` 过滤，在两处 `.where(...)` 各追加一个条件：

```python
    # 1) 查询当前页的 cascade_group_id 列表
    base_where = [
        PointTransaction.user_id == user_id,
        PointTransaction.cascade_group_id.isnot(None),
    ]
    if resolved_cascade_group_id is not None:
        base_where.append(PointTransaction.cascade_group_id == resolved_cascade_group_id)

    group_subq = (
        select(
            PointTransaction.cascade_group_id,
            func.min(PointTransaction.created_at).label("group_created_at"),
        )
        .where(*base_where)
        .group_by(PointTransaction.cascade_group_id)
        .order_by(text("group_created_at desc"))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .subquery()
    )

    total = await db.scalar(
        select(func.count(func.distinct(PointTransaction.cascade_group_id)))
        .where(*base_where)
    ) or 0
```

函数末尾将 `return result, total` 改为：

```python
    return result, total, matched_transaction_id
```

- [ ] **Step 4：运行全部新测试**

```bash
cd backend && uv run pytest tests/test_points_api.py -k "grouped_search" -v
```

期望：4 个测试全部 PASS。

- [ ] **Step 5：运行全量积分测试，确保没有回归**

```bash
cd backend && uv run pytest tests/test_points_api.py tests/test_points_ledger.py -q
```

期望：全部 PASS。

- [ ] **Step 6：提交**

```bash
git add backend/app/services/points/billing.py backend/tests/test_points_api.py
git commit -m "feat(points): grouped 搜索支持 cascade_group_id/billing_id/transaction_id"
```

---

## Task 3：更新路由层（用户端 + 管理员端）

**Files:**
- Modify: `backend/app/api/v1/routes/points.py`（`list_grouped_transactions` 路由）
- Modify: `backend/app/api/v1/routes/admin/users.py`（`list_user_points_transactions_grouped` 路由）

- [ ] **Step 1：更新用户端 grouped 路由**

打开 `backend/app/api/v1/routes/points.py`，找到 `list_grouped_transactions` 函数（约第 112 行），替换整个函数：

```python
@router.get(
    "/transactions/grouped",
    response_model=ApiResponse[GroupedTransactionResponse],
    summary="按操作组聚合的积分流水",
)
async def list_grouped_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    cascade_group_id: str | None = Query(None, description="按操作ID精确搜索"),
    billing_id: str | None = Query(None, description="按账单ID搜索，返回所属操作组"),
    transaction_id: str | None = Query(None, description="按流水ID搜索，返回所属操作组"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[GroupedTransactionResponse]:
    """按 cascade_group_id 聚合展示流水。支持按操作ID/账单ID/流水ID精确搜索。"""
    from app.services.points.billing import list_grouped_transactions as _list_grouped

    groups, total, matched_transaction_id = await _list_grouped(
        db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        cascade_group_id=cascade_group_id,
        billing_id=billing_id,
        transaction_id=transaction_id,
    )

    created_by_ids = {
        b["created_by"]
        for g in groups for b in g.get("billings", [])
        if b.get("created_by") and b["created_by"] != _SYSTEM_CREATED_BY
    }
    user_map: dict[str, str] = {_SYSTEM_CREATED_BY: _SYSTEM_CREATED_BY_DISPLAY}
    if created_by_ids:
        rows = await db.execute(select(User.id, User.username).where(User.id.in_(created_by_ids)))
        user_map.update({r.id: r.username for r in rows})
    for g in groups:
        for b in g.get("billings", []):
            b["created_by_username"] = user_map.get(b.get("created_by") or "", None)

    from app.schemas.common import Pagination
    max_page = max(1, (total + page_size - 1) // page_size) if page_size > 0 else 1
    pagination = Pagination(page=page, page_size=page_size, total=total, max_page=max_page)
    return success_response(
        GroupedTransactionResponse(
            items=[OperationGroupRead(**g) for g in groups],
            pagination=pagination,
            matched_transaction_id=matched_transaction_id,
        )
    )
```

注意：函数名与 import 别名冲突，使用 `_list_grouped` 别名避免递归。同时在文件顶部的 `from app.services.points.billing import ...` 中**移除** `list_grouped_transactions`（改为在函数内部局部 import）。

- [ ] **Step 2：更新管理员端 grouped 路由**

打开 `backend/app/api/v1/routes/admin/users.py`，找到 `list_user_points_transactions_grouped`（约第 234 行），替换：

```python
@router.get(
    "/{user_id}/points/transactions/grouped",
    response_model=ApiResponse[GroupedTransactionResponse],
    summary="查看某用户按操作组聚合的积分流水",
)
async def list_user_points_transactions_grouped(
    user_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    cascade_group_id: str | None = Query(None, description="按操作ID精确搜索"),
    billing_id: str | None = Query(None, description="按账单ID搜索，返回所属操作组"),
    transaction_id: str | None = Query(None, description="按流水ID搜索，返回所属操作组"),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[GroupedTransactionResponse]:
    """按 cascade_group_id 聚合展示目标用户流水，供管理员查看。支持三种 ID 搜索。"""
    from app.schemas.common import Pagination

    groups, total, matched_transaction_id = await list_grouped_transactions(
        db,
        user_id=user_id,
        page=page,
        page_size=page_size,
        cascade_group_id=cascade_group_id,
        billing_id=billing_id,
        transaction_id=transaction_id,
    )

    created_by_ids = {
        b["created_by"]
        for g in groups for b in g.get("billings", [])
        if b.get("created_by") and b["created_by"] != _SYSTEM_CREATED_BY
    }
    user_map: dict[str, str] = {_SYSTEM_CREATED_BY: _SYSTEM_CREATED_BY_DISPLAY}
    if created_by_ids:
        rows = await db.execute(select(User.id, User.username).where(User.id.in_(created_by_ids)))
        user_map.update({r.id: r.username for r in rows})
    for g in groups:
        for b in g.get("billings", []):
            b["created_by_username"] = user_map.get(b.get("created_by") or "", None)

    max_page = max(1, (total + page_size - 1) // page_size) if page_size > 0 else 1
    pagination = Pagination(page=page, page_size=page_size, total=total, max_page=max_page)
    return success_response(
        GroupedTransactionResponse(
            items=[OperationGroupRead(**g) for g in groups],
            pagination=pagination,
            matched_transaction_id=matched_transaction_id,
        )
    )
```

- [ ] **Step 3：语法检查**

```bash
cd backend && python -m py_compile app/api/v1/routes/points.py app/api/v1/routes/admin/users.py
```

期望：无输出。

- [ ] **Step 4：运行全量 grouped 搜索测试**

```bash
cd backend && uv run pytest tests/test_points_api.py -k "grouped_search" -v
```

期望：4 个测试全部 PASS。

- [ ] **Step 5：提交**

```bash
git add backend/app/api/v1/routes/points.py backend/app/api/v1/routes/admin/users.py
git commit -m "feat(points): grouped 路由开放三种 ID 搜索参数（用户端 + 管理员端）"
```

---

## Task 4：OpenAPI 同步

**Files:**
- Regenerate: `front/openapi.json`, `front/src/services/generated/`

**前提：** 需要后端服务在 `http://127.0.0.1:8000` 运行。

- [ ] **Step 1：启动后端**

```bash
cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

在另一个终端继续后续步骤。

- [ ] **Step 2：生成前端客户端**

```bash
cd front && pnpm run openapi:update
```

期望：`front/openapi.json` 更新，`front/src/services/generated/` 重新生成（包含新的 `cascadeGroupId` / `billingId` / `transactionId` 参数及 `matched_transaction_id` 响应字段）。

- [ ] **Step 3：验证生成结果**

```bash
grep -r "matchedTransactionId\|cascadeGroupId\|billingId\|transactionId" front/src/services/generated/ | head -20
```

期望：能看到对应字段名出现在生成的 service 或 model 文件中。

- [ ] **Step 4：提交**

```bash
git add front/openapi.json front/src/services/generated/
git commit -m "chore(front): 同步 OpenAPI 客户端（grouped 搜索参数 + matched_transaction_id）"
```

---

## Task 5：重写 PointTransactionTable

**Files:**
- Rewrite: `front/src/components/points/PointTransactionTable.tsx`

- [ ] **Step 1：完整替换组件文件**

用以下完整内容替换 `front/src/components/points/PointTransactionTable.tsx`：

```tsx
/**
 * 积分流水表格通用组件（按操作三层展开视图）。
 * 用户积分页（PointsPage）与管理员用户详情页（AdminUserDetailPage）共用此组件。
 *
 * 三层结构：操作组（cascade_group_id）→ 账单（billing_id）→ 流水事件（transaction）
 * highlightTransactionId / highlightBillingId 由父组件在搜索后传入，驱动自动展开与高亮。
 */

import { useEffect, useState } from 'react'
import { Table, Tag, Typography } from 'antd'
import { RightOutlined } from '@ant-design/icons'
import type { TableColumnsType } from 'antd'
import { LlmService } from '../../services/generated'
import type {
  BillingEventRead,
  BillingLifecycleRead,
  OperationGroupRead,
  PointTransactionType,
} from '../../services/generated'
import { PointsBadge } from './PointsBadge'
import { formatBusinessType } from './businessTypeLabels'

const TX_TYPE_COLOR: Record<PointTransactionType, string> = {
  recharge: 'green',
  freeze: 'orange',
  consume: 'red',
  unfreeze: 'blue',
}

const TX_TYPE_LABEL: Record<PointTransactionType, string> = {
  recharge: '充值',
  freeze: '冻结',
  consume: '扣减',
  unfreeze: '解冻',
}

const TX_AMOUNT_COLOR: Record<PointTransactionType, string> = {
  recharge: 'text-green-500',
  consume: 'text-red-500',
  freeze: 'text-orange-500',
  unfreeze: 'text-blue-500',
}

const BILLING_STATUS_MAP: Record<string, { label: string; color: string }> = {
  settled: { label: '已结算', color: 'green' },
  refunded: { label: '已退回', color: 'blue' },
  frozen:   { label: '冻结中', color: 'orange' },
}

const formatTxTime = (v?: string | null): string => {
  if (!v) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  }).format(new Date(v))
}

const CopyableId: React.FC<{ value?: string | null }> = ({ value }) => {
  if (!value) return <span className="text-gray-400">—</span>
  const display = value.length > 10 ? `${value.slice(0, 8)}…` : value
  return (
    <Typography.Text
      copyable={{ text: value, tooltips: ['复制', '已复制'] }}
      className="!font-mono !text-xs !text-gray-500"
    >
      {display}
    </Typography.Text>
  )
}

/** Level 3 迷你表格：单个 billing 下的流水事件列表。 */
const eventColumns = (highlightId?: string): TableColumnsType<BillingEventRead> => [
  {
    title: 'ID',
    dataIndex: 'id',
    width: 170,
    render: (v: string) => (
      <span className="flex items-center gap-1">
        <Tag color="cyan" className="m-0 shrink-0 !text-xs !py-0">流水</Tag>
        <CopyableId value={v} />
      </span>
    ),
  },
  {
    title: '类型',
    dataIndex: 'type',
    width: 70,
    render: (t: PointTransactionType) => (
      <Tag color={TX_TYPE_COLOR[t]}>{TX_TYPE_LABEL[t]}</Tag>
    ),
  },
  {
    title: '金额',
    dataIndex: 'amount',
    width: 80,
    render: (v: number, r: BillingEventRead) => (
      <span className={`text-xs font-medium ${TX_AMOUNT_COLOR[r.type]}`}>
        {Math.abs(v)}
      </span>
    ),
  },
  {
    title: '时间',
    dataIndex: 'created_at',
    width: 160,
    render: (v?: string | null) => (
      <span className="text-xs text-gray-400">{formatTxTime(v)}</span>
    ),
  },
  {
    title: '余额后',
    dataIndex: 'balance_after',
    width: 85,
    render: (v?: number | null) =>
      v != null ? <PointsBadge value={v} size="sm" /> : <span className="text-gray-300">—</span>,
  },
  {
    title: '冻结后',
    dataIndex: 'frozen_after',
    width: 75,
    render: (v?: number | null) => (
      <span className="text-xs text-orange-400">{v ?? '—'}</span>
    ),
  },
]

export interface PointTransactionTableProps {
  dataSource: OperationGroupRead[]
  loading?: boolean
  total?: number
  page?: number
  pageSize?: number
  onChange?: (page: number, pageSize: number) => void
  /** 按流水ID搜索时传入，驱动自动展开到对应账单并高亮该流水行。 */
  highlightTransactionId?: string
  /** 按账单ID搜索时传入，驱动自动展开到对应账单行。 */
  highlightBillingId?: string
}

export const PointTransactionTable: React.FC<PointTransactionTableProps> = ({
  dataSource,
  loading,
  total = 0,
  page = 1,
  pageSize = 10,
  onChange,
  highlightTransactionId,
  highlightBillingId,
}) => {
  const [modelMap, setModelMap] = useState<Record<string, string>>({})
  const [expandedOpKeys, setExpandedOpKeys] = useState<string[]>([])
  const [expandedBillKeys, setExpandedBillKeys] = useState<string[]>([])

  // 解析 model_id → 名称
  useEffect(() => {
    const ids = [
      ...new Set(
        dataSource
          .flatMap((g) => (g.billings ?? []).map((b) => b.model_id))
          .filter((id): id is string => !!id)
      ),
    ]
    if (ids.length === 0) return
    void Promise.all(
      ids.map((id) =>
        LlmService.getModelApiV1LlmModelsModelIdGet({ modelId: id })
          .then((res) => (res.data ? { id, name: res.data.name } : null))
          .catch(() => null)
      )
    ).then((results) => {
      const patch: Record<string, string> = {}
      for (const r of results) if (r) patch[r.id] = r.name
      setModelMap((prev) => ({ ...prev, ...patch }))
    })
  }, [dataSource])

  // 搜索命中时自动展开对应操作组与账单行
  useEffect(() => {
    if (!highlightTransactionId && !highlightBillingId) {
      setExpandedOpKeys([])
      setExpandedBillKeys([])
      return
    }
    const newOpKeys: string[] = []
    const newBillKeys: string[] = []
    for (const op of dataSource) {
      if (!op.cascade_group_id) continue
      for (const bill of op.billings ?? []) {
        const matchBilling = highlightBillingId && bill.billing_id === highlightBillingId
        const matchTx =
          highlightTransactionId &&
          (bill.events ?? []).some((e) => e.id === highlightTransactionId)
        if (matchBilling || matchTx) {
          newOpKeys.push(op.cascade_group_id)
          newBillKeys.push(bill.billing_id)
        }
      }
    }
    setExpandedOpKeys(newOpKeys)
    setExpandedBillKeys(newBillKeys)
  }, [dataSource, highlightTransactionId, highlightBillingId])

  // Level 2 列定义（账单行）
  const billingColumns = (modelMap: Record<string, string>): TableColumnsType<BillingLifecycleRead> => [
    {
      title: 'ID',
      dataIndex: 'billing_id',
      width: 185,
      render: (v: string) => (
        <span className="flex items-center gap-1">
          <Tag color="purple" className="m-0 shrink-0 !text-xs !py-0">账单</Tag>
          <CopyableId value={v} />
        </span>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (v: string) => {
        const st = BILLING_STATUS_MAP[v] ?? { label: v, color: 'default' }
        return <Tag color={st.color}>{st.label}</Tag>
      },
    },
    {
      title: '模型',
      dataIndex: 'model_id',
      ellipsis: true,
      render: (v: string | null) => (
        <span className="text-xs text-gray-500">{v ? (modelMap[v] ?? v) : '—'}</span>
      ),
    },
    {
      title: '冻结额',
      dataIndex: 'frozen_amount',
      width: 75,
      render: (v: number) => (
        <span className="text-orange-500 text-xs font-medium">{v}</span>
      ),
    },
    {
      title: '扣减额',
      dataIndex: 'net_amount',
      width: 75,
      render: (v: number) =>
        v > 0 ? (
          <span className="text-red-500 text-xs font-medium">−{v}</span>
        ) : (
          <span className="text-gray-300">—</span>
        ),
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 165,
      render: (v?: string | null) => (
        <span className="text-xs text-gray-400">{formatTxTime(v)}</span>
      ),
    },
  ]

  // Level 1 列定义（操作组行）
  const opColumns: TableColumnsType<OperationGroupRead> = [
    {
      title: 'ID',
      dataIndex: 'cascade_group_id',
      width: 195,
      render: (v?: string | null) => (
        <span className="flex items-center gap-1">
          <Tag className="m-0 shrink-0 !text-xs !py-0">操作</Tag>
          <CopyableId value={v} />
        </span>
      ),
    },
    {
      title: '业务类型',
      dataIndex: 'business_type',
      render: (v?: string | null) => formatBusinessType(v),
    },
    {
      title: '操作时间',
      dataIndex: 'created_at',
      width: 165,
      render: (v?: string | null) => formatTxTime(v),
    },
    {
      title: '净消耗',
      dataIndex: 'total_net',
      width: 100,
      render: (v?: number) => <PointsBadge value={v ?? 0} size="sm" />,
    },
    {
      title: '账单数',
      width: 75,
      render: (_: unknown, record: OperationGroupRead) => (
        <span className="text-gray-400 text-xs">{record.billings?.length ?? 0} 笔</span>
      ),
    },
  ]

  const expandIcon = ({
    expanded,
    onExpand,
    record,
  }: {
    expanded: boolean
    onExpand: (record: unknown, e: React.MouseEvent) => void
    record: unknown
  }) => (
    <RightOutlined
      className={`transition-transform duration-200 text-gray-400 cursor-pointer mr-1 ${
        expanded ? 'rotate-90' : ''
      }`}
      onClick={(e) => onExpand(record, e)}
    />
  )

  return (
    <Table<OperationGroupRead>
      rowKey={(r) => r.cascade_group_id ?? JSON.stringify(r)}
      loading={loading}
      dataSource={dataSource}
      columns={opColumns}
      size="small"
      scroll={{ x: 800 }}
      onRow={() => ({ style: { cursor: 'pointer' } })}
      expandable={{
        expandedRowKeys: expandedOpKeys,
        onExpandedRowsChange: (keys) => setExpandedOpKeys(keys as string[]),
        expandRowByClick: true,
        showExpandColumn: true,
        expandIcon,
        expandedRowRender: (op: OperationGroupRead) => (
          <div className="bg-slate-50 py-2 px-4">
            <Table<BillingLifecycleRead>
              rowKey="billing_id"
              dataSource={op.billings ?? []}
              columns={billingColumns(modelMap)}
              size="small"
              pagination={false}
              onRow={() => ({ style: { cursor: 'pointer' } })}
              expandable={{
                expandedRowKeys: expandedBillKeys,
                onExpandedRowsChange: (keys) => setExpandedBillKeys(keys as string[]),
                expandRowByClick: true,
                showExpandColumn: true,
                expandIcon,
                expandedRowRender: (bill: BillingLifecycleRead) => (
                  <div className="bg-slate-100 px-4 py-2">
                    <Table<BillingEventRead>
                      rowKey="id"
                      dataSource={bill.events ?? []}
                      columns={eventColumns(highlightTransactionId)}
                      size="small"
                      pagination={false}
                      rowClassName={(r) =>
                        r.id === highlightTransactionId
                          ? 'bg-amber-50 !ring-1 !ring-amber-300'
                          : ''
                      }
                    />
                  </div>
                ),
              }}
            />
          </div>
        ),
      }}
      pagination={{
        current: page,
        pageSize,
        total,
        showSizeChanger: true,
        onChange,
      }}
    />
  )
}
```

- [ ] **Step 2：TypeScript 类型检查**

```bash
cd front && pnpm exec tsc --noEmit 2>&1 | head -40
```

期望：无报错。若有报错，检查 `BillingEventRead` / `BillingLifecycleRead` 的 `events` 字段是否在生成的类型中已存在（Task 4 的 openapi:update 后应已包含）。

- [ ] **Step 3：提交**

```bash
git add front/src/components/points/PointTransactionTable.tsx
git commit -m "feat(front): PointTransactionTable 重写为三层展开视图，移除 flat 模式"
```

---

## Task 6：更新 PointsPage

**Files:**
- Modify: `front/src/pages/points/PointsPage.tsx`

- [ ] **Step 1：完整替换文件**

```tsx
import { useEffect, useState } from 'react'
import type React from 'react'
import { Card, Input, Select, Space, message } from 'antd'
import { PointsService } from '../../services/generated'
import type {
  OperationGroupRead,
  PointsSummaryRead,
} from '../../services/generated'
import { PointsAccountCard } from '../../components/points/PointsAccountCard'
import { PointTransactionTable } from '../../components/points/PointTransactionTable'

type IdSearchType = 'cascade_group_id' | 'billing_id' | 'transaction_id'

const ID_TYPE_OPTIONS: { label: string; value: IdSearchType }[] = [
  { label: '操作ID', value: 'cascade_group_id' },
  { label: '账单ID', value: 'billing_id' },
  { label: '流水ID', value: 'transaction_id' },
]

/**
 * 用户积分页：展示当前用户积分账户摘要与积分流水（按操作三层展开视图）。
 * 流水支持按三种 ID 类型搜索，流水ID搜索时自动展开并高亮目标行。
 */
const PointsPage: React.FC = () => {
  const [summary, setSummary] = useState<PointsSummaryRead | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [groupedData, setGroupedData] = useState<OperationGroupRead[]>([])
  const [groupedTotal, setGroupedTotal] = useState(0)
  const [groupedLoading, setGroupedLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [searchIdType, setSearchIdType] = useState<IdSearchType>('cascade_group_id')
  const [searchIdValue, setSearchIdValue] = useState<string | undefined>(undefined)
  const [highlightTransactionId, setHighlightTransactionId] = useState<string | undefined>(undefined)

  const loadSummary = async () => {
    setSummaryLoading(true)
    try {
      const res = await PointsService.getMyPointsApiV1PointsMeGet({})
      setSummary(res.data ?? null)
    } catch {
      message.error('积分摘要加载失败')
    } finally {
      setSummaryLoading(false)
    }
  }

  const loadGrouped = async (
    p: number,
    ps: number,
    idType?: IdSearchType,
    idValue?: string,
  ) => {
    setGroupedLoading(true)
    try {
      const res = await PointsService.listGroupedTransactionsApiV1PointsTransactionsGroupedGet({
        page: p,
        pageSize: ps,
        cascadeGroupId: idType === 'cascade_group_id' ? idValue : undefined,
        billingId: idType === 'billing_id' ? idValue : undefined,
        transactionId: idType === 'transaction_id' ? idValue : undefined,
      })
      setGroupedData(res.data?.items ?? [])
      setGroupedTotal(res.data?.pagination?.total ?? 0)
      setHighlightTransactionId(res.data?.matchedTransactionId ?? undefined)
    } catch {
      message.error('流水加载失败')
    } finally {
      setGroupedLoading(false)
    }
  }

  useEffect(() => {
    void loadSummary()
    void loadGrouped(1, pageSize)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const highlightBillingId =
    searchIdType === 'billing_id' ? searchIdValue : undefined

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      <Card title="积分账户">
        <PointsAccountCard summary={summary} loading={summaryLoading} />
      </Card>

      <Card
        title="积分流水"
        extra={
          <Space>
            <Select<IdSearchType>
              size="small"
              value={searchIdType}
              style={{ width: 88 }}
              options={ID_TYPE_OPTIONS}
              onChange={(v) => {
                setSearchIdType(v)
                setSearchIdValue(undefined)
                setHighlightTransactionId(undefined)
              }}
            />
            <Input.Search
              allowClear
              placeholder="输入搜索值"
              size="small"
              style={{ width: 200 }}
              value={searchIdValue}
              onChange={(e) => setSearchIdValue(e.target.value || undefined)}
              onSearch={(v) => {
                const val = v.trim() || undefined
                setSearchIdValue(val)
                setPage(1)
                void loadGrouped(1, pageSize, searchIdType, val)
                if (!val) setHighlightTransactionId(undefined)
              }}
            />
          </Space>
        }
      >
        <PointTransactionTable
          dataSource={groupedData}
          loading={groupedLoading}
          total={groupedTotal}
          page={page}
          pageSize={pageSize}
          highlightTransactionId={highlightTransactionId}
          highlightBillingId={highlightBillingId}
          onChange={(p, ps) => {
            setPage(p)
            setPageSize(ps)
            void loadGrouped(p, ps, searchIdType, searchIdValue)
          }}
        />
      </Card>
    </div>
  )
}

export default PointsPage
```

- [ ] **Step 2：TypeScript 类型检查**

```bash
cd front && pnpm exec tsc --noEmit 2>&1 | head -40
```

期望：无报错。注意 `matchedTransactionId` 是生成客户端的驼峰形式，若生成器使用其他命名约定，按实际生成的字段名调整。

- [ ] **Step 3：提交**

```bash
git add front/src/pages/points/PointsPage.tsx
git commit -m "feat(front): PointsPage 移除明细模式，新增三种 ID 搜索"
```

---

## Task 7：更新 AdminUserDetailPage

**Files:**
- Modify: `front/src/pages/admin/AdminUserDetailPage.tsx`

- [ ] **Step 1：移除 flat 模式相关 state 与函数**

在 `AdminUserDetailPage.tsx` 中删除以下内容：
- `txGroupedView` state（第 47 行附近）
- `txIdSearch` state（第 48 行附近）
- `transactions` state（第 42 行附近）
- `txLoading` state（第 43 行附近）
- `txTotal` state（第 44 行附近）
- `txPage` state（第 45 行附近）
- `txPageSize` state（第 46 行附近）
- `loadTransactions` 函数（第 78 行附近）
- `PointTransactionRead` import（第 26 行附近）

- [ ] **Step 2：新增搜索相关 state**

在保留的 state 区块中新增：

```ts
const [searchIdType, setSearchIdType] = useState<'cascade_group_id' | 'billing_id' | 'transaction_id'>('cascade_group_id')
const [searchIdValue, setSearchIdValue] = useState<string | undefined>(undefined)
const [highlightTransactionId, setHighlightTransactionId] = useState<string | undefined>(undefined)
```

- [ ] **Step 3：更新 loadGrouped 接受搜索参数**

将 `loadGrouped` 替换为：

```ts
const loadGrouped = async (
  page: number,
  pageSize: number,
  idType?: 'cascade_group_id' | 'billing_id' | 'transaction_id',
  idValue?: string,
) => {
  setGroupedLoading(true)
  try {
    const res = await AdminService.listUserPointsTransactionsGroupedApiV1AdminUsersUserIdPointsTransactionsGroupedGet({
      userId: id,
      page,
      pageSize,
      cascadeGroupId: idType === 'cascade_group_id' ? idValue : undefined,
      billingId: idType === 'billing_id' ? idValue : undefined,
      transactionId: idType === 'transaction_id' ? idValue : undefined,
    })
    setGroupedData(res.data?.items ?? [])
    setGroupedTotal(res.data?.pagination?.total ?? 0)
    setHighlightTransactionId(res.data?.matchedTransactionId ?? undefined)
  } catch {
    message.error('分组流水加载失败')
  } finally {
    setGroupedLoading(false)
  }
}
```

- [ ] **Step 4：更新 Tab 内搜索 UI**

将 Tab `transactions` 的 children 头部区域（Radio.Group + 旧 Input.Search）替换为：

```tsx
<div className="mb-3">
  <Space>
    <Select<'cascade_group_id' | 'billing_id' | 'transaction_id'>
      size="small"
      value={searchIdType}
      style={{ width: 88 }}
      options={[
        { label: '操作ID', value: 'cascade_group_id' },
        { label: '账单ID', value: 'billing_id' },
        { label: '流水ID', value: 'transaction_id' },
      ]}
      onChange={(v) => {
        setSearchIdType(v)
        setSearchIdValue(undefined)
        setHighlightTransactionId(undefined)
      }}
    />
    <Input.Search
      allowClear
      placeholder="输入搜索值"
      size="small"
      style={{ width: 200 }}
      value={searchIdValue}
      onChange={(e) => setSearchIdValue(e.target.value || undefined)}
      onSearch={(v) => {
        const val = v.trim() || undefined
        setSearchIdValue(val)
        setGroupedPage(1)
        void loadGrouped(1, groupedPageSize, searchIdType, val)
        if (!val) setHighlightTransactionId(undefined)
      }}
    />
  </Space>
</div>
```

- [ ] **Step 5：更新 PointTransactionTable 调用**

将 `<PointTransactionTable ...>` 的 props 更新为：

```tsx
<PointTransactionTable
  dataSource={groupedData}
  loading={groupedLoading}
  total={groupedTotal}
  page={groupedPage}
  pageSize={groupedPageSize}
  highlightTransactionId={highlightTransactionId}
  highlightBillingId={searchIdType === 'billing_id' ? searchIdValue : undefined}
  onChange={(page, pageSize) => {
    setGroupedPage(page)
    setGroupedPageSize(pageSize)
    void loadGrouped(page, pageSize, searchIdType, searchIdValue)
  }}
/>
```

同时删除 `viewMode` prop（组件已不再接受此 prop）。

- [ ] **Step 6：移除已无用的充值后刷新逻辑中的 flat 分支**

找到 `handleRecharge` 中 `if (txGroupedView)` 分支（约第 154 行），替换为：

```ts
setGroupedPage(1)
await loadGrouped(1, groupedPageSize)
```

- [ ] **Step 7：清理 import**

删除 `PointTransactionRead` 和 `Radio` 的 import（若已无使用）。

- [ ] **Step 8：TypeScript 类型检查**

```bash
cd front && pnpm exec tsc --noEmit 2>&1 | head -40
```

期望：无报错。

- [ ] **Step 9：提交**

```bash
git add front/src/pages/admin/AdminUserDetailPage.tsx
git commit -m "feat(front): AdminUserDetailPage 移除明细模式，新增三种 ID 搜索"
```

---

## Task 8：最终验证

- [ ] **Step 1：后端全量相关测试**

```bash
cd backend && uv run pytest tests/test_points_api.py tests/test_points_ledger.py tests/test_auto_cascade_billing.py -q
```

期望：全部 PASS。

- [ ] **Step 2：前端 TypeScript 类型检查**

```bash
cd front && pnpm exec tsc --noEmit
```

期望：无报错。

- [ ] **Step 3：前端 ESLint**

```bash
cd front && pnpm run lint 2>&1 | tail -20
```

期望：无 error（warning 可接受）。

- [ ] **Step 4：最终提交**

若以上三步均通过，确认无遗漏修改：

```bash
git status
```

如有未提交文件，补充提交后完成。
