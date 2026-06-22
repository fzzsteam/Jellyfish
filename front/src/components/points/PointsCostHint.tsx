import type { PointsQuoteResponse } from '../../services/generated'

/**
 * PointsCostHintProps。
 * 直接接收 usePointsQuote 的试算状态字段，保持无状态、零副作用。
 */
export type PointsCostHintProps = {
  quote: PointsQuoteResponse | null
  loading: boolean
  error: string | null
}

/**
 * 积分消耗提示组件。
 *
 * 用于在文本/图片/视频生成触发按钮旁展示本次扣费的轻量提示：
 * - loading：正在试算。
 * - error：试算失败（不阻断渲染，给用户一个可感知的状态）。
 * - quote 不足：橙色高亮可用额度与所需积分。
 * - quote 充足：中性灰色展示将消耗积分。
 *
 * 仅做展示，不参与提交控制（提交门控由调用方根据 canSubmit 决定按钮 disabled）。
 */
export function PointsCostHint({ quote, loading, error }: PointsCostHintProps) {
  if (loading) {
    return <span className="text-xs text-gray-500">正在计算积分…</span>
  }
  if (error) {
    return <span className="text-xs text-red-500">{error}</span>
  }
  if (!quote) {
    return null
  }
  if (!quote.sufficient) {
    return (
      <span className="text-xs text-orange-500">
        可用 {quote.available_points}，本次需要 {quote.required_points}
      </span>
    )
  }
  return <span className="text-xs text-gray-500">将消耗 {quote.required_points} 积分</span>
}
