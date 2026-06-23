import { useEffect, useState } from 'react'
import type React from 'react'
import { Card, Radio, Select, Space, message } from 'antd'
import { PointsService } from '../../services/generated'
import type {
  OperationGroupRead,
  PointTransactionRead,
  PointTransactionType,
  PointsSummaryRead,
} from '../../services/generated'
import { PointsAccountCard } from '../../components/points/PointsAccountCard'
import { PointTransactionTable } from '../../components/points/PointTransactionTable'

/** 流水类型筛选项。 */
const TYPE_FILTER_OPTIONS: { label: string; value: PointTransactionType }[] = [
  { label: '充值', value: 'recharge' },
  { label: '冻结', value: 'freeze' },
  { label: '扣减', value: 'consume' },
  { label: '解冻', value: 'unfreeze' },
]

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
  // 分组视图（按操作组聚合）相关状态
  const [groupedView, setGroupedView] = useState(false)
  const [groupedData, setGroupedData] = useState<OperationGroupRead[]>([])
  const [groupedTotal, setGroupedTotal] = useState(0)
  const [groupedLoading, setGroupedLoading] = useState(false)

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

  /** 加载分组流水（按操作组聚合），按页拉取。 */
  const loadGrouped = async (p: number, ps: number) => {
    setGroupedLoading(true)
    try {
      const res = await PointsService.listGroupedTransactionsApiV1PointsTransactionsGroupedGet({
        page: p,
        pageSize: ps,
      })
      setGroupedData(res.data?.items ?? [])
      setGroupedTotal(res.data?.pagination?.total ?? 0)
    } catch {
      message.error('分组流水加载失败')
    } finally {
      setGroupedLoading(false)
    }
  }

  useEffect(() => {
    void loadSummary()
    void loadTransactions(1, pageSize, typeFilter)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      <Card title="积分账户">
        <PointsAccountCard summary={summary} loading={loading} />
      </Card>

      <Card
        title="积分流水"
        extra={
          <Space>
            <Radio.Group
              size="small"
              value={groupedView ? 'grouped' : 'flat'}
              onChange={(e) => {
                const next = e.target.value === 'grouped'
                setGroupedView(next)
                setPage(1)
                if (next) {
                  void loadGrouped(1, pageSize)
                } else {
                  void loadTransactions(1, pageSize, typeFilter)
                }
              }}
            >
              <Radio.Button value="flat">明细</Radio.Button>
              <Radio.Button value="grouped">按操作</Radio.Button>
            </Radio.Group>
            {!groupedView && (
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
            )}
          </Space>
        }
      >
        <PointTransactionTable
          dataSource={groupedView ? groupedData : transactions}
          loading={groupedView ? groupedLoading : txLoading}
          total={groupedView ? groupedTotal : total}
          page={page}
          pageSize={pageSize}
          viewMode={groupedView ? 'grouped' : 'flat'}
          onChange={(p, ps) => {
            setPage(p)
            setPageSize(ps)
            if (groupedView) {
              void loadGrouped(p, ps)
            } else {
              void loadTransactions(p, ps, typeFilter)
            }
          }}
        />
      </Card>
    </div>
  )
}

export default PointsPage
