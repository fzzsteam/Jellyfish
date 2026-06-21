import { useEffect, useState } from 'react'
import type React from 'react'
import { Button, Card, Form, Input, Modal, Space, Switch, Table, Tag, message } from 'antd'
import { Link } from 'react-router-dom'
import { AdminService } from '../../services/generated'
import type { UserAdminRead } from '../../services/generated'
import { useAuthStore } from '../../store/useAuthStore'

/** 管理员用户列表页：展示全部用户，支持创建、启用/禁用、重置密码。 */
const AdminUserListPage: React.FC = () => {
  const [users, setUsers] = useState<UserAdminRead[]>([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm()

  // 当前登录管理员：用于在列表里禁用"重置自己"
  const authUser = useAuthStore((state) => state.user)
  // 重置成功后一次性展示的临时密码
  const [resetResult, setResetResult] = useState<{ username: string; temporary_password: string } | null>(null)
  // 正在重置中的用户 id，用于按钮 loading
  const [resettingId, setResettingId] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const res = await AdminService.listUsersApiV1AdminUsersGet({ page: 1, pageSize: 100 })
      setUsers(res.data?.items ?? [])
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
