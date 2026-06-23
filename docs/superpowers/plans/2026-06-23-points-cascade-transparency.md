# 积分流水可读性与级联消费透明化 - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the cascade consumption of "一键提取分镜" (divide + cascaded extract + N image tasks) visible in both pre-operation estimation and post-operation transaction history, with billing_id lifecycle grouping.

**Architecture:** Add a `cascade_group_id` column to `point_transactions` (freeze writes it, consume/unfreeze copy from freeze row). A new grouped API endpoint aggregates by this column. Frontend composes text×2 + per-image unit price for estimation and renders grouped transaction view.

**Tech Stack:** Python/FastAPI/SQLAlchemy, TypeScript/React/Ant Design, MySQL (migration)

---

### Task 1: Model + Migration + Schema

**Files:**
- Modify: `backend/app/models/points.py`
- Create: `backend/sql/013-add-point-transactions-cascade-group-id.sql`
- Modify: `backend/app/schemas/points.py`

- [ ] **Step 1: Add column to PointTransaction model**

In `backend/app/models/points.py`, after the `remark` column:

```python
cascade_group_id: Mapped[str | None] = mapped_column(
    String(64),
    nullable=True,
    index=True,
    comment="级联分组键：同一次操作的 root billing_id；充值/手动调整为 NULL",
)
```

- [ ] **Step 2: Create migration SQL**

`backend/sql/013-add-point-transactions-cascade-group-id.sql`:

```sql
SET @dbname = DATABASE();
SET @exists = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'point_transactions'
      AND COLUMN_NAME = 'cascade_group_id'
);
SET @sql = IF(@exists = 0,
    'ALTER TABLE point_transactions
        ADD COLUMN cascade_group_id VARCHAR(64) NULL COMMENT "级联分组键",
        ADD INDEX ix_point_transactions_cascade_group_id (cascade_group_id)',
    'SELECT "column cascade_group_id already exists"'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
```

- [ ] **Step 3: Add to PointTransactionRead schema**

In `backend/app/schemas/points.py`, after line 111 (`pricing_snapshot: dict[str, Any] | None`), add:

```python
cascade_group_id: str | None = Field(None, description="级联分组键"),
```

- [ ] **Step 4: Add grouped response schemas**

In `backend/app/schemas/points.py`, after `PointTransactionRead`:

```python
class BillingEventRead(BaseModel):
    """同 billing_id 生命周期内的一条事件（freeze/consume/unfreeze 明细）。"""
    id: str
    type: PointTransactionType
    amount: int
    created_at: datetime | None = None
    balance_after: int | None = None
    frozen_after: int | None = None

class BillingLifecycleRead(BaseModel):
    """按 billing_id 聚合的单据生命周期。"""
    billing_id: str
    business_type: str | None = None
    model_id: str | None = None
    status: str   # frozen/settled/refunded
    frozen_amount: int = 0
    net_amount: int = 0   # consume 金额
    events: list[BillingEventRead] = []

class OperationGroupRead(BaseModel):
    """按 cascade_group_id 聚合的操作组。"""
    cascade_group_id: str | None = None
    business_type: str | None = None
    created_at: datetime | None = None
    total_net: int = 0
    billings: list[BillingLifecycleRead] = []

class GroupedTransactionResponse(BaseModel):
    items: list[OperationGroupRead]
    pagination: PaginationInfo
```

- [ ] **Step 5: Run syntax check**

```bash
cd backend && python -m py_compile app/models/points.py app/schemas/points.py
```

Expected: no errors.

---

### Task 2: Ledger — freeze / consume / unfreeze cascade_group_id support

**Files:**
- Modify: `backend/app/services/points/ledger.py`

- [ ] **Step 1: Add `cascade_group_id` param to `freeze_points`**

```python
async def freeze_points(
    db: AsyncSession,
    *,
    user_id: str,
    billing_id: str,
    amount: int,
    model_id: str | None,
    business_type: str,
    business_id: str | None,
    snapshot: dict[str, Any] | None,
    created_by: str | None = None,
    cascade_group_id: str | None = None,
) -> PointTransaction:
```

- [ ] **Step 2: Auto-default cascade_group_id for billing source**

Before the `PointTransaction(...)` constructor in `freeze_points`:

```python
if cascade_group_id is None and source == "billing":
    cascade_group_id = billing_id
```

- [ ] **Step 3: Write into PointTransaction row**

In the `PointTransaction(...)` constructor, add the field:

```python
cascade_group_id=cascade_group_id,
```

- [ ] **Step 4: consume_frozen — copy from freeze_tx**

In `consume_frozen`'s `PointTransaction(...)` constructor, add:

```python
cascade_group_id=freeze_tx.cascade_group_id,
```

(Same spot as `business_type=freeze_tx.business_type` — follow the existing copy pattern.)

- [ ] **Step 5: unfreeze_frozen — copy from freeze_tx**

Same addition in `unfreeze_frozen`'s `PointTransaction(...)` constructor:

```python
cascade_group_id=freeze_tx.cascade_group_id,
```

- [ ] **Step 6: Run syntax check**

```bash
cd backend && python -m py_compile app/services/points/ledger.py
```

Expected: no errors.

---

### Task 3: Billing layer — freeze_for_task + grouped query

**Files:**
- Modify: `backend/app/services/points/billing.py`

- [ ] **Step 1: freeze_for_task passes cascade_group_id**

```python
async def freeze_for_task(
    db: AsyncSession,
    *,
    user_id: str,
    quote_token: str,
    business_type: str,
    category: ModelCategoryKey,
    model_id: str | None,
    cascade_group_id: str | None = None,
) -> FreezeForTaskResult:
```

Inside, in the `freeze_points` call, add `cascade_group_id=cascade_group_id`.

- [ ] **Step 2: Add list_grouped_transactions function**

After `list_user_transactions`, add a new async function:

```python
async def list_grouped_transactions(
    db: AsyncSession,
    *,
    user_id: str,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
```

Key query logic:
1. Select distinct `cascade_group_id` for the user, with `MIN(created_at)` per group, ordered by that time desc, paginated.
2. Count total distinct groups (plus NULL groups).
3. Load all `point_transactions` matching those `cascade_group_id`s in one query.
4. In memory, group by `cascade_group_id` → then by `billing_id` → compute status/net per billing → compute total_net per group.
5. NULL-cascade_group_id transactions (recharge) become single-member groups keyed by `billing_id`.

The output dicts must match `OperationGroupRead` structure:
```python
{
    "cascade_group_id": str | None,
    "business_type": str | None,
    "created_at": datetime,    # group min time
    "total_net": int,          # sum of consume amounts
    "billings": [{
        "billing_id", "business_type", "model_id",
        "status", "frozen_amount", "net_amount",
        "events": [{"id", "type", "amount", "created_at", "balance_after", "frozen_after"}]
    }]
}
```

- [ ] **Step 3: Run syntax check**

```bash
cd backend && python -m py_compile app/services/points/billing.py
```

Expected: no errors.

---

### Task 4: Script processing tasks — _freeze_for_script_task

**Files:**
- Modify: `backend/app/services/script_processing_tasks.py`

- [ ] **Step 1: Add cascade_group_id param to _freeze_for_script_task**

```python
async def _freeze_for_script_task(
    db: AsyncSession,
    *,
    user_id: str,
    quote_token: str | None,
    business_type: str,
    cascade_group_id: str | None = None,
) -> str | None:
```

In the `freeze_for_task` call, add `cascade_group_id=cascade_group_id`.

- [ ] **Step 2: Update all callers**

All `create_*_task` functions call `_freeze_for_script_task`. Pass `cascade_group_id=None` (default) — `freeze_points` auto-defaults to `billing_id` for billing sources, so root tasks get their own billing_id as cascade_group_id automatically.

- [ ] **Step 3: Run syntax check**

```bash
cd backend && python -m py_compile app/services/script_processing_tasks.py
```

---

### Task 5: Shot auto preparation — cascade_root_billing_id chain

**Files:**
- Modify: `backend/app/services/studio/shot_auto_preparation.py`

- [ ] **Step 1: Add cascade_root_billing_id to _freeze_image_task_async**

```python
async def _freeze_image_task_async(
    *,
    user_id: str,
    billing_id: str,
    amount: int,
    model_id: str,
    unit_points: int,
    cascade_group_id: str | None = None,
) -> None:
```

In the `freeze_points` call, add `cascade_group_id=cascade_group_id`.

- [ ] **Step 2: Add cascade_root_billing_id to _schedule_image_task_sync**

```python
def _schedule_image_task_sync(
    db: Session,
    *,
    ...,
    cascade_root_billing_id: str | None = None,
) -> None:
```

In the `_freeze_image_task_async` call, add `cascade_group_id=cascade_root_billing_id`.

- [ ] **Step 3: Add cascade_root_billing_id to _auto_create_and_link_sync**

```python
def _auto_create_and_link_sync(
    db: Session,
    *,
    ...,
    cascade_root_billing_id: str | None = None,
) -> bool:
```

In the `_schedule_image_task_sync` call, add `cascade_root_billing_id=cascade_root_billing_id`.

- [ ] **Step 4: Add cascade_root_billing_id to auto_prepare_chapter_shots_sync**

```python
def auto_prepare_chapter_shots_sync(
    db: Session,
    *,
    user_id: str,
    project_id: str,
    chapter_id: str,
    cascade_root_billing_id: str | None = None,
) -> AutoPreparationSummary:
```

In the two `_schedule_image_task_sync` calls (lines ~1004 and ~1105 in the file), add `cascade_root_billing_id=cascade_root_billing_id`.

- [ ] **Step 5: Run syntax check**

```bash
cd backend && python -m py_compile app/services/studio/shot_auto_preparation.py
```

---

### Task 6: Worker — executor wiring

**Files:**
- Modify: `backend/app/services/script_processing_worker.py`

- [ ] **Step 1: DivideTaskExecutor.apply_result — pass root billing_id**

```python
summary = apply_auto_extraction_after_division(
    ctx.db, user_id=ctx.task.user_id, chapter_id=chapter_id, result=result,
    cascade_root_billing_id=ctx.task.billing_id,
)
```

- [ ] **Step 2: apply_auto_extraction_after_division — propagate to extract freeze + auto-prep**

Add `cascade_root_billing_id: str | None = None` parameter to `apply_auto_extraction_after_division`. In the three `auto_prepare_chapter_shots_sync` calls, pass `cascade_root_billing_id=cascade_root_billing_id`. In the extract `_freeze_text_call_async` call, add `cascade_group_id=cascade_root_billing_id`.

- [ ] **Step 3: ExtractTaskExecutor.apply_result — pass root billing_id**

```python
summary = auto_prepare_chapter_shots_sync(
    ctx.db, user_id=ctx.task.user_id, project_id=project_id, chapter_id=chapter_id,
    cascade_root_billing_id=ctx.task.billing_id,
)
```

- [ ] **Step 4: Run syntax check**

```bash
cd backend && python -m py_compile app/services/script_processing_worker.py
```

---

### Task 7: API — new grouped endpoint

**Files:**
- Modify: `backend/app/api/v1/routes/points.py`

- [ ] **Step 1: Add grouped endpoint**

```python
from app.schemas.points import (
    GroupedTransactionResponse, OperationGroupRead, BillingLifecycleRead, BillingEventRead,
)

@router.get(
    "/transactions/grouped",
    response_model=ApiResponse[GroupedTransactionResponse],
    summary="按操作组聚合的积分流水",
)
async def list_grouped_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[GroupedTransactionResponse]:
    """按 cascade_group_id 聚合展示流水。同一操作级联的多个 billing_id 归为一组。"""
    from app.services.points.billing import list_grouped_transactions
    groups, total = await list_grouped_transactions(
        db, user_id=current_user.id, page=page, page_size=page_size,
    )
    from app.schemas.common import pagination_info
    return success_response(GroupedTransactionResponse(
        items=[OperationGroupRead(**g) for g in groups],
        pagination=pagination_info(page=page, page_size=page_size, total=total),
    ))
```

- [ ] **Step 2: Run syntax check**

```bash
cd backend && python -m py_compile app/api/v1/routes/points.py
```

---

### Task 8: Frontend — business type mapping + PointsCostHint

**Files:**
- Create: `front/src/components/points/businessTypeLabels.ts`
- Modify: `front/src/components/points/PointsCostHint.tsx`
- Modify: `front/src/pages/aiStudio/project/ProjectWorkbench/tabs/ChaptersTab.tsx`

- [ ] **Step 1: Create business type mapping**

`front/src/components/points/businessTypeLabels.ts`:

```ts
export const BUSINESS_TYPE_LABELS: Record<string, string> = {
  script_divide: '分镜拆解',
  script_extract: '分镜提取',
  script_merge: '实体合并',
  script_consistency: '一致性检查',
  script_variant: '变体分析',
  script_character_portrait: '角色形象分析',
  script_prop_info: '道具信息分析',
  script_scene_info: '场景信息分析',
  script_costume_info: '服装信息分析',
  script_optimize: '剧本优化',
  script_simplify: '剧本精简',
  image_generation: '图片生成',
  video_generation: '视频生成',
}

export function formatBusinessType(key: string | null | undefined): string {
  if (!key) return '—'
  return BUSINESS_TYPE_LABELS[key] ?? key
}
```

- [ ] **Step 2: Update PointsCostHint props**

Add optional props: `textMultiplier?: number` and `perImagePoints?: number | null`.

When `quote` is sufficient and `perImagePoints != null`:
```
将消耗 [X×Y] 每张资产图 [Z]（按实际新建数量另计）
```

When `perImagePoints === null` (user has no default image model):
```
将消耗 [X×Y] 图片模型未配置
```

Add CSS class `inline-flex items-center gap-1 text-xs text-gray-400` on the fragment wrapper.

- [ ] **Step 3: Add second usePointsQuote in ChaptersTab**

After `const divideQuote = usePointsQuote({...})`, add:

```ts
const imageQuote = usePointsQuote({
  businessType: 'image_generation',
  category: 'image',
  modelId: null,
  enabled: chapters.length > 0,
  generationCount: 1,
})
```

- [ ] **Step 4: Wire into PointsCostHint**

```tsx
<PointsCostHint
  quote={divideQuote.quote}
  loading={divideQuote.loading}
  error={divideQuote.error}
  textMultiplier={2}
  perImagePoints={imageQuote.quote?.required_points ?? null}
/>
{imageQuote.quote && (
  <div className="text-xs text-gray-400 mt-0.5">
    分镜拆解为必执行项；若积分不足以覆盖资产图生成，对应资产将建档但不生成图片。
  </div>
)}
```

- [ ] **Step 5: Run TypeScript check**

```bash
cd front && pnpm exec tsc --noEmit
```

---

### Task 9: Frontend — PointTransactionTable grouped view

**Files:**
- Modify: `front/src/components/points/PointTransactionTable.tsx`
- Modify: `front/src/pages/points/PointsPage.tsx`

- [ ] **Step 1: Add grouped state + API call in PointsPage**

```ts
const [groupedView, setGroupedView] = useState(false)
const [groupedData, setGroupedData] = useState<OperationGroupRead[]>([])
const [groupedTotal, setGroupedTotal] = useState(0)
const [groupedLoading, setGroupedLoading] = useState(false)

const loadGrouped = async (p: number, ps: number) => {
  setGroupedLoading(true)
  try {
    const res = await PointsService.listGroupedTransactionsApiV1PointsTransactionsGroupedGet({
      page: p, pageSize: ps,
    })
    setGroupedData(res.data?.items ?? [])
    setGroupedTotal(res.data?.pagination?.total ?? 0)
  } catch {
    message.error('分组流水加载失败')
  } finally {
    setGroupedLoading(false)
  }
}
```

Add a Radio/segmented control next to the type filter to toggle between flat and grouped view.

- [ ] **Step 2: Add grouped table rendering**

Accept a `viewMode` prop in `PointTransactionTable`. When `"grouped"`, render rows per `OperationGroupRead`:

```
Row: [时间] [业务类型] [净消耗] [展开▶]
Expand: billing列表 — each shows [billing_id] [状态] [冻结额→净额]
  Expand→billing: event明细 list
```

Use `expandable` on `Table<OperationGroupRead>` with `expandedRowRender`.

Columns for grouped mode:
```ts
columns = [
  { title: '操作时间', width: 180, render: (g) => formatTxTime(g.created_at) },
  { title: '业务类型', render: (g) => formatBusinessType(g.business_type) },
  { title: '净消耗', render: (g) => <PointsBadge value={g.total_net} size="sm" /> },
  { title: '账单数', render: (g) => `${g.billings.length} 笔` },
]
```

- [ ] **Step 3: Use formatBusinessType in flat mode**

In flat mode columns, replace `{ title: '业务类型', dataIndex: 'business_type', render: (v) => v || '—' }` with:
```tsx
{ title: '业务类型', dataIndex: 'business_type', render: (v) => formatBusinessType(v) || '—' },
```

- [ ] **Step 4: Run TypeScript check**

```bash
cd front && pnpm exec tsc --noEmit
```

Expected: no errors.

---

### Task 10: OpenAPI regenerate + verification

- [ ] **Step 1: Start backend dev server**

```bash
cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
```

- [ ] **Step 2: Regenerate OpenAPI client**

```bash
cd front && pnpm run openapi:update
```

Expected: generates updated types including `OperationGroupRead`, `BillingLifecycleRead`, `BillingEventRead`, `GroupedTransactionResponse`, and `cascade_group_id` on `PointTransactionRead`.

- [ ] **Step 3: Run tests**

```bash
cd backend && uv run pytest tests/test_points_sync_billing.py tests/test_auto_cascade_billing.py -q
```

Expected: existing tests pass (cascade_group_id is nullable, default None — all existing behavior preserved).

- [ ] **Step 4: Run frontend type check**

```bash
cd front && pnpm exec tsc --noEmit
```

Expected: no type errors.

- [ ] **Step 5: Clean up**

```bash
kill %1 2>/dev/null; true
```

---

### Task 11: Update architecture doc

**Files:**
- Modify: `site/content/docs/architecture/points-billing.md`

- [ ] **Step 1: Document cascade_group_id column**

In the `point_transactions` table section, add row:

```markdown
| `cascade_group_id` | VARCHAR(64) NULL, index | 级联分组键，同一次操作的 root billing_id |
```

- [ ] **Step 2: Document grouped endpoint**

After the "API endpoints" listing, add a paragraph for `GET /transactions/grouped` — what it does, when to use it.

- [ ] **Step 3: Document the cascade billing flow**

Add a subsection describing how divide + auto-extract + auto-prep image cascade billing works, and how `cascade_group_id` ties the billing_ids together for the grouped view.