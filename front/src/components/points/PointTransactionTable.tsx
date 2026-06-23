/**
 * 积分流水表格通用组件。
 * 用户积分页（PointsPage）与管理员用户详情页（AdminUserDetailPage）共用此组件，
 * 避免列定义和金额渲染逻辑重复。
 *
 * 模型名称在组件内部自动解析：dataSource 更新时提取去重的 model_id，
 * 并发拉取后回填，父组件无需维护 modelMap。
 */

import { useEffect, useState } from 'react'
import { Table, Tag } from 'antd'
import type { TableColumnsType } from 'antd'
import { LlmService } from '../../services/generated'
import type {
  BillingLifecycleRead,
  OperationGroupRead,
  PointTransactionRead,
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

const formatTxTime = (v?: string | null): string => {
  if (!v) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(v))
}

/**
 * 根据流水类型决定金额的前缀符号与颜色：
 * - recharge：按 amount 符号（正→绿色"+"，负→红色"-"）
 * - consume：始终红色加"-"（amount 字段本身存正数，语义上是扣减）
 * - freeze/unfreeze：中性操作，无前缀，颜色与类型标签一致
 */
const getTxAmountStyle = (
  type: PointTransactionType,
  amount: number,
): { prefix: string; colorClass: string } => {
  switch (type) {
    case 'recharge':
      return amount >= 0
        ? { prefix: '+', colorClass: 'text-green-500' }
        : { prefix: '-', colorClass: 'text-red-500' }
    case 'consume':
      return { prefix: '-', colorClass: 'text-red-500' }
    case 'freeze':
      return { prefix: '', colorClass: 'text-orange-500' }
    case 'unfreeze':
      return { prefix: '', colorClass: 'text-blue-500' }
  }
}

interface PointTransactionTableProps {
  /** 明细模式传 PointTransactionRead[]，分组模式传 OperationGroupRead[] */
  dataSource: PointTransactionRead[] | OperationGroupRead[]
  loading?: boolean
  total?: number
  page?: number
  pageSize?: number
  /** 视图模式：flat=明细流水，grouped=按操作组聚合 */
  viewMode?: 'flat' | 'grouped'
  onChange?: (page: number, pageSize: number) => void
}

export const PointTransactionTable: React.FC<PointTransactionTableProps> = ({
  dataSource,
  loading,
  total = 0,
  page = 1,
  pageSize = 10,
  viewMode = 'flat',
  onChange,
}) => {
  const [modelMap, setModelMap] = useState<Record<string, string>>({})

  useEffect(() => {
    // 仅明细模式需要解析 model_id；分组模式 dataSource 为 OperationGroupRead[]
    if (viewMode !== 'flat') return
    const items = dataSource as PointTransactionRead[]
    const ids = [...new Set(
      items.map((t) => t.model_id).filter((id): id is string => !!id)
    )]
    if (ids.length === 0) return

    // 只拉当前页里出现的 model_id，并发请求后合并到已有 map
    void Promise.all(
      ids.map((id) =>
        LlmService.getModelApiV1LlmModelsModelIdGet({ modelId: id })
          .then((res) => res.data ? { id, name: res.data.name } : null)
          .catch(() => null)
      )
    ).then((results) => {
      const patch: Record<string, string> = {}
      for (const r of results) if (r) patch[r.id] = r.name
      setModelMap((prev) => ({ ...prev, ...patch }))
    })
  }, [dataSource])

  const columns: TableColumnsType<PointTransactionRead> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v?: string | null) => formatTxTime(v),
    },
    {
      title: '类型',
      dataIndex: 'type',
      width: 90,
      render: (t: PointTransactionType) => <Tag color={TX_TYPE_COLOR[t]}>{TX_TYPE_LABEL[t]}</Tag>,
    },
    {
      title: '金额',
      dataIndex: 'amount',
      width: 100,
      render: (v: number, record: PointTransactionRead) => {
        const { prefix, colorClass } = getTxAmountStyle(record.type, v)
        return (
          <span className={`text-xs font-medium ${colorClass}`}>
            {prefix}{Math.abs(v).toLocaleString()}
          </span>
        )
      },
    },
    { title: '业务类型', dataIndex: 'business_type', render: (v: string | null | undefined) => formatBusinessType(v) },
    {
      title: '模型',
      dataIndex: 'model_id',
      ellipsis: true,
      render: (v: string | null) => (v ? (modelMap[v] ?? v) : '—'),
    },
    {
      title: '余额',
      dataIndex: 'balance_after',
      width: 100,
      render: (v: number) => <PointsBadge value={v} size="sm" />,
    },
    { title: '备注', dataIndex: 'remark', ellipsis: true, render: (v) => v || '—' },
    {
      title: '操作人',
      dataIndex: 'created_by_username',
      width: 120,
      render: (v: string | null) => v || '—',
    },
  ]

  /**
   * 分组模式列定义：按 cascade_group_id 聚合展示操作级联。
   * 展开行展示该组内每笔 billing 的生命周期明细。
   */
  const groupedColumns: TableColumnsType<OperationGroupRead> = [
    {
      title: '操作时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v?: string | null) => formatTxTime(v),
    },
    {
      title: '业务类型',
      dataIndex: 'business_type',
      key: 'business_type',
      render: (v?: string | null) => formatBusinessType(v),
    },
    {
      title: '净消耗',
      dataIndex: 'total_net',
      key: 'total_net',
      width: 120,
      render: (v?: number) => <PointsBadge value={v ?? 0} size="sm" />,
    },
    {
      title: '账单数',
      key: 'billings',
      width: 100,
      render: (_: unknown, record: OperationGroupRead) => `${record.billings?.length ?? 0} 笔`,
    },
  ]

  /** billing 生命周期状态对应的中文标签与 Tag 颜色。 */
  const BILLING_STATUS_MAP: Record<string, { label: string; color: string }> = {
    settled: { label: '已结算', color: 'green' },
    refunded: { label: '已退回', color: 'blue' },
    frozen: { label: '冻结中', color: 'orange' },
  }

  // 分组模式：按操作组聚合展示，展开行显示 billing 明细
  if (viewMode === 'grouped') {
    return (
      <Table<OperationGroupRead>
        rowKey={(r) => r.cascade_group_id ?? JSON.stringify(r)}
        loading={loading}
        dataSource={dataSource as OperationGroupRead[]}
        columns={groupedColumns}
        size="small"
        scroll={{ x: 900, y: 400 }}
        expandable={{
          expandedRowRender: (record: OperationGroupRead) => (
            <div className="pl-4">
              {(record.billings ?? []).map((b: BillingLifecycleRead) => {
                const st = BILLING_STATUS_MAP[b.status] ?? { label: b.status, color: 'default' }
                return (
                  <div key={b.billing_id} className="flex items-center gap-3 py-1 text-xs">
                    <Tag color={st.color}>{st.label}</Tag>
                    <span className="text-gray-500">{formatBusinessType(b.business_type)}</span>
                    <span className="text-gray-400">
                      冻结 {b.frozen_amount ?? 0}
                      {b.net_amount !== undefined && b.net_amount > 0 && ` → 扣减 ${b.net_amount}`}
                    </span>
                  </div>
                )
              })}
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

  // 明细模式：展示逐笔流水
  return (
    <Table<PointTransactionRead>
      rowKey="id"
      loading={loading}
      dataSource={dataSource as PointTransactionRead[]}
      columns={columns}
      size="small"
      scroll={{ x: 900, y: 400 }}
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
