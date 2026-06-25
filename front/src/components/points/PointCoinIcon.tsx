import './PointCoinIcon.css'

/** 统一使用 /point_pet.svg（金币），无需颜色变体。尺寸略放大以与文字比例协调。 */
const SIZE_PX: Record<'xs' | 'sm' | 'md' | 'lg', number> = {
  xs: 16,
  sm: 20,
  md: 26,
  lg: 34,
}

type IconSize = keyof typeof SIZE_PX

/**
 * 积分金币图标。
 * 全局统一，不做颜色过滤——SVG 自带渐变金色。
 * 配合父容器 `point-amount-hover` class 触发弹跳+金色光晕动效。
 */
export function PointCoinIcon({
  size = 'md',
  className = '',
}: {
  size?: IconSize
  className?: string
}) {
  const px = SIZE_PX[size]
  return (
    <img
      src="/point_pet.svg"
      alt="积分"
      className={`point-coin-icon select-none${className ? ` ${className}` : ''}`}
      style={{ width: px, height: px, display: 'block', flexShrink: 0 }}
      draggable={false}
    />
  )
}
