import { useEffect, useState } from 'react'
import type React from 'react'
import { Button, Card, Form, Input, Modal, Switch, Table, Tag, message } from 'antd'
import { Link } from 'react-router-dom'
import { AdminService } from '../../services/generated'
import type { UserAdminRead } from '../../services/generated'

/** 管理员用户列表页：展示全部用户，支持创建与启用/禁用。 */
const AdminUserListPage: React.FC = () => {
  const [users, setUsers] = useState<UserAdminRead[]>([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm()

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
      render: (_: unknown, u: UserAdminRead) => (
        <Switch
          checked={u.is_active}
          onChange={() => void toggleActive(u)}
          checkedChildren="启用"
          unCheckedChildren="禁用"
        />
      ),
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
    </Card>
  )
}

export default AdminUserListPage
