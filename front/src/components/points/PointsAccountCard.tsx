import { Spin } from 'antd'
import type { PointsSummaryRead } from '../../services/generated'
import { PointsBadge } from './PointsBadge'

/**
 * 积分账户摘要块：横排展示可用/冻结/总余额，替代平铺的 Descriptions。
 * 可用积分金色大号突出，冻结橙色警示，余额灰色中性。
 */
export function PointsAccountCard({
  summary,
  loading = false,
}: {
  summary: PointsSummaryRead | null
  loading?: boolean
}) {
  if (loading) {
    return (
      <div className="flex justify-center py-6">
        <Spin />
      </div>
    )
  }

  return (
    <div className="flex flex-wrap gap-6 items-end">
      <div className="flex flex-col gap-1">
        <span className="text-xs text-gray-400">可用积分</span>
        <PointsBadge value={summary?.available ?? null} size="lg" />
      </div>
      <div className="flex flex-col gap-1">
        <span className="text-xs text-gray-400">冻结积分</span>
        <span className="text-base font-semibold text-orange-400">
          {summary?.frozen?.toLocaleString() ?? '—'}
        </span>
      </div>
      <div className="flex flex-col gap-1">
        <span className="text-xs text-gray-400">总余额</span>
        <span className="text-base font-semibold text-gray-400">
          {summary?.balance?.toLocaleString() ?? '—'}
        </span>
      </div>
    </div>
  )
}
