import type React from 'react'
import { useEffect } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { Spin } from 'antd'
import { useAuthStore } from '../store/useAuthStore'

const PrivateRoute: React.FC = () => {
  const status = useAuthStore((state) => state.status)
  const initialize = useAuthStore((state) => state.initialize)
  const location = useLocation()

  useEffect(() => {
    if (status === 'idle') {
      void initialize()
    }
  }, [status, initialize])

  if (status === 'idle') {
    return (
      <div className="flex items-center justify-center h-screen">
        <Spin size="large" />
      </div>
    )
  }

  if (status === 'unauthenticated') {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <Outlet />
}

export default PrivateRoute
