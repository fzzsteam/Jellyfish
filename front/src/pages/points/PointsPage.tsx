import { useEffect, useState } from 'react'
import type React from 'react'
import { Card, Select, Table, Tag, message } from 'antd'
import type { TableColumnsType } from 'antd'
import { PointsService } from '../../services/generated'
import type {
  PointTransactionRead,
  PointTransactionType,
  PointsSummaryRead,
} from '../../services/generated'
import { PointsAccountCard } from '../../components/points/PointsAccountCard'
import { PointsBadge } from '../../components/points/PointsBadge'

/** 积分流水类型 → 标签颜色与中文标签，便于一眼区分充值/冻结/扣减/解冻。 */
const TX_TYPE_COLOR: Record<PointTransactionType, string> = {
  recharge: 'green',
  freeze: 'orange',
  consume: 'red',
  unfreeze: 'blue',
}

const TX_TYPE_LABEL: Record<PointTransactionType, string> = {
  recharge: '充值',
  freeze: '冻结',
  consume: '扣减',
  unfreeze: '解冻',
}

/** 流水类型筛选项。 */
const TYPE_FILTER_OPTIONS: { label: string; value: PointTransactionType }[] = [
  { label: '充值', value: 'recharge' },
  { label: '冻结', value: 'freeze' },
  { label: '扣减', value: 'consume' },
  { label: '解冻', value: 'unfreeze' },
]

/**
 * 流水时间格式化：沿用项目内 Intl.DateTimeFormat 的既定约定
 * （见 taskNotificationHelpers.tsx），避免引入 dayjs 依赖。
 */
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

/**
 * 用户积分页：展示当前用户积分账户摘要与积分流水。
 * 流水支持按类型筛选 + 服务端分页。数据通过 generated PointsService 拉取。
 */
const PointsPage: React.FC = () => {
  const [summary, setSummary] = useState<PointsSummaryRead | null>(null)
  const [transactions, setTransactions] = useState<PointTransactionRead[]>([])
  const [loading, setLoading] = useState(false)
  const [txLoading, setTxLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [total, setTotal] = useState(0)
  const [typeFilter, setTypeFilter] = useState<PointTransactionType | undefined>(undefined)

  /** 加载积分摘要。 */
  const loadSummary = async () => {
    setLoading(true)
    try {
      const res = await PointsService.getMyPointsApiV1PointsMeGet({})
      setSummary(res.data ?? null)
    } catch {
      message.error('积分摘要加载失败')
    } finally {
      setLoading(false)
    }
  }

  /** 加载积分流水，按页 + 类型筛选拉取。 */
  const loadTransactions = async (p: number, ps: number, type?: PointTransactionType) => {
    setTxLoading(true)
    try {
      const res = await PointsService.listMyTransactionsApiV1PointsTransactionsGet({
        page: p,
        pageSize: ps,
        type,
      })
      setTransactions(res.data?.items ?? [])
      setTotal(res.data?.pagination?.total ?? 0)
    } catch {
      message.error('流水加载失败')
    } finally {
      setTxLoading(false)
    }
  }

  useEffect(() => {
    void loadSummary()
    void loadTransactions(1, pageSize, typeFilter)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /** 流水列定义：时间/类型/金额/业务类型/模型/余额/备注/操作人。 */
  const columns: TableColumnsType<PointTransactionRead> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v?: string | null) => formatTxTime(v),
    },
    {
      title: '类型',
      dataIndex: 'type',
      width: 90,
      render: (t: PointTransactionType) => <Tag color={TX_TYPE_COLOR[t]}>{TX_TYPE_LABEL[t]}</Tag>,
    },
    {
      title: '金额',
      dataIndex: 'amount',
      width: 100,
      render: (v: number) => <PointsBadge value={v} size="sm" insufficient={v < 0} />,
    },
    { title: '业务类型', dataIndex: 'business_type', render: (v) => v || '—' },
    { title: '模型', dataIndex: 'model_id', ellipsis: true, render: (v) => v || '—' },
    {
      title: '余额',
      dataIndex: 'balance_after',
      width: 100,
      render: (v: number) => <PointsBadge value={v} size="sm" />,
    },
    { title: '备注', dataIndex: 'remark', ellipsis: true, render: (v) => v || '—' },
    { title: '操作人', dataIndex: 'created_by_username', width: 120, render: (v) => v || '—' },
  ]

  return (
    <div className="flex flex-col gap-4 p-4">
      <Card title="积分账户">
        <PointsAccountCard summary={summary} loading={loading} />
      </Card>

      <Card
        title="积分流水"
        extra={
          <Select<PointTransactionType>
            allowClear
            placeholder="按类型筛选"
            style={{ width: 160 }}
            value={typeFilter}
            options={TYPE_FILTER_OPTIONS}
            onChange={(v) => {
              setTypeFilter(v)
              setPage(1)
              void loadTransactions(1, pageSize, v)
            }}
          />
        }
      >
        <Table<PointTransactionRead>
          rowKey="id"
          loading={txLoading}
          dataSource={transactions}
          columns={columns}
          size="small"
          scroll={{ x: 900, y: 400 }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            onChange: (p, ps) => {
              setPage(p)
              setPageSize(ps)
              void loadTransactions(p, ps, typeFilter)
            },
          }}
        />
      </Card>
    </div>
  )
}

export default PointsPage
