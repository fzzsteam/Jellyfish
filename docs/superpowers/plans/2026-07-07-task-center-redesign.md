# Task Center Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move task center to a top-level page, show clearer task context and raw errors, and expose full traceback only to administrators.

**Architecture:** Keep `generation_tasks.error` as the raw user-visible error. Add `generation_tasks.error_trace` for full traceback text, return it only when `current_user.is_admin` is true, and render it behind an admin-only “查看错误详情” control. Replace the floating task-center widget with a normal routed page while keeping the runtime polling store for global task state.

**Tech Stack:** FastAPI, SQLAlchemy async/sync stores, MySQL SQL migration scripts, OpenAPI generated TypeScript client, React, Ant Design, Zustand.

---

## File Structure

- Modify `backend/app/models/task.py`: add `GenerationTask.error_trace`.
- Modify `backend/sql/017-add-generation-task-error-trace.sql`: add idempotent MySQL migration.
- Modify `backend/app/core/task_manager/types.py`: add `error` / `error_trace` to task list and status/result view types where needed.
- Modify `backend/app/core/task_manager/stores.py`: select and persist `error_trace`; extend async and sync `set_error`.
- Modify async worker failure sites:
  - `backend/app/services/studio/image_task_runner.py`
  - `backend/app/services/film/generated_video.py`
  - `backend/app/services/film/shot_frame_prompt_tasks.py`
  - `backend/app/services/script_processing_tasks.py`
  - `backend/app/core/task_manager/strategies.py`
  - `backend/app/services/worker/task_executor.py`
- Modify `backend/app/api/v1/routes/film/common.py`: add `error` and admin-gated `error_trace` to task response schemas.
- Modify `backend/app/api/v1/routes/film/task_status.py`: return `error_trace` only for admins.
- Test `backend/tests/test_task_status_api_responses.py`: assert admin-only `error_trace`.
- Run `pnpm run openapi:update` after backend schema changes.
- Modify generated frontend models via OpenAPI update.
- Create `front/src/pages/tasks/TaskCenterPage.tsx`: full task list page.
- Modify `front/src/layouts/MainLayout.tsx`: add top-level “任务中心” menu item and remove floating `<TaskCenter />`.
- Modify `front/src/App.tsx`: add `/tasks` route.
- Modify `front/src/pages/aiStudio/components/TaskCenter.tsx`: either delete or stop rendering it from layout. Prefer delete after confirming no imports remain.
- Modify `front/src/pages/aiStudio/components/taskUiStore.ts`: carry `error` / `error_trace`.
- Modify `front/src/pages/aiStudio/components/taskNotificationHelpers.tsx`: remove “查看” buttons from running and settled notifications.
- Modify docs only in `docs/superpowers/plans` as this project no longer needs Hugo site documentation for this task.

---

### Task 1: Backend Error Trace Contract

**Files:**
- Modify: `backend/app/models/task.py`
- Create: `backend/sql/017-add-generation-task-error-trace.sql`
- Modify: `backend/app/core/task_manager/types.py`
- Modify: `backend/app/core/task_manager/stores.py`
- Modify: `backend/app/api/v1/routes/film/common.py`
- Modify: `backend/app/api/v1/routes/film/task_status.py`
- Test: `backend/tests/test_task_status_api_responses.py`

- [ ] **Step 1: Keep the failing admin-gating test**

Ensure `backend/tests/test_task_status_api_responses.py` contains:

```python
def test_list_tasks_exposes_error_trace_only_to_admin(client: TestClient, monkeypatch) -> None:
    class _FakeStore:
        def __init__(self, _db) -> None:
            pass

        async def list_task_views(self, **_kwargs):
            from app.core.task_manager.types import TaskListItemView

            return (
                [
                    TaskListItemView(
                        id="task-failed",
                        task_kind="image_generation",
                        status=TaskStatus.failed,
                        progress=20,
                        error="RuntimeError: provider failed",
                        error_trace="Traceback (most recent call last):\nRuntimeError: provider failed",
                    )
                ],
                1,
            )

    async def _admin_user():
        return User(id="admin-1", username="admin", hashed_password="x", is_admin=True, is_active=True)

    async def _normal_user():
        return User(id="user-1", username="user", hashed_password="x", is_admin=False, is_active=True)

    monkeypatch.setattr(task_status_route, "SqlAlchemyTaskStore", _FakeStore)
    db = _FakeTaskDB()
    app.dependency_overrides[get_db] = _override_db(db)
    app.dependency_overrides[get_current_user] = _normal_user
    try:
        normal_response = client.get("/api/v1/film/tasks")
        app.dependency_overrides[get_current_user] = _admin_user
        admin_response = client.get("/api/v1/film/tasks")
    finally:
        app.dependency_overrides.clear()

    assert normal_response.status_code == 200
    assert normal_response.json()["data"]["items"][0]["error"] == "RuntimeError: provider failed"
    assert normal_response.json()["data"]["items"][0]["error_trace"] is None
    assert admin_response.status_code == 200
    assert admin_response.json()["data"]["items"][0]["error_trace"].startswith("Traceback")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
uv run pytest tests/test_task_status_api_responses.py::test_list_tasks_exposes_error_trace_only_to_admin -q
```

Expected: FAIL because `TaskListItemView` and `TaskListItemRead` do not yet expose `error_trace`.

- [ ] **Step 3: Add model and migration**

In `backend/app/models/task.py`, add after `error`:

```python
    error_trace: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        comment="失败异常链路，仅管理员可通过任务中心查看",
    )
```

Create `backend/sql/017-add-generation-task-error-trace.sql`:

```sql
SET @has_generation_tasks_error_trace = (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'generation_tasks'
    AND COLUMN_NAME = 'error_trace'
);

SET @add_generation_tasks_error_trace = IF(
  @has_generation_tasks_error_trace = 0,
  "ALTER TABLE generation_tasks ADD COLUMN error_trace LONGTEXT NOT NULL COMMENT '失败异常链路，仅管理员可通过任务中心查看'",
  "SELECT 1"
);
PREPARE stmt_add_generation_tasks_error_trace FROM @add_generation_tasks_error_trace;
EXECUTE stmt_add_generation_tasks_error_trace;
DEALLOCATE PREPARE stmt_add_generation_tasks_error_trace;
```

- [ ] **Step 4: Extend task view dataclasses**

In `backend/app/core/task_manager/types.py`:

```python
@dataclass(slots=True)
class TaskStatusView:
    ...
    error: str = ""
    error_trace: str = ""
```

```python
@dataclass(slots=True)
class TaskListItemView:
    ...
    error: str = ""
    error_trace: str = ""
```

Keep `TaskRecord.error` unchanged for summary; add:

```python
    error_trace: str = ""
```

- [ ] **Step 5: Persist and select error_trace**

In `backend/app/core/task_manager/stores.py`:

```python
def _task_record_from_row(row: GenerationTask) -> TaskRecord:
    return TaskRecord(
        ...
        error=row.error or "",
        error_trace=row.error_trace or "",
        ...
    )
```

Include `GenerationTask.error_trace` in `get_status_view` select and return it:

```python
GenerationTask.error_trace,
...
error_trace=row.error_trace or "",
```

In `list_task_views`, set:

```python
error=task.error or "",
error_trace=task.error_trace or "",
```

Change async store method signature and implementation:

```python
async def set_error(self, task_id: str, error: str, *, error_trace: str = "") -> None:
    await self._update_columns(task_id, error=error or "", error_trace=error_trace or "")
```

Change sync store method:

```python
def set_error(self, task_id: str, error: str, *, error_trace: str = "") -> None:
    row = self.db.get(GenerationTask, task_id)
    if row is None:
        return
    row.error = error or ""
    row.error_trace = error_trace or ""
    self.db.flush()
```

- [ ] **Step 6: Add API schema fields and admin gating**

In `backend/app/api/v1/routes/film/common.py`, add to `TaskListItemRead`:

```python
    error: str = Field("", description="失败原因摘要")
    error_trace: str | None = Field(None, description="完整异常链路，仅管理员返回")
```

Add to `TaskStatusRead` and `TaskResultRead`:

```python
    error: str = ""
    error_trace: str | None = None
```

In `backend/app/api/v1/routes/film/task_status.py`, when creating response items:

```python
error=item.error,
error_trace=item.error_trace if current_user.is_admin else None,
```

For status/result responses:

```python
error=view.error,
error_trace=view.error_trace if current_user.is_admin else None,
```

```python
error=rec.error,
error_trace=rec.error_trace if current_user.is_admin else None,
```

- [ ] **Step 7: Run backend response test**

Run:

```bash
cd backend
uv run pytest tests/test_task_status_api_responses.py::test_list_tasks_exposes_error_trace_only_to_admin -q
```

Expected: PASS.

---

### Task 2: Capture Full Tracebacks on Task Failure

**Files:**
- Modify: `backend/app/services/studio/image_task_runner.py`
- Modify: `backend/app/services/film/generated_video.py`
- Modify: `backend/app/services/film/shot_frame_prompt_tasks.py`
- Modify: `backend/app/services/script_processing_tasks.py`
- Modify: `backend/app/core/task_manager/strategies.py`
- Modify: `backend/app/services/worker/task_executor.py`
- Test: `backend/tests/test_image_task_runner_candidates.py`

- [ ] **Step 1: Write failing traceback persistence test**

Add to `backend/tests/test_image_task_runner_candidates.py` near existing provider error test:

```python
@pytest.mark.asyncio
async def test_run_image_generation_task_persists_error_trace_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, engine = await _build_session()
    try:
        task_id = "task-error-trace"
        db.add(
            GenerationTask(
                id=task_id,
                mode=GenerationDeliveryMode.async_polling,
                task_kind="image_generation",
                status=GenerationTaskStatus.pending,
                progress=0,
                payload={},
                result=None,
                error="",
                error_trace="",
                user_id="test-user",
            )
        )
        await db.commit()
        await db.close()

        class ExplodingImageGenerationTask:
            def __init__(self, *args: object, **kwargs: object) -> None:
                pass

            async def run(self) -> None:
                raise RuntimeError("provider exploded")

        async_session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        monkeypatch.setattr("app.services.studio.image_task_runner.async_session_maker", async_session_local)
        monkeypatch.setattr("app.services.studio.image_task_runner.ImageGenerationTask", ExplodingImageGenerationTask)

        await run_image_generation_task(
            task_id,
            {
                "provider": "aliyun_bailian",
                "api_key": "test-key",
                "base_url": None,
                "relation_type": "scene_image",
                "relation_entity_id": "1",
                "input": {"prompt": "生成图片", "model": "wan2.7-image-pro"},
            },
        )

        async with async_session_local() as verify_db:
            row = await verify_db.get(GenerationTask, task_id)
            assert row is not None
            assert row.status == GenerationTaskStatus.failed
            assert row.error == "provider exploded"
            assert "Traceback (most recent call last)" in row.error_trace
            assert "RuntimeError: provider exploded" in row.error_trace
    finally:
        await engine.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
uv run pytest tests/test_image_task_runner_candidates.py::test_run_image_generation_task_persists_error_trace_on_exception -q
```

Expected: FAIL because `error_trace` is not written.

- [ ] **Step 3: Add traceback capture imports and calls**

In each async runner failure block, import `traceback` and call:

```python
await store.set_error(task_id, str(exc), error_trace=traceback.format_exc())
```

Apply to:

```python
backend/app/services/studio/image_task_runner.py
backend/app/services/film/generated_video.py
backend/app/services/film/shot_frame_prompt_tasks.py
backend/app/services/script_processing_tasks.py
backend/app/core/task_manager/strategies.py
```

In sync executor `backend/app/services/worker/task_executor.py`, change `_mark_failed`:

```python
def _mark_failed(self, task_id: str, error: str, *, error_trace: str = "") -> None:
    ...
    ctx.store.set_error(task_id, error, error_trace=error_trace)
```

Call it as:

```python
self._mark_failed(task_id, str(exc), error_trace=traceback.format_exc())
```

For `HTTPException`, use:

```python
self._mark_failed(task_id, error, error_trace=traceback.format_exc())
```

- [ ] **Step 4: Run backend tests**

Run:

```bash
cd backend
uv run pytest tests/test_image_task_runner_candidates.py::test_run_image_generation_task_persists_error_trace_on_exception -q
uv run pytest tests/test_task_status_api_responses.py tests/test_image_task_runner_candidates.py -q
```

Expected: PASS.

---

### Task 3: Sync OpenAPI and Generated Frontend Types

**Files:**
- Generated by command: `front/openapi.json`
- Generated by command: `front/src/services/generated/**`

- [ ] **Step 1: Run OpenAPI update**

Run:

```bash
pnpm run openapi:update
```

Expected: generated `TaskListItemRead`, `TaskStatusRead`, and `TaskResultRead` include `error` and `error_trace`.

- [ ] **Step 2: Inspect generated fields**

Run:

```bash
rg -n "error_trace|error" front/src/services/generated/models/TaskListItemRead.ts front/src/services/generated/models/TaskStatusRead.ts front/src/services/generated/models/TaskResultRead.ts
```

Expected: all three models expose `error`; `error_trace` should be nullable.

---

### Task 4: Build Full Task Center Page

**Files:**
- Create: `front/src/pages/tasks/TaskCenterPage.tsx`
- Modify: `front/src/pages/aiStudio/components/taskUiStore.ts`
- Modify: `front/src/pages/aiStudio/components/taskCopy.ts`

- [ ] **Step 1: Extend frontend task item state**

In `front/src/pages/aiStudio/components/taskUiStore.ts`, add:

```ts
  error?: string | null
  errorTrace?: string | null
  createdAtTs?: number | null
  updatedAtTs?: number | null
  executorType?: string | null
  executorTaskId?: string | null
```

Map generated fields:

```ts
      error: server?.error ?? optimistic?.error ?? '',
      errorTrace: server?.error_trace ?? optimistic?.errorTrace ?? null,
      createdAtTs: server?.created_at_ts ?? optimistic?.createdAtTs,
      updatedAtTs: server?.updated_at_ts ?? optimistic?.updatedAtTs,
      executorType: server?.executor_type ?? optimistic?.executorType,
      executorTaskId: server?.executor_task_id ?? optimistic?.executorTaskId,
```

- [ ] **Step 2: Create page component**

Create `front/src/pages/tasks/TaskCenterPage.tsx` with:

```tsx
import { Button, Card, Collapse, Empty, Input, Progress, Select, Space, Table, Tag, Typography, message } from 'antd'
import { CopyOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { FilmService, type TaskListItemRead, type TaskStatus } from '../../services/generated'
import { useAuthStore } from '../../store/useAuthStore'
import { resolveTaskSourceLabel, resolveTaskTitle } from '../aiStudio/components/taskCopy'

const ACTIVE_STATUSES: TaskStatus[] = ['pending', 'running', 'streaming']

function statusLabel(status: TaskStatus): { text: string; color: string } {
  if (status === 'succeeded') return { text: '已完成', color: 'green' }
  if (status === 'failed') return { text: '失败', color: 'red' }
  if (status === 'cancelled') return { text: '已取消', color: 'orange' }
  if (status === 'running') return { text: '运行中', color: 'blue' }
  if (status === 'streaming') return { text: '处理中', color: 'cyan' }
  return { text: '等待中', color: 'default' }
}

function formatTs(ts?: number | null): string {
  if (!ts) return '-'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(ts * 1000))
}

function formatElapsed(ms?: number | null): string {
  if (ms == null || ms < 0) return '-'
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return `${seconds} 秒`
  const minutes = Math.floor(seconds / 60)
  const remainSeconds = seconds % 60
  if (minutes < 60) return remainSeconds ? `${minutes} 分 ${remainSeconds} 秒` : `${minutes} 分`
  const hours = Math.floor(minutes / 60)
  const remainMinutes = minutes % 60
  return remainMinutes ? `${hours} 小时 ${remainMinutes} 分` : `${hours} 小时`
}

export default function TaskCenterPage() {
  const authUser = useAuthStore((state) => state.user)
  const [items, setItems] = useState<TaskListItemRead[]>([])
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<TaskStatus[]>([])
  const [taskKind, setTaskKind] = useState<string | undefined>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await FilmService.listTasksApiV1FilmTasksGet({
        statuses: statusFilter.length ? statusFilter : undefined,
        taskKind,
        recentSeconds: statusFilter.length ? 0 : 86400,
        page,
        pageSize,
      })
      setItems(res.data?.items ?? [])
      setTotal(res.data?.pagination?.total ?? 0)
    } catch {
      message.error('加载任务列表失败')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, statusFilter, taskKind])

  useEffect(() => {
    void load()
  }, [load])

  const taskKindOptions = useMemo(
    () => Array.from(new Set(items.map((item) => item.task_kind))).map((value) => ({ label: resolveTaskTitle(value), value })),
    [items],
  )

  return (
    <div className="h-full overflow-auto bg-gray-50 p-4">
      <Card
        title="任务中心"
        extra={<Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>}
      >
        <Space className="mb-4" wrap>
          <Select
            mode="multiple"
            allowClear
            placeholder="状态"
            value={statusFilter}
            onChange={(value) => {
              setStatusFilter(value)
              setPage(1)
            }}
            style={{ minWidth: 220 }}
            options={[
              { label: '等待中', value: 'pending' },
              { label: '运行中', value: 'running' },
              { label: '处理中', value: 'streaming' },
              { label: '已完成', value: 'succeeded' },
              { label: '失败', value: 'failed' },
              { label: '已取消', value: 'cancelled' },
            ]}
          />
          <Select
            allowClear
            placeholder="任务类型"
            value={taskKind}
            onChange={(value) => {
              setTaskKind(value)
              setPage(1)
            }}
            style={{ minWidth: 220 }}
            options={taskKindOptions}
          />
        </Space>
        <Table
          rowKey="task_id"
          loading={loading}
          dataSource={items}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPage)
              setPageSize(nextPageSize)
            },
          }}
          locale={{ emptyText: <Empty description="暂无任务记录" /> }}
          columns={[
            {
              title: '任务',
              dataIndex: 'task_kind',
              render: (_value, row) => (
                <div className="min-w-[260px]">
                  <div className="font-medium">{resolveTaskTitle(row.task_kind)}</div>
                  <div className="text-xs text-gray-500">{resolveTaskSourceLabel(row.relation_type, row.relation_entity_id) || '无关联上下文'}</div>
                  <Typography.Text copyable className="text-xs text-gray-400">{row.task_id}</Typography.Text>
                </div>
              ),
            },
            {
              title: '状态信息',
              dataIndex: 'status',
              render: (_value, row) => {
                const meta = statusLabel(row.status)
                return (
                  <div className="min-w-[180px]">
                    <Tag color={meta.color}>{meta.text}</Tag>
                    <Progress percent={Math.max(0, Math.min(100, Math.round(row.progress)))} size="small" showInfo={false} />
                    <div className="mt-1 text-xs text-gray-500">进度 {row.progress}%</div>
                  </div>
                )
              },
            },
            {
              title: '时间',
              render: (_value, row) => (
                <div className="text-xs text-gray-500 min-w-[160px]">
                  <div>创建：{formatTs(row.created_at_ts)}</div>
                  <div>更新：{formatTs(row.updated_at_ts)}</div>
                  <div>耗时：{formatElapsed(row.elapsed_ms)}</div>
                </div>
              ),
            },
            {
              title: '错误',
              dataIndex: 'error',
              render: (_value, row) => {
                if (!row.error) return <span className="text-gray-400">-</span>
                return (
                  <div className="max-w-[420px]">
                    <Input.TextArea value={row.error} autoSize={{ minRows: 2, maxRows: 5 }} readOnly />
                    {authUser?.is_admin && row.error_trace ? (
                      <Collapse
                        ghost
                        size="small"
                        items={[
                          {
                            key: 'trace',
                            label: '查看错误详情',
                            children: <pre className="max-h-[360px] overflow-auto whitespace-pre-wrap rounded bg-gray-950 p-3 text-xs text-gray-100">{row.error_trace}</pre>,
                          },
                        ]}
                      />
                    ) : null}
                  </div>
                )
              },
            },
            {
              title: '操作',
              render: (_value, row) => (
                <Space direction="vertical" size={6}>
                  <Button size="small" icon={<CopyOutlined />} onClick={() => void navigator.clipboard.writeText(row.task_id)}>复制 ID</Button>
                  {ACTIVE_STATUSES.includes(row.status) ? (
                    <Button
                      size="small"
                      danger
                      icon={<StopOutlined />}
                      disabled={row.cancel_requested}
                      onClick={async () => {
                        await FilmService.cancelTaskApiV1FilmTasksTaskIdCancelPost({
                          taskId: row.task_id,
                          requestBody: { reason: '用户在任务中心取消任务' },
                        })
                        message.success('已发送取消请求')
                        void load()
                      }}
                    >
                      {row.cancel_requested ? '取消中' : '取消'}
                    </Button>
                  ) : null}
                </Space>
              ),
            },
          ]}
        />
      </Card>
    </div>
  )
}
```

- [ ] **Step 3: Type-check page dependencies**

Run:

```bash
cd front
pnpm exec tsc --noEmit
```

Expected: may fail until route/menu task is complete; errors should only reference missing route imports if any.

---

### Task 5: Move Task Center to Top-Level Navigation

**Files:**
- Modify: `front/src/App.tsx`
- Modify: `front/src/layouts/MainLayout.tsx`
- Delete or stop using: `front/src/pages/aiStudio/components/TaskCenter.tsx`

- [ ] **Step 1: Add route**

In `front/src/App.tsx`, import:

```ts
import TaskCenterPage from './pages/tasks/TaskCenterPage'
```

Add inside the private `MainLayout` route:

```tsx
<Route path="tasks" element={<TaskCenterPage />} />
```

- [ ] **Step 2: Add top-level menu item**

In `front/src/layouts/MainLayout.tsx`, import icon:

```ts
import { UnorderedListOutlined } from '@ant-design/icons'
```

Update selected keys:

```ts
if (location.pathname.startsWith('/tasks')) return ['tasks']
```

Add menu item after projects:

```tsx
{
  key: 'tasks',
  icon: <UnorderedListOutlined />,
  label: <Link to="/tasks">任务中心</Link>,
},
```

- [ ] **Step 3: Remove floating widget render**

In `front/src/layouts/MainLayout.tsx`, remove:

```ts
import { TaskCenter } from '../pages/aiStudio/components/TaskCenter'
```

Remove:

```tsx
<TaskCenter />
```

Keep:

```tsx
<TaskRuntimeProvider>
  ...
</TaskRuntimeProvider>
```

Runtime polling still feeds global task state for pages that need it.

- [ ] **Step 4: Delete unused floating component if no imports remain**

Run:

```bash
rg -n "TaskCenter" front/src
```

If only the component file remains, delete:

```bash
rm front/src/pages/aiStudio/components/TaskCenter.tsx
```

Use `apply_patch` for deletion in this environment.

---

### Task 6: Remove “查看” Buttons from Task Notifications

**Files:**
- Modify: `front/src/pages/aiStudio/components/taskNotificationHelpers.tsx`

- [ ] **Step 1: Remove navigation button from running notifications**

Replace notification `btn` logic with cancel-only:

```tsx
btn:
  onCancel && !task.cancelRequested ? (
    <Button size="small" danger onClick={onCancel}>
      取消任务
    </Button>
  ) : undefined,
```

- [ ] **Step 2: Remove navigation button from settled notifications**

Replace:

```tsx
btn: onNavigate ? <Button size="small" onClick={onNavigate}>查看</Button> : undefined,
```

with:

```tsx
btn: undefined,
```

- [ ] **Step 3: Keep task store navigation metadata**

Do not remove `onNavigate` from `useTaskUiStore` yet. Some pages may still use it internally, and this task only removes the top-right “查看” button.

---

### Task 7: Verification

**Files:**
- No new files beyond prior tasks.

- [ ] **Step 1: Run backend targeted tests**

```bash
cd backend
uv run pytest tests/test_task_status_api_responses.py tests/test_image_task_runner_candidates.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend type check**

```bash
cd front
pnpm exec tsc --noEmit
```

Expected: PASS.

- [ ] **Step 3: Check old floating entry is gone**

```bash
rg -n "TaskCenter|收起任务|任务中心'\\}\\)" front/src/pages/aiStudio/components front/src/layouts front/src/App.tsx
```

Expected: no floating `TaskCenter` render remains; `/tasks` route and side menu entry remain.

- [ ] **Step 4: Check OpenAPI generated fields**

```bash
rg -n "error_trace" front/src/services/generated/models backend/app/api/v1/routes/film/common.py backend/app/core/task_manager
```

Expected: generated models and backend schemas include `error_trace`.

---

## Self-Review

- Spec coverage: top-level menu, user-filtered task list, raw error display, admin-only error details, cancel button, removal of floating entry, and removal of notification “查看” button are all covered.
- Scope control: log SDK/SLS/Sentry integration is deliberately excluded. The task table stores traceback directly as requested.
- Security: `error_trace` is returned only when `current_user.is_admin`; normal users still see raw `error`.
- API sync: OpenAPI update is required because task response models change.
