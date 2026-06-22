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
  Space,
  Spin,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd'
import { ArrowLeftOutlined, CheckOutlined, CloseCircleOutlined, EditOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons'
import { FilmService, LlmService, ScriptProcessingService, StudioEntitiesService, StudioFilesService } from '../../../../services/generated'
import type { AssetImageCandidateRead, ModelRead, ProviderRead, TaskStatus } from '../../../../services/generated'
import { buildFileDownloadUrl } from '../utils'
import { AssetImageCandidateGallery } from './AssetImageCandidateGallery'
import { MentionEditor } from './MentionEditor'
import type { MentionAssetKind, MentionImageOption } from './MentionEditor'
import { DisplayImageCard } from './DisplayImageCard'
import { defaultTaskActionErrorMessage, executeAsyncTaskCreate, executeTaskCancel, notifyExistingTask } from '../../components/taskActionHelpers'
import { handleTaskResultSafely } from '../../components/taskResultHelpers'
import { useRelationTaskNotification } from '../../components/taskNotificationHelpers'
import { useTaskPageContext } from '../../components/taskPageContext'
import { TASK_COPY } from '../../components/taskCopy'
import { usePointsQuote } from '../../../../hooks/usePointsQuote'
import { PointsCostHint } from '../../../../components/points/PointsCostHint'
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
const ASSET_MENTION_PAGE_SIZE = 100
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
  visual_style: '现实' | '动漫'
  style?: string
}

const DEFAULT_ANGLES: AssetViewAngle[] = ['FRONT', 'LEFT', 'RIGHT', 'BACK']

export type BaseAsset = {
  id: string
  name: string
  description?: string
  tags?: string[]
  view_count?: number
  visual_style?: '现实' | '动漫'
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
}

type ImageModelOption = ModelRead & {
  provider_name: string
}

type MentionEntityRecord = {
  id?: string
  name?: string | null
  title?: string | null
}

type MentionImageRecord = {
  id?: number | string
  file_id?: string | null
  view_angle?: string | null
  name?: string | null
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
async function listMentionEntities(entityType: MentionAssetKind): Promise<MentionEntityRecord[]> {
  const result: MentionEntityRecord[] = []
  let page = 1
  let maxPage = 1
  do {
    const res = await StudioEntitiesService.listEntitiesApiV1StudioEntitiesEntityTypeGet({
      entityType,
      page,
      pageSize: ASSET_MENTION_PAGE_SIZE,
    })
    const data = res.data
    result.push(...((data?.items ?? []) as MentionEntityRecord[]))
    maxPage = data?.pagination?.max_page ?? page
    page += 1
  } while (page <= maxPage)
  return result
}

// Loads every image page for one asset entity, keeping only records that have file_id.
async function listMentionEntityImages(entityType: MentionAssetKind, entityId: string): Promise<MentionImageRecord[]> {
  const result: MentionImageRecord[] = []
  let page = 1
  let maxPage = 1
  do {
    const res = await StudioEntitiesService.listEntityImagesApiV1StudioEntitiesEntityTypeEntityIdImagesGet({
      entityType,
      entityId,
      page,
      pageSize: ASSET_MENTION_PAGE_SIZE,
    })
    const data = res.data
    result.push(...((data?.items ?? []) as MentionImageRecord[]).filter((item) => Boolean(item.file_id)))
    maxPage = data?.pagination?.max_page ?? page
    page += 1
  } while (page <= maxPage)
  return result
}

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
  const [deletingCandidateId, setDeletingCandidateId] = useState<number | null>(null)
  const [uploadingCandidates, setUploadingCandidates] = useState(false)
  const [mentionedFileIds, setMentionedFileIds] = useState<string[]>([])

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
      visual_style: (asset?.visual_style ?? '现实') as '现实' | '动漫',
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

  // Saves current form edits and starts generation directly from the description field.
  const handleGenerateImage = async (image: TImage) => {
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

      const taskId = await createGenerationTask(assetId, image.id, {
        prompt,
        images: mentionedFileIds,
        model_id: selectedImageModelId,
      })
      if (!taskId) {
        message.error('生成任务创建失败：缺少任务 ID')
        return
      }
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
        message.error('发起生成失败')
      }
    } finally {
      setSavingBase(false)
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

  // Loads all reusable asset images for the selected @ mention category and deduplicates by file_id.
  const loadMentionImagesByKind = useCallback(async (kind: MentionAssetKind): Promise<MentionImageOption[]> => {
    const entities = await listMentionEntities(kind)
    const seen = new Set<string>()
    const options: MentionImageOption[] = []
    for (const entity of entities) {
      if (!entity.id) continue
      const entityName = entity.name || entity.title || entity.id
      const entityImages = await listMentionEntityImages(kind, entity.id)
      entityImages.forEach((image, index) => {
        if (!image.file_id || seen.has(image.file_id)) return
        seen.add(image.file_id)
        options.push({
          id: `${kind}:${entity.id}:${image.id ?? index}`,
          file_id: image.file_id,
          label: entityName,
          subtitle: image.view_angle || image.name || entityName,
        })
      })
    }
    return options
  }, [])

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
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <div className="text-gray-600 text-sm">描述</div>
                      {relationType === 'actor_image' ||
                      relationType === 'character_image' ||
                      relationType === 'scene_image' ||
                      relationType === 'prop_image' ||
                      relationType === 'costume_image' ? (
                        <>
                          <Button
                            type="primary"
                            size="small"
                            onClick={() => void handleSmartDetectMissing()}
                            loading={smartDetectLoading}
                            disabled={Boolean(loading) || !!smartDetectTask || !smartDetectQuote.canSubmit}
                          >
                            {smartDetectTask ? '检测中' : '智能检测'}
                          </Button>
                          <PointsCostHint quote={smartDetectQuote.quote} loading={smartDetectQuote.loading} error={smartDetectQuote.error} />
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
                  <MentionEditor
                    value={formDesc}
                    onChange={(text, fileIds) => {
                      setFormDesc(text)
                      setMentionedFileIds(fileIds)
                    }}
                    disabled={smartDetectBusy || savingBase}
                    placeholder="支持输入 @ 选择候选池图片作为参考"
                    loadImagesByKind={loadMentionImagesByKind}
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
                        <div className="flex items-center gap-2">
                          <Button
                            type="primary"
                            size="small"
                            disabled={!slot.image}
                            loading={Boolean(slot.image && generatingByImageId[slot.image.id])}
                            onClick={() => slot.image && void handleGenerateImage(slot.image)}
                          >
                            生成
                          </Button>
                          <Button
                            size="small"
                            icon={<EditOutlined />}
                            disabled={!slot.image}
                            onClick={() => slot.image && void openHistoryModal(slot.image)}
                          >
                            候选池
                          </Button>
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
    </div>
  )
}
