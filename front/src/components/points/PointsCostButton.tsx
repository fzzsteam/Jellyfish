import type { ButtonProps } from 'antd'
import { Button, Tooltip } from 'antd'
import type { ReactNode } from 'react'
import type { PointsQuoteResponse } from '../../services/generated'
import { PointCoinIcon } from './PointCoinIcon'

export type PointsCostButtonProps = ButtonProps & {
  quote: PointsQuoteResponse | null
  quoteLoading?: boolean
  quoteError?: string | null
  textMultiplier?: number
}

/**
 * 将积分消耗内嵌在按钮内的联合按钮。
 *
 * 对齐策略：全部用 inline style 而非 Tailwind，
 * 避免 Ant Design Button 内部 span 包裹层干扰 CSS 优先级。
 *
 * 数量颜色随按钮底色适配：
 *   primary（蓝底）  → amber-200（浅金）
 *   default/其他     → amber-600（深金）
 *   insufficient     → disabled + Tooltip 提示
 */
export function PointsCostButton({
  quote,
  quoteLoading,
  quoteError,
  textMultiplier,
  disabled,
  children,
  ...buttonProps
}: PointsCostButtonProps) {
  const totalPoints =
    quote !== null && quote !== undefined
      ? textMultiplier && textMultiplier > 1
        ? quote.required_points * textMultiplier
        : quote.required_points
      : null

  const insufficient = !!quote && !quote.sufficient
  const effectiveDisabled = !!disabled || !!quoteLoading || !!quoteError || !quote || insufficient

  const isPrimary = buttonProps.type === 'primary'

  const amountStyle: React.CSSProperties = {
    color: insufficient
      ? (isPrimary ? '#fca5a5' : '#ef4444')   // red-300 / red-500
      : isPrimary
        ? '#fde68a'                             // amber-200
        : '#d97706',                            // amber-600
    display: 'inline-flex',
    alignItems: 'center',
    gap: 2,
    fontSize: 11,
    fontWeight: 600,
    lineHeight: 1,
    marginLeft: 6,
  }

  let costNode: ReactNode = null
  if (quoteLoading) {
    costNode = (
      <span style={{ marginLeft: 6, fontSize: 11, opacity: 0.45, lineHeight: 1 }}>···</span>
    )
  } else if (!quoteError && totalPoints !== null) {
    costNode = (
      <span style={amountStyle}>
        <PointCoinIcon size="xs" />
        <span>{totalPoints.toLocaleString()}</span>
      </span>
    )
  }

  const btn = (
    <Button {...buttonProps} disabled={effectiveDisabled}>
      {/* inline style 强制 flex 对齐，绕开 Ant Design Button 内部 span 的 line-height 干扰 */}
      <span style={{ display: 'inline-flex', alignItems: 'center', lineHeight: 1 }}>
        <span>{children}</span>
        {costNode}
      </span>
    </Button>
  )

  if (insufficient && quote) {
    return (
      <Tooltip title={`积分不足：可用 ${quote.available_points}，需要 ${quote.required_points}`}>
        <span style={{ display: 'inline-flex' }}>{btn}</span>
      </Tooltip>
    )
  }

  return btn
}
