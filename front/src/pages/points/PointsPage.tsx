import { useEffect, useState } from 'react'
import type React from 'react'
import { Card, Input, Select, Space, Tabs, message } from 'antd'
import { PointsService } from '../../services/generated'
import type {
  OperationGroupRead,
  PointTransactionRead,
  PointsSummaryRead,
} from '../../services/generated'
import { PointsAccountCard } from '../../components/points/PointsAccountCard'
import { PointTransactionTable } from '../../components/points/PointTransactionTable'
import { SimplePointTransactionTable } from '../../components/points/SimplePointTransactionTable'

/**
 * 用户积分页：展示当前用户积分账户摘要与积分流水（三层展开分组视图）。
 * 数据通过 generated PointsService 拉取。
 */
const PointsPage: React.FC = () => {
  const [summary, setSummary] = useState<PointsSummaryRead | null>(null)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [groupedData, setGroupedData] = useState<OperationGroupRead[]>([])
  const [simpleTxns, setSimpleTxns] = useState<PointTransactionRead[]>([])
  const [groupedTotal, setGroupedTotal] = useState(0)
  const [groupedLoading, setGroupedLoading] = useState(false)
  const [searchIdType, setSearchIdType] = useState<'cascade_group_id' | 'billing_id' | 'transaction_id'>('cascade_group_id')
  const [searchIdValue, setSearchIdValue] = useState<string | undefined>(undefined)
  const [highlightTransactionId, setHighlightTransactionId] = useState<string | undefined>(undefined)

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

  /**
   * 加载分组流水（按操作组聚合），按页拉取。
   * 支持三种 ID 过滤：操作ID(cascade_group_id)、账单ID(billing_id)、流水ID(transaction_id)。
   * 当按 transaction_id 搜索时，后端会返回 matched_transaction_id 用于高亮命中行。
   */
  const loadGrouped = async (
    p: number,
    ps: number,
    idType?: 'cascade_group_id' | 'billing_id' | 'transaction_id',
    idValue?: string,
  ) => {
    setGroupedLoading(true)
    try {
      const res = await PointsService.listGroupedTransactionsApiV1PointsTransactionsGroupedGet({
        page: p,
        pageSize: ps,
        cascadeGroupId: idType === 'cascade_group_id' ? idValue : undefined,
        billingId: idType === 'billing_id' ? idValue : undefined,
        transactionId: idType === 'transaction_id' ? idValue : undefined,
      })
      setGroupedData(res.data?.items ?? [])
      setSimpleTxns(res.data?.simple_txns ?? [])
      setGroupedTotal(res.data?.pagination?.total ?? 0)
      setHighlightTransactionId(res.data?.matched_transaction_id ?? undefined)
    } catch {
      message.error('流水加载失败')
    } finally {
      setGroupedLoading(false)
    }
  }

  useEffect(() => {
    void loadSummary()
    void loadGrouped(1, pageSize)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      <Card title="积分账户">
        <PointsAccountCard summary={summary} loading={loading} />
      </Card>

      <Card title="积分流水">
        <Tabs
          defaultActiveKey="operations"
          items={[
            {
              key: 'operations',
              label: '操作记录',
              children: (
                <div>
                  <div className="mb-3">
                    <Space>
                      <Select<'cascade_group_id' | 'billing_id' | 'transaction_id'>
                        size="small"
                        value={searchIdType}
                        style={{ width: 88 }}
                        options={[
                          { label: '操作ID', value: 'cascade_group_id' },
                          { label: '账单ID', value: 'billing_id' },
                          { label: '流水ID', value: 'transaction_id' },
                        ]}
                        onChange={(v) => {
                          setSearchIdType(v)
                          setSearchIdValue(undefined)
                          setHighlightTransactionId(undefined)
                        }}
                      />
                      <Input.Search
                        allowClear
                        placeholder="输入搜索值"
                        size="small"
                        style={{ width: 200 }}
                        value={searchIdValue}
                        onChange={(e) => setSearchIdValue(e.target.value || undefined)}
                        onSearch={(v) => {
                          const val = v.trim() || undefined
                          setSearchIdValue(val)
                          setPage(1)
                          void loadGrouped(1, pageSize, searchIdType, val)
                          if (!val) setHighlightTransactionId(undefined)
                        }}
                      />
                    </Space>
                  </div>
                  <PointTransactionTable
                    dataSource={groupedData}
                    loading={groupedLoading}
                    total={groupedTotal}
                    page={page}
                    pageSize={pageSize}
                    highlightTransactionId={highlightTransactionId}
                    highlightBillingId={searchIdType === 'billing_id' ? searchIdValue : undefined}
                    onChange={(p, ps) => {
                      setPage(p)
                      setPageSize(ps)
                      void loadGrouped(p, ps, searchIdType, searchIdValue)
                    }}
                  />
                </div>
              ),
            },
            {
              key: 'simple',
              label: '充值/调整',
              children: <SimplePointTransactionTable dataSource={simpleTxns} />,
            },
          ]}
        />
      </Card>
    </div>
  )
}

export default PointsPage
