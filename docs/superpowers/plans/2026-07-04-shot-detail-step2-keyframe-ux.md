# 镜头详情"提取确认"体验优化与关键帧面板迁移 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化镜头详情页第 2 步（资产与对白确认）的命名与状态展示，支持手动补录对白，并把关键帧/参考图生成能力从已废弃的 `ChapterStudio.tsx` 迁移到镜头详情页"生成视频"步骤，解除当前"缺少参考帧但无处可去"的阻塞。

**Architecture:** 全部改动在 `front/` 内完成，不新增后端 API、不修改 OpenAPI。复用已有生成客户端方法（对白 CRUD、`StudioImageTasksService`、`StudioShotFrameImagesService`、`FilmService`）与已有 Hook（`usePointsQuote`、`useGenerationDraft`）。关键帧生成弹窗按新页面的 `unionAssets` 数据结构重写，不整体照搬 `ChapterStudio.tsx`。

**Tech Stack:** React + TypeScript + Ant Design + Tailwind（前端唯一栈，无新增依赖）。前端无自动化测试框架，验证手段为 `pnpm exec tsc --noEmit` + 手动浏览器验证（每个任务的验证步骤都会给出具体点击路径）。

**关联文档：**
- 设计文档：`docs/superpowers/specs/2026-07-04-shot-detail-step2-keyframe-ux-design.md`
- 前置规划：`docs/superpowers/specs/2026-07-02-project-shot-flow-redesign-design.md`（本计划不实现其"生成模式与模型能力"目标，仅落地一个技术 key 的临时 Select）

---

## 文件结构总览

| 文件 | 改动类型 | 职责 |
|---|---|---|
| `front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx` | 修改 | 步骤标题、状态徽标合并、对白/关键帧状态与回调、`reference_mode` 状态接入 |
| `front/src/pages/aiStudio/shots/components/ChapterShotAssetConfirmation.tsx` | 修改 | "2.1"子标题文案 |
| `front/src/pages/aiStudio/shots/components/ChapterShotDialogueConfirmation.tsx` | 修改 | 新增"新增对白"按钮与本地草稿行 |
| `front/src/pages/guide/CreationGuidePage.tsx` | 修改 | 同步"提取确认"→"资产与对白确认"引导文案 |
| `front/src/pages/aiStudio/shots/components/ShotVideoGenerationTab.tsx` | 修改 | 新增参考模式 Select、渲染关键帧卡片小节 |
| `front/src/pages/aiStudio/shots/components/ShotKeyframeCard.tsx` | 新建 | 单个帧类型卡片：候选缩略图 + 生成/使用 |
| `front/src/pages/aiStudio/shots/components/ShotKeyframeGenerateModal.tsx` | 新建 | 统一生成弹窗：参考图选择（自动+手动合一）+ 提示词编辑 + 提交 |

---

### Task 1: 命名调整（步骤标题 + 引导文案）

**Files:**
- Modify: `front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx:2563`
- Modify: `front/src/pages/aiStudio/shots/components/ChapterShotAssetConfirmation.tsx:300`
- Modify: `front/src/pages/guide/CreationGuidePage.tsx:22,38,56,57,69,222,223,227`

- [ ] **Step 1: 修改步骤 2 外层标题**

在 `ChapterShotEditPage.tsx:2563` 找到：

```tsx
          <span>2 提取确认</span>
```

改为：

```tsx
          <span>2 资产与对白确认</span>
```

- [ ] **Step 2: 修改步骤 2 工作区标题（同一文件内的另一处出现）**

在同文件搜索 `提取确认工作区`（约 2571 行）：

```tsx
                <div className="text-sm font-medium text-slate-900">提取确认工作区</div>
```

改为：

```tsx
                <div className="text-sm font-medium text-slate-900">资产与对白确认工作区</div>
```

- [ ] **Step 3: 修改 2.1 子模块标题**

在 `ChapterShotAssetConfirmation.tsx:300` 找到：

```tsx
            <div className="text-sm font-medium text-slate-900">资产候选确认</div>
```

改为：

```tsx
            <div className="text-sm font-medium text-slate-900">资产关联</div>
```

- [ ] **Step 4: 同步 `CreationGuidePage.tsx` 引导文案**

逐一替换以下字符串（保持标点与上下文不变，只替换"提取确认"字样为"资产与对白确认"）：

`CreationGuidePage.tsx:22`：

```tsx
  { id: 'prepare', title: '镜头详情四步', eyebrow: '5', summary: '在基础信息、提取确认、生成视频、视频结果四步里推进单镜头。' },
```

改为：

```tsx
  { id: 'prepare', title: '镜头详情四步', eyebrow: '5', summary: '在基础信息、资产与对白确认、生成视频、视频结果四步里推进单镜头。' },
```

`CreationGuidePage.tsx:38`：

```tsx
  { title: '镜头详情四步准备', description: '在基础信息 / 提取确认里确认资产、对白和镜头信息' },
```

改为：

```tsx
  { title: '镜头详情四步准备', description: '在基础信息 / 资产与对白确认里确认资产、对白和镜头信息' },
```

`CreationGuidePage.tsx:56`：

```tsx
  { key: 'prepare', status: '待准备镜头', meaning: '镜头已拆好，还需要进入镜头详情完成基础信息与提取确认。', action: '进入分镜列表或镜头详情' },
```

改为：

```tsx
  { key: 'prepare', status: '待准备镜头', meaning: '镜头已拆好，还需要进入镜头详情完成基础信息与资产与对白确认。', action: '进入分镜列表或镜头详情' },
```

`CreationGuidePage.tsx:57`：

```tsx
  { key: 'shoot', status: '待继续生成', meaning: '镜头已完成提取确认，但是否可生成仍要看视频准备度。', action: '进入分镜列表或镜头详情的生成视频步骤' },
```

改为：

```tsx
  { key: 'shoot', status: '待继续生成', meaning: '镜头已完成资产与对白确认，但是否可生成仍要看视频准备度。', action: '进入分镜列表或镜头详情的生成视频步骤' },
```

`CreationGuidePage.tsx:69`：

```tsx
  { src: '/guide/guide-shot-008.jpg', caption: '图 09 镜头详情 · 提取确认' },
```

改为：

```tsx
  { src: '/guide/guide-shot-008.jpg', caption: '图 09 镜头详情 · 资产与对白确认' },
```

`CreationGuidePage.tsx:222-227`：

```tsx
            <GuideBlock id="prepare" number="5" title="镜头详情四步（基础信息 / 提取确认 / 生成视频 / 视频结果）">
              <p>在分镜列表点「编辑」进入镜头详情。镜头详情按「基础信息 / 提取确认 / 生成视频 / 视频结果」四个步骤组织，前两个步骤先把镜头准备完整，后两个步骤再承担生成与结果回看。</p>
              <Figure {...screenshots[7]} />
              <p>基础信息里重点确认标题、剧本摘录、景别、机位、运镜、时长和动作拍点。动作拍点保留 2-4 条即可。</p>
              <Figure {...screenshots[8]} />
              <p>提取确认里检查场景、角色、道具、服装和对白。主路径里系统会先自动准备候选；手动重新提取只作为修复入口。待确认候选需要关联或忽略；纯画面镜头可标记「无需提取」。`shot.status = ready` 只表示这里的确认完成，不等于已经满足视频生成条件。</p>
```

改为：

```tsx
            <GuideBlock id="prepare" number="5" title="镜头详情四步（基础信息 / 资产与对白确认 / 生成视频 / 视频结果）">
              <p>在分镜列表点「编辑」进入镜头详情。镜头详情按「基础信息 / 资产与对白确认 / 生成视频 / 视频结果」四个步骤组织，前两个步骤先把镜头准备完整，后两个步骤再承担生成与结果回看。</p>
              <Figure {...screenshots[7]} />
              <p>基础信息里重点确认标题、剧本摘录、景别、机位、运镜、时长和动作拍点。动作拍点保留 2-4 条即可。</p>
              <Figure {...screenshots[8]} />
              <p>资产与对白确认里检查场景、角色、道具、服装和对白。主路径里系统会先自动准备候选；手动重新提取只作为修复入口。待确认候选需要关联或忽略；纯画面镜头可标记「无需提取」。`shot.status = ready` 只表示这里的确认完成，不等于已经满足视频生成条件。</p>
```

- [ ] **Step 5: 类型检查**

Run: `cd front && pnpm exec tsc --noEmit`
Expected: 无新增报错（纯文案改动不影响类型）

- [ ] **Step 6: 浏览器手动验证**

打开任意镜头详情页，确认左侧步骤条第 2 步显示"2 资产与对白确认"，进入该步骤后工作区标题显示"资产与对白确认工作区"，其下 2.1 子标题显示"资产关联"。打开"创建引导"页（`/guide` 或对应路由），确认相关文案已同步更新。

- [ ] **Step 7: Commit**

```bash
git add front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx front/src/pages/aiStudio/shots/components/ChapterShotAssetConfirmation.tsx front/src/pages/guide/CreationGuidePage.tsx
git commit -m "feat: 步骤2改名为资产与对白确认"
```

---

### Task 2: 分镜列表状态徽标合并

**Files:**
- Modify: `front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx:197-253`（状态函数）
- Modify: `front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx:2916-3022`（列表渲染）

- [ ] **Step 1: 用一个合并函数替换 `getExtractionListStatus` 与 `getShotPreparationIssueSummary`**

在 `ChapterShotEditPage.tsx:197-249` 找到现有的两个函数：

```tsx
function getExtractionListStatus(shot: ShotRead): {
  text: string
  background: string
  color: string
} {
  const state = getShotExtractionSummary(shot).state
  if (state === 'skipped') {
    return { text: '已跳过', background: '#e0f2fe', color: '#075985' }
  }
  if (state === 'not_extracted') {
    return { text: '未提取', background: '#fef3c7', color: '#92400e' }
  }
  if (state === 'extracted_empty') {
    return { text: '已提取无结果', background: '#dbeafe', color: '#1d4ed8' }
  }
  if (state === 'extracted_resolved' || shot.status === 'ready') {
    return { text: '确认已完成', background: '#dbeafe', color: '#1d4ed8' }
  }
  return { text: '待确认', background: '#fef3c7', color: '#92400e' }
}

function isPendingExtractionConfirmation(shot: ShotRead): boolean {
  return getShotExtractionSummary(shot).state === 'extracted_pending'
}

function isActionablePreparationShot(shot: ShotRead): boolean {
  const state = getShotExtractionSummary(shot).state
  return state === 'not_extracted' || state === 'extracted_pending'
}

function getShotPreparationIssueSummary(shot: ShotRead): {
  text: string
  tone: 'gold' | 'blue' | 'green'
} {
  const basicReady = !!shot.title?.trim() && !!shot.script_excerpt?.trim()
  const extractionState = getShotExtractionSummary(shot).state
  if (!basicReady) {
    return { text: '基础待补', tone: 'gold' }
  }
  if (extractionState === 'not_extracted') {
    return { text: '待执行提取', tone: 'gold' }
  }
  if (extractionState === 'extracted_pending') {
    return { text: '待确认候选', tone: 'gold' }
  }
  if (extractionState === 'extracted_empty') {
    return { text: '已提取无结果', tone: 'blue' }
  }
  if (extractionState === 'skipped') {
    return { text: '已跳过提取', tone: 'blue' }
  }
  return { text: '准备完成', tone: 'green' }
}
```

保留 `isPendingExtractionConfirmation` 和 `isActionablePreparationShot`（后面渲染逻辑仍依赖），删除 `getExtractionListStatus` 和 `getShotPreparationIssueSummary`，替换为一个新函数：

```tsx
function isPendingExtractionConfirmation(shot: ShotRead): boolean {
  return getShotExtractionSummary(shot).state === 'extracted_pending'
}

function isActionablePreparationShot(shot: ShotRead): boolean {
  const state = getShotExtractionSummary(shot).state
  return state === 'not_extracted' || state === 'extracted_pending'
}

/**
 * 合并"基础信息完整性"与"资产/对白候选处理进度"两件事，输出分镜列表唯一的准备阶段徽标。
 * 待处理数量 = 待确认资产候选数 + 待确认对白候选数，取自 shot.extraction 聚合字段。
 */
function getShotPreparationBadge(shot: ShotRead): {
  text: string
  tone: 'gold' | 'blue' | 'green'
} {
  const basicReady = !!shot.title?.trim() && !!shot.script_excerpt?.trim()
  if (!basicReady) {
    return { text: '基础待补', tone: 'gold' }
  }
  const extraction = getShotExtractionSummary(shot)
  const pendingCount = (extraction.asset_candidate_pending_count ?? 0) + (extraction.dialogue_candidate_pending_count ?? 0)
  if (extraction.state === 'not_extracted') {
    return { text: '待执行提取', tone: 'gold' }
  }
  if (pendingCount > 0) {
    return { text: `待关联确认 ${pendingCount} 项`, tone: 'gold' }
  }
  return { text: '准备完成', tone: 'green' }
}
```

- [ ] **Step 2: 确认 `ShotExtractionSummaryRead` 是否已有 pending 计数字段**

Run: `cd front/src && grep -n "asset_candidate_pending_count\|dialogue_candidate_pending_count\|pending_count" services/generated/models/ShotExtractionSummaryRead.ts`

如果输出为空（字段名不同），打开 `front/src/services/generated/models/ShotExtractionSummaryRead.ts` 查看实际字段名（比如可能是 `asset_candidate_total` / `dialogue_candidate_total` 且没有单独的 pending 计数），并按实际字段名调整 Step 1 里 `pendingCount` 的取值表达式，保持"待关联确认 N 项"里的 N 表示"待处理资产候选数 + 待处理对白候选数"这个语义不变。

- [ ] **Step 3: 更新列表渲染，只保留合并后的单个徽标**

在 `ChapterShotEditPage.tsx:2916-3022` 的 `renderItem` 里，找到：

```tsx
                  renderItem={(item) => {
                    const active = item.id === shotId
                    const selected = selectedShotIds.includes(item.id)
                    const itemBasicReady = !!item.title?.trim() && !!item.script_excerpt?.trim()
                    const itemConfirmStatus = getExtractionListStatus(item)
                    const itemIssueSummary = getShotPreparationIssueSummary(item)
                    const itemActionable = isActionablePreparationShot(item) || !itemBasicReady
                    const itemCompleted = itemBasicReady && !itemActionable
```

改为：

```tsx
                  renderItem={(item) => {
                    const active = item.id === shotId
                    const selected = selectedShotIds.includes(item.id)
                    const itemBasicReady = !!item.title?.trim() && !!item.script_excerpt?.trim()
                    const itemPreparationBadge = getShotPreparationBadge(item)
                    const itemActionable = isActionablePreparationShot(item) || !itemBasicReady
                    const itemCompleted = itemBasicReady && !itemActionable
```

找到名称右侧的徽标渲染（约 2981-2999 行）：

```tsx
                              <span
                                className="inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-medium"
                                style={{
                                  background:
                                    itemIssueSummary.tone === 'green'
                                      ? '#dcfce7'
                                      : itemIssueSummary.tone === 'blue'
                                        ? '#dbeafe'
                                        : '#fef3c7',
                                  color:
                                    itemIssueSummary.tone === 'green'
                                      ? '#166534'
                                      : itemIssueSummary.tone === 'blue'
                                        ? '#1d4ed8'
                                        : '#92400e',
                                }}
                              >
                                {itemIssueSummary.text}
                              </span>
```

改为：

```tsx
                              <span
                                className="inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-medium"
                                style={{
                                  background:
                                    itemPreparationBadge.tone === 'green'
                                      ? '#dcfce7'
                                      : itemPreparationBadge.tone === 'blue'
                                        ? '#dbeafe'
                                        : '#fef3c7',
                                  color:
                                    itemPreparationBadge.tone === 'green'
                                      ? '#166534'
                                      : itemPreparationBadge.tone === 'blue'
                                        ? '#1d4ed8'
                                        : '#92400e',
                                }}
                              >
                                {itemPreparationBadge.text}
                              </span>
```

找到名称下方的两个徽标（约 3002-3022 行）：

```tsx
                          <div className="text-xs text-gray-500 truncate">{item.script_excerpt ?? ''}</div>
                          <div className="mt-1 flex flex-wrap items-center gap-1">
                            <span
                              className="inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-medium"
                              style={{
                                background: itemBasicReady ? '#dcfce7' : '#fef3c7',
                                color: itemBasicReady ? '#166534' : '#92400e',
                              }}
                            >
                              {itemBasicReady ? '基础已完成' : '基础待补'}
                            </span>
                            <span
                              className="inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-medium"
                              style={{
                                background: itemConfirmStatus.background,
                                color: itemConfirmStatus.color,
                              }}
                            >
                              {itemConfirmStatus.text}
                            </span>
                          </div>
```

改为（只保留原文摘录，去掉两个重复徽标）：

```tsx
                          <div className="text-xs text-gray-500 truncate">{item.script_excerpt ?? ''}</div>
```

- [ ] **Step 4: 全文搜索确认没有遗留引用**

Run: `cd front/src && grep -n "getExtractionListStatus\|getShotPreparationIssueSummary\|itemConfirmStatus\|itemIssueSummary" pages/aiStudio/shots/ChapterShotEditPage.tsx`
Expected: 无输出（全部已替换为 `getShotPreparationBadge` / `itemPreparationBadge`）

- [ ] **Step 5: 类型检查**

Run: `cd front && pnpm exec tsc --noEmit`
Expected: 无报错

- [ ] **Step 6: 浏览器手动验证**

打开任意章节的分镜列表右侧栏，确认每条镜头只显示 1 个徽标（名称右侧），基础信息缺失时显示"基础待补"，资产/对白候选有待处理项时显示"待关联确认 N 项"（N 为实际待处理数之和），全部完成时显示"准备完成"（绿色）。确认名称下方不再出现另外两个徽标。

- [ ] **Step 7: Commit**

```bash
git add front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx
git commit -m "feat: 分镜列表状态徽标合并为单个准备阶段徽标"
```

---

### Task 3: 对白手动新增

**Files:**
- Modify: `front/src/pages/aiStudio/shots/components/ChapterShotDialogueConfirmation.tsx`
- Modify: `front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx`（新增状态与回调，接线到组件）

- [ ] **Step 1: 在 `ChapterShotDialogueConfirmation.tsx` 新增草稿行的 props 与本地状态**

在文件顶部 `type ChapterShotDialogueConfirmationProps` 里新增两个 prop（紧跟在 `onUpdateExtractedDialogText` 之后）：

```tsx
  onUpdateExtractedDialogText: (candidateId: number, text: string) => void
  /** 新增一条本地草稿对白（尚未持久化），插入到已保存列表末尾 */
  onAddDraftDialogueLine: () => void
  /** 草稿行内容变化（说话人/对象/文本），非空文本时由父组件负责创建持久化记录 */
  draftDialogueLine: { speakerName: string; targetName: string; text: string } | null
  onUpdateDraftDialogueLine: (patch: Partial<{ speakerName: string; targetName: string; text: string }>) => void
  onBlurDraftDialogueLine: () => void
  draftDialogueSaving: boolean
```

- [ ] **Step 2: 在标题行按钮组新增"新增对白"按钮**

找到（约 108-121 行）：

```tsx
        <div className="flex items-center gap-2">
          {extractedDialogLines.length > 0 ? (
            <>
              <Button size="small" loading={batchDialogAdding} onClick={onAcceptAll}>
                全部接受
              </Button>
              <Button size="small" disabled={batchDialogAdding} onClick={onIgnoreAll}>
                全部忽略
              </Button>
            </>
          ) : null}
          {dialogLoading ? <Spin size="small" /> : null}
        </div>
```

改为：

```tsx
        <div className="flex items-center gap-2">
          <Button size="small" icon={<PlusOutlined />} disabled={!!draftDialogueLine} onClick={onAddDraftDialogueLine}>
            新增对白
          </Button>
          {extractedDialogLines.length > 0 ? (
            <>
              <Button size="small" loading={batchDialogAdding} onClick={onAcceptAll}>
                全部接受
              </Button>
              <Button size="small" disabled={batchDialogAdding} onClick={onIgnoreAll}>
                全部忽略
              </Button>
            </>
          ) : null}
          {dialogLoading ? <Spin size="small" /> : null}
        </div>
```

- [ ] **Step 3: 在已保存列表末尾渲染草稿行**

找到已保存列表的渲染块结尾（约 130-162 行，`savedDialogLines.length > 0 ? (...) : null` 这一整块），在它之后、`{extractedDialogLines.length > 0 ? (` 之前插入草稿行渲染：

```tsx
        {draftDialogueLine ? (
          <div className="flex items-start gap-2">
            <Tooltip title="新增草稿，输入内容后自动保存">
              <span className="mt-1 text-slate-400">
                <PlusOutlined />
              </span>
            </Tooltip>
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              loading={draftDialogueSaving}
              onClick={onBlurDraftDialogueLine}
            />
            <Input
              className="w-36 shrink-0 text-xs"
              size="small"
              value={draftDialogueLine.speakerName}
              placeholder="说话人"
              onChange={(e) => onUpdateDraftDialogueLine({ speakerName: e.target.value })}
            />
            <Input.TextArea
              value={draftDialogueLine.text}
              onChange={(e) => onUpdateDraftDialogueLine({ text: e.target.value })}
              onBlur={onBlurDraftDialogueLine}
              autoSize={{ minRows: 1, maxRows: 4 }}
              placeholder="对白内容，输入后自动保存"
              disabled={draftDialogueSaving}
            />
          </div>
        ) : null}
```

- [ ] **Step 4: 在 `ChapterShotEditPage.tsx` 新增草稿行状态**

在 `savedDialogLines` 等状态附近（约 345-349 行）新增：

```tsx
  const [draftDialogueLine, setDraftDialogueLine] = useState<{ speakerName: string; targetName: string; text: string } | null>(null)
  const [draftDialogueSaving, setDraftDialogueSaving] = useState(false)
```

- [ ] **Step 5: 新增草稿行的操作回调**

在 `deleteSavedDialogLine` 定义之后（约 769 行之后）新增：

```tsx
  const addDraftDialogueLine = useCallback(() => {
    setDraftDialogueLine({ speakerName: '', targetName: '', text: '' })
  }, [])

  const updateDraftDialogueLine = useCallback(
    (patch: Partial<{ speakerName: string; targetName: string; text: string }>) => {
      setDraftDialogueLine((prev) => (prev ? { ...prev, ...patch } : prev))
    },
    [],
  )

  /**
   * 草稿行失焦时：内容非空则创建持久化对白记录并转为已保存行；内容为空则直接丢弃草稿，不调用接口。
   */
  const commitDraftDialogueLine = useCallback(async () => {
    if (!shotId || !draftDialogueLine) return
    const text = draftDialogueLine.text.trim()
    if (!text) {
      setDraftDialogueLine(null)
      return
    }
    if (draftDialogueSaving) return
    setDraftDialogueSaving(true)
    try {
      const nextIndex = savedDialogLines.reduce((max, l) => Math.max(max, l.index ?? 0), 0) + 1
      const res = await StudioShotDialogLinesService.createShotDialogLineApiV1StudioShotDialogLinesPost({
        requestBody: {
          shot_detail_id: shotId,
          index: nextIndex,
          text,
          speaker_name: draftDialogueLine.speakerName.trim() || null,
          target_name: draftDialogueLine.targetName.trim() || null,
        },
      })
      const created = res.data
      if (created) {
        setSavedDialogLines((prev) => [...prev, created])
        message.success('已新增对白')
      }
      setDraftDialogueLine(null)
    } catch {
      message.error('新增对白失败')
    } finally {
      setDraftDialogueSaving(false)
    }
  }, [draftDialogueLine, draftDialogueSaving, savedDialogLines, shotId])
```

- [ ] **Step 6: 接线到组件**

找到 `<ChapterShotDialogueConfirmation` 渲染处（约 2671-2683 行），在 `onUpdateExtractedDialogText={...}` 之后新增：

```tsx
            onUpdateExtractedDialogText={updateExtractedDialogText}
            onAddDraftDialogueLine={addDraftDialogueLine}
            draftDialogueLine={draftDialogueLine}
            onUpdateDraftDialogueLine={updateDraftDialogueLine}
            onBlurDraftDialogueLine={() => void commitDraftDialogueLine()}
            draftDialogueSaving={draftDialogueSaving}
```

- [ ] **Step 7: 确认 `ShotDialogLineCreate` 字段名与实际生成模型一致**

Run: `cd front/src && cat services/generated/models/ShotDialogLineCreate.ts`
Expected: 包含 `shot_detail_id: string`、`index: number`、`text: string`、`speaker_name?: (string | null)`、`target_name?: (string | null)`，与 Step 5 里 `requestBody` 字段一致。若字段名不同（例如实际是 `line_mode` 必填而非可选），据实调整 Step 5 的 `requestBody`。

- [ ] **Step 8: 类型检查**

Run: `cd front && pnpm exec tsc --noEmit`
Expected: 无报错

- [ ] **Step 9: 浏览器手动验证**

打开任意镜头详情页，进入"2 资产与对白确认"步骤，点击"新增对白"按钮，确认出现一行可编辑空行；输入说话人和对白内容后点击其他地方（失焦），确认该行变成已保存行样式（可继续编辑、可删除），刷新页面后仍然保留。再次点击"新增对白"，不输入任何内容直接点击其他地方，确认草稿行消失且没有产生新的空对白记录（可通过刷新页面确认列表条数未变化）。

- [ ] **Step 10: Commit**

```bash
git add front/src/pages/aiStudio/shots/components/ChapterShotDialogueConfirmation.tsx front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx
git commit -m "feat: 对白确认支持手动新增"
```

---

### Task 4: `reference_mode` 状态与关键帧卡片骨架

**Files:**
- Modify: `front/src/pages/aiStudio/shots/components/ShotVideoGenerationTab.tsx`
- Create: `front/src/pages/aiStudio/shots/components/ShotKeyframeCard.tsx`
- Modify: `front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx`

本任务只搭骨架：新增参考模式 Select、按选中模式动态显示对应帧类型卡片、卡片展示已有候选缩略图和当前使用中的图片。"生成"按钮先只留空回调（下一任务实现弹窗），"使用"按钮直接可用。

- [ ] **Step 1: 新建 `ShotKeyframeCard.tsx`**

Create: `front/src/pages/aiStudio/shots/components/ShotKeyframeCard.tsx`

```tsx
import { Button, Empty, Image, Tag } from 'antd'
import type { ShotFrameType } from '../../../../services/generated'

export type ShotKeyframeCandidate = {
  linkId: number
  fileId: string
  thumbUrl: string
}

const FRAME_TYPE_LABEL: Record<ShotFrameType, string> = { first: '首帧', key: '关键帧', last: '尾帧' }

type ShotKeyframeCardProps = {
  frameType: ShotFrameType
  currentFileId: string | null
  candidates: ShotKeyframeCandidate[]
  applyingFileId: string | null
  onGenerate: (frameType: ShotFrameType) => void
  onApply: (frameType: ShotFrameType, fileId: string) => void
}

/** 单个帧类型（首帧/关键帧/尾帧）卡片：候选缩略图横向列表 + 生成 + 使用。 */
export function ShotKeyframeCard({
  frameType,
  currentFileId,
  candidates,
  applyingFileId,
  onGenerate,
  onApply,
}: ShotKeyframeCardProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white/80 p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-slate-900">{FRAME_TYPE_LABEL[frameType]}</div>
        <Button size="small" onClick={() => onGenerate(frameType)}>
          生成
        </Button>
      </div>
      {candidates.length === 0 ? (
        <Empty description="暂无候选图片" image={Empty.PRESENTED_IMAGE_SIMPLE} imageStyle={{ height: 40 }} />
      ) : (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {candidates.map((candidate) => {
            const isCurrent = candidate.fileId === currentFileId
            return (
              <div key={candidate.linkId} className="shrink-0 space-y-1">
                <Image src={candidate.thumbUrl} width={72} height={72} className="rounded-md object-cover" />
                {isCurrent ? (
                  <Tag color="blue" className="!m-0 text-center block">
                    使用中
                  </Tag>
                ) : (
                  <Button
                    size="small"
                    block
                    loading={applyingFileId === candidate.fileId}
                    onClick={() => onApply(frameType, candidate.fileId)}
                  >
                    使用
                  </Button>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 在 `ShotVideoGenerationTab.tsx` 新增参考模式 Select 与动态卡片区域**

在文件顶部 import 区新增：

```tsx
import type { ShotFrameType } from '../../../../services/generated'
import { ShotKeyframeCard, type ShotKeyframeCandidate } from './ShotKeyframeCard'
```

在 `type ShotVideoGenerationTabProps` 里新增字段（紧跟 `videoReadinessLoading` 之后）：

```tsx
  videoReadinessLoading: boolean
  referenceMode: 'first' | 'last' | 'key' | 'first_last' | 'first_last_key' | 'text_only'
  onReferenceModeChange: (mode: 'first' | 'last' | 'key' | 'first_last' | 'first_last_key' | 'text_only') => void
  keyframeCandidatesByType: Record<ShotFrameType, ShotKeyframeCandidate[]>
  keyframeCurrentFileIdByType: Record<ShotFrameType, string | null>
  keyframeApplyingFileId: string | null
  onGenerateKeyframe: (frameType: ShotFrameType) => void
  onApplyKeyframe: (frameType: ShotFrameType, fileId: string) => void
```

在组件函数参数解构里同步新增这些字段；组件体内新增帧类型映射与卡片渲染逻辑：

```tsx
const REFERENCE_MODE_OPTIONS: Array<{ value: ShotVideoGenerationTabProps['referenceMode']; label: string }> = [
  { value: 'text_only', label: '纯文字（不用参考帧）' },
  { value: 'first', label: '首帧参考' },
  { value: 'last', label: '尾帧参考' },
  { value: 'key', label: '关键帧参考' },
  { value: 'first_last', label: '首尾帧' },
  { value: 'first_last_key', label: '首尾 + 关键帧' },
]

const REQUIRED_FRAME_TYPES_BY_MODE: Record<ShotVideoGenerationTabProps['referenceMode'], ShotFrameType[]> = {
  text_only: [],
  first: ['first'],
  last: ['last'],
  key: ['key'],
  first_last: ['first', 'last'],
  first_last_key: ['first', 'last', 'key'],
}
```

在"生成配置"卡片内、`Descriptions` 之后、模型/清晰度 `grid` 之前插入参考模式 Select 与关键帧卡片小节：

```tsx
          <div className="space-y-1">
            <Typography.Text className="text-xs text-slate-500">参考模式</Typography.Text>
            <Select
              className="w-full"
              value={referenceMode}
              onChange={onReferenceModeChange}
              options={REFERENCE_MODE_OPTIONS}
            />
          </div>

          {REQUIRED_FRAME_TYPES_BY_MODE[referenceMode].length > 0 ? (
            <div className="space-y-2">
              <Typography.Text className="text-xs text-slate-500">关键帧与参考图</Typography.Text>
              <div className="grid gap-2 md:grid-cols-2">
                {REQUIRED_FRAME_TYPES_BY_MODE[referenceMode].map((frameType) => (
                  <ShotKeyframeCard
                    key={frameType}
                    frameType={frameType}
                    currentFileId={keyframeCurrentFileIdByType[frameType]}
                    candidates={keyframeCandidatesByType[frameType]}
                    applyingFileId={keyframeApplyingFileId}
                    onGenerate={onGenerateKeyframe}
                    onApply={onApplyKeyframe}
                  />
                ))}
              </div>
            </div>
          ) : null}
```

- [ ] **Step 3: 在 `ChapterShotEditPage.tsx` 新增关键帧相关状态**

在 `firstFrameReadiness` 状态定义附近（约 361-362 行）新增：

```tsx
  const [videoReferenceMode, setVideoReferenceMode] = useState<'first' | 'last' | 'key' | 'first_last' | 'first_last_key' | 'text_only'>('first')
  const [frameImages, setFrameImages] = useState<ShotFrameImageRead[]>([])
  const [keyframeCandidatesByType, setKeyframeCandidatesByType] = useState<Record<ShotFrameType, ShotKeyframeCandidate[]>>({
    first: [],
    last: [],
    key: [],
  })
  const [keyframeApplyingFileId, setKeyframeApplyingFileId] = useState<string | null>(null)
```

在文件顶部 import 区补充：

```tsx
import type { ShotFrameImageRead, ShotFrameType } from '../../../services/generated'
import { StudioShotFrameImagesService } from '../../../services/generated'
import { ShotKeyframeCard, type ShotKeyframeCandidate } from './components/ShotKeyframeCard'
import { listTaskLinksNormalized } from '../../../services/filmTaskLinks'
```

（若 `ShotKeyframeCard` 未在本文件直接使用而只在 `ShotVideoGenerationTab.tsx` 内部使用，则跳过对 `ShotKeyframeCard` 组件本身的 import，只保留 `ShotKeyframeCandidate` 类型的 import。）

- [ ] **Step 4: 新增拉取分镜帧图片列表与候选缩略图的函数**

在 `firstFrameReadiness` 自动拉取的 `useEffect`（约 932-960 行）之后新增：

```tsx
  const refreshFrameImages = useCallback(async () => {
    if (!shotId) return
    try {
      const res = await StudioShotFrameImagesService.listShotFrameImagesApiV1StudioShotFrameImagesGet({
        shotDetailId: shotId,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      })
      setFrameImages((res.data?.items ?? []) as ShotFrameImageRead[])
    } catch {
      setFrameImages([])
    }
  }, [shotId])

  const refreshKeyframeCandidates = useCallback(
    async (frameType: ShotFrameType) => {
      const slotId = frameImages.find((x) => x.frame_type === frameType)?.id
      if (!slotId) {
        setKeyframeCandidatesByType((prev) => ({ ...prev, [frameType]: [] }))
        return
      }
      const links = await listTaskLinksNormalized({
        resourceType: 'image',
        relationType: 'shot_frame_image',
        relationEntityId: String(slotId),
        order: 'updated_at',
        isDesc: true,
        page: 1,
        pageSize: 100,
      })
      const seen = new Set<string>()
      const candidates: ShotKeyframeCandidate[] = links
        .filter((l) => Boolean(l.file_id))
        .filter((l) => {
          const fid = String(l.file_id)
          if (seen.has(fid)) return false
          seen.add(fid)
          return true
        })
        .map((l) => ({
          linkId: l.id,
          fileId: String(l.file_id),
          thumbUrl: buildFileDownloadUrl(String(l.file_id)) ?? '',
        }))
      setKeyframeCandidatesByType((prev) => ({ ...prev, [frameType]: candidates }))
    },
    [frameImages],
  )

  useEffect(() => {
    void refreshFrameImages()
  }, [refreshFrameImages])

  useEffect(() => {
    void refreshKeyframeCandidates('first')
    void refreshKeyframeCandidates('last')
    void refreshKeyframeCandidates('key')
  }, [refreshKeyframeCandidates])
```

确认文件顶部已 import `buildFileDownloadUrl`（若尚未导入，从 `../assets/utils` 补充：`import { buildFileDownloadUrl, resolveAssetUrl } from '../assets/utils'`，注意与已有的 `resolveAssetUrl` import 合并为一行，不要重复 import 同一模块）。

- [ ] **Step 5: 新增"使用"候选图片的回调**

```tsx
  const applyKeyframeCandidate = useCallback(
    async (frameType: ShotFrameType, fileId: string) => {
      const slotId = frameImages.find((x) => x.frame_type === frameType)?.id
      if (!slotId) return
      setKeyframeApplyingFileId(fileId)
      try {
        await StudioShotFrameImagesService.updateShotFrameImageApiV1StudioShotFrameImagesImageIdPatch({
          imageId: slotId,
          requestBody: { file_id: fileId },
        })
        message.success('已设为当前使用图片')
        await refreshFrameImages()
      } catch {
        message.error('设置失败')
      } finally {
        setKeyframeApplyingFileId(null)
      }
    },
    [frameImages, refreshFrameImages],
  )
```

Run: `cd front/src && cat services/generated/models/ShotFrameImageUpdate.ts` 确认 `file_id` 是该模型的合法字段（若字段名不同据实调整）。

- [ ] **Step 6: 接线到 `ShotVideoGenerationTab`**

找到 `<ShotVideoGenerationTab` 渲染处（约 2705-2716 行），在现有 props 之后新增：

```tsx
          referenceMode={videoReferenceMode}
          onReferenceModeChange={setVideoReferenceMode}
          keyframeCandidatesByType={keyframeCandidatesByType}
          keyframeCurrentFileIdByType={{
            first: frameImages.find((x) => x.frame_type === 'first')?.file_id ?? null,
            last: frameImages.find((x) => x.frame_type === 'last')?.file_id ?? null,
            key: frameImages.find((x) => x.frame_type === 'key')?.file_id ?? null,
          }}
          keyframeApplyingFileId={keyframeApplyingFileId}
          onGenerateKeyframe={() => {}}
          onApplyKeyframe={(frameType, fileId) => void applyKeyframeCandidate(frameType, fileId)}
```

（`onGenerateKeyframe` 先留空函数，Task 5 会替换为打开生成弹窗。）

- [ ] **Step 7: 类型检查**

Run: `cd front && pnpm exec tsc --noEmit`
Expected: 无报错。若 `ShotKeyframeCandidate` 或 `ShotFrameImageRead` 等类型导入路径与实际生成目录结构不符，按 `front/src/services/generated/index.ts` 实际导出路径调整 import。

- [ ] **Step 8: 浏览器手动验证**

打开一个还没有任何关键帧图片的镜头，进入"生成视频"步骤，确认出现"参考模式"下拉框，默认选中"首帧参考"，下方出现 1 张"首帧"卡片（无候选图片，显示空状态）。切换到"首尾帧"，确认下方变成 2 张卡片（首帧+尾帧）；切换到"纯文字"，确认卡片区域消失。

- [ ] **Step 9: Commit**

```bash
git add front/src/pages/aiStudio/shots/components/ShotVideoGenerationTab.tsx front/src/pages/aiStudio/shots/components/ShotKeyframeCard.tsx front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx
git commit -m "feat: 生成视频步骤新增参考模式选择与关键帧卡片骨架"
```

---

### Task 5: 关键帧生成弹窗（自动+手动参考图选择 + 提交生成）

**Files:**
- Create: `front/src/pages/aiStudio/shots/components/ShotKeyframeGenerateModal.tsx`
- Modify: `front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx`

- [ ] **Step 1: 新建 `ShotKeyframeGenerateModal.tsx`**

Create: `front/src/pages/aiStudio/shots/components/ShotKeyframeGenerateModal.tsx`

```tsx
import { useEffect, useMemo, useState } from 'react'
import { Button, Checkbox, Input, Modal, Spin } from 'antd'
import { ArrowDownOutlined, ArrowUpOutlined } from '@ant-design/icons'
import type { ShotFrameType, ShotLinkedAssetItem } from '../../../../services/generated'

export type KeyframeReferenceOption = ShotLinkedAssetItem & { kind: 'scene' | 'actor' | 'prop' | 'costume' }

type ShotKeyframeGenerateModalProps = {
  open: boolean
  frameType: ShotFrameType | null
  frameLabel: string
  loading: boolean
  submitting: boolean
  prompt: string
  onPromptChange: (value: string) => void
  quoteText: string | null
  referenceOptions: KeyframeReferenceOption[]
  selectedFileIds: string[]
  onChangeSelectedFileIds: (fileIds: string[]) => void
  onClose: () => void
  onSubmit: () => void
}

/**
 * 关键帧生成弹窗：默认列出当前镜头已关联资产作为参考图（等价于旧页自动收集），
 * 可勾选/取消，并可用上移下移按钮调整顺序；编辑提示词后提交生成任务。
 */
export function ShotKeyframeGenerateModal({
  open,
  frameType,
  frameLabel,
  loading,
  submitting,
  prompt,
  onPromptChange,
  quoteText,
  referenceOptions,
  selectedFileIds,
  onChangeSelectedFileIds,
  onClose,
  onSubmit,
}: ShotKeyframeGenerateModalProps) {
  const optionsByKind = useMemo(() => {
    const groups: Record<string, KeyframeReferenceOption[]> = { scene: [], actor: [], prop: [], costume: [] }
    referenceOptions.forEach((option) => {
      groups[option.kind]?.push(option)
    })
    return groups
  }, [referenceOptions])

  const toggleFileId = (fileId: string, checked: boolean) => {
    if (checked) {
      if (selectedFileIds.includes(fileId)) return
      onChangeSelectedFileIds([...selectedFileIds, fileId])
    } else {
      onChangeSelectedFileIds(selectedFileIds.filter((id) => id !== fileId))
    }
  }

  const moveFileId = (index: number, direction: -1 | 1) => {
    const target = index + direction
    if (target < 0 || target >= selectedFileIds.length) return
    const next = selectedFileIds.slice()
    const [item] = next.splice(index, 1)
    next.splice(target, 0, item)
    onChangeSelectedFileIds(next)
  }

  const kindLabel: Record<string, string> = { scene: '场景', actor: '角色', prop: '道具', costume: '服装' }

  return (
    <Modal
      title={`生成${frameLabel}`}
      open={open}
      onCancel={onClose}
      onOk={onSubmit}
      okButtonProps={{ loading: submitting, disabled: !prompt.trim() }}
      okText="提交生成"
      width={720}
      destroyOnClose
    >
      {loading ? (
        <div className="py-10 text-center">
          <Spin />
        </div>
      ) : (
        <div className="space-y-4">
          <div className="space-y-1">
            <div className="text-xs text-slate-500">提示词</div>
            <Input.TextArea value={prompt} onChange={(e) => onPromptChange(e.target.value)} autoSize={{ minRows: 2, maxRows: 6 }} />
          </div>

          <div className="space-y-2">
            <div className="text-xs text-slate-500">参考图（默认取当前镜头已关联资产，可取消勾选或调整顺序）</div>
            {(['scene', 'actor', 'prop', 'costume'] as const).map((kind) =>
              optionsByKind[kind].length > 0 ? (
                <div key={kind} className="space-y-1">
                  <div className="text-[11px] font-medium text-slate-600">{kindLabel[kind]}</div>
                  <div className="flex flex-wrap gap-2">
                    {optionsByKind[kind].map((option) => (
                      <Checkbox
                        key={`${option.type}:${option.id}`}
                        checked={!!option.file_id && selectedFileIds.includes(option.file_id)}
                        disabled={!option.file_id}
                        onChange={(e) => option.file_id && toggleFileId(option.file_id, e.target.checked)}
                      >
                        {option.name}
                      </Checkbox>
                    ))}
                  </div>
                </div>
              ) : null,
            )}
          </div>

          {selectedFileIds.length > 0 ? (
            <div className="space-y-1">
              <div className="text-xs text-slate-500">已选参考图顺序（影响融图优先级）</div>
              <div className="space-y-1">
                {selectedFileIds.map((fileId, index) => {
                  const matched = referenceOptions.find((option) => option.file_id === fileId)
                  return (
                    <div key={fileId} className="flex items-center justify-between gap-2 rounded-md bg-slate-50 px-2 py-1 text-xs">
                      <span>{matched?.name ?? fileId}</span>
                      <div className="flex items-center gap-1">
                        <Button
                          size="small"
                          type="text"
                          icon={<ArrowUpOutlined />}
                          disabled={index === 0}
                          onClick={() => moveFileId(index, -1)}
                        />
                        <Button
                          size="small"
                          type="text"
                          icon={<ArrowDownOutlined />}
                          disabled={index === selectedFileIds.length - 1}
                          onClick={() => moveFileId(index, 1)}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ) : null}

          {quoteText ? <div className="text-xs text-slate-500">{quoteText}</div> : null}
        </div>
      )}
    </Modal>
  )
}
```

- [ ] **Step 2: 在 `ChapterShotEditPage.tsx` 新增关键帧生成弹窗状态**

在 Task 4 新增的关键帧状态之后追加：

```tsx
  const [keyframeModalOpen, setKeyframeModalOpen] = useState(false)
  const [keyframeModalFrameType, setKeyframeModalFrameType] = useState<ShotFrameType | null>(null)
  const [keyframeModalPrompt, setKeyframeModalPrompt] = useState('')
  const [keyframeModalSelectedFileIds, setKeyframeModalSelectedFileIds] = useState<string[]>([])
  const [keyframeModalSubmitting, setKeyframeModalSubmitting] = useState(false)

  const keyframeImageQuote = usePointsQuote({
    businessType: 'image_generation',
    category: 'image',
    modelId: null,
    resolutionProfile: 'standard',
    enabled: keyframeModalOpen,
  })
```

- [ ] **Step 3: 构建参考图候选列表（来自第 2 步已关联资产）**

新增一个 `useMemo`，把 `unionAssets` 里状态为 `linked`/`generating` 且有 `file_id` 的项目摊平成 `KeyframeReferenceOption[]`：

```tsx
  const keyframeReferenceOptions = useMemo<KeyframeReferenceOption[]>(() => {
    const kindToType: Record<AssetKind, ShotLinkedAssetItem['type']> = {
      scene: 'scene',
      actor: 'character',
      prop: 'prop',
      costume: 'costume',
    }
    const options: KeyframeReferenceOption[] = []
    ;(['scene', 'actor', 'prop', 'costume'] as AssetKind[]).forEach((kind) => {
      unionAssets[kind]
        .filter((asset) => (asset.status === 'linked' || asset.status === 'generating') && !!asset.file_id)
        .forEach((asset) => {
          options.push({
            kind,
            type: kindToType[kind],
            id: asset.id ?? asset.name,
            name: asset.name,
            file_id: asset.file_id ?? null,
          })
        })
    })
    return options
  }, [unionAssets])
```

在文件顶部 import 区新增 `KeyframeReferenceOption` 类型与 `ShotLinkedAssetItem`：

```tsx
import { ShotKeyframeGenerateModal, type KeyframeReferenceOption } from './components/ShotKeyframeGenerateModal'
import type { ShotLinkedAssetItem } from '../../../services/generated'
```

- [ ] **Step 4: 打开弹窗的回调（对应 Task 4 里空的 `onGenerateKeyframe`）**

```tsx
  const openKeyframeGenerateModal = useCallback(
    (frameType: ShotFrameType) => {
      setKeyframeModalFrameType(frameType)
      const basePrompt =
        frameType === 'first'
          ? shotDetail?.first_frame_prompt ?? ''
          : frameType === 'last'
            ? shotDetail?.last_frame_prompt ?? ''
            : shotDetail?.key_frame_prompt ?? ''
      setKeyframeModalPrompt(basePrompt)
      setKeyframeModalSelectedFileIds(
        keyframeReferenceOptions.map((option) => option.file_id).filter((id): id is string => !!id),
      )
      setKeyframeModalOpen(true)
    },
    [keyframeReferenceOptions, shotDetail],
  )
```

把 Task 4 Step 6 里的 `onGenerateKeyframe={() => {}}` 改为：

```tsx
          onGenerateKeyframe={(frameType) => openKeyframeGenerateModal(frameType)}
```

- [ ] **Step 5: 提交生成任务并轮询**

```tsx
  const submitKeyframeGeneration = useCallback(async () => {
    if (!shotId || !keyframeModalFrameType) return
    const prompt = keyframeModalPrompt.trim()
    if (!prompt) return
    const ratio = resolvedVideoRatio
    if (!ratio) {
      message.warning('请先设置视频比例')
      return
    }
    if (!keyframeImageQuote.quoteToken) {
      message.warning('请等待积分试算完成后再提交')
      return
    }
    setKeyframeModalSubmitting(true)
    try {
      const images: ShotLinkedAssetItem[] = keyframeModalSelectedFileIds
        .map((fileId) => keyframeReferenceOptions.find((option) => option.file_id === fileId))
        .filter((option): option is KeyframeReferenceOption => !!option)
        .map((option) => ({ type: option.type, id: option.id, name: option.name, file_id: option.file_id }))

      const created = await StudioImageTasksService.createShotFrameImageGenerationTaskApiV1StudioImageTasksShotShotIdFrameImageTasksPost({
        shotId,
        requestBody: {
          frame_type: keyframeModalFrameType,
          model_id: null,
          prompt,
          images,
          target_ratio: ratio,
          resolution_profile: 'standard',
          quote_token: keyframeImageQuote.quoteToken,
        },
      })
      const taskId = created.data?.task_id ?? null
      message.success('已提交生成任务')
      setKeyframeModalOpen(false)
      if (taskId) {
        void pollKeyframeTask(taskId, keyframeModalFrameType)
      }
    } catch {
      message.error('提交生成任务失败')
    } finally {
      setKeyframeModalSubmitting(false)
    }
  }, [
    keyframeImageQuote.quoteToken,
    keyframeModalFrameType,
    keyframeModalPrompt,
    keyframeModalSelectedFileIds,
    keyframeReferenceOptions,
    resolvedVideoRatio,
    shotId,
  ])

  /** 轮询关键帧生成任务：间隔 2 秒，最多 30 次，完成后刷新候选缩略图。 */
  const pollKeyframeTask = useCallback(
    async (taskId: string, frameType: ShotFrameType) => {
      for (let attempt = 0; attempt < 30; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000))
        try {
          const res = await FilmService.getTaskStatusApiV1FilmTasksTaskIdStatusGet({ taskId })
          const status = res.data?.status
          if (status === 'succeeded') {
            await refreshFrameImages()
            await refreshKeyframeCandidates(frameType)
            return
          }
          if (status === 'failed' || status === 'cancelled') {
            message.error('关键帧生成任务失败')
            return
          }
        } catch {
          return
        }
      }
    },
    [refreshFrameImages, refreshKeyframeCandidates],
  )
```

- [ ] **Step 6: 渲染弹窗**

在文件里其它 `<Modal` 渲染附近（例如紧邻视频提示词预览弹窗之后）新增：

```tsx
      <ShotKeyframeGenerateModal
        open={keyframeModalOpen}
        frameType={keyframeModalFrameType}
        frameLabel={keyframeModalFrameType === 'first' ? '首帧' : keyframeModalFrameType === 'last' ? '尾帧' : '关键帧'}
        loading={false}
        submitting={keyframeModalSubmitting}
        prompt={keyframeModalPrompt}
        onPromptChange={setKeyframeModalPrompt}
        quoteText={
          keyframeImageQuote.quote
            ? `预计消耗 ${keyframeImageQuote.quote.points} 积分`
            : keyframeImageQuote.loading
              ? '积分试算中…'
              : null
        }
        referenceOptions={keyframeReferenceOptions}
        selectedFileIds={keyframeModalSelectedFileIds}
        onChangeSelectedFileIds={setKeyframeModalSelectedFileIds}
        onClose={() => setKeyframeModalOpen(false)}
        onSubmit={() => void submitKeyframeGeneration()}
      />
```

Run: `cd front/src && grep -n "points\b" services/generated/models/PointsQuoteResponse.ts` 确认积分字段实际名称（可能是 `points_cost` 或 `total_points` 而非 `points`），据实调整 `quoteText` 表达式。

- [ ] **Step 7: 类型检查**

Run: `cd front && pnpm exec tsc --noEmit`
Expected: 无报错

- [ ] **Step 8: 浏览器手动验证**

打开一个已关联若干角色/场景/道具的镜头，进入"生成视频"步骤，参考模式选"首帧参考"，点击"首帧"卡片的"生成"按钮：确认弹窗打开，参考图区域默认勾选了该镜头已关联的全部资产，取消勾选一项后已选顺序列表同步减少，尝试上移/下移调整顺序。填写提示词后点击"提交生成"，确认弹窗关闭且几秒/几十秒后候选缩略图区域出现新图片（可手动刷新页面验证轮询结果落库）。点击候选图片的"使用"，确认该图片被标记为"使用中"，且 `reference_frames_ready` 诊断项（打开"诊断"抽屉查看）从"未通过"变为"通过"。

- [ ] **Step 9: Commit**

```bash
git add front/src/pages/aiStudio/shots/components/ShotKeyframeGenerateModal.tsx front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx
git commit -m "feat: 关键帧生成弹窗支持自动+手动参考图选择"
```

---

### Task 6: `reference_mode` 接入单镜头生成/诊断链路

**Files:**
- Modify: `front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx:945,952,1830,1895`（仅单镜头专属链路，不改批量/右键共用的 `runDiagnosticsForShots`、`loadShotGenerationContext`、`generateVideosForShots`）

- [ ] **Step 1: 首帧准备度自动检查改为使用 `videoReferenceMode`**

找到（约 932-960 行）：

```tsx
  useEffect(() => {
    if (!shotId || !preparationState?.ready_for_generation) {
      firstFrameReadinessRequestSeqRef.current += 1
      setFirstFrameReadiness(null)
      setFirstFrameReadinessLoading(false)
      return
    }
    const requestShotId = shotId
    const requestSeq = ++firstFrameReadinessRequestSeqRef.current
    setFirstFrameReadinessLoading(true)
    setFirstFrameReadiness(null)
    void (async () => {
      try {
        const res = await StudioShotsService.getShotVideoReadinessApiApiV1StudioShotsShotIdVideoReadinessGet({
          shotId: requestShotId,
          referenceMode: 'first',
        })
        if (requestSeq !== firstFrameReadinessRequestSeqRef.current || currentShotIdRef.current !== requestShotId) return
        setFirstFrameReadiness(res.data ?? null)
      } catch {
        if (requestSeq !== firstFrameReadinessRequestSeqRef.current || currentShotIdRef.current !== requestShotId) return
        setFirstFrameReadiness(null)
      } finally {
        if (requestSeq === firstFrameReadinessRequestSeqRef.current && currentShotIdRef.current === requestShotId) {
          setFirstFrameReadinessLoading(false)
        }
      }
    })()
  }, [preparationState?.ready_for_generation, shotId])
```

改为：

```tsx
  useEffect(() => {
    if (!shotId || !preparationState?.ready_for_generation) {
      firstFrameReadinessRequestSeqRef.current += 1
      setFirstFrameReadiness(null)
      setFirstFrameReadinessLoading(false)
      return
    }
    const requestShotId = shotId
    const requestSeq = ++firstFrameReadinessRequestSeqRef.current
    setFirstFrameReadinessLoading(true)
    setFirstFrameReadiness(null)
    void (async () => {
      try {
        const res = await StudioShotsService.getShotVideoReadinessApiApiV1StudioShotsShotIdVideoReadinessGet({
          shotId: requestShotId,
          referenceMode: videoReferenceMode,
        })
        if (requestSeq !== firstFrameReadinessRequestSeqRef.current || currentShotIdRef.current !== requestShotId) return
        setFirstFrameReadiness(res.data ?? null)
      } catch {
        if (requestSeq !== firstFrameReadinessRequestSeqRef.current || currentShotIdRef.current !== requestShotId) return
        setFirstFrameReadiness(null)
      } finally {
        if (requestSeq === firstFrameReadinessRequestSeqRef.current && currentShotIdRef.current === requestShotId) {
          setFirstFrameReadinessLoading(false)
        }
      }
    })()
  }, [preparationState?.ready_for_generation, shotId, videoReferenceMode])
```

（状态变量名 `firstFrameReadiness` 保留不改名，避免连锁改动无关代码；语义上它现在表示"当前选中参考模式下的准备度"。）

- [ ] **Step 2: 单镜头"诊断"按钮改为使用 `videoReferenceMode`**

找到（约 1940-1965 行）`openVideoDiagnostics` 内的：

```tsx
      const res = await StudioShotsService.getShotVideoReadinessApiApiV1StudioShotsShotIdVideoReadinessGet({
        shotId: requestShotId,
        referenceMode: 'first',
      })
```

改为：

```tsx
      const res = await StudioShotsService.getShotVideoReadinessApiApiV1StudioShotsShotIdVideoReadinessGet({
        shotId: requestShotId,
        referenceMode: videoReferenceMode,
      })
```

并把 `openVideoDiagnostics` 的依赖数组从 `[shotId]` 改为 `[shotId, videoReferenceMode]`。

**注意**：不要修改 `runDiagnosticsForShots`（约 1971-2018 行）和 `loadShotGenerationContext`（约 2024-2036 行）里的 `referenceMode: 'first'`——这两个函数被批量诊断/批量生成/右键单条生成共用，本次改造范围只覆盖"生成视频"步骤自己的专属入口，维持这两处不变。

- [ ] **Step 3: 单镜头提示词预览改为使用 `videoReferenceMode`**

找到 `openVideoPromptPreview` 内提交预览请求处（约 1826-1834 行）：

```tsx
      const res = await FilmService.previewVideoGenerationPromptApiV1FilmTasksVideoPreviewPromptPost({
        requestBody: {
          shot_id: requestShotId,
          reference_mode: 'first',
          prompt: null,
          images: [],
          ratio: resolvedVideoRatio,
        },
      })
```

改为：

```tsx
      const res = await FilmService.previewVideoGenerationPromptApiV1FilmTasksVideoPreviewPromptPost({
        requestBody: {
          shot_id: requestShotId,
          reference_mode: videoReferenceMode,
          prompt: null,
          images: [],
          ratio: resolvedVideoRatio,
        },
      })
```

并把 `openVideoPromptPreview` 的依赖数组补充 `videoReferenceMode`（同时把内部判断 `firstFrameReadiness?.ready !== true` 的提示文案 `'当前镜头首帧模式还未就绪，请先查看诊断'` 改为更通用的 `'当前参考模式所需的参考帧还未就绪，请先在下方关键帧卡片生成或查看诊断'`，因为现在不一定是首帧模式）。

- [ ] **Step 4: 单镜头视频生成提交改为使用 `videoReferenceMode`**

找到 `submitVideoGeneration` 内（约 1891-1902 行）：

```tsx
      const created = await FilmService.createVideoGenerationTaskApiV1FilmTasksVideoPost({
        requestBody: {
          shot_id: shotId,
          model_id: selectedVideoModelId,
          reference_mode: 'first',
          prompt,
          images: [],
          ratio: resolvedVideoRatio,
          resolution: videoResolution,
          quote_token: videoQuote.quoteToken,
        },
      })
```

改为：

```tsx
      const created = await FilmService.createVideoGenerationTaskApiV1FilmTasksVideoPost({
        requestBody: {
          shot_id: shotId,
          model_id: selectedVideoModelId,
          reference_mode: videoReferenceMode,
          prompt,
          images: [],
          ratio: resolvedVideoRatio,
          resolution: videoResolution,
          quote_token: videoQuote.quoteToken,
        },
      })
```

并在 `submitVideoGeneration` 的依赖数组里补充 `videoReferenceMode`。

- [ ] **Step 5: 全文搜索确认改动范围正确**

Run: `cd front/src && grep -n "reference_mode: 'first'\|referenceMode: 'first'" pages/aiStudio/shots/ChapterShotEditPage.tsx`
Expected: 只剩下 `runDiagnosticsForShots`、`loadShotGenerationContext`、`generateVideosForShots` 内的出现（批量/右键共用逻辑，本任务不改），单镜头"生成视频"步骤自己的 4 处已全部替换为 `videoReferenceMode`。

- [ ] **Step 6: 类型检查**

Run: `cd front && pnpm exec tsc --noEmit`
Expected: 无报错

- [ ] **Step 7: 浏览器手动验证**

打开一个已经设置好首帧图片的镜头，进入"生成视频"步骤，确认参考模式为"首帧参考"时诊断项通过、可以点击"生成视频"进入提示词预览弹窗。切换参考模式为"纯文字"，确认诊断项里 `reference_frames_ready` 变为"当前参考模式不需要参考帧"、通过状态；提交后确认视频生成请求（可在浏览器 Network 面板确认）里的 `reference_mode` 字段值等于当前选中的模式。切换到"首尾帧"且尾帧未设置时，确认"生成视频"按钮被禁用且 Tooltip 提示缺少尾帧。

- [ ] **Step 8: Commit**

```bash
git add front/src/pages/aiStudio/shots/ChapterShotEditPage.tsx
git commit -m "feat: 单镜头生成/诊断链路接入可选参考模式"
```

---

## 全部任务完成后的收尾检查

- [ ] 再次运行 `cd front && pnpm exec tsc --noEmit`，确认全部改动累计无类型错误
- [ ] 对照 `docs/superpowers/specs/2026-07-04-shot-detail-step2-keyframe-ux-design.md` 的"测试与验证"一节逐条复查
- [ ] 更新 `site/content/docs/architecture/generation-workspace.md`，补充"关键帧与参考图面板已迁移到镜头详情页'生成视频'步骤，`reference_mode` 目前为手动 Select（技术 key），模型能力过滤仍是后续独立工作"
- [ ] 走 `superpowers:finishing-a-development-branch` 决定合并/PR 方式
