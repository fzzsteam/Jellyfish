import { Modal } from 'antd'
import type { PointsQuoteResponse } from '../../../../services/generated'
import { PointsBadge } from '../../../../components/points/PointsBadge'

/**
 * 提取/自动准备流程积分确认弹窗的单行费用项。
 *
 * 渲染优先级：free > quote（含 textMultiplier）> 加载中 > 未配置。
 */
export type ExtractionCostRow = {
  label: string
  /** 标记为免费操作，显示"免费"绿色标签。 */
  free?: true
  /** 积分 quote；null = 加载中或未配置，需配合 loading/noModel 区分。 */
  quote?: PointsQuoteResponse | null
  /** 乘以该系数后展示（例如 divide+extract 两次文本调用传 2）。 */
  textMultiplier?: number
  /** true = 没有配置对应模型，显示"未配置"而不是"计算中"。 */
  noModel?: true
  /** true = quote 正在加载中。 */
  loading?: boolean
}

type ExtractionConfirmModalProps = {
  open: boolean
  title: string
  okText?: string
  onConfirm: () => void
  onCancel: () => void
  /** 积分消耗明细行，按显示顺序传入。 */
  costRows: ExtractionCostRow[]
  /** 弹窗底部补充说明文案。 */
  note?: string
}

function CostRowValue({ row }: { row: ExtractionCostRow }) {
  if (row.free) {
    return <span className="text-green-600 text-xs font-medium">免费</span>
  }
  if (row.loading) {
    return <span className="text-gray-400 text-xs">计算中…</span>
  }
  if (row.noModel) {
    return <span className="text-gray-400 text-xs">图片模型未配置</span>
  }
  if (row.quote) {
    const points = row.textMultiplier && row.textMultiplier > 1
      ? row.quote.required_points * row.textMultiplier
      : row.quote.required_points
    return <PointsBadge value={points} size="sm" />
  }
  return <span className="text-gray-400 text-xs">计算中…</span>
}

/**
 * 提取/自动准备流程积分确认弹窗。
 *
 * 被以下场景复用：
 * - 分镜列表页"一键提取分镜并自动准备"（divide + extract + auto-prepare）
 * - 分镜准备页"重新提取/刷新候选"（单条 extract + auto-prepare）
 * - 分镜准备页"批量提取"（多条 extract + auto-prepare）
 */
export function ExtractionConfirmModal({
  open,
  title,
  okText = '确认，开始提取',
  onConfirm,
  onCancel,
  costRows,
  note,
}: ExtractionConfirmModalProps) {
  return (
    <Modal
      title={title}
      open={open}
      onOk={onConfirm}
      onCancel={onCancel}
      okText={okText}
      cancelText="取消"
      destroyOnClose
    >
      <div className="flex flex-col gap-3 py-2 text-sm text-gray-600">
        <p>本次操作包含以下步骤，积分消耗如下：</p>
        <div className="flex flex-col gap-2 rounded-lg bg-gray-50 px-4 py-3">
          {costRows.map((row, i) => (
            <div key={i} className="flex items-center justify-between">
              <span>{row.label}</span>
              <CostRowValue row={row} />
            </div>
          ))}
        </div>
        {note && (
          <p className="text-gray-400 text-xs leading-relaxed">{note}</p>
        )}
      </div>
    </Modal>
  )
}
