import { Spin } from 'antd'
import type { PointsSummaryRead } from '../../services/generated'

/**
 * 积分账户摘要块：三项横排（可用/冻结/总余额），竖向分隔线分组，
 * 数值直接展示，不套 PointsBadge 避免双层卡片视觉噪音。
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

  const items = [
    {
      label: '可用积分',
      value: summary?.available,
      cls: 'text-amber-500',
      prefix: '🪙 ',
    },
    {
      label: '冻结积分',
      value: summary?.frozen,
      cls: (summary?.frozen ?? 0) > 0 ? 'text-orange-400' : 'text-gray-400',
    },
    {
      label: '总余额',
      value: summary?.balance,
      cls: 'text-gray-500',
    },
  ]

  return (
    <div className="flex items-stretch divide-x divide-gray-100">
      {items.map(({ label, value, cls, prefix }) => (
        <div key={label} className="flex flex-col gap-0.5 px-4 first:pl-0">
          <span className="text-xs text-gray-400">{label}</span>
          <span className={`text-lg font-semibold ${cls}`}>
            {value !== undefined && value !== null
              ? `${prefix ?? ''}${value.toLocaleString()}`
              : '—'}
          </span>
        </div>
      ))}
    </div>
  )
}
