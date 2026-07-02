# Project Shot Flow Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将项目入口、分镜列表、镜头详情和原分镜工作室收敛为“章节流水线 -> 分镜列表 -> 镜头详情四步闭环”的主流程。

**Architecture:** 保留现有后端 API 与 OpenAPI generated client，优先迁移前端信息架构与页面职责。单镜头生成能力从 `ChapterStudio` 迁移到 `ChapterShotEditPage` 的新增 Tab，批量能力迁移到 `ChapterShotsPage` 顶部工具栏，旧 `/studio` 路由改为兼容跳转。

**Tech Stack:** React, TypeScript, Vite, Ant Design, React Router, OpenAPI generated services, pnpm.

---

## File Map

- Modify: `front/src/layouts/MainLayout.tsx`
  - 移除顶部“分镜列表 / 分镜工作室”项目级导航。
  - 保留项目上下文导航到项目工作台。
- Modify: `front/src/pages/aiStudio/project/ProjectWorkbench/constants.tsx`
  - 默认 Tab 改为 `chapters`。
  - Dashboard 文案改为“总览”。
- Modify: `front/src/pages/aiStudio/project/ProjectWorkbench/index.tsx`
  - 主 CTA 不再跳工作室。
  - 准备状态统一跳分镜列表或章节 Tab。
- Modify: `front/src/pages/aiStudio/project/ProjectWorkbench/chapterPreparation.tsx`
  - `prepare_shots` 文案改为“确认/处理分镜”，不叫“进入工作室”。
- Modify: `front/src/pages/aiStudio/project/ProjectWorkbench/tabs/DashboardTab.tsx`
  - 删除推荐动作、当前待办、动态摘要。
  - 保留资产健康快照和项目轻量统计。
- Modify: `front/src/pages/aiStudio/project/ProjectWorkbench/tabs/ChaptersTab.tsx`
  - 章节主动作不再跳工作室。
- Modify: `front/src/pages/aiStudio/project/ProjectLobby.tsx`
  - 项目卡片按钮固定为“打开项目”。
  - 删除项目速览重复入口。
- Modify: `front/src/pages/aiStudio/project/ProjectWorkbench/routes.ts`
  - 支持镜头详情 Tab query 的路径 helper。
- Modify: `front/src/App.tsx`
  - `/studio` 路由改用兼容跳转组件。
- Create: `front/src/pages/aiStudio/chapter/ChapterStudioRedirect.tsx`
  - 旧工作室路由跳转到推荐镜头详情的“生成视频” Tab，若无镜头则跳分镜列表。
- Modify: `front/src/pages/aiStudio/shots/ChapterShotsPage.tsx`
  - 分镜列表去掉进入工作室按钮。
  - 每行主按钮按步骤跳镜头详情 Tab。
  - 批量工具栏收口为批量生成、批量下载、批量诊断、更多维护。
- Create: `front/src/pages/aiStudio/shots/shotFlowStatus.ts`
  - 集中计算分镜列表行状态和主动作。
- Create: `front/src/pages/aiStudio/shots/components/ShotBatchToolbar.tsx`
  - 分镜列表批量工具栏。
- Create: `front/src/pages/aiStudio/shots/components/ShotVideoGenerationTab.tsx`
  - 镜头详情“生成视频” Tab。
- Create: `front/src/pages/aiStudio/shots/components/ShotVideoResultsTab.tsx`
  - 镜头详情“视频结果” Tab。
- Create: `front/src/pages/aiStudio/shots/components/VideoDiagnosticsDrawer.tsx`
  - 单镜头和批量诊断展示。
- Modify: `front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx`
  - 两 Tab 扩展为四 Tab。
  - 接入生成视频、视频结果、诊断入口。
- Reference: `front/src/pages/aiStudio/chapter/ChapterStudio.tsx`
  - 仅作为迁移单镜头生成逻辑的参考文件，不在本计划中继续作为主入口。
- Modify: `site/content/docs/plans/creative-flow-ux-optimization.md`
  - 同步计划方向。
- Modify: `site/content/docs/architecture/shot-page-boundary.md`
  - 实施完成后同步当前页面职责。
- Modify: `site/content/docs/architecture/shot-status-flow.md`
  - 同步 `shot.status` 与生成诊断展示语义。
- Modify: `site/content/docs/architecture/generation-workspace.md`
  - 同步原工作室降级与镜头详情生成入口。

## Task 1: Project-Level Navigation Cleanup

**Files:**
- Modify: `front/src/layouts/MainLayout.tsx`
- Modify: `front/src/pages/aiStudio/project/ProjectWorkbench/constants.tsx`
- Modify: `front/src/pages/aiStudio/project/ProjectWorkbench/chapterPreparation.tsx`
- Modify: `front/src/pages/aiStudio/project/ProjectWorkbench/index.tsx`
- Modify: `front/src/pages/aiStudio/project/ProjectWorkbench/tabs/ChaptersTab.tsx`
- Modify: `front/src/pages/aiStudio/project/ProjectLobby.tsx`

- [ ] **Step 1: Inspect current navigation and stage action callsites**

Run:

```bash
rg -n "分镜列表|分镜工作室|进入工作室|进入分镜工作室|进入拍摄|prepare_shots|getChapterStudioPath|getChapterShotsPath|项目速览|进入章节工作室" front/src/layouts front/src/pages/aiStudio/project
```

Expected: Output includes `MainLayout.tsx`, `ProjectLobby.tsx`, `ProjectWorkbench/index.tsx`, `DashboardTab.tsx`, `ChaptersTab.tsx`, and `chapterPreparation.tsx`.

- [ ] **Step 2: Remove chapter-level nav items from `MainLayout`**

In `front/src/layouts/MainLayout.tsx`, change `activeNav` and `navItems` so only project-level buttons remain:

```tsx
const activeNav = useMemo(() => {
  if (!urlProjectId) return 'home'
  return 'workbench'
}, [urlProjectId])
```

Replace `navItems` construction with:

```tsx
const navItems = useMemo(() => [
  {
    key: 'home',
    label: '主页面',
    path: '/projects',
    visible: true,
    enabled: true,
  },
  {
    key: 'workbench',
    label: '项目工作台',
    path: urlProjectId ? `/projects/${urlProjectId}` : null,
    visible: !!urlProjectId,
    enabled: !!urlProjectId,
  },
], [urlProjectId])
```

Delete now-unused `urlChapterId`, `storedChapterId`, `effectiveChapterId`, and related localStorage effects from `MainLayout`.

- [ ] **Step 3: Change project workbench default tab**

In `front/src/pages/aiStudio/project/ProjectWorkbench/constants.tsx`, set:

```tsx
export const DEFAULT_TAB: TabKey = 'chapters'
```

Change dashboard label in `TAB_CONFIG`:

```tsx
{ key: 'dashboard', label: '总览', icon: <HomeOutlined /> },
```

- [ ] **Step 4: Rewrite chapter preparation copy**

In `front/src/pages/aiStudio/project/ProjectWorkbench/chapterPreparation.tsx`, update `prepare_shots`:

```tsx
return {
  key: 'prepare_shots',
  text: '待确认分镜',
  color: 'blue',
  hint: '已有分镜，建议进入分镜列表处理待确认镜头',
  primaryAction: '处理分镜',
  primaryIcon: <FileSearchOutlined />,
}
```

Update `shoot` copy to avoid “拍摄” ambiguity:

```tsx
text: '可生成视频',
hint: '当前章节已有可继续生成的视频分镜',
primaryAction: '进入分镜',
```

- [ ] **Step 5: Stop workbench CTA from jumping to studio**

In `front/src/pages/aiStudio/project/ProjectWorkbench/index.tsx`, remove `getChapterStudioPath` import and change `prepare_shots` branch:

```tsx
if (state.key === 'prepare_shots') {
  return {
    label: `处理${chapterLabel}分镜`,
    hint: `${chapterLabel}已有分镜，建议进入分镜列表处理待确认镜头`,
    icon: state.primaryIcon,
    onClick: () => navigate(getChapterShotsPath(projectId, recommendedChapter.id)),
  }
}
```

Change final `shoot` branch to navigate to `getChapterShotsPath(projectId, recommendedChapter.id)`.

- [ ] **Step 6: Stop chapter row primary actions from jumping to studio**

In `front/src/pages/aiStudio/project/ProjectWorkbench/tabs/ChaptersTab.tsx`, change `handlePrimaryAction`:

```tsx
if (state.key === 'prepare_shots') {
  navigate(getChapterShotsPath(projectId, record.id))
  return
}
```

For `shoot`, use `ensureHasShotsBeforeShooting` only if it will route to shots when no shots exist; otherwise navigate to `getChapterShotsPath(projectId, record.id)` for existing shots.

Remove “进入工作室” from `buildActionMenuItems`; keep `查看分镜` as the chapter-level route.

- [ ] **Step 7: Simplify project lobby main actions**

In `front/src/pages/aiStudio/project/ProjectLobby.tsx`, change `handlePrimaryAction` to always navigate project-level:

```tsx
const handlePrimaryAction = (project: ProjectView) => {
  navigate(`/projects/${project.id}?tab=chapters`)
}
```

Change `mainActionLabel` to:

```tsx
const mainActionLabel = '打开项目'
```

Remove `getChapterStudioPath` and `getChapterShotsPath` imports if unused.

In project overview side panel, delete the bottom primary button that duplicates card navigation. Keep project name, description, progress, and stats.

- [ ] **Step 8: Run frontend typecheck**

Run:

```bash
cd front && pnpm exec tsc --noEmit
```

Expected: command exits 0. If it fails on unused imports from edited files, remove the imports and rerun.

- [ ] **Step 9: Commit**

Run:

```bash
git add front/src/layouts/MainLayout.tsx front/src/pages/aiStudio/project/ProjectWorkbench/constants.tsx front/src/pages/aiStudio/project/ProjectWorkbench/chapterPreparation.tsx front/src/pages/aiStudio/project/ProjectWorkbench/index.tsx front/src/pages/aiStudio/project/ProjectWorkbench/tabs/ChaptersTab.tsx front/src/pages/aiStudio/project/ProjectLobby.tsx
git commit -m "refactor: simplify project navigation flow"
```

## Task 2: Studio Route Compatibility Redirect

**Files:**
- Create: `front/src/pages/aiStudio/chapter/ChapterStudioRedirect.tsx`
- Modify: `front/src/App.tsx`
- Modify: `front/src/pages/aiStudio/project/ProjectWorkbench/routes.ts`

- [ ] **Step 1: Add helper for shot detail Tab links**

In `front/src/pages/aiStudio/project/ProjectWorkbench/routes.ts`, add:

```ts
export type ShotDetailTabKey = 'basic' | 'confirm' | 'generate' | 'results'

export function getChapterShotDetailPath(
  projectId: string,
  chapterId: string,
  shotId: string,
  tab?: ShotDetailTabKey,
) {
  const base = getChapterShotEditPath(projectId, chapterId, shotId)
  return tab ? `${base}?tab=${tab}` : base
}
```

- [ ] **Step 2: Create redirect component**

Create `front/src/pages/aiStudio/chapter/ChapterStudioRedirect.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { Spin, message } from 'antd'
import { StudioShotsService } from '../../../services/generated'
import { getChapterShotDetailPath, getChapterShotsPath } from '../project/ProjectWorkbench/routes'

/**
 * Compatibility redirect for the removed standalone studio page.
 *
 * The canonical single-shot workflow now lives in the shot detail page. This
 * route keeps old links functional by selecting the first shot in the chapter
 * and opening its video generation tab.
 */
export default function ChapterStudioRedirect() {
  const { projectId, chapterId } = useParams<{ projectId: string; chapterId: string }>()
  const [target, setTarget] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    if (!projectId || !chapterId) {
      setTarget('/projects')
      return () => {
        cancelled = true
      }
    }

    StudioShotsService.listShotsApiV1StudioShotsGet({
      chapterId,
      page: 1,
      pageSize: 1,
      order: 'index',
      isDesc: false,
    })
      .then((res) => {
        if (cancelled) return
        const firstShot = res.data?.items?.[0]
        setTarget(
          firstShot
            ? getChapterShotDetailPath(projectId, chapterId, firstShot.id, 'generate')
            : getChapterShotsPath(projectId, chapterId),
        )
      })
      .catch(() => {
        if (cancelled) return
        message.error('无法打开旧工作室链接，已返回分镜列表')
        setTarget(getChapterShotsPath(projectId, chapterId))
      })

    return () => {
      cancelled = true
    }
  }, [chapterId, projectId])

  if (target) return <Navigate to={target} replace />

  return (
    <div className="flex h-full min-h-[240px] items-center justify-center">
      <Spin />
    </div>
  )
}
```

- [ ] **Step 3: Wire route in `App.tsx`**

Replace `ChapterStudio` import:

```tsx
import ChapterStudioRedirect from './pages/aiStudio/chapter/ChapterStudioRedirect'
```

Replace route element:

```tsx
<Route path="projects/:projectId/chapters/:chapterId/studio" element={<ChapterStudioRedirect />} />
```

Do not delete `ChapterStudio.tsx` in this task.

- [ ] **Step 4: Run frontend typecheck**

Run:

```bash
cd front && pnpm exec tsc --noEmit
```

Expected: command exits 0.

- [ ] **Step 5: Commit**

Run:

```bash
git add front/src/pages/aiStudio/project/ProjectWorkbench/routes.ts front/src/pages/aiStudio/chapter/ChapterStudioRedirect.tsx front/src/App.tsx
git commit -m "refactor: redirect legacy chapter studio route"
```

## Task 3: Shot List Flow Status and Batch Toolbar

**Files:**
- Create: `front/src/pages/aiStudio/shots/shotFlowStatus.ts`
- Create: `front/src/pages/aiStudio/shots/components/ShotBatchToolbar.tsx`
- Modify: `front/src/pages/aiStudio/shots/ChapterShotsPage.tsx`

- [ ] **Step 1: Add shot flow status helper**

Create `front/src/pages/aiStudio/shots/shotFlowStatus.ts`:

```ts
import type { ShotRead } from '../../../services/generated'

export type ShotFlowStep = 'basic' | 'confirm' | 'generate' | 'results'

export type ShotFlowState = {
  step: ShotFlowStep
  label: string
  buttonLabel: string
  tagColor: string
  hint: string
}

export type ShotRuntimeLike = {
  has_active_tasks?: boolean
  active_task_count?: number
}

export function getShotFlowState(shot: ShotRead, runtime?: ShotRuntimeLike): ShotFlowState {
  const hasBasic = Boolean(shot.title?.trim()) && Boolean(shot.script_excerpt?.trim())
  const hasResult = Boolean(shot.generated_video_file_id?.trim())

  if (!hasBasic) {
    return {
      step: 'basic',
      label: '基础待补',
      buttonLabel: '补基础信息',
      tagColor: 'gold',
      hint: '请先补齐标题和剧本摘录',
    }
  }

  if (shot.status !== 'ready') {
    return {
      step: 'confirm',
      label: '待确认',
      buttonLabel: '确认资产与台词',
      tagColor: 'gold',
      hint: '请先完成资产与台词确认',
    }
  }

  if (hasResult) {
    return {
      step: 'results',
      label: '已有结果',
      buttonLabel: '查看结果',
      tagColor: 'green',
      hint: '当前镜头已有生成视频',
    }
  }

  if (runtime?.has_active_tasks) {
    return {
      step: 'generate',
      label: '任务运行中',
      buttonLabel: '查看生成',
      tagColor: 'processing',
      hint: `当前镜头有 ${runtime.active_task_count ?? 1} 个运行中任务`,
    }
  }

  return {
    step: 'generate',
    label: '可生成',
    buttonLabel: '生成视频',
    tagColor: 'blue',
    hint: '可进入生成视频步骤',
  }
}
```

- [ ] **Step 2: Add batch toolbar component**

Create `front/src/pages/aiStudio/shots/components/ShotBatchToolbar.tsx`:

```tsx
import { Button, Dropdown, Space } from 'antd'
import type { MenuProps } from 'antd'
import {
  DownloadOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  ToolOutlined,
} from '@ant-design/icons'

type ShotBatchToolbarProps = {
  selectedCount: number
  generating?: boolean
  downloading?: boolean
  diagnosticLoading?: boolean
  maintenanceMenuItems: MenuProps['items']
  onBatchGenerate: () => void
  onBatchDownload: () => void
  onBatchDiagnose: () => void
}

/**
 * Chapter-level batch toolbar for selected shots.
 *
 * Batch actions belong to the shot list, not the single-shot detail page.
 */
export function ShotBatchToolbar({
  selectedCount,
  generating = false,
  downloading = false,
  diagnosticLoading = false,
  maintenanceMenuItems,
  onBatchGenerate,
  onBatchDownload,
  onBatchDiagnose,
}: ShotBatchToolbarProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <Space size="small" wrap>
        <span className="text-xs text-slate-500">已选 {selectedCount} 条</span>
        <Button size="small" type="primary" icon={<ThunderboltOutlined />} loading={generating} onClick={onBatchGenerate}>
          批量生成
        </Button>
        <Button size="small" icon={<DownloadOutlined />} loading={downloading} onClick={onBatchDownload}>
          批量下载
        </Button>
        <Button size="small" icon={<ToolOutlined />} loading={diagnosticLoading} onClick={onBatchDiagnose}>
          批量诊断
        </Button>
        <Dropdown menu={{ items: maintenanceMenuItems }} trigger={['click']}>
          <Button size="small" icon={<SettingOutlined />}>
            更多维护
          </Button>
        </Dropdown>
      </Space>
    </div>
  )
}
```

- [ ] **Step 3: Update shot list filters and imports**

In `ChapterShotsPage.tsx`, import:

```tsx
import { getChapterShotDetailPath } from '../project/ProjectWorkbench/routes'
import { getShotFlowState, type ShotFlowStep } from './shotFlowStatus'
import { ShotBatchToolbar } from './components/ShotBatchToolbar'
```

Remove `getChapterStudioPath` import and old `statusTag` helper if unused.

Change `type ShotListFilter`:

```ts
type ShotListFilter = 'all' | 'basic' | 'confirm' | 'generate' | 'results'
```

- [ ] **Step 4: Add tab navigation helper**

In `ChapterShotsPage`, add:

```tsx
const openShotDetail = (shot: ShotRead, tab?: ShotFlowStep) => {
  if (!projectId || !chapterId) return
  navigate(getChapterShotDetailPath(projectId, chapterId, shot.id, tab))
}
```

Replace `handleOpenSelectedInStudio` with:

```tsx
const handleOpenSelectedShot = () => {
  const firstId = selectedRowKeys[0]?.toString()
  const shot = shots.find((item) => item.id === firstId)
  if (!shot) return
  const flow = getShotFlowState(shot, shotRuntimeMap[shot.id])
  openShotDetail(shot, flow.step)
}
```

- [ ] **Step 5: Update table columns to user-step actions**

In the columns definition, replace status rendering with flow state rendering:

```tsx
{
  title: '当前步骤',
  key: 'flow',
  width: 160,
  render: (_, record) => {
    const flow = getShotFlowState(record, shotRuntimeMap[record.id])
    return (
      <Tooltip title={flow.hint}>
        <Tag color={flow.tagColor}>{flow.label}</Tag>
      </Tooltip>
    )
  },
},
{
  title: '操作',
  key: 'actions',
  fixed: 'right',
  width: 180,
  render: (_, record) => {
    const flow = getShotFlowState(record, shotRuntimeMap[record.id])
    return (
      <Space size="small">
        <Button size="small" type="primary" onClick={() => openShotDetail(record, flow.step)}>
          {flow.buttonLabel}
        </Button>
        <Dropdown menu={{ items: buildActionMenuItems(record) }} trigger={['click']}>
          <Button size="small" type="text">更多</Button>
        </Dropdown>
      </Space>
    )
  },
}
```

Keep create, insert, reorder, edit/delete low-frequency items in `buildActionMenuItems`.

- [ ] **Step 6: Remove studio button and old segmented labels**

Delete the header button:

```tsx
进入分镜工作室
```

Change segmented options:

```tsx
options={[
  { label: `全部 ${shotFilterCounts.all}`, value: 'all' },
  { label: `基础待补 ${shotFilterCounts.basic}`, value: 'basic' },
  { label: `待确认 ${shotFilterCounts.confirm}`, value: 'confirm' },
  { label: `可生成 ${shotFilterCounts.generate}`, value: 'generate' },
  { label: `已有结果 ${shotFilterCounts.results}`, value: 'results' },
]}
```

Compute counts using `getShotFlowState`.

- [ ] **Step 7: Add visible batch toolbar**

When `selectedRowKeys.length > 0`, render `ShotBatchToolbar` above the table:

```tsx
{selectedRowKeys.length > 0 ? (
  <ShotBatchToolbar
    selectedCount={selectedRowKeys.length}
    maintenanceMenuItems={batchMaintenanceMenuItems}
    onBatchGenerate={() => message.warning('请先完成单镜头生成配置后再批量生成')}
    onBatchDownload={() => message.warning('当前选中镜头暂无可下载视频')}
    onBatchDiagnose={() => message.warning('请先完成诊断接入')}
  />
) : null}
```

Keep existing batch delete wired through `batchMaintenanceMenuItems`:

```tsx
const batchMaintenanceMenuItems: MenuProps['items'] = [
  {
    key: 'delete',
    label: '删除',
    danger: true,
    icon: <DeleteOutlined />,
    onClick: () => void handleBatchDelete(),
  },
]
```

- [ ] **Step 8: Run frontend typecheck**

Run:

```bash
cd front && pnpm exec tsc --noEmit
```

Expected: command exits 0.

- [ ] **Step 9: Commit**

Run:

```bash
git add front/src/pages/aiStudio/shots/ChapterShotsPage.tsx front/src/pages/aiStudio/shots/shotFlowStatus.ts front/src/pages/aiStudio/shots/components/ShotBatchToolbar.tsx
git commit -m "refactor: make shot list a chapter queue"
```

## Task 4: Expand Shot Detail to Four Tabs

**Files:**
- Modify: `front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx`
- Create: `front/src/pages/aiStudio/shots/components/ShotVideoGenerationTab.tsx`
- Create: `front/src/pages/aiStudio/shots/components/ShotVideoResultsTab.tsx`
- Create: `front/src/pages/aiStudio/shots/components/VideoDiagnosticsDrawer.tsx`

- [ ] **Step 1: Add URL tab support**

In `ChapterShotEditPage.tsx`, import:

```tsx
import { useSearchParams } from 'react-router-dom'
```

Add types:

```ts
type ShotDetailTabKey = 'basic' | 'confirm' | 'generate' | 'results'

function isShotDetailTabKey(value: string | null): value is ShotDetailTabKey {
  return value === 'basic' || value === 'confirm' || value === 'generate' || value === 'results'
}
```

Replace editor tab state with:

```tsx
const [searchParams, setSearchParams] = useSearchParams()
const tabFromUrl = searchParams.get('tab')
const [editorTabKey, setEditorTabKey] = useState<ShotDetailTabKey>(
  isShotDetailTabKey(tabFromUrl) ? tabFromUrl : 'basic',
)
```

- [ ] **Step 2: Update tab change handler**

Replace `handleEditorTabChange`:

```tsx
const handleEditorTabChange = useCallback(
  (key: string) => {
    const nextKey: ShotDetailTabKey = isShotDetailTabKey(key) ? key : 'basic'
    setEditorTabKey(nextKey)
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('tab', nextKey)
        return next
      },
      { replace: true },
    )
    if (shotId) {
      editorTabMemoryRef.current[shotId] = nextKey
      tabAutoInitShotIdRef.current = shotId
    }
  },
  [setSearchParams, shotId],
)
```

Update `editorTabMemoryRef` typing to `Record<string, ShotDetailTabKey>`.

- [ ] **Step 3: Add initial generation tab component**

Create `front/src/pages/aiStudio/shots/components/ShotVideoGenerationTab.tsx`:

```tsx
import { Button, Card, Space, Tag, Tooltip } from 'antd'
import { ToolOutlined, VideoCameraOutlined } from '@ant-design/icons'
import type { ShotDetailRead, ShotPreparationStateRead, ShotRead } from '../../../../services/generated'

type ShotVideoGenerationTabProps = {
  shot: ShotRead | null
  shotDetail: ShotDetailRead | null
  preparationState: ShotPreparationStateRead | null
  onOpenDiagnostics: () => void
}

function getDisabledReason(
  shot: ShotRead | null,
  shotDetail: ShotDetailRead | null,
  preparationState: ShotPreparationStateRead | null,
) {
  if (!shot) return '请先选择镜头'
  if (!preparationState?.ready_for_generation) return '请先完成基础信息、动作拍点、资产与台词确认'
  if (!shotDetail?.duration || shotDetail.duration <= 0) return '请先设置镜头时长'
  return null
}

/**
 * Single-shot video submission workspace.
 *
 * This component intentionally keeps diagnostics behind a low-frequency action;
 * the primary path is model/mode selection followed by prompt preview.
 */
export function ShotVideoGenerationTab({
  shot,
  shotDetail,
  preparationState,
  onOpenDiagnostics,
}: ShotVideoGenerationTabProps) {
  const disabledReason = getDisabledReason(shot, shotDetail, preparationState)

  return (
    <div className="space-y-4">
      <Card size="small" title="生成配置">
        <Space direction="vertical" className="w-full" size="middle">
          <div className="flex flex-wrap items-center gap-2">
            <Tag color="blue">模型能力驱动</Tag>
            <span className="text-xs text-slate-500">请先完成前置准备，再进入视频生成提交。</span>
          </div>
          <Tooltip title={disabledReason ?? '进入提示词预览与积分确认'}>
            <span>
              <Button type="primary" icon={<VideoCameraOutlined />} disabled={Boolean(disabledReason)}>
                生成视频
              </Button>
            </span>
          </Tooltip>
          <Button icon={<ToolOutlined />} onClick={onOpenDiagnostics}>
            诊断
          </Button>
        </Space>
      </Card>
    </div>
  )
}
```

- [ ] **Step 4: Add initial results tab component**

Create `front/src/pages/aiStudio/shots/components/ShotVideoResultsTab.tsx`:

```tsx
import { Card, Empty } from 'antd'
import type { ShotRead } from '../../../../services/generated'

type ShotVideoResultsTabProps = {
  shot: ShotRead | null
}

/**
 * Displays successful video versions for a single shot.
 *
 * Displays the current generated video recorded on the shot.
 */
export function ShotVideoResultsTab({ shot }: ShotVideoResultsTabProps) {
  if (!shot?.generated_video_file_id) {
    return (
      <Card size="small" title="视频结果">
        <Empty description="当前镜头还没有已生成视频" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    )
  }

  return (
    <Card size="small" title="当前视频">
      <video src={`/api/v1/studio/files/${shot.generated_video_file_id}/download`} controls className="w-full rounded-lg bg-black" />
    </Card>
  )
}
```

- [ ] **Step 5: Add diagnostics drawer component**

Create `front/src/pages/aiStudio/shots/components/VideoDiagnosticsDrawer.tsx`:

```tsx
import { Drawer, Empty, List, Tag } from 'antd'
import type { ShotVideoReadinessRead } from '../../../../services/generated'

type VideoDiagnosticsDrawerProps = {
  open: boolean
  loading?: boolean
  title?: string
  readiness: ShotVideoReadinessRead | null
  onClose: () => void
}

/**
 * Low-frequency video diagnostics viewer.
 *
 * Check keys stay in English for support/debuggability; user-facing messages
 * remain localized in Chinese.
 */
export function VideoDiagnosticsDrawer({
  open,
  loading = false,
  title = '生成诊断',
  readiness,
  onClose,
}: VideoDiagnosticsDrawerProps) {
  return (
    <Drawer title={title} open={open} onClose={onClose} width={520}>
      {!readiness ? (
        <Empty description={loading ? '诊断加载中…' : '暂无诊断结果'} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List
          dataSource={readiness.checks ?? []}
          renderItem={(item) => (
            <List.Item>
              <div className="flex w-full items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-mono text-xs text-slate-700">{item.key}</div>
                  <div className="mt-1 text-sm text-slate-600">{item.message}</div>
                </div>
                <Tag color={item.ok ? 'green' : 'red'}>{item.ok ? '通过' : '未通过'}</Tag>
              </div>
            </List.Item>
          )}
        />
      )}
    </Drawer>
  )
}
```

- [ ] **Step 6: Wire new tabs in edit page**

In `ChapterShotEditPage.tsx`, import new components and `StudioShotsService` already exists:

```tsx
import { ShotVideoGenerationTab } from './components/ShotVideoGenerationTab'
import { ShotVideoResultsTab } from './components/ShotVideoResultsTab'
import { VideoDiagnosticsDrawer } from './components/VideoDiagnosticsDrawer'
```

Add state:

```tsx
const [diagnosticsOpen, setDiagnosticsOpen] = useState(false)
const [videoReadiness, setVideoReadiness] = useState<ShotVideoReadinessRead | null>(null)
const [videoReadinessLoading, setVideoReadinessLoading] = useState(false)
```

Add `ShotVideoReadinessRead` to generated type imports.

Add loader:

```tsx
const openVideoDiagnostics = useCallback(async () => {
  if (!shotId) return
  setDiagnosticsOpen(true)
  setVideoReadinessLoading(true)
  try {
    const res = await StudioShotsService.getShotVideoReadinessApiApiV1StudioShotsShotIdVideoReadinessGet({
      shotId,
      referenceMode: 'first',
    })
    setVideoReadiness(res.data ?? null)
  } catch {
    message.error('加载生成诊断失败')
    setVideoReadiness(null)
  } finally {
    setVideoReadinessLoading(false)
  }
}, [shotId])
```

Append `generate` and `results` to `editorTabItems`:

```tsx
{
  key: 'generate',
  label: <span>3 生成视频</span>,
  children: (
    <ShotVideoGenerationTab
      shot={shot}
      shotDetail={shotDetail}
      preparationState={preparationState}
      onOpenDiagnostics={() => void openVideoDiagnostics()}
    />
  ),
},
{
  key: 'results',
  label: <span>4 视频结果</span>,
  children: <ShotVideoResultsTab shot={shot} />,
},
```

Render drawer near existing modals:

```tsx
<VideoDiagnosticsDrawer
  open={diagnosticsOpen}
  loading={videoReadinessLoading}
  readiness={videoReadiness}
  onClose={() => setDiagnosticsOpen(false)}
/>
```

- [ ] **Step 7: Remove old studio CTA text from edit page**

Replace `nextStepTitle`, `nextStepDescription`, and any button using `goToStudio` with copy and navigation to the new `generate` tab:

```tsx
const goToGenerateTab = () => handleEditorTabChange('generate')
```

Use labels:

```tsx
const nextStepTitle = statusReady ? '下一步：生成视频' : '下一步：先完成镜头准备'
```

- [ ] **Step 8: Run frontend typecheck**

Run:

```bash
cd front && pnpm exec tsc --noEmit
```

Expected: command exits 0.

- [ ] **Step 9: Commit**

Run:

```bash
git add front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx front/src/pages/aiStudio/shots/components/ShotVideoGenerationTab.tsx front/src/pages/aiStudio/shots/components/ShotVideoResultsTab.tsx front/src/pages/aiStudio/shots/components/VideoDiagnosticsDrawer.tsx
git commit -m "feat: add shot detail video workflow tabs"
```

## Task 5: Migrate Single-Shot Video Generation and Results

**Files:**
- Modify: `front/src/pages/aiStudio/shots/components/ShotVideoGenerationTab.tsx`
- Modify: `front/src/pages/aiStudio/shots/components/ShotVideoResultsTab.tsx`
- Modify: `front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx`
- Reference only: `front/src/pages/aiStudio/chapter/ChapterStudio.tsx`

- [ ] **Step 1: Extract generation code by reading current studio**

Run:

```bash
sed -n '2960,3135p' front/src/pages/aiStudio/chapter/ChapterStudio.tsx
sed -n '4140,4235p' front/src/pages/aiStudio/chapter/ChapterStudio.tsx
sed -n '6100,6145p' front/src/pages/aiStudio/chapter/ChapterStudio.tsx
```

Expected: Output shows `useGenerationDraft`, `videoQuote`, `buildVideoRefSelection`, `openVideoPromptPreview`, `submitVideoGeneration`, and preview modal.

- [ ] **Step 2: Add generation props to `ShotVideoGenerationTab`**

Replace the initial props with:

```tsx
type VideoModelOption = {
  id: string
  name: string
  provider_name?: string | null
}

type ShotVideoGenerationTabProps = {
  shot: ShotRead | null
  shotDetail: ShotDetailRead | null
  preparationState: ShotPreparationStateRead | null
  videoModels: VideoModelOption[]
  selectedVideoModelId: string | null
  videoModelsLoading: boolean
  videoResolution: '720p' | '1080p'
  quoteNode: React.ReactNode
  onModelChange: (modelId: string) => void
  onResolutionChange: (resolution: '720p' | '1080p') => void
  onOpenDiagnostics: () => void
  onOpenPromptPreview: () => void
}
```

Render:

```tsx
<Select
  value={selectedVideoModelId ?? undefined}
  loading={videoModelsLoading}
  placeholder="选择视频模型"
  options={videoModels.map((model) => ({
    value: model.id,
    label: `${model.name}${model.provider_name ? ` · ${model.provider_name}` : ''}`,
  }))}
  onChange={onModelChange}
/>
<Segmented
  value={videoResolution}
  options={[{ value: '720p', label: '720p' }, { value: '1080p', label: '1080p' }]}
  onChange={(value) => onResolutionChange(value as '720p' | '1080p')}}
/>
{quoteNode}
<Button type="primary" icon={<VideoCameraOutlined />} disabled={Boolean(disabledReason)} onClick={onOpenPromptPreview}>
  生成视频
</Button>
```

- [ ] **Step 3: Move minimal generation state into edit page**

In `ChapterShotEditPage.tsx`, add imports:

```tsx
import { FilmService, LlmService } from '../../../services/generated'
import { PointsCostButton } from '../../../components/points/PointsCostButton'
import { useGenerationDraft } from '../hooks/useGenerationDraft'
```

Add state:

```tsx
const [videoModels, setVideoModels] = useState<VideoModelOption[]>([])
const [videoModelsLoading, setVideoModelsLoading] = useState(false)
const [selectedVideoModelId, setSelectedVideoModelId] = useState<string | null>(null)
const [videoResolution, setVideoResolution] = useState<'720p' | '1080p'>('720p')
const [videoPromptPreviewOpen, setVideoPromptPreviewOpen] = useState(false)
const [videoPromptPreviewLoading, setVideoPromptPreviewLoading] = useState(false)
const [videoPromptPreviewDraft, setVideoPromptPreviewDraft] = useState('')
const [videoPromptPreviewSubmitting, setVideoPromptPreviewSubmitting] = useState(false)
```

Load models with existing generated API used by `ChapterStudio`; if exact method name differs, reuse the same method from `ChapterStudio.tsx`.

- [ ] **Step 4: Implement `openVideoPromptPreview` with first-frame mode**

Use first-frame as first migrated mode:

```tsx
const openVideoPromptPreview = async () => {
  if (!shotId) return
  if (!preparationState?.ready_for_generation) {
    message.warning('请先完成基础信息、动作拍点、资产与台词确认')
    return
  }
  setVideoPromptPreviewOpen(true)
  setVideoPromptPreviewLoading(true)
  try {
    const res = await FilmService.previewVideoGenerationPromptApiV1FilmTasksVideoPreviewPromptPost({
      requestBody: {
        shot_id: shotId,
        reference_mode: 'first',
        prompt: null,
        images: [],
        ratio: '16:9',
      },
    })
    setVideoPromptPreviewDraft(res.data?.prompt ?? '')
  } catch {
    message.error('获取视频提示词预览失败')
    setVideoPromptPreviewOpen(false)
  } finally {
    setVideoPromptPreviewLoading(false)
  }
}
```

If the current shot has no first frame and the API rejects the empty `images`, keep the warning message and leave more model modes for the next refinement task.

- [ ] **Step 5: Add prompt preview modal**

Render a modal in `ChapterShotEditPage.tsx`:

```tsx
<Modal
  title="视频生成提示词预览"
  open={videoPromptPreviewOpen}
  onCancel={() => setVideoPromptPreviewOpen(false)}
  width={900}
  footer={
    <Space>
      <Button onClick={() => setVideoPromptPreviewOpen(false)}>取消</Button>
      <PointsCostButton
        type="primary"
        loading={videoPromptPreviewSubmitting}
        quote={videoQuote.quote}
        quoteLoading={videoQuote.loading}
        quoteError={videoQuote.error}
        onClick={() => void submitVideoGeneration()}
      >
        生成
      </PointsCostButton>
    </Space>
  }
>
  {videoPromptPreviewLoading ? <Spin /> : <Input.TextArea rows={12} value={videoPromptPreviewDraft} onChange={(event) => setVideoPromptPreviewDraft(event.target.value)} />}
</Modal>
```

- [ ] **Step 6: Add quote and submit**

Add quote:

```tsx
const videoQuote = usePointsQuote({
  businessType: 'video_generation',
  category: 'video',
  modelId: selectedVideoModelId,
  durationSeconds: shotDetail?.duration ?? null,
  resolution: videoResolution,
  enabled: !!selectedVideoModelId && !!shotDetail?.duration,
})
```

Add submit:

```tsx
const submitVideoGeneration = async () => {
  if (!shotId || !videoQuote.quoteToken) return
  setVideoPromptPreviewSubmitting(true)
  try {
    await FilmService.createVideoGenerationTaskApiV1FilmTasksVideoPost({
      requestBody: {
        shot_id: shotId,
        model_id: selectedVideoModelId,
        reference_mode: 'first',
        prompt: videoPromptPreviewDraft,
        images: [],
        ratio: '16:9',
        resolution: videoResolution,
        quote_token: videoQuote.quoteToken,
      },
    })
    message.success('视频生成任务已提交')
    setVideoPromptPreviewOpen(false)
  } catch (error) {
    const pointsAware = makePointsAwareGetErrorMessage(videoQuote.refresh)
    message.error(pointsAware(error, '发起视频生成失败'))
  } finally {
    setVideoPromptPreviewSubmitting(false)
  }
}
```

- [ ] **Step 7: Wire results tab to generated video file**

Enhance `ShotVideoResultsTab`:

```tsx
import { Button, Card, Empty, Space, Tag } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'

const url = shot?.generated_video_file_id
  ? `/api/v1/studio/files/${shot.generated_video_file_id}/download`
  : null
```

Render video, download link, and `当前使用` tag. Do not implement task progress here.

- [ ] **Step 8: Run frontend typecheck**

Run:

```bash
cd front && pnpm exec tsc --noEmit
```

Expected: command exits 0. If API payload fields mismatch, inspect generated service signatures and adjust to generated type names.

- [ ] **Step 9: Commit**

Run:

```bash
git add front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx front/src/pages/aiStudio/shots/components/ShotVideoGenerationTab.tsx front/src/pages/aiStudio/shots/components/ShotVideoResultsTab.tsx
git commit -m "feat: move single shot video generation into shot detail"
```

## Task 6: Batch Diagnostics and Batch Action Wiring

**Files:**
- Modify: `front/src/pages/aiStudio/shots/ChapterShotsPage.tsx`
- Modify: `front/src/pages/aiStudio/shots/components/ShotBatchToolbar.tsx`
- Modify: `front/src/pages/aiStudio/shots/components/VideoDiagnosticsDrawer.tsx`

- [ ] **Step 1: Add batch diagnostic state**

In `ChapterShotsPage.tsx`, add:

```tsx
const [batchDiagnosticsOpen, setBatchDiagnosticsOpen] = useState(false)
const [batchDiagnosticsLoading, setBatchDiagnosticsLoading] = useState(false)
const [batchDiagnostics, setBatchDiagnostics] = useState<Array<{ shot: ShotRead; readiness: ShotVideoReadinessRead | null; error?: string }>>([])
```

Add `ShotVideoReadinessRead` type import.

- [ ] **Step 2: Implement batch diagnostics**

Add:

```tsx
const runBatchDiagnostics = async () => {
  const selected = shots.filter((shot) => selectedRowKeys.includes(shot.id))
  if (selected.length === 0) {
    message.warning('请先选择分镜')
    return
  }
  setBatchDiagnosticsOpen(true)
  setBatchDiagnosticsLoading(true)
  try {
    const results = await Promise.all(
      selected.map(async (shot) => {
        try {
          const res = await StudioShotsService.getShotVideoReadinessApiApiV1StudioShotsShotIdVideoReadinessGet({
            shotId: shot.id,
            referenceMode: 'first',
          })
          return { shot, readiness: res.data ?? null }
        } catch (error) {
          return { shot, readiness: null, error: '诊断失败' }
        }
      }),
    )
    setBatchDiagnostics(results)
  } finally {
    setBatchDiagnosticsLoading(false)
  }
}
```

- [ ] **Step 3: Extend diagnostics drawer for batch**

Update `VideoDiagnosticsDrawer.tsx` props:

```tsx
type BatchDiagnosticItem = {
  title: string
  readiness: ShotVideoReadinessRead | null
  error?: string
}

batchItems?: BatchDiagnosticItem[]
```

If `batchItems` exists, render a `List` of shot titles, status tags, and nested checks. Default expand failed items by rendering failed checks first.

- [ ] **Step 4: Wire toolbar**

In `ChapterShotsPage.tsx`, change toolbar:

```tsx
<ShotBatchToolbar
  selectedCount={selectedRowKeys.length}
  diagnosticLoading={batchDiagnosticsLoading}
  maintenanceMenuItems={batchMaintenanceMenuItems}
  onBatchGenerate={() => message.warning('请先完成单镜头生成配置后再批量生成')}
  onBatchDownload={() => message.warning('当前选中镜头暂无可下载视频')}
  onBatchDiagnose={() => void runBatchDiagnostics()}
/>
```

Render drawer:

```tsx
<VideoDiagnosticsDrawer
  open={batchDiagnosticsOpen}
  title="批量诊断"
  loading={batchDiagnosticsLoading}
  readiness={null}
  batchItems={batchDiagnostics.map((item) => ({
    title: item.shot.title || `第 ${item.shot.index} 镜`,
    readiness: item.readiness,
    error: item.error,
  }))}
  onClose={() => setBatchDiagnosticsOpen(false)}
/>
```

- [ ] **Step 5: Keep maintenance menu small**

Ensure `batchMaintenanceMenuItems` contains only:

```tsx
[
  { key: 'hide', label: '隐藏' },
  { key: 'delete', label: '删除', danger: true },
  { key: 'skip-extraction', label: '维护：标记无需提取', danger: true },
  { key: 'restore-extraction', label: '维护：恢复提取' },
]
```

Do not add merge.

- [ ] **Step 6: Run frontend typecheck**

Run:

```bash
cd front && pnpm exec tsc --noEmit
```

Expected: command exits 0.

- [ ] **Step 7: Commit**

Run:

```bash
git add front/src/pages/aiStudio/shots/ChapterShotsPage.tsx front/src/pages/aiStudio/shots/components/ShotBatchToolbar.tsx front/src/pages/aiStudio/shots/components/VideoDiagnosticsDrawer.tsx
git commit -m "feat: add shot list batch diagnostics"
```

## Task 7: Documentation and Final Verification

**Files:**
- Modify: `site/content/docs/plans/creative-flow-ux-optimization.md`
- Modify: `site/content/docs/architecture/shot-page-boundary.md`
- Modify: `site/content/docs/architecture/shot-status-flow.md`
- Modify: `site/content/docs/architecture/generation-workspace.md`
- Modify: `用户使用手册.md`
- Modify: `front/src/pages/guide/CreationGuidePage.tsx`

- [ ] **Step 1: Update plan doc**

In `site/content/docs/plans/creative-flow-ux-optimization.md`, replace references saying standalone workbench/studio is the main route with:

```markdown
当前推进方向调整为：项目工作台默认进入章节流水线；分镜列表作为章节镜头队列；镜头详情承载基础信息、提取确认、生成视频与视频结果；原分镜工作室仅保留兼容跳转。
```

- [ ] **Step 2: Update architecture page boundary**

In `site/content/docs/architecture/shot-page-boundary.md`, add:

```markdown
镜头详情页是单镜头主工作区，包含基础信息、提取确认、生成视频、视频结果四个步骤。分镜列表只负责章节级队列、提取入口和批量操作。原分镜工作室不再作为主流程入口。
```

- [ ] **Step 3: Update status flow architecture**

In `site/content/docs/architecture/shot-status-flow.md`, add:

```markdown
`shot.status=ready` 只表示提取确认完成。用户界面应展示“提取确认完成”或“准备完成”，不得把它等同于“可生成视频”。视频生成按钮由诊断结果控制，诊断项保留英文 key 和中文说明。
```

- [ ] **Step 4: Update generation workspace architecture**

In `site/content/docs/architecture/generation-workspace.md`, add:

```markdown
单镜头视频生成入口位于镜头详情的“生成视频”步骤。批量生成、批量下载和批量诊断位于分镜列表顶部工具栏。全局任务中心继续负责运行中、失败和取消状态。
```

- [ ] **Step 5: Update user-facing guide text**

In `用户使用手册.md` and `front/src/pages/guide/CreationGuidePage.tsx`, replace the old route:

```text
项目工作台 -> 分镜列表 -> 分镜工作室
```

with:

```text
项目工作台 -> 分镜列表 -> 镜头详情（基础信息 / 提取确认 / 生成视频 / 视频结果）
```

Remove “顶部导航分镜工作室” descriptions.

- [ ] **Step 6: Run frontend typecheck**

Run:

```bash
cd front && pnpm exec tsc --noEmit
```

Expected: command exits 0.

- [ ] **Step 7: Review route and copy search**

Run:

```bash
rg -n "进入分镜工作室|分镜工作室|批量视频准备度|已就绪分镜|进入章节工作室" front/src site/content/docs 用户使用手册.md
```

Expected: Remaining matches are either compatibility notes, architecture history, or explicitly acceptable references to old route compatibility. Main UI copy must not contain “进入分镜工作室” or “批量视频准备度”.

- [ ] **Step 8: Commit docs**

Run:

```bash
git add site/content/docs/plans/creative-flow-ux-optimization.md site/content/docs/architecture/shot-page-boundary.md site/content/docs/architecture/shot-status-flow.md site/content/docs/architecture/generation-workspace.md 用户使用手册.md front/src/pages/guide/CreationGuidePage.tsx
git commit -m "docs: update shot flow architecture"
```

- [ ] **Step 9: Final verification**

Run:

```bash
cd front && pnpm exec tsc --noEmit
```

Expected: command exits 0.

Run:

```bash
git status --short
```

Expected: no unstaged or uncommitted changes except intentionally ignored local files.

## Self-Review Checklist

- Spec coverage:
  - Project list entry cleanup: Task 1.
  - Project workbench default chapters: Task 1.
  - Global nav removal: Task 1.
  - Studio route compatibility: Task 2.
  - Shot list as queue: Task 3.
  - Four-tab shot detail: Task 4.
  - Single-shot video generation and results: Task 5.
  - Batch diagnostics and toolbar: Task 6.
  - Documentation sync: Task 7.
- Completeness scan:
  - Target end state contains implemented user-facing flows for navigation, shot queue, diagnostics, single-shot generation, and results.
  - No task contains undefined file paths.
- Type consistency:
  - `ShotDetailTabKey` values are `basic | confirm | generate | results`.
  - Generated client usage stays under `front/src/services/generated`.
  - Diagnostics key names remain backend readiness key strings.
