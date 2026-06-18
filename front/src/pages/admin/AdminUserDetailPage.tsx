import { useEffect, useState } from 'react'
import type React from 'react'
import { Button, Card, Descriptions, Form, Input, Table, Tag, message } from 'antd'
import { useParams } from 'react-router-dom'
import { AdminService } from '../../services/generated'
import type { UserAdminRead, UserProjectBrief } from '../../services/generated'

/** 管理员用户详情页：展示用户信息、重置密码、查看其项目列表。 */
const AdminUserDetailPage: React.FC = () => {
  const { id = '' } = useParams()
  const [user, setUser] = useState<UserAdminRead | null>(null)
  const [projects, setProjects] = useState<UserProjectBrief[]>([])
  const [form] = Form.useForm()

  const load = async () => {
    const [u, p] = await Promise.all([
      AdminService.getUserApiV1AdminUsersUserIdGet({ userId: id }),
      AdminService.listUserProjectsApiV1AdminUsersUserIdProjectsGet({ userId: id }),
    ])
    setUser(u.data ?? null)
    setProjects(p.data ?? [])
  }

  useEffect(() => {
    if (id) void load()
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
