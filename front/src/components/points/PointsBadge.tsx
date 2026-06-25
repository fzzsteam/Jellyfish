import { PointCoinIcon } from './PointCoinIcon'

/**
 * PointsBadge：积分数值展示徽标，金币图标 + 琥珀色数值。
 *
 * 三档尺寸：
 *   lg — 积分页/管理详情余额大字展示
 *   md — 模型详情单价、字段级展示
 *   sm — 表格列、按钮旁轻量提示
 */
export type PointsBadgeProps = {
  value: number | null | undefined
  suffix?: string
  size?: 'sm' | 'md' | 'lg'
  insufficient?: boolean
}

export function PointsBadge({ value, suffix, size = 'md', insufficient = false }: PointsBadgeProps) {
  if (value === null || value === undefined) {
    return <span className="text-gray-400">—</span>
  }

  const color       = insufficient ? 'text-red-600'    : 'text-amber-600'
  const bgColor     = insufficient ? 'bg-red-50'       : 'bg-amber-50'
  const gradientBg  = insufficient
    ? 'bg-gradient-to-r from-red-50 to-rose-50'
    : 'bg-gradient-to-r from-amber-50 to-yellow-50'
  const borderColor = insufficient ? 'border-red-100' : 'border-amber-200'

  if (size === 'lg') {
    return (
      <div className={`point-amount-hover inline-flex flex-col items-start ${gradientBg} rounded-xl px-4 py-2.5 border ${borderColor} cursor-default`}>
        <div className="flex items-center gap-2">
          <PointCoinIcon size="md" />
          <span className={`text-2xl font-bold tracking-tight leading-none ${color}`}>{value.toLocaleString()}</span>
        </div>
        {suffix && <span className="text-xs text-gray-400 mt-1 pl-0.5">{suffix}</span>}
      </div>
    )
  }

  if (size === 'md') {
    return (
      <span className={`point-amount-hover inline-flex items-center gap-1.5 ${bgColor} rounded-full px-2.5 py-0.5 border ${borderColor} cursor-default`}>
        <PointCoinIcon size="sm" />
        <span className={`text-sm font-bold leading-none ${color}`}>{value.toLocaleString()}</span>
        {suffix && <span className="text-xs text-gray-400 ml-0.5">{suffix}</span>}
      </span>
    )
  }

  // sm
  return (
    <span className={`point-amount-hover inline-flex items-center gap-1 ${color} cursor-default`}>
      <PointCoinIcon size="xs" />
      <span className={`text-xs font-semibold leading-none ${color}`}>{value.toLocaleString()}</span>
      {suffix && <span className="text-xs text-gray-400 ml-0.5">{suffix}</span>}
    </span>
  )
}
