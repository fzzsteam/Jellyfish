import { useEffect, useState } from 'react'
import type React from 'react'
import { Card, message } from 'antd'
import { PointsService } from '../../services/generated'
import type {
  OperationGroupRead,
  PointsSummaryRead,
} from '../../services/generated'
import { PointsAccountCard } from '../../components/points/PointsAccountCard'
import { PointTransactionTable } from '../../components/points/PointTransactionTable'

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
    void loadGrouped(1, pageSize)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      <Card title="积分账户">
        <PointsAccountCard summary={summary} loading={loading} />
      </Card>

      <Card title="积分流水">
        <PointTransactionTable
          dataSource={groupedData}
          loading={groupedLoading}
          total={groupedTotal}
          page={page}
          pageSize={pageSize}
          onChange={(p, ps) => {
            setPage(p)
            setPageSize(ps)
            void loadGrouped(p, ps)
          }}
        />
      </Card>
    </div>
  )
}

export default PointsPage
