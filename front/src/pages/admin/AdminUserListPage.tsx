import { useEffect, useState } from 'react'
import type React from 'react'
import { Button, Card, Form, Input, InputNumber, Modal, Space, Switch, Table, Tag, message } from 'antd'
import { Link } from 'react-router-dom'
import { AdminService } from '../../services/generated'
import type { PointsSummaryRead, UserAdminRead } from '../../services/generated'
import { useAuthStore } from '../../store/useAuthStore'
import { PointsBadge } from '../../components/points/PointsBadge'

/** 充值快捷金额选项。 */
const RECHARGE_PRESETS = [100, 500, 1000, 5000]

/** 管理员用户列表页：展示全部用户，支持创建、启用/禁用、重置密码。 */
const AdminUserListPage: React.FC = () => {
  const [users, setUsers] = useState<UserAdminRead[]>([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm()
  // 各用户积分摘要：key=userId，value=PointsSummaryRead。加载用户后并行拉取。
  const [pointsMap, setPointsMap] = useState<Record<string, PointsSummaryRead>>({})

  // 当前登录管理员：用于在列表里禁用"重置自己"
  const authUser = useAuthStore((state) => state.user)
  // 重置成功后一次性展示的临时密码
  const [resetResult, setResetResult] = useState<{ username: string; temporary_password: string } | null>(null)
  // 正在重置中的用户 id，用于按钮 loading
  const [resettingId, setResettingId] = useState<string | null>(null)
  // 充值弹窗目标用户
  const [rechargeTarget, setRechargeTarget] = useState<UserAdminRead | null>(null)
  const [rechargeForm] = Form.useForm<{ amount: number; remark: string }>()
  // 充值提交中
  const [recharging, setRecharging] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const res = await AdminService.listUsersApiV1AdminUsersGet({ page: 1, pageSize: 100 })
      const items = res.data?.items ?? []
      setUsers(items)
      // 并行拉取每个用户的积分摘要，失败不阻塞列表渲染。
      const results = await Promise.all(
        items.map((u) =>
          AdminService.getUserPointsApiV1AdminUsersUserIdPointsGet({ userId: u.id })
            .then((r) => r.data ?? null)
            .catch(() => null),
        ),
      )
      const next: Record<string, PointsSummaryRead> = {}
      items.forEach((u, i) => {
        const p = results[i]
        if (p) next[u.id] = p
      })
      setPointsMap(next)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const handleCreate = async () => {
    const values = await form.validateFields()
    try {
      await AdminService.createUserApiV1AdminUsersPost({ requestBody: values })
      message.success('用户已创建')
      setCreating(false)
      form.resetFields()
      void load()
    } catch {
      message.error('创建失败（用户名可能已存在）')
    }
  }

  const toggleActive = async (user: UserAdminRead) => {
    try {
      await AdminService.updateUserApiV1AdminUsersUserIdPatch({
        userId: user.id,
        requestBody: { is_active: !user.is_active },
      })
      void load()
    } catch {
      message.error('操作失败')
    }
  }

  const handleReset = (user: UserAdminRead) => {
    Modal.confirm({
      title: `重置「${user.username}」的密码？`,
      content: '将生成新的随机密码，该用户原密码立即失效。',
      okText: '重置',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        setResettingId(user.id)
        try {
          const res = await AdminService.resetPasswordApiV1AdminUsersUserIdResetPasswordPost({ userId: user.id })
          setResetResult({
            username: user.username,
            temporary_password: res.data?.temporary_password ?? '',
          })
          void load()
        } catch {
          message.error('重置失败')
        } finally {
          setResettingId(null)
        }
      },
    })
  }

  const handleRecharge = async () => {
    const values = await rechargeForm.validateFields()
    setRecharging(true)
    try {
      await AdminService.rechargeUserPointsApiV1AdminUsersUserIdPointsRechargePost({
        userId: rechargeTarget!.id,
        requestBody: { amount: values.amount, remark: values.remark ?? null },
      })
      message.success(`已为「${rechargeTarget!.username}」${values.amount >= 0 ? '充值' : '扣减'} ${Math.abs(values.amount)} 积分`)
      // 刷新该用户积分摘要
      const res = await AdminService.getUserPointsApiV1AdminUsersUserIdPointsGet({ userId: rechargeTarget!.id }).catch(() => null)
      if (res?.data) {
        setPointsMap((prev) => ({ ...prev, [rechargeTarget!.id]: res.data! }))
      }
      setRechargeTarget(null)
      rechargeForm.resetFields()
    } catch (err: unknown) {
      const detail = (err as { body?: { detail?: string } })?.body?.detail
      message.error(typeof detail === 'string' ? detail : '操作失败')
    } finally {
      setRecharging(false)
    }
  }

  const copyTempPassword = async () => {
    if (!resetResult) return
    try {
      await navigator.clipboard.writeText(resetResult.temporary_password)
      message.success('已复制到剪贴板')
    } catch {
      message.error('复制失败，请手动选择复制')
    }
  }

  const columns = [
    {
      title: '用户名',
      dataIndex: 'username',
      render: (_: string, u: UserAdminRead) => <Link to={`/admin/users/${u.id}`}>{u.username}</Link>,
    },
    {
      title: '角色',
      dataIndex: 'is_admin',
      render: (v: boolean) => (v ? <Tag color="gold">管理员</Tag> : <Tag>成员</Tag>),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      render: (v: boolean) => (v ? <Tag color="green">启用</Tag> : <Tag color="red">禁用</Tag>),
    },
    {
      // 积分摘要列：可用/冻结；尚未加载到时显示 '—'。
      title: '积分(可用/冻结)',
      key: 'points',
      render: (_: unknown, u: UserAdminRead) => {
        const p = pointsMap[u.id]
        if (!p) return <span className="text-gray-400">—</span>
        return (
          <span className="inline-flex items-center gap-1.5">
            <PointsBadge value={p.available} size="sm" />
            <span className="text-gray-300">/</span>
            <span className={`text-xs font-medium ${p.frozen > 0 ? 'text-orange-400' : 'text-gray-400'}`}>
              {p.frozen.toLocaleString()}
            </span>
          </span>
        )
      },
    },
    {
      title: '操作',
      render: (_: unknown, u: UserAdminRead) => {
        // 自己不能在列表里重置密码，应走右上角自助改密
        const isSelf = u.id === authUser?.id
        return (
          <Space>
            <Switch
              checked={u.is_active}
              onChange={() => void toggleActive(u)}
              disabled={isSelf}
              checkedChildren="启用"
              unCheckedChildren="禁用"
              title={isSelf ? '不能操作自己的账号' : undefined}
            />
            <Button
              size="small"
              disabled={isSelf}
              loading={resettingId === u.id}
              onClick={() => handleReset(u)}
              title={isSelf ? '请通过右上角修改自己的密码' : undefined}
            >
              重置密码
            </Button>
            <Button size="small" onClick={() => { setRechargeTarget(u); rechargeForm.resetFields() }}>
              充值积分
            </Button>
          </Space>
        )
      },
    },
  ]

  return (
    <Card title="用户管理" extra={<Button type="primary" onClick={() => setCreating(true)}>创建用户</Button>}>
      <Table rowKey="id" loading={loading} columns={columns} dataSource={users} />
      <Modal
        title="创建用户"
        open={creating}
        onOk={() => void handleCreate()}
        onCancel={() => setCreating(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="password" label="初始密码" rules={[{ required: true, min: 6, message: '至少 6 位' }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="is_admin" label="管理员" valuePropName="checked" initialValue={false}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* 充值积分弹窗：允许正负整数，负数必须填备注 */}
      <Modal
        title={`充值积分 — ${rechargeTarget?.username ?? ''}`}
        open={!!rechargeTarget}
        onOk={() => void handleRecharge()}
        onCancel={() => { setRechargeTarget(null); rechargeForm.resetFields() }}
        okText="确认"
        cancelText="取消"
        confirmLoading={recharging}
        destroyOnClose
      >
        <Form form={rechargeForm} layout="vertical" className="mt-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-sm text-gray-500">快捷：</span>
            {RECHARGE_PRESETS.map((preset) => (
              <Button
                key={preset}
                size="small"
                onClick={() => rechargeForm.setFieldValue('amount', preset)}
              >
                +{preset}
              </Button>
            ))}
          </div>
          <Form.Item
            name="amount"
            label="积分数量（正数充值，负数扣减）"
            rules={[
              { required: true, message: '请输入积分数量' },
              { type: 'integer', message: '请输入整数' },
              {
                validator: (_, value) => value !== 0 ? Promise.resolve() : Promise.reject(new Error('不能为 0')),
              },
            ]}
          >
            <InputNumber style={{ width: '100%' }} placeholder="如：100 或 -50" />
          </Form.Item>
          <Form.Item
            name="remark"
            label="备注"
            rules={[
              ({ getFieldValue }) => ({
                validator(_, value) {
                  const amount = getFieldValue('amount') as number
                  if (amount < 0 && !value?.trim()) {
                    return Promise.reject(new Error('扣减积分必须填写备注'))
                  }
                  return Promise.resolve()
                },
              }),
            ]}
          >
            <Input placeholder="说明充值/扣减原因（扣减时必填）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 重置结果：临时密码仅展示一次，需立即复制 */}
      <Modal
        title="重置成功"
        open={!!resetResult}
        onCancel={() => setResetResult(null)}
        onOk={() => setResetResult(null)}
        okText="我已复制"
        cancelText="关闭"
      >
        <p className="mb-2">
          <strong>{resetResult?.username}</strong> 的新临时密码（仅显示一次，请立即复制）：
        </p>
        <Space.Compact style={{ width: '100%' }}>
          <Input.Password value={resetResult?.temporary_password ?? ''} readOnly />
          <Button onClick={() => void copyTempPassword()}>复制</Button>
        </Space.Compact>
      </Modal>
    </Card>
  )
}

export default AdminUserListPage
