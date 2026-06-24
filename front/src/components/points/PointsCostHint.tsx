import type { PointsQuoteResponse } from '../../services/generated'
import { PointsBadge } from './PointsBadge'

/**
 * PointsCostHintProps。
 * 直接接收 usePointsQuote 的试算状态字段，保持无状态、零副作用。
 *
 * - textMultiplier: 文本类业务的计量倍数（如分镜拆解分镜+提取=单价×2），徽标直接展示计算后总价。
 */
export type PointsCostHintProps = {
  quote: PointsQuoteResponse | null
  loading: boolean
  error: string | null
  textMultiplier?: number
}

/**
 * 积分消耗提示组件。
 *
 * 用于在文本/图片/视频生成触发按钮旁展示本次扣费的轻量提示：
 * - loading：正在试算。
 * - error：试算失败（不阻断渲染，给用户一个可感知的状态）。
 * - quote 不足：橙色高亮可用额度与所需积分。
 * - quote 充足：金色积分徽标展示将消耗积分。
 *
 * textMultiplier 时徽标直接展示总价（如 required_points=2, multiplier=2 → 徽标显示 4），
 * 不额外追加 ×N 文字（避免用户混淆「乘数」与「总价」）。
 *
 * 仅做展示，不参与提交控制（提交门控由调用方根据 canSubmit 决定按钮 disabled）。
 */
export function PointsCostHint({ quote, loading, error, textMultiplier }: PointsCostHintProps) {
  if (loading) {
    return <span className="text-xs text-gray-400">正在计算积分…</span>
  }
  if (error) {
    return <span className="text-xs text-red-500">{error}</span>
  }
  if (!quote) {
    return null
  }
  const showMultiplier = typeof textMultiplier === 'number' && textMultiplier > 1
  const totalPoints = showMultiplier ? quote.required_points * textMultiplier! : quote.required_points
  if (!quote.sufficient) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-orange-500">
        <span>可用</span>
        <PointsBadge value={quote.available_points} size="sm" insufficient />
        <span>，需要</span>
        <PointsBadge value={quote.required_points} size="sm" insufficient />
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-gray-400">
      <span>将消耗</span>
      <PointsBadge value={totalPoints} size="sm" />
    </span>
  )
}