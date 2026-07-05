import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Button,
  Card,
  Col,
  Collapse,
  Empty,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd'
import { ArrowLeftOutlined, CheckOutlined, CloseCircleOutlined, EditOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons'
import { FilmService, LlmService, ScriptProcessingService, StudioFilesService } from '../../../../services/generated'
import type { AssetImageCandidateRead, ModelRead, ProviderRead, TaskStatus } from '../../../../services/generated'
import { buildFileDownloadUrl } from '../utils'
import { AssetImageCandidateGallery } from './AssetImageCandidateGallery'
import { DisplayImageCard } from './DisplayImageCard'
import { AssetReferencePickerDrawer, type AssetReferenceKind, type AssetReferenceOption } from './AssetReferencePickerDrawer'
import { AssetReferencePanel } from './AssetReferencePanel'
import { defaultTaskActionErrorMessage, executeAsyncTaskCreate, executeTaskCancel, notifyExistingTask } from '../../components/taskActionHelpers'
import { handleTaskResultSafely } from '../../components/taskResultHelpers'
import { useRelationTaskNotification } from '../../components/taskNotificationHelpers'
import { useTaskPageContext } from '../../components/taskPageContext'
import { TASK_COPY } from '../../components/taskCopy'
import { usePointsQuote } from '../../../../hooks/usePointsQuote'
import { PointsCostButton } from '../../../../components/points/PointsCostButton'
import { makePointsAwareGetErrorMessage } from '../../../../components/points/pointsTaskError'
import { useLocation } from 'react-router-dom'
import {
  CHARACTER_PORTRAIT_ANALYSIS_RELATION_TYPE,
  COSTUME_INFO_ANALYSIS_RELATION_TYPE,
  PROP_INFO_ANALYSIS_RELATION_TYPE,
  SCENE_INFO_ANALYSIS_RELATION_TYPE,
  type RelationTaskState,
  toRelationTaskStateFromStatusRead,
  useCancelableRelationTask,
} from '../../project/ProjectWorkbench/chapterDivisionTasks'

const MAX_VIEW_COUNT = 4
// 与后端 `AssetViewAngle`（backend/app/models/studio.py）一致的枚举值
export type AssetViewAngle =
  | 'FRONT'
  | 'LEFT'
  | 'RIGHT'
  | 'BACK'
  | 'THREE_QUARTER'
  | 'TOP'
  | 'DETAIL'

export type AssetUpdate = {
  name: string
  description: string
  tags: string[]
  view_count: number
  visual_style: string
  style?: string
}

const DEFAULT_ANGLES: AssetViewAngle[] = ['FRONT', 'LEFT', 'RIGHT', 'BACK']

export type BaseAsset = {
  id: string
  name: string
  description?: string
  tags?: string[]
  view_count?: number
  visual_style?: string
  style?: string
}

export type BaseAssetImage = {
  id: number
  view_angle?: AssetViewAngle
  file_id?: string | null
  width?: number | null
  height?: number | null
  format?: string | null
}

type ImageGenerationPayload = {
  prompt: string
  images: string[]
  model_id: string | null
  // 积分试算返回的 quote_token，透传到后端做幂等冻结与价格复核。
  quote_token: string | null
  resolution_profile: AssetImageResolutionProfile
}

type AssetImageResolutionProfile = 'standard' | 'high'

type RenderedPromptPreview = {
  prompt: string
  images: string[]
}

const ASSET_IMAGE_RESOLUTION_OPTIONS: Array<{ value: AssetImageResolutionProfile; label: string }> = [
  { value: 'standard', label: '1K' },
  { value: 'high', label: '2K' },
]

type ImageModelOption = ModelRead & {
  provider_name: string
}

export type AssetEditPageBaseProps<TAsset extends BaseAsset, TImage extends BaseAssetImage> = {
  assetId?: string
  missingAssetIdText: string
  assetDisplayName: string
  backTo: string
  relationType: string
  getAsset: (assetId: string) => Promise<TAsset | null>
  updateAsset: (assetId: string, payload: AssetUpdate) => Promise<TAsset | null>
  listImages: (assetId: string) => Promise<TImage[]>
  createImageSlot: (assetId: string, angle: AssetViewAngle) => Promise<void>
  updateImage: (assetId: string, imageId: number, payload: { file_id: string; width?: number | null; height?: number | null; format?: string | null }) => Promise<void>
  listImageCandidates: (assetId: string, imageId: number) => Promise<AssetImageCandidateRead[]>
  adoptImageCandidate: (assetId: string, imageId: number, candidateId: number) => Promise<void>
  deleteImageCandidate: (assetId: string, imageId: number, candidateId: number) => Promise<void>
  createGenerationTask: (assetId: string, imageId: number, payload: ImageGenerationPayload) => Promise<string | null>
  renderPromptPreview: (assetId: string, imageId: number, payload: { prompt: string; images: string[] }) => Promise<RenderedPromptPreview | null>
  attachImageCandidates?: (assetId: string, imageId: number, fileIds: string[]) => Promise<void>
  onNavigate: (to: string, replace?: boolean) => void
}

function normalizeTags(input: string): string[] {
  return input
    .split(/[,，\n]/g)
    .map((t) => t.trim())
    .filter(Boolean)
}

function clampViewCount(value?: number | null): number {
  const next = Number.isFinite(value as number) ? Number(value) : 1
  return Math.max(1, Math.min(MAX_VIEW_COUNT, Math.trunc(next)))
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function isTerminalStatus(status: TaskStatus): boolean {
  return status === 'succeeded' || status === 'failed' || status === 'cancelled'
}

// 从 generated client 或 fetch 包装错误中提取 HTTP 状态码，用于保存前冲突提示。
function getHttpStatus(error: unknown): number | undefined {
  const maybe = error as { status?: number; statusCode?: number; response?: { status?: number }; body?: { code?: number; status?: number } }
  return maybe.response?.status ?? maybe.status ?? maybe.statusCode ?? maybe.body?.status ?? maybe.body?.code
}

// 识别资产名唯一约束冲突，兼容 generated client、响应体和通用错误文本的不同包装。
function isAssetNameConflictError(error: unknown): boolean {
  if (getHttpStatus(error) === 409) return true

  const maybe = error as { message?: string; body?: { message?: string; detail?: string } }
  const text = [maybe.body?.message, maybe.body?.detail, maybe.message].filter(Boolean).join('\n')
  return /name already exists|Duplicate entry|uq_(actors|scenes|props|costumes)_name/i.test(text)
}

function getSmartDetectRelationType(relationType: string): string | null {
  if (relationType === 'actor_image' || relationType === 'character_image') return CHARACTER_PORTRAIT_ANALYSIS_RELATION_TYPE
  if (relationType === 'scene_image') return SCENE_INFO_ANALYSIS_RELATION_TYPE
  if (relationType === 'prop_image') return PROP_INFO_ANALYSIS_RELATION_TYPE
  if (relationType === 'costume_image') return COSTUME_INFO_ANALYSIS_RELATION_TYPE
  return null
}

function getAssetNavigateRelationType(relationType: string): string | null {
  if (relationType === 'actor_image') return 'actor'
  if (relationType === 'character_image') return 'character'
  if (relationType === 'scene_image') return 'scene'
  if (relationType === 'prop_image') return 'prop'
  if (relationType === 'costume_image') return 'costume'
  return null
}

// Loads every entity page for an @ mention category so the picker can expose all asset images.
// Loads every image page for one asset entity, keeping only records that have file_id.
export function AssetEditPageBase<TAsset extends BaseAsset, TImage extends BaseAssetImage>({
  assetId,
  missingAssetIdText,
  assetDisplayName,
  backTo,
  relationType,
  getAsset,
  updateAsset,
  listImages,
  createImageSlot,
  listImageCandidates,
  adoptImageCandidate,
  deleteImageCandidate,
  createGenerationTask,
  attachImageCandidates,
  onNavigate,
}: AssetEditPageBaseProps<TAsset, TImage>) {
  const taskCopy = TASK_COPY.smartDetect
  const location = useLocation()
  // 从 URL 读取一次性预填名称（由分镜准备"新建"按钮传入）。
  // 用 window.location.search 直接读取（而非 useSearchParams），避免清除时触发 React Router 重渲染链。
  const prefillNameRef = useRef<string | null>(
    new URLSearchParams(window.location.search).get('prefillName')?.trim() || null,
  )
  // onNavigate 来自父组件内联函数，每次渲染都是新引用；用 ref 稳定化以避免 loadData 被重建重跑。
  const onNavigateRef = useRef(onNavigate)
  onNavigateRef.current = onNavigate
  const [loading, setLoading] = useState(true)
  const [asset, setAsset] = useState<TAsset | null>(null)
  const [images, setImages] = useState<TImage[]>([])

  const [formName, setFormName] = useState('')
  const [formDesc, setFormDesc] = useState('')
  const [formTags, setFormTags] = useState('')
  const [savingBase, setSavingBase] = useState(false)
  const [imageModelsLoading, setImageModelsLoading] = useState(false)
  const [imageModels, setImageModels] = useState<ImageModelOption[]>([])
  const [selectedImageModelId, setSelectedImageModelId] = useState<string | null>(null)

  const [smartDetectLoading, setSmartDetectLoading] = useState(false)
  const [smartDetectOpen, setSmartDetectOpen] = useState(false)
  const [smartDetectIssues, setSmartDetectIssues] = useState<string[]>([])
  const [smartDetectOptimizedDesc, setSmartDetectOptimizedDesc] = useState('')

  const [generatingByImageId, setGeneratingByImageId] = useState<Record<number, boolean>>({})
  const [generationTask, setGenerationTask] = useState<RelationTaskState | null>(null)
  const [generationSettledTask, setGenerationSettledTask] = useState<RelationTaskState | null>(null)

  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyCandidates, setHistoryCandidates] = useState<AssetImageCandidateRead[]>([])
  const [editingSlotImage, setEditingSlotImage] = useState<TImage | null>(null)
  const [adoptingImageId, setAdoptingImageId] = useState<number | null>(null)
  const [uploadingCandidates, setUploadingCandidates] = useState(false)
  const [referenceOptions, setReferenceOptions] = useState<AssetReferenceOption[]>([])
  const [referenceFileIds, setReferenceFileIds] = useState<string[]>([])
  const [referencePickerOpen, setReferencePickerOpen] = useState(false)
  const [referencePickerInitialKind, setReferencePickerInitialKind] = useState<AssetReferenceKind>('scene')
  const [referenceReplaceFileId, setReferenceReplaceFileId] = useState<string | null>(null)
  const [pendingGenerateImage, setPendingGenerateImage] = useState<TImage | null>(null)
  const [generateConfirmOpen, setGenerateConfirmOpen] = useState(false)
  const [generateConfirmLoading, setGenerateConfirmLoading] = useState(false)
  const [generateConfirmPrompt, setGenerateConfirmPrompt] = useState('')
  const [generateConfirmImages, setGenerateConfirmImages] = useState<string[]>([])
  const [assetImageResolutionProfile, setAssetImageResolutionProfile] =
    useState<AssetImageResolutionProfile>('standard')

  const smartDetectRelationType = useMemo(() => getSmartDetectRelationType(relationType), [relationType])
  const smartDetectRelationEntityId = useMemo(
    () => (assetId && smartDetectRelationType ? `${relationType}:${assetId}` : null),
    [assetId, relationType, smartDetectRelationType],
  )
  const assetNavigateRelationType = useMemo(
    () => getAssetNavigateRelationType(relationType),
    [relationType],
  )

  // 资产智能检测：根据 relationType 映射到对应文本类业务计费标签。
  // 4 种分析（角色/场景/道具/服装）共享同一类调用入口但 business_type 不同，故动态解析。
  const smartDetectBusinessType = useMemo(() => {
    switch (relationType) {
      case 'actor_image':
      case 'character_image':
        return 'script_character_portrait'
      case 'scene_image':
        return 'script_scene_info'
      case 'prop_image':
        return 'script_prop_info'
      case 'costume_image':
        return 'script_costume_info'
      default:
        return ''
    }
  }, [relationType])
  const smartDetectDesc = (formDesc || '').trim()
  const smartDetectQuote = usePointsQuote({
    businessType: smartDetectBusinessType,
    category: 'text',
    modelId: null,
    enabled: !!smartDetectBusinessType && !!smartDetectDesc,
  })
  // 资产图片生成的积分试算。计费类别 image，模型跟随用户在模型选择区点选的具体模型；
  // 未选中模型时不试算（canSubmit=false 阻断生成）。
  const imageQuote = usePointsQuote({
    businessType: 'image_generation',
    category: 'image',
    modelId: selectedImageModelId,
    resolutionProfile: assetImageResolutionProfile,
    enabled: !!selectedImageModelId,
  })

  // Loads selectable image models so asset image generation can target a concrete model.
  useEffect(() => {
    let active = true
    setImageModelsLoading(true)
    void (async () => {
      try {
        const [modelsRes, providersRes] = await Promise.all([
          LlmService.listModelsApiV1LlmModelsGet({
            category: 'image',
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
          .filter((model) => model.category === 'image')
          .filter((model) => activeProviderIds.size === 0 || activeProviderIds.has(model.provider_id))
          .map((model) => ({
            ...model,
            provider_name: providerNameById.get(model.provider_id) ?? model.provider_id,
          }))
        setImageModels(items)
        setSelectedImageModelId((prev) => {
          if (prev && items.some((item) => item.id === prev)) return prev
          return items[0]?.id ?? null
        })
      } catch {
        if (active) {
          setImageModels([])
          setSelectedImageModelId(null)
        }
      } finally {
        if (active) {
          setImageModelsLoading(false)
        }
      }
    })()

    return () => {
      active = false
    }
  }, [])

  const applySmartDetectResult = useCallback(async (taskId: string) => {
    await handleTaskResultSafely(taskId, {
      readErrorMessage: '读取智能检测结果失败',
      failedFallbackMessage: '智能检测失败',
      onSucceeded: (resultValue) => {
        const result = resultValue as Record<string, any>
        const issues = Array.isArray(result.issues)
          ? result.issues.filter((it: unknown): it is string => typeof it === 'string' && it.trim().length > 0)
          : []
        const optimizedDesc = String(result.optimized_description ?? '').trim()
        setSmartDetectIssues(issues)
        setSmartDetectOptimizedDesc(optimizedDesc)
        setSmartDetectOpen(true)
        if (issues.length > 0) message.warning(`发现 ${issues.length} 项可能缺失信息`)
        else message.success('未发现缺失信息')
      },
      onFailed: (errorMessage) => {
        message.error(errorMessage)
      },
      onReadError: () => {
        message.error('读取智能检测结果失败')
      },
    })
  }, [])
  const { task: smartDetectTask, settledTask: smartDetectSettledTask, trackTaskData: trackSmartDetectTaskData, applyCancelData: applySmartDetectCancelData } = useCancelableRelationTask({
    enabled: !!assetId && !!smartDetectRelationType && !!smartDetectRelationEntityId,
    relationType: smartDetectRelationType || '',
    relationEntityId: smartDetectRelationEntityId,
    onTaskSettled: applySmartDetectResult,
  })
  useTaskPageContext(
    [
      smartDetectRelationType && smartDetectRelationEntityId
        ? {
            relationType: smartDetectRelationType,
            relationEntityId: smartDetectRelationEntityId,
          }
        : null,
      assetNavigateRelationType && assetId
        ? {
            relationType: assetNavigateRelationType,
            relationEntityId: assetId,
          }
        : null,
    ],
  )
  const smartDetectBusy = smartDetectLoading || !!smartDetectTask

  const ensureImageSlots = useCallback(async (targetViewCount: number) => {
    if (!assetId) return []

    let current = await listImages(assetId)

    const byAngle = new Map<AssetViewAngle, TImage>()
    current.forEach((img) => {
      if (img.view_angle && !byAngle.has(img.view_angle)) {
        byAngle.set(img.view_angle, img)
      }
    })

    const requiredAngles = DEFAULT_ANGLES.slice(0, targetViewCount)
    let created = false

    for (const angle of requiredAngles) {
      if (!byAngle.get(angle)) {
        await createImageSlot(assetId, angle)
        created = true
      }
    }

    if (created) {
      current = await listImages(assetId)
    }

    return current
  }, [assetId, createImageSlot, listImages])

  const loadData = useCallback(async () => {
    if (!assetId) return

    setLoading(true)
    try {
      const nextAsset = await getAsset(assetId)
      if (!nextAsset) {
        message.error(`未找到${assetDisplayName}资产`)
        onNavigateRef.current(backTo, true)
        return
      }

      setAsset(nextAsset)
      const prefillName = prefillNameRef.current
      prefillNameRef.current = null  // 消费一次后清空，防止 reload 时重复覆盖
      setFormName(prefillName ?? nextAsset.name)
      // prefillName 已消费，用 replaceState 清除 URL 参数。
      // 不用 setSearchParams 是因为它会触发父组件重渲染，导致 loadData 被重建重跑，覆盖掉刚设置的预填名称。
      if (prefillName) {
        const cleanUrl = new URL(window.location.href)
        cleanUrl.searchParams.delete('prefillName')
        window.history.replaceState(null, '', cleanUrl.toString())
      }
      setFormDesc(nextAsset.description ?? '')
      setFormTags((nextAsset.tags ?? []).join(', '))
      const targetCount = clampViewCount(nextAsset.view_count)
      const imageRows = await ensureImageSlots(targetCount)
      setImages(imageRows)
    } catch {
      message.error(`加载${assetDisplayName}资产失败`)
    } finally {
      setLoading(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assetId, assetDisplayName, backTo, ensureImageSlots, getAsset])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const slotItems = useMemo(() => {
    const count = clampViewCount(asset?.view_count)
    const byAngle = new Map<AssetViewAngle, TImage>()
    images.forEach((img) => {
      if (img.view_angle) byAngle.set(img.view_angle, img)
    })

    return DEFAULT_ANGLES.slice(0, count).map((angle) => {
      const image = byAngle.get(angle) ?? null
      return {
        angle,
        image,
        imageUrl: buildFileDownloadUrl(image?.file_id),
      }
    })
  }, [asset?.view_count, images])

  // Builds the asset update payload from the current form so generation can use unsaved edits.
  const buildBasePayload = useCallback((): AssetUpdate | null => {
    if (!formName.trim()) {
      message.warning('请输入名称')
      return null
    }

    return {
      name: formName.trim(),
      description: formDesc.trim(),
      tags: normalizeTags(formTags),
      view_count: clampViewCount(asset?.view_count),
      visual_style: asset?.visual_style ?? '现实',
      style: asset?.style,
    }
  }, [asset?.style, asset?.view_count, asset?.visual_style, formDesc, formName, formTags])

  const handleSmartDetectMissing = async () => {
    if (!assetId) return
    if (!smartDetectRelationEntityId) return

    const description = (formDesc || '').trim()
    if (!description) {
      if (relationType === 'actor_image') message.warning('请先输入演员描述再进行智能检测')
      else if (relationType === 'character_image') message.warning('请先输入角色描述再进行智能检测')
      else if (relationType === 'scene_image') message.warning('请先输入场景描述再进行智能检测')
      else if (relationType === 'prop_image') message.warning('请先输入道具描述再进行智能检测')
      else if (relationType === 'costume_image') message.warning('请先输入服装描述再进行智能检测')
      return
    }

    if (notifyExistingTask(smartDetectTask, {
      cancellingMessage: taskCopy.cancellingMessage,
      runningMessage: taskCopy.runningMessage,
    })) {
      return
    }

    setSmartDetectLoading(true)
    try {
      const request = () => {
        if (relationType === 'actor_image' || relationType === 'character_image') {
          const subjectLabel = relationType === 'character_image' ? '角色' : '演员'
          const character_context = asset?.name ? `${subjectLabel}名：${formName}\n标签：${formTags}` : `标签：${formTags}`
          return ScriptProcessingService.analyzeCharacterPortraitAsyncApiV1ScriptProcessingAnalyzeCharacterPortraitAsyncPost({
            requestBody: {
              relation_entity_id: smartDetectRelationEntityId,
              character_description: description,
              character_context: (character_context || '').trim() || null,
              quote_token: smartDetectQuote.quoteToken,
            },
          })
        }
        if (relationType === 'scene_image') {
          const scene_context = asset?.name ? `场景名：${formName}\n标签：${formTags}` : `标签：${formTags}`
          return ScriptProcessingService.analyzeSceneInfoAsyncApiV1ScriptProcessingAnalyzeSceneInfoAsyncPost({
            requestBody: {
              relation_entity_id: smartDetectRelationEntityId,
              scene_description: description,
              scene_context: (scene_context || '').trim() || null,
              quote_token: smartDetectQuote.quoteToken,
            },
          })
        }
        if (relationType === 'prop_image') {
          const prop_context = asset?.name ? `道具名：${formName}\n标签：${formTags}` : `标签：${formTags}`
          return ScriptProcessingService.analyzePropInfoAsyncApiV1ScriptProcessingAnalyzePropInfoAsyncPost({
            requestBody: {
              relation_entity_id: smartDetectRelationEntityId,
              prop_description: description,
              prop_context: (prop_context || '').trim() || null,
              quote_token: smartDetectQuote.quoteToken,
            },
          })
        }
        const costume_context = asset?.name ? `服装名：${formName}\n标签：${formTags}` : `标签：${formTags}`
        return ScriptProcessingService.analyzeCostumeInfoAsyncApiV1ScriptProcessingAnalyzeCostumeInfoAsyncPost({
          requestBody: {
            relation_entity_id: smartDetectRelationEntityId,
            costume_description: description,
            costume_context: (costume_context || '').trim() || null,
            quote_token: smartDetectQuote.quoteToken,
          },
        })
      }

      await executeAsyncTaskCreate({
        request,
        trackTaskData: trackSmartDetectTaskData,
        startedMessage: taskCopy.startedMessage,
        reusedMessage: taskCopy.reusedMessage,
        fallbackErrorMessage: '智能检测失败',
        getErrorMessage: (error, fallbackMessage) => {
          // 积分相关错误（积分不足/报价已变更）优先识别并触发刷新，返回语义文案。
          const pointsAware = makePointsAwareGetErrorMessage(smartDetectQuote.refresh)
          const pointsMessage = pointsAware(error, fallbackMessage)
          if (pointsMessage !== fallbackMessage) {
            return pointsMessage
          }
          const maybeAny = error as { response?: { status?: number }; status?: number }
          const status = maybeAny?.response?.status ?? maybeAny?.status
          if (status === 404) {
            return '接口未找到：请运行 `pnpm run openapi:update` 生成客户端代码后重试'
          }
          return defaultTaskActionErrorMessage(error, fallbackMessage)
        },
      })
    } catch {
      // executeAsyncTaskCreate 已统一处理错误提示
    } finally {
      setSmartDetectLoading(false)
    }
  }

  const handleCancelSmartDetectTask = async () => {
    if (!smartDetectTask?.taskId) return
    try {
      await executeTaskCancel({
        taskId: smartDetectTask.taskId,
        reason: `用户在${assetDisplayName}资产编辑页取消智能检测任务`,
        applyCancelData: applySmartDetectCancelData,
        cancelledImmediatelyMessage: taskCopy.cancelledImmediatelyMessage,
        cancelRequestedMessage: taskCopy.cancelRequestedMessage,
        fallbackErrorMessage: '取消智能检测任务失败',
      })
    } catch {
      // executeTaskCancel 已统一处理错误提示
    }
  }

  useRelationTaskNotification({
    task: smartDetectTask,
    settledTask: smartDetectSettledTask,
    title: taskCopy.title,
    sourceLabel: formName?.trim() ? `${assetDisplayName}：${formName.trim()}` : `${assetDisplayName}编辑页`,
    runningDescription: taskCopy.runningDescription,
    cancellingDescription: taskCopy.cancellingDescription,
    successDescription: taskCopy.successDescription,
    cancelledDescription: taskCopy.cancelledDescription,
    failedDescription: taskCopy.failedDescription,
    onCancel: smartDetectTask ? () => void handleCancelSmartDetectTask() : null,
    onNavigate: () => onNavigate(location.pathname),
  })
  useRelationTaskNotification({
    task: generationTask,
    settledTask: generationSettledTask,
    title: TASK_COPY.imageGeneration.title,
    sourceLabel: formName?.trim() ? `${assetDisplayName}：${formName.trim()}` : `${assetDisplayName}编辑页`,
    runningDescription: TASK_COPY.imageGeneration.runningDescription,
    cancellingDescription: TASK_COPY.imageGeneration.cancellingDescription,
    successDescription: TASK_COPY.imageGeneration.successDescription,
    cancelledDescription: TASK_COPY.imageGeneration.cancelledDescription,
    failedDescription: TASK_COPY.imageGeneration.failedDescription,
    onCancel:
      generationTask?.taskId
        ? () =>
            void executeTaskCancel({
              taskId: generationTask.taskId,
              reason: `用户在${assetDisplayName}资产编辑页取消图片生成任务`,
              applyCancelData: (data) => {
                setGenerationTask((current) =>
                  current
                    ? {
                        ...current,
                        taskId: data?.task_id || current.taskId,
                        status: (data?.status ?? current.status) as TaskStatus,
                        cancelRequested: data?.cancel_requested ?? true,
                      }
                    : current,
                )
                return null
              },
              cancelledImmediatelyMessage: TASK_COPY.imageGeneration.cancelledImmediatelyMessage,
              cancelRequestedMessage: TASK_COPY.imageGeneration.cancelRequestedMessage,
              fallbackErrorMessage: '取消图片生成任务失败',
            })
        : null,
    onNavigate: () => onNavigate(location.pathname),
  })

  // Saves current form edits, fetches the rendered prompt+reference preview, and opens the
  // confirmation modal so users see exactly what will be sent before a billed generation starts.
  const openGenerateConfirm = async (image: TImage) => {
    if (!assetId || !asset) return
    const prompt = formDesc.trim()
    if (!prompt) {
      message.warning('请先填写描述')
      return
    }
    const payload = buildBasePayload()
    if (!payload) return

    setGeneratingByImageId((prev) => ({ ...prev, [image.id]: true }))
    setSavingBase(true)
    try {
      const nextAsset = await updateAsset(assetId, payload)
      if (nextAsset) setAsset(nextAsset)

      const rendered = await renderPromptPreview(assetId, image.id, {
        prompt,
        images: referenceFileIds,
      })
      setGenerateConfirmPrompt(rendered?.prompt ?? prompt)
      setGenerateConfirmImages(rendered?.images ?? referenceFileIds)
      setPendingGenerateImage(image)
      setGenerateConfirmOpen(true)
    } catch {
      message.error('生成预览失败')
    } finally {
      setSavingBase(false)
      setGeneratingByImageId((prev) => ({ ...prev, [image.id]: false }))
    }
  }

  // Runs the actual billed generation using the previewed prompt/images once the user confirms.
  const confirmGenerateImage = async () => {
    if (!assetId || !pendingGenerateImage) return
    const image = pendingGenerateImage
    setGenerateConfirmLoading(true)
    setGeneratingByImageId((prev) => ({ ...prev, [image.id]: true }))
    try {
      const taskId = await createGenerationTask(assetId, image.id, {
        prompt: generateConfirmPrompt,
        images: generateConfirmImages,
        model_id: selectedImageModelId,
        quote_token: imageQuote.quoteToken,
        resolution_profile: assetImageResolutionProfile,
      })
      if (!taskId) {
        message.error('生成任务创建失败：缺少任务 ID')
        return
      }
      setGenerateConfirmOpen(false)
      setPendingGenerateImage(null)
      setGenerationTask({
        taskId,
        status: 'pending',
        progress: 0,
        cancelRequested: false,
      })
      setGenerationSettledTask(null)

      let finalStatus: TaskStatus = 'pending'
      let finalTaskState: RelationTaskState | null = null
      for (let i = 0; i < 30; i += 1) {
        await sleep(2000)
        const statusRes = await FilmService.getTaskStatusApiV1FilmTasksTaskIdStatusGet({ taskId })
        const status = statusRes.data?.status
        if (!status) continue
        finalStatus = status
        if (statusRes.data) {
          finalTaskState = toRelationTaskStateFromStatusRead(statusRes.data)
          setGenerationTask(finalTaskState)
        }
        if (isTerminalStatus(status)) break
      }
      if (finalTaskState && isTerminalStatus(finalTaskState.status)) {
        setGenerationTask(null)
        setGenerationSettledTask(finalTaskState)
      }

      if (finalStatus === 'succeeded') {
        await loadData()
      } else if (finalStatus !== 'failed' && finalStatus !== 'cancelled') {
        message.warning('生成任务仍在执行，请稍后刷新')
      }
    } catch (error) {
      if (isAssetNameConflictError(error)) {
        message.error(`${assetDisplayName}名称已存在，请修改名称或编辑已有资产后再生成`)
      } else {
        // 优先识别积分业务错误（积分不足/报价已变更），命中后刷新报价并返回语义文案。
        const pointsAware = makePointsAwareGetErrorMessage(imageQuote.refresh)
        const msg = pointsAware(error, '发起生成失败')
        message.error(msg)
      }
    } finally {
      setGenerateConfirmLoading(false)
      setGeneratingByImageId((prev) => ({ ...prev, [image.id]: false }))
    }
  }

  const openHistoryModal = async (targetImage: TImage) => {
    if (!assetId) return
    setEditingSlotImage(targetImage)
    setHistoryOpen(true)
    setHistoryLoading(true)

    try {
      const candidates = await listImageCandidates(assetId, targetImage.id)
      setHistoryCandidates(candidates)
    } catch {
      message.error('加载候选图片失败')
      setHistoryCandidates([])
    } finally {
      setHistoryLoading(false)
    }
  }

  const handleAdoptHistoryImage = async (candidate: AssetImageCandidateRead) => {
    if (!assetId || !editingSlotImage || !candidate.file_id) return

    setAdoptingImageId(candidate.id)
    try {
      await adoptImageCandidate(assetId, editingSlotImage.id, candidate.id)
      message.success('角度图片已更新')
      setHistoryOpen(false)
      setEditingSlotImage(null)
      await loadData()
    } catch {
      message.error('更新角度图片失败')
    } finally {
      setAdoptingImageId(null)
    }
  }

  const handleDeleteCandidate = async (candidate: AssetImageCandidateRead) => {
    if (!assetId || !editingSlotImage) return

    setDeletingCandidateId(candidate.id)
    try {
      await deleteImageCandidate(assetId, editingSlotImage.id, candidate.id)
      message.success('候选图片已移除')
      const candidates = await listImageCandidates(assetId, editingSlotImage.id)
      setHistoryCandidates(candidates)
    } catch {
      message.error('移除候选图片失败')
    } finally {
      setDeletingCandidateId(null)
    }
  }

  const handleCandidateUpload = async (files: File[]) => {
    if (!assetId || !editingSlotImage || files.length === 0 || !attachImageCandidates) return
    setUploadingCandidates(true)
    try {
      const fileIds: string[] = []
      for (const file of files) {
        const res = await StudioFilesService.uploadFileApiApiV1StudioFilesUploadPost({
          formData: { file } as any,
          name: file.name,
        })
        const fileId = res.data?.id
        if (fileId) fileIds.push(String(fileId))
      }
      if (fileIds.length > 0) {
        await attachImageCandidates(assetId, editingSlotImage.id, fileIds)
        const candidates = await listImageCandidates(assetId, editingSlotImage.id)
        setHistoryCandidates(candidates)
        message.success(`已上传 ${fileIds.length} 张图片到候选池`)
      }
    } catch {
      message.error('上传候选图片失败')
    } finally {
      setUploadingCandidates(false)
    }
  }

  // 打开资产库抽屉以"新增"一张参考图。
  const openReferencePickerToAdd = useCallback(() => {
    setReferencePickerInitialKind('scene')
    setReferenceReplaceFileId(null)
    setReferencePickerOpen(true)
  }, [])

  // 打开资产库抽屉以"替换"已选参考图列表里的某一项；按 fileId 反查其所属资产类型作为默认 tab。
  const openReferencePickerToReplace = useCallback(
    (fileId: string) => {
      const existing = referenceOptions.find((option) => option.file_id === fileId)
      setReferencePickerInitialKind(existing?.kind ?? 'scene')
      setReferenceReplaceFileId(fileId)
      setReferencePickerOpen(true)
    },
    [referenceOptions],
  )

  /**
   * 资产库选图确认回调：只把选中的资产图片临时加入本次生成的参考图候选，
   * 不写入任何资产关联关系——与镜头详情页关键帧生成的"临时参考图"语义一致。
   */
  const handleReferencePicked = useCallback(
    (option: AssetReferenceOption) => {
      setReferenceOptions((prev) => {
        const withoutDuplicate = prev.filter((item) => item.file_id !== option.file_id)
        return [...withoutDuplicate, option]
      })
      if (referenceReplaceFileId) {
        setReferenceFileIds((prev) => prev.map((id) => (id === referenceReplaceFileId ? option.file_id : id)))
      } else {
        setReferenceFileIds((prev) => (prev.includes(option.file_id) ? prev : [...prev, option.file_id]))
      }
      setReferencePickerOpen(false)
    },
    [referenceReplaceFileId],
  )

  if (!assetId) {
    return (
      <Card>
        <Empty description={missingAssetIdText} />
      </Card>
    )
  }

  return (
    <div className="space-y-4 h-full overflow-auto">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Space>
            <Button icon={<ArrowLeftOutlined />} onClick={() => onNavigate(backTo)}>
              返回{assetDisplayName}资产
            </Button>
            <Typography.Title level={5} style={{ margin: 0 }}>
              {assetDisplayName}资产编辑
            </Typography.Title>
            {asset?.id ? <Tag>{asset.id}</Tag> : null}
          </Space>
          <Button icon={<ReloadOutlined />} onClick={() => void loadData()} loading={loading}>
            刷新
          </Button>
        </div>
      </Card>

      <Collapse
        defaultActiveKey={['base', 'views']}
        items={[
          {
            key: 'base',
            label: '基础信息展示',
            children: loading ? (
              <div className="py-8 text-center">
                <Spin />
              </div>
            ) : (
              <div className="space-y-3">
                <div>
                  <div className="text-gray-600 text-sm mb-1">名称</div>
                  <Input value={formName} onChange={(e) => setFormName(e.target.value)} disabled={smartDetectBusy || savingBase} />
                </div>
                <div>
                    <div className="flex items-center gap-2 mb-1">
                      <div className="text-gray-600 text-sm">描述</div>
                      {relationType === 'actor_image' ||
                      relationType === 'character_image' ||
                      relationType === 'scene_image' ||
                      relationType === 'prop_image' ||
                      relationType === 'costume_image' ? (
                        <>
                          <PointsCostButton
                            type="primary"
                            size="small"
                            loading={smartDetectLoading}
                            disabled={Boolean(loading) || !!smartDetectTask}
                            quote={smartDetectQuote.quote}
                            quoteLoading={smartDetectQuote.loading}
                            quoteError={smartDetectQuote.error}
                            onClick={() => void handleSmartDetectMissing()}
                          >
                            {smartDetectTask ? '检测中' : '智能检测'}
                          </PointsCostButton>
                          {smartDetectTask ? (
                            <Button
                              size="small"
                              danger
                              icon={<CloseCircleOutlined />}
                              disabled={smartDetectTask.cancelRequested}
                              onClick={() => void handleCancelSmartDetectTask()}
                            >
                              {smartDetectTask.cancelRequested ? '正在取消' : '取消检测'}
                            </Button>
                          ) : null}
                        </>
                      ) : null}
                    </div>
                  <Input.TextArea
                    value={formDesc}
                    onChange={(e) => setFormDesc(e.target.value)}
                    disabled={smartDetectBusy || savingBase}
                    placeholder="请输入描述"
                    rows={4}
                  />
                </div>
                <div>
                  <div className="text-gray-600 text-sm mb-2">模型选择</div>
                  {imageModelsLoading ? (
                    <div className="h-28 flex items-center justify-center rounded border border-dashed border-gray-200 bg-gray-50">
                      <Spin size="small" />
                    </div>
                  ) : imageModels.length === 0 ? (
                    <div className="h-28 flex items-center justify-center rounded border border-dashed border-gray-200 bg-gray-50 text-sm text-gray-400">
                      暂无可用图片模型
                    </div>
                  ) : (
                    <div className="space-y-1">
                      {imageModels.map((model) => {
                        const selected = model.id === selectedImageModelId
                        return (
                          <div
                            key={model.id}
                            role="button"
                            tabIndex={0}
                            className={[
                              'flex cursor-pointer items-start gap-2 rounded px-3 py-2 transition-colors select-none',
                              selected ? 'bg-blue-50 ring-1 ring-blue-400' : 'hover:bg-gray-50',
                              (savingBase || smartDetectBusy) ? 'pointer-events-none opacity-50' : '',
                            ].join(' ')}
                            onClick={() => setSelectedImageModelId(model.id)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault()
                                setSelectedImageModelId(model.id)
                              }
                            }}
                          >
                            <div className="flex-1 min-w-0">
                              <div className="truncate text-sm font-medium text-gray-800">{model.name}</div>
                              <div className="mt-0.5 flex items-center gap-1.5">
                                <Tag className="m-0 flex-shrink-0 px-1 py-0 text-[10px] leading-4">{model.provider_name}</Tag>
                                {model.description ? (
                                  <span className="truncate text-xs text-gray-500">{model.description}</span>
                                ) : null}
                              </div>
                            </div>
                            {selected ? <CheckOutlined className="mt-0.5 flex-shrink-0 text-blue-500" /> : null}
                          </div>
                        )
                      })}
                    </div>
                  )}
                  <div className="mt-3">
                    <div className="text-gray-600 text-sm mb-1">分辨率</div>
                    <Select
                      size="small"
                      value={assetImageResolutionProfile}
                      options={ASSET_IMAGE_RESOLUTION_OPTIONS}
                      onChange={(value) => setAssetImageResolutionProfile(value)}
                      disabled={savingBase || smartDetectBusy || imageModelsLoading || imageModels.length === 0}
                    />
                  </div>
                </div>
              </div>
            ),
          },
          {
            key: 'views',
            label: '图片',
            children: (
              <Row gutter={[16, 16]}>
                {slotItems.map((slot) => (
                  <Col xs={24} sm={12} lg={8} xl={6} key={slot.angle}>
                    <DisplayImageCard
                      title={null}
                      imageUrl={slot.imageUrl}
                      imageAlt={slot.angle}
                      placeholder="暂无图片"
                      hoverable={false}
                      imageHeightClassName="h-44"
                      footer={
                        <div className="flex flex-col gap-1">
                          <div className="flex items-center gap-2">
                            <PointsCostButton
                              type="primary"
                              size="small"
                              disabled={!slot.image}
                              loading={Boolean(slot.image && generatingByImageId[slot.image.id])}
                              quote={imageQuote.quote}
                              quoteLoading={imageQuote.loading}
                              quoteError={imageQuote.error}
                              onClick={() => slot.image && void handleGenerateImage(slot.image)}
                            >
                              生成
                            </PointsCostButton>
                            <Button
                              size="small"
                              icon={<EditOutlined />}
                              disabled={!slot.image}
                              onClick={() => slot.image && void openHistoryModal(slot.image)}
                            >
                              候选池
                            </Button>
                          </div>
                        </div>
                      }
                    />
                  </Col>
                ))}
              </Row>
            ),
          },
        ]}
      />

      <Modal
        title={
          <div className="flex items-center justify-between pr-8">
            <span>图片候选池</span>
            {attachImageCandidates && (
              <Upload
                accept="image/*"
                multiple
                showUploadList={false}
                disabled={uploadingCandidates}
                beforeUpload={(file, fileList) => {
                  const isLast = file.uid === fileList[fileList.length - 1]?.uid
                  if (isLast) void handleCandidateUpload(fileList)
                  return Upload.LIST_IGNORE
                }}
              >
                <Button size="small" icon={<UploadOutlined />} loading={uploadingCandidates}>
                  本地上传
                </Button>
              </Upload>
            )}
          </div>
        }
        open={historyOpen}
        onCancel={() => {
          setHistoryOpen(false)
          setEditingSlotImage(null)
        }}
        footer={null}
        width={960}
      >
        {historyLoading ? (
          <div className="py-8 text-center">
            <Spin />
          </div>
        ) : historyCandidates.length === 0 ? (
          <Empty description="暂无候选图片。生成图片后，所有结果会保留在这里供选择。" />
        ) : (
          <AssetImageCandidateGallery
            candidates={historyCandidates}
            adoptingId={adoptingImageId}
            deletingId={deletingCandidateId}
            resolveFileUrl={(fileId) => buildFileDownloadUrl(fileId) ?? ''}
            onAdopt={handleAdoptHistoryImage}
            onDelete={handleDeleteCandidate}
          />
        )}
      </Modal>

      <Modal
        title="智能检测：缺失信息"
        open={smartDetectOpen}
        onCancel={() => setSmartDetectOpen(false)}
        footer={null}
        destroyOnClose
        width={880}
      >
        {smartDetectLoading ? (
          <div className="py-8 text-center">
            <Spin />
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-2">
              {smartDetectIssues.length === 0 ? (
                <div className="text-sm text-gray-600">未发现缺失信息。</div>
              ) : (
                <div className="text-sm text-gray-600">发现 {smartDetectIssues.length} 项可能缺失信息（建议参考下面优化后的描述）：</div>
              )}
              {smartDetectIssues.length > 0 ? (
                <div className="space-y-2">
                  {smartDetectIssues.map((it, idx) => (
                    <div key={`${idx}_${it}`} className="text-sm text-gray-800">
                      {idx + 1}. {it}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>

            <div>
              <div className="text-xs text-gray-500 mb-2">优化后的描述（可直接填入）</div>
              <Input.TextArea rows={6} value={smartDetectOptimizedDesc} readOnly />
            </div>

            <div className="flex justify-end gap-2">
              <Button
                onClick={() => {
                  const next = smartDetectOptimizedDesc.trim()
                  if (!next) {
                    message.warning('未返回有效的优化描述')
                    return
                  }
                  setFormDesc(next)
                  setSmartDetectOpen(false)
                  message.success('已填入描述')
                }}
                disabled={!smartDetectOptimizedDesc.trim()}
              >
                填入描述
              </Button>
              <Button onClick={() => setSmartDetectOpen(false)}>关闭</Button>
            </div>
          </div>
        )}
      </Modal>

      <AssetReferencePickerDrawer
        open={referencePickerOpen}
        initialKind={referencePickerInitialKind}
        onSelect={handleReferencePicked}
        onClose={() => setReferencePickerOpen(false)}
      />
    </div>
  )
}
