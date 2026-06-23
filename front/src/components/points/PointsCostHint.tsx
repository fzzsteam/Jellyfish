import type { PointsQuoteResponse } from '../../services/generated'
import { PointsBadge } from './PointsBadge'

/**
 * PointsCostHintProps。
 * 直接接收 usePointsQuote 的试算状态字段，保持无状态、零副作用。
 *
 * - textMultiplier: 文本类业务的计量倍数（如分镜拆解 = 单价 × 章节数），展示为 [X×Y] 形式；
 *   未传或 <=1 时回退到仅展示 required_points。
 * - perImagePoints: 单张资产图积分；非空时追加「每张资产图 Z」说明，为空表示图片模型未配置。
 */
export type PointsCostHintProps = {
  quote: PointsQuoteResponse | null
  loading: boolean
  error: string | null
  textMultiplier?: number
  perImagePoints?: number | null
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
 * 仅做展示，不参与提交控制（提交门控由调用方根据 canSubmit 决定按钮 disabled）。
 */
export function PointsCostHint({ quote, loading, error, textMultiplier, perImagePoints }: PointsCostHintProps) {
  if (loading) {
    return <span className="text-xs text-gray-400">正在计算积分…</span>
  }
  if (error) {
    return <span className="text-xs text-red-500">{error}</span>
  }
  if (!quote) {
    return null
  }
  // 计量倍数展示：仅当显式传入且 >1 时按 [单价×倍数] 形式呈现，否则回退为纯数值。
  const showMultiplier = typeof textMultiplier === 'number' && textMultiplier > 1
  // 倍数生效时徽标展示「单价 × 倍数 = 总积分」，并追加 ×倍数文字提示。
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
      {showMultiplier && <span>×{textMultiplier}</span>}
      {perImagePoints != null ? (
        <span>，每张资产图 <PointsBadge value={perImagePoints} size="sm" />（按实际新建数量另计）</span>
      ) : (
        <span>（图片模型未配置）</span>
      )}
    </span>
  )
}
