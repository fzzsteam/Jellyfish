import { Drawer, Empty, List, Spin, Tag, Typography } from 'antd'
import type { ShotVideoReadinessRead } from '../../../../services/generated'

type VideoDiagnosticsDrawerProps = {
  open: boolean
  loading: boolean
  readiness: ShotVideoReadinessRead | null
  onClose: () => void
}

/**
 * 展示视频生成准备度诊断结果。
 * check.key 保持后端英文标识，状态与说明使用中文呈现，便于定位具体缺口。
 */
export function VideoDiagnosticsDrawer({
  open,
  loading,
  readiness,
  onClose,
}: VideoDiagnosticsDrawerProps) {
  const checks = readiness?.checks ?? []

  return (
    <Drawer
      title="视频生成诊断"
      width={480}
      open={open}
      onClose={onClose}
      destroyOnClose
    >
      {loading ? (
        <div className="py-10 text-center">
          <Spin />
        </div>
      ) : !readiness || checks.length === 0 ? (
        <Empty description="暂无诊断结果" />
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
            <Typography.Text strong>{readiness.ready ? '当前镜头可生成视频' : '当前镜头暂不可生成视频'}</Typography.Text>
            <Tag color={readiness.ready ? 'green' : 'gold'}>{readiness.ready ? '可生成' : '待补齐'}</Tag>
          </div>

          <List
            dataSource={checks}
            renderItem={(check) => (
              <List.Item>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <Typography.Text code>{check.key}</Typography.Text>
                    <Tag color={check.ok ? 'green' : 'red'}>{check.ok ? '通过' : '未通过'}</Tag>
                  </div>
                  <div className="mt-1 text-sm text-slate-600">{check.message || '无说明'}</div>
                </div>
              </List.Item>
            )}
          />
        </div>
      )}
    </Drawer>
  )
}
