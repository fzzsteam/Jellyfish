# Jellyfish 创作流程体验优化 Implementation Plan

> **给 agentic workers：** REQUIRED SUB-SKILL：执行本计划时必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，并按任务逐项执行。所有步骤都使用 checkbox（`- [ ]`）跟踪。

**Goal:** 优化 Jellyfish AI 短剧平台的核心创作流，让用户从项目进入后能清楚知道下一步做什么，并把“分镜准备”和“视频生成”两个阶段稳定区分开。

**Architecture:** 本阶段优先做“主流程纠偏 + 下一步推荐 + 分镜自动准备”，不新增完整新手 Wizard，不改公开 API。实现方式是集中 next-action 判断、把分镜列表页改成准备队列、让章节分镜提取任务串行完成资产/对白候选提取与保守自动关联、把分镜编辑页强化为检查补缺站、把分镜工作室聚焦为生成工作区；公司成员反馈中的 9 张参考图、资产图片历史、批量上传等能力先做能力审计和二期边界记录，避免通过手写前端绕路破坏 OpenAPI/generated client 约定。

**Tech Stack:** React 18、TypeScript、Ant Design、React Router、Tailwind utility class、现有 OpenAPI generated client（`front/src/services/generated`）、`site/content/docs` 文档体系。

---

## 文件结构

### 新建文件

- `front/src/pages/aiStudio/project/ProjectWorkbench/creativeFlowNextAction.tsx`
  - 统一项目、章节、分镜队列的“下一步动作”判断。
  - 统一 `prepare_shots`、`shoot` 等阶段的文案、图标、路由意图。
  - 保证 `prepare_shots` 主流程进入分镜准备队列或待确认镜头编辑页，而不是直接进入工作室。

- `front/src/pages/aiStudio/project/ProjectWorkbench/components/CreativeFlowStrip.tsx`
  - 展示紧凑主流程条：原文 -> 分镜 -> 准备确认 -> 生成。
  - 给分镜列表页、分镜编辑页、分镜工作室复用。

- `front/src/pages/aiStudio/shots/components/ShotPreparationNextActionPanel.tsx`
  - 展示单镜头准备完成后的出口：继续处理下一条待确认镜头，或进入工作室生成。

- `front/src/pages/aiStudio/chapter/studioShotSelection.ts`
  - 封装工作室默认选中镜头规则：优先运行中、其次 ready、避免默认落到 pending。

### 修改文件

- `backend/app/services/script_processing_worker.py`
  - `script_divide` 写库后串行执行 chapter 级资产/对白提取与自动准备。
  - `script_extract` 作为修复入口刷新候选后，也尝试执行自动准备。

- `backend/app/services/studio/shot_auto_preparation.py`
  - 新增内部同步服务，批量处理章节下所有镜头候选。
  - 同类型、已有可用 `file_id` 图片、精确或高置信唯一匹配的资产自动关联。
  - 无图、低置信或多候选匹配保留 pending。
  - 对白候选默认自动写入 `ShotDialogLine` 并 accepted，重复执行保持幂等。

- `front/src/pages/aiStudio/project/ProjectWorkbench/chapterPreparation.tsx`
  - 修改 `extract_shots` 文案，明确“提取分镜并自动准备”。
  - 修改 `prepare_shots` 文案，从“进入工作室”改为“准备分镜”。

- `front/src/pages/aiStudio/project/ProjectWorkbench/index.tsx`
  - 使用统一 next-action helper 驱动顶部主按钮。

- `front/src/pages/aiStudio/project/ProjectWorkbench/tabs/DashboardTab.tsx`
  - 使用统一 next-action helper 驱动推荐动作和待办卡片。

- `front/src/pages/aiStudio/project/ProjectWorkbench/tabs/ChaptersTab.tsx`
  - 将章节表格里的 `prepare_shots` 主操作改为进入分镜准备队列。

- `front/src/pages/aiStudio/project/ProjectLobby.tsx`
  - 将项目大厅卡片里的 `prepare_shots` 主操作改为进入分镜准备队列。

- `front/src/pages/aiStudio/shots/ChapterShotsPage.tsx`
  - 调整为“分镜准备队列”。
  - 明确区分信息确认状态、运行中任务状态、视频生成准备度。
  - 选中 pending 分镜时进入编辑确认；选中 ready 分镜时进入工作室。

- `front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx`
  - 增加准备状态出口面板。
  - 将“提取并刷新候选”降级为“重新提取/刷新候选”修复入口。
  - 当前镜头 ready 后引导处理下一条 pending 镜头；本章都 ready 后引导进入工作室。

- `front/src/pages/aiStudio/chapter/ChapterStudio.tsx`
  - 默认选择可生成或运行中的镜头。
  - 没有 ready 镜头时显示返回准备页的阻塞提示。
  - 折叠维护、诊断、调试等次级功能。

- `front/src/pages/aiStudio/chapter/components/ChapterStudioBatchToolbar.tsx`
  - 突出“本章 ready 分镜一键生成”的入口。

- `front/src/pages/aiStudio/chapter/components/ChapterStudioMaintenancePanel.tsx`
  - 保持维护能力，但收进次级区域。

### 文档文件

- `site/content/docs/architecture/shot-page-boundary.md`
- `site/content/docs/architecture/shot-status-flow.md`
- `site/content/docs/architecture/generation-workspace.md`
- `site/content/docs/plans/creative-flow-ux-optimization.md`

### 不修改

- 不修改 `site/content/blog/**` 历史 release note。
- 不修改 `front/src/services/generated/**`，除非本阶段明确产生 API 变更并已运行 `pnpm run openapi:update`。
- 不新增手写前端 service wrapper。
- 不新增公开 API；本阶段允许补后端内部 worker/service，让 `script_divide` 写入分镜后自动提取并准备资产/对白。
- 不修改 `front/src/services/generated/**`，除非实现过程中发生公开 API 契约变化并已运行 `pnpm run openapi:update`。

## 任务 1：新增统一 next-action helper 与流程条

**Files:**
- Create: `front/src/pages/aiStudio/project/ProjectWorkbench/creativeFlowNextAction.tsx`
- Create: `front/src/pages/aiStudio/project/ProjectWorkbench/components/CreativeFlowStrip.tsx`

- [ ] **Step 1：创建 `creativeFlowNextAction.tsx`**

写入以下代码。新函数都带注释，满足 AGENTS.md 对函数/代码块注释的要求。

```tsx
import React from 'react'
import {
  CheckCircleOutlined,
  EditOutlined,
  FileSearchOutlined,
  ScissorOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import type { Chapter } from './hooks/useProjectData'
import { getChapterPreparationState } from './chapterPreparation'
import {
  getChapterShotEditPath,
  getChapterShotsPath,
  getChapterStudioPath,
} from './routes'

export type CreativeFlowStageKey =
  | 'create_chapter'
  | 'edit_raw'
  | 'extract_shots'
  | 'prepare_shots'
  | 'shoot'

export type CreativeFlowTarget =
  | { kind: 'project_chapters'; projectId: string }
  | { kind: 'chapter_raw'; projectId: string; chapterId: string }
  | { kind: 'chapter_shots'; projectId: string; chapterId: string }
  | { kind: 'shot_edit'; projectId: string; chapterId: string; shotId: string }
  | {
      kind: 'chapter_studio'
      projectId: string
      chapterId: string
      selectedShotIds?: string[]
      focusShotId?: string
    }

export type CreativeFlowAction = {
  key: CreativeFlowStageKey
  label: string
  hint: string
  primaryAction: string
  icon: React.ReactNode
  target: CreativeFlowTarget
}

export type CreativeFlowShot = {
  id: string
  status?: string | null
  hasActiveTasks?: boolean
}

export type ShotQueueActionInput = {
  projectId: string
  chapterId: string
  shots: CreativeFlowShot[]
  selectedShotIds?: string[]
}

const stageCopy: Record<CreativeFlowStageKey, Omit<CreativeFlowAction, 'target'>> = {
  create_chapter: {
    key: 'create_chapter',
    label: '创建章节',
    hint: '先创建第一章，再进入分镜提取与准备流程。',
    primaryAction: '创建第一章',
    icon: <EditOutlined />,
  },
  edit_raw: {
    key: 'edit_raw',
    label: '补充原文',
    hint: '这一章还没有原文内容，先补齐章节文本。',
    primaryAction: '编辑章节原文',
    icon: <EditOutlined />,
  },
  extract_shots: {
    key: 'extract_shots',
    label: '提取分镜',
    hint: '这一章已有原文，下一步是提取分镜。',
    primaryAction: '提取分镜',
    icon: <ScissorOutlined />,
  },
  prepare_shots: {
    key: 'prepare_shots',
    label: '准备分镜',
    hint: '这一章已有分镜，先确认资产、对白和镜头基础信息。',
    primaryAction: '准备分镜',
    icon: <FileSearchOutlined />,
  },
  shoot: {
    key: 'shoot',
    label: '生成视频',
    hint: '分镜信息已确认，可以进入工作室检查视频准备度并生成。',
    primaryAction: '进入工作室生成',
    icon: <VideoCameraOutlined />,
  },
}

/**
 * 生成章节级下一步动作，让项目大厅、工作台和章节表格复用同一套阶段判断。
 * 这样 `prepare_shots` 不会在主流程里提前跳到生成工作室。
 */
export function getChapterCreativeFlowAction(projectId: string, chapter: Chapter): CreativeFlowAction {
  const state = getChapterPreparationState(chapter)
  if (state.key === 'edit_raw') {
    return {
      ...stageCopy.edit_raw,
      icon: state.primaryIcon,
      target: { kind: 'chapter_raw', projectId, chapterId: chapter.id },
    }
  }
  if (state.key === 'extract_shots') {
    return {
      ...stageCopy.extract_shots,
      icon: state.primaryIcon,
      target: { kind: 'chapter_shots', projectId, chapterId: chapter.id },
    }
  }
  if (state.key === 'prepare_shots') {
    return {
      ...stageCopy.prepare_shots,
      icon: state.primaryIcon,
      target: { kind: 'chapter_shots', projectId, chapterId: chapter.id },
    }
  }
  return {
    ...stageCopy.shoot,
    icon: state.primaryIcon,
    target: { kind: 'chapter_studio', projectId, chapterId: chapter.id },
  }
}

/**
 * 生成分镜队列级下一步动作：pending 分镜进入确认页，ready 分镜进入工作室。
 * runtime task 只作为运行状态，不会写回或复用为 `shot.status`。
 */
export function getShotQueueCreativeFlowAction(input: ShotQueueActionInput): CreativeFlowAction {
  const { projectId, chapterId, shots, selectedShotIds = [] } = input
  const selectedShots = shots.filter((shot) => selectedShotIds.includes(shot.id))
  const pendingSelected = selectedShots.find((shot) => shot.status !== 'ready')
  const readySelected = selectedShots.filter((shot) => shot.status === 'ready')
  const activeShot = shots.find((shot) => shot.hasActiveTasks)
  const nextPending = shots.find((shot) => shot.status !== 'ready')
  const readyShots = shots.filter((shot) => shot.status === 'ready')

  if (pendingSelected) {
    return {
      ...stageCopy.prepare_shots,
      primaryAction: '确认选中分镜',
      target: { kind: 'shot_edit', projectId, chapterId, shotId: pendingSelected.id },
    }
  }
  if (readySelected.length > 0) {
    return {
      ...stageCopy.shoot,
      primaryAction: readySelected.length > 1 ? '生成选中分镜' : '生成当前分镜',
      target: {
        kind: 'chapter_studio',
        projectId,
        chapterId,
        selectedShotIds: readySelected.map((shot) => shot.id),
        focusShotId: readySelected[0]?.id,
      },
    }
  }
  if (nextPending) {
    return {
      ...stageCopy.prepare_shots,
      primaryAction: '处理下一个待确认镜头',
      target: { kind: 'shot_edit', projectId, chapterId, shotId: nextPending.id },
    }
  }
  if (readyShots.length > 0) {
    return {
      ...stageCopy.shoot,
      primaryAction: '进入工作室生成',
      target: {
        kind: 'chapter_studio',
        projectId,
        chapterId,
        selectedShotIds: readyShots.map((shot) => shot.id),
        focusShotId: activeShot?.id ?? readyShots[0]?.id,
      },
    }
  }
  return {
    ...stageCopy.extract_shots,
    primaryAction: '提取分镜',
    target: { kind: 'chapter_shots', projectId, chapterId },
  }
}

/**
 * 把统一动作目标转换成 React Router 可消费的路径和 state。
 * 章节创建、章节原文编辑仍由调用页保留本地 modal/URL 参数逻辑。
 */
export function resolveCreativeFlowNavigation(target: CreativeFlowTarget) {
  if (target.kind === 'chapter_shots') return { pathname: getChapterShotsPath(target.projectId, target.chapterId) }
  if (target.kind === 'shot_edit') return { pathname: getChapterShotEditPath(target.projectId, target.chapterId, target.shotId) }
  if (target.kind === 'chapter_studio') {
    return {
      pathname: getChapterStudioPath(target.projectId, target.chapterId),
      state: {
        focusShotId: target.focusShotId,
        selectedShotIds: target.selectedShotIds ?? [],
      },
    }
  }
  return { pathname: `/projects/${target.projectId}` }
}
```

- [ ] **Step 2：创建 `CreativeFlowStrip.tsx`**

```tsx
import React from 'react'
import {
  CheckCircleOutlined,
  EditOutlined,
  ScissorOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import { Steps } from 'antd'
import type { CreativeFlowStageKey } from '../creativeFlowNextAction'

type CreativeFlowStripProps = {
  current: CreativeFlowStageKey
  compact?: boolean
}

const stageOrder: CreativeFlowStageKey[] = ['edit_raw', 'extract_shots', 'prepare_shots', 'shoot']
const stageTitles: Record<CreativeFlowStageKey, string> = {
  create_chapter: '创建',
  edit_raw: '原文',
  extract_shots: '分镜',
  prepare_shots: '准备确认',
  shoot: '生成',
}

const stageIcons: Record<CreativeFlowStageKey, React.ReactNode> = {
  create_chapter: <EditOutlined />,
  edit_raw: <EditOutlined />,
  extract_shots: <ScissorOutlined />,
  prepare_shots: <CheckCircleOutlined />,
  shoot: <VideoCameraOutlined />,
}

/**
 * 展示稳定创作主流程，让各页面用同一条路径提醒用户当前所处阶段。
 * 它只是轻量流程提示，不创建新的新手 Wizard。
 */
export function CreativeFlowStrip({ current, compact = false }: CreativeFlowStripProps) {
  const currentIndex = Math.max(0, stageOrder.indexOf(current))
  return (
    <Steps
      size={compact ? 'small' : 'default'}
      current={currentIndex}
      items={stageOrder.map((key) => ({
        title: stageTitles[key],
        icon: stageIcons[key],
      }))}
    />
  )
}
```

- [ ] **Step 3：运行类型检查**

```powershell
cd D:\Jellyfish\Jellyfish\front
pnpm exec tsc --noEmit
```

预期结果：

```text
TypeScript 无报错，新增 helper 与流程条组件 import 正常。
```

- [ ] **Step 4：提交**

```powershell
cd D:\Jellyfish\Jellyfish
git add front/src/pages/aiStudio/project/ProjectWorkbench/creativeFlowNextAction.tsx front/src/pages/aiStudio/project/ProjectWorkbench/components/CreativeFlowStrip.tsx
git commit -m "feat: add creative flow next action helpers"
```

## 任务 2：把项目与章节入口改回“准备优先”

**Files:**
- Modify: `front/src/pages/aiStudio/project/ProjectWorkbench/chapterPreparation.tsx`
- Modify: `front/src/pages/aiStudio/project/ProjectWorkbench/index.tsx`
- Modify: `front/src/pages/aiStudio/project/ProjectWorkbench/tabs/DashboardTab.tsx`
- Modify: `front/src/pages/aiStudio/project/ProjectWorkbench/tabs/ChaptersTab.tsx`
- Modify: `front/src/pages/aiStudio/project/ProjectLobby.tsx`

- [ ] **Step 1：修改 `chapterPreparation.tsx` 中 `prepare_shots` 文案**

将 `prepare_shots` 配置改成：

```tsx
{
  key: 'prepare_shots',
  text: '待准备分镜',
  color: 'gold',
  hint: '已有分镜，建议先确认资产、对白与镜头基础信息',
  primaryAction: '准备分镜',
  primaryIcon: <FileSearchOutlined />,
}
```

- [ ] **Step 2：修改工作台顶部主按钮逻辑**

在 `ProjectWorkbench/index.tsx` 增加 import：

```tsx
import {
  getChapterCreativeFlowAction,
  resolveCreativeFlowNavigation,
} from './creativeFlowNextAction'
```

把当前 `primaryCta` 中按 `state.key` 分支的章节动作收敛为：

```tsx
const action = getChapterCreativeFlowAction(projectId, recommendedChapter)
const chapterLabel = `第 ${recommendedChapter.index} 章`
if (action.target.kind === 'chapter_raw') {
  return {
    label: `编辑${chapterLabel}原文`,
    hint: `${chapterLabel}还没有原文内容，建议先补章节原文`,
    icon: action.icon,
    onClick: () => {
      setTabInUrl('chapters')
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.set(TAB_PARAM, 'chapters')
          next.set(EDIT_PARAM, recommendedChapter.id)
          return next
        },
        { replace: true },
      )
    },
  }
}
const navigation = resolveCreativeFlowNavigation(action.target)
return {
  label: `${action.primaryAction} · ${chapterLabel}`,
  hint: `${chapterLabel} · ${action.hint}`,
  icon: action.icon,
  onClick: () => navigate(navigation.pathname, navigation.state ? { state: navigation.state } : undefined),
}
```

- [ ] **Step 3：修改 Dashboard 推荐动作**

在 `DashboardTab.tsx` 增加 import：

```tsx
import {
  getChapterCreativeFlowAction,
  resolveCreativeFlowNavigation,
} from '../creativeFlowNextAction'
```

将 `handleRecommendedAction` 中推荐章节后的分支改为：

```tsx
const action = getChapterCreativeFlowAction(projectId, recommendedChapter)
if (action.target.kind === 'chapter_raw') {
  onSelectTab('chapters')
  navigate(`/projects/${projectId}?tab=chapters&edit=${recommendedChapter.id}`, { replace: false })
  return
}
const navigation = resolveCreativeFlowNavigation(action.target)
navigate(navigation.pathname, navigation.state ? { state: navigation.state } : undefined)
```

同时把 Dashboard 待办卡片中的 `prepare_shots` 文案改为：

```tsx
{
  key: 'prepare_shots',
  title: '待准备分镜',
  count: chaptersNeedingShotPrep,
  hint: '已有分镜，先确认资产、对白与镜头基础信息',
  icon: <ClockCircleOutlined />,
}
```

- [ ] **Step 4：修改 ChaptersTab 主操作**

在 `ChaptersTab.tsx` 的 `handlePrimaryAction` 中，把 `prepare_shots` 分支改为：

```tsx
if (state.key === 'prepare_shots') {
  navigate(getChapterShotsPath(projectId, record.id))
  return
}
```

操作菜单中可以保留显式工作室入口，但必须表达为生成入口：

```tsx
{
  key: 'studio',
  label: '进入工作室生成',
  icon: <FileSearchOutlined />,
  onClick: () => navigate(getChapterStudioPath(projectId, record.id)),
}
```

- [ ] **Step 5：修改 ProjectLobby 项目卡片入口**

在 `ProjectLobby.tsx` 中找到 `prepare_shots` 或等价 stage 的导航分支，将：

```tsx
navigate(getChapterStudioPath(project.id, stageSummary.chapterId))
```

改为：

```tsx
navigate(getChapterShotsPath(project.id, stageSummary.chapterId))
```

`shoot` 阶段继续进入：

```tsx
navigate(getChapterStudioPath(project.id, stageSummary.chapterId))
```

- [ ] **Step 6：验证 `prepare_shots` 不再主流程直达工作室**

```powershell
cd D:\Jellyfish\Jellyfish
rg -n "prepare_shots|进入工作室生成|getChapterStudioPath|getChapterShotsPath" front/src/pages/aiStudio/project
```

预期结果：

```text
prepare_shots 主操作进入 getChapterShotsPath。
shoot 或显式“进入工作室生成”入口仍可进入 getChapterStudioPath。
```

- [ ] **Step 7：运行类型检查**

```powershell
cd D:\Jellyfish\Jellyfish\front
pnpm exec tsc --noEmit
```

预期结果：

```text
TypeScript 通过。
```

- [ ] **Step 8：提交**

```powershell
cd D:\Jellyfish\Jellyfish
git add front/src/pages/aiStudio/project/ProjectWorkbench/chapterPreparation.tsx front/src/pages/aiStudio/project/ProjectWorkbench/index.tsx front/src/pages/aiStudio/project/ProjectWorkbench/tabs/DashboardTab.tsx front/src/pages/aiStudio/project/ProjectWorkbench/tabs/ChaptersTab.tsx front/src/pages/aiStudio/project/ProjectLobby.tsx
git commit -m "feat: route shot preparation entries to preparation queue"
```

## 任务 3：把分镜列表页改成准备队列

**Files:**
- Modify: `front/src/pages/aiStudio/shots/ChapterShotsPage.tsx`

- [ ] **Step 1：导入统一 helper**

```tsx
import { CreativeFlowStrip } from '../project/ProjectWorkbench/components/CreativeFlowStrip'
import {
  getShotQueueCreativeFlowAction,
  resolveCreativeFlowNavigation,
  type CreativeFlowShot,
} from '../project/ProjectWorkbench/creativeFlowNextAction'
```

- [ ] **Step 2：构造队列动作输入**

在 `selectedShotIds` 附近增加：

```tsx
const creativeFlowShots = useMemo<CreativeFlowShot[]>(
  () =>
    shots.map((shot) => ({
      id: shot.id,
      status: shot.status,
      hasActiveTasks: Boolean(runtimeSummaryMap[shot.id]?.has_active_tasks),
    })),
  [runtimeSummaryMap, shots],
)

const queueAction = useMemo(
  () =>
    projectId && chapterId
      ? getShotQueueCreativeFlowAction({
          projectId,
          chapterId,
          shots: creativeFlowShots,
          selectedShotIds,
        })
      : null,
  [chapterId, creativeFlowShots, projectId, selectedShotIds],
)
```

如果文件中的 runtime summary map 变量名不同，保留原变量名，只要语义仍是 `shotId -> runtime summary`。

- [ ] **Step 3：增加队列主动作处理函数**

```tsx
/**
 * 执行分镜队列主动作：pending 分镜进入准备确认页，ready 分镜进入生成工作室。
 */
const handleQueuePrimaryAction = useCallback(() => {
  if (!queueAction) return
  const navigation = resolveCreativeFlowNavigation(queueAction.target)
  navigate(navigation.pathname, navigation.state ? { state: navigation.state } : undefined)
}, [navigate, queueAction])
```

- [ ] **Step 4：替换选中分镜的默认工作室跳转**

将原来“选中分镜后直接进入工作室”的处理改为：

```tsx
const handleSelectedPrimaryAction = useCallback(() => {
  handleQueuePrimaryAction()
}, [handleQueuePrimaryAction])
```

选中 pending 分镜时应该进入 `ChapterShotEditPage`；选中 ready 分镜时才进入 `ChapterStudio`。

- [ ] **Step 5：在页首增加准备队列引导区**

在表格卡片前增加：

```tsx
<Card size="small">
  <div className="flex flex-col gap-3">
    <CreativeFlowStrip current="prepare_shots" compact />
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="min-w-0">
        <div className="font-medium">分镜准备队列</div>
        <div className="text-xs text-gray-500">
          先确认待处理镜头，确认完成后再进入工作室生成视频。
        </div>
      </div>
      <Button
        type="primary"
        size="large"
        icon={queueAction?.icon}
        disabled={!queueAction}
        onClick={handleQueuePrimaryAction}
      >
        {queueAction?.primaryAction ?? '准备分镜'}
      </Button>
    </div>
  </div>
</Card>
```

- [ ] **Step 6：调整筛选与状态文案**

筛选文案改为：

```tsx
const statusFilterOptions = [
  { key: 'all', label: '全部' },
  { key: 'pending', label: '待确认' },
  { key: 'ready', label: '已确认' },
  { key: 'generating', label: '生成中任务' },
]
```

规则：

```text
pending / ready 来自 shot.status。
generating 来自 runtime summary，不来自 shot.status。
video-readiness 仍只在生成工作室里作为生成前门禁展示。
```

- [ ] **Step 7：调整顶部按钮**

把原本泛化的“进入分镜工作室”“继续当前镜头”替换为：

```tsx
<Button onClick={handleQueuePrimaryAction} type="primary" size="large">
  {queueAction?.primaryAction ?? '准备分镜'}
</Button>
<Button onClick={() => navigate(getChapterStudioPath(projectId, chapterId))}>
  查看生成工作室
</Button>
```

第一个按钮必须走队列主动作，第二个按钮只是显式查看工作室。

- [ ] **Step 8：运行类型检查**

```powershell
cd D:\Jellyfish\Jellyfish\front
pnpm exec tsc --noEmit
```

预期结果：

```text
TypeScript 通过。
```

- [ ] **Step 9：提交**

```powershell
cd D:\Jellyfish\Jellyfish
git add front/src/pages/aiStudio/shots/ChapterShotsPage.tsx
git commit -m "feat: make chapter shots page a preparation queue"
```

## 任务 4：强化分镜编辑页的准备闭环

**Files:**
- Create: `front/src/pages/aiStudio/shots/components/ShotPreparationNextActionPanel.tsx`
- Modify: `front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx`

- [ ] **Step 1：创建 `ShotPreparationNextActionPanel.tsx`**

```tsx
import { Button, Card, Space, Tag } from 'antd'
import { CheckCircleOutlined, FileSearchOutlined, VideoCameraOutlined } from '@ant-design/icons'
import type { ReactNode } from 'react'

type ShotPreparationNextActionPanelProps = {
  currentReady: boolean
  pendingCount: number
  nextPendingLabel?: string
  onOpenNextPending: () => void
  onOpenStudio: () => void
  extra?: ReactNode
}

/**
 * 展示分镜准备页的出口，让用户知道应该继续确认下一条分镜还是进入工作室生成。
 */
export function ShotPreparationNextActionPanel({
  currentReady,
  pendingCount,
  nextPendingLabel,
  onOpenNextPending,
  onOpenStudio,
  extra,
}: ShotPreparationNextActionPanelProps) {
  const canContinuePreparation = pendingCount > 0
  return (
    <Card size="small" className="border-emerald-100 bg-emerald-50">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <Space size={6} wrap>
            <Tag color={currentReady ? 'green' : 'gold'} icon={currentReady ? <CheckCircleOutlined /> : <FileSearchOutlined />}>
              {currentReady ? '当前镜头已确认' : '当前镜头待确认'}
            </Tag>
            <span className="text-xs text-gray-600">
              {canContinuePreparation
                ? `本章还有 ${pendingCount} 条分镜待确认`
                : '本章分镜确认已完成，可以进入工作室生成'}
            </span>
          </Space>
          {nextPendingLabel ? <div className="mt-1 text-xs text-gray-500">下一条：{nextPendingLabel}</div> : null}
        </div>
        <Space wrap>
          {extra}
          {canContinuePreparation ? (
            <Button type="primary" size="large" icon={<FileSearchOutlined />} onClick={onOpenNextPending}>
              处理下一个待确认镜头
            </Button>
          ) : (
            <Button type="primary" size="large" icon={<VideoCameraOutlined />} onClick={onOpenStudio}>
              进入工作室生成
            </Button>
          )}
        </Space>
      </div>
    </Card>
  )
}
```

- [ ] **Step 2：在 `ChapterShotEditPage.tsx` 导入组件**

```tsx
import { CreativeFlowStrip } from '../project/ProjectWorkbench/components/CreativeFlowStrip'
import { ShotPreparationNextActionPanel } from './components/ShotPreparationNextActionPanel'
```

- [ ] **Step 3：计算下一条待确认镜头**

在已有 `shotsSorted` 附近增加：

```tsx
const pendingShots = useMemo(
  () => shotsSorted.filter((item) => item.status !== 'ready'),
  [shotsSorted],
)
const nextPendingShot = useMemo(
  () => pendingShots.find((item) => item.id !== shotId) ?? null,
  [pendingShots, shotId],
)
const currentShotReady = currentShot?.status === 'ready'
```

如果当前文件里的当前镜头变量不是 `currentShot`，使用文件已有变量名替换。

- [ ] **Step 4：插入流程条与出口面板**

在页面头部或准备摘要卡附近加入：

```tsx
<CreativeFlowStrip current="prepare_shots" compact />
<ShotPreparationNextActionPanel
  currentReady={currentShotReady}
  pendingCount={pendingShots.length}
  nextPendingLabel={nextPendingShot ? `#${nextPendingShot.index} ${nextPendingShot.title ?? ''}` : undefined}
  onOpenNextPending={() => {
    if (!nextPendingShot || !projectId || !chapterId) return
    navigate(getChapterShotEditPath(projectId, chapterId, nextPendingShot.id))
  }}
  onOpenStudio={goToStudio}
/>
```

保留现有：

```text
提取刷新
跳过提取 / 恢复提取
资产候选关联 / 忽略
对白候选接受 / 忽略
镜头基础信息编辑
```

- [ ] **Step 5：根据当前阻塞项优先展示相关 tab**

添加 helper：

```tsx
/**
 * 根据准备缺口选择默认 tab，让用户先看到最需要处理的准备项。
 */
function getPreferredPreparationTab(input: {
  assetsPending: number
  dialoguePending: number
  basicInfoReady: boolean
}) {
  if (!input.basicInfoReady) return 'basic'
  if (input.assetsPending > 0) return 'assets'
  if (input.dialoguePending > 0) return 'dialogue'
  return 'summary'
}
```

若文件中 tab key 不同，使用本地映射连接到现有 key：

```tsx
const preparationTabKeyMap = {
  basic: 'basic',
  assets: 'assets',
  dialogue: 'dialogue',
  summary: 'summary',
} as const
```

- [ ] **Step 6：运行类型检查**

```powershell
cd D:\Jellyfish\Jellyfish\front
pnpm exec tsc --noEmit
```

预期结果：

```text
TypeScript 通过。
```

- [ ] **Step 7：提交**

```powershell
cd D:\Jellyfish\Jellyfish
git add front/src/pages/aiStudio/shots/components/ShotPreparationNextActionPanel.tsx front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx
git commit -m "feat: guide shot preparation next actions"
```

## 任务 5：让分镜工作室聚焦生成

**Files:**
- Create: `front/src/pages/aiStudio/chapter/studioShotSelection.ts`
- Modify: `front/src/pages/aiStudio/chapter/ChapterStudio.tsx`
- Modify: `front/src/pages/aiStudio/chapter/components/ChapterStudioMaintenancePanel.tsx`

- [ ] **Step 1：创建工作室默认选择 helper**

```ts
export type StudioSelectableShot = {
  id: string
  status?: string | null
}

export type StudioRuntimeSummary = {
  has_active_tasks?: boolean | null
}

/**
 * 按生成优先级选择工作室首个镜头：运行中优先，其次 ready。
 * 当没有可生成镜头时返回 null，让页面显示返回准备页的阻塞提示。
 */
export function chooseGenerationFirstShotId(
  shots: StudioSelectableShot[],
  runtimeMap: Record<string, StudioRuntimeSummary | undefined>,
  requestedShotId?: string | null,
) {
  if (requestedShotId && shots.some((shot) => shot.id === requestedShotId && shot.status === 'ready')) {
    return requestedShotId
  }

  const activeShot = shots.find((shot) => runtimeMap[shot.id]?.has_active_tasks)
  if (activeShot) return activeShot.id

  const readyShot = shots.find((shot) => shot.status === 'ready')
  if (readyShot) return readyShot.id

  return null
}
```

- [ ] **Step 2：在 `ChapterStudio.tsx` 使用 helper**

增加 import：

```tsx
import { chooseGenerationFirstShotId } from './studioShotSelection'
import { CreativeFlowStrip } from '../project/ProjectWorkbench/components/CreativeFlowStrip'
```

将当前默认选择 `status !== 'ready'` 的逻辑替换为：

```tsx
const nextSelectedShotId = chooseGenerationFirstShotId(enriched, shotRuntimeMap, locationState?.focusShotId ?? null)
setSelectedShotId(nextSelectedShotId)
setSelectedShotIds(nextSelectedShotId ? [nextSelectedShotId] : [])
```

用户手动点选镜头后的行为保持不变。

- [ ] **Step 3：增加没有 ready 镜头时的阻塞状态**

```tsx
const readyShotCount = shots.filter((shot) => shot.status === 'ready').length
const hasActiveGeneration = shots.some((shot) => shotRuntimeMap[shot.id]?.has_active_tasks)
const studioBlockedByPreparation = readyShotCount === 0 && !hasActiveGeneration
```

渲染：

```tsx
{studioBlockedByPreparation ? (
  <Card size="small" className="border-amber-200 bg-amber-50">
    <div className="space-y-3">
      <CreativeFlowStrip current="prepare_shots" compact />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-medium text-amber-900">本章还没有可生成的分镜</div>
          <div className="text-xs text-amber-800">
            请先在分镜准备页确认资产、对白和镜头基础信息。工作室只负责生成准备与视频生成。
          </div>
        </div>
        <Button
          type="primary"
          size="large"
          onClick={() => projectId && chapterId && navigate(getChapterShotsPath(projectId, chapterId))}
        >
          返回分镜准备
        </Button>
      </div>
    </div>
  </Card>
) : null}
```

- [ ] **Step 4：pending 镜头只保留诊断和返回准备页入口**

当 `selectedShot?.status !== 'ready'` 时渲染：

```tsx
{selectedShot && selectedShot.status !== 'ready' ? (
  <Alert
    type="warning"
    showIcon
    message="当前分镜还未完成信息确认"
    description="请先回到分镜准备页处理资产、对白与镜头基础信息，再继续生成。"
    action={
      <Button size="small" onClick={() => navigate(getChapterShotEditPath(projectId, chapterId, selectedShot.id))}>
        去确认分镜
      </Button>
    }
  />
) : null}
```

保留 `ChapterStudioReadinessDiagnosisPanel`，但它应作为诊断/快捷入口，不是主确认入口。

- [ ] **Step 5：折叠维护类操作**

将 `ChapterStudioMaintenancePanel` 放入次级区域：

```tsx
<Collapse
  ghost
  size="small"
  items={[
    {
      key: 'maintenance',
      label: '维护与高级操作',
      children: (
        <ChapterStudioMaintenancePanel
          selectedShot={selectedShot}
          selectedCount={selectedShotIds.length}
          onSkipExtraction={handleSkipExtraction}
          onResumeExtraction={handleResumeExtraction}
          onDeleteShot={handleDeleteShot}
        />
      ),
    },
  ]}
/>
```

以实际 `ChapterStudioMaintenancePanel.tsx` props 为准调整名字，但不要把维护信息移入任务中心。

- [ ] **Step 6：运行类型检查**

```powershell
cd D:\Jellyfish\Jellyfish\front
pnpm exec tsc --noEmit
```

预期结果：

```text
TypeScript 通过。
```

- [ ] **Step 7：提交**

```powershell
cd D:\Jellyfish\Jellyfish
git add front/src/pages/aiStudio/chapter/studioShotSelection.ts front/src/pages/aiStudio/chapter/ChapterStudio.tsx front/src/pages/aiStudio/chapter/components/ChapterStudioMaintenancePanel.tsx
git commit -m "feat: focus chapter studio on generation"
```

## 任务 6：突出 ready 分镜一键批量生成

**Files:**
- Modify: `front/src/pages/aiStudio/chapter/ChapterStudio.tsx`
- Modify: `front/src/pages/aiStudio/chapter/components/ChapterStudioBatchToolbar.tsx`

- [ ] **Step 1：扩展批量工具栏 props**

在 `ChapterStudioBatchToolbar.tsx` 中改为：

```tsx
type ChapterStudioBatchToolbarProps = {
  selectedCount: number
  readyCount: number
  blockedCount: number
  checkingReadiness: boolean
  generating: boolean
  onSelectReadyShots: () => void
  onCheckReadiness: () => void
  onGenerateReadyShots: () => void
}
```

- [ ] **Step 2：把 ready 批量生成设为主动作**

工具栏渲染顺序：

```tsx
<Space wrap>
  <Button onClick={onSelectReadyShots}>
    选中本章可生成分镜（{readyCount}）
  </Button>
  <Button loading={checkingReadiness} onClick={onCheckReadiness}>
    检查视频准备度
  </Button>
  <Button
    type="primary"
    size="large"
    disabled={readyCount === 0}
    loading={generating}
    onClick={onGenerateReadyShots}
  >
    一键生成可生成分镜
  </Button>
  {blockedCount > 0 ? <Tag color="gold">跳过 {blockedCount} 条待补齐</Tag> : null}
</Space>
```

- [ ] **Step 3：在 ChapterStudio 计算 ready/blocked**

```tsx
const readyShots = useMemo(
  () => shots.filter((shot) => shot.status === 'ready'),
  [shots],
)
const blockedShotCount = Math.max(0, shots.length - readyShots.length)
const handleSelectReadyShots = useCallback(() => {
  const ids = readyShots.map((shot) => shot.id)
  setSelectedShotIds(ids)
  setSelectedShotId(ids[0] ?? null)
}, [readyShots])
```

- [ ] **Step 4：增加 ready 分镜批量生成处理函数**

```tsx
/**
 * 执行本章 ready 分镜的一键生成路径。
 * video-readiness 仍是最终门禁，被阻塞的分镜只提示缺口，不强行生成。
 */
const handleGenerateReadyShots = useCallback(async () => {
  if (readyShots.length === 0) {
    message.warning('本章还没有已确认的分镜')
    return
  }
  setSelectedShotIds(readyShots.map((shot) => shot.id))
  setSelectedShotId(readyShots[0]?.id ?? null)
  const readinessResults = await fetchBatchVideoReadiness(readyShots)
  const videoReadyShots = readinessResults.filter((item) => item.readiness?.ready)
  if (videoReadyShots.length === 0) {
    setBatchVideoReadinessItems(readinessResults)
    setBatchVideoReadinessOpen(true)
    message.warning('已确认分镜还缺少视频生成条件，请先补齐准备度')
    return
  }
  await runBatchVideoGeneration(videoReadyShots.map((item) => item.shot))
}, [fetchBatchVideoReadiness, readyShots, runBatchVideoGeneration])
```

如果当前 `fetchBatchVideoReadiness` 和 `runBatchVideoGeneration` 只读取 `selectedShots`，调整为可选参数：

```tsx
const fetchBatchVideoReadiness = useCallback(
  async (targetShots = selectedShots) => {
    // 原有函数体里使用 targetShots
  },
  [selectedShots],
)
```

- [ ] **Step 5：接入工具栏 props**

```tsx
<ChapterStudioBatchToolbar
  selectedCount={selectedShotIds.length}
  readyCount={readyShots.length}
  blockedCount={blockedShotCount}
  checkingReadiness={batchVideoReadinessLoading}
  generating={batchVideoGenerating}
  onSelectReadyShots={handleSelectReadyShots}
  onCheckReadiness={handleOpenBatchVideoReadiness}
  onGenerateReadyShots={handleGenerateReadyShots}
/>
```

如果当前 loading 变量名不同，保持语义一致即可。

- [ ] **Step 6：运行类型检查**

```powershell
cd D:\Jellyfish\Jellyfish\front
pnpm exec tsc --noEmit
```

预期结果：

```text
TypeScript 通过。
```

- [ ] **Step 7：提交**

```powershell
cd D:\Jellyfish\Jellyfish
git add front/src/pages/aiStudio/chapter/ChapterStudio.tsx front/src/pages/aiStudio/chapter/components/ChapterStudioBatchToolbar.tsx
git commit -m "feat: promote ready shot batch generation"
```

## 任务 7：记录多参考图与资产反馈的能力审计

**Files:**
- Modify: `site/content/docs/plans/creative-flow-ux-optimization.md`

- [ ] **Step 1：确认当前视频参考图合同**

```powershell
cd D:\Jellyfish\Jellyfish
rg -n "reference_mode|images\\?|VideoGenerationTaskRequest" front/src/services/generated/models front/src/pages/aiStudio/chapter backend/app
```

预期证据：

```text
VideoGenerationTaskRequest.ts 已有 images?: Array<string>。
reference_mode 仍是 first / last / key / first_last / first_last_key / text_only 等固定组合。
```

- [ ] **Step 2：确认资产图片历史现状**

```powershell
cd D:\Jellyfish\Jellyfish
rg -n "generated image|history|image history|generated_image|AssetEditPageBase|images" front/src/pages/aiStudio/assets backend/app
```

预期证据：

```text
能判断“第二张图覆盖第一张”的反馈是 UI 展示问题，还是后端持久化/API 合同缺口。
```

- [ ] **Step 3：在站点计划中写入能力审计结论**

在 `site/content/docs/plans/creative-flow-ux-optimization.md` 增加：

```markdown
## 能力审计结论

- 多参考图视频生成：当前 generated request 已有 `images?: Array<string>`，但 `reference_mode` 仍是固定的首帧、尾帧、关键帧组合。`happyhorse-1.0-r2v` 最多 9 张参考图的体验需要先明确 provider capability、video-readiness 规则和 OpenAPI 枚举/请求合同，第一阶段不通过前端手写绕路实现。
- 资产图片历史：本次先判断已有生成历史是展示问题还是持久化合同问题。若已有历史数据，下一阶段优先改 UI 选择与回滚；若缺少持久化，则按后端 API、OpenAPI、generated client、前端页面的顺序推进。
- 批量本地上传：属于资产管理增强，不并入主流程纠偏第一阶段。后续实现必须使用文件/资产现有接口或按 API 变更流程同步。
```

- [ ] **Step 4：提交**

```powershell
cd D:\Jellyfish\Jellyfish
git add site/content/docs/plans/creative-flow-ux-optimization.md
git commit -m "docs: record creative flow capability audit"
```

## 任务 8：同步已落地行为到 architecture 文档

**Files:**
- Modify: `site/content/docs/architecture/shot-page-boundary.md`
- Modify: `site/content/docs/architecture/shot-status-flow.md`
- Modify: `site/content/docs/architecture/generation-workspace.md`
- Modify: `site/content/docs/plans/creative-flow-ux-optimization.md`

- [ ] **Step 1：更新页面职责边界文档**

在 `shot-page-boundary.md` 增加：

```markdown
## 当前入口路由规则

- 项目大厅、项目工作台和章节列表中的 `prepare_shots` 主行动进入分镜准备队列。
- 分镜准备队列负责把待确认镜头送到 `ChapterShotEditPage`。
- 只有 `shoot` 阶段、已确认分镜或显式的“查看生成工作室”入口进入 `ChapterStudio`。
- `ChapterStudio` 可以显示诊断入口，但不再作为提取确认主入口。
```

- [ ] **Step 2：更新状态语义文档**

在 `shot-status-flow.md` 增加：

```markdown
## 前端展示约束

- `pending / ready` 只用于信息确认状态。
- 生成中来自 runtime summary 或任务系统。
- 分镜列表和工作室必须分开展示信息确认状态、运行时任务状态和 video-readiness。
- 工作室默认选择 ready 或有运行中任务的镜头；没有可生成镜头时，引导回分镜准备。
```

- [ ] **Step 3：更新生成工作室架构文档**

在 `generation-workspace.md` 增加：

```markdown
## 工作室首屏与批量生成

- 工作室首屏优先呈现视频准备度、生成主行动和结果回看。
- 维护、诊断和调试类功能默认收起到次级区域。
- 本章 ready 分镜可以通过“一键生成可生成分镜”入口批量推进。
- 批量生成前仍以 video-readiness 为最终门禁；被阻塞的分镜只提示缺口，不修改 `shot.status`。
```

- [ ] **Step 4：更新 active plan 状态**

在 `site/content/docs/plans/creative-flow-ux-optimization.md` 增加：

```markdown
## 第一阶段落地状态

- next-action helper 已统一项目、章节、分镜准备与工作室入口。
- `prepare_shots` 主流程已进入分镜准备队列。
- 分镜列表已作为准备队列展示待确认、已确认与运行中任务。
- 分镜编辑页已提供下一条待确认镜头或进入工作室的出口。
- 工作室已优先选择 ready 或运行中的镜头，并突出 ready 分镜批量生成入口。
```

- [ ] **Step 5：提交**

```powershell
cd D:\Jellyfish\Jellyfish
git add site/content/docs/architecture/shot-page-boundary.md site/content/docs/architecture/shot-status-flow.md site/content/docs/architecture/generation-workspace.md site/content/docs/plans/creative-flow-ux-optimization.md
git commit -m "docs: update creative flow architecture"
```

## 任务 9：最终验证与手动页面检查

**Files:**
- 本任务不预期改代码文件。

- [ ] **Step 1：运行后端自动准备测试与前端类型检查**

```powershell
cd D:\Jellyfish\Jellyfish
uv run --project backend pytest backend/tests/test_shot_auto_preparation_service.py -q
```

```powershell
cd D:\Jellyfish\Jellyfish\front
pnpm exec tsc --noEmit
```

预期结果：

```text
后端自动准备测试通过。
TypeScript 通过。
```

- [ ] **Step 2：确认本阶段没有误改公开 API/generated client**

```powershell
cd D:\Jellyfish\Jellyfish
git diff --name-only HEAD~8..HEAD
```

预期结果：

```text
没有 backend API 路由契约变更。
没有 front/src/services/generated 文件变更。
```

如果执行阶段确实修改了 API，则必须运行：

```powershell
cd D:\Jellyfish\Jellyfish\front
pnpm run openapi:update
pnpm exec tsc --noEmit
```

预期结果：

```text
OpenAPI 更新完成，TypeScript 通过。
```

- [ ] **Step 3：启动前端开发服务**

```powershell
cd D:\Jellyfish\Jellyfish\front
pnpm run dev -- --host 127.0.0.1
```

预期结果：

```text
Vite 输出本地访问地址，例如 http://127.0.0.1:5173。
```

- [ ] **Step 4：用 Browser 插件检查主流程**

在本地页面验证：

```text
项目大厅的 prepare_shots 主动作进入分镜准备队列。
工作台 Dashboard 的 prepare_shots 推荐动作进入分镜准备队列。
章节列表的 prepare_shots 主动作进入分镜准备队列。
分镜列表页存在 pending 分镜时，主动作进入分镜编辑页。
分镜列表页全部 ready 时，主动作进入工作室。
工作室在存在 ready 或运行中镜头时，不默认选中 pending 镜头。
工作室没有 ready 镜头时，显示返回分镜准备的阻塞提示。
任务中心仍只展示通用任务状态，不展示 prompt 调试、图文映射或业务重上下文。
```

- [ ] **Step 5：检查占位词和边界问题**

```powershell
cd D:\Jellyfish\Jellyfish
$patterns = @('TO' + 'DO', 'TB' + 'D', 'implement ' + 'later', 'fill in ' + 'details', 'handwritten service', 'shot.status.*generating')
rg -n ($patterns -join '|') front/src/pages/aiStudio site/content/docs
```

预期结果：

```text
没有本次新增的占位文本。
没有新增手写前端 service wrapper。
没有新增把 shot.status 当作运行中生成状态的逻辑。
```

- [ ] **Step 6：如手动检查产生修复，提交最终修复**

```powershell
cd D:\Jellyfish\Jellyfish
git status --short
git add front/src/pages/aiStudio site/content/docs
git commit -m "fix: polish creative flow ux"
```

预期结果：

```text
只提交本次实现相关文件。
未跟踪的 .understand-anything 目录继续保持未暂存，除非用户明确要求提交它。
```

## 规格覆盖自检

- “主流程纠偏 + 下一步推荐”：任务 1、2、3 覆盖。
- 暂不加入完整新手 Wizard：任务 1 的流程条是轻量提示，不引入独立 Wizard。
- 分镜列表页作为准备队列：任务 3 覆盖。
- 分镜编辑页作为准备站：任务 4 覆盖。
- 分镜工作室作为生成工作区：任务 5、6 覆盖。
- 按钮更明显、初始引导更清晰：任务 2、3、4、6 使用统一主按钮与 `size="large"` 行动入口。
- 一键生成 ready 分镜：任务 6 覆盖。
- 任务中心保持通用轻量：任务 9 手动检查覆盖，并且计划不修改 Task Center。
- 9 张参考图、资产图片历史、批量上传、本地图片、AI2D/AI3D 风格：任务 7 记录能力审计与二期边界。
- architecture 与 plans 文档同步：任务 8 覆盖。
- 验证要求：任务 9 覆盖。

## 类型与命名一致性自检

- `CreativeFlowStageKey` 使用现有阶段：`edit_raw`、`extract_shots`、`prepare_shots`、`shoot`，额外只增加空项目用的 `create_chapter`。
- `prepare_shots` 的主流程目标只能是 `chapter_shots` 或 `shot_edit`。
- `shoot` 的目标才是 `chapter_studio`。
- `shot.status` 只判断信息确认状态，`ready` 表示确认完成。
- 运行中状态来自 `has_active_tasks` / runtime summary。
- 视频生成门禁继续来自 `video-readiness`。
