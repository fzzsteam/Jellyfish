import type React from 'react'
import { useEffect } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { Spin } from 'antd'
import { useAuthStore } from '../store/useAuthStore'

/**
 * 管理员路由守卫：在 PrivateRoute 已保证登录的基础上，进一步要求 is_admin。
 * 存在意义：把"管理页仅管理员可见"的访问控制收敛到一处，避免每个管理页各自判断。
 * - status === 'idle' 时尝试恢复会话，期间 loading
 * - 未登录跳 /login；已登录但非管理员跳首页 /projects
 */
const AdminRoute: React.FC = () => {
  const status = useAuthStore((state) => state.status)
  const user = useAuthStore((state) => state.user)
  const initialize = useAuthStore((state) => state.initialize)

  useEffect(() => {
    if (status === 'idle') void initialize()
  }, [status, initialize])

  if (status === 'idle') {
    return (
      <div className="flex items-center justify-center h-screen">
        <Spin size="large" />
      </div>
    )
  }
  if (status === 'unauthenticated') {
    return <Navigate to="/login" replace />
  }
  if (!user?.is_admin) {
    return <Navigate to="/projects" replace />
  }
  return <Outlet />
}

export default AdminRoute
