import { Button, Card, Segmented, Select, Tag, Tooltip, Typography } from 'antd'
import { QuestionCircleOutlined, ToolOutlined, VideoCameraAddOutlined } from '@ant-design/icons'
import type { PointsQuoteResponse, ShotDetailRead, ShotFrameType, ShotPreparationStateRead, ShotRead } from '../../../../services/generated'
import { PointsCostButton } from '../../../../components/points/PointsCostButton'
import { ShotKeyframeCard, type ShotKeyframeCandidate } from './ShotKeyframeCard'

/** 视频生成参考模式：决定需要哪些帧类型（首帧/尾帧/关键帧）参与生成。 */
type ReferenceMode = 'first' | 'last' | 'key' | 'first_last' | 'first_last_key' | 'text_only'
type ReferenceModeSelection = ReferenceMode | null

const REFERENCE_MODE_OPTIONS: Array<{ value: ReferenceMode; label: string }> = [
  { value: 'text_only', label: '纯文字（不用参考帧）' },
  { value: 'first', label: '首帧参考' },
  { value: 'last', label: '尾帧参考' },
  { value: 'key', label: '关键帧参考' },
  { value: 'first_last', label: '首尾帧' },
  { value: 'first_last_key', label: '首尾 + 关键帧' },
]

const REQUIRED_FRAME_TYPES_BY_MODE: Record<ReferenceMode, ShotFrameType[]> = {
  text_only: [],
  first: ['first'],
  last: ['last'],
  key: ['key'],
  first_last: ['first', 'last'],
  first_last_key: ['first', 'last', 'key'],
}

type ShotVideoGenerationTabProps = {
  shot: ShotRead | null
  shotDetail: ShotDetailRead | null
  preparationState: ShotPreparationStateRead | null
  videoModels: Array<{ id: string; name: string; provider_name?: string | null }>
  selectedVideoModelId: string | null
  videoModelsLoading: boolean
  videoResolution: '720p' | '1080p'
  videoRatio: string | null
  videoRatioOptions: Array<{ value: string; label: string }>
  videoReadinessReady: boolean | null
  videoReadinessLoading: boolean
  referenceMode: ReferenceModeSelection
  onReferenceModeChange: (mode: ReferenceModeSelection) => void
  onVideoRatioChange: (ratio: string | null) => void
  keyframeCandidatesByType: Record<ShotFrameType, ShotKeyframeCandidate[]>
  keyframeCurrentFileIdByType: Record<ShotFrameType, string | null>
  keyframeApplyingFileId: string | null
  onGenerateKeyframe: (frameType: ShotFrameType) => void
  onApplyKeyframe: (frameType: ShotFrameType, fileId: string) => void
  videoQuote: PointsQuoteResponse | null
  videoQuoteLoading: boolean
  videoQuoteError: string | null
  onModelChange: (modelId: string) => void
  onResolutionChange: (resolution: '720p' | '1080p') => void
  onOpenDiagnostics: () => void
  onOpenPromptPreview: () => void
}

/**
 * 计算生成入口不可用的最短原因。
 * 该原因直接作为按钮 Tooltip，避免页面常驻展示完整 readiness 明细。
 */
function getGenerateDisabledReason(
  shot: ShotRead | null,
  shotDetail: ShotDetailRead | null,
  preparationState: ShotPreparationStateRead | null,
  selectedVideoModelId: string | null,
  videoRatio: string | null,
  videoReadinessLoading: boolean,
): string | null {
  if (!shot) return '未选择镜头'
  if (!(preparationState?.ready_for_generation ?? shot.status === 'ready')) return '未完成准备'
  if (!shotDetail?.duration || shotDetail.duration <= 0) return '未设置时长'
  if (!videoRatio) return '请先设置视频比例'
  if (!selectedVideoModelId) return '未选择视频模型'
  if (videoReadinessLoading) return '检查生成条件中'
  return null
}

/**
 * 展示单镜头视频生成配置。
 * 生成动作先进入提示词预览与积分确认弹窗，避免配置卡直接创建任务。
 */
export function ShotVideoGenerationTab({
  shot,
  shotDetail,
  preparationState,
  videoModels,
  selectedVideoModelId,
  videoModelsLoading,
  videoResolution,
  videoRatio,
  videoRatioOptions,
  videoReadinessReady,
  videoReadinessLoading,
  referenceMode,
  onReferenceModeChange,
  onVideoRatioChange,
  keyframeCandidatesByType,
  keyframeCurrentFileIdByType,
  keyframeApplyingFileId,
  onGenerateKeyframe,
  onApplyKeyframe,
  videoQuote,
  videoQuoteLoading,
  videoQuoteError,
  onModelChange,
  onResolutionChange,
  onOpenDiagnostics,
  onOpenPromptPreview,
}: ShotVideoGenerationTabProps) {
  const requiredFrameTypes = referenceMode ? REQUIRED_FRAME_TYPES_BY_MODE[referenceMode] : []
  const disabledReason = getGenerateDisabledReason(
    shot,
    shotDetail,
    preparationState,
    selectedVideoModelId,
    videoRatio,
    videoReadinessLoading,
  )
  const readyForGeneration = !disabledReason
  const videoReadinessLabel = videoReadinessLoading
    ? '检查中'
    : videoReadinessReady === false
      ? '有风险'
      : videoReadinessReady === true
        ? '通过'
        : '未检查'

  return (
    <Card
      className="flex h-full flex-col"
      bodyStyle={{ padding: 16, flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Typography.Text className="text-base font-semibold text-slate-900">
            {shot ? `镜头 #${shot.index} · ${shot.title || '未命名镜头'}` : '未选择镜头'}
          </Typography.Text>
          <Tag color={readyForGeneration ? 'green' : 'gold'} className="!m-0">
            {readyForGeneration ? '可生成' : '待补齐'}
          </Tag>
        </div>
        <Button size="small" icon={<ToolOutlined />} onClick={onOpenDiagnostics}>
          诊断
        </Button>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
        <span>时长 <span className="font-medium text-slate-900">{shotDetail?.duration ? `${shotDetail.duration}s` : '未设置'}</span></span>
        <span>比例 <span className="font-medium text-slate-900">{videoRatio ?? '未设置'}</span></span>
        <span>准备 <span className="font-medium text-slate-900">{preparationState?.ready_for_generation ? '完成' : '待继续'}</span></span>
        <span>诊断 <span className="font-medium text-slate-900">{videoReadinessLabel}</span></span>
      </div>

      <div className="mt-3 min-h-0 flex-1 space-y-5 overflow-y-auto pb-3 pr-1">
        <div className="grid grid-cols-1 gap-3">
          <label className="block min-w-0 space-y-1">
            <span className="text-xs font-medium text-slate-500">视频比例</span>
            <Select
              allowClear
              className="w-full"
              placeholder={videoRatio ?? '请选择视频比例'}
              value={shotDetail?.override_video_ratio ?? undefined}
              onChange={(value) => onVideoRatioChange(value ?? null)}
              options={videoRatioOptions}
            />
          </label>
          <label className="block min-w-0 space-y-1">
            <span className="text-xs font-medium text-slate-500">视频模型</span>
            <Select
              className="w-full"
              placeholder="请选择视频模型"
              loading={videoModelsLoading}
              value={selectedVideoModelId ?? undefined}
              onChange={onModelChange}
              options={videoModels.map((model) => ({
                value: model.id,
                label: model.provider_name ? `${model.name} · ${model.provider_name}` : model.name,
              }))}
            />
          </label>
          <label className="block min-w-0 space-y-1">
            <span className="text-xs font-medium text-slate-500">清晰度</span>
            <Segmented
              block
              value={videoResolution}
              onChange={(value) => onResolutionChange(value as '720p' | '1080p')}
              options={[
                { label: '720p', value: '720p' },
                { label: '1080p', value: '1080p' },
              ]}
            />
          </label>
          <label className="block min-w-0 space-y-1">
            <span className="inline-flex items-center gap-1 text-xs font-medium text-slate-500">
              参考模式
              <Tooltip title="参考模式可不选；不选时默认使用第二步已确认资产图片。">
                <QuestionCircleOutlined className="cursor-help text-slate-400" />
              </Tooltip>
            </span>
            <Select
              allowClear
              className="w-full"
              placeholder="不选择则使用已确认资产图片"
              value={referenceMode ?? undefined}
              onChange={(value) => onReferenceModeChange(value ?? null)}
              options={REFERENCE_MODE_OPTIONS}
            />
          </label>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs font-medium text-slate-500">参考帧</span>
            {requiredFrameTypes.length > 0 ? (
              <Tag className="!m-0">{`${requiredFrameTypes.length} 个帧位`}</Tag>
            ) : (
              <Tag className="!m-0">不使用参考帧</Tag>
            )}
          </div>
          {requiredFrameTypes.length > 0 ? (
            <div className="flex w-full flex-col gap-2">
                {requiredFrameTypes.map((frameType) => (
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
          ) : referenceMode === 'text_only' ? (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-sm text-slate-500">
              当前为纯文字生成，不使用首帧、尾帧、关键帧或资产参考图。
            </div>
          ) : null}
        </div>
      </div>

      <div className="sticky bottom-0 z-10 -mx-4 mt-3 flex flex-wrap items-center justify-end gap-2 border-t border-slate-100 bg-white px-4 pt-3 pb-1 shadow-[0_-8px_16px_rgba(15,23,42,0.04)]">
        <Tooltip title={disabledReason || '预览提示词并确认积分'}>
          <span>
            <PointsCostButton
              type="primary"
              icon={<VideoCameraAddOutlined />}
              disabled={!!disabledReason}
              quote={videoQuote}
              quoteLoading={videoQuoteLoading}
              quoteError={videoQuoteError}
              onClick={onOpenPromptPreview}
            >
              生成视频
            </PointsCostButton>
          </span>
        </Tooltip>
        {videoQuoteError ? (
          <Typography.Text type="danger" className="text-xs">{videoQuoteError}</Typography.Text>
        ) : null}
      </div>
    </Card>
  )
}
