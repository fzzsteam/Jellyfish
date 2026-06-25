import { Spin } from 'antd'
import type { PointsSummaryRead } from '../../services/generated'
import { PointCoinIcon } from './PointCoinIcon'

/**
 * 积分账户摘要块：三项横排（可用/冻结/总余额），竖向分隔线分组。
 * 可用积分前置水母图标，hover 触发弹跳动效。
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
      cls: 'text-amber-600',
      showIcon: true,
    },
    {
      label: '冻结积分',
      value: summary?.frozen,
      cls: (summary?.frozen ?? 0) > 0 ? 'text-orange-400' : 'text-gray-400',
      showIcon: false,
    },
    {
      label: '总余额',
      value: summary?.balance,
      cls: 'text-gray-500',
      showIcon: false,
    },
  ]

  return (
    <div className="flex items-stretch divide-x divide-gray-100">
      {items.map(({ label, value, cls, showIcon }) => (
        <div key={label} className="flex flex-col gap-0.5 px-4 first:pl-0">
          <span className="text-xs text-gray-400">{label}</span>
          {value !== undefined && value !== null ? (
            <span className={`point-amount-hover inline-flex items-center gap-1 text-lg font-semibold ${cls} cursor-default`}>
              {showIcon && <PointCoinIcon size="sm" />}
              {value.toLocaleString()}
            </span>
          ) : (
            <span className={`text-lg font-semibold ${cls}`}>—</span>
          )}
        </div>
      ))}
    </div>
  )
}
