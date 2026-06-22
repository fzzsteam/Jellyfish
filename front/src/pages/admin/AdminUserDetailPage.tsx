import { useEffect, useState } from 'react'
import type React from 'react'
import {
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Table,
  Tag,
  message,
} from 'antd'
import type { TableColumnsType } from 'antd'
import { useParams } from 'react-router-dom'
import { AdminService } from '../../services/generated'
import type {
  PointTransactionRead,
  PointTransactionType,
  PointsSummaryRead,
  UserAdminRead,
  UserProjectBrief,
} from '../../services/generated'

/** 积分流水类型 → 标签颜色映射，便于一眼区分充值/冻结/扣减/解冻。 */
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

/**
 * 流水时间格式化：沿用项目内 Intl.DateTimeFormat 的既定约定
 * （见 taskNotificationHelpers.tsx），避免引入 dayjs 依赖。
 */
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
 * 管理员用户详情页：展示用户信息、积分账户、积分充值与积分流水，
 * 以及该用户的项目列表。积分相关数据通过 generated AdminService 拉取。
 */
const AdminUserDetailPage: React.FC = () => {
  const { id = '' } = useParams()
  const [user, setUser] = useState<UserAdminRead | null>(null)
  const [projects, setProjects] = useState<UserProjectBrief[]>([])
  const [points, setPoints] = useState<PointsSummaryRead | null>(null)
  const [transactions, setTransactions] = useState<PointTransactionRead[]>([])
  const [txLoading, setTxLoading] = useState(false)
  const [txTotal, setTxTotal] = useState(0)
  const [txPage, setTxPage] = useState(1)
  const [txPageSize, setTxPageSize] = useState(10)
  const [recharging, setRecharging] = useState(false)
  const [form] = Form.useForm()
  const [rechargeForm] = Form.useForm()

  /** 一次性加载用户基础信息 + 项目 + 积分摘要（首屏）。 */
  const load = async () => {
    try {
      const [u, p, pts] = await Promise.all([
        AdminService.getUserApiV1AdminUsersUserIdGet({ userId: id }),
        AdminService.listUserProjectsApiV1AdminUsersUserIdProjectsGet({ userId: id }),
        AdminService.getUserPointsApiV1AdminUsersUserIdPointsGet({ userId: id }).catch(() => null),
      ])
      setUser(u.data ?? null)
      setProjects(p.data ?? [])
      setPoints(pts?.data ?? null)
    } catch {
      message.error('加载失败')
    }
  }

  /** 单独加载积分流水，按页拉取。 */
  const loadTransactions = async (page: number, pageSize: number) => {
    setTxLoading(true)
    try {
      const res = await AdminService.listUserPointsTransactionsApiV1AdminUsersUserIdPointsTransactionsGet({
        userId: id,
        page,
        pageSize,
      })
      setTransactions(res.data?.items ?? [])
      setTxTotal(res.data?.pagination?.total ?? 0)
    } catch {
      message.error('流水加载失败')
    } finally {
      setTxLoading(false)
    }
  }

  useEffect(() => {
    if (id) {
      void load()
      void loadTransactions(1, txPageSize)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  const resetPassword = async () => {
    const { password } = await form.validateFields()
    try {
      await AdminService.updateUserApiV1AdminUsersUserIdPatch({ userId: id, requestBody: { password } })
      message.success('密码已重置，该用户需重新登录')
      form.resetFields()
    } catch {
      message.error('重置失败')
    }
  }

  /**
   * 提交积分充值：正数为充值，负数为扣减。
   * 前端校验：负数时备注必填；金额为非零整数。
   */
  const handleRecharge = async () => {
    const values = await rechargeForm.validateFields()
    const amount = Number(values.amount)
    if (!Number.isInteger(amount) || amount === 0) {
      message.error('金额必须是非零整数')
      return
    }
    if (amount < 0 && !values.remark?.trim()) {
      message.error('扣减（负数）时备注必填')
      return
    }
    setRecharging(true)
    try {
      await AdminService.rechargeUserPointsApiV1AdminUsersUserIdPointsRechargePost({
        userId: id,
        requestBody: { amount, remark: values.remark?.trim() ? values.remark.trim() : null },
      })
      message.success(amount > 0 ? '充值成功' : '扣减成功')
      rechargeForm.resetFields()
      // 充值后刷新摘要与流水。
      const pts = await AdminService.getUserPointsApiV1AdminUsersUserIdPointsGet({ userId: id })
      setPoints(pts.data ?? null)
      await loadTransactions(1, txPageSize)
      setTxPage(1)
    } catch {
      message.error('充值失败')
    } finally {
      setRecharging(false)
    }
  }

  /** 积分流水表格列定义。 */
  const txColumns: TableColumnsType<PointTransactionRead> = [
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
    { title: '金额', dataIndex: 'amount', width: 80 },
    { title: '业务类型', dataIndex: 'business_type', render: (v) => v || '—' },
    { title: '模型', dataIndex: 'model_id', ellipsis: true, render: (v) => v || '—' },
    { title: '余额', dataIndex: 'balance_after', width: 80 },
    { title: '备注', dataIndex: 'remark', ellipsis: true, render: (v) => v || '—' },
    { title: '操作人', dataIndex: 'created_by', width: 100, render: (v) => v || '—' },
  ]

  return (
    <div className="flex flex-col gap-4">
      <Card title="用户信息">
        <Descriptions column={2}>
          <Descriptions.Item label="用户名">{user?.username}</Descriptions.Item>
          <Descriptions.Item label="角色">
            {user?.is_admin ? <Tag color="gold">管理员</Tag> : <Tag>成员</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            {user?.is_active ? <Tag color="green">启用</Tag> : <Tag color="red">禁用</Tag>}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 积分账户摘要 */}
      <Card title="积分账户">
        <Descriptions column={3}>
          <Descriptions.Item label="可用积分">{points?.available ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="冻结积分">{points?.frozen ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="总余额">{points?.balance ?? '—'}</Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 积分充值 / 扣减表单 */}
      <Card title="积分充值">
        <Form form={rechargeForm} layout="inline">
          <Form.Item
            name="amount"
            label="金额"
            rules={[
              { required: true, message: '请输入金额' },
              {
                validator: (_, value) => {
                  if (value === null || value === undefined) return Promise.resolve()
                  if (!Number.isInteger(Number(value))) return Promise.reject(new Error('必须为整数'))
                  if (Number(value) === 0) return Promise.reject(new Error('不可为 0'))
                  return Promise.resolve()
                },
              },
            ]}
          >
            <InputNumber min={undefined} step={1} precision={0} placeholder="正数充值/负数扣减" />
          </Form.Item>
          <Form.Item
            name="remark"
            label="备注"
            rules={[
              {
                validator: (_, value) => {
                  const amount = rechargeForm.getFieldValue('amount')
                  // 仅当金额为负整数时强制备注，正数可留空。
                  if (Number.isInteger(Number(amount)) && Number(amount) < 0 && !String(value ?? '').trim()) {
                    return Promise.reject(new Error('扣减（负数）时备注必填'))
                  }
                  return Promise.resolve()
                },
              },
            ]}
          >
            <Input.TextArea rows={1} placeholder="扣减时必填" className="w-64" />
          </Form.Item>
          <Button type="primary" loading={recharging} onClick={() => void handleRecharge()}>
            提交
          </Button>
        </Form>
        <div className="text-xs text-gray-400 mt-2">
          正数为充值，负数为扣减；扣减时备注必填且不得侵蚀冻结额。
        </div>
      </Card>

      {/* 积分流水，服务端分页 */}
      <Card title="积分流水">
        <Table<PointTransactionRead>
          rowKey="id"
          loading={txLoading}
          dataSource={transactions}
          columns={txColumns}
          size="small"
          pagination={{
            current: txPage,
            pageSize: txPageSize,
            total: txTotal,
            showSizeChanger: true,
            onChange: (page, pageSize) => {
              setTxPage(page)
              setTxPageSize(pageSize)
              void loadTransactions(page, pageSize)
            },
          }}
        />
      </Card>

      <Card title="重置密码">
        <Form form={form} layout="inline" onFinish={() => void resetPassword()}>
          <Form.Item name="password" rules={[{ required: true, min: 6, message: '至少 6 位' }]}>
            <Input.Password placeholder="新密码" />
          </Form.Item>
          <Button type="primary" htmlType="submit">重置</Button>
        </Form>
      </Card>

      <Card title="该用户的项目">
        <Table
          rowKey="id"
          dataSource={projects}
          pagination={false}
          columns={[
            { title: '项目 ID', dataIndex: 'id' },
            { title: '项目名', dataIndex: 'name' },
          ]}
        />
      </Card>
    </div>
  )
}

export default AdminUserDetailPage
