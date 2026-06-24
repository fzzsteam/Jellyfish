/**
 * SimplePointTransactionTable：展示充值/调整场景的扁平积分流水列表。
 *
 * 该组件服务于单笔充值/调整详情，不承载 PointTransactionTable 的三层展开关系。
 */
import { Table, Tag, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import type { PointTransactionRead, PointTransactionType } from '../../services/generated'
import { PointsBadge } from './PointsBadge'

const TX_TYPE_LABEL: Partial<Record<PointTransactionType, string>> = {
  recharge: '充值',
  freeze: '冻结',
  consume: '扣减',
  unfreeze: '解冻',
}

const formatTxTime = (v?: string | null): string => {
  if (!v) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(v))
}

/** 复制友好的短 ID 展示，避免流水 ID 过长撑开表格。 */
const CopyableId: React.FC<{ value?: string | null }> = ({ value }) => {
  if (!value) return <span className="text-gray-400">—</span>
  const display = value.length > 10 ? `${value.slice(0, 8)}…` : value
  return (
    <Typography.Text
      copyable={{ text: value, tooltips: ['复制', '已复制'] }}
      className="!font-mono !text-xs !text-gray-500"
    >
      {display}
    </Typography.Text>
  )
}

export interface SimplePointTransactionTableProps {
  dataSource: PointTransactionRead[]
  loading?: boolean
}

/** 格式化充值/调整流水金额，正数绿色加号、负数红色减号。 */
function renderAmount(value: number, record: PointTransactionRead) {
  const sign = value >= 0 ? '+' : '−'
  const colorClass = value >= 0 ? 'text-green-500' : 'text-red-500'
  const label = TX_TYPE_LABEL[record.type] ?? '调整'
  return (
    <span className={`text-xs font-medium ${colorClass}`} title={label}>
      {sign}{Math.abs(value).toLocaleString()}
    </span>
  )
}

const columns: TableColumnsType<PointTransactionRead> = [
  {
    title: 'ID',
    dataIndex: 'id',
    width: 170,
    render: (v: string) => (
      <span className="flex items-center gap-1">
        <Tag color="cyan" className="m-0 shrink-0 !text-xs !py-0">流水</Tag>
        <CopyableId value={v} />
      </span>
    ),
  },
  {
    title: '金额',
    dataIndex: 'amount',
    width: 90,
    render: (v: number, r) => renderAmount(v, r),
  },
  {
    title: '余额',
    dataIndex: 'balance_after',
    width: 100,
    render: (v: number) => <PointsBadge value={v} size="sm" />,
  },
  {
    title: '时间',
    dataIndex: 'created_at',
    width: 165,
    render: (v?: string | null) => (
      <span className="text-xs text-gray-400">{formatTxTime(v)}</span>
    ),
  },
  {
    title: '备注',
    dataIndex: 'remark',
    ellipsis: true,
    render: (v?: string | null) => (
      <span className="text-xs text-gray-500" title={v ?? undefined}>{v || '—'}</span>
    ),
  },
  {
    title: '操作人',
    dataIndex: 'created_by_username',
    width: 120,
    render: (v?: string | null) => <span className="text-xs text-gray-500">{v || '—'}</span>,
  },
]

/** 无分页的简化流水表格，由父组件负责传入固定列表。 */
export const SimplePointTransactionTable: React.FC<SimplePointTransactionTableProps> = ({
  dataSource,
  loading,
}) => (
  <Table<PointTransactionRead>
    rowKey="id"
    loading={loading}
    dataSource={dataSource}
    columns={columns}
    size="small"
    pagination={false}
    scroll={{ x: 760 }}
  />
)
