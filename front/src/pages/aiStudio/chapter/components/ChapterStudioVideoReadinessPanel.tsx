import { Spin, Tag, Tooltip } from 'antd'
import { VideoCameraAddOutlined } from '@ant-design/icons'
import type { ShotRead, ShotVideoReadinessRead } from '../../../../services/generated'

type ChapterStudioVideoReadinessPanelProps = {
  selectedShot: ShotRead | null
  videoReadinessLoading: boolean
  videoReadiness: ShotVideoReadinessRead | null
}

export function ChapterStudioVideoReadinessPanel({
  selectedShot,
  videoReadinessLoading,
  videoReadiness,
}: ChapterStudioVideoReadinessPanelProps) {
  return (
    <div className="cs-group">
      <div className="cs-group-title">
        <VideoCameraAddOutlined /> 视频准备度
      </div>
      {videoReadinessLoading ? (
        <div className="py-6 text-center">
          <Spin />
        </div>
      ) : !selectedShot ? (
        <div className="text-xs text-gray-400">请先选择一个分镜。</div>
      ) : !videoReadiness ? (
        <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-500">
          暂时无法获取当前镜头的视频准备度，请稍后重试。
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-start justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <div>
              <div className="text-sm font-medium text-slate-900">
                {videoReadiness.ready ? '当前镜头已满足视频生成条件' : '当前镜头还不能直接生成视频'}
              </div>
            </div>
            <Tag color={videoReadiness.ready ? 'green' : 'gold'}>
              {videoReadiness.ready ? '可生成' : '待补齐'}
            </Tag>
          </div>

          <div className="flex flex-wrap gap-2">
            {(videoReadiness.checks ?? []).map((check) => (
              <Tooltip key={check.key} title={check.message}>
                <Tag color={check.ok ? 'green' : 'default'}>
                  {check.ok ? '通过' : '未通过'} · {check.key}
                </Tag>
              </Tooltip>
            ))}
          </div>

          {(videoReadiness.checks ?? []).some((check) => !check.ok) ? (
            <div className="space-y-1">
              {(videoReadiness.checks ?? []).filter((check) => !check.ok).map((check) => (
                <div key={check.key} className="text-xs text-gray-600">
                  • {check.message}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
