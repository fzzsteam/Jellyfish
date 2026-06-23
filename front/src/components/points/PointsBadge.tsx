/**
 * PointsBadge：积分数值展示徽标，金币视觉风格。
 *
 * 三档尺寸：
 *   lg — 积分页/管理详情余额大字展示
 *   md — 模型详情单价、字段级展示
 *   sm — 表格列、生成按钮旁轻量提示
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

  const color = insufficient ? 'text-orange-500' : 'text-amber-500'
  const bgColor = insufficient ? 'bg-orange-50' : 'bg-amber-50'
  const gradientBg = insufficient
    ? 'bg-gradient-to-r from-orange-50 to-red-50'
    : 'bg-gradient-to-r from-amber-50 to-yellow-50'

  if (size === 'lg') {
    return (
      <div className={`inline-flex flex-col items-start ${gradientBg} rounded-xl px-4 py-2 border border-amber-100`}>
        <div className={`flex items-center gap-1.5 ${color}`}>
          <span className="text-lg">🪙</span>
          <span className={`text-2xl font-bold ${color}`}>{value.toLocaleString()}</span>
        </div>
        {suffix && <span className="text-xs text-gray-400 mt-0.5">{suffix}</span>}
      </div>
    )
  }

  if (size === 'md') {
    return (
      <span className={`inline-flex items-center gap-1 ${bgColor} rounded-full px-2.5 py-0.5 border border-amber-100`}>
        <span className="text-sm">🪙</span>
        <span className={`text-base font-semibold ${color}`}>{value.toLocaleString()}</span>
        {suffix && <span className="text-xs text-gray-400 ml-0.5">{suffix}</span>}
      </span>
    )
  }

  // sm
  return (
    <span className={`inline-flex items-center gap-0.5 ${color}`}>
      <span className="text-xs">🪙</span>
      <span className={`text-xs font-medium ${color}`}>{value.toLocaleString()}</span>
      {suffix && <span className="text-xs text-gray-400 ml-0.5">{suffix}</span>}
    </span>
  )
}
