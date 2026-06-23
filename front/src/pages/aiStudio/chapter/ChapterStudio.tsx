import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Button,
  Card,
  Divider,
  Dropdown,
  Image,
  Input,
  Layout,
  Modal,
  Popover,
  Radio,
  Segmented,
  Select,
  Slider,
  Spin,
  Space,
  Switch,
  Tabs,
  Tag,
  Tooltip,
  message,
} from 'antd'
import {
  AppstoreOutlined,
  ArrowLeftOutlined,
  CameraOutlined,
  CheckCircleOutlined,
  CheckOutlined,
  ClockCircleOutlined,
  CustomerServiceOutlined,
  DeleteOutlined,
  DoubleLeftOutlined,
  DoubleRightOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  FileTextOutlined,
  FullscreenOutlined,
  LinkOutlined,
  MergeCellsOutlined,
  PictureOutlined,
  SettingOutlined,
  SoundOutlined,
  StopOutlined,
  ToolOutlined,
  VideoCameraOutlined,
  ThunderboltOutlined,
  UndoOutlined,
  UploadOutlined,
  PlusOutlined,
  UserOutlined,
  DownloadOutlined,
} from '@ant-design/icons'
import { useLocation, useParams, Link } from 'react-router-dom'
import {
  FilmService,
  LlmService,
  PointsService,
  StudioChaptersService,
  StudioEntitiesService,
  StudioFilesService,
  StudioImageTasksService,
  StudioProjectsService,
  StudioShotCharacterLinksService,
  StudioShotDetailsService,
  StudioShotFrameImagesService,
  StudioShotLinksService,
  StudioShotsService,
} from '../../../services/generated'
import { StudioEntitiesApi } from '../../../services/studioEntities'
import type {
  CameraAngle,
  CameraMovement,
  CameraShotType,
  ChapterRead,
  EntityNameExistenceItem,
  ImageGenerationOptionsRead,
  ModelRead,
  ProviderRead,
  ProjectCostumeLinkRead,
  ShotDetailRead,
  ShotExtractedCandidateRead,
  ShotAssetsOverviewRead,
  ShotFrameImageRead,
  ShotCharacterLinkRead,
  ProjectPropLinkRead,
  ShotFramePromptMappingRead,
  ShotRead,
  ShotVideoReadinessRead,
  ShotRuntimeSummaryRead,
  ProjectSceneLinkRead,
  ShotStatus,
  ShotVideoPromptPackRead,
} from '../../../services/generated'
import { listTaskLinksNormalized } from '../../../services/filmTaskLinks'
import { buildFileDownloadUrl, resolveAssetUrl } from '../assets/utils'
import type { Chapter } from '../../../mocks/data'
import { executeTaskCancel } from '../components/taskActionHelpers'
import { useRelationTaskNotification } from '../components/taskNotificationHelpers'
import { TASK_COPY } from '../components/taskCopy'
import { ChapterStudioBatchToolbar } from './components/ChapterStudioBatchToolbar'
import { ChapterStudioReadinessDiagnosisPanel } from './components/ChapterStudioReadinessDiagnosisPanel'
import { ChapterStudioVideoReadinessPanel } from './components/ChapterStudioVideoReadinessPanel'
import { useGenerationDraft, type GenerationDraftState } from '../hooks/useGenerationDraft'
import { usePointsQuote } from '../../../hooks/usePointsQuote'
import { PointsCostHint } from '../../../components/points/PointsCostHint'
import { makePointsAwareGetErrorMessage } from '../../../components/points/pointsTaskError'
import { useTaskPageContext } from '../components/taskPageContext'
import type { RelationTaskState } from '../project/ProjectWorkbench/chapterDivisionTasks'
import { toRelationTaskStateFromStatusRead } from '../project/ProjectWorkbench/chapterDivisionTasks'
import { useProjectStyleOptions } from '../project/useProjectStyleOptions'
import './chapterStudio.separation.css'

const { Sider, Content } = Layout
const { TextArea } = Input

type ShotFramePromptDebugContext = Record<string, unknown>
type ShotFramePromptQualityChecks = {
  passed: boolean
  issues: string[]
} | null
type FramePromptDerived = {
  basePrompt: string
  renderedPrompt: string
  selectedGuidance: string[]
  droppedGuidance: string[]
  selectedGuidanceDetails: Array<{ text: string; category: string; reasonTag: string; reason: string }>
  droppedGuidanceDetails: Array<{ text: string; category: string; reasonTag: string; reason: string }>
  images: string[]
  mappings: ShotFramePromptMappingRead[]
}
type VideoReferenceMode = 'first' | 'last' | 'key' | 'first_last' | 'first_last_key' | 'text_only'
type VideoPromptDerived = {
  prompt: string
  images: string[]
  pack: ShotVideoPromptPackRead | null
}
type GeneratedVideoItem = { linkId: number; fileId: string; url: string }
type VideoModelOption = ModelRead & {
  provider_name: string
}

type FullscreenCapableVideo = HTMLVideoElement & {
  webkitRequestFullscreen?: () => Promise<void> | void
  msRequestFullscreen?: () => Promise<void> | void
}

/** 切换单个结果卡片内的视频播放状态，让中间区域可以直接快速预览。 */
function toggleVideoPlayback(video: HTMLVideoElement | null): void {
  if (!video) return
  if (video.paused) {
    void video.play().catch(() => undefined)
    return
  }
  video.pause()
}

/** 安全触发浏览器原生全屏，兼容常见旧版 WebKit/MS 前缀实现。 */
function requestVideoFullscreen(video: HTMLVideoElement | null): void {
  if (!video) {
    message.warning('当前视频暂不可全屏播放')
    return
  }
  const target = video as FullscreenCapableVideo
  const request = target.requestFullscreen ?? target.webkitRequestFullscreen ?? target.msRequestFullscreen
  if (!request) {
    message.warning('当前浏览器不支持全屏播放')
    return
  }
  void request.call(target)
}

/** 展示当前分镜已生成的视频结果，替代旧的大播放器主预览。 */
function GeneratedVideoGrid({
  selectedShot,
  videos,
  selectedVideosByShot,
  onSelectVideo,
  onDeleteVideo,
}: {
  selectedShot: StudioShot | null
  videos: GeneratedVideoItem[]
  selectedVideosByShot: Record<string, string>
  onSelectVideo: (shotId: string, fileId: string) => void
  onDeleteVideo: (item: GeneratedVideoItem) => void
}) {
  const videoRefs = useRef<Record<string, HTMLVideoElement | null>>({})

  if (!selectedShot) {
    return (
      <div className="cs-video-empty">
        <VideoCameraOutlined className="text-2xl text-gray-300" />
        <div className="font-medium text-gray-500">请选择一个分镜</div>
        <div className="text-xs text-gray-400">选择左侧分镜后，这里会展示该分镜已生成的视频结果。</div>
      </div>
    )
  }

  if (videos.length === 0) {
    return (
      <div className="cs-video-empty">
        <VideoCameraOutlined className="text-2xl text-gray-300" />
        <div className="font-medium text-gray-500">当前分镜暂无已生成视频</div>
        <div className="text-xs text-gray-400">请在右侧“视频生成”面板发起生成，完成后会在这里显示小视频列表。</div>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 2xl:grid-cols-2 gap-4">
      {videos.map((item, idx) => (
        <div key={`${item.linkId}-${item.fileId}`} className="cs-video-result-card">
          <div className="cs-video-thumb">
            <video
              ref={(node) => {
                videoRefs.current[item.fileId] = node
              }}
              src={item.url}
              className="h-full w-full object-contain bg-black"
              preload="metadata"
              muted
              playsInline
              onClick={(event) => toggleVideoPlayback(event.currentTarget)}
            />
          </div>
          <div className="mt-2 flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="text-sm font-medium text-gray-700">视频 {idx + 1}</div>
              <div className="truncate text-xs text-gray-400">{item.fileId}</div>
            </div>
            <Space size="small">
              <Tooltip title={selectedVideosByShot[selectedShot.id] === item.fileId ? '已选择' : '选择该视频'}>
                <Button
                  size="small"
                  icon={<CheckOutlined />}
                  type={selectedVideosByShot[selectedShot.id] === item.fileId ? 'primary' : 'default'}
                  onClick={() => onSelectVideo(selectedShot.id, item.fileId)}
                />
              </Tooltip>
              <Tooltip title="全屏播放">
                <Button
                  size="small"
                  icon={<FullscreenOutlined />}
                  onClick={() => requestVideoFullscreen(videoRefs.current[item.fileId] ?? null)}
                />
              </Tooltip>
              <Tooltip title="下载视频">
                <Button
                  size="small"
                  icon={<DownloadOutlined />}
                  onClick={() => window.open(item.url, '_blank', 'noopener,noreferrer')}
                />
              </Tooltip>
              <Tooltip title="删除视频">
                <Button
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => onDeleteVideo(item)}
                />
              </Tooltip>
            </Space>
          </div>
        </div>
      ))}
    </div>
  )
}

function readDebugContextText(
  context: ShotFramePromptDebugContext | null,
  key: string,
): string {
  if (!context) return ''
  const value = context[key]
  return typeof value === 'string' ? value.trim() : ''
}

function buildKeyframeGuidanceSummary(items: string[]): string[] {
  const result: string[] = []
  const seen = new Set<string>()
  items
    .flatMap((item) => item.split('；'))
    .map((item) => item.trim())
    .filter(Boolean)
    .forEach((item) => {
      if (seen.has(item)) return
      seen.add(item)
      result.push(item)
    })
  return result
}

function stripDirectiveLevelPrefix(item: string): string {
  const text = String(item || '').trim()
  if (text.startsWith('必须：')) return text.slice(3).trim()
  if (text.startsWith('优先：')) return text.slice(3).trim()
  return text
}

function parseDirectorCommandSummary(summary: string): Array<{
  level: 'must' | 'prefer'
  text: string
}> {
  return String(summary || '')
    .split('；')
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      if (item.startsWith('必须：')) {
        return { level: 'must' as const, text: item.slice(3).trim() }
      }
      if (item.startsWith('优先：')) {
        return { level: 'prefer' as const, text: item.slice(3).trim() }
      }
      return { level: 'prefer' as const, text: item }
    })
}

function buildGuidanceLevelSummary(
  parsedDirectorCommands: Array<{ level: 'must' | 'prefer'; text: string }>,
  guidanceSummary: string[],
): { must: number; prefer: number; normal: number } {
  const must = parsedDirectorCommands.filter((item) => item.level === 'must').length
  const prefer = parsedDirectorCommands.filter((item) => item.level === 'prefer').length
  const parsedTexts = new Set(parsedDirectorCommands.map((item) => item.text.trim()).filter(Boolean))
  const normal = guidanceSummary
    .map((item) => stripDirectiveLevelPrefix(item))
    .filter((item) => item && !parsedTexts.has(item)).length
  return { must, prefer, normal }
}

function buildActionBeatPhaseTags(summary: string): Array<{ text: string; phaseLabel: string }> {
  return String(summary || '')
    .split('；')
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const matched = item.match(/^\d+\.\s*(触发|峰值|收束)\s*·\s*(.+)$/)
      if (!matched) {
        return { phaseLabel: '阶段', text: item }
      }
      return {
        phaseLabel: matched[1],
        text: matched[2].trim(),
      }
    })
}

type InspectorMode = 'push' | 'overlay'
type ShotFilter = 'all' | 'pendingConfirm' | 'generating' | 'ready' | 'hidden' | 'problem'

type StudioShot = ShotRead & {
  hidden?: boolean
  hasProblem?: boolean
  hasSpeech?: boolean
  hasMusic?: boolean
}

type ShotRuntimeState = {
  has_active_tasks: boolean
  has_active_video_tasks: boolean
  has_active_prompt_tasks: boolean
  has_active_frame_tasks: boolean
  active_task_count: number
}

type LayoutPrefs = {
  leftWidth: number
  rightWidth: number
  inspectorOpen: boolean
  inspectorMode: InspectorMode
  autoOpenInspector: boolean
  timelineCollapsed: boolean
}

type KeyframeCardState = {
  loading: boolean
  taskStatus: string | null
  taskId: string | null
  thumbs: Array<{ linkId: number; fileId: string; thumbUrl: string }>
  modalOpen: boolean
  applyingFileId: string | null
}

type KeyframeResolutionProfile = 'standard' | 'high'

type InspectorTabKey = 'camera' | 'prompt_image' | 'keyframe_gen' | 'gen_ref'

const LAYOUT_STORAGE_KEY = 'jellyfish_chapter_studio_layout_v1'
type PromptFrameType = 'first' | 'key' | 'last'

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n))
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function getResolutionProfileLabel(profile: KeyframeResolutionProfile): string {
  return profile === 'high' ? '高清（3K）' : '标准（2K）'
}

function resolveKeyframePixelSize(
  options: ImageGenerationOptionsRead | null,
  ratio: string,
  profile: KeyframeResolutionProfile,
): string {
  const normalizedRatio = String(ratio ?? '').trim()
  if (!options || !normalizedRatio) return ''
  const profiles = options.ratio_size_profiles?.[normalizedRatio] ?? null
  if (!profiles) return ''
  return profiles[profile] ?? profiles.standard ?? ''
}

function mapGenerationDraftStateToRenderState(
  state: GenerationDraftState,
): 'idle' | 'stale' | 'syncing' | 'clean' | 'error' {
  if (state === 'derived' || state === 'submitted') return 'clean'
  if (state === 'deriving' || state === 'submitting') return 'syncing'
  if (state === 'draft_changed' || state === 'context_changed') return 'stale'
  if (state === 'error') return 'error'
  return 'idle'
}

function getKeyframeRenderStatusMeta(state: GenerationDraftState) {
  const renderState = mapGenerationDraftStateToRenderState(state)
  if (renderState === 'clean') {
    return {
      color: 'green' as const,
      label: '已同步',
      description: '当前最终提示词已与基础提示词和参考图顺序保持一致。',
    }
  }
  if (renderState === 'syncing') {
    return {
      color: 'blue' as const,
      label: '同步中',
      description: '正在根据当前基础提示词和参考图顺序更新最终提示词…',
    }
  }
  if (renderState === 'error') {
    return {
      color: 'red' as const,
      label: '同步失败',
      description: '自动更新失败，请重试。若问题持续存在，请检查基础提示词和参考图。',
    }
  }
  if (renderState === 'idle') {
    return {
      color: 'default' as const,
      label: '待生成',
      description: '请先输入基础提示词，系统会自动生成最终提示词。',
    }
  }
  return {
    color: 'gold' as const,
    label: '待同步',
    description: '基础提示词或参考图顺序已变化，最终提示词正在等待更新。',
  }
}

function applyTaskCancelState(
  currentTask: RelationTaskState | null,
  data?: { task_id?: string | null; status?: string | null; cancel_requested?: boolean | null } | null,
): RelationTaskState | null {
  if (!currentTask) return null
  return {
    ...currentTask,
    taskId: data?.task_id || currentTask.taskId,
    status: (data?.status ?? currentTask.status) as RelationTaskState['status'],
    cancelRequested: data?.cancel_requested ?? true,
  }
}

function reorder<T>(list: T[], startIndex: number, endIndex: number) {
  const result = [...list]
  const [removed] = result.splice(startIndex, 1)
  result.splice(endIndex, 0, removed)
  return result
}

function normalizeAssetName(value?: string | null) {
  return String(value ?? '').trim().toLowerCase()
}

function uniqueNames(values: Array<string | null | undefined>) {
  const seen = new Set<string>()
  const result: string[] = []
  values.forEach((value) => {
    const raw = String(value ?? '').trim()
    if (!raw) return
    const key = normalizeAssetName(raw)
    if (!key || seen.has(key)) return
    seen.add(key)
    result.push(raw)
  })
  return result
}

function isTypingTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName.toLowerCase()
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return true
  if (target.isContentEditable) return true
  return Boolean(target.closest('[contenteditable="true"]'))
}

function toUIChapter(c: ChapterRead): Chapter {
  return {
    id: c.id,
    projectId: c.project_id,
    index: c.index,
    title: c.title,
    summary: c.summary ?? '',
    storyboardCount: c.shot_count ?? c.storyboard_count ?? 0,
    status: c.status ?? 'draft',
    updatedAt: new Date().toISOString(),
  }
}

const CAMERA_SHOT_OPTIONS: { value: CameraShotType; label: string }[] = [
  { value: 'ECU', label: '极特写' },
  { value: 'CU', label: '特写' },
  { value: 'MCU', label: '中近景' },
  { value: 'MS', label: '中景' },
  { value: 'MLS', label: '中远景' },
  { value: 'LS', label: '远景' },
  { value: 'ELS', label: '大全景' },
]

const CAMERA_ANGLE_OPTIONS: { value: CameraAngle; label: string }[] = [
  { value: 'EYE_LEVEL', label: '平视' },
  { value: 'HIGH_ANGLE', label: '俯视' },
  { value: 'LOW_ANGLE', label: '仰视' },
  { value: 'BIRD_EYE', label: '鸟瞰' },
  { value: 'DUTCH', label: '倾斜' },
  { value: 'OVER_SHOULDER', label: '越肩' },
]

const CAMERA_MOVEMENT_OPTIONS: { value: CameraMovement; label: string }[] = [
  { value: 'STATIC', label: '固定' },
  { value: 'PAN', label: '摇镜' },
  { value: 'TILT', label: '俯仰' },
  { value: 'DOLLY_IN', label: '推进' },
  { value: 'DOLLY_OUT', label: '拉出' },
  { value: 'TRACK', label: '跟拍' },
  { value: 'CRANE', label: '升降' },
  { value: 'HANDHELD', label: '手持' },
  { value: 'STEADICAM', label: '稳定器' },
  { value: 'ZOOM_IN', label: '变焦推' },
  { value: 'ZOOM_OUT', label: '变焦拉' },
]

const VIDEO_DURATION_MIN_SECONDS = 3
const VIDEO_DURATION_MAX_SECONDS = 15

function normalizeVideoDurationSeconds(value: number | null | undefined): number {
  // Keep the studio duration aligned with HappyHorse's official 3-15s integer range.
  const rounded = Number.isFinite(Number(value)) ? Math.round(Number(value)) : VIDEO_DURATION_MIN_SECONDS
  return Math.max(VIDEO_DURATION_MIN_SECONDS, Math.min(VIDEO_DURATION_MAX_SECONDS, rounded))
}

function useLocalStoragePrefs() {
  const [prefs, setPrefs] = useState<LayoutPrefs>(() => {
    try {
      const raw = window.localStorage.getItem(LAYOUT_STORAGE_KEY)
      if (!raw) {
        return {
          leftWidth: 280,
          rightWidth: 420,
          inspectorOpen: false,
          inspectorMode: 'push',
          autoOpenInspector: true,
          timelineCollapsed: false,
        }
      }
      const parsed = JSON.parse(raw) as Partial<LayoutPrefs>
      return {
        leftWidth: typeof parsed.leftWidth === 'number' ? parsed.leftWidth : 280,
        rightWidth: typeof parsed.rightWidth === 'number' ? parsed.rightWidth : 420,
        inspectorOpen: typeof parsed.inspectorOpen === 'boolean' ? parsed.inspectorOpen : false,
        inspectorMode: parsed.inspectorMode === 'overlay' ? 'overlay' : 'push',
        autoOpenInspector: typeof parsed.autoOpenInspector === 'boolean' ? parsed.autoOpenInspector : true,
        timelineCollapsed: typeof parsed.timelineCollapsed === 'boolean' ? parsed.timelineCollapsed : false,
      }
    } catch {
      return {
        leftWidth: 280,
        rightWidth: 420,
        inspectorOpen: false,
        inspectorMode: 'push',
        autoOpenInspector: true,
        timelineCollapsed: false,
      }
    }
  })

  useEffect(() => {
    window.localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(prefs))
  }, [prefs])

  return [prefs, setPrefs] as const
}

const ChapterStudio: React.FC = () => {
  const { projectId, chapterId } = useParams<{
    projectId?: string
    chapterId?: string
  }>()
  const location = useLocation()
  const [chapter, setChapter] = useState<Chapter | null>(null)
  const [projectVisualStyle, setProjectVisualStyle] = useState<string>('现实')
  const [projectStyle, setProjectStyle] = useState<string>('真人都市')
  const [projectDefaultVideoRatio, setProjectDefaultVideoRatio] = useState<string>('')
  const { videoRatioOptions, defaultVideoRatio: capabilityDefaultVideoRatio } = useProjectStyleOptions()
  const [imageGenerationOptions, setImageGenerationOptions] = useState<ImageGenerationOptionsRead | null>(null)
  const [shots, setShots] = useState<StudioShot[]>([])
  const [shotRuntimeMap, setShotRuntimeMap] = useState<Record<string, ShotRuntimeState>>({})
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null)
  const [selectedShotIds, setSelectedShotIds] = useState<string[]>([])
  const locationSelectionAppliedRef = useRef(false)
  const lastSelectedIndexRef = useRef<number>(-1)
  const [shotDetail, setShotDetail] = useState<ShotDetailRead | null>(null)
  const [frameImages, setFrameImages] = useState<ShotFrameImageRead[]>([])
  const [sceneLinks, setSceneLinks] = useState<ProjectSceneLinkRead[]>([])
  const [propLinks, setPropLinks] = useState<ProjectPropLinkRead[]>([])
  const [costumeLinks, setCostumeLinks] = useState<ProjectCostumeLinkRead[]>([])
  const [shotCharacterLinks, setShotCharacterLinks] = useState<ShotCharacterLinkRead[]>([])
  const [shotCandidateItems, setShotCandidateItems] = useState<ShotExtractedCandidateRead[]>([])
  const shotCandidatesRequestSeqRef = useRef(0)
  const [shotDurations, setShotDurations] = useState<Record<string, number>>({})
  // 批量视频生成配置（ChapterStudio 作用域，独立于 Inspector 的单次提交配置）。
  // 批量按钮位于视频结果区，需要自己的模型与清晰度选择；因每个分镜时长不同，
  // quote_token 的 params_hash 绑定 duration_seconds，故批量无法复用单一凭证，
  // 必须在循环内逐镜试算。
  const [batchVideoModels, setBatchVideoModels] = useState<VideoModelOption[]>([])
  const [batchVideoModelsLoading, setBatchVideoModelsLoading] = useState(false)
  const [batchVideoModelId, setBatchVideoModelId] = useState<string | null>(null)
  const [batchVideoModelPickerOpen, setBatchVideoModelPickerOpen] = useState(false)
  const [batchVideoResolution, setBatchVideoResolution] = useState<'720p' | '1080p'>('720p')
  const batchVideoModel = useMemo(
    () => batchVideoModels.find((item) => item.id === batchVideoModelId) ?? null,
    [batchVideoModelId, batchVideoModels],
  )
  const [loadingShots, setLoadingShots] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [prefs, setPrefs] = useLocalStoragePrefs()
  // 分镜帧图片生成的积分试算（ChapterStudio 作用域）。图片模型由后端按用户默认解析，
  // 故 modelId 恒为 null。本报价服务于 ChapterStudio 内的两处调用点：
  // 批量生成（runBatchGenerate）与 Ctrl+Enter 生成（generateFrameImageTask）。
  // 关键帧预览弹窗位于 Inspector 子组件，独立持有自己的 imageQuote（见 Inspector 内）。
  // 分镜帧分辨率档位（standard=1K/high=2K）：声明前置以供本 imageQuote 绑定，保证试算与
  // 创建任务提交的 resolution_profile 一致（否则 quote_token params_hash 校验失败）。
  const [keyframeResolutionProfile, setKeyframeResolutionProfile] = useState<KeyframeResolutionProfile>('standard')
  const imageQuote = usePointsQuote({
    businessType: 'image_generation',
    category: 'image',
    modelId: null,
    resolutionProfile: keyframeResolutionProfile,
    enabled: true,
  })
  // 批量视频模型加载：与 Inspector 的视频模型选择一致，取 category=video 的启用模型。
  // 独立加载以避免与 Inspector 状态耦合（批量按钮在 ChapterStudio 视频结果区）。
  useEffect(() => {
    let active = true
    setBatchVideoModelsLoading(true)
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
          .filter((model) => activeProviderIds.size === 0 || activeProviderIds.has(model.provider_id))
          .map((model) => ({
            ...model,
            provider_name: providerNameById.get(model.provider_id) ?? model.provider_id,
          }))
        setBatchVideoModels(items)
        setBatchVideoModelId((prev) => {
          if (prev && items.some((item) => item.id === prev)) return prev
          return items[0]?.id ?? null
        })
      } catch {
        if (active) {
          setBatchVideoModels([])
        }
      } finally {
        if (active) {
          setBatchVideoModelsLoading(false)
        }
      }
    })()
    return () => {
      active = false
    }
  }, [])
  const [generating, setGenerating] = useState(false)
  const [batchSkipExtractionUpdating, setBatchSkipExtractionUpdating] = useState(false)
  const [batchVideoReadinessOpen, setBatchVideoReadinessOpen] = useState(false)
  const [batchVideoReadinessLoading, setBatchVideoReadinessLoading] = useState(false)
  const [batchVideoReadinessItems, setBatchVideoReadinessItems] = useState<
    Array<{ shot: StudioShot; readiness: ShotVideoReadinessRead | null; error?: string }>
  >([])
  const [batchGenerating, setBatchGenerating] = useState(false)
  const [batchGenerateProgress, setBatchGenerateProgress] = useState<{ current: number; total: number } | null>(null)
  const [batchDownloading, setBatchDownloading] = useState(false)
  const [batchDownloadProgress, setBatchDownloadProgress] = useState<{ current: number; total: number } | null>(null)
  const [saving, setSaving] = useState(false)
  const saveTimerRef = useRef<number | null>(null)
  const cameraPatchSeqRef = useRef(0)
  const [cameraUpdating, setCameraUpdating] = useState(false)
  const [promptAssetsUpdating, setPromptAssetsUpdating] = useState(false)

  const [videoResolutionProfile, setVideoResolutionProfile] = useState<'720p' | '1080p'>('720p')
  const [generatedVideos, setGeneratedVideos] = useState<GeneratedVideoItem[]>([])
  /** shotId → 该分镜被选中的视频 fileId */
  const [selectedVideosByShot, setSelectedVideosByShot] = useState<Record<string, string>>({})
  const [videoResultsRefreshKey, setVideoResultsRefreshKey] = useState(0)

  const [filter, setFilter] = useState<ShotFilter>('all')
  const [editingTitleId, setEditingTitleId] = useState<string | null>(null)
  const [editingTitleValue, setEditingTitleValue] = useState('')
  const [draggingShotId, setDraggingShotId] = useState<string | null>(null)
  const [dragOverShotId, setDragOverShotId] = useState<string | null>(null)
  const [isResizing, setIsResizing] = useState(false)

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const res = await LlmService.getImageGenerationOptionsApiV1LlmImageGenerationOptionsGet({})
        if (!active) return
        setImageGenerationOptions(res.data ?? null)
      } catch {
        if (!active) return
        setImageGenerationOptions(null)
      }
    })()
    return () => {
      active = false
    }
  }, [])

  const containerRef = useRef<HTMLDivElement | null>(null)
  const dragStateRef = useRef<null | { type: 'left' | 'right'; startX: number; startLeft: number; startRight: number }>(null)
  const resizeRafRef = useRef<number | null>(null)
  const pendingResizeRef = useRef<null | { leftWidth?: number; rightWidth?: number }>(null)
  const resolveShotVideoRatio = useCallback(
    (detail?: ShotDetailRead | null) => {
      const shotRatio = String(detail?.override_video_ratio ?? '').trim()
      const projectRatio = String(projectDefaultVideoRatio ?? '').trim()
      const fallbackRatio = String(capabilityDefaultVideoRatio ?? '').trim()
      return shotRatio || projectRatio || fallbackRatio
    },
    [capabilityDefaultVideoRatio, projectDefaultVideoRatio],
  )

  const hiddenKey = useMemo(() => (chapterId ? `jellyfish_hidden_shots_${chapterId}` : null), [chapterId])
  const hiddenIds = useMemo(() => {
    if (!hiddenKey) return new Set<string>()
    try {
      const raw = window.localStorage.getItem(hiddenKey)
      const arr = raw ? (JSON.parse(raw) as unknown) : []
      return new Set(Array.isArray(arr) ? (arr.filter((x) => typeof x === 'string') as string[]) : [])
    } catch {
      return new Set<string>()
    }
  }, [hiddenKey])

  const saveHiddenIds = (next: Set<string>) => {
    if (!hiddenKey) return
    try {
      window.localStorage.setItem(hiddenKey, JSON.stringify(Array.from(next)))
    } catch {
      // ignore
    }
  }

  const toggleHiddenShots = (ids: string[]) => {
    if (!hiddenKey) return
    const next = new Set(hiddenIds)
    ids.forEach((id) => {
      if (next.has(id)) next.delete(id)
      else next.add(id)
    })
    saveHiddenIds(next)
    setShots((prev) => prev.map((s) => (ids.includes(s.id) ? { ...s, hidden: next.has(s.id) } : s)))
  }

  const loadShots = async () => {
    if (!chapterId) return
    setLoadingShots(true)
    try {
      const [res, runtimeRes] = await Promise.all([
        StudioShotsService.listShotsApiV1StudioShotsGet({
          chapterId,
          page: 1,
          pageSize: 100,
          order: 'index',
          isDesc: false,
        }),
        StudioShotsService.listShotRuntimeSummaryApiV1StudioShotsRuntimeSummaryGet({
          chapterId,
        }),
      ])
      const arr = res.data?.items ?? []
      const runtimeItems: ShotRuntimeSummaryRead[] = runtimeRes.data ?? []
      setShotRuntimeMap(
        Object.fromEntries(
          runtimeItems.map((item) => [
            item.shot_id,
            {
              has_active_tasks: item.has_active_tasks,
              has_active_video_tasks: item.has_active_video_tasks,
              has_active_prompt_tasks: item.has_active_prompt_tasks,
              has_active_frame_tasks: item.has_active_frame_tasks,
              active_task_count: item.active_task_count,
            },
          ]),
        ),
      )
      // 给分镜补充一些“工作台态”的展示字段（后续可由后端返回）
      const enriched: StudioShot[] = arr
        .slice()
        .sort((a, b) => a.index - b.index)
        .map((s, idx) => ({
          ...s,
          hidden: hiddenIds.has(s.id),
          hasProblem: idx === 4,
          hasSpeech: false,
          hasMusic: idx % 3 !== 0,
        }))

      setShots(enriched)

      const locationState = location.state as { focusShotId?: string; selectedShotIds?: string[] } | null
      if (!locationSelectionAppliedRef.current && locationState) {
        const nextSelectedIds = (locationState.selectedShotIds ?? []).filter((id) =>
          enriched.some((shot) => shot.id === id),
        )
        const focusShotId =
          locationState.focusShotId && enriched.some((shot) => shot.id === locationState.focusShotId)
            ? locationState.focusShotId
            : nextSelectedIds[0] ?? null

        if (nextSelectedIds.length > 0) {
          setSelectedShotIds(nextSelectedIds)
        }
        if (focusShotId) {
          setSelectedShotId(focusShotId)
        }
        locationSelectionAppliedRef.current = true
        return
      }

      const selectedExists = selectedShotId ? enriched.some((s) => s.id === selectedShotId) : false
      if (!selectedShotId || !selectedExists) {
        const firstUnfinished = enriched.find((s) => !s.hidden && s.status !== 'ready')
        const firstVisible = enriched.find((s) => !s.hidden)
        setSelectedShotId((firstUnfinished ?? firstVisible ?? enriched[0])?.id ?? null)
      }
    } catch {
      message.error('加载分镜失败')
    } finally {
      setLoadingShots(false)
    }
  }

  const patchShotInList = (shotId: string, patch: Partial<StudioShot>) => {
    setShots((prev) => prev.map((s) => (s.id === shotId ? { ...s, ...patch } : s)))
  }

  const loadChapter = async () => {
    if (!chapterId) return
    try {
      const [chapterRes, projectRes] = await Promise.all([
        StudioChaptersService.getChapterApiV1StudioChaptersChapterIdGet({ chapterId }),
        projectId ? StudioProjectsService.getProjectApiV1StudioProjectsProjectIdGet({ projectId }) : Promise.resolve(null),
      ])
      const data = chapterRes.data
      if (!data) {
        setChapter(null)
        return
      }
      setChapter(toUIChapter(data))
      const nextVisualStyle = projectRes?.data?.visual_style
      const nextStyle = projectRes?.data?.style
      const nextDefaultRatio = typeof projectRes?.data?.default_video_ratio === 'string' ? projectRes.data.default_video_ratio : ''
      if (typeof nextVisualStyle === 'string' && nextVisualStyle.trim()) {
        setProjectVisualStyle(nextVisualStyle)
      }
      if (typeof nextStyle === 'string' && nextStyle.trim()) {
        setProjectStyle(nextStyle)
      }
      setProjectDefaultVideoRatio(nextDefaultRatio)
    } catch {
      // 章节信息仅用于标题展示，失败不阻断工作台
      setChapter(null)
      setProjectDefaultVideoRatio('')
    }
  }

  useEffect(() => {
    void loadShots()
    void loadChapter()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapterId, location.state, projectId])

  useEffect(() => {
    if (!selectedShotId) {
      shotCandidatesRequestSeqRef.current += 1
      setShotDetail(null)
      setFrameImages([])
      setSceneLinks([])
      setPropLinks([])
      setCostumeLinks([])
      setShotCharacterLinks([])
      setShotCandidateItems([])
      return
    }
    setLoadingDetail(true)
    const reqSeq = ++shotCandidatesRequestSeqRef.current
    setShotCandidateItems([])
    Promise.all([
      StudioShotDetailsService.getShotDetailApiV1StudioShotDetailsShotIdGet({ shotId: selectedShotId }).then((r: any) => r.data ?? null),
      StudioShotFrameImagesService.listShotFrameImagesApiV1StudioShotFrameImagesGet({
        shotDetailId: selectedShotId,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      }).then((r: any) => r.data?.items ?? []),
      StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
        entityType: 'scene',
        projectId: projectId ?? null,
        chapterId: chapterId ?? null,
        shotId: selectedShotId,
        assetId: null,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      }).then((r: any) => r.data?.items ?? []),
      StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
        entityType: 'prop',
        projectId: projectId ?? null,
        chapterId: chapterId ?? null,
        shotId: selectedShotId,
        assetId: null,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      }).then((r: any) => r.data?.items ?? []),
      StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
        entityType: 'costume',
        projectId: projectId ?? null,
        chapterId: chapterId ?? null,
        shotId: selectedShotId,
        assetId: null,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      }).then((r: any) => r.data?.items ?? []),
      StudioShotCharacterLinksService.listShotCharacterLinksApiV1StudioShotCharacterLinksGet({
        shotId: selectedShotId,
      }).then((r: any) => (r.data ?? []) as ShotCharacterLinkRead[]),
      StudioShotsService.getShotExtractedCandidatesApiV1StudioShotsShotIdExtractedCandidatesGet({
        shotId: selectedShotId,
      }).then((r) => r.data ?? []),
    ])
      .then(([detail, frames, scenes, props, costumes, shotCharacters, candidates]) => {
        if (reqSeq !== shotCandidatesRequestSeqRef.current) return
        setShotDetail(detail)
        lastSavedDetailRef.current = detail
        setFrameImages(frames)
        setSceneLinks(scenes)
        setPropLinks(props)
        setCostumeLinks(costumes)
        setShotCharacterLinks(shotCharacters)
        setShotCandidateItems(candidates as ShotExtractedCandidateRead[])
        if (detail?.duration != null) {
          setShotDurations((prev) => ({ ...prev, [selectedShotId]: detail.duration ?? 0 }))
        }
      })
      .catch(() => {
        if (reqSeq !== shotCandidatesRequestSeqRef.current) return
        message.error('加载分镜详情失败')
      })
      .finally(() => {
        if (reqSeq !== shotCandidatesRequestSeqRef.current) return
        setLoadingDetail(false)
      })
  }, [selectedShotId])

  useEffect(() => {
    // 选中分镜时同步多选的“主选中项”
    if (!selectedShotId) return
    if (selectedShotIds.includes(selectedShotId)) return
    setSelectedShotIds([selectedShotId])
  }, [selectedShotId, selectedShotIds])

  const selectedShot = useMemo(() => shots.find((s) => s.id === selectedShotId) ?? null, [shots, selectedShotId])
  useTaskPageContext(
    selectedShotId
      ? [
          {
            relationType: 'shot',
            relationEntityId: selectedShotId,
          },
        ]
      : [],
  )
  const selectedShots = useMemo(
    () => shots.filter((shot) => selectedShotIds.includes(shot.id)),
    [selectedShotIds, shots],
  )
  useEffect(() => {
    if (!selectedShot?.id) {
      setGeneratedVideos([])
      return
    }
    let canceled = false
    void (async () => {
      try {
        const links = await listTaskLinksNormalized({
          resourceType: 'video',
          relationType: 'video',
          relationEntityId: selectedShot.id,
          order: 'updated_at',
          isDesc: true,
          page: 1,
          pageSize: 100,
        })
        if (canceled) return
        const seen = new Set<string>()
        const list = links
          .filter((link) => Boolean(link.file_id))
          .map((link) => ({
            linkId: link.id,
            fileId: String(link.file_id),
            url: buildFileDownloadUrl(String(link.file_id)) ?? '',
          }))
          .filter((video) => Boolean(video.url))
          .filter((video) => {
            if (seen.has(video.fileId)) return false
            seen.add(video.fileId)
            return true
          })
        const currentId = selectedShot.generated_video_file_id?.trim() || ''
        if (currentId && !list.some((video) => video.fileId === currentId)) {
          const currentUrl = buildFileDownloadUrl(currentId) ?? ''
          if (currentUrl) list.unshift({ linkId: -1, fileId: currentId, url: currentUrl })
        }
        setGeneratedVideos(list)
        // 若该分镜尚未选中视频，默认选中第一条
        if (list.length > 0) {
          setSelectedVideosByShot((prev) =>
            prev[selectedShot.id] ? prev : { ...prev, [selectedShot.id]: list[0].fileId },
          )
        }
      } catch {
        if (!canceled) setGeneratedVideos([])
      }
    })()
    return () => {
      canceled = true
    }
  }, [selectedShot?.id, selectedShot?.generated_video_file_id, videoResultsRefreshKey])

  const handleDeleteVideo = useCallback(
    (item: GeneratedVideoItem) => {
      Modal.confirm({
        title: '删除视频',
        content: '确认删除该视频？此操作不可撤销。',
        okText: '删除',
        okButtonProps: { danger: true },
        cancelText: '取消',
        onOk: async () => {
          try {
            if (item.linkId !== -1) {
              await FilmService.deleteTaskLinkApiV1FilmTaskLinksLinkIdDelete({ linkId: item.linkId })
            }
            await StudioFilesService.deleteFileApiApiV1StudioFilesFileIdDelete({ fileId: item.fileId })
            // 若被删除的视频正好是当前已选中项，清除选中状态
            if (selectedShot && selectedVideosByShot[selectedShot.id] === item.fileId) {
              setSelectedVideosByShot((prev) => {
                const next = { ...prev }
                delete next[selectedShot.id]
                return next
              })
            }
            setVideoResultsRefreshKey((k) => k + 1)
            message.success('视频已删除')
          } catch {
            message.error('删除失败，请稍后重试')
          }
        },
      })
    },
    [selectedShot, selectedVideosByShot],
  )

  const refreshPromptAssetLinks = async (shotId: string) => {
    const [scenes, props, costumes] = await Promise.all([
      StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
        entityType: 'scene',
        projectId: projectId ?? null,
        chapterId: chapterId ?? null,
        shotId,
        assetId: null,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      }).then((r: any) => (r.data?.items ?? []) as ProjectSceneLinkRead[]),
      StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
        entityType: 'prop',
        projectId: projectId ?? null,
        chapterId: chapterId ?? null,
        shotId,
        assetId: null,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      }).then((r: any) => (r.data?.items ?? []) as ProjectPropLinkRead[]),
      StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
        entityType: 'costume',
        projectId: projectId ?? null,
        chapterId: chapterId ?? null,
        shotId,
        assetId: null,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      }).then((r: any) => (r.data?.items ?? []) as ProjectCostumeLinkRead[]),
    ])
    setSceneLinks(scenes)
    setPropLinks(props)
    setCostumeLinks(costumes)
  }

  /** 刷新当前分镜帧图列表，供右侧关键帧/参考图面板在展开选项前拉取最新状态。 */
  const refreshShotFrameImages = useCallback(async () => {
    if (!selectedShotId) return
    try {
      const res = await StudioShotFrameImagesService.listShotFrameImagesApiV1StudioShotFrameImagesGet({
        shotDetailId: selectedShotId,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      })
      setFrameImages((res.data?.items ?? []) as ShotFrameImageRead[])
    } catch {
      message.error('刷新关键帧类型失败')
    }
  }, [selectedShotId])

  const loadShotCandidateItems = useCallback(async (shotId: string) => {
    try {
      const res = await StudioShotsService.getShotExtractedCandidatesApiV1StudioShotsShotIdExtractedCandidatesGet({
        shotId,
      })
      setShotCandidateItems(res.data ?? [])
    } catch {
      setShotCandidateItems([])
    }
  }, [])

  const batchUpdateSkipExtraction = useCallback(
    async (skip: boolean) => {
      const targetShots = selectedShots.filter((shot) => Boolean(shot.skip_extraction) !== skip)
      if (targetShots.length === 0) {
        message.info(skip ? '所选分镜已全部标记为无需提取' : '所选分镜已全部恢复提取')
        return
      }
      setBatchSkipExtractionUpdating(true)
      try {
        const results = await Promise.all(
          targetShots.map(async (shot) => {
            const res = await StudioShotsService.updateShotSkipExtractionApiV1StudioShotsShotIdSkipExtractionPatch({
              shotId: shot.id,
              requestBody: { skip },
            })
            return { shotId: shot.id, data: res.data?.state.shot ?? null }
          }),
        )
        results.forEach(({ shotId, data }) => {
          if (data) {
            patchShotInList(shotId, data as Partial<StudioShot>)
          } else {
            patchShotInList(shotId, { skip_extraction: skip })
          }
        })
        if (selectedShotId && targetShots.some((shot) => shot.id === selectedShotId)) {
          await loadShotCandidateItems(selectedShotId)
        }
        message.success(
          skip
            ? `已批量标记 ${targetShots.length} 条分镜为无需提取`
            : `已批量恢复 ${targetShots.length} 条分镜的提取确认流程`,
        )
      } catch {
        message.error(skip ? '批量标记无需提取失败' : '批量恢复提取失败')
      } finally {
        setBatchSkipExtractionUpdating(false)
      }
    },
    [loadShotCandidateItems, patchShotInList, selectedShotId, selectedShots],
  )

  const fetchBatchVideoReadiness = useCallback(async () => {
    if (selectedShots.length === 0) {
      message.info('请先选择要检查的视频分镜')
      return [] as Array<{ shot: StudioShot; readiness: ShotVideoReadinessRead | null; error?: string }>
    }
    return Promise.all(
      selectedShots
        .slice()
        .sort((a, b) => a.index - b.index)
        .map(async (shot) => {
          try {
            const res = await StudioShotsService.getShotVideoReadinessApiApiV1StudioShotsShotIdVideoReadinessGet({
              shotId: shot.id,
              referenceMode: 'text_only',
            })
            return {
              shot,
              readiness: (res.data ?? null) as ShotVideoReadinessRead | null,
            }
          } catch {
            return {
              shot,
              readiness: null,
              error: '视频准备度检查失败，请稍后重试',
            }
          }
        }),
    )
  }, [selectedShots])

  const batchInspectVideoReadiness = useCallback(async () => {
    setBatchVideoReadinessOpen(true)
    setBatchVideoReadinessLoading(true)
    try {
      const results = await fetchBatchVideoReadiness()
      setBatchVideoReadinessItems(results)
    } finally {
      setBatchVideoReadinessLoading(false)
    }
  }, [fetchBatchVideoReadiness])

  /** 串行为所有可见分镜提交视频生成任务 */
  const handleBatchGenerateAll = useCallback(async () => {
    const ratio = resolveShotVideoRatio(null)
    if (!ratio) {
      message.warning('当前缺少视频比例，请先设置项目默认比例')
      return
    }
    if (!batchVideoModelId) {
      message.warning('请先选择视频模型')
      return
    }
    const targets = shots.filter((s) => !s.hidden)
    if (targets.length === 0) {
      message.warning('没有可见分镜')
      return
    }
    setBatchGenerating(true)
    setBatchGenerateProgress({ current: 0, total: targets.length })
    let successCount = 0
    let failCount = 0
    let skipCount = 0
    for (let i = 0; i < targets.length; i++) {
      const shot = targets[i]
      setBatchGenerateProgress({ current: i + 1, total: targets.length })
      // 批量视频按逐镜试算：quote_token 的 params_hash 绑定 duration_seconds，
      // 各分镜时长不同故无法复用单一凭证。无 duration 的分镜直接跳过（不计失败）。
      const durationSeconds = shotDurations[shot.id] ?? null
      if (!durationSeconds) {
        skipCount++
        continue
      }
      try {
        const previewRes = await FilmService.previewVideoGenerationPromptApiV1FilmTasksVideoPreviewPromptPost({
            requestBody: {
              shot_id: shot.id,
              reference_mode: 'text_only',
              prompt: null,
              images: [],
            ratio,
          } as any,
        })
        const derived = (previewRes as any)?.data ?? null
        const prompt = typeof derived?.prompt === 'string' ? derived.prompt : ''
        const images: string[] = Array.isArray(derived?.images)
          ? (derived.images as string[]).filter(Boolean)
          : []
        // 逐镜试算积分，获取绑定本镜 duration+resolution+model 的 quote_token。
        const quoteRes = await PointsService.quoteMyPointsApiV1PointsQuotePost({
          requestBody: {
            business_type: 'video_generation',
            category: 'video',
            model_id: batchVideoModelId,
            duration_seconds: durationSeconds,
            resolution: batchVideoResolution,
            generation_count: 1,
          },
        })
        const perShotQuoteToken = quoteRes.data?.quote_token ?? null
        if (!perShotQuoteToken) {
          failCount++
          continue
        }
        await FilmService.createVideoGenerationTaskApiV1FilmTasksVideoPost({
          requestBody: {
            shot_id: shot.id,
            model_id: batchVideoModelId,
            reference_mode: 'text_only',
            prompt,
            images,
            ratio: ratio as '16:9' | '4:3' | '1:1' | '3:4' | '9:16' | '21:9',
            resolution: batchVideoResolution,
            quote_token: perShotQuoteToken,
          },
        })
        successCount++
      } catch (error) {
        // 积分不足/报价变更：提示后继续下一镜，避免单个分镜阻塞整批。
        const pointsAware = makePointsAwareGetErrorMessage(() => {})
        const msg = pointsAware(error, '分镜视频生成失败')
        message.error(`分镜 ${String(shot.index).padStart(2, '0')}：${msg}`)
        failCount++
      }
    }
    setBatchGenerating(false)
    setBatchGenerateProgress(null)
    if (failCount === 0 && skipCount === 0) {
      message.success(`已成功提交 ${successCount} 个分镜的视频生成任务`)
    } else {
      const parts = [`${successCount} 成功`]
      if (failCount > 0) parts.push(`${failCount} 失败`)
      if (skipCount > 0) parts.push(`${skipCount} 跳过（无时长）`)
      message.warning(`提交完成：${parts.join('，')}`)
    }
  }, [resolveShotVideoRatio, shots, setBatchGenerating, setBatchGenerateProgress, batchVideoModelId, batchVideoResolution, shotDurations])

  /** 将所有已生成视频下载到用户选择的本地文件夹 */
  /** 下载每个分镜中被选中的视频到用户指定的本地文件夹 */
  const handleBatchDownloadAll = useCallback(async () => {
    // 收集所有已选中的视频：{ shot, fileId, url }
    const targets = shots
      .filter((s) => !s.hidden && selectedVideosByShot[s.id])
      .map((s) => ({
        shot: s,
        fileId: selectedVideosByShot[s.id],
        url: buildFileDownloadUrl(selectedVideosByShot[s.id]) ?? '',
      }))
      .filter((t) => Boolean(t.url))

    if (targets.length === 0) {
      message.warning('没有已选中的视频，请先在各分镜中点击"√"选择视频')
      return
    }

    setBatchDownloading(true)
    setBatchDownloadProgress({ current: 0, total: targets.length })
    try {
      // 优先使用 File System Access API（Chrome/Edge 86+），支持选择本地文件夹
      if (typeof (window as any).showDirectoryPicker === 'function') {
        let dirHandle: FileSystemDirectoryHandle
        try {
          dirHandle = await (window as any).showDirectoryPicker({ mode: 'readwrite' })
        } catch {
          // 用户取消选择文件夹
          return
        }
        for (let i = 0; i < targets.length; i++) {
          const { shot, fileId, url } = targets[i]
          setBatchDownloadProgress({ current: i + 1, total: targets.length })
          try {
            const resp = await fetch(url)
            const blob = await resp.blob()
            const idx = String(shot.index ?? i + 1).padStart(2, '0')
            const title = (shot.title ?? '').replace(/[\\/:*?"<>|]/g, '_').slice(0, 30)
            const filename = `${idx}_${title}_${fileId.slice(0, 8)}.mp4`
            const fileHandle: FileSystemFileHandle = await dirHandle.getFileHandle(filename, { create: true })
            const writable = await fileHandle.createWritable()
            await writable.write(blob)
            await writable.close()
          } catch {
            // 单个文件失败不中断整体流程
          }
        }
        message.success(`已下载 ${targets.length} 个视频到所选文件夹`)
      } else {
        // 降级：逐个触发 <a download>
        for (let i = 0; i < targets.length; i++) {
          const { shot, fileId, url } = targets[i]
          setBatchDownloadProgress({ current: i + 1, total: targets.length })
          const idx = String(shot.index ?? i + 1).padStart(2, '0')
          const title = (shot.title ?? '').replace(/[\\/:*?"<>|]/g, '_').slice(0, 30)
          const a = document.createElement('a')
          a.href = url
          a.download = `${idx}_${title}_${fileId.slice(0, 8)}.mp4`
          document.body.appendChild(a)
          a.click()
          document.body.removeChild(a)
          await new Promise((r) => setTimeout(r, 300))
        }
        message.success(`已触发 ${targets.length} 个视频下载`)
      }
    } finally {
      setBatchDownloading(false)
      setBatchDownloadProgress(null)
    }
  }, [shots, selectedVideosByShot])

  const runBatchGenerate = useCallback(
    async (targetShotIds: string[]) => {
      for (const id of targetShotIds) {
        const framesRes = await StudioShotFrameImagesService.listShotFrameImagesApiV1StudioShotFrameImagesGet({
          shotDetailId: id,
          order: null,
          isDesc: false,
          page: 1,
          pageSize: 100,
        })
        const frames = framesRes.data?.items ?? []
        const target = frames.find((x) => x.frame_type === 'key') ?? frames[0]
        if (!target) continue

        const detailRes: any = await StudioShotDetailsService.getShotDetailApiV1StudioShotDetailsShotIdGet({ shotId: id })
        const d = detailRes?.data as any
        const prompt =
          (target.frame_type === 'first'
            ? d?.first_frame_prompt
            : target.frame_type === 'last'
              ? d?.last_frame_prompt
              : d?.key_frame_prompt) ?? ''
        if (!String(prompt || '').trim()) continue

        const linked = await StudioShotsService.listShotLinkedAssetsApiV1StudioShotsShotIdLinkedAssetsGet({
          shotId: id,
          page: 1,
          pageSize: 100,
        })
        const items = (linked.data?.items ?? []) as any[]
        const extractFileId = (thumbnail?: string | null): string | null => {
          const v = (thumbnail || '').trim()
          if (!v) return null
          if (!v.includes('/') && !v.includes(':')) return v
          try {
            const url = new URL(v, typeof window !== 'undefined' ? window.location.origin : 'http://localhost')
            const m = url.pathname.match(/\/api\/v1\/studio\/files\/([^/]+)\/download\/?$/)
            if (m?.[1]) return decodeURIComponent(m[1])
          } catch {
            // ignore
          }
          return null
        }
        const imagesPayload = items
          .map((x) => {
            const fileId = typeof x?.file_id === 'string' && x.file_id.trim() ? x.file_id.trim() : extractFileId(x?.thumbnail)
            return fileId
              ? {
                  type: x?.type as any,
                  id: String(x?.id ?? ''),
                  name: String(x?.name ?? x?.id ?? ''),
                  file_id: fileId,
                }
              : null
          })
          .filter(Boolean)
        const targetRatio = resolveShotVideoRatio(d)
        if (!targetRatio) continue
        await StudioImageTasksService.createShotFrameImageGenerationTaskApiV1StudioImageTasksShotShotIdFrameImageTasksPost({
          shotId: id,
          requestBody: {
            frame_type: target.frame_type as any,
            model_id: null,
            prompt,
            images: imagesPayload,
            target_ratio: targetRatio,
            resolution_profile: keyframeResolutionProfile,
            quote_token: imageQuote.quoteToken,
          } as any,
        })
      }
    },
    [keyframeResolutionProfile, resolveShotVideoRatio, imageQuote.quoteToken],
  )

  const updatePromptProps = async (propIds: string[]) => {
    if (!selectedShotId || !projectId) return
    const next = Array.from(new Set(propIds.map((x) => x.trim()).filter(Boolean)))
    setPromptAssetsUpdating(true)
    try {
      const currentLinks = propLinks.filter((l) => (l.shot_id ?? null) === selectedShotId)
      await Promise.all(currentLinks.map((l) => StudioShotLinksService.deleteProjectPropLinkApiV1StudioShotLinksPropLinkIdDelete({ linkId: l.id })))
      await Promise.all(
        next.map((pid) =>
          StudioShotLinksService.createProjectPropLinkApiV1StudioShotLinksPropPost({
            requestBody: { project_id: projectId, chapter_id: chapterId ?? null, shot_id: selectedShotId, asset_id: pid },
          }),
        ),
      )
      await refreshPromptAssetLinks(selectedShotId)
      await loadShotCandidateItems(selectedShotId)
    } catch {
      message.error('更新道具失败')
    } finally {
      setPromptAssetsUpdating(false)
    }
  }

  const updatePromptCostumes = async (costumeIds: string[]) => {
    if (!selectedShotId || !projectId) return
    const next = Array.from(new Set(costumeIds.map((x) => x.trim()).filter(Boolean)))
    setPromptAssetsUpdating(true)
    try {
      const currentLinks = costumeLinks.filter((l) => (l.shot_id ?? null) === selectedShotId)
      await Promise.all(currentLinks.map((l) => StudioShotLinksService.deleteProjectCostumeLinkApiV1StudioShotLinksCostumeLinkIdDelete({ linkId: l.id })))
      await Promise.all(
        next.map((cid) =>
          StudioShotLinksService.createProjectCostumeLinkApiV1StudioShotLinksCostumePost({
            requestBody: { project_id: projectId, chapter_id: chapterId ?? null, shot_id: selectedShotId, asset_id: cid },
          }),
        ),
      )
      await refreshPromptAssetLinks(selectedShotId)
      await loadShotCandidateItems(selectedShotId)
    } catch {
      message.error('更新服装失败')
    } finally {
      setPromptAssetsUpdating(false)
    }
  }

  const updatePromptScene = async (sceneId?: string) => {
    if (!selectedShotId || !projectId) return
    setPromptAssetsUpdating(true)
    try {
      const currentLinks = sceneLinks.filter((l) => (l.shot_id ?? null) === selectedShotId)
      await Promise.all(currentLinks.map((l) => StudioShotLinksService.deleteProjectSceneLinkApiV1StudioShotLinksSceneLinkIdDelete({ linkId: l.id })))
      const nextSceneId = (sceneId ?? '').trim()
      if (nextSceneId) {
        await StudioShotLinksService.createProjectSceneLinkApiV1StudioShotLinksScenePost({
          requestBody: {
            project_id: projectId,
            chapter_id: chapterId ?? null,
            shot_id: selectedShotId,
            asset_id: nextSceneId,
          },
        })
      }
      await refreshPromptAssetLinks(selectedShotId)
      await loadShotCandidateItems(selectedShotId)
      patchShotDetailLocal({ scene_id: nextSceneId || null })
    } catch {
      message.error('更新场景失败')
    } finally {
      setPromptAssetsUpdating(false)
    }
  }

  const updatePromptActors = async (actorIds: string[]) => {
    if (!selectedShotId) return
    const next = Array.from(new Set(actorIds.map((x) => x.trim()).filter(Boolean)))
    const current = shotCharacterLinks
      .slice()
      .sort((a, b) => (a.index ?? 0) - (b.index ?? 0))
      .map((x) => x.character_id)
    const removed = current.filter((id) => !next.includes(id))
    if (removed.length > 0) {
      message.warning('当前接口暂不支持移除已关联角色，仅会新增或重排')
    }
    if (next.length === 0) return
    setPromptAssetsUpdating(true)
    try {
      await Promise.all(
        next.map((characterId, index) =>
          StudioShotCharacterLinksService.upsertShotCharacterLinkApiV1StudioShotCharacterLinksPost({
            requestBody: { shot_id: selectedShotId, character_id: characterId, index, note: '' },
          }),
        ),
      )
      const refreshed = await StudioShotCharacterLinksService.listShotCharacterLinksApiV1StudioShotCharacterLinksGet({ shotId: selectedShotId })
      setShotCharacterLinks((refreshed.data ?? []) as ShotCharacterLinkRead[])
      await loadShotCandidateItems(selectedShotId)
    } catch {
      message.error('更新角色失败')
    } finally {
      setPromptAssetsUpdating(false)
    }
  }

  const generateFrameImageTask = async () => {
    if (!selectedShotId) return
    const target = frameImages.find((x) => x.frame_type === 'key') || frameImages[0]
    if (!target) {
      message.warning('请先添加一张分镜帧图（frame image）')
      return
    }
    const prompt =
      (target.frame_type === 'first'
        ? shotDetail?.first_frame_prompt
        : target.frame_type === 'last'
          ? shotDetail?.last_frame_prompt
          : shotDetail?.key_frame_prompt) ?? ''
    if (!prompt.trim()) {
      message.warning('请先生成或填写提示词')
      return
    }
    setGenerating(true)
    try {
      const linked = await StudioShotsService.listShotLinkedAssetsApiV1StudioShotsShotIdLinkedAssetsGet({
        shotId: selectedShotId,
        page: 1,
        pageSize: 100,
      })
      const items = (linked.data?.items ?? []) as any[]
      const extractFileId = (thumbnail?: string | null): string | null => {
        const v = (thumbnail || '').trim()
        if (!v) return null
        if (!v.includes('/') && !v.includes(':')) return v
        try {
          const url = new URL(v, typeof window !== 'undefined' ? window.location.origin : 'http://localhost')
          const m = url.pathname.match(/\/api\/v1\/studio\/files\/([^/]+)\/download\/?$/)
          if (m?.[1]) return decodeURIComponent(m[1])
        } catch {
          // ignore
        }
        return null
      }
      const imagesPayload = items
        .map((x) => {
          const fileId = typeof x?.file_id === 'string' && x.file_id.trim() ? x.file_id.trim() : extractFileId(x?.thumbnail)
          return fileId
            ? {
                type: x?.type as any,
                id: String(x?.id ?? ''),
                name: String(x?.name ?? x?.id ?? ''),
                file_id: fileId,
              }
            : null
        })
        .filter(Boolean)
      const targetRatio = resolveShotVideoRatio(shotDetail)
      if (!targetRatio) {
        message.warning('请先设置视频比例')
        return
      }
      await StudioImageTasksService.createShotFrameImageGenerationTaskApiV1StudioImageTasksShotShotIdFrameImageTasksPost({
        shotId: selectedShotId,
        requestBody: {
          frame_type: target.frame_type as any,
          model_id: null,
          prompt,
          images: imagesPayload,
          target_ratio: targetRatio,
          resolution_profile: keyframeResolutionProfile,
          quote_token: imageQuote.quoteToken,
        } as any,
      })
      message.success('已创建生成任务')
    } catch (error) {
      // 优先识别积分业务错误（积分不足/报价已变更），命中后刷新报价并返回语义文案。
      const pointsAware = makePointsAwareGetErrorMessage(imageQuote.refresh)
      const fallback = '创建生成任务失败'
      const msg = pointsAware(error, fallback)
      message.error(msg)
    } finally {
      setGenerating(false)
    }
  }

  // 选中分镜后若开启自动展开属性面板：默认展开（尤其是未就绪分镜）
  useEffect(() => {
    if (!selectedShot) return
    if (!prefs.autoOpenInspector) return
    if (prefs.inspectorOpen) return
    // “若无视频则自动展开”：这里用 status !== ready 作为近似判定
    if (selectedShot.status !== 'ready') {
      setPrefs((p) => ({ ...p, inspectorOpen: true }))
    }
  }, [prefs.autoOpenInspector, prefs.inspectorOpen, selectedShot, setPrefs])

  const lastSavedDetailRef = useRef<ShotDetailRead | null>(null)

  const patchShotDetailLocal = (patch: Partial<ShotDetailRead>) => {
    setShotDetail((prev) => (prev ? { ...prev, ...patch } : prev))
  }

  const patchShotDetailImmediate = async (patch: Partial<ShotDetailRead>) => {
    if (!selectedShotId) return
    patchShotDetailLocal(patch)
    setCameraUpdating(true)
    const seq = ++cameraPatchSeqRef.current
    try {
      const r: any = await StudioShotDetailsService.updateShotDetailApiV1StudioShotDetailsShotIdPatch({
        shotId: selectedShotId,
        requestBody: patch as any,
      })
      if (seq !== cameraPatchSeqRef.current) return
      if (r.data) {
        setShotDetail(r.data)
        lastSavedDetailRef.current = r.data
        if (r.data.duration != null) {
          setShotDurations((m) => ({ ...m, [selectedShotId]: r.data?.duration ?? 0 }))
        }
      }
    } catch {
      if (seq !== cameraPatchSeqRef.current) return
      message.error('镜头语言更新失败')
    } finally {
      if (seq === cameraPatchSeqRef.current) setCameraUpdating(false)
    }
  }

  // 自动保存（防抖）：shotDetail 变更后 PATCH 到后端
  useEffect(() => {
    if (!selectedShotId || !shotDetail) return
    if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current)
    setSaving(true)
    saveTimerRef.current = window.setTimeout(() => {
      const prev = lastSavedDetailRef.current
      const next = shotDetail
      const patch: Record<string, unknown> = {}
      const assignIfChanged = <K extends keyof ShotDetailRead>(key: K) => {
        if (prev?.[key] !== next[key]) patch[key] = next[key] ?? null
      }
      assignIfChanged('scene_id')
      // 镜头语言字段（camera_shot/angle/movement/duration）走即时更新，不在此处防抖提交
      // array / object fields
      if (JSON.stringify(prev?.mood_tags ?? null) !== JSON.stringify(next.mood_tags ?? null)) patch.mood_tags = next.mood_tags ?? null
      assignIfChanged('atmosphere')
      assignIfChanged('follow_atmosphere')
      assignIfChanged('has_bgm')
      assignIfChanged('override_video_ratio')
      assignIfChanged('vfx_type')
      assignIfChanged('vfx_note')
      assignIfChanged('first_frame_prompt')
      assignIfChanged('key_frame_prompt')
      assignIfChanged('last_frame_prompt')

      const keys = Object.keys(patch)
      if (keys.length === 0) {
        setSaving(false)
        saveTimerRef.current = null
        return
      }

      void StudioShotDetailsService.updateShotDetailApiV1StudioShotDetailsShotIdPatch({
        shotId: selectedShotId,
        requestBody: patch as any,
      })
        .then((r: any) => {
          if (r.data) {
            setShotDetail(r.data)
            lastSavedDetailRef.current = r.data
            if (r.data.duration != null) {
              setShotDurations((m) => ({ ...m, [selectedShotId]: r.data?.duration ?? 0 }))
            }
          }
        })
        .catch(() => {
          message.error('自动保存失败')
        })
        .finally(() => {
          setSaving(false)
          saveTimerRef.current = null
        })
    }, 1000)
    return () => {
      if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current)
      saveTimerRef.current = null
    }
  }, [selectedShotId, shotDetail])

  // 快捷键：←/→ 切换分镜，P/Ctrl+I 面板，H 隐藏，M 合并，Ctrl/Cmd+Enter 保存并生成
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (isTypingTarget(e.target)) return
      const key = e.key.toLowerCase()

      if (key === 'p' || (key === 'i' && (e.ctrlKey || e.metaKey))) {
        e.preventDefault()
        setPrefs((p) => ({ ...p, inspectorOpen: !p.inspectorOpen }))
        return
      }

      if (key === 'arrowleft' || key === 'arrowright') {
        e.preventDefault()
        const visible = shots.filter((s) => !s.hidden)
        const idx = visible.findIndex((s) => s.id === selectedShotId)
        if (idx === -1) return
        const next = key === 'arrowleft' ? visible[idx - 1] : visible[idx + 1]
        if (next) setSelectedShotId(next.id)
        return
      }

      if ((e.ctrlKey || e.metaKey) && key === 'enter') {
        e.preventDefault()
        void generateFrameImageTask()
        return
      }

      if (key === 'h') {
        e.preventDefault()
        if (!selectedShotId) return
        toggleHiddenShots([selectedShotId])
        return
      }

      if (key === 'm') {
        e.preventDefault()
        if (selectedShotIds.length < 2) {
          message.info('请先多选至少 2 个分镜再合并')
          return
        }
        Modal.confirm({
          title: `合并 ${selectedShotIds.length} 个分镜？`,
          content: '将它们合并为一个新的分镜（Mock 行为）。',
          okText: '合并',
          cancelText: '取消',
          onOk: () => {
            message.success('已合并（Mock）')
          },
        })
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [selectedShotId, selectedShotIds.length, shots, setPrefs])

  const statusTag = (status: ShotStatus | undefined) => {
    const s = status ?? 'pending'
    const map = { pending: 'default', generating: 'processing', ready: 'success' } as const
    const text = { pending: '待确认', generating: '生成中', ready: '已就绪' } as const
    return <Tag color={map[s]}>{text[s]}</Tag>
  }

  const statusDotClass = (status: ShotStatus | undefined) => {
    if (status === 'generating') return 'cs-generating'
    if (status === 'ready') return 'cs-ready'
    return 'cs-pending'
  }

  const getShotReadinessFlags = useCallback((shot: StudioShot) => {
    const runtime = shotRuntimeMap[shot.id]
    const isReady = !shot.hidden && shot.status === 'ready'
    const isGenerating = !shot.hidden && Boolean(runtime?.has_active_tasks)
    const isPendingConfirm = !shot.hidden && shot.status === 'pending'
    const hasProblem = Boolean(shot.hasProblem)
    const missing: string[] = []
    if (isPendingConfirm) missing.push('待确认')
    if (isGenerating) missing.push('生成中')
    return {
      isReady,
      isGenerating,
      isPendingConfirm,
      hasProblem,
      missing,
    }
  }, [shotRuntimeMap])

  const getShotProgressCount = useCallback(
    (shot: StudioShot) => {
      return [shot.status !== 'pending', shot.status === 'ready'].filter(Boolean).length
    },
    [getShotReadinessFlags],
  )

  const getShotPrimaryHint = useCallback(
    (shot: StudioShot) => {
      const flags = getShotReadinessFlags(shot)
      if (flags.hasProblem) return '存在待处理问题'
      if (flags.isGenerating) {
        const runtime = shotRuntimeMap[shot.id]
        return `镜头相关任务进行中（${runtime?.active_task_count ?? 1}）`
      }
      if (flags.isPendingConfirm) {
        return shot.skip_extraction
          ? '已标记无需提取，等待系统完成流程状态同步'
          : '请先完成信息提取确认'
      }
      return '镜头已具备视频生成前置条件'
    },
    [getShotReadinessFlags, shotRuntimeMap],
  )

  const chapterTitle = useMemo(() => {
    if (!chapter) return '章节生成工作台'
    return `第${chapter.index}章 · ${chapter.title.replace(/^第\d+[集章：:\s]*/g, '').trim() || chapter.title}`
  }, [chapter])

  const filteredShots = useMemo(() => {
    const list = shots.slice().sort((a, b) => a.index - b.index)
    switch (filter) {
      case 'pendingConfirm':
        return list.filter((s) => getShotReadinessFlags(s).isPendingConfirm)
      case 'generating':
        return list.filter((s) => getShotReadinessFlags(s).isGenerating)
      case 'ready':
        return list.filter((s) => getShotReadinessFlags(s).isReady)
      case 'hidden':
        return list.filter((s) => Boolean(s.hidden))
      case 'problem':
        return list.filter((s) => !s.hidden && Boolean(s.hasProblem))
      default:
        return list
    }
  }, [filter, getShotReadinessFlags, shots])

  const shotFilterCounts = useMemo(() => {
    const list = shots.slice()
    return {
      all: list.length,
      pendingConfirm: list.filter((s) => getShotReadinessFlags(s).isPendingConfirm).length,
      generating: list.filter((s) => getShotReadinessFlags(s).isGenerating).length,
      ready: list.filter((s) => getShotReadinessFlags(s).isReady).length,
      hidden: list.filter((s) => Boolean(s.hidden)).length,
      problem: list.filter((s) => !s.hidden && Boolean(s.hasProblem)).length,
    } satisfies Record<ShotFilter, number>
  }, [getShotReadinessFlags, shots])

  const multiToolbarVisible = selectedShotIds.length > 1

  const handleSelectShot = (shotId: string, indexInFiltered: number, e: React.MouseEvent) => {
    setSelectedShotId(shotId)
    const isRange = e.shiftKey && lastSelectedIndexRef.current >= 0
    const isToggle = e.ctrlKey || e.metaKey

    if (isRange) {
      const start = Math.min(lastSelectedIndexRef.current, indexInFiltered)
      const end = Math.max(lastSelectedIndexRef.current, indexInFiltered)
      const rangeIds = filteredShots.slice(start, end + 1).map((s) => s.id)
      setSelectedShotIds(Array.from(new Set([...selectedShotIds, ...rangeIds])))
      return
    }

    if (isToggle) {
      setSelectedShotIds((prev) => (prev.includes(shotId) ? prev.filter((id) => id !== shotId) : [...prev, shotId]))
      lastSelectedIndexRef.current = indexInFiltered
      return
    }

    setSelectedShotIds([shotId])
    lastSelectedIndexRef.current = indexInFiltered
  }

  const matchesFilter = (s: StudioShot, f: ShotFilter) => {
    const flags = getShotReadinessFlags(s)
    switch (f) {
      case 'pendingConfirm':
        return flags.isPendingConfirm
      case 'generating':
        return flags.isGenerating
      case 'ready':
        return flags.isReady
      case 'hidden':
        return Boolean(s.hidden)
      case 'problem':
        return !s.hidden && flags.hasProblem
      default:
        return true
    }
  }

  const reorderWithinFilter = (sourceId: string, destId: string) => {
    if (sourceId === destId) return
    setShots((prev) => {
      const ordered = prev.slice().sort((a, b) => a.index - b.index)
      const subset = ordered.filter((s) => matchesFilter(s, filter))
      const sourceIndex = subset.findIndex((s) => s.id === sourceId)
      const destIndex = subset.findIndex((s) => s.id === destId)
      if (sourceIndex === -1 || destIndex === -1) return prev
      const movedSubset = reorder(subset, sourceIndex, destIndex)
      const movedQueue = [...movedSubset]
      const replaced = ordered.map((s) => (matchesFilter(s, filter) ? (movedQueue.shift() as StudioShot) : s))
      const next = replaced.map((s, idx) => ({ ...s, index: idx + 1 }))

      // 后台同步排序（不阻塞 UI）
      const beforeMap = new Map(prev.map((s) => [s.id, s.index]))
      void (async () => {
        try {
          const changed = next.filter((s) => beforeMap.get(s.id) !== s.index)
          await Promise.all(
            changed.map((s) =>
              StudioShotsService.updateShotApiV1StudioShotsShotIdPatch({
                shotId: s.id,
                requestBody: { index: s.index },
              }),
            ),
          )
        } catch {
          message.error('同步排序失败')
        }
      })()

      return next
    })
  }

  const beginResize = (type: 'left' | 'right', e: React.PointerEvent) => {
    if (!containerRef.current) return
    const startX = e.clientX
    dragStateRef.current = {
      type,
      startX,
      startLeft: prefs.leftWidth,
      startRight: prefs.rightWidth,
    }
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    setIsResizing(true)
  }

  const onResizeMove = (e: React.PointerEvent) => {
    const st = dragStateRef.current
    if (!st) return
    const dx = e.clientX - st.startX
    const minLeft = 240
    const maxLeft = 360
    const minRight = 360
    const maxRight = 720
    if (st.type === 'left') {
      pendingResizeRef.current = { leftWidth: clamp(st.startLeft + dx, minLeft, maxLeft) }
    } else {
      // right：推挤/覆盖都复用 width 偏好
      pendingResizeRef.current = { rightWidth: clamp(st.startRight - dx, minRight, maxRight) }
    }

    if (resizeRafRef.current) return
    resizeRafRef.current = window.requestAnimationFrame(() => {
      const pending = pendingResizeRef.current
      pendingResizeRef.current = null
      resizeRafRef.current = null
      if (!pending) return
      setPrefs((p) => ({
        ...p,
        ...(typeof pending.leftWidth === 'number' ? { leftWidth: pending.leftWidth } : null),
        ...(typeof pending.rightWidth === 'number' ? { rightWidth: pending.rightWidth } : null),
      }))
    })
  }

  const endResize = () => {
    dragStateRef.current = null
    pendingResizeRef.current = null
    if (resizeRafRef.current) {
      window.cancelAnimationFrame(resizeRafRef.current)
      resizeRafRef.current = null
    }
    setIsResizing(false)
  }

  const shotContextMenu = (shot: StudioShot) => ([
    {
      key: 'toggle_hide',
      icon: shot.hidden ? <EyeOutlined /> : <EyeInvisibleOutlined />,
      label: shot.hidden ? '取消隐藏' : '隐藏',
      onClick: () => toggleHiddenShots([shot.id]),
    },
    {
      key: 'delete',
      icon: <DeleteOutlined />,
      danger: true,
      label: '删除',
      onClick: () =>
        Modal.confirm({
          title: '删除分镜？',
          content: '此操作不可撤销。',
          okText: '删除',
          okButtonProps: { danger: true },
          cancelText: '取消',
          onOk: async () => {
            try {
              await StudioShotsService.deleteShotApiV1StudioShotsShotIdDelete({ shotId: shot.id })
              await loadShots()
              message.success('已删除')
            } catch {
              message.error('删除失败')
            }
          },
        }),
    },
  ])

  const batchMenuItems = [
    {
      key: 'merge',
      icon: <MergeCellsOutlined />,
      label: '合并',
      disabled: selectedShotIds.length < 2,
      onClick: () => {
        if (selectedShotIds.length < 2) return
        Modal.confirm({
          title: `合并 ${selectedShotIds.length} 个分镜？`,
          okText: '合并',
          cancelText: '取消',
          onOk: () => message.success('已合并（Mock）'),
        })
      },
    },
    {
      key: 'hide',
      icon: <EyeInvisibleOutlined />,
      label: '隐藏',
      onClick: () => toggleHiddenShots(selectedShotIds),
    },
    {
      key: 'delete',
      icon: <DeleteOutlined />,
      danger: true,
      label: '删除',
      onClick: () =>
        Modal.confirm({
          title: `删除 ${selectedShotIds.length} 个分镜？`,
          okText: '删除',
          okButtonProps: { danger: true },
          cancelText: '取消',
          onOk: async () => {
            try {
              await Promise.all(selectedShotIds.map((id) => StudioShotsService.deleteShotApiV1StudioShotsShotIdDelete({ shotId: id })))
              await loadShots()
              message.success('已删除')
            } catch {
              message.error('删除失败')
            }
          },
        }),
    },
    { type: 'divider' as const },
    {
      key: 'skip-extraction',
      icon: <StopOutlined />,
      danger: true,
      label: '维护：标记无需提取',
      onClick: () =>
        Modal.confirm({
          title: `确认以维护方式将 ${selectedShotIds.length} 个分镜标记为无需提取？`,
          content: '这属于准备阶段的维护性调整。标记后这些分镜会直接按“提取确认已完成”处理。',
          okText: '确认',
          okButtonProps: { danger: true, loading: batchSkipExtractionUpdating },
          cancelText: '取消',
          cancelButtonProps: { disabled: batchSkipExtractionUpdating },
          onOk: () => batchUpdateSkipExtraction(true),
        }),
    },
    {
      key: 'restore-extraction',
      icon: <UndoOutlined />,
      label: '维护：恢复提取',
      disabled: batchSkipExtractionUpdating,
      onClick: () => batchUpdateSkipExtraction(false),
    },
    { type: 'divider' as const },
    {
      key: 'generate',
      icon: <ThunderboltOutlined />,
      label: '批量生成',
      onClick: () => {
        if (selectedShotIds.length === 0) return
        Modal.confirm({
          title: `批量生成 ${selectedShotIds.length} 个分镜？`,
          okText: '开始',
          cancelText: '取消',
          onOk: async () => {
            setGenerating(true)
            try {
              const readinessResults = await fetchBatchVideoReadiness()
              const readyShots = readinessResults.filter((item) => item.readiness?.ready)
              const blockedShots = readinessResults.filter((item) => !item.readiness?.ready)

              if (blockedShots.length > 0) {
                setBatchVideoReadinessItems(readinessResults)
                setBatchVideoReadinessOpen(true)
              }

              if (readyShots.length === 0) {
                message.warning('当前选中的分镜都未通过视频准备度检查，已为你展开检查结果')
                return
              }

              if (blockedShots.length > 0) {
                message.warning(`其中 ${blockedShots.length} 条未通过检查，已自动跳过，仅继续生成 ${readyShots.length} 条`)
              }

              await runBatchGenerate(readyShots.map((item) => item.shot.id))
              message.success('已创建批量生成任务')
            } catch (error) {
              // 优先识别积分业务错误（积分不足/报价已变更），命中后刷新报价并返回语义文案。
              const pointsAware = makePointsAwareGetErrorMessage(imageQuote.refresh)
              const fallback = '批量生成失败'
              const msg = pointsAware(error, fallback)
              message.error(msg)
            } finally {
              setGenerating(false)
            }
          },
        })
      },
    },
  ]

  const batchMaintenanceMenuItems = batchMenuItems.filter((item) => item.key !== 'generate')


  return (
    <div className={['cs-studio w-full h-full min-h-0 flex flex-col', isResizing ? 'cs-resizing' : ''].join(' ')} ref={containerRef}>
      {/* 顶部工具栏（常驻） */}
      <div
        className="cs-topbar flex items-center gap-4 px-4 py-3"
        style={{
          flexShrink: 0,
        }}
      >
        <div className="flex items-center gap-2 min-w-0">
          {projectId && (
            <Link
              to={`/projects/${projectId}?tab=chapters`}
              className="text-sm text-gray-600 hover:text-blue-600 flex items-center gap-1 shrink-0"
            >
              <ArrowLeftOutlined /> 返回
            </Link>
          )}
          <Divider type="vertical" />
          <div className="min-w-0">
            <div className="font-medium text-gray-900 truncate">{chapterTitle}</div>
            <div className="text-xs text-gray-500">
              {saving ? (
                <span className="inline-flex items-center gap-1">
                  <ClockCircleOutlined /> 自动保存中…
                </span>
              ) : (
                <span className="inline-flex items-center gap-1">
                  <CheckCircleOutlined /> 已保存
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex-1 min-w-0" />

      </div>

      {/* 三栏动态布局 */}
      <Layout
        className="flex-1 min-h-0"
        style={{
          background: 'transparent',
          position: 'relative',
          overflow: 'hidden',
        }}
        onPointerMove={onResizeMove}
        onPointerUp={endResize}
        onPointerCancel={endResize}
      >
        {/* 左侧：分镜列表 */}
        <Sider
          width={prefs.leftWidth}
          collapsedWidth={0}
          className="cs-left flex flex-col"
          style={{
            overflow: 'hidden',
          }}
        >
          <div className="cs-group m-3 mb-2 flex flex-col gap-2 min-w-0">
            <div className="cs-group-title mb-0 flex items-center gap-2 shrink-0">
              <FileTextOutlined /> 分镜列表
            </div>
            <div className="overflow-x-auto min-w-0 -mx-1 px-1">
              <Segmented
                size="small"
                value={filter}
                onChange={(v) => setFilter(v as ShotFilter)}
                options={[
                  { label: `全部 ${shotFilterCounts.all}`, value: 'all' },
                  { label: `待确认 ${shotFilterCounts.pendingConfirm}`, value: 'pendingConfirm' },
                  { label: `生成中 ${shotFilterCounts.generating}`, value: 'generating' },
                  { label: `已就绪 ${shotFilterCounts.ready}`, value: 'ready' },
                ]}
              />
            </div>
          </div>

          {multiToolbarVisible && (
            <ChapterStudioBatchToolbar
              selectedCount={selectedShotIds.length}
              batchVideoReadinessLoading={batchVideoReadinessLoading}
              generating={generating}
              maintenanceMenuItems={batchMaintenanceMenuItems}
              onBatchInspectVideoReadiness={() => void batchInspectVideoReadiness()}
              onBatchGenerate={() => batchMenuItems.find((item) => item.key === 'generate')?.onClick?.()}
            />
          )}

          <div className="cs-left-scroll px-3 pb-3">
            {loadingShots ? (
              <div className="text-gray-500 text-center py-4">加载中...</div>
            ) : (
              <div>
                {filteredShots.map((s, i) => {
                  const isActive = selectedShotId === s.id
                  const isSelected = selectedShotIds.includes(s.id)
                  const isDragging = draggingShotId === s.id
                  const isDragOver = dragOverShotId === s.id && draggingShotId && draggingShotId !== s.id
                  const readiness = getShotReadinessFlags(s)
                  const progressCount = getShotProgressCount(s)
                  const primaryHint = getShotPrimaryHint(s)
                  return (
                    <div
                      key={s.id}
                      draggable
                      onDragStart={(e) => {
                        setDraggingShotId(s.id)
                        setDragOverShotId(null)
                        e.dataTransfer.effectAllowed = 'move'
                        e.dataTransfer.setData('text/plain', s.id)
                      }}
                      onDragEnter={() => {
                        if (!draggingShotId || draggingShotId === s.id) return
                        setDragOverShotId(s.id)
                      }}
                      onDragOver={(e) => {
                        e.preventDefault()
                        e.dataTransfer.dropEffect = 'move'
                      }}
                      onDrop={(e) => {
                        e.preventDefault()
                        const sourceId = e.dataTransfer.getData('text/plain') || draggingShotId
                        if (!sourceId) return
                        reorderWithinFilter(sourceId, s.id)
                        setDraggingShotId(null)
                        setDragOverShotId(null)
                      }}
                      onDragEnd={() => {
                        setDraggingShotId(null)
                        setDragOverShotId(null)
                      }}
                      style={{
                        opacity: isDragging ? 0.92 : 1,
                        outline: isDragOver ? '2px dashed var(--ant-color-primary)' : 'none',
                        borderRadius: 8,
                      }}
                    >
                      <Dropdown menu={{ items: shotContextMenu(s) }} trigger={['contextMenu']}>
                        <Card
                          size="small"
                          className={[
                            'cs-shot-item mb-2 cursor-pointer transition-colors',
                            isSelected ? 'cs-shot-selected' : '',
                            isActive ? 'cs-shot-active' : '',
                          ].filter(Boolean).join(' ')}
                          style={{
                            opacity: s.hidden ? 0.55 : 1,
                          }}
                          onClick={(e) => handleSelectShot(s.id, i, e)}
                          onDoubleClick={() => {
                            setEditingTitleId(s.id)
                            setEditingTitleValue(s.title)
                          }}
                        >
                            <div className="flex gap-2">
                            <div className="w-16 h-10 rounded bg-gray-200 flex-shrink-0 flex items-center justify-center text-gray-400 text-xs overflow-hidden">
                              <span>16:9</span>
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className={`cs-dot ${statusDotClass(s.status)}`} />
                                <span className="text-xs text-gray-500 shrink-0">
                                  {String(s.index).padStart(2, '0')}
                                </span>
                                {editingTitleId === s.id ? (
                                  <Input
                                    size="small"
                                    value={editingTitleValue}
                                    autoFocus
                                    onChange={(ev) => setEditingTitleValue(ev.target.value)}
                                    onBlur={() => {
                                      const nextTitle = editingTitleValue.trim()
                                      setShots((prev) => prev.map((x) => (x.id === s.id ? { ...x, title: nextTitle || x.title } : x)))
                                      if (nextTitle && nextTitle !== s.title) {
                                        void StudioShotsService.updateShotApiV1StudioShotsShotIdPatch({
                                          shotId: s.id,
                                          requestBody: { title: nextTitle },
                                        }).catch(() => message.error('保存标题失败'))
                                      }
                                      setEditingTitleId(null)
                                    }}
                                    onKeyDown={(ev) => {
                                      if (ev.key === 'Enter') {
                                        (ev.currentTarget as HTMLInputElement).blur()
                                      }
                                      if (ev.key === 'Escape') {
                                        setEditingTitleId(null)
                                      }
                                    }}
                                  />
                                ) : (
                                  <div className="font-medium text-sm truncate" title="双击编辑标题">
                                    {s.title}
                                  </div>
                                )}
                              </div>
                              <div className="text-xs text-gray-500 mt-1 truncate">
                                {shotDetail?.movement ? `${CAMERA_MOVEMENT_OPTIONS.find((x) => x.value === shotDetail.movement)?.label ?? shotDetail.movement} · ` : ''}
                                {((shotDurations[s.id] ?? shotDetail?.duration ?? 0) || 0).toFixed(1)}s
                              </div>
                              <div className="cs-shot-progress mt-1">
                                <div className="cs-shot-progress__dots" aria-hidden="true">
                                  {[0, 1].map((idx) => (
                                    <span
                                      key={idx}
                                      className={[
                                        'cs-shot-progress__dot',
                                        idx < progressCount ? 'is-on' : '',
                                      ].join(' ')}
                                    />
                                  ))}
                                </div>
                                <span className="cs-shot-progress__text">{progressCount}/2</span>
                              </div>
                              <div className="cs-shot-hint mt-1">
                                {primaryHint}
                              </div>
                              <div className="mt-1 flex flex-wrap gap-1 items-center">
                                {readiness.isReady ? (
                                  <Tag className="m-0" color="success">已就绪</Tag>
                                ) : readiness.isGenerating ? (
                                  <Tag className="m-0" color="processing">生成中</Tag>
                                ) : (
                                  <Tag className="m-0" color="gold">待确认</Tag>
                                )}
                                {s.skip_extraction && (
                                  <Tag className="m-0" color="cyan">
                                    无需提取
                                  </Tag>
                                )}
                                {s.hasMusic && <Tag icon={<SoundOutlined />} className="m-0" color="default">音乐</Tag>}
                                {statusTag(s.status)}
                                {s.hidden && <Tag icon={<EyeInvisibleOutlined />} className="m-0">隐藏</Tag>}
                              </div>
                            </div>
                            </div>
                        </Card>
                      </Dropdown>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </Sider>

        {/* 左侧拖拽条 */}
        <div
          role="separator"
          className="cs-sep h-full"
          style={{
            width: 10,
            cursor: 'col-resize',
            background: 'transparent',
            flexShrink: 0,
          }}
          onPointerDown={(e) => beginResize('left', e)}
          title="拖拽调整左侧宽度"
        />

        {/* 中央：视频结果区 */}
        <Content className="cs-main min-w-0 min-h-0 flex flex-col" style={{ padding: 16, position: 'relative', overflow: 'hidden' }}>
          <Card
            title={
              <div className="flex items-center gap-3 min-w-0">
                <span className="font-medium">视频结果区</span>
                {selectedShot && (
                  <span className="text-xs text-gray-500 truncate">
                    当前分镜：{String(selectedShot.index).padStart(2, '0')} · {selectedShot.title}
                  </span>
                )}
              </div>
            }
            extra={
              <div className="flex items-center gap-2">
                <Popover
                  open={batchVideoModelPickerOpen}
                  onOpenChange={setBatchVideoModelPickerOpen}
                  trigger="click"
                  placement="bottomRight"
                  title={<span className="text-sm font-medium">批量视频模型</span>}
                  content={(
                    <div style={{ width: 240 }}>
                      {batchVideoModelsLoading ? (
                        <div className="py-3 text-center text-xs text-gray-400">加载中...</div>
                      ) : batchVideoModels.length === 0 ? (
                        <div className="py-3 text-center text-xs text-gray-400">暂无可用视频模型</div>
                      ) : (
                        <div className="space-y-1">
                          {batchVideoModels.map((model) => (
                            <div
                              key={model.id}
                              role="button"
                              tabIndex={0}
                              onClick={() => {
                                setBatchVideoModelId(model.id)
                                setBatchVideoModelPickerOpen(false)
                              }}
                              onKeyDown={(event) => {
                                if (event.key === 'Enter' || event.key === ' ') {
                                  event.preventDefault()
                                  setBatchVideoModelId(model.id)
                                  setBatchVideoModelPickerOpen(false)
                                }
                              }}
                              className={[
                                'flex cursor-pointer items-start gap-2 rounded px-3 py-2 transition-colors select-none',
                                batchVideoModelId === model.id ? 'bg-blue-50 ring-1 ring-blue-400' : 'hover:bg-gray-50',
                              ].join(' ')}
                            >
                              <div className="flex-1 min-w-0">
                                <div className="truncate text-sm font-medium text-gray-800">{model.name}</div>
                                <Tag className="m-0 mt-0.5 flex-shrink-0 px-1 py-0 text-[10px] leading-4">{model.provider_name}</Tag>
                              </div>
                              {batchVideoModelId === model.id && <CheckOutlined className="mt-0.5 flex-shrink-0 text-blue-500" />}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                >
                  <Button
                    size="small"
                    loading={batchVideoModelsLoading}
                    icon={<AppstoreOutlined />}
                    className="text-left"
                    style={{ justifyContent: 'flex-start' }}
                  >
                    {batchVideoModel ? batchVideoModel.name : '批量模型'}
                  </Button>
                </Popover>
                <Segmented
                  size="small"
                  value={batchVideoResolution}
                  options={[
                    { value: '720p', label: '720p' },
                    { value: '1080p', label: '1080p' },
                  ]}
                  onChange={(value) => setBatchVideoResolution(value as '720p' | '1080p')}
                />
                <Button
                  size="small"
                  loading={batchGenerating}
                  disabled={!batchVideoModelId}
                  onClick={handleBatchGenerateAll}
                >
                  {batchGenerating && batchGenerateProgress
                    ? `生成中 ${batchGenerateProgress.current}/${batchGenerateProgress.total}`
                    : '一键全部生成'}
                </Button>
                <Button
                  size="small"
                  loading={batchDownloading}
                  disabled={generatedVideos.length === 0}
                  onClick={handleBatchDownloadAll}
                >
                  {batchDownloading && batchDownloadProgress
                    ? `下载中 ${batchDownloadProgress.current}/${batchDownloadProgress.total}`
                    : '一键全部下载'}
                </Button>
                <Tag className="m-0" color={generatedVideos.length > 0 ? 'blue' : 'default'}>
                  已生成 {generatedVideos.length}
                </Tag>
              </div>
            }
            className="cs-preview-card flex-1 min-h-0"
            bodyStyle={{ height: '100%', minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', gap: 12 }}
          >
            <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden pr-1">
              <GeneratedVideoGrid
                selectedShot={selectedShot}
                videos={generatedVideos}
                selectedVideosByShot={selectedVideosByShot}
                onSelectVideo={(shotId, fileId) =>
                  setSelectedVideosByShot((prev) => {
                    if (prev[shotId] === fileId) {
                      const next = { ...prev }
                      delete next[shotId]
                      return next
                    }
                    return { ...prev, [shotId]: fileId }
                  })
                }
                onDeleteVideo={handleDeleteVideo}
              />
            </div>
          </Card>
        </Content>

        {/* 右侧：属性面板（推挤 / 覆盖） */}
        {prefs.inspectorMode === 'push' ? (
          <>
            {/* 右侧拖拽条（推挤模式） */}
            {prefs.inspectorOpen && (
              <div
                role="separator"
                className="cs-sep cs-sep-strong h-full"
                style={{
                  width: 10,
                  cursor: 'col-resize',
                  background: 'transparent',
                  flexShrink: 0,
                }}
                onPointerDown={(e) => beginResize('right', e)}
                title="拖拽调整属性面板宽度"
              />
            )}
            <Sider
              width={prefs.inspectorOpen ? prefs.rightWidth : 0}
              collapsedWidth={0}
              collapsed={!prefs.inspectorOpen}
              className="cs-right"
              style={{
                overflow: 'hidden',
              }}
            >
              <Inspector
                projectId={projectId}
                chapterId={chapterId}
                projectVisualStyle={projectVisualStyle}
                projectStyle={projectStyle}
                projectDefaultVideoRatio={projectDefaultVideoRatio}
                capabilityDefaultVideoRatio={capabilityDefaultVideoRatio}
                videoRatioOptions={videoRatioOptions}
                imageGenerationOptions={imageGenerationOptions}
                keyframeResolutionProfile={keyframeResolutionProfile}
                onChangeKeyframeResolutionProfile={setKeyframeResolutionProfile}
                videoResolutionProfile={videoResolutionProfile}
                onChangeVideoResolutionProfile={setVideoResolutionProfile}
                loadingDetail={loadingDetail}
                shotDetail={shotDetail}
                frameImages={frameImages}
                sceneLinks={sceneLinks}
                propLinks={propLinks}
                costumeLinks={costumeLinks}
                shotCharacterLinks={shotCharacterLinks}
                shotCandidateItems={shotCandidateItems}
                cameraUpdating={cameraUpdating}
                promptAssetsUpdating={promptAssetsUpdating}
                onUpdatePromptScene={updatePromptScene}
                onUpdatePromptActors={updatePromptActors}
                onUpdatePromptProps={updatePromptProps}
                onUpdatePromptCostumes={updatePromptCostumes}
                selectedShot={selectedShot}
                onPatchShotDetail={patchShotDetailLocal}
                onPatchShotDetailImmediate={patchShotDetailImmediate}
                onVideoResultsChanged={() => setVideoResultsRefreshKey((value) => value + 1)}
                onRefreshShotFrameImages={refreshShotFrameImages}
                onClose={() => setPrefs((p) => ({ ...p, inspectorOpen: false }))}
              />
            </Sider>

            {!prefs.inspectorOpen && (
              <div
                className="cs-right-strip"
                onClick={() => setPrefs((p) => ({ ...p, inspectorOpen: true }))}
                title="展开属性面板（P / Ctrl/Cmd+I）"
              >
                <span>属性</span>
              </div>
            )}
          </>
        ) : (
          <>
            {/* 覆盖模式：右侧抽屉覆盖中央 */}
            {prefs.inspectorOpen && (
              <div
                className="absolute top-0 right-0 h-full"
                style={{
                  width: prefs.rightWidth,
                  background: '#f9fafc',
                  borderLeft: '2px solid #cbd5e1',
                  zIndex: 20,
                  boxShadow: '-4px 0 12px rgba(0,0,0,0.06)',
                  display: 'flex',
                  flexDirection: 'row',
                }}
              >
                <div
                  role="separator"
                  className="cs-sep cs-sep-strong"
                  style={{ width: 10, flexShrink: 0 }}
                  onPointerDown={(e) => beginResize('right', e)}
                  title="拖拽调整覆盖宽度"
                />
                <div className="flex-1 min-w-0 overflow-hidden">
                  <Inspector
                    projectId={projectId}
                    chapterId={chapterId}
                    projectVisualStyle={projectVisualStyle}
                    projectStyle={projectStyle}
                    projectDefaultVideoRatio={projectDefaultVideoRatio}
                    capabilityDefaultVideoRatio={capabilityDefaultVideoRatio}
                    videoRatioOptions={videoRatioOptions}
                    imageGenerationOptions={imageGenerationOptions}
                    keyframeResolutionProfile={keyframeResolutionProfile}
                    onChangeKeyframeResolutionProfile={setKeyframeResolutionProfile}
                    videoResolutionProfile={videoResolutionProfile}
                    onChangeVideoResolutionProfile={setVideoResolutionProfile}
                    loadingDetail={loadingDetail}
                    shotDetail={shotDetail}
                    frameImages={frameImages}
                    sceneLinks={sceneLinks}
                    propLinks={propLinks}
                    costumeLinks={costumeLinks}
                    shotCharacterLinks={shotCharacterLinks}
                    shotCandidateItems={shotCandidateItems}
                    cameraUpdating={cameraUpdating}
                    promptAssetsUpdating={promptAssetsUpdating}
                    onUpdatePromptScene={updatePromptScene}
                    onUpdatePromptActors={updatePromptActors}
                    onUpdatePromptProps={updatePromptProps}
                    onUpdatePromptCostumes={updatePromptCostumes}
                    selectedShot={selectedShot}
                    onPatchShotDetail={patchShotDetailLocal}
                    onPatchShotDetailImmediate={patchShotDetailImmediate}
                    onVideoResultsChanged={() => setVideoResultsRefreshKey((value) => value + 1)}
                    onRefreshShotFrameImages={refreshShotFrameImages}
                    onClose={() => setPrefs((p) => ({ ...p, inspectorOpen: false }))}
                  />
                </div>
              </div>
            )}

            {/* 覆盖模式下，右侧边缘常驻开关 */}
            <Tooltip title={prefs.inspectorOpen ? '收起属性面板' : '展开属性面板'}>
              <Button
                size="small"
                className="absolute top-1/2 -translate-y-1/2"
                style={{ right: 4, zIndex: 30 }}
                icon={prefs.inspectorOpen ? <DoubleRightOutlined /> : <DoubleLeftOutlined />}
                onClick={() => setPrefs((p) => ({ ...p, inspectorOpen: !p.inspectorOpen }))}
              />
            </Tooltip>
          </>
        )}

        <Modal
          title={`批量视频准备度（${selectedShots.length} 条）`}
          open={batchVideoReadinessOpen}
          onCancel={() => {
            if (batchVideoReadinessLoading) return
            setBatchVideoReadinessOpen(false)
          }}
          footer={[
            <Button key="close" onClick={() => setBatchVideoReadinessOpen(false)} disabled={batchVideoReadinessLoading}>
              关闭
            </Button>,
            <Button
              key="refresh"
              type="primary"
              icon={<VideoCameraOutlined />}
              loading={batchVideoReadinessLoading}
              onClick={() => void batchInspectVideoReadiness()}
            >
              重新检查
            </Button>,
          ]}
          width={880}
          destroyOnClose={false}
        >
          {batchVideoReadinessLoading ? (
            <div className="py-10 text-center">
              <Spin />
            </div>
          ) : batchVideoReadinessItems.length === 0 ? (
            <div className="text-sm text-gray-500">暂无批量视频准备度结果</div>
          ) : (
            <div className="space-y-3 max-h-[65vh] overflow-y-auto pr-1">
              <div className="text-xs text-gray-500">
                当前按 <Tag className="!mx-1">text_only</Tag> 参考模式检查这批分镜是否具备视频生成条件。
              </div>
              {batchVideoReadinessItems.map(({ shot, readiness, error }) => {
                const failedChecks = (readiness?.checks ?? []).filter((item) => !item.ok)
                return (
                  <div key={shot.id} className="rounded-lg border border-solid border-gray-200 bg-white px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-medium truncate">
                          {String(shot.index).padStart(2, '0')} · {shot.title}
                        </div>
                        <div className="text-xs text-gray-500 mt-1">
                          {error
                            ? error
                            : readiness?.ready
                              ? '当前镜头已满足视频生成条件。'
                              : `当前镜头还有 ${failedChecks.length} 项待补齐。`}
                        </div>
                      </div>
                      <Tag color={error ? 'red' : readiness?.ready ? 'green' : 'gold'}>
                        {error ? '检查失败' : readiness?.ready ? '可生成' : '待补齐'}
                      </Tag>
                    </div>
                    {!error ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {(readiness?.checks ?? []).map((check) => (
                          <Tooltip key={check.key} title={check.message}>
                            <Tag color={check.ok ? 'green' : 'default'}>
                              {check.ok ? '通过' : '未通过'} · {check.key}
                            </Tag>
                          </Tooltip>
                        ))}
                      </div>
                    ) : null}
                    {!error && failedChecks.length > 0 ? (
                      <div className="mt-3 space-y-1">
                        {failedChecks.map((check) => (
                          <div key={check.key} className="text-xs text-gray-600">
                            • {check.message}
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                )
              })}
            </div>
          )}
        </Modal>
      </Layout>
    </div>
  )
}

export default ChapterStudio

function Inspector(props: {
  projectId?: string
  chapterId?: string
  projectVisualStyle: string
  projectStyle: string
  projectDefaultVideoRatio: string
  capabilityDefaultVideoRatio: string
  videoRatioOptions: Array<{ value: string; label: React.ReactNode }>
  imageGenerationOptions: ImageGenerationOptionsRead | null
  keyframeResolutionProfile: KeyframeResolutionProfile
  onChangeKeyframeResolutionProfile: (value: KeyframeResolutionProfile) => void
  videoResolutionProfile: '720p' | '1080p'
  onChangeVideoResolutionProfile: (value: '720p' | '1080p') => void
  loadingDetail: boolean
  shotDetail: ShotDetailRead | null
  frameImages: ShotFrameImageRead[]
  sceneLinks: ProjectSceneLinkRead[]
  propLinks: ProjectPropLinkRead[]
  costumeLinks: ProjectCostumeLinkRead[]
  shotCharacterLinks: ShotCharacterLinkRead[]
  shotCandidateItems: ShotExtractedCandidateRead[]
  cameraUpdating: boolean
  promptAssetsUpdating: boolean
  onUpdatePromptScene: (sceneId?: string) => Promise<void>
  onUpdatePromptActors: (actorIds: string[]) => Promise<void>
  onUpdatePromptProps: (propIds: string[]) => Promise<void>
  onUpdatePromptCostumes: (costumeIds: string[]) => Promise<void>
  selectedShot: StudioShot | null
  onClose: () => void
  onPatchShotDetail: (patch: Partial<ShotDetailRead>) => void
  onPatchShotDetailImmediate: (patch: Partial<ShotDetailRead>) => Promise<void>
  onVideoResultsChanged: () => void
  /** 下拉展开时拉取最新分镜帧图，用于「参考」关键帧类型选项动态更新 */
  onRefreshShotFrameImages?: () => Promise<void>
}) {
  const {
    projectId,
    chapterId,
    projectVisualStyle,
    projectStyle,
    projectDefaultVideoRatio,
    capabilityDefaultVideoRatio,
    videoRatioOptions,
    imageGenerationOptions,
    keyframeResolutionProfile,
    onChangeKeyframeResolutionProfile,
    videoResolutionProfile,
    onChangeVideoResolutionProfile,
    loadingDetail,
    shotDetail,
    frameImages,
    sceneLinks,
    propLinks,
    costumeLinks,
    shotCharacterLinks,
    shotCandidateItems,
    cameraUpdating,
    promptAssetsUpdating,
    onUpdatePromptScene,
    onUpdatePromptActors,
    onUpdatePromptProps,
    onUpdatePromptCostumes,
    selectedShot,
    onClose,
    onPatchShotDetail,
    onPatchShotDetailImmediate,
    onVideoResultsChanged,
    onRefreshShotFrameImages,
  } = props
  const currentChapterId = chapterId ?? null
  const [imageVersion, setImageVersion] = useState('v1')
  const [refImageType, setRefImageType] = useState<string | undefined>(undefined)
  const [refFrameTypeSelectLoading, setRefFrameTypeSelectLoading] = useState(false)
  const [useBoneDepth, setUseBoneDepth] = useState(false)
  const [audioMode, setAudioMode] = useState<'none' | 'prompt' | 'upload'>('none')
  const videoResolution = videoResolutionProfile
  const setVideoResolution = onChangeVideoResolutionProfile
  const [inspectorTabKey, setInspectorTabKey] = useState<InspectorTabKey>('camera')
  const [sceneNameMap, setSceneNameMap] = useState<Record<string, string>>({})
  const [characterNameMap, setCharacterNameMap] = useState<Record<string, string>>({})
  const [linkRoleOpen, setLinkRoleOpen] = useState(false)
  const [linkRoleLoading, setLinkRoleLoading] = useState(false)
  const [linkRoleSelectedIds, setLinkRoleSelectedIds] = useState<string[]>([])
  const [projectRoleOptions, setProjectRoleOptions] = useState<
    Array<{ value: string; label: React.ReactNode; searchLabel: string; disabled?: boolean }>
  >([])
  const [shotLinkedAssets, setShotLinkedAssets] = useState<
    Array<{ type: string; id: string; name?: string; thumbnail?: string; image_id?: number | null }>
  >([])
  const [shotAssetsOverview, setShotAssetsOverview] = useState<ShotAssetsOverviewRead | null>(null)
  const shotAssetsOverviewRequestSeqRef = useRef(0)
  const [shotRenderPromptLoading, setShotRenderPromptLoading] = useState(false)
  const [shotExtractStatus, setShotExtractStatus] = useState<{
    source: 'idle'
    updatedAt: number | null
    message: string
  }>({
    source: 'idle',
    updatedAt: null,
    message: '',
  })
  const [readinessExistenceMap, setReadinessExistenceMap] = useState<Record<string, EntityNameExistenceItem>>({})
  const [readinessExistenceLoading, setReadinessExistenceLoading] = useState(false)
  const [linkSceneOpen, setLinkSceneOpen] = useState(false)
  const [linkSceneLoading, setLinkSceneLoading] = useState(false)
  const [projectSceneOptions, setProjectSceneOptions] = useState<Array<{ value: string; label: React.ReactNode; searchLabel: string }>>([])

  const [linkPropOpen, setLinkPropOpen] = useState(false)
  const [linkPropLoading, setLinkPropLoading] = useState(false)
  const [linkPropSelectedIds, setLinkPropSelectedIds] = useState<string[]>([])
  const [projectPropOptions, setProjectPropOptions] = useState<Array<{ value: string; label: React.ReactNode; searchLabel: string; disabled?: boolean }>>([])

  const [linkCostumeOpen, setLinkCostumeOpen] = useState(false)
  const [linkCostumeLoading, setLinkCostumeLoading] = useState(false)
  const [linkCostumeSelectedIds, setLinkCostumeSelectedIds] = useState<string[]>([])
  const [projectCostumeOptions, setProjectCostumeOptions] = useState<Array<{ value: string; label: React.ReactNode; searchLabel: string; disabled?: boolean }>>([])
  const [keyframePromptPreviewOpen, setKeyframePromptPreviewOpen] = useState(false)
  const [keyframePromptPreviewLoading, setKeyframePromptPreviewLoading] = useState(false)
  const [keyframePromptActionLoading, setKeyframePromptActionLoading] = useState(false)
  const [keyframePromptPreviewFrameType, setKeyframePromptPreviewFrameType] = useState<PromptFrameType>('key')
  const [keyframePromptDebugContext, setKeyframePromptDebugContext] = useState<ShotFramePromptDebugContext | null>(null)
  const [keyframePromptDebugCollapsed, setKeyframePromptDebugCollapsed] = useState(true)
  const [keyframeDirectiveCollapsed, setKeyframeDirectiveCollapsed] = useState(true)
  const [keyframePromptDecisionCollapsed, setKeyframePromptDecisionCollapsed] = useState(true)
  const [keyframePromptQualityChecks, setKeyframePromptQualityChecks] = useState<ShotFramePromptQualityChecks>(null)
  const [videoPromptPreviewOpen, setVideoPromptPreviewOpen] = useState(false)
  const [videoPromptPreviewLoading, setVideoPromptPreviewLoading] = useState(false)
  const [videoPromptPreviewSubmitting, setVideoPromptPreviewSubmitting] = useState(false)
  const [videoPromptContextCollapsed, setVideoPromptContextCollapsed] = useState(true)
  const [videoModelPickerOpen, setVideoModelPickerOpen] = useState(false)
  const [videoModelsLoading, setVideoModelsLoading] = useState(false)
  const [videoModels, setVideoModels] = useState<VideoModelOption[]>([])
  // 分镜帧图片生成的积分试算（Inspector 独立组件，内部独立持有报价）。
  // 关键帧提示词预览弹窗与 useGenerationDraft 的 submit 共用：图片单价稳定，
  // 同一报价可在弹窗存活期内复用；后端按 quote_token 逐次幂等校验。
  // resolutionProfile 绑定关键帧档位，保证试算与创建任务的 resolution_profile 一致。
  const imageQuote = usePointsQuote({
    businessType: 'image_generation',
    category: 'image',
    modelId: null,
    resolutionProfile: keyframeResolutionProfile,
    enabled: true,
  })
  const [selectedVideoModelId, setSelectedVideoModelId] = useState<string | null>(null)
  const selectedVideoModel = useMemo(
    () => videoModels.find((item) => item.id === selectedVideoModelId) ?? null,
    [selectedVideoModelId, videoModels],
  )
  // 视频生成的积分试算（单次提交路径）。绑定 model + duration + resolution，
  // 任意一项缺失或试算未就绪时 canSubmit 为 false，门控「生成视频」按钮。
  const videoQuote = usePointsQuote({
    businessType: 'video_generation',
    category: 'video',
    modelId: selectedVideoModelId,
    durationSeconds: shotDetail?.duration ?? null,
    resolution: videoResolution,
    enabled: !!selectedVideoModelId && !!shotDetail?.duration,
  })
  // 分镜帧提示词生成（shot_frame_prompt）走真实文本 LLM，属文本类计费业务。
  // 报价与具体镜头无关，文本单价稳定，Inspector 存活期内复用同一报价。
  const shotFramePromptQuote = usePointsQuote({
    businessType: 'shot_frame_prompt',
    category: 'text',
    modelId: null,
    enabled: true,
  })
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
          .filter((model) => activeProviderIds.size === 0 || activeProviderIds.has(model.provider_id))
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

  const resolveVideoRatioForRequest = useCallback(() => {
    const shotRatio = String(shotDetail?.override_video_ratio ?? '').trim()
    const projectRatio = String(projectDefaultVideoRatio ?? '').trim()
    const fallbackRatio = String(capabilityDefaultVideoRatio ?? '').trim()
    return shotRatio || projectRatio || fallbackRatio
  }, [capabilityDefaultVideoRatio, projectDefaultVideoRatio, shotDetail?.override_video_ratio])
  const resolvedKeyframeRatio = resolveVideoRatioForRequest()
  const resolvedKeyframePixelSize = resolveKeyframePixelSize(
    imageGenerationOptions,
    resolvedKeyframeRatio,
    keyframeResolutionProfile,
  )
  const videoPromptDraft = useGenerationDraft<
    { prompt: string },
    { referenceMode: VideoReferenceMode; images: string[] },
    VideoPromptDerived,
    { taskId: string | null }
  >({
    initialBase: { prompt: '' },
    initialContext: { referenceMode: 'text_only', images: [] },
    derive: async ({ base, context }) => {
      if (!selectedShot?.id) {
        throw new Error('shot is required')
      }
      const ratio = resolveVideoRatioForRequest()
      if (!ratio) {
        throw new Error('video ratio is required')
      }
      const res = await FilmService.previewVideoGenerationPromptApiV1FilmTasksVideoPreviewPromptPost({
        requestBody: {
          shot_id: selectedShot.id,
          model_id: selectedVideoModelId,
          reference_mode: context.referenceMode,
          prompt: (base.prompt || '').trim() || null,
          images: context.images,
          ratio,
        } as any,
      })
      const data = (res as any)?.data ?? null
      return {
        prompt: typeof data?.prompt === 'string' ? data.prompt : '',
        images: Array.isArray(data?.images) ? (data.images as string[]).filter(Boolean) : [],
        pack: data?.pack ?? null,
      }
    },
    submit: async ({ derived, context }) => {
      if (!selectedShot?.id) {
        throw new Error('shot is required')
      }
      const ratio = resolveVideoRatioForRequest()
      if (!ratio) {
        throw new Error('video ratio is required')
      }
      // 视频生成必传清晰度档位与积分试算凭证；未试算或凭证缺失时阻断提交。
      if (!videoQuote.quoteToken) {
        throw new Error('video quote token is required')
      }
      const created = await FilmService.createVideoGenerationTaskApiV1FilmTasksVideoPost({
        requestBody: {
          shot_id: selectedShot.id,
          model_id: selectedVideoModelId,
          reference_mode: context.referenceMode,
          prompt: (derived.prompt || '').trim(),
          images: derived.images,
          ratio: ratio as '16:9' | '4:3' | '1:1' | '3:4' | '9:16' | '21:9',
          resolution: videoResolution,
          quote_token: videoQuote.quoteToken,
        },
      })
      return {
        taskId: created.data?.task_id ?? null,
      }
    },
  })
  const videoPromptPreviewDraft = videoPromptDraft.base.prompt
  const videoPromptPreviewImages = videoPromptDraft.context.images
  const videoReferenceMode = videoPromptDraft.context.referenceMode
  const videoPromptPreviewPack = videoPromptDraft.derived?.pack ?? null
  const videoActionBeatPhases = videoPromptPreviewPack?.action_beat_phases ?? []
  const videoActionBeats = videoActionBeatPhases.length > 0
    ? videoActionBeatPhases.map((item) => ({
        text: item.text,
        phase: item.phase,
      }))
    : (videoPromptPreviewPack?.action_beats ?? []).map((text) => ({
        text,
        phase: null,
      }))
  const videoVisibleActionBeats = videoPromptContextCollapsed
    ? videoActionBeats.slice(0, 2)
    : videoActionBeats
  const hiddenVideoActionBeatCount = Math.max(0, videoActionBeats.length - videoVisibleActionBeats.length)
  const [videoTaskPolling, setVideoTaskPolling] = useState(false)
  const [videoTaskStatus, setVideoTaskStatus] = useState<string | null>(null)
  const [videoTaskId, setVideoTaskId] = useState<string | null>(null)
  const [videoTask, setVideoTask] = useState<RelationTaskState | null>(null)
  const [videoSettledTask, setVideoSettledTask] = useState<RelationTaskState | null>(null)
  const [promptTask, setPromptTask] = useState<RelationTaskState | null>(null)
  const [promptSettledTask, setPromptSettledTask] = useState<RelationTaskState | null>(null)
  const [frameImageTask, setFrameImageTask] = useState<RelationTaskState | null>(null)
  const [frameImageSettledTask, setFrameImageSettledTask] = useState<RelationTaskState | null>(null)
  const [videoReadiness, setVideoReadiness] = useState<ShotVideoReadinessRead | null>(null)
  const [videoReadinessLoading, setVideoReadinessLoading] = useState(false)
  const [keyframeCards, setKeyframeCards] = useState<Record<PromptFrameType, KeyframeCardState>>({
    first: { loading: false, taskStatus: null, taskId: null, thumbs: [], modalOpen: false, applyingFileId: null },
    key: { loading: false, taskStatus: null, taskId: null, thumbs: [], modalOpen: false, applyingFileId: null },
    last: { loading: false, taskStatus: null, taskId: null, thumbs: [], modalOpen: false, applyingFileId: null },
  })
  const selectedShotSourceLabel = useMemo(() => {
    if (!selectedShot) return '分镜工作室'
    const shotTitle = selectedShot.title?.trim()
    return shotTitle ? `镜头：${shotTitle}` : `镜头：第 ${selectedShot.index} 镜`
  }, [selectedShot])
  useRelationTaskNotification({
    task: videoTask,
    settledTask: videoSettledTask,
    title: TASK_COPY.videoGeneration.title,
    sourceLabel: selectedShotSourceLabel,
    runningDescription: TASK_COPY.videoGeneration.runningDescription,
    cancellingDescription: TASK_COPY.videoGeneration.cancellingDescription,
    successDescription: TASK_COPY.videoGeneration.successDescription,
    cancelledDescription: TASK_COPY.videoGeneration.cancelledDescription,
    failedDescription: TASK_COPY.videoGeneration.failedDescription,
    onCancel:
      videoTask?.taskId
        ? () =>
            void executeTaskCancel({
              taskId: videoTask.taskId,
              reason: '用户在分镜工作室取消视频生成任务',
              applyCancelData: (data) => {
                setVideoTask((current) => applyTaskCancelState(current, data))
                return null
              },
              cancelledImmediatelyMessage: TASK_COPY.videoGeneration.cancelledImmediatelyMessage,
              cancelRequestedMessage: TASK_COPY.videoGeneration.cancelRequestedMessage,
              fallbackErrorMessage: '取消视频生成任务失败',
            })
        : null,
    onNavigate: () => undefined,
  })
  useRelationTaskNotification({
    task: promptTask,
    settledTask: promptSettledTask,
    title: TASK_COPY.shotFramePrompt.title,
    sourceLabel: selectedShotSourceLabel,
    runningDescription: TASK_COPY.shotFramePrompt.runningDescription,
    cancellingDescription: TASK_COPY.shotFramePrompt.cancellingDescription,
    successDescription: TASK_COPY.shotFramePrompt.successDescription,
    cancelledDescription: TASK_COPY.shotFramePrompt.cancelledDescription,
    failedDescription: TASK_COPY.shotFramePrompt.failedDescription,
    onCancel:
      promptTask?.taskId
        ? () =>
            void executeTaskCancel({
              taskId: promptTask.taskId,
              reason: '用户在分镜工作室取消分镜提示词生成任务',
              applyCancelData: (data) => {
                setPromptTask((current) => applyTaskCancelState(current, data))
                return null
              },
              cancelledImmediatelyMessage: TASK_COPY.shotFramePrompt.cancelledImmediatelyMessage,
              cancelRequestedMessage: TASK_COPY.shotFramePrompt.cancelRequestedMessage,
              fallbackErrorMessage: '取消分镜提示词生成任务失败',
            })
        : null,
    onNavigate: () => undefined,
  })
  useRelationTaskNotification({
    task: frameImageTask,
    settledTask: frameImageSettledTask,
    title: TASK_COPY.shotFrameImage.title,
    sourceLabel: selectedShotSourceLabel,
    runningDescription: TASK_COPY.shotFrameImage.runningDescription,
    cancellingDescription: TASK_COPY.shotFrameImage.cancellingDescription,
    successDescription: TASK_COPY.shotFrameImage.successDescription,
    cancelledDescription: TASK_COPY.shotFrameImage.cancelledDescription,
    failedDescription: TASK_COPY.shotFrameImage.failedDescription,
    onCancel:
      frameImageTask?.taskId
        ? () =>
            void executeTaskCancel({
              taskId: frameImageTask.taskId,
              reason: '用户在分镜工作室取消关键帧图片生成任务',
              applyCancelData: (data) => {
                setFrameImageTask((current) => applyTaskCancelState(current, data))
                return null
              },
              cancelledImmediatelyMessage: TASK_COPY.shotFrameImage.cancelledImmediatelyMessage,
              cancelRequestedMessage: TASK_COPY.shotFrameImage.cancelRequestedMessage,
              fallbackErrorMessage: '取消关键帧图片生成任务失败',
            })
        : null,
    onNavigate: () => undefined,
  })
  const showAvTab = false
  const showGenRefParams = false
  const showGenRefVersions = false

  const getInspectorTabForSelectedShot = useCallback(
    (shot: StudioShot | null): InspectorTabKey => {
      if (!shot) return 'camera'
      if (shot.hasProblem) return 'prompt_image'
      if (!(shot.script_excerpt ?? '').trim() || shot.status !== 'ready') return 'prompt_image'
      if (shot.status === 'ready') return 'gen_ref'
      return 'camera'
    },
    [],
  )

  useEffect(() => {
    setInspectorTabKey(getInspectorTabForSelectedShot(selectedShot))
  }, [getInspectorTabForSelectedShot, selectedShot?.id])
  useEffect(() => {
    if (!selectedShot?.id) {
      setVideoReadiness(null)
      return
    }
    let canceled = false
    setVideoReadinessLoading(true)
    void (async () => {
      try {
        const res = await StudioShotsService.getShotVideoReadinessApiApiV1StudioShotsShotIdVideoReadinessGet({
          shotId: selectedShot.id,
          referenceMode: videoReferenceMode,
        })
        if (canceled) return
        setVideoReadiness((res.data ?? null) as ShotVideoReadinessRead | null)
      } catch {
        if (canceled) return
        setVideoReadiness(null)
      } finally {
        if (!canceled) setVideoReadinessLoading(false)
      }
    })()
    return () => {
      canceled = true
    }
  }, [
    selectedShot?.id,
    selectedShot?.status,
    videoReferenceMode,
    shotDetail?.duration,
    shotDetail?.first_frame_prompt,
    shotDetail?.key_frame_prompt,
    shotDetail?.last_frame_prompt,
    frameImages.map((x) => `${x.id}:${x.file_id ?? ''}`).join('|'),
  ])

  const sceneIds = useMemo(() => Array.from(new Set(sceneLinks.map((x) => x.scene_id).filter(Boolean))), [sceneLinks])
  const characterIds = useMemo(() => Array.from(new Set(shotCharacterLinks.map((x) => x.character_id).filter(Boolean))), [shotCharacterLinks])

  const linkedCharacterIds = useMemo(() => characterIds, [characterIds])
  const linkedSceneId = useMemo(() => {
    if (!selectedShot?.id) return null
    return sceneLinks.find((l) => (l.shot_id ?? null) === selectedShot.id)?.scene_id ?? shotDetail?.scene_id ?? null
  }, [sceneLinks, selectedShot?.id, shotDetail?.scene_id])
  const linkedPropIds = useMemo(() => {
    if (!selectedShot?.id) return []
    return Array.from(new Set(propLinks.filter((l) => (l.shot_id ?? null) === selectedShot.id).map((l) => l.prop_id).filter(Boolean))) as string[]
  }, [propLinks, selectedShot?.id])
  const linkedCostumeIds = useMemo(() => {
    if (!selectedShot?.id) return []
    return Array.from(new Set(costumeLinks.filter((l) => (l.shot_id ?? null) === selectedShot.id).map((l) => l.costume_id).filter(Boolean))) as string[]
  }, [costumeLinks, selectedShot?.id])

  useEffect(() => {
    if (!selectedShot?.id) {
      setShotLinkedAssets([])
      return
    }
    let canceled = false
    void (async () => {
      try {
        const res = await StudioShotsService.listShotLinkedAssetsApiV1StudioShotsShotIdLinkedAssetsGet({
          shotId: selectedShot.id,
          page: 1,
          pageSize: 100,
        })
        if (canceled) return
        const items = (res.data?.items ?? []) as any[]
        setShotLinkedAssets(
          items
            .filter((x) => x && typeof x.type === 'string' && typeof x.id === 'string')
            .map((x) => ({
              type: String(x.type),
              id: String(x.id),
              name: typeof x.name === 'string' ? x.name : undefined,
              image_id: typeof x.image_id === 'number' ? x.image_id : x.image_id === null ? null : undefined,
              thumbnail: typeof x.thumbnail === 'string' && x.thumbnail.trim() ? x.thumbnail.trim() : undefined,
            })),
        )
      } catch {
        if (!canceled) setShotLinkedAssets([])
      }
    })()
    return () => {
      canceled = true
    }
  }, [selectedShot?.id])

  const loadShotAssetsOverview = useCallback(
    async (shotId: string) => {
      const reqSeq = ++shotAssetsOverviewRequestSeqRef.current
      try {
        const res = await StudioShotsService.getShotAssetsOverviewApiApiV1StudioShotsShotIdAssetsOverviewGet({
          shotId,
        })
        if (reqSeq !== shotAssetsOverviewRequestSeqRef.current) return
        setShotAssetsOverview(res.data ?? null)
      } catch {
        if (reqSeq !== shotAssetsOverviewRequestSeqRef.current) return
        setShotAssetsOverview(null)
      }
    },
    [],
  )

  useEffect(() => {
    if (!selectedShot?.id) {
      shotAssetsOverviewRequestSeqRef.current += 1
      setShotAssetsOverview(null)
      return
    }
    void loadShotAssetsOverview(selectedShot.id)
  }, [loadShotAssetsOverview, selectedShot?.id, shotCandidateItems])

  useEffect(() => {
    if (!selectedShot?.id) {
      setShotExtractStatus({ source: 'idle', updatedAt: null, message: '' })
      return
    }
    setShotExtractStatus({
      source: 'idle',
      updatedAt: null,
      message: '待确认候选请前往分镜编辑页提取或刷新。',
    })
  }, [
    selectedShot?.id,
  ])

  const linkedAssetThumbByKey = useMemo(() => {
    const map = new Map<string, string>()
    shotLinkedAssets.forEach((it) => {
      if (!it.thumbnail) return
      map.set(`${it.type}:${it.id}`, it.thumbnail)
    })
    return map
  }, [shotLinkedAssets])

  const promptAssetReadiness = useMemo(() => {
    if (selectedShot?.skip_extraction) {
      return {
        checks: [] as Array<{
          key: 'characters' | 'scene' | 'props' | 'costumes'
          label: string
          importance: string
          entries: Array<{ id: number; name: string; status: ShotExtractedCandidateRead['candidate_status'] }>
          missing: string[]
          expectedCount: number
          actualCount: number
          ignoredCount: number
          resolvedCount: number
          ready: boolean
        }>,
        expectedChecks: [] as Array<{
          key: 'characters' | 'scene' | 'props' | 'costumes'
          label: string
          importance: string
          entries: Array<{ id: number; name: string; status: ShotExtractedCandidateRead['candidate_status'] }>
          missing: string[]
          expectedCount: number
          actualCount: number
          ignoredCount: number
          resolvedCount: number
          ready: boolean
        }>,
        readyCount: 1,
        totalCount: 1,
        percent: 100,
        hasMissing: false,
      }
    }
    const overviewItems = shotAssetsOverview?.items ?? []
    const bucket = (type: 'character' | 'scene' | 'prop' | 'costume') =>
      overviewItems.filter((item) => item.type === type)

    const checks = [
      {
        key: 'characters' as const,
        label: '角色',
        importance: '影响人物一致性、关键帧参考图和画面主体描述。',
        candidates: bucket('character'),
      },
      {
        key: 'scene' as const,
        label: '场景',
        importance: '影响镜头环境描述、视频提示词和整体空间连续性。',
        candidates: bucket('scene'),
      },
      {
        key: 'props' as const,
        label: '道具',
        importance: '影响关键动作细节，缺失时容易让画面叙事元素不完整。',
        candidates: bucket('prop'),
      },
      {
        key: 'costumes' as const,
        label: '服装',
        importance: '影响角色外观连续性，尤其在多镜头或生成多版本时更明显。',
        candidates: bucket('costume'),
      },
    ].map((item) => {
      const entries = item.candidates.map((candidate) => ({
        id: candidate.candidate_id ?? -1,
        name: candidate.name,
        status: candidate.candidate_status ?? (candidate.is_linked ? 'linked' : 'pending'),
      }))
      const pending = entries.filter((entry) => entry.status === 'pending')
      const linked = entries.filter((entry) => entry.status === 'linked')
      const ignored = entries.filter((entry) => entry.status === 'ignored')
      return {
        ...item,
        entries,
        missing: pending.map((entry) => entry.name),
        expectedCount: entries.length,
        actualCount: linked.length,
        ignoredCount: ignored.length,
        resolvedCount: linked.length + ignored.length,
        ready: entries.length === 0 || pending.length === 0,
      }
    })

    const expectedChecks = checks.filter((item) => item.expectedCount > 0)
    const readyCount = expectedChecks.filter((item) => item.ready).length
    return {
      checks,
      expectedChecks,
      readyCount,
      totalCount: expectedChecks.length,
      percent: expectedChecks.length === 0 ? 100 : Math.round((readyCount / expectedChecks.length) * 100),
      hasMissing: expectedChecks.some((item) => item.missing.length > 0),
    }
  }, [selectedShot?.skip_extraction, shotAssetsOverview?.items])

  useEffect(() => {
    if (!projectId || !selectedShot?.id) {
      setReadinessExistenceMap({})
      return
    }

    const overviewItems = shotAssetsOverview?.items ?? []
    const characterNames = uniqueNames(
      overviewItems.filter((item) => item.type === 'character' && item.candidate_status === 'pending').map((item) => item.name),
    )
    const sceneNames = uniqueNames(
      overviewItems.filter((item) => item.type === 'scene' && item.candidate_status === 'pending').map((item) => item.name),
    )
    const propNames = uniqueNames(
      overviewItems.filter((item) => item.type === 'prop' && item.candidate_status === 'pending').map((item) => item.name),
    )
    const costumeNames = uniqueNames(
      overviewItems.filter((item) => item.type === 'costume' && item.candidate_status === 'pending').map((item) => item.name),
    )

    if (characterNames.length === 0 && sceneNames.length === 0 && propNames.length === 0 && costumeNames.length === 0) {
      setReadinessExistenceMap({})
      return
    }

    let cancelled = false
    setReadinessExistenceLoading(true)
    void (async () => {
      try {
        const res = await StudioEntitiesService.checkEntityNamesExistenceApiV1StudioEntitiesExistenceCheckPost({
          requestBody: {
            project_id: projectId,
            shot_id: selectedShot.id,
            character_names: characterNames,
            scene_names: sceneNames,
            prop_names: propNames,
            costume_names: costumeNames,
          },
        })
        if (cancelled) return
        const data = res.data
        const next: Record<string, EntityNameExistenceItem> = {}
        ;(data?.characters ?? []).forEach((item) => {
          next[`characters:${normalizeAssetName(item.name)}`] = item
        })
        ;(data?.scenes ?? []).forEach((item) => {
          next[`scene:${normalizeAssetName(item.name)}`] = item
        })
        ;(data?.props ?? []).forEach((item) => {
          next[`props:${normalizeAssetName(item.name)}`] = item
        })
        ;(data?.costumes ?? []).forEach((item) => {
          next[`costumes:${normalizeAssetName(item.name)}`] = item
        })
        setReadinessExistenceMap(next)
      } catch {
        if (!cancelled) setReadinessExistenceMap({})
      } finally {
        if (!cancelled) setReadinessExistenceLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [
    projectId,
    selectedShot?.id,
    shotAssetsOverview?.items,
  ])

  const getReadinessExistenceLabel = useCallback((checkKey: 'characters' | 'scene' | 'props' | 'costumes', name: string) => {
    const item = readinessExistenceMap[`${checkKey}:${normalizeAssetName(name)}`]
    if (!item) {
      return readinessExistenceLoading ? '检测中' : null
    }
    if (!item.exists) return '需新建'
    if (item.linked_to_project && !item.linked_to_shot) return '项目内可关联'
    if (!item.linked_to_project) return '资产库已有'
    if (item.linked_to_shot) return '已关联'
    return null
  }, [readinessExistenceLoading, readinessExistenceMap])

  const shotExtractStatusText = useMemo(() => {
    if (!shotExtractStatus.message) return ''
    if (!shotExtractStatus.updatedAt) return shotExtractStatus.message
    const time = new Date(shotExtractStatus.updatedAt).toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
    return `${shotExtractStatus.message} · ${time}`
  }, [shotExtractStatus])

  const goToShotEditForAssets = useCallback(() => {
    if (!projectId || !currentChapterId || !selectedShot?.id) return
    window.location.assign(`/projects/${projectId}/chapters/${currentChapterId}/shots/${selectedShot.id}/edit`)
  }, [currentChapterId, projectId, selectedShot?.id])

  const extractFileIdFromThumbnail = useCallback((thumbnail?: string | null): string | null => {
    const v = (thumbnail || '').trim()
    if (!v) return null
    // 纯 file_id：不包含路径或协议
    if (!v.includes('/') && !v.includes(':')) return v
    try {
      const url = new URL(v, typeof window !== 'undefined' ? window.location.origin : 'http://localhost')
      const m = url.pathname.match(/\/api\/v1\/studio\/files\/([^/]+)\/download\/?$/)
      if (m?.[1]) return decodeURIComponent(m[1])
    } catch {
      // ignore
    }
    return null
  }, [])

  const shotLinkedAssetNameByFileId = useMemo(() => {
    const map = new Map<string, string>()
    shotLinkedAssets.forEach((it: any) => {
      const fid =
        (typeof it?.file_id === 'string' && it.file_id.trim() ? it.file_id.trim() : null) ??
        extractFileIdFromThumbnail(it?.thumbnail ?? null)
      if (!fid) return
      const name = typeof it?.name === 'string' && it.name.trim() ? it.name.trim() : String(it?.id ?? '')
      if (!name) return
      map.set(fid, name)
    })
    return map
  }, [extractFileIdFromThumbnail, shotLinkedAssets])

  const deriveKeyframePromptPreview = useCallback(
    async ({
      base,
      context,
    }: {
      base: { frameType: PromptFrameType; prompt: string }
      context: { refFileIds: string[] }
    }): Promise<FramePromptDerived> => {
      if (!selectedShot?.id) {
        throw new Error('shot is required')
      }
      const basePrompt = (base.prompt || '').trim()
      const refFileIds = (context.refFileIds || []).filter(Boolean)
      if (!basePrompt) {
        return {
          basePrompt: '',
          renderedPrompt: '',
          selectedGuidance: [],
          droppedGuidance: [],
          selectedGuidanceDetails: [],
          droppedGuidanceDetails: [],
          images: [],
          mappings: [],
        }
      }

      const imagesPayload = refFileIds
        .map((fid) => {
          const match =
            shotLinkedAssets.find((x) => extractFileIdFromThumbnail(x.thumbnail ?? null) === fid) ??
            shotLinkedAssets.find((x) => (x as any)?.file_id === fid)
          return match
            ? {
                type: match.type as any,
                id: match.id,
                name: match.name ?? match.id,
                file_id: fid,
              }
            : null
        })
        .filter(Boolean)

      const rendered = await StudioImageTasksService.renderShotFramePromptApiV1StudioImageTasksShotShotIdFrameRenderPromptPost({
        shotId: selectedShot.id,
        requestBody: {
          frame_type: base.frameType,
          prompt: basePrompt,
          images: imagesPayload as any,
        } as any,
      })
      const d = rendered.data as any
      return {
        basePrompt: typeof d?.base_prompt === 'string' ? d.base_prompt : basePrompt,
        renderedPrompt: typeof d?.rendered_prompt === 'string' ? d.rendered_prompt : '',
        selectedGuidance: Array.isArray(d?.selected_guidance)
          ? d.selected_guidance.map((item: unknown) => String(item ?? '').trim()).filter(Boolean)
          : [],
        droppedGuidance: Array.isArray(d?.dropped_guidance)
          ? d.dropped_guidance.map((item: unknown) => String(item ?? '').trim()).filter(Boolean)
          : [],
        selectedGuidanceDetails: Array.isArray(d?.selected_guidance_details)
          ? d.selected_guidance_details
            .map((item: any) => ({
              text: String(item?.text ?? '').trim(),
              category: String(item?.category ?? '').trim(),
              reasonTag: String(item?.reason_tag ?? '').trim(),
              reason: String(item?.reason ?? '').trim(),
            }))
            .filter((item: { text: string }) => item.text)
          : [],
        droppedGuidanceDetails: Array.isArray(d?.dropped_guidance_details)
          ? d.dropped_guidance_details
            .map((item: any) => ({
              text: String(item?.text ?? '').trim(),
              category: String(item?.category ?? '').trim(),
              reasonTag: String(item?.reason_tag ?? '').trim(),
              reason: String(item?.reason ?? '').trim(),
            }))
            .filter((item: { text: string }) => item.text)
          : [],
        images: Array.isArray(d?.images) ? (d.images as string[]).filter(Boolean) : [],
        mappings: Array.isArray(d?.mappings) ? (d.mappings as ShotFramePromptMappingRead[]) : [],
      }
    },
    [extractFileIdFromThumbnail, selectedShot?.id, shotLinkedAssets],
  )

  const keyframePromptDraft = useGenerationDraft<
    { frameType: PromptFrameType; prompt: string },
    { refFileIds: string[] },
    FramePromptDerived,
    { taskId: string | null }
  >({
    initialBase: { frameType: 'key', prompt: '' },
    initialContext: { refFileIds: [] },
    derive: deriveKeyframePromptPreview,
    submit: async ({ base, context, derived }) => {
      if (!selectedShot?.id) {
        throw new Error('shot is required')
      }
      const resolvedItems =
        derived.mappings.length > 0
          ? derived.mappings.map((mapping) => ({
              type: mapping.type,
              id: mapping.id,
              name: mapping.name,
              file_id: mapping.file_id,
            }))
          : (context.refFileIds || []).map((fid) => {
              const match =
                shotLinkedAssets.find((x) => extractFileIdFromThumbnail(x.thumbnail ?? null) === fid) ??
                shotLinkedAssets.find((x) => (x as any)?.file_id === fid)
              return {
                type: (match?.type as any) ?? 'character',
                id: match?.id ?? fid,
                name: match?.name ?? match?.id ?? fid,
                file_id: fid,
              }
            })

      const ratio = resolveVideoRatioForRequest()
      if (!ratio) {
        throw new Error('video ratio is required')
      }
      const created = await StudioImageTasksService.createShotFrameImageGenerationTaskApiV1StudioImageTasksShotShotIdFrameImageTasksPost({
        shotId: selectedShot.id,
        requestBody: {
          frame_type: base.frameType,
          model_id: null,
          prompt: (base.prompt || '').trim(),
          images: resolvedItems as any,
          target_ratio: ratio,
          resolution_profile: keyframeResolutionProfile,
          quote_token: imageQuote.quoteToken,
        } as any,
      })
      return {
        taskId: created.data?.task_id ?? null,
      }
    },
  })
  const keyframePromptPreviewDraft = keyframePromptDraft.base.prompt
  const keyframePromptRenderedDraft = keyframePromptDraft.derived?.renderedPrompt ?? ''
  const keyframePromptSelectedGuidance = keyframePromptDraft.derived?.selectedGuidance ?? []
  const keyframePromptDroppedGuidance = keyframePromptDraft.derived?.droppedGuidance ?? []
  const keyframePromptSelectedGuidanceDetails = keyframePromptDraft.derived?.selectedGuidanceDetails ?? []
  const keyframePromptDroppedGuidanceDetails = keyframePromptDraft.derived?.droppedGuidanceDetails ?? []
  const keyframePromptVisibleSelectedGuidanceDetails = keyframePromptDecisionCollapsed
    ? keyframePromptSelectedGuidanceDetails.slice(0, 2)
    : keyframePromptSelectedGuidanceDetails
  const keyframePromptVisibleDroppedGuidanceDetails = keyframePromptDecisionCollapsed
    ? keyframePromptDroppedGuidanceDetails.slice(0, 1)
    : keyframePromptDroppedGuidanceDetails
  const keyframePromptRenderMappings = keyframePromptDraft.derived?.mappings ?? []
  const keyframePromptPreviewRefFileIds = keyframePromptDraft.context.refFileIds
  const keyframePromptRenderState = keyframePromptDraft.state
  const renderShotPromptToTextarea = useCallback(
    async (opts?: { frameType?: PromptFrameType; prompt?: string; refFileIds?: string[]; showPreviewLoading?: boolean }) => {
      if (!selectedShot?.id) return
      const frameType = opts?.frameType ?? keyframePromptPreviewFrameType
      const basePrompt = (typeof opts?.prompt === 'string' ? opts.prompt : keyframePromptPreviewDraft || '').trim()
      const refFileIds = (opts?.refFileIds ?? keyframePromptPreviewRefFileIds ?? []).filter(Boolean)
      const nextBase = { frameType, prompt: basePrompt }
      const nextContext = { refFileIds }
      keyframePromptDraft.hydrate({
        base: nextBase,
        context: nextContext,
        state: basePrompt ? 'draft_changed' : 'idle',
      })
      if (!basePrompt) {
        return
      }
      setShotRenderPromptLoading(true)
      if (opts?.showPreviewLoading) {
        setKeyframePromptPreviewLoading(true)
      }
      try {
        const derived = await keyframePromptDraft.deriveNow({ base: nextBase, context: nextContext })
        if (derived?.images?.length) {
          keyframePromptDraft.hydrate({
            base: nextBase,
            context: { refFileIds: derived.images },
            derived: {
              ...derived,
              images: derived.images,
            },
          })
        }
      } catch {
        keyframePromptDraft.setState('error')
      } finally {
        if (opts?.showPreviewLoading) {
          setKeyframePromptPreviewLoading(false)
        }
        setShotRenderPromptLoading(false)
      }
    },
    [
      keyframePromptDraft,
      keyframeResolutionProfile,
      keyframePromptPreviewDraft,
      keyframePromptPreviewFrameType,
      keyframePromptPreviewRefFileIds,
      selectedShot?.id,
    ],
  )

  const orderedLinkedCharacterIds = useMemo(() => {
    return shotCharacterLinks
      .slice()
      .sort((a, b) => (a.index ?? 0) - (b.index ?? 0))
      .map((x) => x.character_id)
      .filter(Boolean)
      .map((x) => String(x))
  }, [shotCharacterLinks])

  const autoKeyframeRefFileIds = useMemo(() => {
    const out: string[] = []
    const push = (fid: string | null) => {
      if (!fid) return
      if (out.includes(fid)) return
      out.push(fid)
    }
    // 角色（按 index 顺序）
    orderedLinkedCharacterIds.forEach((cid) =>
      push(extractFileIdFromThumbnail(linkedAssetThumbByKey.get(`character:${cid}`) ?? null)),
    )
    // 场景（单个）
    if (linkedSceneId) push(extractFileIdFromThumbnail(linkedAssetThumbByKey.get(`scene:${linkedSceneId}`) ?? null))
    // 道具
    linkedPropIds.forEach((pid) => push(extractFileIdFromThumbnail(linkedAssetThumbByKey.get(`prop:${pid}`) ?? null)))
    // 服装
    linkedCostumeIds.forEach((cid) =>
      push(extractFileIdFromThumbnail(linkedAssetThumbByKey.get(`costume:${cid}`) ?? null)),
    )
    return out
  }, [
    extractFileIdFromThumbnail,
    linkedCostumeIds,
    linkedPropIds,
    linkedSceneId,
    linkedAssetThumbByKey,
    orderedLinkedCharacterIds,
  ])

  const moveKeyframePromptRefFile = useCallback((fromIndex: number, toIndex: number) => {
    const current = keyframePromptPreviewRefFileIds
    if (fromIndex < 0 || toIndex < 0 || fromIndex >= current.length || toIndex >= current.length) return
    const next = reorder(current, fromIndex, toIndex)
    keyframePromptDraft.setContext({ refFileIds: next })
  }, [keyframePromptDraft, keyframePromptPreviewRefFileIds])

  const loadProjectRoleOptions = async () => {
    if (!projectId) {
      setProjectRoleOptions([])
      return
    }
    setLinkRoleLoading(true)
    try {
      const res = await StudioEntitiesApi.list('character', { page: 1, pageSize: 20, q: null })
      const items = (res.data?.items ?? []).filter((x: any) => x?.project_id === projectId)
      const opts = items.map((c: any) => {
        const id = String(c?.id ?? '')
        const name = String(c?.name ?? id)
        const thumb = typeof c?.thumbnail === 'string' ? c.thumbnail : ''
        const disabled = linkedCharacterIds.includes(id)
        return {
          value: id,
          searchLabel: name,
          disabled,
          label: (
            <div className="flex items-center gap-2 min-w-0">
              {thumb ? (
                <img src={resolveAssetUrl(thumb)} alt="" className="w-6 h-6 rounded object-cover shrink-0" />
              ) : (
                <div className="w-6 h-6 rounded bg-gray-100 flex items-center justify-center text-gray-400 shrink-0">
                  <UserOutlined />
                </div>
              )}
              <div className="min-w-0 truncate">{name}</div>
            </div>
          ),
        }
      })
      setProjectRoleOptions(opts)
    } catch {
      setProjectRoleOptions([])
    } finally {
      setLinkRoleLoading(false)
    }
  }

  const loadProjectAssetOptions = async (kind: 'scene' | 'prop' | 'costume') => {
    if (!projectId) return
    if (kind === 'scene') setLinkSceneLoading(true)
    if (kind === 'prop') setLinkPropLoading(true)
    if (kind === 'costume') setLinkCostumeLoading(true)
    try {
      const res = await StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
        entityType: kind,
        projectId,
        chapterId: null,
        shotId: null,
        assetId: null,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 20,
      })
      const items = (res.data?.items ?? []) as any[]
      const ids = Array.from(
        new Set(
          items
            .map((it) => (kind === 'scene' ? it.scene_id : kind === 'prop' ? it.prop_id : it.costume_id))
            .filter(Boolean)
            .map((x) => String(x)),
        ),
      )
      const details = await Promise.all(
        ids.map(async (id) => {
          try {
            const r = await StudioEntitiesApi.get(kind as any, id)
            const d = (r.data ?? null) as any
            return { id, name: String(d?.name ?? id), thumb: typeof d?.thumbnail === 'string' ? d.thumbnail : '' }
          } catch {
            return { id, name: id, thumb: '' }
          }
        }),
      )
      const nextThumbMap: Record<string, string> = {}
      details.forEach((d) => {
        if (d.thumb) nextThumbMap[d.id] = d.thumb
      })

      const makeLabel = (d: { id: string; name: string; thumb: string }) => (
        <div className="flex items-center gap-2 min-w-0">
          {d.thumb ? (
            <img src={resolveAssetUrl(d.thumb)} alt="" className="w-6 h-6 rounded object-cover shrink-0" />
          ) : (
            <div className="w-6 h-6 rounded bg-gray-100 flex items-center justify-center text-gray-400 shrink-0">
              <UserOutlined />
            </div>
          )}
          <div className="min-w-0 truncate">{d.name}</div>
        </div>
      )

      if (kind === 'scene') {
        setProjectSceneOptions(details.map((d) => ({ value: d.id, searchLabel: d.name, label: makeLabel(d) })))
      } else if (kind === 'prop') {
        setProjectPropOptions(
          details.map((d) => ({ value: d.id, searchLabel: d.name, label: makeLabel(d), disabled: linkedPropIds.includes(d.id) })),
        )
      } else {
        setProjectCostumeOptions(
          details.map((d) => ({ value: d.id, searchLabel: d.name, label: makeLabel(d), disabled: linkedCostumeIds.includes(d.id) })),
        )
      }
    } finally {
      if (kind === 'scene') setLinkSceneLoading(false)
      if (kind === 'prop') setLinkPropLoading(false)
      if (kind === 'costume') setLinkCostumeLoading(false)
    }
  }

  const openReadinessLinker = useCallback(
    async (kind: 'characters' | 'scene' | 'props' | 'costumes') => {
      if (!selectedShot?.id) return
      if (kind === 'characters') {
        setInspectorTabKey('keyframe_gen')
        setLinkRoleSelectedIds([])
        setLinkRoleOpen(true)
        await loadProjectRoleOptions()
        return
      }
      if (kind === 'scene') {
        setInspectorTabKey('keyframe_gen')
        setLinkSceneOpen(true)
        await loadProjectAssetOptions('scene')
        return
      }
      if (kind === 'props') {
        setInspectorTabKey('keyframe_gen')
        setLinkPropSelectedIds([])
        setLinkPropOpen(true)
        await loadProjectAssetOptions('prop')
        return
      }
      setInspectorTabKey('keyframe_gen')
      setLinkCostumeSelectedIds([])
      setLinkCostumeOpen(true)
      await loadProjectAssetOptions('costume')
    },
    [loadProjectAssetOptions, loadProjectRoleOptions, selectedShot?.id],
  )

  const openReadinessCreate = useCallback((kind: 'characters' | 'scene' | 'props' | 'costumes', name: string) => {
    if (!projectId || !selectedShot?.id) return
    const currentShotId = selectedShot.id
    const styleQ =
      `&visualStyle=${encodeURIComponent(projectVisualStyle)}` +
      `&style=${encodeURIComponent(projectStyle)}`
    const ctxQ =
      `&projectId=${encodeURIComponent(projectId)}` +
      `&chapterId=${encodeURIComponent(currentChapterId ?? '')}` +
      `&shotId=${encodeURIComponent(currentShotId)}` +
      styleQ
    const open = (url: string) => window.open(url, '_blank', 'noopener,noreferrer')
    if (kind === 'characters') {
      open(`/projects/${encodeURIComponent(projectId)}?tab=roles&create=1&name=${encodeURIComponent(name)}${ctxQ}`)
      return
    }
    const tab = kind === 'scene' ? 'scene' : kind === 'props' ? 'prop' : 'costume'
    open(`/assets?tab=${tab}&create=1&name=${encodeURIComponent(name)}${ctxQ}`)
  }, [currentChapterId, projectId, projectStyle, projectVisualStyle, selectedShot?.id])

  const handleReadinessMissingAction = useCallback(async (kind: 'characters' | 'scene' | 'props' | 'costumes', name: string) => {
    const item = readinessExistenceMap[`${kind}:${normalizeAssetName(name)}`]
    if (item && !item.exists) {
      openReadinessCreate(kind, name)
      return
    }
    await openReadinessLinker(kind)
  }, [openReadinessCreate, openReadinessLinker, readinessExistenceMap])

  useEffect(() => {
    if (sceneIds.length === 0) {
      setSceneNameMap({})
      return
    }
    void (async () => {
      const entries = await Promise.all(
        sceneIds.map(async (id) => {
          try {
            const r = await StudioEntitiesApi.get('scene', id)
            const d = r.data as { name?: string } | null | undefined
            return [id, d?.name?.trim() || id] as const
          } catch {
            return [id, id] as const
          }
        }),
      )
      setSceneNameMap(Object.fromEntries(entries))
    })()
  }, [sceneIds])

  useEffect(() => {
    if (characterIds.length === 0) {
      setCharacterNameMap({})
      return
    }
    void (async () => {
      const entries = await Promise.all(
        characterIds.map(async (id) => {
          try {
            const r = await StudioEntitiesApi.get('character', id)
            const d = r.data as { name?: string; thumbnail?: string | null } | null | undefined
            const name = d?.name?.trim() || id
            const thumb = typeof d?.thumbnail === 'string' && d.thumbnail.trim() ? d.thumbnail.trim() : ''
            return { id, name, thumb }
          } catch {
            return { id, name: id, thumb: '' }
          }
        }),
      )
      const nextNameMap: Record<string, string> = {}
      entries.forEach((e) => {
        nextNameMap[e.id] = e.name
      })
      setCharacterNameMap(nextNameMap)
    })()
  }, [characterIds])

  const getPromptFromDetailByType = (frameType: PromptFrameType): string => {
    if (!shotDetail) return ''
    if (frameType === 'first') return shotDetail.first_frame_prompt ?? ''
    if (frameType === 'last') return shotDetail.last_frame_prompt ?? ''
    return shotDetail.key_frame_prompt ?? ''
  }

  const frameLabel: Record<PromptFrameType, string> = { first: '首帧', key: '关键帧', last: '尾帧' }

  const handleRefFrameTypeDropdownVisibleChange = useCallback(
    async (open: boolean) => {
      if (!open || !onRefreshShotFrameImages) return
      setRefFrameTypeSelectLoading(true)
      try {
        await onRefreshShotFrameImages()
      } finally {
        setRefFrameTypeSelectLoading(false)
      }
    },
    [onRefreshShotFrameImages],
  )

  const refFrameTypeOptions = useMemo(() => {
    const kinds = new Set((frameImages ?? []).map((x) => x.frame_type))
    const opts: Array<{ value: string; label: string }> = []
    if (kinds.has('first')) opts.push({ value: 'first', label: '首帧' })
    if (kinds.has('last')) opts.push({ value: 'last', label: '尾帧' })
    if (kinds.has('first') && kinds.has('last')) opts.push({ value: 'first_last', label: '首尾帧' })
    if (kinds.has('key')) opts.push({ value: 'key', label: '关键帧' })
    return opts
  }, [frameImages])

  useEffect(() => {
    const allowed = new Set(refFrameTypeOptions.map((x) => x.value))
    setRefImageType((prev) => (prev && allowed.has(prev) ? prev : undefined))
  }, [refFrameTypeOptions])

  const buildVideoRefSelection = () => {
    const first = frameImages.find((x) => x.frame_type === 'first')?.file_id ?? null
    const last = frameImages.find((x) => x.frame_type === 'last')?.file_id ?? null
    const key = frameImages.find((x) => x.frame_type === 'key')?.file_id ?? null

    const s = refImageType
    if (s === 'first_last') {
      return {
        referenceMode: 'first_last' as const,
        images: [first, last].filter((x): x is string => Boolean(x)),
      }
    }
    if (s === 'key') return { referenceMode: 'key' as const, images: key ? [key] : [] }
    if (s === 'first') return { referenceMode: 'first' as const, images: first ? [first] : [] }
    if (s === 'last') return { referenceMode: 'last' as const, images: last ? [last] : [] }
    return { referenceMode: 'text_only' as const, images: [] }
  }

  const openVideoPromptPreview = async () => {
    if (!selectedShot?.id) {
      message.warning('请先选择一个分镜')
      return
    }
    const { referenceMode, images } = buildVideoRefSelection()
    const nextContext = { referenceMode, images }
    videoPromptDraft.hydrate({
      base: { prompt: '' },
      context: nextContext,
    })
    setVideoPromptContextCollapsed(true)
    setVideoPromptPreviewOpen(true)
    setVideoPromptPreviewLoading(true)
    try {
      const derived = await videoPromptDraft.deriveNow({
        base: { prompt: '' },
        context: nextContext,
      })
      if (derived) {
        videoPromptDraft.hydrate({
          base: { prompt: derived.prompt },
          context: {
            referenceMode,
            images: derived.images,
          },
          derived,
        })
      }
    } catch {
      message.error('获取视频提示词预览失败')
    } finally {
      setVideoPromptPreviewLoading(false)
    }
  }

  const submitVideoGeneration = async () => {
    if (!selectedShot?.id) {
      message.warning('请先选择一个分镜')
      return
    }
    if (!resolveVideoRatioForRequest()) {
      message.warning('当前镜头缺少视频比例，请先设置项目默认比例或镜头覆盖比例')
      return
    }
    const prompt = (videoPromptPreviewDraft || '').trim()
    if (!prompt) {
      message.warning('请输入视频提示词')
      return
    }
    setVideoPromptPreviewSubmitting(true)
    try {
      const submitted = await videoPromptDraft.submitNow()
      const taskId = submitted?.taskId
      if (!taskId) {
        message.error('视频生成任务创建失败：缺少任务 ID')
        return
      }
      setVideoTaskId(taskId)
      setVideoTaskStatus('pending')
      setVideoTaskPolling(true)
      setVideoTask({
        taskId,
        status: 'pending',
        progress: 0,
        cancelRequested: false,
      })
      setVideoSettledTask(null)
      setVideoPromptPreviewOpen(false)
    } catch (error) {
      // 优先识别积分业务错误（积分不足/报价已变更），命中后刷新报价并返回语义文案。
      const pointsAware = makePointsAwareGetErrorMessage(videoQuote.refresh)
      const fallback = '发起视频生成失败'
      const msg = pointsAware(error, fallback)
      message.error(msg)
    } finally {
      setVideoPromptPreviewSubmitting(false)
    }
  }

  useEffect(() => {
    if (!videoTaskPolling || !videoTaskId) return
    let cancelled = false
    void (async () => {
      try {
        let finalTaskState: RelationTaskState | null = null
        for (let i = 0; i < 60; i += 1) {
          await sleep(2000)
          if (cancelled) return
          const statusRes = await FilmService.getTaskStatusApiV1FilmTasksTaskIdStatusGet({ taskId: videoTaskId })
          const status = statusRes.data?.status ?? null
          if (!status) continue
          if (statusRes.data) {
            finalTaskState = toRelationTaskStateFromStatusRead(statusRes.data)
            setVideoTask(finalTaskState)
          }
          setVideoTaskStatus(status)
          if (status === 'succeeded' || status === 'failed' || status === 'cancelled') break
        }
        if (
          !cancelled &&
          finalTaskState &&
          (finalTaskState.status === 'succeeded' ||
            finalTaskState.status === 'failed' ||
            finalTaskState.status === 'cancelled')
        ) {
          setVideoTask(null)
          setVideoSettledTask(finalTaskState)
          if (finalTaskState.status === 'succeeded') {
            onVideoResultsChanged()
          }
        }
      } catch {
        if (!cancelled) {
          message.error('获取视频任务状态失败')
        }
      } finally {
        if (!cancelled) setVideoTaskPolling(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [videoTaskPolling, videoTaskId])
  const updateCardState = (frameType: PromptFrameType, patch: Partial<KeyframeCardState>) => {
    setKeyframeCards((prev) => ({ ...prev, [frameType]: { ...prev[frameType], ...patch } }))
  }

  const getLatestFrameSlotId = async (frameType: PromptFrameType): Promise<number | null> => {
    if (!selectedShot?.id) return null
    const res = await StudioShotFrameImagesService.listShotFrameImagesApiV1StudioShotFrameImagesGet({
      shotDetailId: selectedShot.id,
      order: null,
      isDesc: false,
      page: 1,
      pageSize: 100,
    })
    const items = (res.data?.items ?? []) as ShotFrameImageRead[]
    const slot = items.find((x) => x.frame_type === frameType)
    return slot?.id ?? null
  }

  const loadCardThumbs = async (frameType: PromptFrameType, slotIdOverride?: number | null, retryCount = 1) => {
    const localSlotId = frameImages.find((x) => x.frame_type === frameType)?.id ?? null
    const slotId = slotIdOverride ?? localSlotId ?? (await getLatestFrameSlotId(frameType))
    if (!slotId) {
      updateCardState(frameType, { thumbs: [] })
      return
    }
    let thumbs: Array<{ linkId: number; fileId: string; thumbUrl: string }> = []
    for (let i = 0; i < retryCount; i += 1) {
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
      thumbs = links
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
      if (thumbs.length > 0 || i === retryCount - 1) break
      await sleep(800)
    }
    updateCardState(frameType, { thumbs })
  }

  const generateKeyframeCard = async (frameType: PromptFrameType) => {
    if (!selectedShot?.id) {
      message.warning('请先选择一个分镜')
      return
    }
    try {
      setKeyframePromptPreviewLoading(true)
      setKeyframePromptPreviewOpen(true)
      setKeyframePromptPreviewFrameType(frameType)
      setKeyframePromptDebugCollapsed(true)
      setKeyframeDirectiveCollapsed(true)
      setKeyframePromptDecisionCollapsed(true)
      const basePrompt = getPromptFromDetailByType(frameType)
      keyframePromptDraft.hydrate({
        base: { frameType, prompt: basePrompt },
        context: { refFileIds: autoKeyframeRefFileIds },
        state: basePrompt.trim() ? 'draft_changed' : 'idle',
      })
      setKeyframePromptDebugContext(null)
      setKeyframePromptQualityChecks(null)
      // 文本区域内容：统一由 frame-render-prompt 获取
      if (basePrompt.trim()) {
        void renderShotPromptToTextarea({
          frameType,
          prompt: basePrompt,
          refFileIds: autoKeyframeRefFileIds,
          showPreviewLoading: true,
        })
      } else {
        setKeyframePromptPreviewLoading(false)
      }
    } catch {
      message.error('获取提示词失败')
      setKeyframePromptPreviewLoading(false)
    } finally {
      // loading 由 renderShotPromptToTextarea 结束后关闭
    }
  }

  const regenerateKeyframePrompt = async () => {
    if (!selectedShot?.id) {
      message.warning('请先选择一个分镜')
      return
    }
    // 分镜帧提示词生成为文本类计费业务，未试算或凭证缺失时阻断提交。
    if (!shotFramePromptQuote.quoteToken) {
      message.warning('积分试算未就绪，请稍后再试')
      return
    }
    const frameType = keyframePromptPreviewFrameType
    setKeyframePromptActionLoading(true)
    try {
      const created = await FilmService.createShotFramePromptTaskApiV1FilmTasksShotFramePromptsPost({
        requestBody: {
          shot_id: selectedShot.id,
          frame_type: frameType,
          quote_token: shotFramePromptQuote.quoteToken,
        },
      })
      const taskId = created.data?.task_id
      if (!taskId) {
        message.error('生成任务创建失败：缺少任务 ID')
        return
      }
      setPromptTask({
        taskId,
        status: 'pending',
        progress: 0,
        cancelRequested: false,
      })
      setPromptSettledTask(null)

      let finalStatus = 'pending'
      let finalTaskState: RelationTaskState | null = null
      for (let i = 0; i < 30; i += 1) {
        await sleep(2000)
        const statusRes = await FilmService.getTaskStatusApiV1FilmTasksTaskIdStatusGet({ taskId })
        const status = statusRes.data?.status
        if (!status) continue
        finalStatus = status
        if (statusRes.data) {
          finalTaskState = toRelationTaskStateFromStatusRead(statusRes.data)
          setPromptTask(finalTaskState)
        }
        if (status === 'succeeded' || status === 'failed' || status === 'cancelled') break
      }
      if (
        finalTaskState &&
        (finalTaskState.status === 'succeeded' ||
          finalTaskState.status === 'failed' ||
          finalTaskState.status === 'cancelled')
      ) {
        setPromptTask(null)
        setPromptSettledTask(finalTaskState)
      }

      if (finalStatus !== 'succeeded') {
        if (finalStatus !== 'failed' && finalStatus !== 'cancelled') {
          message.warning('生成任务仍在执行，请稍后重试')
        }
        return
      }

      const resultRes = await FilmService.getTaskResultApiV1FilmTasksTaskIdResultGet({ taskId })
      const result = (resultRes.data?.result ?? null) as Record<string, unknown> | null
      const generatedPrompt = typeof result?.prompt === 'string' ? result.prompt : ''
      const debugContext =
        result && typeof result.debug_context === 'object' && result.debug_context !== null
          ? (result.debug_context as ShotFramePromptDebugContext)
          : null
      const qualityChecks =
        result &&
        typeof result.quality_checks === 'object' &&
        result.quality_checks !== null &&
        typeof (result.quality_checks as Record<string, unknown>).passed === 'boolean'
          ? {
              passed: Boolean((result.quality_checks as Record<string, unknown>).passed),
              issues: Array.isArray((result.quality_checks as Record<string, unknown>).issues)
                ? ((result.quality_checks as Record<string, unknown>).issues as unknown[])
                    .map((item) => (typeof item === 'string' ? item.trim() : ''))
                    .filter(Boolean)
                : [],
            }
          : null
      if (!generatedPrompt.trim()) {
        message.warning('生成完成，但未返回提示词')
        return
      }
      if (frameType === 'first') {
        onPatchShotDetail({ first_frame_prompt: generatedPrompt })
      } else if (frameType === 'last') {
        onPatchShotDetail({ last_frame_prompt: generatedPrompt })
      } else {
        onPatchShotDetail({ key_frame_prompt: generatedPrompt })
      }
      setKeyframePromptDebugContext(debugContext)
      setKeyframePromptQualityChecks(qualityChecks)
      keyframePromptDraft.replaceBase({ frameType, prompt: generatedPrompt })
      keyframePromptDraft.setState('draft_changed')
      await renderShotPromptToTextarea({
        frameType,
        prompt: generatedPrompt,
        refFileIds: keyframePromptPreviewRefFileIds.length > 0 ? keyframePromptPreviewRefFileIds : autoKeyframeRefFileIds,
      })
      message.success('提示词已生成')
    } catch (error) {
      // 优先识别积分业务错误（积分不足/报价已变更），命中后刷新报价并返回语义文案。
      const pointsAware = makePointsAwareGetErrorMessage(shotFramePromptQuote.refresh)
      const msg = pointsAware(error, '生成提示词失败')
      message.error(msg)
    } finally {
      setKeyframePromptActionLoading(false)
    }
  }

  useEffect(() => {
    // 弹窗打开时，若当前没有参考图，则自动填充为分镜关联实体的参考图
    if (!keyframePromptPreviewOpen) return
    if (keyframePromptPreviewRefFileIds.length > 0) return
    if (autoKeyframeRefFileIds.length === 0) return
    keyframePromptDraft.setContext({ refFileIds: autoKeyframeRefFileIds })
  }, [autoKeyframeRefFileIds, keyframePromptPreviewOpen, keyframePromptPreviewRefFileIds.length])

  useEffect(() => {
    if (!keyframePromptPreviewOpen) return
    if (mapGenerationDraftStateToRenderState(keyframePromptRenderState) !== 'stale') return
    const basePrompt = (keyframePromptPreviewDraft || '').trim()
    if (!basePrompt) return
    const refFileIds =
      keyframePromptPreviewRefFileIds.length > 0 ? keyframePromptPreviewRefFileIds : autoKeyframeRefFileIds
    const timer = window.setTimeout(() => {
      void renderShotPromptToTextarea({
        frameType: keyframePromptPreviewFrameType,
        prompt: basePrompt,
        refFileIds,
      })
    }, 400)
    return () => {
      window.clearTimeout(timer)
    }
  }, [
    autoKeyframeRefFileIds,
    keyframePromptPreviewDraft,
    keyframePromptPreviewFrameType,
    keyframePromptPreviewOpen,
    keyframePromptPreviewRefFileIds,
    keyframePromptRenderState,
    renderShotPromptToTextarea,
  ])

  const confirmGenerateKeyframeWithPrompt = async () => {
    if (!selectedShot?.id) {
      message.warning('请先选择一个分镜')
      return
    }
    const frameType = keyframePromptPreviewFrameType
    const basePrompt = (keyframePromptPreviewDraft || '').trim()
    if (!basePrompt) {
      message.warning('请输入提示词')
      return
    }

    setKeyframePromptActionLoading(true)
    updateCardState(frameType, { loading: true, taskStatus: 'pending', taskId: null })
    try {
      const refFileIds = keyframePromptPreviewRefFileIds.length > 0 ? keyframePromptPreviewRefFileIds : autoKeyframeRefFileIds
      keyframePromptDraft.replaceContext({ refFileIds })
      const submitted = await keyframePromptDraft.submitNow()
      const taskId = submitted?.taskId
      if (!taskId) {
        message.error('生成任务创建失败：缺少任务 ID')
        updateCardState(frameType, { loading: false, taskStatus: 'failed' })
        return
      }
      updateCardState(frameType, { taskId })
      setFrameImageTask({
        taskId,
        status: 'pending',
        progress: 0,
        cancelRequested: false,
      })
      setFrameImageSettledTask(null)

      let finalStatus = 'pending'
      let finalTaskState: RelationTaskState | null = null
      for (let i = 0; i < 30; i += 1) {
        await sleep(2000)
        const statusRes = await FilmService.getTaskStatusApiV1FilmTasksTaskIdStatusGet({ taskId })
        const status = statusRes.data?.status
        if (!status) continue
        finalStatus = status
        if (statusRes.data) {
          finalTaskState = toRelationTaskStateFromStatusRead(statusRes.data)
          setFrameImageTask(finalTaskState)
        }
        updateCardState(frameType, { taskStatus: status })
        if (status === 'succeeded' || status === 'failed' || status === 'cancelled') break
      }
      if (
        finalTaskState &&
        (finalTaskState.status === 'succeeded' ||
          finalTaskState.status === 'failed' ||
          finalTaskState.status === 'cancelled')
      ) {
        setFrameImageTask(null)
        setFrameImageSettledTask(finalTaskState)
      }
      if (finalStatus === 'succeeded') {
        const latestSlotId = await getLatestFrameSlotId(frameType)
        await loadCardThumbs(frameType, latestSlotId, 5)
        setKeyframePromptPreviewOpen(false)
      } else if (finalStatus !== 'failed' && finalStatus !== 'cancelled') {
        message.warning('生成任务仍在执行，请稍后刷新')
      }
    } catch (error) {
      updateCardState(frameType, { taskStatus: 'failed' })
      // 优先识别积分业务错误（积分不足/报价已变更），命中后刷新报价并返回语义文案。
      const pointsAware = makePointsAwareGetErrorMessage(imageQuote.refresh)
      const fallback = `${frameLabel[frameType]}生成失败`
      const msg = pointsAware(error, fallback)
      message.error(msg)
    } finally {
      updateCardState(frameType, { loading: false })
      setKeyframePromptActionLoading(false)
    }
  }

  const applyCardImage = async (frameType: PromptFrameType, fileId: string) => {
    const slot = frameImages.find((x) => x.frame_type === frameType)
    if (!slot) return
    updateCardState(frameType, { applyingFileId: fileId })
    try {
      await StudioShotFrameImagesService.updateShotFrameImageApiV1StudioShotFrameImagesImageIdPatch({
        imageId: slot.id,
        requestBody: { file_id: fileId } as any,
      })
      await loadCardThumbs(frameType)
      message.success('已切换使用图片')
    } catch {
      message.error('切换失败')
    } finally {
      updateCardState(frameType, { applyingFileId: null })
    }
  }

  useEffect(() => {
    if (!selectedShot?.id) return
    void Promise.all([loadCardThumbs('first'), loadCardThumbs('key'), loadCardThumbs('last')])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedShot?.id, frameImages.map((x) => `${x.id}:${x.file_id ?? ''}`).join('|')])

  return (
    <div className="w-full h-full flex flex-col min-h-0">
      <div className="cs-inspector-header flex items-center justify-between">
        <div className="min-w-0">
          <div className="font-medium truncate">分镜生成面板</div>
          <div className="text-xs text-gray-500 truncate">
            {selectedShot ? `${String(selectedShot.index).padStart(2, '0')} · ${selectedShot.title}` : '未选择分镜'}
          </div>
        </div>
        <Space size="small">
          <Tooltip title="收起">
            <Button size="small" type="text" icon={<DoubleRightOutlined />} onClick={onClose} />
          </Tooltip>
        </Space>
      </div>

      <div className="cs-inspector flex-1 min-h-0 overflow-auto">
        <Tabs
          tabPosition="left"
          activeKey={inspectorTabKey}
          onChange={(activeKey) => setInspectorTabKey(activeKey as InspectorTabKey)}
          items={(() => {
            const items = [
{
              key: 'camera',
              label: '生成参数',
              children: (
                <div>
                  {loadingDetail ? (
                    <div className="text-gray-500">加载中…</div>
                  ) : shotDetail ? (
                    <>
                      <div className="cs-group">
                        <div className="cs-group-title">
                          <CameraOutlined /> 镜头语言
                        </div>
                        <div className="space-y-4">
                          <div>
                            <div className="text-gray-500 text-xs mb-1">景别</div>
                            <Radio.Group
                              value={shotDetail.camera_shot}
                              optionType="button"
                              buttonStyle="solid"
                              size="small"
                              options={CAMERA_SHOT_OPTIONS}
                              onChange={(e) => void onPatchShotDetailImmediate({ camera_shot: e.target.value })}
                              disabled={cameraUpdating}
                            />
                          </div>
                          <div>
                            <div className="text-gray-500 text-xs mb-1">角度</div>
                            <Radio.Group
                              value={shotDetail.angle}
                              optionType="button"
                              size="small"
                              options={CAMERA_ANGLE_OPTIONS}
                              onChange={(e) => void onPatchShotDetailImmediate({ angle: e.target.value })}
                              disabled={cameraUpdating}
                            />
                          </div>
                          <div>
                            <div className="text-gray-500 text-xs mb-1">运镜</div>
                            <Radio.Group
                              value={shotDetail.movement}
                              size="small"
                              options={CAMERA_MOVEMENT_OPTIONS}
                              onChange={(e) => void onPatchShotDetailImmediate({ movement: e.target.value })}
                              disabled={cameraUpdating}
                            />
                          </div>
                          <div>
                            <div className="text-gray-500 text-xs mb-1">时长（3–15s，整数）</div>
                            <div className="flex items-center gap-2">
                              <Slider
                                min={VIDEO_DURATION_MIN_SECONDS}
                                max={VIDEO_DURATION_MAX_SECONDS}
                                step={1}
                                value={normalizeVideoDurationSeconds(shotDetail.duration)}
                                style={{ flex: 1 }}
                                onChange={(v) => void onPatchShotDetailImmediate({ duration: normalizeVideoDurationSeconds(Number(v)) })}
                                disabled={cameraUpdating}
                              />
                              <Input
                                size="small"
                                value={`${normalizeVideoDurationSeconds(shotDetail.duration)}`}
                                style={{ width: 72 }}
                                onChange={(e) => {
                                  const raw = Number(e.target.value)
                                  if (!Number.isFinite(raw)) return
                                  const n = normalizeVideoDurationSeconds(raw)
                                  void onPatchShotDetailImmediate({ duration: n })
                                }}
                                disabled={cameraUpdating}
                              />
                            </div>
                          </div>
                          <div>
                            <div className="text-gray-500 text-xs mb-1">视频比例</div>
                            <Select
                              size="small"
                              allowClear
                              value={shotDetail.override_video_ratio ?? undefined}
                              placeholder={projectDefaultVideoRatio || capabilityDefaultVideoRatio || '请选择视频比例'}
                              options={videoRatioOptions}
                              onChange={(value) => {
                                onPatchShotDetail({ override_video_ratio: value ?? null })
                              }}
                              disabled={cameraUpdating}
                            />
                          </div>
                          <div>
                            <div className="text-gray-500 text-xs mb-1">分辨率</div>
                            <Select
                              size="small"
                              value={videoResolution}
                              options={[
                                { value: '720p', label: '720p' },
                                { value: '1080p', label: '1080p' },
                              ]}
                              onChange={(value) => setVideoResolution(value)}
                              disabled={cameraUpdating}
                            />
                          </div>
                        </div>
                      </div>

                    </>
                  ) : (
                    <div className="text-gray-500">请选择分镜</div>
                  )}
                </div>
              ),
            },
              {
              key: 'prompt_image',
              label: '确认资产与台词',
              children: (
                <div>
                  <ChapterStudioReadinessDiagnosisPanel
                    selectedShot={selectedShot}
                    shotAssetsOverview={shotAssetsOverview}
                    promptAssetReadiness={promptAssetReadiness}
                    shotExtractStatusSource={shotExtractStatus.source}
                    shotExtractStatusText={shotExtractStatusText}
                    onGoToShotEdit={goToShotEditForAssets}
                    onHandleMissingAction={(kind, name) => {
                      void handleReadinessMissingAction(kind, name)
                    }}
                    getReadinessExistenceLabel={getReadinessExistenceLabel}
                  />

                  <div className="cs-group">
                    <div className="cs-group-title">
                      <PictureOutlined /> 氛围描述
                    </div>
                    <div>
                        <TextArea
                          rows={3}
                          placeholder="氛围描述…（可选跟随画面）"
                          value={shotDetail?.atmosphere ?? ''}
                          onChange={(e) => onPatchShotDetail({ atmosphere: e.target.value })}
                        />
                    </div>
                  </div>

                </div>
              ),
            },
              {
              key: 'keyframe_gen',
              label: '关键帧与参考图',
              children: (
                <div className="space-y-3">
                  <div className="cs-group">
                    <div className="cs-group-title">
                      <SettingOutlined /> 关键帧规格
                    </div>
                    <div className="text-xs text-gray-500 mb-2">
                      关键帧会跟随当前视频比例生成；这里控制参考帧分辨率档位。
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="min-w-[96px] text-xs text-gray-500">分辨率档位</div>
                      <Select
                        size="small"
                        value={keyframeResolutionProfile}
                        style={{ width: 160 }}
                        options={[
                          { value: 'standard', label: '标准（2K）' },
                          { value: 'high', label: '高清（3K）' },
                        ]}
                        onChange={(value) => onChangeKeyframeResolutionProfile(value as KeyframeResolutionProfile)}
                      />
                    </div>
                    <div className="mt-2 rounded bg-gray-50 px-3 py-2 text-xs text-gray-600">
                      <div>
                        当前规格：{resolvedKeyframeRatio || '未设置比例'} ·{' '}
                        {getResolutionProfileLabel(keyframeResolutionProfile)}
                        {resolvedKeyframePixelSize ? ` → ${resolvedKeyframePixelSize}` : ''}
                      </div>
                      <div className="mt-1 text-gray-500">
                        当前模型：{imageGenerationOptions?.provider || '未识别供应商'}
                        {imageGenerationOptions?.model_name ? ` / ${imageGenerationOptions.model_name}` : ''}
                      </div>
                    </div>
                  </div>
                  {(['first', 'key', 'last'] as PromptFrameType[]).map((ft) => {
                    const st = keyframeCards[ft]
                    const slot = frameImages.find((x) => x.frame_type === ft)
                    const inUseFileId = slot?.file_id ? String(slot.file_id) : ''
                    const statusText =
                      st.taskStatus === 'pending'
                        ? '排队中'
                        : st.taskStatus === 'running'
                          ? '生成中'
                          : st.taskStatus === 'succeeded'
                            ? '已完成'
                            : st.taskStatus === 'failed'
                              ? '失败'
                              : st.taskStatus === 'cancelled'
                                ? '已取消'
                                : ''
                    return (
                      <div key={ft} className="cs-group">
                        <div className="cs-group-title flex items-center justify-between gap-2">
                          <span>{frameLabel[ft]}图片</span>
                          <Space size={8}>
                            <Button size="small" type="link" onClick={() => updateCardState(ft, { modalOpen: true })}>
                              更多
                            </Button>
                            <Button size="small" type="primary" loading={st.loading} onClick={() => void generateKeyframeCard(ft)}>
                              生成
                            </Button>
                          </Space>
                        </div>
                        <div className="text-xs text-gray-500 min-h-5">{statusText}</div>
                        {st.thumbs.length === 0 ? (
                          <div className="mt-2 h-24 border border-dashed rounded flex items-center justify-center text-xs text-gray-400">暂无图片</div>
                        ) : (
                          <div className="mt-2 flex items-center gap-2 overflow-x-auto whitespace-nowrap pb-1">
                            {st.thumbs.slice(0, 4).map((it) => (
                              <img key={it.linkId} src={it.thumbUrl} alt="" className="w-16 h-16 rounded object-cover border border-gray-200 shrink-0" />
                            ))}
                          </div>
                        )}
                        <Modal title={`${frameLabel[ft]}图片`} open={st.modalOpen} onCancel={() => updateCardState(ft, { modalOpen: false })} footer={null} width={720}>
                          {ft === 'first' ? (
                            <div className="mb-3">
                              <div className="text-sm text-gray-600 mb-2">关联角色</div>
                              <div className="flex items-center gap-2 overflow-x-auto pb-1">
                                <button
                                  type="button"
                                  className="w-12 h-12 rounded border border-dashed border-gray-300 flex items-center justify-center text-gray-500 shrink-0 hover:border-gray-400 hover:text-gray-700"
                                  disabled={promptAssetsUpdating || linkRoleLoading}
                                  onClick={() => {
                                    setLinkRoleSelectedIds([])
                                    setLinkRoleOpen(true)
                                    void loadProjectRoleOptions()
                                  }}
                                  title="添加关联角色"
                                >
                                  <PlusOutlined />
                                </button>
                                {linkedCharacterIds.length === 0 ? (
                                  <div className="text-xs text-gray-400">暂无关联角色</div>
                                ) : (
                                  linkedCharacterIds.map((cid) => {
                                    const thumb = linkedAssetThumbByKey.get(`character:${cid}`)
                                    const name = characterNameMap[cid] ?? cid
                                    return thumb ? (
                                    <Image
                                        key={cid}
                                        width={48}
                                        height={48}
                                        style={{ objectFit: 'cover', borderRadius: 8 }}
                                        src={resolveAssetUrl(thumb)}
                                        preview={{ src: resolveAssetUrl(thumb) }}
                                      />
                                    ) : (
                                      <div
                                        key={cid}
                                        title={name}
                                        className="w-12 h-12 rounded bg-gray-100 flex items-center justify-center text-gray-400 shrink-0"
                                      >
                                        <UserOutlined />
                                      </div>
                                    )
                                  })
                                )}
                              </div>

                              <div className="mt-3 text-sm text-gray-600 mb-2">关联场景</div>
                              <div className="flex items-center gap-2 overflow-x-auto pb-1">
                                <button
                                  type="button"
                                  className="w-12 h-12 rounded border border-dashed border-gray-300 flex items-center justify-center text-gray-500 shrink-0 hover:border-gray-400 hover:text-gray-700"
                                  disabled={promptAssetsUpdating || linkSceneLoading}
                                  onClick={() => {
                                    setLinkSceneOpen(true)
                                    void loadProjectAssetOptions('scene')
                                  }}
                                  title="添加/更换关联场景"
                                >
                                  <PlusOutlined />
                                </button>
                                {linkedSceneId ? (
                                  linkedAssetThumbByKey.get(`scene:${linkedSceneId}`) ? (
                                    <Image
                                      key={linkedSceneId}
                                      width={48}
                                      height={48}
                                      style={{ objectFit: 'cover', borderRadius: 8 }}
                                      src={resolveAssetUrl(linkedAssetThumbByKey.get(`scene:${linkedSceneId}`) ?? '')}
                                      preview={{ src: resolveAssetUrl(linkedAssetThumbByKey.get(`scene:${linkedSceneId}`) ?? '') }}
                                    />
                                  ) : (
                                    <div className="text-xs text-gray-400">已关联场景：{sceneNameMap[linkedSceneId] ?? linkedSceneId}</div>
                                  )
                                ) : (
                                  <div className="text-xs text-gray-400">暂无关联场景</div>
                                )}
                              </div>

                              <div className="mt-3 text-sm text-gray-600 mb-2">关联道具</div>
                              <div className="flex items-center gap-2 overflow-x-auto pb-1">
                                <button
                                  type="button"
                                  className="w-12 h-12 rounded border border-dashed border-gray-300 flex items-center justify-center text-gray-500 shrink-0 hover:border-gray-400 hover:text-gray-700"
                                  disabled={promptAssetsUpdating || linkPropLoading}
                                  onClick={() => {
                                    setLinkPropSelectedIds([])
                                    setLinkPropOpen(true)
                                    void loadProjectAssetOptions('prop')
                                  }}
                                  title="添加关联道具"
                                >
                                  <PlusOutlined />
                                </button>
                                {linkedPropIds.length === 0 ? (
                                  <div className="text-xs text-gray-400">暂无关联道具</div>
                                ) : (
                                  linkedPropIds.map((pid) =>
                                    linkedAssetThumbByKey.get(`prop:${pid}`) ? (
                                      <Image
                                        key={pid}
                                        width={48}
                                        height={48}
                                        style={{ objectFit: 'cover', borderRadius: 8 }}
                                        src={resolveAssetUrl(linkedAssetThumbByKey.get(`prop:${pid}`) ?? '')}
                                        preview={{ src: resolveAssetUrl(linkedAssetThumbByKey.get(`prop:${pid}`) ?? '') }}
                                      />
                                    ) : (
                                      <div key={pid} className="w-12 h-12 rounded bg-gray-100 flex items-center justify-center text-gray-400 shrink-0">
                                        <UserOutlined />
                                      </div>
                                    ),
                                  )
                                )}
                              </div>

                              <div className="mt-3 text-sm text-gray-600 mb-2">关联服装</div>
                              <div className="flex items-center gap-2 overflow-x-auto pb-1">
                                <button
                                  type="button"
                                  className="w-12 h-12 rounded border border-dashed border-gray-300 flex items-center justify-center text-gray-500 shrink-0 hover:border-gray-400 hover:text-gray-700"
                                  disabled={promptAssetsUpdating || linkCostumeLoading}
                                  onClick={() => {
                                    setLinkCostumeSelectedIds([])
                                    setLinkCostumeOpen(true)
                                    void loadProjectAssetOptions('costume')
                                  }}
                                  title="添加关联服装"
                                >
                                  <PlusOutlined />
                                </button>
                                {linkedCostumeIds.length === 0 ? (
                                  <div className="text-xs text-gray-400">暂无关联服装</div>
                                ) : (
                                  linkedCostumeIds.map((cid) =>
                                    linkedAssetThumbByKey.get(`costume:${cid}`) ? (
                                      <Image
                                        key={cid}
                                        width={48}
                                        height={48}
                                        style={{ objectFit: 'cover', borderRadius: 8 }}
                                        src={resolveAssetUrl(linkedAssetThumbByKey.get(`costume:${cid}`) ?? '')}
                                        preview={{ src: resolveAssetUrl(linkedAssetThumbByKey.get(`costume:${cid}`) ?? '') }}
                                      />
                                    ) : (
                                      <div key={cid} className="w-12 h-12 rounded bg-gray-100 flex items-center justify-center text-gray-400 shrink-0">
                                        <UserOutlined />
                                      </div>
                                    ),
                                  )
                                )}
                              </div>
                            </div>
                          ) : null}

                          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                            {st.thumbs.map((it) => {
                              const inUse = inUseFileId && inUseFileId === it.fileId
                              return (
                                <div key={it.linkId} className="border rounded p-2">
                                  <img src={it.thumbUrl} alt="" className="w-full h-36 object-cover rounded" />
                                  <div className="mt-2 flex items-center justify-between">
                                    {inUse ? (
                                      <Tag color="green">使用中</Tag>
                                    ) : (
                                      <Button size="small" loading={st.applyingFileId === it.fileId} onClick={() => void applyCardImage(ft, it.fileId)}>
                                        使用
                                      </Button>
                                    )}
                                  </div>
                                </div>
                              )
                            })}
                          </div>

                          <Modal
                            title="关联角色"
                            open={linkRoleOpen}
                            onCancel={() => setLinkRoleOpen(false)}
                            footer={null}
                            destroyOnClose
                            width={560}
                          >
                            <div className="space-y-2">
                              <div className="text-xs text-gray-500">来源：当前项目全部角色（选择后立即保存；已关联的角色不可重复选择）</div>
                              <Select
                                mode="multiple"
                                className="w-full"
                                placeholder="选择要关联到当前分镜的角色"
                                value={linkRoleSelectedIds}
                                loading={linkRoleLoading}
                                disabled={promptAssetsUpdating}
                                options={projectRoleOptions}
                                optionFilterProp="searchLabel"
                                showSearch
                                filterOption={(input: string, option?: any) =>
                                  String(option?.searchLabel ?? '').toLowerCase().includes(input.toLowerCase())
                                }
                                onChange={(vals: Array<string | number>) => {
                                  const nextNew = (vals ?? []).map((v) => String(v)).filter(Boolean)
                                  setLinkRoleSelectedIds(nextNew)
                                  const merged = Array.from(new Set([...linkedCharacterIds, ...nextNew]))
                                  void (async () => {
                                    await onUpdatePromptActors(merged)
                                    setLinkRoleOpen(false)
                                    setLinkRoleSelectedIds([])
                                  })()
                                }}
                              />
                            </div>
                          </Modal>

                          <Modal
                            title="关联场景"
                            open={linkSceneOpen}
                            onCancel={() => setLinkSceneOpen(false)}
                            footer={null}
                            destroyOnClose
                            width={560}
                          >
                            <div className="space-y-2">
                              <div className="text-xs text-gray-500">来源：当前项目场景（选择后立即保存）</div>
                              <Select
                                className="w-full"
                                placeholder="选择要关联到当前分镜的场景"
                                value={linkedSceneId ?? undefined}
                                loading={linkSceneLoading}
                                disabled={promptAssetsUpdating}
                                options={projectSceneOptions}
                                optionFilterProp="searchLabel"
                                showSearch
                                filterOption={(input: string, option?: any) =>
                                  String(option?.searchLabel ?? '').toLowerCase().includes(input.toLowerCase())
                                }
                                onChange={(v: string) => {
                                  void (async () => {
                                    await onUpdatePromptScene(v)
                                    setLinkSceneOpen(false)
                                  })()
                                }}
                              />
                            </div>
                          </Modal>

                          <Modal
                            title="关联道具"
                            open={linkPropOpen}
                            onCancel={() => setLinkPropOpen(false)}
                            footer={null}
                            destroyOnClose
                            width={560}
                          >
                            <div className="space-y-2">
                              <div className="text-xs text-gray-500">来源：当前项目道具（选择后立即保存；已关联的不可重复选择）</div>
                              <Select
                                mode="multiple"
                                className="w-full"
                                placeholder="选择要关联到当前分镜的道具"
                                value={linkPropSelectedIds}
                                loading={linkPropLoading}
                                disabled={promptAssetsUpdating}
                                options={projectPropOptions}
                                optionFilterProp="searchLabel"
                                showSearch
                                filterOption={(input: string, option?: any) =>
                                  String(option?.searchLabel ?? '').toLowerCase().includes(input.toLowerCase())
                                }
                                onChange={(vals: Array<string | number>) => {
                                  const nextNew = (vals ?? []).map((v) => String(v)).filter(Boolean)
                                  setLinkPropSelectedIds(nextNew)
                                  const merged = Array.from(new Set([...linkedPropIds, ...nextNew]))
                                  void (async () => {
                                    await onUpdatePromptProps(merged)
                                    setLinkPropOpen(false)
                                    setLinkPropSelectedIds([])
                                  })()
                                }}
                              />
                            </div>
                          </Modal>

                          <Modal
                            title="关联服装"
                            open={linkCostumeOpen}
                            onCancel={() => setLinkCostumeOpen(false)}
                            footer={null}
                            destroyOnClose
                            width={560}
                          >
                            <div className="space-y-2">
                              <div className="text-xs text-gray-500">来源：当前项目服装（选择后立即保存；已关联的不可重复选择）</div>
                              <Select
                                mode="multiple"
                                className="w-full"
                                placeholder="选择要关联到当前分镜的服装"
                                value={linkCostumeSelectedIds}
                                loading={linkCostumeLoading}
                                disabled={promptAssetsUpdating}
                                options={projectCostumeOptions}
                                optionFilterProp="searchLabel"
                                showSearch
                                filterOption={(input: string, option?: any) =>
                                  String(option?.searchLabel ?? '').toLowerCase().includes(input.toLowerCase())
                                }
                                onChange={(vals: Array<string | number>) => {
                                  const nextNew = (vals ?? []).map((v) => String(v)).filter(Boolean)
                                  setLinkCostumeSelectedIds(nextNew)
                                  const merged = Array.from(new Set([...linkedCostumeIds, ...nextNew]))
                                  void (async () => {
                                    await onUpdatePromptCostumes(merged)
                                    setLinkCostumeOpen(false)
                                    setLinkCostumeSelectedIds([])
                                  })()
                                }}
                              />
                            </div>
                          </Modal>
                        </Modal>
                      </div>
                    )
                  })}
                </div>
              ),
            },
              ...(showAvTab ? [{
                key: 'av',
                label: '音视频控制',
                children: (
                  <div>
                    <div className="cs-group">
                      <div className="cs-group-title">
                        <CustomerServiceOutlined /> 配乐
                      </div>
                      <div className="space-y-3">
                        <Radio.Group
                          value={audioMode}
                          onChange={(e) => setAudioMode(e.target.value)}
                          options={[
                            { value: 'none', label: '无' },
                            { value: 'prompt', label: '提示词' },
                            { value: 'upload', label: '上传音频' },
                          ]}
                        />
                        {audioMode === 'prompt' && <TextArea rows={3} placeholder="配乐提示词（支持多版本）…" />}
                        {audioMode === 'upload' && (
                          <Button block icon={<UploadOutlined />}>
                            上传音频
                          </Button>
                        )}
                      </div>
                    </div>

                    <div className="cs-group">
                      <div className="cs-group-title">
                        <SoundOutlined /> 音效
                      </div>
                      <div className="space-y-3">
                        <Button block icon={<UploadOutlined />}>
                          添加一条音效（Mock）
                        </Button>
                      </div>
                    </div>

                    <div className="cs-group">
                      <div className="cs-group-title">
                        <SettingOutlined /> 开关
                      </div>
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-sm">关闭配乐</span>
                          <Switch />
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-sm">关闭对白</span>
                          <Switch />
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-sm">智能对口型</span>
                          <Switch />
                        </div>
                      </div>
                    </div>
                  </div>
                ),
              }] : []),
              {
              key: 'gen_ref',
              label: '视频生成',
              children: (
                <div>
                  <ChapterStudioVideoReadinessPanel
                    selectedShot={selectedShot}
                    videoReadinessLoading={videoReadinessLoading}
                    videoReadiness={videoReadiness}
                  />

                  <div className="cs-group">
                    <div className="cs-group-title">
                      <LinkOutlined /> 参考
                    </div>
                    <Select
                      allowClear
                      placeholder="按已有关键帧类型选择"
                      className="w-full"
                      value={refImageType}
                      onChange={(v) => setRefImageType(v === undefined || v === null ? undefined : String(v))}
                      options={refFrameTypeOptions}
                      loading={refFrameTypeSelectLoading}
                      onDropdownVisibleChange={handleRefFrameTypeDropdownVisibleChange}
                    />
                  </div>

                  {showGenRefParams && (
                    <div className="cs-group">
                      <div className="cs-group-title">
                        <ToolOutlined /> 参数
                      </div>
                      <Space direction="vertical" className="w-full" size="small">
                        <Select
                          size="small"
                          placeholder="模型选择"
                          options={[
                            { value: 'model_a', label: '模型 A（写实）' },
                            { value: 'model_b', label: '模型 B（风格化）' },
                          ]}
                        />
                        <div className="flex items-center justify-between">
                          <span className="text-sm">ControlNet（深度/骨骼）</span>
                          <Switch checked={useBoneDepth} onChange={setUseBoneDepth} />
                        </div>
                        <Slider min={3} max={12} defaultValue={5} />
                      </Space>
                    </div>
                  )}

                  <div className="cs-group">
                    <div className="cs-group-title">
                      <ThunderboltOutlined /> 生成
                    </div>
                    <Space direction="vertical" className="w-full" size="small">
                      <Popover
                        open={videoModelPickerOpen}
                        onOpenChange={setVideoModelPickerOpen}
                        trigger="click"
                        placement="leftTop"
                        title={<span className="text-sm font-medium">选择视频模型</span>}
                        content={(
                          <div style={{ width: 260 }}>
                            {videoModelsLoading ? (
                              <div className="py-3 text-center text-xs text-gray-400">加载中...</div>
                            ) : videoModels.length === 0 ? (
                              <div className="py-3 text-center text-xs text-gray-400">
                                暂无可用视频模型，请先在模型管理中配置
                              </div>
                            ) : (
                              <div className="space-y-1">
                                {videoModels.map((model) => (
                                  <div
                                    key={model.id}
                                    role="button"
                                    tabIndex={0}
                                    onClick={() => {
                                      setSelectedVideoModelId(model.id)
                                      setVideoModelPickerOpen(false)
                                    }}
                                    onKeyDown={(event) => {
                                      if (event.key === 'Enter' || event.key === ' ') {
                                        event.preventDefault()
                                        setSelectedVideoModelId(model.id)
                                        setVideoModelPickerOpen(false)
                                      }
                                    }}
                                    className={[
                                      'flex cursor-pointer items-start gap-2 rounded px-3 py-2 transition-colors select-none',
                                      selectedVideoModelId === model.id ? 'bg-blue-50 ring-1 ring-blue-400' : 'hover:bg-gray-50',
                                    ].join(' ')}
                                  >
                                    <div className="flex-1 min-w-0">
                                      <div className="truncate text-sm font-medium text-gray-800">{model.name}</div>
                                      <div className="mt-0.5 flex items-center gap-1.5">
                                        <Tag className="m-0 flex-shrink-0 px-1 py-0 text-[10px] leading-4">{model.provider_name}</Tag>
                                      </div>
                                      {model.description ? <div className="mt-1 text-xs text-gray-500">{model.description}</div> : null}
                                    </div>
                                    {selectedVideoModelId === model.id && <CheckOutlined className="mt-0.5 flex-shrink-0 text-blue-500" />}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      >
                        <Button
                          size="small"
                          block
                          loading={videoModelsLoading}
                          icon={<AppstoreOutlined />}
                          className="text-left"
                          style={{ justifyContent: 'flex-start' }}
                        >
                          {selectedVideoModel ? selectedVideoModel.name : '选择模型'}
                        </Button>
                      </Popover>
                      <Segmented
                        size="small"
                        block
                        value={videoResolution}
                        options={[
                          { value: '720p', label: '720p' },
                          { value: '1080p', label: '1080p' },
                        ]}
                        onChange={(value) => setVideoResolution(value as '720p' | '1080p')}
                      />
                      <PointsCostHint quote={videoQuote.quote} loading={videoQuote.loading} error={videoQuote.error} />
                      <Button type="primary" block icon={<VideoCameraOutlined />} disabled={!videoQuote.canSubmit} loading={videoPromptPreviewSubmitting || videoTaskPolling} onClick={() => void openVideoPromptPreview()}>
                        生成视频
                      </Button>
                      {videoTaskStatus ? <span className="text-xs text-gray-500">任务状态：{videoTaskStatus}</span> : null}
                    </Space>
                  </div>

                  {showGenRefVersions && (
                    <div className="cs-group">
                      <div className="cs-group-title">
                        <AppstoreOutlined /> 版本
                      </div>
                      <Tabs
                        type="card"
                        size="small"
                        activeKey={imageVersion}
                        onChange={setImageVersion}
                        items={[
                          { key: 'v1', label: 'v1' },
                          { key: 'v2', label: 'v2' },
                          { key: 'v3', label: 'v3' },
                        ]}
                      />
                    </div>
                  )}
                </div>
              ),
              },
            ]

            const order: Record<string, number> = {
              prompt_image: 0,
              keyframe_gen: 1,
              camera: 2,
              gen_ref: 3,
              av: 4,
            }

            return items.sort((a, b) => (order[String(a.key)] ?? 999) - (order[String(b.key)] ?? 999))
          })()}
        />

        <Modal
          title={`${frameLabel[keyframePromptPreviewFrameType]}图片生成提示词预览`}
          open={keyframePromptPreviewOpen}
          onCancel={() => {
            if (keyframePromptActionLoading) return
            setKeyframePromptPreviewOpen(false)
          }}
          footer={(
            <div className="flex items-center justify-between">
              <PointsCostHint quote={imageQuote.quote} loading={imageQuote.loading} error={imageQuote.error} />
              <Space>
                <Button
                  loading={keyframePromptActionLoading}
                  onClick={() => {
                    if (keyframePromptActionLoading) return
                    setKeyframePromptPreviewOpen(false)
                  }}
                >
                  取消
                </Button>
                <Button type="primary" loading={keyframePromptActionLoading} disabled={!imageQuote.canSubmit} onClick={() => void confirmGenerateKeyframeWithPrompt()}>
                  生成
                </Button>
              </Space>
            </div>
          )}
          destroyOnClose
          width={900}
        >
          {(() => {
            const hasBasePrompt = keyframePromptPreviewDraft.trim().length > 0
            const renderStatusMeta = getKeyframeRenderStatusMeta(keyframePromptRenderState)
            const debugVisualStyle = readDebugContextText(keyframePromptDebugContext, 'visual_style')
            const debugStyle = readDebugContextText(keyframePromptDebugContext, 'style')
            const debugCharacterContext = readDebugContextText(keyframePromptDebugContext, 'character_context')
            const debugSceneContext = readDebugContextText(keyframePromptDebugContext, 'scene_context')
            const debugPropContext = readDebugContextText(keyframePromptDebugContext, 'prop_context')
            const debugCostumeContext = readDebugContextText(keyframePromptDebugContext, 'costume_context')
            const debugShotDescription = readDebugContextText(keyframePromptDebugContext, 'shot_description')
            const debugDialogSummary = readDebugContextText(keyframePromptDebugContext, 'dialog_summary')
            const debugPreviousShotTitle = readDebugContextText(keyframePromptDebugContext, 'previous_shot_title')
            const debugPreviousShotScriptExcerpt = readDebugContextText(keyframePromptDebugContext, 'previous_shot_script_excerpt')
            const debugPreviousShotEndState = readDebugContextText(keyframePromptDebugContext, 'previous_shot_end_state')
            const debugNextShotTitle = readDebugContextText(keyframePromptDebugContext, 'next_shot_title')
            const debugNextShotScriptExcerpt = readDebugContextText(keyframePromptDebugContext, 'next_shot_script_excerpt')
            const debugNextShotStartGoal = readDebugContextText(keyframePromptDebugContext, 'next_shot_start_goal')
            const debugContinuityGuidance = readDebugContextText(keyframePromptDebugContext, 'continuity_guidance')
            const debugCompositionAnchor = readDebugContextText(keyframePromptDebugContext, 'composition_anchor')
            const debugScreenDirectionGuidance = readDebugContextText(keyframePromptDebugContext, 'screen_direction_guidance')
            const debugFrameSpecificGuidance = readDebugContextText(keyframePromptDebugContext, 'frame_specific_guidance')
            const debugDirectorCommandSummary = readDebugContextText(keyframePromptDebugContext, 'director_command_summary')
            const debugActionBeatPhases = readDebugContextText(keyframePromptDebugContext, 'action_beat_phases')
            const debugSelectedActionBeatPhase = readDebugContextText(keyframePromptDebugContext, 'selected_action_beat_phase')
            const debugSelectedActionBeatText = readDebugContextText(keyframePromptDebugContext, 'selected_action_beat_text')
            const actionBeatPhaseTags = buildActionBeatPhaseTags(debugActionBeatPhases)
            const parsedDirectorCommandSummary = parseDirectorCommandSummary(debugDirectorCommandSummary)
            const keyframeGuidanceSummary = buildKeyframeGuidanceSummary([
              debugDirectorCommandSummary,
              debugFrameSpecificGuidance,
              debugContinuityGuidance,
              debugCompositionAnchor,
              debugScreenDirectionGuidance,
            ])
            const guidanceLevelSummary = buildGuidanceLevelSummary(parsedDirectorCommandSummary, keyframeGuidanceSummary)
            const debugUnifyStyle =
              typeof keyframePromptDebugContext?.unify_style === 'boolean'
                ? (keyframePromptDebugContext.unify_style ? '是' : '否')
                : readDebugContextText(keyframePromptDebugContext, 'unify_style')
            const hasPromptDebugContext = Boolean(
              debugVisualStyle ||
                debugStyle ||
                debugCharacterContext ||
                debugSceneContext ||
                debugPropContext ||
                debugCostumeContext ||
                debugShotDescription ||
                debugDialogSummary ||
                debugPreviousShotTitle ||
                debugPreviousShotScriptExcerpt ||
                debugPreviousShotEndState ||
                debugNextShotTitle ||
                debugNextShotScriptExcerpt ||
                debugNextShotStartGoal ||
                debugContinuityGuidance ||
                debugCompositionAnchor ||
                debugScreenDirectionGuidance ||
                debugFrameSpecificGuidance ||
                debugDirectorCommandSummary ||
                debugActionBeatPhases ||
                debugSelectedActionBeatText ||
                debugUnifyStyle,
            )
            const hasPromptQualityChecks = keyframePromptQualityChecks !== null
            return keyframePromptPreviewLoading ? (
              <div className="py-8 text-center">
                <Spin />
              </div>
            ) : (
              <div className="space-y-4">
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <div className="mb-2 flex items-center justify-between">
                    <div>
                      <div className="text-sm font-medium text-slate-900">参考图映射</div>
                      <div className="mt-1 text-xs text-slate-500">
                        图片顺序会直接决定最终提示词中的图1、图2映射关系，并影响模型生成结果。
                      </div>
                    </div>
                    <Tag color="gold">顺序影响图1/图2</Tag>
                  </div>
                  {keyframePromptPreviewRefFileIds.length === 0 ? (
                    <div className="text-xs text-gray-400">暂无关联图片</div>
                  ) : (
                    <div className="flex gap-3 overflow-x-auto pb-1">
                      <Image.PreviewGroup>
                        {keyframePromptPreviewRefFileIds.map((fid, index) => (
                          <div key={fid} className="w-[92px] shrink-0">
                            <Tooltip title={shotLinkedAssetNameByFileId.get(fid) ?? fid}>
                              <Image
                                width={72}
                                height={72}
                                style={{ objectFit: 'cover', borderRadius: 8, border: '1px solid #e2e8f0' }}
                                src={buildFileDownloadUrl(fid)}
                              />
                            </Tooltip>
                            <div className="mt-1">
                              <Tag color="blue">{`图${index + 1}`}</Tag>
                            </div>
                            <div className="truncate text-[11px] text-gray-700">
                              {shotLinkedAssetNameByFileId.get(fid) ?? fid}
                            </div>
                            <div className="mt-1 flex gap-1">
                              <Button
                                size="small"
                                disabled={index === 0 || keyframePromptActionLoading || shotRenderPromptLoading}
                                onClick={() => moveKeyframePromptRefFile(index, index - 1)}
                              >
                                左移
                              </Button>
                              <Button
                                size="small"
                                disabled={
                                  index === keyframePromptPreviewRefFileIds.length - 1 ||
                                  keyframePromptActionLoading ||
                                  shotRenderPromptLoading
                                }
                                onClick={() => moveKeyframePromptRefFile(index, index + 1)}
                              >
                                右移
                              </Button>
                            </div>
                          </div>
                        ))}
                      </Image.PreviewGroup>
                    </div>
                  )}
                </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <div className="mb-2 flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium text-slate-900">基础提示词</div>
                    <div className="mt-1 text-xs text-slate-500">
                      描述画面内容本身，不包含图片映射说明。
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      AI生成会继承当前项目风格，并优先参考已确认的角色、场景、道具和服装设定。
                    </div>
                  </div>
                  <Space size="small">
                    <Tag color={hasBasePrompt ? 'blue' : 'default'}>{hasBasePrompt ? '可编辑' : '未生成'}</Tag>
                    <Button
                      size="small"
                      type={hasBasePrompt ? 'default' : 'primary'}
                      loading={keyframePromptActionLoading}
                      disabled={!shotFramePromptQuote.canSubmit}
                      onClick={() => void regenerateKeyframePrompt()}
                    >
                      AI生成
                    </Button>
                  </Space>
                </div>
                <div className="mb-2">
                  <PointsCostHint
                    quote={shotFramePromptQuote.quote}
                    loading={shotFramePromptQuote.loading}
                    error={shotFramePromptQuote.error}
                  />
                </div>
                {!hasBasePrompt ? (
                  <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
                    当前还没有基础提示词。你可以先让 AI 生成一版，再按需修改；也可以直接手动输入。
                  </div>
                  ) : null}
                  {hasPromptQualityChecks ? (
                    <div
                      className={`mb-3 rounded-lg border px-3 py-2 text-xs ${
                        keyframePromptQualityChecks?.passed
                          ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                          : 'border-amber-200 bg-amber-50 text-amber-700'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <Tag color={keyframePromptQualityChecks?.passed ? 'green' : 'gold'}>
                          {keyframePromptQualityChecks?.passed ? '质量校验通过' : '已触发自动修正'}
                        </Tag>
                        <span>
                          {keyframePromptQualityChecks?.passed
                            ? '本次 AI 生成已通过基础质量校验。'
                            : '本次 AI 生成触发过自动修正，系统已尽量清理不符合基础提示词要求的内容。'}
                        </span>
                      </div>
                    </div>
                  ) : null}
                  <Input.TextArea
                    rows={6}
                    value={keyframePromptPreviewDraft}
                    onChange={(e) => {
                      keyframePromptDraft.setBase((prev) => ({ ...prev, prompt: e.target.value }))
                      if (!e.target.value.trim()) {
                        keyframePromptDraft.resetDerived()
                      }
                    }}
                    placeholder="请输入基础提示词，例如人物动作、场景氛围、镜头视角等…"
                    disabled={keyframePromptActionLoading || shotRenderPromptLoading}
                  />
                  {keyframeGuidanceSummary.length > 0 || debugDirectorCommandSummary ? (
                    <div className="mt-3 rounded-lg border border-sky-200 bg-sky-50 px-3 py-3 text-xs text-sky-800">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="font-medium">基础提示词生成依据</div>
                          <div className="mt-1 text-sky-700">
                            这些导演约束主要用于生成上游基础提示词，默认先看摘要；只有少量高优先级规则会再进入最终图片提示词。
                          </div>
                        </div>
                        <Button size="small" type="text" onClick={() => setKeyframeDirectiveCollapsed((prev) => !prev)}>
                          {keyframeDirectiveCollapsed ? '展开细节' : '收起细节'}
                        </Button>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <Tag color="red">{`必须 ${guidanceLevelSummary.must}`}</Tag>
                        <Tag color="blue">{`优先 ${guidanceLevelSummary.prefer}`}</Tag>
                        <Tag>{`普通 ${guidanceLevelSummary.normal}`}</Tag>
                        {actionBeatPhaseTags.length > 0 ? (
                          <Tag color="purple">{`动作阶段 ${actionBeatPhaseTags.length}`}</Tag>
                        ) : null}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {(keyframeDirectiveCollapsed
                          ? (
                            parsedDirectorCommandSummary.length > 0
                              ? parsedDirectorCommandSummary
                                  .slice(0, 2)
                                  .map((item) => `${item.level === 'must' ? '必须' : '优先'} · ${item.text}`)
                              : keyframeGuidanceSummary.slice(0, 2)
                          )
                          : keyframeGuidanceSummary
                        ).map((item) => (
                          <Tooltip key={item} title={item}>
                            <Tag color="blue" className="max-w-[240px] overflow-hidden">
                              <span className="inline-block max-w-[200px] truncate align-bottom">{item}</span>
                            </Tag>
                          </Tooltip>
                        ))}
                      </div>
                      {actionBeatPhaseTags.length > 0 ? (
                        <div className="mt-3 rounded-lg border border-slate-200 bg-white px-3 py-3 text-xs text-slate-700">
                          <div className="flex items-center justify-between gap-2">
                            <div className="font-medium text-slate-800">当前帧消费的动作阶段</div>
                            {debugSelectedActionBeatPhase && debugSelectedActionBeatText ? (
                              <Tag color="purple">
                                {`${debugSelectedActionBeatPhase} · ${debugSelectedActionBeatText}`}
                              </Tag>
                            ) : null}
                          </div>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {actionBeatPhaseTags.map((item, index) => (
                              <Tooltip key={`${item.phaseLabel}:${index}:${item.text}`} title={`${item.phaseLabel} · ${item.text}`}>
                                <Tag
                                  color={
                                    item.phaseLabel === '触发'
                                      ? 'gold'
                                      : item.phaseLabel === '峰值'
                                        ? 'blue'
                                        : 'green'
                                  }
                                  className="max-w-[240px] overflow-hidden"
                                >
                                  <span className="inline-block max-w-[200px] truncate align-bottom">
                                    {item.phaseLabel} · {item.text}
                                  </span>
                                </Tag>
                              </Tooltip>
                            ))}
                          </div>
                        </div>
                      ) : null}
                      {!keyframeDirectiveCollapsed ? (
                        <div className="mt-3 grid gap-3 md:grid-cols-2">
                          {debugDirectorCommandSummary ? (
                            <div className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-3 text-xs text-indigo-800">
                              <div className="font-medium">高优先级导演指令</div>
                              <div className="mt-2 flex flex-wrap gap-2">
                                {parsedDirectorCommandSummary.map((item, index) => (
                                  <Tooltip key={`${item.level}:${index}:${item.text}`} title={`${item.level === 'must' ? '必须' : '优先'} · ${item.text}`}>
                                    <Tag
                                      color={item.level === 'must' ? 'red' : 'blue'}
                                      className="max-w-[240px] overflow-hidden"
                                    >
                                      <span className="inline-block max-w-[200px] truncate align-bottom">
                                        {item.level === 'must' ? '必须' : '优先'} · {item.text}
                                      </span>
                                    </Tag>
                                  </Tooltip>
                                ))}
                              </div>
                            </div>
                          ) : null}
                          {keyframeGuidanceSummary.length > 0 ? (
                            <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-3 text-xs text-blue-800">
                              <div className="font-medium">补充 Guidance</div>
                              <div className="mt-2 flex flex-wrap gap-2">
                                {keyframeGuidanceSummary.map((item) => (
                                  <Tooltip key={item} title={item}>
                                    <Tag color="blue" className="max-w-[220px] overflow-hidden">
                                      <span className="inline-block max-w-[180px] truncate align-bottom">{item}</span>
                                    </Tag>
                                  </Tooltip>
                                ))}
                              </div>
                            </div>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {hasPromptDebugContext ? (
                    <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-600">
                      <div className="flex items-center justify-between gap-3">
                        <div className="font-medium text-slate-700">最近一次 AI 生成上下文</div>
                        <Space size="small">
                          <Tag color="default">调试信息</Tag>
                          <Button
                            size="small"
                            type="text"
                            onClick={() => setKeyframePromptDebugCollapsed((prev) => !prev)}
                          >
                            {keyframePromptDebugCollapsed ? '展开细节' : '收起细节'}
                          </Button>
                        </Space>
                      </div>
                      {keyframePromptDebugCollapsed ? (
                        <div className="mt-2 text-slate-500">
                          调试信息默认收起，展开后可查看最近一次 AI 生成使用的项目风格、镜头描述、连续性约束与实体上下文。
                        </div>
                      ) : (
                        <div className="mt-2 grid gap-2 md:grid-cols-2">
                          <div>
                            <div className="text-slate-500">项目风格</div>
                            <div className="mt-1 text-slate-700">
                              {[debugVisualStyle, debugStyle].filter(Boolean).join(' / ') || '无'}
                            </div>
                          </div>
                          <div>
                            <div className="text-slate-500">统一风格</div>
                            <div className="mt-1 text-slate-700">{debugUnifyStyle || '无'}</div>
                          </div>
                          {debugShotDescription ? (
                            <div className="md:col-span-2">
                              <div className="text-slate-500">镜头补充描述</div>
                              <div className="mt-1 whitespace-pre-wrap text-slate-700">{debugShotDescription}</div>
                            </div>
                          ) : null}
                          {debugDialogSummary ? (
                            <div className="md:col-span-2">
                              <div className="text-slate-500">对白摘要</div>
                              <div className="mt-1 whitespace-pre-wrap text-slate-700">{debugDialogSummary}</div>
                            </div>
                          ) : null}
                          {debugActionBeatPhases ? (
                            <div className="md:col-span-2">
                              <div className="text-slate-500">动作拍点阶段</div>
                              <div className="mt-1 flex flex-wrap gap-2">
                                {actionBeatPhaseTags.map((item, index) => (
                                  <Tag
                                    key={`debug-action-phase:${index}:${item.text}`}
                                    color={
                                      item.phaseLabel === '触发'
                                        ? 'gold'
                                        : item.phaseLabel === '峰值'
                                          ? 'blue'
                                          : 'green'
                                    }
                                  >
                                    {`${item.phaseLabel} · ${item.text}`}
                                  </Tag>
                                ))}
                              </div>
                              {debugSelectedActionBeatPhase || debugSelectedActionBeatText ? (
                                <div className="mt-2 text-slate-700">
                                  {`当前帧优先消费：${[debugSelectedActionBeatPhase, debugSelectedActionBeatText].filter(Boolean).join(' · ')}`}
                                </div>
                              ) : null}
                            </div>
                          ) : null}
                          {debugPreviousShotTitle || debugPreviousShotScriptExcerpt || debugPreviousShotEndState ? (
                            <div className="md:col-span-2 rounded-lg border border-slate-200 bg-white px-3 py-3">
                              <div className="text-slate-500">上一镜头承接</div>
                              <div className="mt-1 space-y-1 text-slate-700">
                                {debugPreviousShotTitle ? <div>标题：{debugPreviousShotTitle}</div> : null}
                                {debugPreviousShotScriptExcerpt ? (
                                  <div className="whitespace-pre-wrap">摘录：{debugPreviousShotScriptExcerpt}</div>
                                ) : null}
                                {debugPreviousShotEndState ? (
                                  <div className="whitespace-pre-wrap">结尾状态：{debugPreviousShotEndState}</div>
                                ) : null}
                              </div>
                            </div>
                          ) : null}
                          {debugNextShotTitle || debugNextShotScriptExcerpt || debugNextShotStartGoal ? (
                            <div className="md:col-span-2 rounded-lg border border-slate-200 bg-white px-3 py-3">
                              <div className="text-slate-500">下一镜头衔接</div>
                              <div className="mt-1 space-y-1 text-slate-700">
                                {debugNextShotTitle ? <div>标题：{debugNextShotTitle}</div> : null}
                                {debugNextShotScriptExcerpt ? (
                                  <div className="whitespace-pre-wrap">摘录：{debugNextShotScriptExcerpt}</div>
                                ) : null}
                                {debugNextShotStartGoal ? (
                                  <div className="whitespace-pre-wrap">起始目标：{debugNextShotStartGoal}</div>
                                ) : null}
                              </div>
                            </div>
                          ) : null}
                          {debugContinuityGuidance ? (
                            <div className="md:col-span-2">
                              <div className="text-slate-500">连续性建议</div>
                              <div className="mt-1 whitespace-pre-wrap text-slate-700">{debugContinuityGuidance}</div>
                            </div>
                          ) : null}
                          {debugCompositionAnchor ? (
                            <div className="md:col-span-2">
                              <div className="text-slate-500">构图与空间锚点</div>
                              <div className="mt-1 whitespace-pre-wrap text-slate-700">{debugCompositionAnchor}</div>
                            </div>
                          ) : null}
                          {debugScreenDirectionGuidance ? (
                            <div className="md:col-span-2">
                              <div className="text-slate-500">朝向与视线建议</div>
                              <div className="mt-1 whitespace-pre-wrap text-slate-700">{debugScreenDirectionGuidance}</div>
                            </div>
                          ) : null}
                          {debugFrameSpecificGuidance ? (
                            <div className="md:col-span-2">
                              <div className="text-slate-500">当前帧专项建议</div>
                              <div className="mt-1 whitespace-pre-wrap text-slate-700">{debugFrameSpecificGuidance}</div>
                            </div>
                          ) : null}
                          {debugCharacterContext ? (
                            <div className="md:col-span-2">
                              <div className="text-slate-500">角色上下文</div>
                              <div className="mt-1 whitespace-pre-wrap text-slate-700">{debugCharacterContext}</div>
                            </div>
                          ) : null}
                          {debugSceneContext ? (
                            <div className="md:col-span-2">
                              <div className="text-slate-500">场景上下文</div>
                              <div className="mt-1 whitespace-pre-wrap text-slate-700">{debugSceneContext}</div>
                            </div>
                          ) : null}
                          {debugPropContext ? (
                            <div className="md:col-span-2">
                              <div className="text-slate-500">道具上下文</div>
                              <div className="mt-1 whitespace-pre-wrap text-slate-700">{debugPropContext}</div>
                            </div>
                          ) : null}
                          {debugCostumeContext ? (
                            <div className="md:col-span-2">
                              <div className="text-slate-500">服装上下文</div>
                              <div className="mt-1 whitespace-pre-wrap text-slate-700">{debugCostumeContext}</div>
                            </div>
                          ) : null}
                        </div>
                      )}
                    </div>
                  ) : null}
                </div>

                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <div>
                      <div className="text-sm font-medium text-slate-900">最终生成提示词</div>
                      <div className="mt-1 text-xs text-slate-500">
                        系统会根据当前基础提示词和参考图顺序自动生成这一版内容，提交给模型时将使用这里的结果。
                      </div>
                    </div>
                    <Space size="small">
                      <Tag color="geekblue">系统生成</Tag>
                      <Tag>只读</Tag>
                      <Button
                        size="small"
                        onClick={() =>
                          void renderShotPromptToTextarea({
                            frameType: keyframePromptPreviewFrameType,
                            prompt: keyframePromptPreviewDraft,
                            refFileIds:
                              keyframePromptPreviewRefFileIds.length > 0
                                ? keyframePromptPreviewRefFileIds
                                : autoKeyframeRefFileIds,
                          })
                        }
                        disabled={!hasBasePrompt}
                        loading={shotRenderPromptLoading}
                      >
                        重新同步
                      </Button>
                      <Button
                        size="small"
                        onClick={async () => {
                          try {
                            await navigator.clipboard.writeText(keyframePromptRenderedDraft || '')
                            message.success('最终提示词已复制')
                          } catch {
                            message.error('复制失败')
                          }
                        }}
                        disabled={!keyframePromptRenderedDraft.trim()}
                      >
                        复制
                      </Button>
                    </Space>
                  </div>
                  <div
                    className={`mb-3 rounded-lg border px-3 py-2 text-sm ${
                      renderStatusMeta.color === 'green'
                        ? 'border-green-200 bg-green-50 text-green-700'
                        : renderStatusMeta.color === 'blue'
                          ? 'border-blue-200 bg-blue-50 text-blue-700'
                          : renderStatusMeta.color === 'red'
                            ? 'border-red-200 bg-red-50 text-red-700'
                            : renderStatusMeta.color === 'gold'
                              ? 'border-amber-200 bg-amber-50 text-amber-700'
                              : 'border-slate-200 bg-white text-slate-600'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Tag color={renderStatusMeta.color}>{renderStatusMeta.label}</Tag>
                      <span>{renderStatusMeta.description}</span>
                    </div>
                  </div>
                  {keyframePromptRenderMappings.length > 0 ? (
                    <div className="mb-2 flex flex-wrap gap-2">
                      {keyframePromptRenderMappings.map((mapping) => (
                        <Tag key={`${mapping.token}:${mapping.file_id}`}>{`${mapping.token} = ${mapping.name}`}</Tag>
                      ))}
                    </div>
                  ) : null}
                  {keyframePromptSelectedGuidance.length > 0 || keyframePromptDroppedGuidance.length > 0 ? (
                    <div className="mb-3 rounded-lg border border-slate-200 bg-white px-3 py-3 text-xs text-slate-700">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="font-medium text-slate-900">最终图片提示词收敛结果</div>
                          <div className="mt-1 text-slate-500">
                            系统会从上游导演约束里挑出最关键的少量规则，补进最终图片提示词。
                          </div>
                        </div>
                        <Space size="small" wrap>
                          <Tag color="green">{`保留 ${keyframePromptSelectedGuidance.length}`}</Tag>
                          <Tag color="gold">{`压缩 ${keyframePromptDroppedGuidance.length}`}</Tag>
                          {(keyframePromptSelectedGuidance.length > 2 || keyframePromptDroppedGuidance.length > 0) ? (
                            <Button
                              size="small"
                              type="text"
                              onClick={() => setKeyframePromptDecisionCollapsed((prev) => !prev)}
                            >
                              {keyframePromptDecisionCollapsed ? '查看取舍' : '收起取舍'}
                            </Button>
                          ) : null}
                        </Space>
                      </div>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-3 text-xs text-emerald-800">
                          <div className="font-medium">实际保留的 Guidance</div>
                          {keyframePromptSelectedGuidance.length > 0 ? (
                            <div className="mt-2 flex flex-wrap gap-2">
                              {keyframePromptVisibleSelectedGuidanceDetails.map((item) => (
                                <Tooltip
                                  key={`selected:${item.text}`}
                                  title={(
                                    <div className="max-w-[320px] text-xs leading-5">
                                      {item.reasonTag ? (
                                        <Tag color="green" className="mb-1">
                                          {item.reasonTag}
                                        </Tag>
                                      ) : null}
                                      <div>{item.text}</div>
                                      {item.reason ? <div className="mt-1 text-slate-500">{item.reason}</div> : null}
                                    </div>
                                  )}
                                >
                                  <Tag color="green" className="max-w-[240px] overflow-hidden">
                                    <span className="inline-block max-w-[200px] truncate align-bottom">{item.text}</span>
                                  </Tag>
                                </Tooltip>
                              ))}
                              {keyframePromptDecisionCollapsed && keyframePromptSelectedGuidanceDetails.length > 2 ? (
                                <Tag>{`+${keyframePromptSelectedGuidanceDetails.length - 2} 条`}</Tag>
                              ) : null}
                            </div>
                          ) : (
                            <div className="mt-2 text-emerald-700">当前没有额外 guidance 被保留。</div>
                          )}
                        </div>
                        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-3 text-xs text-amber-800">
                          <div className="font-medium">已压缩的 Guidance</div>
                          {keyframePromptDroppedGuidance.length > 0 ? (
                            keyframePromptDecisionCollapsed ? (
                              <div className="mt-2 text-amber-700">
                                当前有 {keyframePromptDroppedGuidance.length} 条 guidance 被压缩，展开后可查看具体取舍原因。
                              </div>
                            ) : (
                              <div className="mt-2 flex flex-wrap gap-2">
                                {keyframePromptVisibleDroppedGuidanceDetails.map((item) => (
                                  <Tooltip
                                    key={`dropped:${item.text}`}
                                    title={(
                                      <div className="max-w-[320px] text-xs leading-5">
                                        {item.reasonTag ? (
                                          <Tag color="gold" className="mb-1">
                                            {item.reasonTag}
                                          </Tag>
                                        ) : null}
                                        <div>{item.text}</div>
                                        {item.reason ? <div className="mt-1 text-slate-500">{item.reason}</div> : null}
                                      </div>
                                    )}
                                  >
                                    <Tag color="gold" className="max-w-[240px] overflow-hidden">
                                      <span className="inline-block max-w-[200px] truncate align-bottom">{item.text}</span>
                                    </Tag>
                                  </Tooltip>
                                ))}
                              </div>
                            )
                          ) : (
                            <div className="mt-2 text-amber-700">当前没有 guidance 被压缩。</div>
                          )}
                        </div>
                      </div>
                    </div>
                  ) : null}
                  {hasBasePrompt ? (
                    <div className="rounded-lg border border-slate-200 bg-white px-3 py-3 text-sm leading-6 text-slate-800 whitespace-pre-wrap min-h-[220px]">
                      {keyframePromptRenderedDraft || '系统正在根据当前内容准备最终提示词…'}
                    </div>
                  ) : (
                    <div className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-6 text-sm text-slate-500">
                      <div className="font-medium text-slate-700">等待基础提示词</div>
                      <div className="mt-2">
                        基础提示词准备完成后，系统会自动：
                      </div>
                      <div className="mt-2 space-y-1 text-slate-500">
                        <div>1. 根据当前参考图顺序生成图1 / 图2映射</div>
                        <div>2. 补充“## 图片内容说明”</div>
                        <div>3. 生成最终提交给模型的提示词</div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )
          })()}
        </Modal>

        <Modal
          title="视频生成提示词预览"
          open={videoPromptPreviewOpen}
          onCancel={() => {
            if (videoPromptPreviewSubmitting) return
            setVideoPromptPreviewOpen(false)
          }}
          okText="生成"
          cancelText="取消"
          onOk={() => void submitVideoGeneration()}
          confirmLoading={videoPromptPreviewSubmitting}
          width={900}
          destroyOnClose
        >
          {videoPromptPreviewLoading ? (
            <div className="py-8 text-center">
              <Spin />
            </div>
          ) : (
            <div className="space-y-3">
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-600">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-medium text-slate-700">镜头连续性上下文</div>
                    <div className="mt-1 text-[11px] leading-5 text-slate-500">
                      这些上下文会参与视频模板渲染和最终提示词补强，默认先展示摘要，需要时再展开细节。
                    </div>
                  </div>
                  <Button
                    type="link"
                    size="small"
                    className="px-0"
                    onClick={() => setVideoPromptContextCollapsed((prev) => !prev)}
                  >
                    {videoPromptContextCollapsed ? '展开细节' : '收起细节'}
                  </Button>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Tag color="blue">{`动作节拍 ${videoActionBeats.length}`}</Tag>
                  {videoPromptPreviewPack?.previous_shot_summary ? (
                    <Tag color="purple">上一镜头</Tag>
                  ) : null}
                  {videoPromptPreviewPack?.next_shot_goal ? (
                    <Tag color="cyan">下一镜头</Tag>
                  ) : null}
                  {videoPromptPreviewPack?.continuity_guidance ? (
                    <Tag color="gold">连续性</Tag>
                  ) : null}
                </div>
                <div className="mt-3 space-y-3">
                  <div>
                    <div className="text-slate-500">动作节拍</div>
                    {videoVisibleActionBeats.length > 0 ? (
                      <div className="mt-1 flex flex-wrap gap-2">
                        {videoVisibleActionBeats.map((item, index) => (
                          <Tag
                            key={`${index}:${item.phase ?? 'raw'}:${item.text}`}
                            color={
                              item.phase === 'trigger'
                                ? 'gold'
                                : item.phase === 'peak'
                                  ? 'blue'
                                  : item.phase === 'aftermath'
                                    ? 'green'
                                    : 'default'
                            }
                          >
                            {item.phase
                              ? `${item.phase === 'trigger' ? '触发' : item.phase === 'peak' ? '峰值' : '收束'} · ${item.text}`
                              : item.text}
                          </Tag>
                        ))}
                        {videoPromptContextCollapsed && hiddenVideoActionBeatCount > 0 ? (
                          <Tag>{`+${hiddenVideoActionBeatCount}`}</Tag>
                        ) : null}
                      </div>
                    ) : (
                      <div className="mt-1 text-gray-400">暂无动作节拍</div>
                    )}
                  </div>
                  {!videoPromptContextCollapsed ? (
                    <>
                      <div>
                        <div className="text-slate-500">上一镜头摘要</div>
                        <div className="mt-1 whitespace-pre-wrap text-slate-700">
                          {videoPromptPreviewPack?.previous_shot_summary || '无'}
                        </div>
                      </div>
                      <div>
                        <div className="text-slate-500">下一镜头目标</div>
                        <div className="mt-1 whitespace-pre-wrap text-slate-700">
                          {videoPromptPreviewPack?.next_shot_goal || '无'}
                        </div>
                      </div>
                      <div>
                        <div className="text-slate-500">连续性建议</div>
                        <div className="mt-1 whitespace-pre-wrap text-slate-700">
                          {videoPromptPreviewPack?.continuity_guidance || '无'}
                        </div>
                      </div>
                      <div>
                        <div className="text-slate-500">构图与空间锚点</div>
                        <div className="mt-1 whitespace-pre-wrap text-slate-700">
                          {videoPromptPreviewPack?.composition_anchor || '无'}
                        </div>
                      </div>
                      <div>
                        <div className="text-slate-500">朝向与视线建议</div>
                        <div className="mt-1 whitespace-pre-wrap text-slate-700">
                          {videoPromptPreviewPack?.screen_direction_guidance || '无'}
                        </div>
                      </div>
                    </>
                  ) : null}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500 mb-2">关联图片（参考图）</div>
                {videoPromptPreviewImages.length === 0 ? (
                  <div className="text-xs text-gray-400">暂无关联图片</div>
                ) : (
                  <div className="flex gap-2 overflow-x-auto pb-1">
                    <Image.PreviewGroup>
                      {videoPromptPreviewImages.map((fid) => (
                        <Image
                          key={fid}
                          width={72}
                          height={72}
                          style={{ objectFit: 'cover', borderRadius: 8 }}
                          src={buildFileDownloadUrl(fid)}
                        />
                      ))}
                    </Image.PreviewGroup>
                  </div>
                )}
              </div>
              <div className="flex items-center gap-4 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <div className="text-xs font-medium text-slate-600">生成参数</div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500">分辨率</span>
                  <Select
                    size="small"
                    value={videoResolution}
                    options={[
                      { value: '720p', label: '720p（标准）' },
                      { value: '1080p', label: '1080p（高清）' },
                    ]}
                    onChange={(value) => setVideoResolution(value)}
                    disabled={videoPromptPreviewSubmitting}
                    style={{ width: 130 }}
                  />
                  <span className="text-xs text-slate-400">
                    {(videoResolution === '1080p'
                      ? ({ '16:9': '1920×1080', '4:3': '1440×1080', '1:1': '1080×1080', '3:4': '1080×1440', '9:16': '1080×1920', '21:9': '2520×1080' } as Record<string, string>)
                      : ({ '16:9': '1280×720', '4:3': '1024×768', '1:1': '1024×1024', '3:4': '768×1024', '9:16': '720×1280', '21:9': '1680×720' } as Record<string, string>)
                    )[resolveVideoRatioForRequest()] ?? ''}
                  </span>
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500 mb-2">提示词（可编辑）</div>
                <Input.TextArea
                  rows={10}
                  value={videoPromptPreviewDraft}
                  onChange={(e) => videoPromptDraft.setBase({ prompt: e.target.value })}
                  placeholder="请输入视频提示词…"
                  disabled={videoPromptPreviewSubmitting}
                />
              </div>
            </div>
          )}
        </Modal>
      </div>
    </div>
  )
}
