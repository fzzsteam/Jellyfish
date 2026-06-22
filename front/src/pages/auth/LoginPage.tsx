import { useState } from 'react'
import type React from 'react'
import { Button, Card, Form, Input, message } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { useNavigate, useLocation, type Location } from 'react-router-dom'
import { useAuthStore } from '../../store/useAuthStore'

interface LoginFormValues {
  username: string
  password: string
}

const LoginPage: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const login = useAuthStore((state) => state.login)
  const [submitting, setSubmitting] = useState(false)

  const handleFinish = async (values: LoginFormValues) => {
    setSubmitting(true)
    try {
      await login(values.username, values.password)
      const from = (location.state as { from?: Location } | null)?.from?.pathname ?? '/projects'
      navigate(from, { replace: true })
    } catch {
      message.error('用户名或密码错误')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex items-center justify-center h-screen bg-gray-50">
      <Card title="Jellyfish 登录" style={{ width: 360 }}>
        <Form layout="vertical" onFinish={handleFinish}>
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" autoComplete="current-password" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={submitting}>
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}

export default LoginPage
