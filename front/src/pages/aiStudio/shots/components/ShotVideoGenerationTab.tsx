import { Button, Card, Descriptions, Space, Tag, Tooltip, Typography } from 'antd'
import { SettingOutlined, ToolOutlined, VideoCameraAddOutlined } from '@ant-design/icons'
import type { ShotDetailRead, ShotPreparationStateRead, ShotRead } from '../../../../services/generated'

type ShotVideoGenerationTabProps = {
  shot: ShotRead | null
  shotDetail: ShotDetailRead | null
  preparationState: ShotPreparationStateRead | null
  onOpenDiagnostics: () => void
}

/**
 * 计算生成入口不可用的最短原因。
 * 该原因直接作为按钮 Tooltip，避免页面常驻展示完整 readiness 明细。
 */
function getGenerateDisabledReason(
  shot: ShotRead | null,
  shotDetail: ShotDetailRead | null,
  preparationState: ShotPreparationStateRead | null,
): string | null {
  if (!shot) return '未选择镜头'
  if (!(preparationState?.ready_for_generation ?? shot.status === 'ready')) return '未完成准备'
  if (!shotDetail?.duration || shotDetail.duration <= 0) return '未设置时长'
  return null
}

/**
 * 展示单镜头视频生成的入口框架。
 * Task 4 只承接生成流程的位置与诊断入口，真实提交逻辑会在后续任务迁移。
 */
export function ShotVideoGenerationTab({
  shot,
  shotDetail,
  preparationState,
  onOpenDiagnostics,
}: ShotVideoGenerationTabProps) {
  const disabledReason = getGenerateDisabledReason(shot, shotDetail, preparationState)
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
        extra={
          <Button size="small" icon={<ToolOutlined />} onClick={onOpenDiagnostics}>
            诊断
          </Button>
        }
      >
        <div className="space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <Typography.Text strong>{shot ? `镜头 #${shot.index} · ${shot.title || '未命名镜头'}` : '未选择镜头'}</Typography.Text>
              <div className="mt-1 text-xs text-slate-500">
                这里承接关键帧、参考图、视频参数和提交生成入口；真实生成操作将在后续任务迁移。
              </div>
            </div>
            <Tag color={readyForGeneration ? 'green' : 'gold'}>
              {readyForGeneration ? '可进入生成配置' : '待补齐'}
            </Tag>
          </div>

          <Descriptions size="small" column={{ xs: 1, sm: 2, md: 3 }} bordered>
            <Descriptions.Item label="镜头时长">
              {shotDetail?.duration ? `${shotDetail.duration}s` : '未设置'}
            </Descriptions.Item>
            <Descriptions.Item label="视频比例">
              {shotDetail?.override_video_ratio || '继承项目默认'}
            </Descriptions.Item>
            <Descriptions.Item label="准备状态">
              {preparationState?.ready_for_generation ? '准备完成' : '待继续准备'}
            </Descriptions.Item>
          </Descriptions>

          <Space>
            <Tooltip title={disabledReason || '后续任务会接入真实视频生成提交'}>
              <span>
                <Button type="primary" icon={<VideoCameraAddOutlined />} disabled={!!disabledReason}>
                  {readyForGeneration ? '进入生成配置' : '生成视频'}
                </Button>
              </span>
            </Tooltip>
            <Typography.Text type="secondary" className="text-xs">
              当前阶段不会提交生成任务。
            </Typography.Text>
          </Space>
        </div>
      </Card>
    </div>
  )
}
