import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Badge, Button, Card, Checkbox, Divider, Dropdown, Empty, Form, Input, Layout, List, Modal, Popconfirm, Segmented, Spin, Tabs, Tooltip, Typography, message } from 'antd'
import type { MenuProps } from 'antd'
import { ArrowLeftOutlined, CloseCircleOutlined, DeleteOutlined, DownloadOutlined, MoreOutlined, PlusOutlined, ReloadOutlined, StopOutlined, ThunderboltOutlined, ToolOutlined, UndoOutlined } from '@ant-design/icons'
import type {
  EntityNameExistenceItem,
  ModelRead,
  ProviderRead,
  ShotAssetOverviewItem,
  ShotAssetsOverviewRead,
  ShotDetailRead,
  ShotDialogLineRead,
  ShotDialogLineUpdate,
  ShotExtractionSummaryRead,
  ShotExtractedDialogueCandidateRead,
  ShotFrameImageRead,
  ShotFrameType,
  ShotLinkedAssetItem,
  ShotPreparationStateRead,
  ShotRead,
  ShotVideoReadinessRead,
  VideoPromptPreviewRequest,
} from '../../../services/generated'
import {
  FilmService,
  LlmService,
  PointsService,
  ScriptProcessingService,
  StudioChaptersService,
  StudioEntitiesService,
  StudioImageTasksService,
  StudioProjectsService,
  StudioShotDetailsService,
  StudioShotDialogLinesService,
  StudioShotFrameImagesService,
  StudioShotsService,
} from '../../../services/generated'
import { executeAsyncTaskCreate, executeTaskCancel, notifyExistingTask } from '../components/taskActionHelpers'
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  getChapterShotDetailPath,
  getChapterShotEditPath,
  getChapterShotsPath,
  type ShotDetailTabKey,
} from '../project/ProjectWorkbench/routes'
import { DisplayImageCard } from '../assets/components/DisplayImageCard'
import { AssetPickerDrawer } from './components/AssetPickerDrawer'
import { ChapterShotAssetConfirmation } from './components/ChapterShotAssetConfirmation'
import { ChapterShotBasicInfoSection } from './components/ChapterShotBasicInfoSection'
import { ChapterShotDialogueConfirmation } from './components/ChapterShotDialogueConfirmation'
import { ChapterShotPreparationGuide } from './components/ChapterShotPreparationGuide'
import { ShotVideoGenerationTab } from './components/ShotVideoGenerationTab'
import { ShotVideoResultsTab } from './components/ShotVideoResultsTab'
import { VideoDiagnosticsDrawer } from './components/VideoDiagnosticsDrawer'
import { useRelationTaskNotification } from '../components/taskNotificationHelpers'
import { useTaskPageContext } from '../components/taskPageContext'
import { createTaskSettledReloader } from '../components/taskResultHelpers'
import { TASK_COPY } from '../components/taskCopy'
import { usePointsQuote } from '../../../hooks/usePointsQuote'
import { PointsCostButton } from '../../../components/points/PointsCostButton'
import { makePointsAwareGetErrorMessage } from '../../../components/points/pointsTaskError'
import { ExtractionConfirmModal } from './components/ExtractionConfirmModal'
import {
  type RelationTaskState,
  SCRIPT_EXTRACTION_RELATION_TYPE,
  useCancelableRelationTask,
} from '../project/ProjectWorkbench/chapterDivisionTasks'
import { StudioEntitiesApi } from '../../../services/studioEntities'
import { buildFileDownloadUrl, resolveAssetUrl } from '../assets/utils'
import { generateUUID } from '../../../utils'
import type { ShotKeyframeCandidate } from './components/ShotKeyframeCard'
import { ShotKeyframeGenerateModal, type KeyframeReferenceOption } from './components/ShotKeyframeGenerateModal'
import { listTaskLinksNormalized } from '../../../services/filmTaskLinks'

const { Header, Content } = Layout
const { TextArea } = Input
const chapterDivisionTaskCopy = TASK_COPY.chapterDivision
const extractTaskCopy = TASK_COPY.scriptExtract

type AssetKind = 'scene' | 'actor' | 'prop' | 'costume'
type VideoModelOption = ModelRead & {
  provider_name: string
}
type NamedDraft = { name: string; thumbnail?: string | null; id?: string | null; file_id?: string | null; description?: string | null }
type AssetVM = NamedDraft & {
  kind: AssetKind
  /**
   * linked     = 已关联（无论是否有图片）
   * generating = 已关联，图片生成任务进行中
   * new        = 待确认候选
   */
  status: 'linked' | 'generating' | 'new'
  candidateId?: number
  candidateStatus?: ShotAssetOverviewItem['candidate_status']
}
type ShotListFilter = 'all' | 'not_extracted' | 'pending'
type VideoRatio = NonNullable<VideoPromptPreviewRequest['ratio']>

type ShotAssetCreatedAndLinkedMessage = {
  type: 'studio-shot-asset-created-and-linked'
  projectId?: string
  chapterId?: string
  shotId?: string
  assetId?: string | null
  assetName?: string
}

const SHOT_DETAIL_TAB_KEYS: readonly ShotDetailTabKey[] = ['basic', 'confirm', 'generate', 'results']
const VIDEO_GENERATION_RELATION_TYPE = 'video'
const SUPPORTED_VIDEO_RATIOS = new Set<VideoRatio>(['16:9', '4:3', '1:1', '3:4', '9:16', '21:9'])

function isShotDetailTabKey(value: string | null): value is ShotDetailTabKey {
  return !!value && SHOT_DETAIL_TAB_KEYS.includes(value as ShotDetailTabKey)
}

/** 将任意字符串收窄为视频生成接口允许的 ratio；非法值返回 null。 */
function toSupportedVideoRatio(value: string | null | undefined): VideoRatio | null {
  const trimmed = String(value ?? '').trim()
  return SUPPORTED_VIDEO_RATIOS.has(trimmed as VideoRatio) ? (trimmed as VideoRatio) : null
}

/**
 * 按镜头覆盖、项目真实默认值的顺序解析视频比例。
 * 只返回 OpenAPI 允许的 ratio union，避免预览和提交 payload 与页面展示不一致。
 */
function resolveVideoRatio(
  shotDetail: ShotDetailRead | null,
  projectDefaultVideoRatio: string,
): VideoRatio | null {
  return (
    toSupportedVideoRatio(shotDetail?.override_video_ratio) ??
    toSupportedVideoRatio(projectDefaultVideoRatio)
  )
}

/**
 * 生成左侧右键与批量操作的展示标题。
 * 单条显示镜头编号，多条显示数量，便于确认本次动作作用范围。
 */
function buildShotActionTitle(targetShots: ShotRead[]): string {
  if (targetShots.length === 1) {
    return `镜头 #${targetShots[0].index}`
  }
  return `已选 ${targetShots.length} 条镜头`
}

const DEFAULT_EXTRACTION_SUMMARY: ShotExtractionSummaryRead = {
  state: 'not_extracted',
  has_extracted: false,
  last_extracted_at: null,
  asset_candidate_total: 0,
  dialogue_candidate_total: 0,
  pending_asset_count: 0,
  pending_dialogue_count: 0,
}

function getExtractionStateMeta(
  shot: ShotRead | null,
  pendingConfirmCount: number,
): {
  tone: 'green' | 'gold' | 'blue'
  title: string
  description: string
} {
  const state = shot?.extraction?.state
  if (state === 'skipped') {
    return {
      tone: 'green',
      title: '当前镜头已标记为无需提取',
      description: '系统会直接按“提取确认已完成”处理。如需恢复正式提取流程，请使用上方维护动作。',
    }
  }
  if (state === 'not_extracted') {
    return {
      tone: 'gold',
      title: '当前镜头还没有执行过信息提取',
      description: '分镜提取主流程会自动准备资产和对白候选；如需修复单条镜头，可在这里重新提取。',
    }
  }
  if (state === 'extracted_empty') {
    return {
      tone: 'blue',
      title: '当前镜头已完成提取，但没有识别到候选',
      description: '这说明系统已经跑过提取流程，只是当前没有识别到资产或对白候选。',
    }
  }
  if (state === 'extracted_resolved') {
    return {
      tone: 'green',
      title: '当前镜头的提取结果已确认完成',
      description: '资产和对白候选都已处理完成，可以继续进入后续生成流程。',
    }
  }
  return {
    tone: 'gold',
    title: '当前镜头仍有提取结果待确认',
    description: `还有 ${pendingConfirmCount} 项待处理，建议先完成资产和对白确认。`,
  }
}

function getShotExtractionSummary(shot: ShotRead | null | undefined): ShotExtractionSummaryRead {
  return shot?.extraction ?? DEFAULT_EXTRACTION_SUMMARY
}

function isPendingExtractionConfirmation(shot: ShotRead): boolean {
  return getShotExtractionSummary(shot).state === 'extracted_pending'
}

function isActionablePreparationShot(shot: ShotRead): boolean {
  const state = getShotExtractionSummary(shot).state
  return state === 'not_extracted' || state === 'extracted_pending'
}

/**
 * 合并"基础信息完整性"与"资产/对白候选处理进度"两件事，输出分镜列表唯一的准备阶段徽标。
 * 待处理数量 = 待确认资产候选数 + 待确认对白候选数，取自 ShotExtractionSummaryRead 的
 * pending_asset_count / pending_dialogue_count 字段（已确认这是生成客户端里的实际字段名）。
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
  const pendingCount = (extraction.pending_asset_count ?? 0) + (extraction.pending_dialogue_count ?? 0)
  if (extraction.state === 'not_extracted') {
    return { text: '待执行提取', tone: 'gold' }
  }
  if (pendingCount > 0) {
    return { text: `待关联确认 ${pendingCount} 项`, tone: 'gold' }
  }
  return { text: '准备完成', tone: 'green' }
}

function overviewTypeToAssetKind(kind: ShotAssetOverviewItem['type']): AssetKind {
  return kind === 'character' ? 'actor' : kind
}

export function ChapterShotEditPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { projectId, chapterId, shotId } = useParams<{
    projectId: string
    chapterId: string
    shotId: string
  }>()

  const [chapterTitle, setChapterTitle] = useState('')
  const [chapterIndex, setChapterIndex] = useState<number | null>(null)
  const [chapterRawText, setChapterRawText] = useState('')
  const [chapterCondensedText, setChapterCondensedText] = useState('')
  const [projectVisualStyle, setProjectVisualStyle] = useState<string>('现实')
  const [projectStyle, setProjectStyle] = useState<string>('真人都市')
  const [projectDefaultVideoRatio, setProjectDefaultVideoRatio] = useState<string>('')
  const [shots, setShots] = useState<ShotRead[]>([])
  const [shot, setShot] = useState<ShotRead | null>(null)
  const [title, setTitle] = useState('')
  const [scriptExcerpt, setScriptExcerpt] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [semanticSaving, setSemanticSaving] = useState(false)
  const [preparationState, setPreparationState] = useState<ShotPreparationStateRead | null>(null)
  const [shotDetail, setShotDetail] = useState<ShotDetailRead | null>(null)
  const [shotAssetsOverview, setShotAssetsOverview] = useState<ShotAssetsOverviewRead | null>(null)
  const preparationStateRequestSeqRef = useRef(0)
  const [extractingAssets, setExtractingAssets] = useState(false)
  const [skipExtractionUpdating, setSkipExtractionUpdating] = useState(false)
  const [batchGenerating, setBatchGenerating] = useState(false)
  const [batchDownloading, setBatchDownloading] = useState(false)
  const [batchDeleting, setBatchDeleting] = useState(false)
  const [chapterDividing, setChapterDividing] = useState(false)
  const [chapterDivideConfirmOpen, setChapterDivideConfirmOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [createSubmitting, setCreateSubmitting] = useState(false)
  const [createForm] = Form.useForm<{ title: string; script_excerpt?: string }>()
  const [insertMode, setInsertMode] = useState<{ direction: 'before' | 'after'; refShot: ShotRead } | null>(null)
  const [insertSubmitting, setInsertSubmitting] = useState(false)
  const [insertForm] = Form.useForm<{ title: string; script_excerpt?: string }>()
  const extractInFlightRef = useRef(false)
  const [selectedShotIds, setSelectedShotIds] = useState<string[]>([])
  const pendingExternalAssetCreateRef = useRef(false)
  const hasHydratedPageRef = useRef(false)

  // 积分试算：单条与批量提取均调用同一个 script_extract 接口，共享同一份 quote_token。
  const extractQuote = usePointsQuote({ businessType: 'script_extract', category: 'text', modelId: null, enabled: !!projectId && !!chapterId })
  const divideQuote = usePointsQuote({ businessType: 'script_divide', category: 'text', modelId: null, enabled: !!chapterId })
  // 图片生成单价，用于提取确认弹窗内展示"每张资产图"参考积分。
  const imageQuote = usePointsQuote({ businessType: 'image_generation', category: 'image', modelId: null, enabled: !!projectId && !!chapterId })
  // 提取确认弹窗：'single' = 当前镜头，'batch' = 批量多选。
  const [extractConfirmOpen, setExtractConfirmOpen] = useState(false)
  const [extractConfirmTarget, setExtractConfirmTarget] = useState<'single' | 'batch'>('single')

  // 资产替换 Drawer 状态：选中的待替换资产、抽屉开关、提交中标记
  const [replaceDrawerOpen, setReplaceDrawerOpen] = useState(false)
  const [replaceDrawerAsset, setReplaceDrawerAsset] = useState<AssetVM | null>(null)
  const [replaceDrawerLoading, setReplaceDrawerLoading] = useState(false)

  // 添加关联资产 Drawer 状态
  const [addDrawerOpen, setAddDrawerOpen] = useState(false)
  const [addDrawerKind, setAddDrawerKind] = useState<AssetKind>('scene')
  const [addDrawerLoading, setAddDrawerLoading] = useState(false)

  // 资产解关联（忽略）状态：正在提交中的实体 ID → loading 标记
  const [unlinkingIds, setUnlinkingIds] = useState<Record<string, boolean>>({})

  const [linkingOpen, setLinkingOpen] = useState(false)
  const [linkingLoading, setLinkingLoading] = useState(false)
  const [linkingActionLoading, setLinkingActionLoading] = useState(false)
  const [linkingHint, setLinkingHint] = useState<string>('')
  const [linkingKind, setLinkingKind] = useState<AssetKind>('scene')
  const [linkingName, setLinkingName] = useState<string>('')
  const [linkingThumb, setLinkingThumb] = useState<string | undefined>(undefined)
  const [linkingItem, setLinkingItem] = useState<EntityNameExistenceItem | null>(null)

  const [existenceByKindName, setExistenceByKindName] = useState<Record<AssetKind, Record<string, EntityNameExistenceItem>>>({
    scene: {},
    actor: {},
    prop: {},
    costume: {},
  })
  const existenceInFlightRef = useRef<Record<AssetKind, boolean>>({
    scene: false,
    actor: false,
    prop: false,
    costume: false,
  })

  const [dialogLoading, setDialogLoading] = useState(false)
  const [savedDialogLines, setSavedDialogLines] = useState<ShotDialogLineRead[]>([])
  const [extractedDialogLines, setExtractedDialogLines] = useState<ShotExtractedDialogueCandidateRead[]>([])
  const [dialogDeletingIds, setDialogDeletingIds] = useState<Record<number, boolean>>({})
  const [dialogAddingKeys, setDialogAddingKeys] = useState<Record<string, boolean>>({})
  const [batchDialogAdding, setBatchDialogAdding] = useState(false)
  const [draftDialogueLine, setDraftDialogueLine] = useState<{ speakerName: string; targetName: string; text: string } | null>(null)
  const [draftDialogueSaving, setDraftDialogueSaving] = useState(false)
  const [candidateActionIds, setCandidateActionIds] = useState<Record<number, boolean>>({})
  const [editorTabKey, setEditorTabKey] = useState<ShotDetailTabKey>('basic')
  const [videoDiagnosticsOpen, setVideoDiagnosticsOpen] = useState(false)
  const [videoDiagnosticsLoading, setVideoDiagnosticsLoading] = useState(false)
  const [videoDiagnosticsTitle, setVideoDiagnosticsTitle] = useState('视频生成诊断')
  const [videoDiagnosticsReadiness, setVideoDiagnosticsReadiness] = useState<ShotVideoReadinessRead | null>(null)
  const [videoDiagnosticsBatchItems, setVideoDiagnosticsBatchItems] = useState<Array<{
    title: string
    readiness: ShotVideoReadinessRead | null
    error?: string
  }> | undefined>(undefined)
  const [firstFrameReadiness, setFirstFrameReadiness] = useState<ShotVideoReadinessRead | null>(null)
  const [firstFrameReadinessLoading, setFirstFrameReadinessLoading] = useState(false)
  // 参考模式：决定生成视频时需要哪些帧类型（首帧/尾帧/关键帧）参与，骨架阶段先本地维护、不联动生成请求体。
  const [videoReferenceMode, setVideoReferenceMode] = useState<'first' | 'last' | 'key' | 'first_last' | 'first_last_key' | 'text_only'>('first')
  // 当前镜头细节下的分镜帧图片槽位（首帧/尾帧/关键帧各一条，含当前使用中的 file_id）。
  const [frameImages, setFrameImages] = useState<ShotFrameImageRead[]>([])
  // 各帧类型的历史候选缩略图（来自任务关联记录），供关键帧卡片展示与切换使用。
  const [keyframeCandidatesByType, setKeyframeCandidatesByType] = useState<Record<ShotFrameType, ShotKeyframeCandidate[]>>({
    first: [],
    last: [],
    key: [],
  })
  const [keyframeApplyingFileId, setKeyframeApplyingFileId] = useState<string | null>(null)
  // 关键帧生成弹窗状态：打开的帧类型、编辑中的提示词、已选参考图 file_id 顺序列表、提交中标记。
  const [keyframeModalOpen, setKeyframeModalOpen] = useState(false)
  const [keyframeModalFrameType, setKeyframeModalFrameType] = useState<ShotFrameType | null>(null)
  const [keyframeModalPrompt, setKeyframeModalPrompt] = useState('')
  const [keyframeModalSelectedFileIds, setKeyframeModalSelectedFileIds] = useState<string[]>([])
  const [keyframeModalSubmitting, setKeyframeModalSubmitting] = useState(false)
  // 关键帧生成的积分试算：独立于资产图片生成的 imageQuote 实例，因为需要额外传 resolutionProfile
  // 才能让 quote_token 的 params_hash 与创建任务时提交的 resolution_profile 对齐。
  const keyframeImageQuote = usePointsQuote({
    businessType: 'image_generation',
    category: 'image',
    modelId: null,
    resolutionProfile: 'standard',
    enabled: keyframeModalOpen,
  })
  const [videoModels, setVideoModels] = useState<VideoModelOption[]>([])
  const [selectedVideoModelId, setSelectedVideoModelId] = useState<string | null>(null)
  const [videoModelsLoading, setVideoModelsLoading] = useState(false)
  const [videoResolution, setVideoResolution] = useState<'720p' | '1080p'>('720p')
  const [videoPromptPreviewOpen, setVideoPromptPreviewOpen] = useState(false)
  const [videoPromptPreviewLoading, setVideoPromptPreviewLoading] = useState(false)
  const [videoPromptPreviewSubmitting, setVideoPromptPreviewSubmitting] = useState(false)
  const [videoPromptPreviewDraft, setVideoPromptPreviewDraft] = useState('')
  const [videoPromptPreviewShotId, setVideoPromptPreviewShotId] = useState<string | null>(null)
  // 视频生成试算绑定模型、镜头时长与清晰度；提示词预览弹窗提交时复用同一 quote_token。
  const videoQuote = usePointsQuote({
    businessType: 'video_generation',
    category: 'video',
    modelId: selectedVideoModelId,
    durationSeconds: shotDetail?.duration ?? null,
    resolution: videoResolution,
    enabled: !!selectedVideoModelId && !!shotDetail?.duration,
  })
  const [shotListFilter, setShotListFilter] = useState<ShotListFilter>('all')
  const dialogDebounceTimersRef = useRef<Map<number, number>>(new Map())
  const tabAutoInitShotIdRef = useRef<string | null>(null)
  const editorTabMemoryRef = useRef<Record<string, ShotDetailTabKey>>({})
  const videoDiagnosticsRequestSeqRef = useRef(0)
  const firstFrameReadinessRequestSeqRef = useRef(0)
  const videoPromptPreviewRequestSeqRef = useRef(0)
  const currentShotIdRef = useRef<string | null>(shotId ?? null)
  const urlTabParam = searchParams.get('tab')
  const explicitUrlTabKey = isShotDetailTabKey(urlTabParam) ? urlTabParam : null
  currentShotIdRef.current = shotId ?? null

  const shotsSorted = useMemo(
    () => [...shots].sort((a, b) => a.index - b.index),
    [shots],
  )
  const selectedShots = useMemo(
    () => shotsSorted.filter((item) => selectedShotIds.includes(item.id)),
    [selectedShotIds, shotsSorted],
  )
  const hasSelection = selectedShotIds.length > 0
  const shotListFilterCounts = useMemo(
    () => ({
      all: shotsSorted.length,
      not_extracted: shotsSorted.filter((item) => getShotExtractionSummary(item).state === 'not_extracted').length,
      pending: shotsSorted.filter((item) => isPendingExtractionConfirmation(item)).length,
    }),
    [shotsSorted],
  )
  const shotListFilterOptions = useMemo<Array<{ label: string; value: ShotListFilter }>>(
    () => [
      { label: `全部 ${shotListFilterCounts.all}`, value: 'all' },
      { label: `未提取 ${shotListFilterCounts.not_extracted}`, value: 'not_extracted' },
      { label: `待确认 ${shotListFilterCounts.pending}`, value: 'pending' },
    ],
    [shotListFilterCounts.all, shotListFilterCounts.not_extracted, shotListFilterCounts.pending],
  )
  const filteredShots = useMemo(() => {
    if (shotListFilter === 'all') return shotsSorted
    if (shotListFilter === 'not_extracted') {
      return shotsSorted.filter((item) => getShotExtractionSummary(item).state === 'not_extracted')
    }
    return shotsSorted.filter((item) => isPendingExtractionConfirmation(item))
  }, [shotListFilter, shotsSorted])
  const filteredShotIds = useMemo(() => filteredShots.map((item) => item.id), [filteredShots])
  const allFilteredSelected = filteredShotIds.length > 0 && filteredShotIds.every((id) => selectedShotIds.includes(id))
  const partiallyFilteredSelected = filteredShotIds.some((id) => selectedShotIds.includes(id)) && !allFilteredSelected
  useEffect(() => {
    const existingIds = new Set(shotsSorted.map((item) => item.id))
    setSelectedShotIds((prev) => {
      const next = prev.filter((id) => existingIds.has(id))
      return next.length === prev.length ? prev : next
    })
  }, [shotsSorted])

  const unionAssets = useMemo(() => {
    const groups: Record<AssetKind, AssetVM[]> = {
      scene: [],
      actor: [],
      prop: [],
      costume: [],
    }
    for (const item of shotAssetsOverview?.items ?? []) {
      if (item.candidate_status === 'ignored') continue
      const kind = overviewTypeToAssetKind(item.type)
      groups[kind].push({
        kind,
        name: item.name,
        thumbnail: item.thumbnail ?? null,
        id: item.linked_entity_id ?? null,
        file_id: item.file_id ?? null,
        description: item.description ?? null,
        status: item.is_generating
          ? 'generating'
          : item.is_linked
            ? 'linked'
            : 'new',
        candidateId: item.candidate_id ?? undefined,
        candidateStatus: item.candidate_status ?? undefined,
      })
    }
    return groups
  }, [shotAssetsOverview])

  // 关键帧生成弹窗的参考图候选：取当前镜头资产总览里已关联（含生成中）且有 file_id 的条目，
  // 按资产种类摊平成 ShotLinkedAssetItem 结构，供弹窗默认全选与手动增减。
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

  const [expandedKinds, setExpandedKinds] = useState<Record<AssetKind, boolean>>({
    scene: false,
    actor: false,
    prop: false,
    costume: false,
  })

  const toggleExpanded = (kind: AssetKind) => {
    setExpandedKinds((prev) => ({ ...prev, [kind]: !prev[kind] }))
  }

  const loadPage = useCallback(async () => {
    if (!chapterId || !shotId || !projectId) return
    if (!hasHydratedPageRef.current) {
      setLoading(true)
    }
    setDialogLoading(true)
    try {
      const [projectRes, chRes, listRes, preparationRes, detailRes] = await Promise.all([
        StudioProjectsService.getProjectApiV1StudioProjectsProjectIdGet({ projectId }),
        StudioChaptersService.getChapterApiV1StudioChaptersChapterIdGet({ chapterId }),
        StudioShotsService.listShotsApiV1StudioShotsGet({
          chapterId,
          page: 1,
          pageSize: 100,
          order: 'index',
          isDesc: false,
        }),
        StudioShotsService.getShotPreparationStateApiApiV1StudioShotsShotIdPreparationStateGet({ shotId }),
        StudioShotDetailsService.getShotDetailApiV1StudioShotDetailsShotIdGet({ shotId }),
      ])
      const nextVisualStyle = projectRes.data?.visual_style
      const nextStyle = projectRes.data?.style
      const nextDefaultVideoRatio = projectRes.data?.default_video_ratio
      if (typeof nextVisualStyle === 'string' && nextVisualStyle.trim()) {
        setProjectVisualStyle(nextVisualStyle)
      }
      if (typeof nextStyle === 'string' && nextStyle.trim()) {
        setProjectStyle(nextStyle)
      }
      setProjectDefaultVideoRatio(typeof nextDefaultVideoRatio === 'string' ? nextDefaultVideoRatio : '')

      const c = chRes.data
      setChapterTitle(c?.title ?? '')
      setChapterIndex(typeof c?.index === 'number' ? c.index : null)
      setChapterRawText(c?.raw_text?.trim?.() ? c.raw_text.trim() : '')
      setChapterCondensedText(c?.condensed_text?.trim?.() ? c.condensed_text.trim() : '')

      const items = listRes.data?.items ?? []
      const preparationState = preparationRes.data ?? null
      const detail = detailRes.data ?? null
      const s = preparationState?.shot ?? null

      if (!s) {
        message.error('分镜不存在')
        navigate(getChapterShotsPath(projectId, chapterId), { replace: true })
        return
      }
      if (s.chapter_id !== chapterId) {
        message.error('分镜不属于当前章节')
        navigate(getChapterShotsPath(projectId, chapterId), { replace: true })
        return
      }

      setPreparationState(preparationState)
      setShotDetail(detail)
      setShot(s)
      setTitle(s.title ?? '')
      setScriptExcerpt(s.script_excerpt ?? '')
      setShots(items.map((item) => (item.id === s.id ? s : item)))
      setShotAssetsOverview(preparationState?.assets_overview ?? null)
      setSavedDialogLines(preparationState?.saved_dialogue_lines ?? [])
      setExtractedDialogLines(
        (preparationState?.dialogue_candidates ?? []).filter((item) => item.candidate_status === 'pending'),
      )
      hasHydratedPageRef.current = true
    } catch {
      message.error('加载失败')
      navigate(getChapterShotsPath(projectId, chapterId), { replace: true })
    } finally {
      setDialogLoading(false)
      setLoading(false)
    }
  }, [chapterId, navigate, projectId, shotId])

  useEffect(() => {
    let active = true
    setVideoModelsLoading(true)
    void (async () => {
      try {
        const [modelsRes, providersRes] = await Promise.all([
          LlmService.listModelsApiV1LlmModelsGet({
            category: 'video',
            order: 'name',
            isDesc: false,
            page: 1,
            pageSize: 100,
          }),
          LlmService.listProvidersApiV1LlmProvidersGet({
            order: 'name',
            isDesc: false,
            page: 1,
            pageSize: 100,
          }),
        ])
        if (!active) return
        const providers = (providersRes.data?.items ?? []) as ProviderRead[]
        const activeProviderIds = new Set(
          providers
            .filter((provider) => provider.status !== 'disabled')
            .map((provider) => provider.id),
        )
        const providerNameById = new Map(providers.map((provider) => [provider.id, provider.name]))
        const items = ((modelsRes.data?.items ?? []) as ModelRead[])
          .filter((model) => model.category === 'video')
          // 视频模型必须挂在明确可用的供应商下；供应商列表为空时不放行，避免误选已禁用供应商的模型。
          .filter((model) => activeProviderIds.has(model.provider_id))
          .map((model) => ({
            ...model,
            provider_name: providerNameById.get(model.provider_id) ?? model.provider_id,
          }))
        setVideoModels(items)
        setSelectedVideoModelId((prev) => {
          if (prev && items.some((item) => item.id === prev)) return prev
          return items[0]?.id ?? null
        })
      } catch {
        if (active) {
          setVideoModels([])
          setSelectedVideoModelId(null)
        }
      } finally {
        if (active) {
          setVideoModelsLoading(false)
        }
      }
    })()
    return () => {
      active = false
    }
  }, [])

  const clearDialogDebounceTimers = useCallback(() => {
    for (const [, timer] of dialogDebounceTimersRef.current.entries()) {
      window.clearTimeout(timer)
    }
    dialogDebounceTimersRef.current.clear()
  }, [])

  const applyPreparationState = useCallback(
    (state: ShotPreparationStateRead, options?: { syncBasicInfo?: boolean }) => {
      setPreparationState(state)
      const nextShot = state.shot
      setShot(nextShot)
      setShots((prev) => prev.map((item) => (item.id === nextShot.id ? nextShot : item)))
      setShotAssetsOverview(state.assets_overview ?? null)
      setSavedDialogLines(state.saved_dialogue_lines ?? [])
      setExtractedDialogLines((state.dialogue_candidates ?? []).filter((item) => item.candidate_status === 'pending'))
      if (options?.syncBasicInfo) {
        setTitle(nextShot.title ?? '')
        setScriptExcerpt(nextShot.script_excerpt ?? '')
      }
    },
    [],
  )

  const loadPreparationState = useCallback(
    async (options?: { syncBasicInfo?: boolean; silent?: boolean }) => {
      if (!shotId) return null
      const reqSeq = ++preparationStateRequestSeqRef.current
      setDialogLoading(true)
      try {
        const res = await StudioShotsService.getShotPreparationStateApiApiV1StudioShotsShotIdPreparationStateGet({
          shotId,
        })
        if (reqSeq !== preparationStateRequestSeqRef.current) return null
        const data = res.data ?? null
        if (!data) return null
        applyPreparationState(data, { syncBasicInfo: options?.syncBasicInfo })
        return data
      } catch {
        if (!options?.silent) {
          message.error('准备状态加载失败')
        }
        return null
      } finally {
        if (reqSeq === preparationStateRequestSeqRef.current) {
          setDialogLoading(false)
        }
      }
    },
    [applyPreparationState, shotId],
  )

  const reloadAfterExtractTaskSettled = useCallback(
    createTaskSettledReloader(loadPage),
    [loadPage],
  )
  const reloadAfterChapterDivisionSettled = useCallback(
    createTaskSettledReloader(loadPage),
    [loadPage],
  )
  const reloadAfterVideoGenerationSettled = useCallback(
    createTaskSettledReloader(loadPage),
    [loadPage],
  )
  const { task: chapterDivisionTask, settledTask: chapterDivisionSettledTask, trackTaskData: trackChapterDivisionTaskData } = useCancelableRelationTask({
    enabled: !!chapterId,
    relationType: 'chapter_division',
    relationEntityId: chapterId,
    onTaskSettled: reloadAfterChapterDivisionSettled,
  })
  const { task: extractTask, settledTask: extractSettledTask, trackTaskData: trackExtractTaskData, applyCancelData: applyExtractCancelData } = useCancelableRelationTask({
    enabled: !!chapterId,
    relationType: SCRIPT_EXTRACTION_RELATION_TYPE,
    relationEntityId: chapterId,
    onTaskSettled: reloadAfterExtractTaskSettled,
  })
  const {
    task: videoGenerationRelation,
    settledTask: videoGenerationSettled,
    setTrackedTask: setTrackedVideoGeneration,
    applyCancelData: applyVideoGenerationCancelData,
  } = useCancelableRelationTask({
    enabled: !!shotId,
    relationType: VIDEO_GENERATION_RELATION_TYPE,
    relationEntityId: shotId,
    onTaskSettled: reloadAfterVideoGenerationSettled,
  })
  useTaskPageContext(
    [
      ...(chapterId
        ? [
            {
              relationType: 'chapter_division',
              relationEntityId: chapterId,
            },
          ]
        : []),
      ...(chapterId
        ? [
            {
              relationType: SCRIPT_EXTRACTION_RELATION_TYPE,
              relationEntityId: chapterId,
            },
          ]
        : []),
      ...(shotId
        ? [
            {
              relationType: VIDEO_GENERATION_RELATION_TYPE,
              relationEntityId: shotId,
            },
          ]
        : []),
    ],
  )
  const extractTaskActive = !!extractTask

  const scheduleSaveDialogLine = useCallback(
    (lineId: number, patch: ShotDialogLineUpdate) => {
      const prev = dialogDebounceTimersRef.current.get(lineId)
      if (prev) window.clearTimeout(prev)
      const timer = window.setTimeout(async () => {
        try {
          await StudioShotDialogLinesService.updateShotDialogLineApiV1StudioShotDialogLinesLineIdPatch({
            lineId,
            requestBody: patch,
          })
        } catch {
          message.error('对白保存失败')
        }
      }, 1000)
      dialogDebounceTimersRef.current.set(lineId, timer)
    },
    [],
  )

  const updateSavedDialogText = useCallback(
    (lineId: number, text: string) => {
      setSavedDialogLines((prev) => prev.map((l) => (l.id === lineId ? { ...l, text } : l)))
      scheduleSaveDialogLine(lineId, { text })
    },
    [scheduleSaveDialogLine],
  )

  const deleteSavedDialogLine = useCallback(
    async (lineId: number) => {
      if (dialogDeletingIds[lineId]) return
      const prevTimer = dialogDebounceTimersRef.current.get(lineId)
      if (prevTimer) window.clearTimeout(prevTimer)
      dialogDebounceTimersRef.current.delete(lineId)
      setDialogDeletingIds((m) => ({ ...m, [lineId]: true }))
      try {
        await StudioShotDialogLinesService.deleteShotDialogLineApiV1StudioShotDialogLinesLineIdDelete({ lineId })
        setSavedDialogLines((prev) => prev.filter((l) => l.id !== lineId))
        message.success('已删除')
      } catch {
        message.error('删除失败')
      } finally {
        setDialogDeletingIds((m) => ({ ...m, [lineId]: false }))
      }
    },
    [dialogDeletingIds],
  )

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
   * 失焦时的保存逻辑：只在对白内容非空时才创建持久化记录；内容为空时保持草稿原样（no-op），
   * 不清空草稿——说话人/对象/内容三个输入框都绑定了这个回调，若为空就清空会导致用户
   * 只是切换字段（还没来得及填写对白内容）就把已经填好的说话人/对象丢失。
   * 草稿的丢弃只应该通过"删除"按钮（discardDraftDialogueLine）触发。
   */
  const commitDraftDialogueLine = useCallback(async () => {
    if (!shotId || !draftDialogueLine) return
    const text = draftDialogueLine.text.trim()
    if (!text) return
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
      if (!created) {
        message.error('新增对白失败：接口未返回数据')
        return
      }
      setSavedDialogLines((prev) => [...prev, created])
      message.success('已新增对白')
      setDraftDialogueLine(null)
    } catch {
      message.error('新增对白失败')
    } finally {
      setDraftDialogueSaving(false)
    }
  }, [draftDialogueLine, draftDialogueSaving, savedDialogLines, shotId])

  const discardDraftDialogueLine = useCallback(() => {
    setDraftDialogueLine(null)
  }, [])

  const updateExtractedDialogText = useCallback((candidateId: number, text: string) => {
    setExtractedDialogLines((prev) => prev.map((l) => (l.id === candidateId ? { ...l, text } : l)))
  }, [])

  const acceptExtractedDialogLine = useCallback(
    async (line: ShotExtractedDialogueCandidateRead, options?: { silent?: boolean }): Promise<ShotPreparationStateRead | null> => {
      const text = (line.text ?? '').trim()
      if (!text) {
        if (!options?.silent) message.warning('请先填写对白内容')
        return null
      }
      const res = await StudioShotsService.acceptExtractedDialogueCandidateApiV1StudioShotsExtractedDialogueCandidatesCandidateIdAcceptPatch({
        candidateId: line.id,
        requestBody: {
          index: line.index,
          text,
          line_mode: line.line_mode,
          speaker_name: line.speaker_name ?? null,
          target_name: line.target_name ?? null,
        },
      })
      return res.data?.state ?? null
    },
    [],
  )

  const addExtractedDialogLine = useCallback(
    async (line: ShotExtractedDialogueCandidateRead) => {
      const loadingKey = String(line.id)
      if (dialogAddingKeys[loadingKey]) return
      setDialogAddingKeys((m) => ({ ...m, [loadingKey]: true }))
      try {
        const created = await acceptExtractedDialogLine(line)
        if (created) {
          applyPreparationState(created)
          message.success('已接受')
        }
      } catch {
        message.error('接受失败')
      } finally {
        setDialogAddingKeys((m) => ({ ...m, [loadingKey]: false }))
      }
    },
    [acceptExtractedDialogLine, applyPreparationState, dialogAddingKeys],
  )

  const acceptAllExtractedDialogLines = useCallback(async () => {
    if (batchDialogAdding || extractedDialogLines.length === 0) return
    setBatchDialogAdding(true)
    try {
      let acceptedCount = 0
      let lastState: ShotPreparationStateRead | null = null
      for (const line of extractedDialogLines) {
        try {
          const accepted = await acceptExtractedDialogLine(line, { silent: true })
          if (accepted) {
            acceptedCount += 1
            lastState = accepted
          }
        } catch {
          // 逐条容错，最后统一反馈。
        }
      }
      if (lastState) {
        applyPreparationState(lastState)
      } else if (acceptedCount > 0) {
        await loadPreparationState({ silent: true })
      }
      if (acceptedCount === extractedDialogLines.length) {
        message.success(`已接受 ${acceptedCount} 条对白`)
      } else if (acceptedCount > 0) {
        message.warning(`已接受 ${acceptedCount} 条，对剩余 ${extractedDialogLines.length - acceptedCount} 条请逐条检查`)
      } else {
        message.error('批量接受失败')
      }
    } finally {
      setBatchDialogAdding(false)
    }
  }, [acceptExtractedDialogLine, applyPreparationState, batchDialogAdding, extractedDialogLines, loadPreparationState])

  const ignoreExtractedDialogLine = useCallback(
    async (
      line: ShotExtractedDialogueCandidateRead,
      options?: { silent?: boolean; applyState?: boolean },
    ): Promise<ShotPreparationStateRead | null> => {
      const loadingKey = String(line.id)
      if (dialogAddingKeys[loadingKey]) return null
      setDialogAddingKeys((m) => ({ ...m, [loadingKey]: true }))
      try {
        const res = await StudioShotsService.ignoreExtractedDialogueCandidateApiV1StudioShotsExtractedDialogueCandidatesCandidateIdIgnorePatch({
          candidateId: line.id,
        })
        const nextState = res.data?.state ?? null
        if (nextState && options?.applyState !== false) {
          applyPreparationState(nextState)
        } else if (!nextState) {
          await loadPreparationState({ silent: true })
        }
        if (!options?.silent) message.success('已忽略')
        return nextState
      } catch {
        if (!options?.silent) message.error('忽略失败')
        throw new Error('ignore failed')
      } finally {
        setDialogAddingKeys((m) => ({ ...m, [loadingKey]: false }))
      }
    },
    [applyPreparationState, dialogAddingKeys, loadPreparationState],
  )

  const ignoreAllExtractedDialogLines = useCallback(async () => {
    if (batchDialogAdding || extractedDialogLines.length === 0) return
    setBatchDialogAdding(true)
    try {
      let ignoredCount = 0
      let lastState: ShotPreparationStateRead | null = null
      for (const line of extractedDialogLines) {
        try {
          const ignored = await ignoreExtractedDialogLine(line, { silent: true, applyState: false })
          ignoredCount += 1
          if (ignored) lastState = ignored
        } catch {
          // 逐条容错，最后统一反馈。
        }
      }
      if (lastState) {
        applyPreparationState(lastState)
      } else if (ignoredCount > 0) {
        await loadPreparationState({ silent: true })
      }
      if (ignoredCount === extractedDialogLines.length) {
        message.success(`已忽略 ${ignoredCount} 条对白`)
      } else if (ignoredCount > 0) {
        message.warning(`已忽略 ${ignoredCount} 条，对剩余 ${extractedDialogLines.length - ignoredCount} 条请逐条检查`)
      } else {
        message.error('批量忽略失败')
      }
    } finally {
      setBatchDialogAdding(false)
    }
  }, [applyPreparationState, batchDialogAdding, extractedDialogLines, ignoreExtractedDialogLine, loadPreparationState])

  useEffect(() => {
    void loadPage()
  }, [loadPage])

  useEffect(() => {
    videoDiagnosticsRequestSeqRef.current += 1
    firstFrameReadinessRequestSeqRef.current += 1
    videoPromptPreviewRequestSeqRef.current += 1
    setVideoDiagnosticsOpen(false)
    setVideoDiagnosticsLoading(false)
    setVideoDiagnosticsReadiness(null)
    setFirstFrameReadiness(null)
    setFirstFrameReadinessLoading(false)
    setVideoPromptPreviewOpen(false)
    setVideoPromptPreviewLoading(false)
    setVideoPromptPreviewDraft('')
    setVideoPromptPreviewShotId(null)
    // 切换镜头时清空关键帧相关状态，避免短暂闪现上一个镜头的候选图片/槽位数据。
    setFrameImages([])
    setKeyframeCandidatesByType({ first: [], last: [], key: [] })
    setKeyframeApplyingFileId(null)
  }, [shotId])

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

  // 拉取当前镜头细节下的分镜帧图片槽位（首帧/尾帧/关键帧），用于展示"当前使用中"图片与定位候选查询所需的槽位 id。
  // 沿用文件里其它镜头维度请求的约定：响应返回前对比 currentShotIdRef，丢弃已经切换镜头后的过期响应。
  const refreshFrameImages = useCallback(async () => {
    if (!shotId) return
    const requestShotId = shotId
    try {
      const res = await StudioShotFrameImagesService.listShotFrameImagesApiV1StudioShotFrameImagesGet({
        shotDetailId: shotId,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      })
      if (currentShotIdRef.current !== requestShotId) return
      setFrameImages((res.data?.items ?? []) as ShotFrameImageRead[])
    } catch {
      if (currentShotIdRef.current !== requestShotId) return
      setFrameImages([])
    }
  }, [shotId])

  // 按帧类型拆分 frameImages 派生出的槽位 id：每种帧类型各自作为独立依赖值，
  // 避免任一帧位变化都让三种帧类型的候选查询一起重新请求。
  const frameSlotIdByType = useMemo<Record<ShotFrameType, number | null>>(
    () => ({
      first: frameImages.find((x) => x.frame_type === 'first')?.id ?? null,
      last: frameImages.find((x) => x.frame_type === 'last')?.id ?? null,
      key: frameImages.find((x) => x.frame_type === 'key')?.id ?? null,
    }),
    [frameImages],
  )
  const frameSlotIdByTypeRef = useRef(frameSlotIdByType)
  frameSlotIdByTypeRef.current = frameSlotIdByType

  // 拉取某帧类型槽位关联的历史生成任务图片，作为候选缩略图列表（按 file_id 去重，保留最新一条链接）。
  // slotId 由调用方传入（而不是内部查 frameImages），使这个回调本身不依赖 frameImages 整个数组；
  // 响应返回后再对比 frameSlotIdByTypeRef 最新值，若该帧类型已经指向其它槽位（通常是切换了镜头），丢弃这次响应。
  const refreshKeyframeCandidates = useCallback(async (frameType: ShotFrameType, slotId: number | null) => {
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
    if (frameSlotIdByTypeRef.current[frameType] !== slotId) return
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
  }, [])

  useEffect(() => {
    void refreshFrameImages()
  }, [refreshFrameImages])

  useEffect(() => {
    void refreshKeyframeCandidates('first', frameSlotIdByType.first)
  }, [refreshKeyframeCandidates, frameSlotIdByType.first])

  useEffect(() => {
    void refreshKeyframeCandidates('last', frameSlotIdByType.last)
  }, [refreshKeyframeCandidates, frameSlotIdByType.last])

  useEffect(() => {
    void refreshKeyframeCandidates('key', frameSlotIdByType.key)
  }, [refreshKeyframeCandidates, frameSlotIdByType.key])

  // "使用"候选缩略图：将该候选图片的 file_id 写回对应帧类型槽位，使其成为当前使用中的图片。
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

  // 打开关键帧生成弹窗：提示词取该帧类型已保存的草稿，参考图默认全选当前镜头已关联资产。
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

  useEffect(() => {
    if (!projectId || !chapterId || !shotId) return

    const resetExistenceCache = () => {
      setExistenceByKindName({
        scene: {},
        actor: {},
        prop: {},
        costume: {},
      })
    }

    const refreshAfterExternalCreate = async () => {
      pendingExternalAssetCreateRef.current = false
      resetExistenceCache()
      await loadPreparationState({ silent: true })
    }

    const handleMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return
      const data = event.data as ShotAssetCreatedAndLinkedMessage | null
      if (!data || data.type !== 'studio-shot-asset-created-and-linked') return
      if (data.projectId !== projectId || data.chapterId !== chapterId || data.shotId !== shotId) return
      void refreshAfterExternalCreate()
    }

    const handleFocus = () => {
      if (!pendingExternalAssetCreateRef.current) return
      void refreshAfterExternalCreate()
    }

    window.addEventListener('message', handleMessage)
    window.addEventListener('focus', handleFocus)
    return () => {
      window.removeEventListener('message', handleMessage)
      window.removeEventListener('focus', handleFocus)
    }
  }, [chapterId, loadPreparationState, projectId, shotId])

  // 切换分镜时：清理对白防抖，准备状态由 loadPage 统一加载
  useEffect(() => {
    clearDialogDebounceTimers()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shotId])

  useEffect(() => () => clearDialogDebounceTimers(), [clearDialogDebounceTimers])

  const saveShot = useCallback(async () => {
    if (!shot || !title.trim()) {
      message.warning('请填写标题')
      return
    }
    setSaving(true)
    setSemanticSaving(true)
    try {
      const [shotRes, detailRes] = await Promise.all([
        StudioShotsService.updateShotApiV1StudioShotsShotIdPatch({
          shotId: shot.id,
          requestBody: {
            title: title.trim(),
            script_excerpt: scriptExcerpt.trim() ? scriptExcerpt.trim() : null,
          },
        }),
        shotDetail
          ? StudioShotDetailsService.updateShotDetailApiV1StudioShotDetailsShotIdPatch({
              shotId: shot.id,
              requestBody: {
                camera_shot: shotDetail.camera_shot,
                angle: shotDetail.angle,
                movement: shotDetail.movement,
                duration: shotDetail.duration ?? 4,
                action_beats: shotDetail.action_beats ?? [],
              },
            })
          : Promise.resolve({ data: null } as any),
      ])

      const next = shotRes.data
      const nextDetail = detailRes.data ?? null
      if (nextDetail) {
        setShotDetail(nextDetail)
      }
      if (next) {
        setShot(next)
        setShots((prev) => prev.map((x) => (x.id === next.id ? next : x)))
        message.success('已保存基础信息与镜头语言')
      }
    } catch {
      message.error('保存失败')
    } finally {
      setSaving(false)
      setSemanticSaving(false)
    }
  }, [scriptExcerpt, shot, shotDetail, title])

  const updateShotSemantic = useCallback((patch: {
    camera_shot?: ShotDetailRead['camera_shot']
    angle?: ShotDetailRead['angle']
    movement?: ShotDetailRead['movement']
    duration?: number
    action_beats?: Array<string>
  }) => {
    setShotDetail((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        ...patch,
      }
    })
  }, [])

  const updateSkipExtraction = useCallback(
    async (skip: boolean) => {
      if (!shotId) return
      setSkipExtractionUpdating(true)
      try {
        const res = await StudioShotsService.updateShotSkipExtractionApiV1StudioShotsShotIdSkipExtractionPatch({
          shotId,
          requestBody: { skip },
        })
        const nextState = res.data?.state ?? null
        if (nextState) {
          applyPreparationState(nextState)
        } else {
          await loadPreparationState({ silent: true })
        }
        message.success(skip ? '已标记为无需提取' : '已恢复提取确认流程')
      } catch {
        message.error(skip ? '标记无需提取失败' : '恢复提取失败')
      } finally {
        setSkipExtractionUpdating(false)
      }
    },
    [applyPreparationState, loadPreparationState, shotId],
  )

  /**
   * 对任意镜头集合批量切换“无需提取”维护标记。
   * 当前镜头使用现有本地状态刷新，其余镜头完成后统一整页重载。
   */
  const updateSkipExtractionForShots = useCallback(
    async (targetShots: ShotRead[], skip: boolean) => {
      if (targetShots.length === 0) return
      if (targetShots.length === 1 && targetShots[0].id === shotId) {
        await updateSkipExtraction(skip)
        return
      }
      setSkipExtractionUpdating(true)
      try {
        await Promise.all(
          targetShots.map((target) =>
            StudioShotsService.updateShotSkipExtractionApiV1StudioShotsShotIdSkipExtractionPatch({
              shotId: target.id,
              requestBody: { skip },
            }),
          ),
        )
        message.success(skip ? `已标记 ${targetShots.length} 条镜头为无需提取` : `已恢复 ${targetShots.length} 条镜头的提取流程`)
        await loadPage()
      } catch {
        message.error(skip ? '批量标记无需提取失败' : '批量恢复提取失败')
      } finally {
        setSkipExtractionUpdating(false)
      }
    },
    [loadPage, shotId, updateSkipExtraction],
  )

  /**
   * 对目标镜头集合执行提取与自动准备。
   * 单条与多条共用同一条提取链路，只在文案和 loading 上区分。
   */
  const extractAssetsForShots = useCallback(async (targetShots: ShotRead[]) => {
    if (!projectId || !chapterId || targetShots.length === 0) return
    if (extractInFlightRef.current) return
    if (notifyExistingTask(extractTask, {
      cancellingMessage: extractTaskCopy.cancellingMessage,
      runningMessage: extractTaskCopy.runningMessage,
    })) {
      return
    }

    const actionableShots = targetShots
      .filter((item) => !item.skip_extraction)
      .sort((a, b) => a.index - b.index)
    if (actionableShots.length === 0) {
      message.info('当前选中的镜头都已标记为无需提取，如需调整请先恢复提取')
      return
    }

    extractInFlightRef.current = true
    setExtractingAssets(true)
    try {
      const scriptDivision = {
        total_shots: actionableShots.length,
        shots: actionableShots.map((item) => ({
          index: item.index,
          start_line: 1,
          end_line: 1,
          script_excerpt: item.script_excerpt ?? '',
          shot_name: item.title ?? '',
        })),
      }
      await executeAsyncTaskCreate({
        request: () =>
          ScriptProcessingService.extractScriptAsyncApiV1ScriptProcessingExtractAsyncPost({
            requestBody: {
              project_id: projectId,
              chapter_id: chapterId,
              script_division: scriptDivision as any,
              consistency: undefined,
              refresh_cache: true,
              quote_token: extractQuote.quoteToken,
            } as any,
          }),
        trackTaskData: trackExtractTaskData,
        startedMessage: actionableShots.length > 1 ? `已开始提取 ${actionableShots.length} 条镜头` : extractTaskCopy.startedMessage,
        reusedMessage: extractTaskCopy.reusedMessage,
        fallbackErrorMessage: actionableShots.length > 1 ? '批量提取失败' : '提取失败',
        getErrorMessage: makePointsAwareGetErrorMessage(extractQuote.refresh),
      })
    } catch {
      // executeAsyncTaskCreate 已统一处理错误提示
    } finally {
      setExtractingAssets(false)
      extractInFlightRef.current = false
    }
  }, [chapterId, extractTask, projectId, extractQuote.quoteToken, extractQuote.refresh])

  const extractAssets = useCallback(async () => {
    if (!shot) return
    await extractAssetsForShots([shot])
  }, [extractAssetsForShots, shot])

  const batchExtractAssets = useCallback(async () => {
    await extractAssetsForShots(selectedShots)
  }, [extractAssetsForShots, selectedShots])

  const cancelExtractTask = useCallback(async () => {
    if (!extractTask?.taskId) return
    try {
      await executeTaskCancel({
        taskId: extractTask.taskId,
        reason: '用户在分镜编辑页取消提取任务',
        applyCancelData: applyExtractCancelData,
        cancelledImmediatelyMessage: extractTaskCopy.cancelledImmediatelyMessage,
        cancelRequestedMessage: extractTaskCopy.cancelRequestedMessage,
        fallbackErrorMessage: '取消提取任务失败',
      })
    } catch {
      // executeTaskCancel 已统一处理错误提示
    }
  }, [applyExtractCancelData, extractTask])

  /** 取消当前镜头的视频生成 relation 任务，并把取消态同步到全局任务通知。 */
  const cancelVideoGeneration = useCallback(async () => {
    if (!videoGenerationRelation?.taskId) return
    try {
      await executeTaskCancel({
        taskId: videoGenerationRelation.taskId,
        reason: '用户在分镜详情页取消视频生成任务',
        applyCancelData: applyVideoGenerationCancelData,
        cancelledImmediatelyMessage: TASK_COPY.videoGeneration.cancelledImmediatelyMessage,
        cancelRequestedMessage: TASK_COPY.videoGeneration.cancelRequestedMessage,
        fallbackErrorMessage: '取消视频生成任务失败',
      })
    } catch {
      // executeTaskCancel 已统一处理错误提示
    }
  }, [applyVideoGenerationCancelData, videoGenerationRelation])

  useRelationTaskNotification({
    task: chapterDivisionTask,
    settledTask: chapterDivisionSettledTask,
    title: chapterDivisionTaskCopy.title,
    sourceLabel: chapterTitle ? `章节：${chapterTitle}` : '分镜详情页',
    runningDescription: chapterDivisionTaskCopy.runningDescription,
    cancellingDescription: chapterDivisionTaskCopy.cancellingDescription,
    successDescription: chapterDivisionTaskCopy.successDescription,
    cancelledDescription: chapterDivisionTaskCopy.cancelledDescription,
    failedDescription: chapterDivisionTaskCopy.failedDescription,
    onCancel: null,
    onNavigate:
      projectId && chapterId
        ? () => navigate(getChapterShotsPath(projectId, chapterId))
        : null,
  })
  useRelationTaskNotification({
    task: extractTask,
    settledTask: extractSettledTask,
    title: extractTaskCopy.title,
    sourceLabel: shot?.title ? `镜头：${shot.title}` : '分镜编辑页',
    runningDescription: extractTaskCopy.runningDescription,
    cancellingDescription: extractTaskCopy.cancellingDescription,
    successDescription: extractTaskCopy.successDescription,
    cancelledDescription: extractTaskCopy.cancelledDescription,
    failedDescription: extractTaskCopy.failedDescription,
    onCancel: extractTask ? () => void cancelExtractTask() : null,
    onNavigate:
      projectId && chapterId && shotId
        ? () => navigate(getChapterShotEditPath(projectId, chapterId, shotId))
        : null,
  })
  useRelationTaskNotification({
    task: videoGenerationRelation,
    settledTask: videoGenerationSettled,
    title: TASK_COPY.videoGeneration.title,
    sourceLabel: shot?.title ? `镜头：${shot.title}` : '分镜详情页',
    runningDescription: TASK_COPY.videoGeneration.runningDescription,
    cancellingDescription: TASK_COPY.videoGeneration.cancellingDescription,
    successDescription: TASK_COPY.videoGeneration.successDescription,
    cancelledDescription: TASK_COPY.videoGeneration.cancelledDescription,
    failedDescription: TASK_COPY.videoGeneration.failedDescription,
    onCancel: videoGenerationRelation ? () => void cancelVideoGeneration() : null,
    onNavigate:
      projectId && chapterId && shotId
        ? () => navigate(getChapterShotDetailPath(projectId, chapterId, shotId, 'results'))
        : null,
  })

  const goShot = (id: string) => {
    if (!projectId || !chapterId || id === shotId) return
    videoDiagnosticsRequestSeqRef.current += 1
    firstFrameReadinessRequestSeqRef.current += 1
    videoPromptPreviewRequestSeqRef.current += 1
    setVideoDiagnosticsOpen(false)
    setVideoDiagnosticsLoading(false)
    setVideoDiagnosticsTitle('视频生成诊断')
    setVideoDiagnosticsReadiness(null)
    setVideoDiagnosticsBatchItems(undefined)
    setFirstFrameReadiness(null)
    setFirstFrameReadinessLoading(false)
    setVideoPromptPreviewOpen(false)
    setVideoPromptPreviewLoading(false)
    setVideoPromptPreviewDraft('')
    setVideoPromptPreviewShotId(null)
    navigate(getChapterShotDetailPath(projectId, chapterId, id, editorTabKey))
  }
  /**
   * 切换当前镜头，同时允许左侧快捷动作直接落到指定 tab。
   */
  const goShotToTab = useCallback(
    (id: string, tab: ShotDetailTabKey) => {
      if (!projectId || !chapterId) return
      if (id === shotId) {
        setEditorTabKey(tab)
        editorTabMemoryRef.current[id] = tab
        tabAutoInitShotIdRef.current = id
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev)
          next.set('tab', tab)
          return next
        }, { replace: true })
        return
      }
      videoDiagnosticsRequestSeqRef.current += 1
      firstFrameReadinessRequestSeqRef.current += 1
      videoPromptPreviewRequestSeqRef.current += 1
      setVideoDiagnosticsOpen(false)
      setVideoDiagnosticsLoading(false)
      setVideoDiagnosticsTitle('视频生成诊断')
      setVideoDiagnosticsReadiness(null)
      setVideoDiagnosticsBatchItems(undefined)
      setFirstFrameReadiness(null)
      setFirstFrameReadinessLoading(false)
      setVideoPromptPreviewOpen(false)
      setVideoPromptPreviewLoading(false)
      setVideoPromptPreviewDraft('')
      setVideoPromptPreviewShotId(null)
      navigate(getChapterShotDetailPath(projectId, chapterId, id, tab))
    },
    [chapterId, navigate, projectId, setSearchParams, shotId],
  )
  const handleShotListClick = useCallback((targetShotId: string) => {
    goShot(targetShotId)
  }, [goShot])

  const toggleShotSelection = useCallback((targetShotId: string, checked: boolean) => {
    setSelectedShotIds((prev) => {
      if (checked) {
        return prev.includes(targetShotId) ? prev : [...prev, targetShotId]
      }
      return prev.filter((id) => id !== targetShotId)
    })
  }, [])

  const toggleSelectAllFilteredShots = useCallback((checked: boolean) => {
    setSelectedShotIds((prev) => {
      if (checked) {
        return Array.from(new Set([...prev, ...filteredShotIds]))
      }
      const filteredSet = new Set(filteredShotIds)
      return prev.filter((id) => !filteredSet.has(id))
    })
  }, [filteredShotIds])

  /**
   * 在左侧列表顶部创建追加镜头，保持“新增”属于列表级入口而不是右键语义。
   */
  const openCreate = useCallback(() => {
    createForm.resetFields()
    setCreateOpen(true)
  }, [createForm])

  const closeCreate = useCallback(() => {
    setCreateOpen(false)
    createForm.resetFields()
  }, [createForm])

  const submitCreate = useCallback(async () => {
    if (!projectId || !chapterId) return
    try {
      const values = await createForm.validateFields()
      setCreateSubmitting(true)
      const nextIndex = shotsSorted.reduce((maxIndex, item) => Math.max(maxIndex, item.index), 0) + 1
      const res = await StudioShotsService.createShotApiV1StudioShotsPost({
        requestBody: {
          id: generateUUID(),
          chapter_id: chapterId,
          index: nextIndex,
          title: values.title.trim(),
          script_excerpt: values.script_excerpt?.trim() ? values.script_excerpt.trim() : '',
          status: 'pending',
        },
      })
      const created = res.data
      if (!created) return
      closeCreate()
      message.success('已新增镜头')
      goShotToTab(created.id, 'basic')
    } catch (error: unknown) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
      message.error('新增镜头失败')
    } finally {
      setCreateSubmitting(false)
    }
  }, [chapterId, closeCreate, createForm, goShotToTab, projectId, shotsSorted])

  /**
   * 右键插入只作用于单条镜头，不继承批量选择，避免和顶部批量菜单语义重叠。
   */
  const openInsert = useCallback((direction: 'before' | 'after', refShot: ShotRead) => {
    insertForm.resetFields()
    setInsertMode({ direction, refShot })
  }, [insertForm])

  const closeInsert = useCallback(() => {
    setInsertMode(null)
    insertForm.resetFields()
  }, [insertForm])

  const submitInsert = useCallback(async () => {
    if (!chapterId || !insertMode) return
    try {
      const values = await insertForm.validateFields()
      setInsertSubmitting(true)
      const { direction, refShot } = insertMode
      const targetIndex = direction === 'before' ? refShot.index : refShot.index + 1
      const toShift = shotsSorted.filter((item) => item.index >= targetIndex).sort((a, b) => b.index - a.index)
      for (const item of toShift) {
        await StudioShotsService.updateShotApiV1StudioShotsShotIdPatch({
          shotId: item.id,
          requestBody: { index: item.index + 1 },
        })
      }
      const res = await StudioShotsService.createShotApiV1StudioShotsPost({
        requestBody: {
          id: generateUUID(),
          chapter_id: chapterId,
          index: targetIndex,
          title: values.title.trim(),
          script_excerpt: values.script_excerpt?.trim() ? values.script_excerpt.trim() : '',
          status: 'pending',
        },
      })
      const created = res.data
      if (!created) return
      closeInsert()
      message.success(direction === 'before' ? '已向上插入镜头' : '已向下插入镜头')
      goShotToTab(created.id, 'basic')
    } catch (error: unknown) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
      message.error('插入镜头失败')
    } finally {
      setInsertSubmitting(false)
    }
  }, [chapterId, closeInsert, goShotToTab, insertForm, insertMode, shotsSorted])

  /**
   * 从详情页直接重跑章节分镜提取，替代旧列表页入口。
   */
  const handleOneClickExtract = useCallback(async () => {
    if (!chapterId) return
    const scriptText = (chapterCondensedText || chapterRawText).trim()
    if (!scriptText) {
      message.error('章节没有可用文本（condensed/raw 为空）')
      return
    }
    setChapterDividing(true)
    try {
      const freshQuote = await divideQuote.refreshNow()
      const quoteToken = freshQuote?.quote_token ?? null
      if (!freshQuote?.sufficient || !quoteToken) {
        message.warning('积分试算已刷新，请确认积分充足后再提交')
        return
      }
      setChapterDivideConfirmOpen(false)
      await executeAsyncTaskCreate({
        request: () =>
          ScriptProcessingService.divideScriptAsyncApiV1ScriptProcessingDivideAsyncPost({
            requestBody: {
              script_text: scriptText,
              write_to_db: true,
              chapter_id: chapterId,
              quote_token: quoteToken,
            },
          }),
        trackTaskData: trackChapterDivisionTaskData,
        startedMessage: chapterDivisionTaskCopy.startedMessage,
        reusedMessage: chapterDivisionTaskCopy.reusedMessage,
        fallbackErrorMessage: '启动分镜提取失败',
        getErrorMessage: makePointsAwareGetErrorMessage(divideQuote.refresh),
      })
    } catch {
      // executeAsyncTaskCreate 已统一处理错误提示
    } finally {
      setChapterDividing(false)
    }
  }, [chapterCondensedText, chapterId, chapterRawText, divideQuote.refresh, divideQuote.refreshNow, trackChapterDivisionTaskData])

  const openLinkingModal = useCallback(
    async (kind: AssetKind, name: string, item: EntityNameExistenceItem, hint: string) => {
      setLinkingKind(kind)
      setLinkingName(name)
      setLinkingItem(item)
      setLinkingHint(hint)
      setLinkingThumb(undefined)
      setLinkingOpen(true)
      if (!item.asset_id) return
      setLinkingLoading(true)
      try {
        const entityType =
          kind === 'scene' ? 'scene' : kind === 'prop' ? 'prop' : kind === 'costume' ? 'costume' : 'character'
        const res = await StudioEntitiesApi.get(entityType as any, item.asset_id)
        const data: any = res.data
        const thumb = resolveAssetUrl(data?.thumbnail ?? data?.images?.[0]?.thumbnail ?? '')
        setLinkingThumb(thumb || undefined)
      } catch {
        // ignore
      } finally {
        setLinkingLoading(false)
      }
    },
    [],
  )

  const doLink = useCallback(async () => {
    if (!projectId || !chapterId || !shotId) return
    if (!linkingItem?.asset_id) return
    setLinkingActionLoading(true)
    try {
      const res = await StudioShotsService.linkExistingAssetForPreparationApiApiV1StudioShotsShotIdPreparationLinkPost({
        shotId,
        requestBody: {
          project_id: projectId,
          chapter_id: chapterId,
          entity_type: linkingKind === 'actor' ? 'character' : linkingKind,
          linked_entity_id: linkingItem.asset_id,
        },
      })
      message.success('已关联')
      if (res.data?.state) {
        applyPreparationState(res.data.state)
      } else {
        await loadPreparationState({ silent: true })
      }
      setLinkingOpen(false)
    } catch {
      message.error('关联失败')
    } finally {
      setLinkingActionLoading(false)
    }
  }, [applyPreparationState, chapterId, linkingItem?.asset_id, linkingKind, loadPreparationState, projectId, shotId])

  const handleNewAsset = useCallback(
    async (asset: AssetVM) => {
      if (!projectId || !chapterId || !shotId) return
      const name = asset.name.trim()
      if (!name) return
      try {
        const req: any = { project_id: projectId, shot_id: shotId }
        if (asset.kind === 'scene') req.scene_names = [name]
        else if (asset.kind === 'prop') req.prop_names = [name]
        else if (asset.kind === 'costume') req.costume_names = [name]
        else req.character_names = [name]

        const res = await StudioEntitiesService.checkEntityNamesExistenceApiV1StudioEntitiesExistenceCheckPost({
          requestBody: req,
        })
        const data = res.data
        const bucket =
          asset.kind === 'scene'
            ? data?.scenes
            : asset.kind === 'prop'
              ? data?.props
              : asset.kind === 'costume'
                ? data?.costumes
                : data?.characters
        const item = (bucket?.[0] as EntityNameExistenceItem | undefined) ?? null
        if (!item) {
          message.error('existence-check 返回为空')
          return
        }

        if (!item.exists) {
          Modal.confirm({
            title: '当前无可关联资产，是否新建？',
            okText: '新建',
            cancelText: '取消',
            onOk: () => {
              pendingExternalAssetCreateRef.current = true
              const open = (url: string) => window.open(url, '_blank', 'noopener,noreferrer')
              const descQ = asset.description?.trim()
                ? `&desc=${encodeURIComponent(asset.description.trim())}`
                : ''
              const styleQ =
                `&visualStyle=${encodeURIComponent(projectVisualStyle)}` +
                `&style=${encodeURIComponent(projectStyle)}`
              const ctxQ =
                `&projectId=${encodeURIComponent(projectId)}` +
                `&chapterId=${encodeURIComponent(chapterId)}` +
                `&shotId=${encodeURIComponent(shotId)}` +
                styleQ
              if (asset.kind === 'scene' || asset.kind === 'prop' || asset.kind === 'costume') {
                open(
                  `/assets?tab=${asset.kind}&create=1&name=${encodeURIComponent(name)}${descQ}${ctxQ}`,
                )
                return
              }
              open(
                `/projects/${encodeURIComponent(projectId)}?tab=roles&create=1&name=${encodeURIComponent(name)}${descQ}${ctxQ}`,
              )
            },
          })
          return
        }

        if (item.exists && !item.linked_to_project) {
          await openLinkingModal(asset.kind, name, item, '在资产库中存在同名资产，可关联')
          return
        }
        if (item.exists && item.linked_to_project && !item.linked_to_shot) {
          await openLinkingModal(asset.kind, name, item, '项目中存在同名资产，可关联')
          return
        }

        message.info('该资产已关联到当前镜头')
      } catch {
        message.error('existence-check 调用失败')
      }
    },
    [openLinkingModal, chapterId, projectId, projectStyle, projectVisualStyle, shotId],
  )

  /**
   * 点击已关联资产卡片下方的"新建"按钮：
   * 直接在新标签页打开该已关联资产的编辑页，供用户为其新建/生成图片。
   * 不创建新草稿资产，图片会挂在原资产（如"合江楼内室"）上，不产生多余的关联记录。
   */
  const handleNewLinkedAsset = useCallback(
    (asset: AssetVM) => {
      if (!asset.id || !projectId) return
      pendingExternalAssetCreateRef.current = true
      const editUrl =
        asset.kind === 'prop' ? `/assets/props/${encodeURIComponent(asset.id)}/edit`
        : asset.kind === 'costume' ? `/assets/costumes/${encodeURIComponent(asset.id)}/edit`
        : asset.kind === 'actor' ? `/projects/${encodeURIComponent(projectId)}/roles/${encodeURIComponent(asset.id)}/edit`
        : `/assets/scenes/${encodeURIComponent(asset.id)}/edit`
      window.open(editUrl, '_blank', 'noopener,noreferrer')
    },
    [projectId],
  )

  const ignoreCandidate = useCallback(
    async (asset: AssetVM) => {
      if (!asset.candidateId) return
      if (candidateActionIds[asset.candidateId]) return
      setCandidateActionIds((prev) => ({ ...prev, [asset.candidateId!]: true }))
      try {
        const res = await StudioShotsService.ignoreExtractedCandidateApiV1StudioShotsExtractedCandidatesCandidateIdIgnorePatch({
          candidateId: asset.candidateId,
        })
        if (res.data?.state) {
          applyPreparationState(res.data.state)
        } else {
          await loadPreparationState({ silent: true })
        }
        message.success('已忽略该候选项')
      } catch {
        message.error('忽略失败')
      } finally {
        setCandidateActionIds((prev) => ({ ...prev, [asset.candidateId!]: false }))
      }
    },
    [applyPreparationState, candidateActionIds, loadPreparationState],
  )


  /** 打开替换抽屉：记录待替换的资产 VM，打开抽屉。 */
  const openReplaceDrawer = useCallback((asset: AssetVM) => {
    setReplaceDrawerAsset(asset)
    setReplaceDrawerOpen(true)
  }, [])

  /** 打开添加关联资产抽屉：记录当前类别，打开抽屉。 */
  const openAddDrawer = useCallback((kind: AssetKind) => {
    setAddDrawerKind(kind)
    setAddDrawerOpen(true)
  }, [])

  /** 提交添加关联：调用 preparation-link 接口将选中实体关联到当前镜头。 */
  const doAddLink = useCallback(
    async (entityId: string, entityName: string) => {
      if (!projectId || !chapterId || !shotId) return
      setAddDrawerLoading(true)
      try {
        const res = await StudioShotsService.linkExistingAssetForPreparationApiApiV1StudioShotsShotIdPreparationLinkPost({
          shotId,
          requestBody: {
            project_id: projectId,
            chapter_id: chapterId,
            entity_type: addDrawerKind === 'actor' ? 'character' : addDrawerKind,
            linked_entity_id: entityId,
          },
        })
        message.success(`已关联「${entityName}」`)
        if (res.data?.state) {
          applyPreparationState(res.data.state)
        } else {
          await loadPreparationState({ silent: true })
        }
        setAddDrawerOpen(false)
      } catch {
        message.error('关联失败，请重试')
      } finally {
        setAddDrawerLoading(false)
      }
    },
    [addDrawerKind, applyPreparationState, chapterId, loadPreparationState, projectId, shotId],
  )

  /**
   * 提交替换请求：调用 preparation-replace 接口，以新实体 ID 替换旧实体关联。
   * 完成后刷新准备状态并关闭抽屉。
   */
  const doReplace = useCallback(
    async (newEntityId: string, newEntityName: string) => {
      if (!projectId || !chapterId || !shotId || !replaceDrawerAsset?.id) return
      setReplaceDrawerLoading(true)
      try {
        const res = await StudioShotsService.replaceAssetForPreparationApiApiV1StudioShotsShotIdPreparationReplacePost({
          shotId,
          requestBody: {
            project_id: projectId,
            chapter_id: chapterId,
            entity_type: replaceDrawerAsset.kind === 'actor' ? 'character' : replaceDrawerAsset.kind,
            old_entity_id: replaceDrawerAsset.id,
            new_entity_id: newEntityId,
          },
        })
        message.success(`已替换为「${newEntityName}」`)
        if (res.data?.state) {
          applyPreparationState(res.data.state)
        } else {
          await loadPreparationState({ silent: true })
        }
        setReplaceDrawerOpen(false)
        setReplaceDrawerAsset(null)
      } catch {
        message.error('替换失败，请重试')
      } finally {
        setReplaceDrawerLoading(false)
      }
    },
    [applyPreparationState, chapterId, loadPreparationState, projectId, replaceDrawerAsset, shotId],
  )

  /**
   * 解除资产关联（"忽略"确认后触发）：
   * 调用 preparation-unlink 接口，移除该实体与当前镜头的关联，刷新准备状态。
   */
  const doUnlinkAsset = useCallback(
    async (asset: AssetVM) => {
      if (!shotId || !asset.id) return
      setUnlinkingIds((prev) => ({ ...prev, [asset.id!]: true }))
      try {
        const res = await StudioShotsService.unlinkAssetForPreparationApiApiV1StudioShotsShotIdPreparationUnlinkPost({
          shotId,
          requestBody: {
            entity_type: asset.kind === 'actor' ? 'character' : asset.kind,
            entity_id: asset.id,
            candidate_id: asset.candidateId ?? null,
          },
        })
        message.success(`已忽略「${asset.name}」的关联`)
        if (res.data?.state) {
          applyPreparationState(res.data.state)
        } else {
          await loadPreparationState({ silent: true })
        }
      } catch {
        message.error('忽略失败，请重试')
      } finally {
        setUnlinkingIds((prev) => ({ ...prev, [asset.id!]: false }))
      }
    },
    [applyPreparationState, loadPreparationState, shotId],
  )

  const resolvedVideoRatio = useMemo(
    () => resolveVideoRatio(shotDetail, projectDefaultVideoRatio),
    [projectDefaultVideoRatio, shotDetail],
  )

  /**
   * 轮询关键帧生成任务：间隔 2 秒，最多 30 次。成功后刷新槽位与候选缩略图；
   * frameSlotIdByTypeRef 由前面 useMemo/useRef 组合维护，总是反映最新的槽位 id
   * （不管这是该帧类型第一次生成、还是往已有槽位补充新候选图，都能拿到正确的 slotId）。
   *
   * requestShotId 是提交生成任务时的镜头 id：这个页面切换镜头只换路由参数、组件不会卸载，
   * 轮询最长可能跨越 60 秒，如果期间用户切到了别的镜头，必须提前停止并放弃写入任何状态，
   * 否则会把 A 镜头生成的结果写进 B 镜头当前显示的候选列表里（与文件里其它地方用
   * currentShotIdRef 校验陈旧响应是同一类问题）。
   */
  const pollKeyframeTask = useCallback(
    async (taskId: string, frameType: ShotFrameType, requestShotId: string) => {
      for (let attempt = 0; attempt < 30; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000))
        if (currentShotIdRef.current !== requestShotId) return
        try {
          const res = await FilmService.getTaskStatusApiV1FilmTasksTaskIdStatusGet({ taskId })
          if (currentShotIdRef.current !== requestShotId) return
          const status = res.data?.status
          if (status === 'succeeded') {
            await refreshFrameImages()
            if (currentShotIdRef.current !== requestShotId) return
            const slotId = frameSlotIdByTypeRef.current[frameType]
            await refreshKeyframeCandidates(frameType, slotId)
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
      if (currentShotIdRef.current === requestShotId) {
        message.warning('关键帧生成任务耗时较长，请稍后手动刷新查看结果')
      }
    },
    [refreshFrameImages, refreshKeyframeCandidates],
  )

  // 提交关键帧生成任务：将弹窗内已选参考图（按顺序）转为 ShotLinkedAssetItem 传给后端，
  // 成功后关闭弹窗并异步轮询任务结果。
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
        void pollKeyframeTask(taskId, keyframeModalFrameType, shotId)
      }
    } catch (error) {
      const pointsAware = makePointsAwareGetErrorMessage(keyframeImageQuote.refresh)
      message.error(pointsAware(error, '提交生成任务失败'))
    } finally {
      setKeyframeModalSubmitting(false)
    }
  }, [
    keyframeImageQuote.quoteToken,
    keyframeImageQuote.refresh,
    keyframeModalFrameType,
    keyframeModalPrompt,
    keyframeModalSelectedFileIds,
    keyframeReferenceOptions,
    pollKeyframeTask,
    resolvedVideoRatio,
    shotId,
  ])

  /**
   * 打开单镜头视频提示词预览。
   * 本页仅迁移首帧参考模式的最小生成路径；提交前先让用户确认提示词和积分消耗。
   */
  const openVideoPromptPreview = useCallback(async () => {
    if (!shotId) {
      message.warning('请先选择一个分镜')
      return
    }
    if (!preparationState?.ready_for_generation) {
      message.warning('请先完成基础信息、动作拍点、资产与台词确认')
      return
    }
    if (!shotDetail?.duration || shotDetail.duration <= 0) {
      message.warning('请先设置镜头时长')
      return
    }
    if (!resolvedVideoRatio) {
      message.warning('请先设置视频比例')
      return
    }
    if (!selectedVideoModelId) {
      message.warning('请先选择视频模型')
      return
    }
    if (firstFrameReadinessLoading) {
      message.warning('正在检查首帧生成条件，请稍后再试')
      return
    }
    if (firstFrameReadiness?.ready !== true) {
      message.warning('当前镜头首帧模式还未就绪，请先查看诊断')
      return
    }

    const requestShotId = shotId
    const requestSeq = ++videoPromptPreviewRequestSeqRef.current
    setVideoPromptPreviewDraft('')
    setVideoPromptPreviewShotId(requestShotId)
    setVideoPromptPreviewOpen(true)
    setVideoPromptPreviewLoading(true)
    try {
      const res = await FilmService.previewVideoGenerationPromptApiV1FilmTasksVideoPreviewPromptPost({
        requestBody: {
          shot_id: requestShotId,
          reference_mode: 'first',
          prompt: null,
          images: [],
          ratio: resolvedVideoRatio,
        },
      })
      if (requestSeq !== videoPromptPreviewRequestSeqRef.current || currentShotIdRef.current !== requestShotId) return
      setVideoPromptPreviewDraft(res.data?.prompt ?? '')
    } catch {
      if (requestSeq !== videoPromptPreviewRequestSeqRef.current || currentShotIdRef.current !== requestShotId) return
      message.error('获取视频提示词预览失败')
      setVideoPromptPreviewOpen(false)
      setVideoPromptPreviewShotId(null)
    } finally {
      if (requestSeq === videoPromptPreviewRequestSeqRef.current && currentShotIdRef.current === requestShotId) {
        setVideoPromptPreviewLoading(false)
      }
    }
  }, [
    firstFrameReadiness?.ready,
    firstFrameReadinessLoading,
    preparationState?.ready_for_generation,
    resolvedVideoRatio,
    selectedVideoModelId,
    shotDetail?.duration,
    shotId,
  ])

  /**
   * 提交当前提示词生成视频任务。
   * 只负责创建任务并刷新镜头数据，任务状态与失败详情仍由全局任务中心承载。
   */
  const submitVideoGeneration = useCallback(async () => {
    if (!shotId) {
      message.warning('请先选择一个分镜')
      return
    }
    if (!videoPromptPreviewOpen || videoPromptPreviewShotId !== shotId) {
      message.warning('当前提示词预览已失效，请重新预览')
      return
    }
    if (!resolvedVideoRatio) {
      message.warning('请先设置视频比例')
      return
    }
    const prompt = videoPromptPreviewDraft.trim()
    if (!prompt) {
      message.warning('请输入视频提示词')
      return
    }
    if (!selectedVideoModelId) {
      message.warning('请先选择视频模型')
      return
    }
    if (!videoQuote.quoteToken) {
      message.warning('请等待积分试算完成后再提交')
      return
    }

    setVideoPromptPreviewSubmitting(true)
    try {
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
      const taskId = created.data?.task_id ?? null
      if (taskId) {
        const nextRelation: RelationTaskState = {
          taskId,
          status: 'pending',
          progress: 0,
          cancelRequested: false,
        }
        setTrackedVideoGeneration(nextRelation)
      }
      message.success('视频生成任务已提交')
      setVideoPromptPreviewOpen(false)
      setVideoPromptPreviewShotId(null)
      setVideoPromptPreviewDraft('')
    } catch (error) {
      const pointsAware = makePointsAwareGetErrorMessage(videoQuote.refresh)
      message.error(pointsAware(error, '发起视频生成失败'))
    } finally {
      setVideoPromptPreviewSubmitting(false)
    }
  }, [
    resolvedVideoRatio,
    selectedVideoModelId,
    setTrackedVideoGeneration,
    shotId,
    videoPromptPreviewDraft,
    videoPromptPreviewOpen,
    videoPromptPreviewShotId,
    videoQuote.quoteToken,
    videoQuote.refresh,
    videoResolution,
  ])

  /**
   * 打开视频生成诊断抽屉，并按首帧参考模式读取当前镜头准备度。
   * 诊断只用于展示缺口，不承载生成任务的运行态信息。
   */
  const openVideoDiagnostics = useCallback(async () => {
    if (!shotId) return
    const requestShotId = shotId
    const requestSeq = ++videoDiagnosticsRequestSeqRef.current
    setVideoDiagnosticsTitle('视频生成诊断')
    setVideoDiagnosticsOpen(true)
    setVideoDiagnosticsLoading(true)
    setVideoDiagnosticsReadiness(null)
    setVideoDiagnosticsBatchItems(undefined)
    try {
      const res = await StudioShotsService.getShotVideoReadinessApiApiV1StudioShotsShotIdVideoReadinessGet({
        shotId: requestShotId,
        referenceMode: 'first',
      })
      if (requestSeq !== videoDiagnosticsRequestSeqRef.current || currentShotIdRef.current !== requestShotId) return
      setVideoDiagnosticsReadiness(res.data ?? null)
    } catch {
      if (requestSeq !== videoDiagnosticsRequestSeqRef.current || currentShotIdRef.current !== requestShotId) return
      message.error('加载生成诊断失败')
      setVideoDiagnosticsReadiness(null)
    } finally {
      if (requestSeq === videoDiagnosticsRequestSeqRef.current && currentShotIdRef.current === requestShotId) {
        setVideoDiagnosticsLoading(false)
      }
    }
  }, [shotId])

  /**
   * 对任意镜头集合执行生成诊断。
   * 单条直接展示详情，多条展示批量诊断列表。
   */
  const runDiagnosticsForShots = useCallback(async (targetShots: ShotRead[]) => {
    if (targetShots.length === 0) return
    const requestSeq = ++videoDiagnosticsRequestSeqRef.current
    setVideoDiagnosticsTitle(targetShots.length === 1 ? `${buildShotActionTitle(targetShots)} · 生成诊断` : `批量诊断（${targetShots.length} 条）`)
    setVideoDiagnosticsOpen(true)
    setVideoDiagnosticsLoading(true)
    setVideoDiagnosticsReadiness(null)
    setVideoDiagnosticsBatchItems(undefined)
    try {
      if (targetShots.length === 1) {
        const res = await StudioShotsService.getShotVideoReadinessApiApiV1StudioShotsShotIdVideoReadinessGet({
          shotId: targetShots[0].id,
          referenceMode: 'first',
        })
        if (requestSeq !== videoDiagnosticsRequestSeqRef.current) return
        setVideoDiagnosticsReadiness(res.data ?? null)
        return
      }

      const results = []
      for (const target of targetShots) {
        try {
          const res = await StudioShotsService.getShotVideoReadinessApiApiV1StudioShotsShotIdVideoReadinessGet({
            shotId: target.id,
            referenceMode: 'first',
          })
          if (requestSeq !== videoDiagnosticsRequestSeqRef.current) return
          results.push({
            title: `#${target.index} · ${target.title?.trim() || '未命名镜头'}`,
            readiness: res.data ?? null,
          })
        } catch (error) {
          if (requestSeq !== videoDiagnosticsRequestSeqRef.current) return
          results.push({
            title: `#${target.index} · ${target.title?.trim() || '未命名镜头'}`,
            readiness: null,
            error: makePointsAwareGetErrorMessage(() => {})(error, '诊断失败'),
          })
        }
      }
      if (requestSeq !== videoDiagnosticsRequestSeqRef.current) return
      setVideoDiagnosticsBatchItems(results)
    } finally {
      if (requestSeq === videoDiagnosticsRequestSeqRef.current) {
        setVideoDiagnosticsLoading(false)
      }
    }
  }, [])

  /**
   * 读取某个镜头生成视频所需的最小上下文。
   * 右键单条生成和批量生成都通过它拿到最新时长、比例和准备度。
   */
  const loadShotGenerationContext = useCallback(async (targetShot: ShotRead) => {
    const [detailRes, readinessRes] = await Promise.all([
      StudioShotDetailsService.getShotDetailApiV1StudioShotDetailsShotIdGet({ shotId: targetShot.id }),
      StudioShotsService.getShotVideoReadinessApiApiV1StudioShotsShotIdVideoReadinessGet({
        shotId: targetShot.id,
        referenceMode: 'first',
      }),
    ])
    const detail = detailRes.data ?? null
    const readiness = readinessRes.data ?? null
    const ratio = resolveVideoRatio(detail, projectDefaultVideoRatio)
    return { detail, readiness, ratio }
  }, [projectDefaultVideoRatio])

  /**
   * 用当前页模型/清晰度配置直接提交指定镜头的视频生成任务。
   * 单条右键生成与批量生成都会走这条链路，保持生成参数来源一致。
   */
  const generateVideosForShots = useCallback(async (targetShots: ShotRead[]) => {
    if (targetShots.length === 0) return
    if (!selectedVideoModelId) {
      message.warning('请先在右侧生成视频页选择视频模型')
      if (targetShots.length === 1) {
        goShotToTab(targetShots[0].id, 'generate')
      }
      return
    }

    setBatchGenerating(true)
    const blockedDiagnostics: Array<{ title: string; readiness: ShotVideoReadinessRead | null; error?: string }> = []
    let successCount = 0
    let failCount = 0
    let skippedCount = 0

    try {
      for (const targetShot of targetShots) {
        try {
          const { detail, readiness, ratio } = await loadShotGenerationContext(targetShot)
          if (!readiness?.ready) {
            blockedDiagnostics.push({
              title: `#${targetShot.index} · ${targetShot.title?.trim() || '未命名镜头'}`,
              readiness,
            })
            skippedCount += 1
            continue
          }
          if (!detail?.duration || detail.duration <= 0 || !ratio) {
            blockedDiagnostics.push({
              title: `#${targetShot.index} · ${targetShot.title?.trim() || '未命名镜头'}`,
              readiness,
              error: !detail?.duration || detail.duration <= 0 ? '未设置镜头时长' : '未设置视频比例',
            })
            skippedCount += 1
            continue
          }

          const previewRes = await FilmService.previewVideoGenerationPromptApiV1FilmTasksVideoPreviewPromptPost({
            requestBody: {
              shot_id: targetShot.id,
              reference_mode: 'first',
              prompt: null,
              images: [],
              ratio,
            },
          })
          const prompt = String(previewRes.data?.prompt ?? '').trim()
          if (!prompt) {
            blockedDiagnostics.push({
              title: `#${targetShot.index} · ${targetShot.title?.trim() || '未命名镜头'}`,
              readiness,
              error: '未生成有效提示词',
            })
            skippedCount += 1
            continue
          }

          const quoteRes = await PointsService.quoteMyPointsApiV1PointsQuotePost({
            requestBody: {
              business_type: 'video_generation',
              category: 'video',
              model_id: selectedVideoModelId,
              duration_seconds: detail.duration,
              resolution: videoResolution,
              generation_count: 1,
            },
          })
          const quoteToken = quoteRes.data?.quote_token ?? null
          if (!quoteToken) {
            failCount += 1
            message.error(`镜头 #${targetShot.index} 试算失败，未拿到 quote token`)
            continue
          }

          await FilmService.createVideoGenerationTaskApiV1FilmTasksVideoPost({
            requestBody: {
              shot_id: targetShot.id,
              model_id: selectedVideoModelId,
              reference_mode: 'first',
              prompt,
              images: [],
              ratio,
              resolution: videoResolution,
              quote_token: quoteToken,
            },
          })
          successCount += 1
        } catch (error) {
          failCount += 1
          const pointsAware = makePointsAwareGetErrorMessage(() => {})
          message.error(`镜头 #${targetShot.index}：${pointsAware(error, '发起视频生成失败')}`)
        }
      }

      if (blockedDiagnostics.length > 0) {
        setVideoDiagnosticsTitle(`批量诊断（${blockedDiagnostics.length} 条待补齐）`)
        setVideoDiagnosticsReadiness(null)
        setVideoDiagnosticsBatchItems(blockedDiagnostics)
        setVideoDiagnosticsOpen(true)
      }

      if (targetShots.length === 1 && successCount === 1) {
        const target = targetShots[0]
        if (target.id === shotId) {
          message.success('视频生成任务已提交')
          void loadPage()
        } else {
          message.success('视频生成任务已提交，已切到该镜头结果页')
          goShotToTab(target.id, 'results')
        }
        return
      }

      const parts = [`${successCount} 成功`]
      if (skippedCount > 0) parts.push(`${skippedCount} 跳过`)
      if (failCount > 0) parts.push(`${failCount} 失败`)
      message[failCount > 0 ? 'warning' : 'success'](`批量生成提交完成：${parts.join('，')}`)
      await loadPage()
    } finally {
      setBatchGenerating(false)
    }
  }, [goShotToTab, loadPage, loadShotGenerationContext, selectedVideoModelId, shotId, videoResolution])

  /**
   * 下载目标镜头的已生成视频。
   * 批量模式下逐个触发浏览器下载，不再引入旧工作室的本地目录选择流程。
   */
  const downloadVideosForShots = useCallback(async (targetShots: ShotRead[]) => {
    const downloadable = targetShots
      .map((target) => ({
        shot: target,
        url: buildFileDownloadUrl(target.generated_video_file_id?.trim()),
      }))
      .filter((item): item is { shot: ShotRead; url: string } => Boolean(item.url))

    if (downloadable.length === 0) {
      message.warning('当前目标镜头暂无可下载视频')
      return
    }

    setBatchDownloading(true)
    try {
      for (const item of downloadable) {
        const anchor = document.createElement('a')
        anchor.href = item.url
        anchor.download = `${item.shot.index}-${item.shot.title?.trim() || 'shot'}.mp4`
        anchor.target = '_blank'
        anchor.rel = 'noreferrer'
        document.body.appendChild(anchor)
        anchor.click()
        document.body.removeChild(anchor)
      }
      message.success(downloadable.length === 1 ? '已开始下载视频' : `已开始下载 ${downloadable.length} 条视频`)
    } finally {
      setBatchDownloading(false)
    }
  }, [])

  /**
   * 删除目标镜头，并在当前镜头被删掉时自动切换到剩余镜头或返回列表页。
   */
  const deleteShots = useCallback(async (targetShots: ShotRead[]) => {
    if (!projectId || !chapterId || targetShots.length === 0) return
    const deletedIds = new Set(targetShots.map((item) => item.id))
    const remainingShots = shotsSorted.filter((item) => !deletedIds.has(item.id))
    const nextShotId = remainingShots[0]?.id
    setBatchDeleting(true)
    try {
      await Promise.all(targetShots.map((target) => StudioShotsService.deleteShotApiV1StudioShotsShotIdDelete({ shotId: target.id })))
      setSelectedShotIds((prev) => prev.filter((id) => !deletedIds.has(id)))
      if (shotId && deletedIds.has(shotId)) {
        if (nextShotId) {
          goShotToTab(nextShotId, editorTabKey)
        } else {
          navigate(getChapterShotsPath(projectId, chapterId))
        }
      } else {
        await loadPage()
      }
      message.success(targetShots.length === 1 ? '已删除镜头' : `已删除 ${targetShots.length} 条镜头`)
    } catch {
      message.error(targetShots.length === 1 ? '删除镜头失败' : '批量删除失败')
    } finally {
      setBatchDeleting(false)
    }
  }, [chapterId, editorTabKey, goShotToTab, loadPage, navigate, projectId, shotId, shotsSorted])

  const batchActionMenuItems: MenuProps['items'] = useMemo(() => [
    {
      key: 'extract',
      label: '提取',
      icon: <ReloadOutlined />,
      disabled: selectedShots.length === 0 || extractTaskActive || !extractQuote.canSubmit,
      onClick: () => {
        if (selectedShots.length === 0) return
        setExtractConfirmTarget('batch')
        setExtractConfirmOpen(true)
      },
    },
    {
      key: 'diagnose',
      label: '诊断',
      icon: <ToolOutlined />,
      disabled: selectedShots.length === 0 || batchGenerating,
      onClick: () => void runDiagnosticsForShots(selectedShots),
    },
    {
      key: 'generate',
      label: '生成视频',
      icon: <ThunderboltOutlined />,
      disabled: selectedShots.length === 0 || batchGenerating,
      onClick: () => void generateVideosForShots(selectedShots),
    },
    {
      key: 'download',
      label: '下载视频',
      icon: <DownloadOutlined />,
      disabled: selectedShots.length === 0 || batchDownloading,
      onClick: () => void downloadVideosForShots(selectedShots),
    },
    { type: 'divider' },
    {
      key: 'delete',
      label: '删除',
      danger: true,
      icon: <DeleteOutlined />,
      disabled: selectedShots.length === 0 || batchDeleting || batchGenerating,
      onClick: () => {
        if (selectedShots.length === 0) return
        Modal.confirm({
          title: `删除 ${selectedShots.length} 条镜头？`,
          okText: '删除',
          okButtonProps: { danger: true, loading: batchDeleting },
          cancelText: '取消',
          onOk: () => deleteShots(selectedShots),
        })
      },
    },
    { type: 'divider' },
    {
      key: 'skip-extraction',
      label: '标记无需提取',
      icon: <StopOutlined />,
      disabled: selectedShots.length === 0 || skipExtractionUpdating || selectedShots.every((item) => item.skip_extraction),
      onClick: () => {
        const targets = selectedShots.filter((item) => !item.skip_extraction)
        if (targets.length === 0) return
        Modal.confirm({
          title: `将 ${targets.length} 条镜头标记为无需提取？`,
          content: '标记后这些镜头会直接按“提取确认已完成”处理。',
          okText: '确认',
          okButtonProps: { danger: true, loading: skipExtractionUpdating },
          cancelText: '取消',
          onOk: () => updateSkipExtractionForShots(targets, true),
        })
      },
    },
    {
      key: 'restore-extraction',
      label: '恢复提取',
      icon: <UndoOutlined />,
      disabled: selectedShots.length === 0 || skipExtractionUpdating || selectedShots.every((item) => !item.skip_extraction),
      onClick: () => {
        const targets = selectedShots.filter((item) => item.skip_extraction)
        if (targets.length === 0) return
        void updateSkipExtractionForShots(targets, false)
      },
    },
  ], [batchDeleting, batchDownloading, batchGenerating, deleteShots, extractQuote.canSubmit, extractTaskActive, runDiagnosticsForShots, selectedShots, skipExtractionUpdating, updateSkipExtractionForShots, generateVideosForShots, downloadVideosForShots])

  /**
   * 左侧右键菜单只保留插入这类位置性动作，避免与顶部批量下拉重复。
   */
  const buildShotContextMenuItems = useCallback((targetShot: ShotRead): MenuProps['items'] => {
    return [
      {
        key: 'insert-before',
        label: '向上插入分镜',
        icon: <PlusOutlined />,
        onClick: () => openInsert('before', targetShot),
      },
      {
        key: 'insert-after',
        label: '向下插入分镜',
        icon: <PlusOutlined />,
        onClick: () => openInsert('after', targetShot),
      },
    ]
  }, [openInsert])

  const prefetchExistenceForNewAssets = useCallback(
    async (kind: AssetKind, items: AssetVM[]) => {
      if (!projectId || !shotId) return
      if (existenceInFlightRef.current[kind]) return
      const missingNames = items
        .filter((x) => x.status === 'new')
        .map((x) => x.name.trim())
        .filter(Boolean)
        .filter((n) => !existenceByKindName[kind][n])
      if (missingNames.length === 0) return

      existenceInFlightRef.current[kind] = true
      try {
        const req: any = { project_id: projectId, shot_id: shotId }
        if (kind === 'scene') req.scene_names = missingNames
        else if (kind === 'prop') req.prop_names = missingNames
        else if (kind === 'costume') req.costume_names = missingNames
        else req.character_names = missingNames

        const res = await StudioEntitiesService.checkEntityNamesExistenceApiV1StudioEntitiesExistenceCheckPost({
          requestBody: req,
        })
        const data = res.data
        const bucket =
          kind === 'scene'
            ? data?.scenes
            : kind === 'prop'
              ? data?.props
              : kind === 'costume'
                ? data?.costumes
                : data?.characters
        const list = Array.isArray(bucket) ? (bucket as EntityNameExistenceItem[]) : []
        if (list.length === 0) return
        setExistenceByKindName((prev) => {
          const next = { ...prev, [kind]: { ...prev[kind] } }
          for (const it of list) {
            const key = it?.name?.trim?.() ? it.name.trim() : ''
            if (!key) continue
            next[kind][key] = it
          }
          return next
        })
      } catch {
        // 静默：避免频繁 toast
      } finally {
        existenceInFlightRef.current[kind] = false
      }
    },
    [existenceByKindName, projectId, shotId],
  )

  useEffect(() => {
    void prefetchExistenceForNewAssets('scene', unionAssets.scene)
    void prefetchExistenceForNewAssets('actor', unionAssets.actor)
    void prefetchExistenceForNewAssets('prop', unionAssets.prop)
    void prefetchExistenceForNewAssets('costume', unionAssets.costume)
  }, [prefetchExistenceForNewAssets, unionAssets])

  if (!projectId || !chapterId || !shotId) {
    return <Navigate to="/projects" replace />
  }

  const hasTitleAndExcerpt = preparationState?.basic_info_ready ?? (!!title.trim() && !!scriptExcerpt.trim())
  const hasSemanticDefaults = preparationState?.semantic_defaults_ready
    ?? (!!shotDetail?.camera_shot && !!shotDetail?.angle && !!shotDetail?.movement && (shotDetail?.duration ?? 0) > 0)
  const actionBeatsCount = preparationState?.action_beats_count
    ?? (shotDetail?.action_beats ?? []).filter((item) => item.trim().length > 0).length
  const actionBeatsReady = preparationState?.action_beats_ready ?? (actionBeatsCount > 0)
  const linkedAssetCount = shotAssetsOverview?.summary.linked_count ?? 0
  const pendingAssetCount = shotAssetsOverview?.summary.pending_count ?? 0
  const pendingConfirmCount = preparationState?.pending_confirm_count ?? (pendingAssetCount + extractedDialogLines.length)
  const assetsReady = !!shotAssetsOverview && pendingAssetCount === 0
  const dialogsReady = extractedDialogLines.length === 0
  const statusReady = preparationState?.ready_for_generation ?? (shot?.status === 'ready')
  const basicInfoReady = hasTitleAndExcerpt && hasSemanticDefaults
  const confirmReady = pendingConfirmCount === 0
  const extractionSummary = getShotExtractionSummary(shot)
  const extractionStateMeta = getExtractionStateMeta(shot, pendingConfirmCount)
  const nextStepTitle = statusReady ? '下一步：生成视频' : '下一步：先完成镜头准备'
  const nextStepDescription = statusReady
    ? '当前镜头的信息提取确认已经完成，可以继续配置关键帧、参考图、视频参数和视频生成。'
    : actionBeatsReady
      ? '当前镜头仍有提取候选、对白或镜头基础信息待确认。先在这里完成准备，准备完成后再继续生成视频。'
      : '当前镜头的动作拍点还没有确认。建议先补齐动作序列，再继续关键帧和视频生成。'

  const checklistItems = [
    {
      key: 'script',
      label: '标题、摘录与镜头语言',
      tone: basicInfoReady ? 'success' : 'warning',
      text: basicInfoReady ? '已确认基础信息与镜头语言' : '请先补齐标题、剧本摘录和镜头语言',
    },
    {
      key: 'action_beats',
      label: '动作拍点',
      tone: actionBeatsReady ? 'success' : 'warning',
      text: actionBeatsReady
        ? `已确认 ${actionBeatsCount} 条动作拍点`
        : '请先确认当前镜头的动作变化序列',
    },
    {
      key: 'assets',
      label: '资产',
      tone: assetsReady ? 'success' : shotAssetsOverview ? 'warning' : 'default',
      text: assetsReady
        ? extractionSummary.state === 'skipped'
          ? '已跳过资产提取'
          : extractionSummary.state === 'extracted_empty'
            ? '已提取无候选'
            : linkedAssetCount > 0
              ? '已完成资产确认'
              : '已完成资产确认'
        : extractionSummary.state === 'not_extracted'
          ? '未提取'
          : extractionSummary.state === 'extracted_empty'
            ? '已提取无候选'
            : shotAssetsOverview
              ? `待处理 ${pendingAssetCount}`
              : '待处理',
    },
    {
      key: 'dialogs',
      label: '对白',
      tone: dialogsReady ? 'success' : extractedDialogLines.length > 0 ? 'warning' : 'default',
      text: dialogsReady
        ? extractionSummary.state === 'skipped'
          ? '已跳过对白提取'
          : extractionSummary.state === 'extracted_empty'
            ? '已提取无候选'
            : savedDialogLines.length > 0
              ? '已完成对白确认'
              : '已完成对白确认'
        : extractionSummary.state === 'not_extracted'
          ? '未提取'
          : extractionSummary.state === 'extracted_empty'
            ? '已提取无候选'
            : extractedDialogLines.length > 0
              ? `待处理 ${extractedDialogLines.length}`
              : '待处理',
    },
    {
      key: 'shoot',
      label: '拍摄准备',
      tone: statusReady ? 'success' : 'default',
      text: statusReady
        ? '已具备进入视频生成流程的前置条件'
        : '请先完成信息提取确认',
    },
  ] as const

  useEffect(() => {
    if (!shotId) return
    if (loading || !shot) return
    if (urlTabParam !== null) {
      const nextTab = explicitUrlTabKey ?? 'basic'
      if (editorTabKey !== nextTab) setEditorTabKey(nextTab)
      editorTabMemoryRef.current[shotId] = nextTab
      tabAutoInitShotIdRef.current = shotId
      return
    }
    const rememberedTab = editorTabMemoryRef.current[shotId]
    if (rememberedTab) {
      if (editorTabKey !== rememberedTab) setEditorTabKey(rememberedTab)
      tabAutoInitShotIdRef.current = shotId
      return
    }
    if (tabAutoInitShotIdRef.current === shotId) return
    setEditorTabKey(pendingConfirmCount > 0 ? 'confirm' : 'basic')
    tabAutoInitShotIdRef.current = shotId
  }, [editorTabKey, explicitUrlTabKey, loading, pendingConfirmCount, shot, shotId, urlTabParam])

  const handleEditorTabChange = useCallback(
    (key: string) => {
      const nextKey = isShotDetailTabKey(key) ? key : 'basic'
      setEditorTabKey(nextKey)
      if (shotId) {
        editorTabMemoryRef.current[shotId] = nextKey
        tabAutoInitShotIdRef.current = shotId
      }
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set('tab', nextKey)
        return next
      }, { replace: true })
    },
    [setSearchParams, shotId],
  )
  const goToGenerateTab = () => handleEditorTabChange('generate')

  const editorTabItems = [
    {
      key: 'basic',
      label: (
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: basicInfoReady ? '#22c55e' : '#f59e0b' }}
          />
          <span>1 基础信息</span>
        </div>
      ),
      children: (
        <ChapterShotBasicInfoSection
          title={title}
          scriptExcerpt={scriptExcerpt}
          saving={saving}
          semanticSaving={semanticSaving}
          semantic={{
            camera_shot: shotDetail?.camera_shot ?? undefined,
            angle: shotDetail?.angle ?? undefined,
            movement: shotDetail?.movement ?? undefined,
            duration: shotDetail?.duration ?? 4,
            action_beats: shotDetail?.action_beats ?? [],
          }}
          actionBeatPhases={preparationState?.action_beat_phases ?? []}
          onTitleChange={setTitle}
          onScriptExcerptChange={setScriptExcerpt}
          onSemanticChange={updateShotSemantic}
          onSave={() => void saveShot()}
        />
      ),
    },
    {
      key: 'confirm',
      label: (
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: confirmReady ? '#22c55e' : '#f59e0b' }}
          />
          <span>2 资产与对白确认</span>
          {pendingConfirmCount > 0 ? <Badge count={pendingConfirmCount} size="small" /> : null}
        </div>
      ),
      children: (
        <div className="rounded-2xl border border-slate-200 bg-slate-50/70 px-4 py-4 space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-sm font-medium text-slate-900">资产与对白确认工作区</div>
              <div className="text-[11px] text-slate-500 mt-1">
                分镜提取后系统会自动准备资产和对白；这里只处理缺失、低置信或需要人工修正的内容。
              </div>
              <div
                className="mt-3 rounded-lg border px-3 py-2 text-xs"
                style={{
                  borderColor:
                    extractionStateMeta.tone === 'green'
                      ? '#86efac'
                      : extractionStateMeta.tone === 'blue'
                        ? '#93c5fd'
                        : '#fcd34d',
                  background:
                    extractionStateMeta.tone === 'green'
                      ? '#f0fdf4'
                      : extractionStateMeta.tone === 'blue'
                        ? '#eff6ff'
                        : '#fffbeb',
                  color:
                    extractionStateMeta.tone === 'green'
                      ? '#166534'
                      : extractionStateMeta.tone === 'blue'
                        ? '#1d4ed8'
                        : '#92400e',
                }}
              >
                <div className="font-medium">{extractionStateMeta.title}</div>
                <div className="mt-1 opacity-90">{extractionStateMeta.description}</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                type="default"
                size="small"
                loading={extractingAssets || extractTaskActive}
                disabled={extractTaskActive || !extractQuote.canSubmit}
                onClick={() => { setExtractConfirmTarget('single'); setExtractConfirmOpen(true) }}
              >
                重新提取/刷新候选
              </Button>
              {extractTask ? (
                <Button
                  size="small"
                  danger
                  icon={<CloseCircleOutlined />}
                  disabled={extractTask.cancelRequested}
                  onClick={() => void cancelExtractTask()}
                >
                  {extractTask.cancelRequested ? '正在取消' : '取消提取'}
                </Button>
              ) : null}
              {shot?.skip_extraction ? (
                <Button
                  size="small"
                  loading={skipExtractionUpdating}
                  onClick={() => void updateSkipExtraction(false)}
                >
                  恢复提取
                </Button>
              ) : (
                <Popconfirm
                  title="确认标记为无需提取？"
                  description="标记后当前镜头会直接按“提取确认已完成”处理。"
                  okText="确认"
                  cancelText="取消"
                  onConfirm={() => void updateSkipExtraction(true)}
                  okButtonProps={{ danger: true, loading: skipExtractionUpdating }}
                  cancelButtonProps={{ disabled: skipExtractionUpdating }}
                >
                  <Button
                    size="small"
                    danger
                    loading={skipExtractionUpdating}
                  >
                    无需提取
                  </Button>
                </Popconfirm>
              )}
            </div>
          </div>

          <ChapterShotAssetConfirmation
            projectId={projectId}
            extraction={extractionSummary}
            unionAssets={unionAssets}
            expandedKinds={expandedKinds}
            candidateActionIds={candidateActionIds}
            existenceByKindName={existenceByKindName}
            onToggleExpanded={toggleExpanded}
            onIgnoreCandidate={(asset) => void ignoreCandidate(asset)}
            onHandleNewAsset={(asset) => void handleNewAsset(asset)}
            onNewLinkedAsset={handleNewLinkedAsset}
            onReplaceAsset={openReplaceDrawer}
            onUnlinkAsset={(asset) => void doUnlinkAsset(asset)}
            unlinkingIds={unlinkingIds}
            onAddAsset={openAddDrawer}
          />

          <Divider className="!my-1" />
          <ChapterShotDialogueConfirmation
            extraction={extractionSummary}
            savedDialogLines={savedDialogLines}
            extractedDialogLines={extractedDialogLines}
            batchDialogAdding={batchDialogAdding}
            dialogLoading={dialogLoading}
            dialogDeletingIds={dialogDeletingIds}
            dialogAddingKeys={dialogAddingKeys}
            onAcceptAll={() => void acceptAllExtractedDialogLines()}
            onIgnoreAll={() => void ignoreAllExtractedDialogLines()}
            onDeleteSavedDialogLine={(lineId) => void deleteSavedDialogLine(lineId)}
            onUpdateSavedDialogText={updateSavedDialogText}
            onAddExtractedDialogLine={(line) => void addExtractedDialogLine(line)}
            onIgnoreExtractedDialogLine={(line) => void ignoreExtractedDialogLine(line)}
            onUpdateExtractedDialogText={updateExtractedDialogText}
            onAddDraftDialogueLine={addDraftDialogueLine}
            draftDialogueLine={draftDialogueLine}
            onUpdateDraftDialogueLine={updateDraftDialogueLine}
            onBlurDraftDialogueLine={() => void commitDraftDialogueLine()}
            onDiscardDraftDialogueLine={discardDraftDialogueLine}
            draftDialogueSaving={draftDialogueSaving}
          />
        </div>
      ),
    },
    {
      key: 'generate',
      label: (
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: statusReady ? '#22c55e' : '#f59e0b' }}
          />
          <span>3 生成视频</span>
        </div>
      ),
      children: (
        <ShotVideoGenerationTab
          shot={shot}
          shotDetail={shotDetail}
          preparationState={preparationState}
          videoModels={videoModels}
          selectedVideoModelId={selectedVideoModelId}
          videoModelsLoading={videoModelsLoading}
          videoResolution={videoResolution}
          videoRatio={resolvedVideoRatio}
          videoReadinessReady={firstFrameReadiness?.ready ?? null}
          videoReadinessLoading={firstFrameReadinessLoading}
          referenceMode={videoReferenceMode}
          onReferenceModeChange={setVideoReferenceMode}
          keyframeCandidatesByType={keyframeCandidatesByType}
          keyframeCurrentFileIdByType={{
            first: frameImages.find((x) => x.frame_type === 'first')?.file_id ?? null,
            last: frameImages.find((x) => x.frame_type === 'last')?.file_id ?? null,
            key: frameImages.find((x) => x.frame_type === 'key')?.file_id ?? null,
          }}
          keyframeApplyingFileId={keyframeApplyingFileId}
          onGenerateKeyframe={(frameType) => openKeyframeGenerateModal(frameType)}
          onApplyKeyframe={(frameType, fileId) => void applyKeyframeCandidate(frameType, fileId)}
          quoteNode={
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <Typography.Text strong>积分报价</Typography.Text>
                <div className="mt-1 text-xs text-slate-500">
                  报价随模型、镜头时长和清晰度变化，提交前会使用当前 quote token 校验。
                </div>
              </div>
              <div className="text-sm">
                {videoQuote.loading ? (
                  <Typography.Text type="secondary">试算中...</Typography.Text>
                ) : videoQuote.error ? (
                  <Typography.Text type="danger">{videoQuote.error}</Typography.Text>
                ) : videoQuote.quote ? (
                  <Typography.Text>
                    预计消耗 <Typography.Text strong>{videoQuote.quote.required_points.toLocaleString()}</Typography.Text> 积分
                  </Typography.Text>
                ) : (
                  <Typography.Text type="secondary">选择模型并设置时长后显示</Typography.Text>
                )}
              </div>
            </div>
          }
          onModelChange={setSelectedVideoModelId}
          onResolutionChange={setVideoResolution}
          onOpenDiagnostics={() => void openVideoDiagnostics()}
          onOpenPromptPreview={() => void openVideoPromptPreview()}
        />
      ),
    },
    {
      key: 'results',
      label: (
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: shot?.generated_video_file_id ? '#22c55e' : '#cbd5e1' }}
          />
          <span>4 视频结果</span>
        </div>
      ),
      children: <ShotVideoResultsTab shot={shot} />,
    },
  ] as const

  return (
    <Layout style={{ height: '100%', minHeight: 0, background: '#eef2f7' }}>
      <Header
        style={{
          padding: '0 16px',
          background: '#fff',
          borderBottom: '1px solid #e2e8f0',
          boxShadow: '0 2px 4px rgba(0,0,0,0.04)',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}
      >
        <Link
          to={`/projects/${projectId}?tab=chapters`}
          className="text-gray-600 hover:text-blue-600 flex items-center gap-1"
        >
          <ArrowLeftOutlined /> 返回章节列表
        </Link>
        <Divider type="vertical" />

        <div className="min-w-0 flex-1 overflow-hidden">
          <Typography.Text
            strong
            className="truncate block"
            style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
          >
            {chapterIndex !== null ? `第${chapterIndex}章 · ${chapterTitle || '未命名'}` : chapterTitle || '章节'}
          </Typography.Text>
          <Typography.Text
            type="secondary"
            className="text-xs truncate block"
            style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
          >
            分镜准备与信息确认
          </Typography.Text>
        </div>
      </Header>

      <Content
        style={{
          padding: 16,
          minHeight: 0,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <Card
          style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
          bodyStyle={{
            padding: 12,
            flex: 1,
            minHeight: 0,
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {loading ? (
            <div className="flex-1 flex items-center justify-center min-h-[200px]">
              <Spin size="large" />
            </div>
          ) : !shot ? (
            <Empty description="无法加载分镜" />
          ) : (
            <div style={{ flex: 1, minHeight: 0, display: 'flex', gap: 12, overflow: 'hidden' }}>
              <Card
                size="small"
                title={
                  <div className="flex min-w-0 items-center gap-2">
                    <div className="flex w-full items-center gap-2">
                      <Tooltip
                        title={
                          shotsSorted.length > 0
                            ? '当前章节已有分镜；如需重新执行一键自动分镜，请先清空现有分镜'
                            : '自动分镜、自动提取并自动生成资产图片'
                        }
                      >
                        <span className="flex-1">
                          <Button
                            className="w-full"
                            size="small"
                            type="primary"
                            icon={<ReloadOutlined />}
                            onClick={() => {
                              if (shotsSorted.length === 0) {
                                setChapterDivideConfirmOpen(true)
                              }
                            }}
                            loading={chapterDividing || !!chapterDivisionTask}
                            disabled={chapterDividing || !!chapterDivisionTask || shotsSorted.length > 0}
                          >
                            {shotsSorted.length === 0 ? '一键自动分镜' : '需先清空分镜'}
                          </Button>
                        </span>
                      </Tooltip>
                      <Button
                        className="flex-1"
                        size="small"
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={openCreate}
                      >
                        新增分镜
                      </Button>
                    </div>
                  </div>
                }
                style={{
                  width: 320,
                  minWidth: 260,
                  maxWidth: 420,
                  height: '100%',
                  minHeight: 0,
                  overflow: 'hidden',
                  display: 'flex',
                  flexDirection: 'column',
                }}
                bodyStyle={{ padding: 8, flex: 1, minHeight: 0, overflow: 'auto' }}
              >
                <div className="mb-3">
                  <Segmented
                    block
                    size="small"
                    value={shotListFilter}
                    onChange={(value) => setShotListFilter(value as ShotListFilter)}
                    options={shotListFilterOptions}
                  />
                  <div className="mt-2 flex items-center justify-between gap-2 rounded-md bg-slate-50 px-2 py-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-slate-700">{`已选 ${selectedShotIds.length} 条`}</span>
                      <Dropdown menu={{ items: batchActionMenuItems }} trigger={['click']} disabled={!hasSelection}>
                        <Button size="small" type="text" icon={<MoreOutlined />} disabled={!hasSelection}>
                          批量操作
                        </Button>
                      </Dropdown>
                    </div>
                    {hasSelection ? (
                      <Button size="small" type="text" onClick={() => setSelectedShotIds([])}>
                        清空
                      </Button>
                    ) : null}
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <Checkbox
                      checked={allFilteredSelected}
                      indeterminate={partiallyFilteredSelected}
                      onChange={(event) => toggleSelectAllFilteredShots(event.target.checked)}
                    >
                      当前列表全选
                    </Checkbox>
                  </div>
                </div>
                <List
                  size="small"
                  dataSource={filteredShots}
                  locale={{ emptyText: <Empty description="暂无镜头" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
                  renderItem={(item) => {
                    const active = item.id === shotId
                    const selected = selectedShotIds.includes(item.id)
                    const itemBasicReady = !!item.title?.trim() && !!item.script_excerpt?.trim()
                    const itemPreparationBadge = getShotPreparationBadge(item)
                    const itemActionable = isActionablePreparationShot(item) || !itemBasicReady
                    const itemCompleted = itemBasicReady && !itemActionable
                    return (
                      <Dropdown menu={{ items: buildShotContextMenuItems(item) }} trigger={['contextMenu']}>
                        <List.Item
                          onClick={() => handleShotListClick(item.id)}
                          style={{
                            cursor: 'pointer',
                            borderRadius: 10,
                            padding: '8px 10px',
                            background: active
                              ? itemCompleted
                                ? 'rgba(34,197,94,0.12)'
                                : 'rgba(59,130,246,0.10)'
                              : selected
                                ? 'rgba(59,130,246,0.06)'
                              : itemActionable
                                ? 'rgba(245,158,11,0.06)'
                                : itemCompleted
                                  ? 'rgba(34,197,94,0.04)'
                                  : undefined,
                            border: active
                              ? itemCompleted
                                ? '1px solid rgba(34,197,94,0.28)'
                                : '1px solid rgba(59,130,246,0.25)'
                              : selected
                                ? '1px solid rgba(59,130,246,0.18)'
                              : itemActionable
                                ? '1px solid rgba(245,158,11,0.22)'
                                : itemCompleted
                                  ? '1px solid rgba(34,197,94,0.16)'
                                  : '1px solid transparent',
                            boxShadow: active && itemCompleted ? '0 0 0 1px rgba(34,197,94,0.08) inset' : undefined,
                          }}
                        >
                          <div className="flex min-w-0 items-start gap-2">
                            <Checkbox
                              className="mt-1 shrink-0"
                              checked={selected}
                              onClick={(event) => event.stopPropagation()}
                              onChange={(event) => toggleShotSelection(item.id, event.target.checked)}
                            />
                            <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-2">
                            <div className="font-medium truncate">
                              #{item.index} · {item.title?.trim() ? item.title : '未命名镜头'}
                            </div>
                            <div className="flex shrink-0 items-center gap-1">
                              {active && itemCompleted ? (
                                <span
                                  className="inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-medium"
                                  style={{
                                    background: '#dcfce7',
                                    color: '#166534',
                                  }}
                                >
                                  当前已完成
                                </span>
                              ) : null}
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
                            </div>
                          </div>
                          <div className="text-xs text-gray-500 truncate">{item.script_excerpt ?? ''}</div>
                            </div>
                          </div>
                        </List.Item>
                      </Dropdown>
                    )
                  }}
                />
              </Card>

              <Card
                size="small"
                title={
                  <div className="space-y-3 min-w-0">
                    <div className="font-medium">{`镜头 #${shot.index} 详情`}</div>
                    <ChapterShotPreparationGuide
                      statusReady={statusReady}
                      checklistItems={checklistItems}
                      nextStepTitle={nextStepTitle}
                      nextStepDescription={nextStepDescription}
                      onGoToGenerate={goToGenerateTab}
                    />
                  </div>
                }
                style={{
                  flex: 1,
                  minWidth: 0,
                  height: '100%',
                  minHeight: 0,
                  overflow: 'hidden',
                  display: 'flex',
                  flexDirection: 'column',
                }}
                bodyStyle={{ padding: 12, flex: 1, minHeight: 0, overflow: 'auto' }}
              >
                <Tabs
                  activeKey={editorTabKey}
                  onChange={handleEditorTabChange}
                  items={editorTabItems as any}
                />
              </Card>
            </div>
          )}
        </Card>
      </Content>

      <VideoDiagnosticsDrawer
        open={videoDiagnosticsOpen}
        loading={videoDiagnosticsLoading}
        title={videoDiagnosticsTitle}
        readiness={videoDiagnosticsReadiness}
        batchItems={videoDiagnosticsBatchItems}
        onClose={() => setVideoDiagnosticsOpen(false)}
      />

      <Modal
        title="关联资产"
        open={linkingOpen}
        onCancel={() => setLinkingOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setLinkingOpen(false)} disabled={linkingActionLoading}>
            取消
          </Button>,
          <Button
            key="link"
            type="primary"
            loading={linkingActionLoading}
            disabled={!linkingItem?.asset_id}
            onClick={() => void doLink()}
          >
            关联
          </Button>,
        ]}
        width={520}
      >
        <div className="space-y-3">
          <Typography.Text>{linkingHint}</Typography.Text>
          <DisplayImageCard
            title={<div className="truncate">{linkingName || '—'}</div>}
            imageAlt={linkingName || 'asset'}
            imageUrl={linkingThumb}
            placeholder={linkingLoading ? <Spin /> : '暂无图片'}
            enablePreview
            hoverable={false}
            size="small"
            imageHeightClassName="h-44"
          />
        </div>
      </Modal>

      {/* 资产替换选择抽屉：从已关联资产卡片右下角"替换"按钮触发 */}
      <AssetPickerDrawer
        open={replaceDrawerOpen}
        kind={replaceDrawerAsset?.kind ?? 'scene'}
        currentEntityId={replaceDrawerAsset?.id}
        projectId={projectId}
        loading={replaceDrawerLoading}
        onSelect={(newId, newName) => void doReplace(newId, newName)}
        onClose={() => {
          setReplaceDrawerOpen(false)
          setReplaceDrawerAsset(null)
        }}
      />

      {/* 添加关联资产抽屉：从各类别 header "添加关联资产" 按钮触发 */}
      <AssetPickerDrawer
        mode="add"
        open={addDrawerOpen}
        kind={addDrawerKind}
        projectId={projectId}
        loading={addDrawerLoading}
        onSelect={(entityId, entityName) => void doAddLink(entityId, entityName)}
        onClose={() => setAddDrawerOpen(false)}
      />

      <Modal
        title="新增分镜"
        open={createOpen}
        onCancel={closeCreate}
        onOk={() => void submitCreate()}
        confirmLoading={createSubmitting}
        okText="创建"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={createForm} layout="vertical">
          <Form.Item
            name="title"
            label="分镜标题"
            rules={[{ required: true, message: '请输入分镜标题' }]}
          >
            <Input maxLength={120} placeholder="例如：主角推门进入房间" />
          </Form.Item>
          <Form.Item name="script_excerpt" label="剧本摘录">
            <Input.TextArea rows={4} maxLength={1000} placeholder="可选，先补一个简短摘录也可以" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={insertMode?.direction === 'before' ? '向上插入分镜' : '向下插入分镜'}
        open={!!insertMode}
        onCancel={closeInsert}
        onOk={() => void submitInsert()}
        confirmLoading={insertSubmitting}
        okText="插入"
        cancelText="取消"
        destroyOnClose
      >
        {insertMode ? (
          <Typography.Paragraph type="secondary">
            将在“{insertMode.refShot.title?.trim() || `镜头 #${insertMode.refShot.index}`}”
            {insertMode.direction === 'before' ? '之前' : '之后'}插入新镜头。
          </Typography.Paragraph>
        ) : null}
        <Form form={insertForm} layout="vertical">
          <Form.Item
            name="title"
            label="分镜标题"
            rules={[{ required: true, message: '请输入分镜标题' }]}
          >
            <Input maxLength={120} placeholder="例如：镜头切到窗边特写" />
          </Form.Item>
          <Form.Item name="script_excerpt" label="剧本摘录">
            <Input.TextArea rows={4} maxLength={1000} placeholder="可选，先补一个简短摘录也可以" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="视频生成提示词预览"
        open={videoPromptPreviewOpen}
        onCancel={() => {
          if (videoPromptPreviewSubmitting) return
          videoPromptPreviewRequestSeqRef.current += 1
          setVideoPromptPreviewOpen(false)
          setVideoPromptPreviewLoading(false)
          setVideoPromptPreviewDraft('')
          setVideoPromptPreviewShotId(null)
        }}
        width={900}
        destroyOnClose
        footer={
          <div className="flex items-center justify-end gap-3">
            <Button
              onClick={() => {
                videoPromptPreviewRequestSeqRef.current += 1
                setVideoPromptPreviewOpen(false)
                setVideoPromptPreviewLoading(false)
                setVideoPromptPreviewDraft('')
                setVideoPromptPreviewShotId(null)
              }}
              disabled={videoPromptPreviewSubmitting}
            >
              取消
            </Button>
            <PointsCostButton
              type="primary"
              loading={videoPromptPreviewSubmitting}
              quote={videoQuote.quote}
              quoteLoading={videoQuote.loading}
              quoteError={videoQuote.error}
              onClick={() => void submitVideoGeneration()}
            >
              确认生成
            </PointsCostButton>
          </div>
        }
      >
        {videoPromptPreviewLoading ? (
          <div className="py-8 text-center">
            <Spin />
          </div>
        ) : (
          <div className="space-y-3">
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
              <div>参考模式：首帧</div>
              <div>视频比例：{resolvedVideoRatio ?? '未设置'}</div>
              <div>清晰度：{videoResolution}</div>
            </div>
            <TextArea
              rows={14}
              value={videoPromptPreviewDraft}
              onChange={(event) => setVideoPromptPreviewDraft(event.target.value)}
              placeholder="视频提示词"
            />
          </div>
        )}
      </Modal>

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
            ? `预计消耗 ${keyframeImageQuote.quote.required_points} 积分`
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

      <ExtractionConfirmModal
        open={chapterDivideConfirmOpen}
        title="确认一键提取分镜并自动准备"
        onConfirm={() => void handleOneClickExtract()}
        onCancel={() => {
          if (chapterDividing) return
          setChapterDivideConfirmOpen(false)
        }}
        costRows={[
          {
            label: '分镜拆解 + 信息提取（文本各一次）',
            quote: divideQuote.quote,
            loading: divideQuote.loading,
            textMultiplier: 2,
          },
          { label: '自动关联已有资产', free: true },
          {
            label: '新资产图片生成（每张）',
            quote: imageQuote.quote,
            loading: imageQuote.loading,
            noModel: !imageQuote.loading && !imageQuote.quote ? true : undefined,
          },
        ]}
        note="资产图数量由 AI 拆解后生成的分镜数决定，拆解前无法预知；积分不足时对应资产将建档但不生成图片。"
      />

      <ExtractionConfirmModal
        open={extractConfirmOpen}
        title={extractConfirmTarget === 'batch'
          ? `确认批量提取（${selectedShots.filter(s => !s.skip_extraction).length} 条镜头）`
          : '确认提取并自动准备'}
        onConfirm={() => {
          setExtractConfirmOpen(false)
          if (extractConfirmTarget === 'batch') {
            void batchExtractAssets()
          } else {
            void extractAssets()
          }
        }}
        onCancel={() => setExtractConfirmOpen(false)}
        costRows={[
          {
            label: 'AI 信息提取（每条镜头）',
            quote: extractQuote.quote,
            loading: extractQuote.loading,
          },
          { label: '自动关联已有资产', free: true },
          {
            label: '新资产图片生成（每张）',
            quote: imageQuote.quote,
            loading: imageQuote.loading,
            noModel: !imageQuote.loading && !imageQuote.quote ? true : undefined,
          },
        ]}
        note="资产图片数量由 AI 提取结果决定，提取前无法预知；积分不足时对应资产将建档但不生成图片。"
      />
    </Layout>
  )
}
