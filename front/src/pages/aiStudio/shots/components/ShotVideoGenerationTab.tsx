import type { ReactNode } from 'react'
import { Button, Card, Descriptions, Segmented, Select, Space, Tag, Tooltip, Typography } from 'antd'
import { SettingOutlined, ToolOutlined, VideoCameraAddOutlined } from '@ant-design/icons'
import type { ShotDetailRead, ShotFrameType, ShotPreparationStateRead, ShotRead } from '../../../../services/generated'
import { ShotKeyframeCard, type ShotKeyframeCandidate } from './ShotKeyframeCard'

/** 视频生成参考模式：决定需要哪些帧类型（首帧/尾帧/关键帧）参与生成。 */
type ReferenceMode = 'first' | 'last' | 'key' | 'first_last' | 'first_last_key' | 'text_only'

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
  videoReadinessReady: boolean | null
  videoReadinessLoading: boolean
  referenceMode: ReferenceMode
  onReferenceModeChange: (mode: ReferenceMode) => void
  keyframeCandidatesByType: Record<ShotFrameType, ShotKeyframeCandidate[]>
  keyframeCurrentFileIdByType: Record<ShotFrameType, string | null>
  keyframeApplyingFileId: string | null
  onGenerateKeyframe: (frameType: ShotFrameType) => void
  onApplyKeyframe: (frameType: ShotFrameType, fileId: string) => void
  quoteNode: ReactNode
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
  videoReadinessReady: boolean | null,
  videoReadinessLoading: boolean,
): string | null {
  if (!shot) return '未选择镜头'
  if (!(preparationState?.ready_for_generation ?? shot.status === 'ready')) return '未完成准备'
  if (!shotDetail?.duration || shotDetail.duration <= 0) return '未设置时长'
  if (!videoRatio) return '请先设置视频比例'
  if (!selectedVideoModelId) return '未选择视频模型'
  if (videoReadinessLoading) return '检查生成条件中'
  if (videoReadinessReady !== true) return '当前参考模式所需条件未就绪，请查看诊断'
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
  videoReadinessReady,
  videoReadinessLoading,
  referenceMode,
  onReferenceModeChange,
  keyframeCandidatesByType,
  keyframeCurrentFileIdByType,
  keyframeApplyingFileId,
  onGenerateKeyframe,
  onApplyKeyframe,
  quoteNode,
  onModelChange,
  onResolutionChange,
  onOpenDiagnostics,
  onOpenPromptPreview,
}: ShotVideoGenerationTabProps) {
  const disabledReason = getGenerateDisabledReason(
    shot,
    shotDetail,
    preparationState,
    selectedVideoModelId,
    videoRatio,
    videoReadinessReady,
    videoReadinessLoading,
  )
  const readyForGeneration = !disabledReason

  return (
    <div className="space-y-4">
      <Card
        title={
          <Space>
            <SettingOutlined />
            <span>生成配置</span>
          </Space>
        }
      >
        <div className="space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <Typography.Text strong>{shot ? `镜头 #${shot.index} · ${shot.title || '未命名镜头'}` : '未选择镜头'}</Typography.Text>
              <div className="mt-1 text-xs text-slate-500">
                按下方选择的参考模式检查生成条件；提示词预览确认后再提交视频生成任务。
              </div>
            </div>
            <Tag color={readyForGeneration ? 'green' : 'gold'}>
              {readyForGeneration ? '可生成' : '待补齐'}
            </Tag>
          </div>

          <Descriptions size="small" column={{ xs: 1, sm: 2, md: 3 }} bordered>
            <Descriptions.Item label="镜头时长">
              {shotDetail?.duration ? `${shotDetail.duration}s` : '未设置'}
            </Descriptions.Item>
            <Descriptions.Item label="视频比例">
              {videoRatio ?? '未设置'}
            </Descriptions.Item>
            <Descriptions.Item label="准备状态">
              {preparationState?.ready_for_generation ? '准备完成' : '待继续准备'}
            </Descriptions.Item>
          </Descriptions>

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

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1">
              <Typography.Text className="text-xs text-slate-500">视频模型</Typography.Text>
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
            </div>
            <div className="space-y-1">
              <Typography.Text className="text-xs text-slate-500">清晰度</Typography.Text>
              <Segmented
                block
                value={videoResolution}
                onChange={(value) => onResolutionChange(value as '720p' | '1080p')}
                options={[
                  { label: '720p', value: '720p' },
                  { label: '1080p', value: '1080p' },
                ]}
              />
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
            {quoteNode}
          </div>

          <Space wrap>
            <Tooltip title={disabledReason || '预览提示词并确认积分'}>
              <span>
                <Button
                  type="primary"
                  icon={<VideoCameraAddOutlined />}
                  disabled={!!disabledReason}
                  onClick={onOpenPromptPreview}
                >
                  生成视频
                </Button>
              </span>
            </Tooltip>
            <Button icon={<ToolOutlined />} onClick={onOpenDiagnostics}>
              诊断
            </Button>
          </Space>
        </div>
      </Card>
    </div>
  )
}
