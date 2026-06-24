/**
 * 积分流水表格通用组件（按操作三层展开视图）。
 * 用户积分页（PointsPage）与管理员用户详情页（AdminUserDetailPage）共用此组件。
 *
 * 三层结构：操作组（cascade_group_id）→ 账单（billing_id）→ 流水事件（transaction）
 * highlightTransactionId / highlightBillingId 由父组件在搜索后传入，驱动自动展开与高亮。
 */

import { useEffect, useState } from 'react'
import { Table, Tag, Typography } from 'antd'
import { RightOutlined } from '@ant-design/icons'
import type { TableColumnsType } from 'antd'
import { LlmService } from '../../services/generated'
import type {
  BillingEventRead,
  BillingLifecycleRead,
  OperationGroupRead,
  PointTransactionType,
} from '../../services/generated'
import { PointsBadge } from './PointsBadge'
import { formatBusinessType } from './businessTypeLabels'

const TX_TYPE_COLOR: Record<PointTransactionType, string> = {
  recharge: 'green',
  freeze: 'orange',
  consume: 'red',
  unfreeze: 'blue',
}

const TX_TYPE_LABEL: Record<PointTransactionType, string> = {
  recharge: '充值',
  freeze: '冻结',
  consume: '扣减',
  unfreeze: '解冻',
}

const TX_AMOUNT_COLOR: Record<PointTransactionType, string> = {
  recharge: 'text-green-500',
  consume: 'text-red-500',
  freeze: 'text-orange-500',
  unfreeze: 'text-blue-500',
}

const BILLING_STATUS_MAP: Record<string, { label: string; color: string }> = {
  settled: { label: '已结算', color: 'green' },
  refunded: { label: '已退回', color: 'blue' },
  frozen:   { label: '冻结中', color: 'orange' },
}

const formatTxTime = (v?: string | null): string => {
  if (!v) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  }).format(new Date(v))
}

const CopyableId: React.FC<{ value?: string | null }> = ({ value }) => {
  if (!value) return <span className="text-gray-400">—</span>
  const display = value.length > 10 ? `${value.slice(0, 8)}…` : value
  return (
    <Typography.Text
      copyable={{ text: value, tooltips: ['复制', '已复制'] }}
      className="!font-mono !text-xs !text-gray-500"
    >
      {display}
    </Typography.Text>
  )
}

/** Level 3 迷你表格列定义：单个 billing 下的流水事件列表。 */
const makeEventColumns = (): TableColumnsType<BillingEventRead> => [
  {
    title: 'ID',
    dataIndex: 'id',
    width: 170,
    render: (v: string) => (
      <span className="flex items-center gap-1">
        <Tag color="cyan" className="m-0 shrink-0 !text-xs !py-0">流水</Tag>
        <CopyableId value={v} />
      </span>
    ),
  },
  {
    title: '类型',
    dataIndex: 'type',
    width: 70,
    render: (t: PointTransactionType) => (
      <Tag color={TX_TYPE_COLOR[t]}>{TX_TYPE_LABEL[t]}</Tag>
    ),
  },
  {
    title: '金额',
    dataIndex: 'amount',
    width: 80,
    render: (v: number, r: BillingEventRead) => (
      <span className={`text-xs font-medium ${TX_AMOUNT_COLOR[r.type]}`}>
        {Math.abs(v)}
      </span>
    ),
  },
  {
    title: '时间',
    dataIndex: 'created_at',
    width: 160,
    render: (v?: string | null) => (
      <span className="text-xs text-gray-400">{formatTxTime(v)}</span>
    ),
  },
  {
    title: '余额',
    dataIndex: 'balance_after',
    width: 85,
    render: (v?: number | null) =>
      v !== null && v !== undefined ? (
        <PointsBadge value={v} size="sm" />
      ) : (
        <span className="text-gray-300">—</span>
      ),
  },
  {
    // 单条流水备注;为空时不显示占位符(如"—"),保持空字符串以与明细语义一致
    title: '备注',
    dataIndex: 'remark',
    ellipsis: true,
    render: (v?: string | null) => v || '',
  },
  ]

/** Level 2 账单行列定义。 */
const makeBillingColumns = (modelMap: Record<string, string>): TableColumnsType<BillingLifecycleRead> => [
  {
    title: 'ID',
    dataIndex: 'billing_id',
    width: 185,
    render: (v: string) => (
      <span className="flex items-center gap-1">
        <Tag color="purple" className="m-0 shrink-0 !text-xs !py-0">账单</Tag>
        <CopyableId value={v} />
      </span>
    ),
  },
  {
    title: '状态',
    dataIndex: 'status',
    width: 90,
    render: (v: string) => {
      const st = BILLING_STATUS_MAP[v] ?? { label: v, color: 'default' }
      return <Tag color={st.color}>{st.label}</Tag>
    },
  },
  {
    title: '模型',
    dataIndex: 'model_id',
    ellipsis: true,
    render: (v: string | null) => (
      <span className="text-xs text-gray-500">{v ? (modelMap[v] ?? v) : '—'}</span>
    ),
  },
  {
    title: '冻结额',
    dataIndex: 'frozen_amount',
    width: 75,
    render: (v: number) => (
      <span className="text-orange-500 text-xs font-medium">{v}</span>
    ),
  },
  {
    title: '扣减额',
    dataIndex: 'net_amount',
    width: 75,
    render: (v: number) =>
      v > 0 ? (
        <span className="text-red-500 text-xs font-medium">−{v}</span>
      ) : (
        <span className="text-gray-300">—</span>
      ),
  },
  {
    title: '时间',
    dataIndex: 'created_at',
    width: 165,
    render: (v?: string | null) => (
      <span className="text-xs text-gray-400">{formatTxTime(v)}</span>
    ),
  },
]

export interface PointTransactionTableProps {
  dataSource: OperationGroupRead[]
  loading?: boolean
  total?: number
  page?: number
  pageSize?: number
  onChange?: (page: number, pageSize: number) => void
  /** 按流水ID搜索时传入，驱动自动展开到对应账单并高亮该流水行。 */
  highlightTransactionId?: string
  /** 按账单ID搜索时传入，驱动自动展开到对应账单行。 */
  highlightBillingId?: string
}

export const PointTransactionTable: React.FC<PointTransactionTableProps> = ({
  dataSource,
  loading,
  total = 0,
  page = 1,
  pageSize = 10,
  onChange,
  highlightTransactionId,
  highlightBillingId,
}) => {
  const [modelMap, setModelMap] = useState<Record<string, string>>({})
  const [expandedOpKeys, setExpandedOpKeys] = useState<string[]>([])
  const [expandedBillKeys, setExpandedBillKeys] = useState<string[]>([])

  // 解析 model_id → 名称
  useEffect(() => {
    const ids = [
      ...new Set(
        dataSource
          .flatMap((g) => (g.billings ?? []).map((b) => b.model_id))
          .filter((id): id is string => !!id)
      ),
    ]
    if (ids.length === 0) return
    void Promise.all(
      ids.map((id) =>
        LlmService.getModelApiV1LlmModelsModelIdGet({ modelId: id })
          .then((res) => (res.data ? { id, name: res.data.name } : null))
          .catch(() => null)
      )
    ).then((results) => {
      const patch: Record<string, string> = {}
      for (const r of results) if (r) patch[r.id] = r.name
      setModelMap((prev) => ({ ...prev, ...patch }))
    })
  }, [dataSource])

  // 搜索命中时自动展开对应操作组与账单行
  useEffect(() => {
    if (!highlightTransactionId && !highlightBillingId) {
      setExpandedOpKeys([])
      setExpandedBillKeys([])
      return
    }
    const newOpKeys: string[] = []
    const newBillKeys: string[] = []
    for (const op of dataSource) {
      if (!op.cascade_group_id) continue
      for (const bill of op.billings ?? []) {
        const matchBilling = highlightBillingId && bill.billing_id === highlightBillingId
        const matchTx =
          highlightTransactionId &&
          (bill.events ?? []).some((e) => e.id === highlightTransactionId)
        if (matchBilling || matchTx) {
          newOpKeys.push(op.cascade_group_id)
          newBillKeys.push(bill.billing_id)
        }
      }
    }
    setExpandedOpKeys(newOpKeys)
    setExpandedBillKeys(newBillKeys)
  }, [dataSource, highlightTransactionId, highlightBillingId])

  /** 通用展开图标，点击时旋转 90°。泛型 T 匹配各层行类型。 */
  function expandIcon<T>({
    expanded,
    onExpand,
    record,
  }: {
    expanded: boolean
    onExpand: (record: T, e: React.MouseEvent<HTMLElement>) => void
    record: T
  }) {
    return (
      <RightOutlined
        className={`transition-transform duration-200 text-gray-400 cursor-pointer mr-1 ${
          expanded ? 'rotate-90' : ''
        }`}
        onClick={(e) => onExpand(record, e as unknown as React.MouseEvent<HTMLElement>)}
      />
    )
  }

  // Level 1 列定义（操作组行）
  const opColumns: TableColumnsType<OperationGroupRead> = [
    {
      title: 'ID',
      dataIndex: 'cascade_group_id',
      width: 195,
      render: (v?: string | null) => (
        <span className="flex items-center gap-1">
          <Tag className="m-0 shrink-0 !text-xs !py-0">操作</Tag>
          <CopyableId value={v} />
        </span>
      ),
    },
    {
      title: '业务类型',
      dataIndex: 'business_type',
      render: (v?: string | null) => formatBusinessType(v),
    },
    {
      title: '操作时间',
      dataIndex: 'created_at',
      width: 165,
      render: (v?: string | null) => formatTxTime(v),
    },
    {
      title: '净消耗',
      dataIndex: 'total_net',
      width: 100,
      render: (v?: number) => <PointsBadge value={v ?? 0} size="sm" />,
    },
    {
      title: '账单数',
      width: 75,
      render: (_: unknown, record: OperationGroupRead) => (
        <span className="text-gray-400 text-xs">{record.billings?.length ?? 0} 笔</span>
      ),
    },
  ]

  return (
    <Table<OperationGroupRead>
      rowKey={(r) => r.cascade_group_id ?? JSON.stringify(r)}
      loading={loading}
      dataSource={dataSource}
      columns={opColumns}
      size="small"
      scroll={{ x: 800 }}
      onRow={() => ({ style: { cursor: 'pointer' } })}
      expandable={{
        expandedRowKeys: expandedOpKeys,
        onExpandedRowsChange: (keys) => setExpandedOpKeys(keys as string[]),
        expandRowByClick: true,
        showExpandColumn: true,
        expandIcon,
        expandedRowRender: (op: OperationGroupRead) => (
          <div className="bg-slate-50 py-2 px-4">
            <Table<BillingLifecycleRead>
              rowKey="billing_id"
              dataSource={op.billings ?? []}
              columns={makeBillingColumns(modelMap)}
              size="small"
              pagination={false}
              onRow={() => ({ style: { cursor: 'pointer' } })}
              expandable={{
                expandedRowKeys: expandedBillKeys,
                onExpandedRowsChange: (keys) => setExpandedBillKeys(keys as string[]),
                expandRowByClick: true,
                showExpandColumn: true,
                expandIcon,
                expandedRowRender: (bill: BillingLifecycleRead) => (
                  <div className="bg-slate-100 px-4 py-2">
                    <Table<BillingEventRead>
                      rowKey="id"
                      dataSource={bill.events ?? []}
                      columns={makeEventColumns()}
                      size="small"
                      pagination={false}
                      rowClassName={(r) =>
                        r.id === highlightTransactionId
                          ? 'bg-amber-50 !ring-1 !ring-amber-300'
                          : ''
                      }
                    />
                  </div>
                ),
              }}
            />
          </div>
        ),
      }}
      pagination={{
        current: page,
        pageSize,
        total,
        showSizeChanger: true,
        onChange,
      }}
    />
  )
}
