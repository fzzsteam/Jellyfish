import { Alert, Drawer, Empty, List, Spin, Tag, Typography } from 'antd'
import type { ShotVideoReadinessCheck, ShotVideoReadinessRead } from '../../../../services/generated'

type VideoDiagnosticsDrawerBatchItem = {
  title: string
  readiness: ShotVideoReadinessRead | null
  error?: string
}

type VideoDiagnosticsDrawerProps = {
  open: boolean
  loading: boolean
  readiness: ShotVideoReadinessRead | null
  title?: string
  batchItems?: VideoDiagnosticsDrawerBatchItem[]
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
  title = '视频生成诊断',
  batchItems,
  onClose,
}: VideoDiagnosticsDrawerProps) {
  const isBatchMode = Array.isArray(batchItems)
  const checks = readiness?.checks ?? []

  return (
    <Drawer
      title={title}
      width={480}
      open={open}
      onClose={onClose}
      destroyOnClose
    >
      {loading ? (
        <div className="py-10 text-center">
          <Spin />
        </div>
      ) : isBatchMode ? (
        <BatchDiagnosticsList items={batchItems ?? []} />
      ) : !readiness || checks.length === 0 ? (
        <Empty description="暂无诊断结果" />
      ) : (
        <ReadinessDetail readiness={readiness} />
      )}
    </Drawer>
  )
}

/**
 * 渲染单镜头诊断详情，保持现有单镜头查看方式不变。
 */
function ReadinessDetail({ readiness }: { readiness: ShotVideoReadinessRead }) {
  return (
    <div className="space-y-4">
      <ReadinessSummary readiness={readiness} />
      <CheckList checks={readiness.checks ?? []} />
    </div>
  )
}

/**
 * 渲染批量诊断列表，让分镜列表页只在用户主动打开时展示低频诊断信息。
 */
function BatchDiagnosticsList({ items }: { items: VideoDiagnosticsDrawerBatchItem[] }) {
  if (items.length === 0) {
    return <Empty description="暂无诊断结果" />
  }

  return (
    <List
      dataSource={items}
      split
      renderItem={(item) => {
        const failedChecks = (item.readiness?.checks ?? []).filter((check) => !check.ok)
        const displayChecks = failedChecks.length > 0 ? failedChecks : item.readiness?.checks ?? []

        return (
          <List.Item>
            <div className="w-full space-y-3">
              <div className="flex items-center justify-between gap-3">
                <Typography.Text strong ellipsis={{ tooltip: item.title }}>
                  {item.title}
                </Typography.Text>
                <ReadinessStatusTag readiness={item.readiness} error={item.error} />
              </div>
              {item.error ? <Alert type="warning" showIcon message={item.error} /> : null}
              {item.readiness ? <CheckList checks={displayChecks} emptyDescription="暂无检查项" /> : null}
            </div>
          </List.Item>
        )
      }}
    />
  )
}

/**
 * 统一渲染准备度状态，避免单镜头与批量模式出现不同文案口径。
 */
function ReadinessSummary({ readiness }: { readiness: ShotVideoReadinessRead }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <Typography.Text strong>{readiness.ready ? '当前镜头可生成视频' : '当前镜头暂不可生成视频'}</Typography.Text>
      <ReadinessStatusTag readiness={readiness} />
    </div>
  )
}

/**
 * 统一渲染诊断检查项，失败项会在批量模式下优先展示。
 */
function CheckList({
  checks,
  emptyDescription = '暂无诊断结果',
}: {
  checks: ShotVideoReadinessCheck[]
  emptyDescription?: string
}) {
  if (checks.length === 0) {
    return <Empty description={emptyDescription} />
  }

  return (
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
  )
}

/**
 * 根据诊断结果输出统一状态标签，优先暴露失败与待补齐状态。
 */
function ReadinessStatusTag({
  readiness,
  error,
}: {
  readiness: ShotVideoReadinessRead | null
  error?: string
}) {
  if (error) {
    return <Tag color="red">失败</Tag>
  }

  if (!readiness) {
    return <Tag>暂无结果</Tag>
  }

  return <Tag color={readiness.ready ? 'green' : 'gold'}>{readiness.ready ? '可生成' : '待补齐'}</Tag>
}
