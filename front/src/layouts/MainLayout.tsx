import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Badge, Layout, Menu, theme, Dropdown, Space, Avatar, Button } from 'antd'
import {
  UserOutlined,
  FolderOutlined,
  PictureOutlined,
  FileTextOutlined,
  ApiOutlined,
  TeamOutlined,
  WalletOutlined,
  LoadingOutlined,
  QuestionCircleOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons'
import { PointsBadge } from '../components/points/PointsBadge'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAppStore } from '../store/useAppStore'
import { useAuthStore } from '../store/useAuthStore'
import { useTranslation } from 'react-i18next'
import ChangePasswordModal from '../components/ChangePasswordModal'
import { FilmService, PointsService } from '../services/generated'
import type { PointsSummaryRead } from '../services/generated'
import { useTaskUiStore } from '../pages/aiStudio/components/taskUiStore'
import { ACTIVE_TASK_STATUSES } from '../pages/tasks/taskStatusConfig'

const { Header, Sider, Content } = Layout
/** 左侧菜单任务数量刷新间隔，仅在存在进行中任务时启用。 */
const TASK_MENU_ACTIVE_COUNT_POLL_INTERVAL_MS = 5000

const MainLayout: React.FC = () => {
  const { t } = useTranslation('layout')
  const location = useLocation()
  const navigate = useNavigate()
  const { token } = theme.useToken()

  const collapsed = useAppStore((state) => state.siderCollapsed)
  const authUser = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)
  const [passwordOpen, setPasswordOpen] = useState(false)
  // 积分摘要：hover 头像下拉时实时拉取一次，避免常驻顶栏的数据陈旧问题。
  const [points, setPoints] = useState<PointsSummaryRead | null>(null)
  const [pointsLoading, setPointsLoading] = useState(false)
  const [serverActiveTaskCount, setServerActiveTaskCount] = useState(0)
  const optimisticActiveTaskCount = useTaskUiStore((state) =>
    Object.values(state.optimisticItems).filter((task) => ACTIVE_TASK_STATUSES.includes(task.status)).length,
  )
  const activeTaskCount = Math.max(serverActiveTaskCount, optimisticActiveTaskCount)

  const selectedKeys = useMemo(() => {
    if (location.pathname === '/projects' || location.pathname.startsWith('/projects/')) return ['projects']
    if (location.pathname.startsWith('/assets')) return ['assets']
    if (location.pathname.startsWith('/prompts')) return ['prompts']
    if (location.pathname.startsWith('/files')) return ['files']
    if (location.pathname.startsWith('/agents')) return ['agents']
    if (location.pathname.startsWith('/models')) return ['models']
    if (location.pathname.startsWith('/points')) return ['points']
    if (location.pathname.startsWith('/tasks')) return ['tasks']
    if (location.pathname.startsWith('/admin')) return ['admin-users']
    return []
  }, [location.pathname])

  useEffect(() => {
    if (!authUser) setPoints(null)
  }, [authUser])

  const loadActiveTaskCount = useCallback(async () => {
    if (!authUser) {
      setServerActiveTaskCount(0)
      return
    }
    try {
      const response = await FilmService.listTasksApiV1FilmTasksGet({
        statuses: ACTIVE_TASK_STATUSES,
        recentSeconds: undefined,
        page: 1,
        pageSize: 1,
      })
      setServerActiveTaskCount(response.data?.pagination?.total ?? 0)
    } catch {
      setServerActiveTaskCount(0)
    }
  }, [authUser])

  useEffect(() => {
    void loadActiveTaskCount()
  }, [loadActiveTaskCount, location.pathname, optimisticActiveTaskCount])

  useEffect(() => {
    if (!authUser || activeTaskCount <= 0) return
    const timer = window.setInterval(() => {
      void loadActiveTaskCount()
    }, TASK_MENU_ACTIVE_COUNT_POLL_INTERVAL_MS)
    return () => {
      window.clearInterval(timer)
    }
  }, [activeTaskCount, authUser, loadActiveTaskCount])

  const handleUserDropdownOpenChange = (open: boolean) => {
    if (!open || !authUser) return
    setPointsLoading(true)
    PointsService.getMyPointsApiV1PointsMeGet({})
      .then((r) => setPoints(r.data ?? null))
      .catch(() => setPoints(null))
      .finally(() => setPointsLoading(false))
  }

  // 从 URL 提取项目上下文，用于顶部导航按钮
  const pathSegments = useMemo(
    () => location.pathname.replace(/^\/+/, '').split('/').filter(Boolean),
    [location.pathname],
  )
  const urlProjectId = useMemo(
    () => (pathSegments[0] === 'projects' && pathSegments[1] ? pathSegments[1] : null),
    [pathSegments],
  )

  // 当前激活的导航项。
  const activeNav = useMemo(() => {
    if (!urlProjectId) return 'home'
    return 'workbench'
  }, [urlProjectId])

  // 用 React state 跟踪 hover，避免直接操作 DOM style 导致导航后残留背景色
  const [hoveredNavKey, setHoveredNavKey] = useState<string | null>(null)
  // 导航发生时（activeNav 变化）清除 hover 残留
  const prevActiveNavRef = useRef(activeNav)
  useEffect(() => {
    if (prevActiveNavRef.current !== activeNav) {
      prevActiveNavRef.current = activeNav
      setHoveredNavKey(null)
    }
  }, [activeNav])

  const navItems = useMemo(() => [
    {
      key: 'home',
      label: '主页面',
      path: '/projects',
      visible: true,
      enabled: true,
    },
    {
      key: 'workbench',
      label: '项目工作台',
      path: urlProjectId ? `/projects/${urlProjectId}` : null,
      visible: !!urlProjectId,
      enabled: !!urlProjectId,
    },
  ], [urlProjectId])

  const menuItems = [
    {
      key: 'projects',
      icon: <FolderOutlined />,
      label: <Link to="/projects">项目列表</Link>,
    },
    {
      key: 'assets',
      icon: <PictureOutlined />,
      label: <Link to="/assets">资产管理</Link>,
    },
    {
      key: 'tasks',
      icon: <UnorderedListOutlined />,
      label: (
        <Link to="/tasks" className="flex items-center justify-between gap-2">
          <span>任务中心</span>
          {activeTaskCount > 0 ? <Badge count={activeTaskCount} size="small" overflowCount={99} /> : null}
        </Link>
      ),
    },
    {
      key: 'prompts',
      icon: <FileTextOutlined />,
      label: <Link to="/prompts">提示词模板</Link>,
    },
    {
      key: 'models',
      icon: <ApiOutlined />,
      label: <Link to="/models">模型管理</Link>,
    },
    {
      key: 'points',
      icon: <WalletOutlined />,
      label: <Link to="/points">积分明细</Link>,
    },
  ]

  // 仅管理员可见"用户管理"入口；末尾条件追加，避免影响非管理员的菜单。
  if (authUser?.is_admin) {
    menuItems.push({
      key: 'admin-users',
      icon: <TeamOutlined />,
      label: <Link to="/admin/users">用户管理</Link>,
    })
  }

  const userMenuItems = [
    {
      key: 'points-summary',
      disabled: true,
      label: (
        <div className="py-1 flex items-center gap-2 min-w-[140px]">
          {pointsLoading ? (
            <span className="text-gray-400 text-xs flex items-center gap-1.5">
              <LoadingOutlined spin /> 加载积分…
            </span>
          ) : points ? (
            <div className="flex flex-col gap-0.5">
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-gray-400 w-8">可用</span>
                <PointsBadge value={points.available} size="sm" />
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-gray-400 w-8">冻结</span>
                <PointsBadge value={points.frozen} size="sm" />
              </div>
            </div>
          ) : (
            <span className="text-gray-400 text-xs">积分暂不可用</span>
          )}
        </div>
      ),
    },
    {
      type: 'divider' as const,
    },
    {
      key: 'change-password',
      label: t('user.changePassword'),
      onClick: () => setPasswordOpen(true),
    },
    {
      type: 'divider' as const,
    },
    {
      key: 'logout',
      label: t('user.logout'),
      onClick: () => {
        logout()
        navigate('/login')
      },
    },
  ]

  return (
    <Layout
      style={{
        height: '100vh',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'row',
      }}
    >
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        width={220}
        style={{
          flexShrink: 0,
          background: token.colorBgContainer,
          borderRight: `1px solid ${token.colorBorderSecondary}`,
          overflow: 'auto',
        }}
      >
        <div className="flex items-center h-16 px-4 border-b border-solid" style={{ borderColor: token.colorBorderSecondary }}>
          <Link to="/projects" className="flex items-center gap-2 min-w-0">
            <img src="/logo-wanxiang.png" alt="万象元生" className="w-12 h-12 shrink-0 rounded-full" />
            {!collapsed && (
              <div className="min-w-0">
                <div className="text-base font-semibold text-gray-900 truncate">
                  {t('title')}
                </div>
                <div className="text-xs text-gray-500 truncate">
                  {t('subtitle')}
                </div>
              </div>
            )}
          </Link>
        </div>

        <Menu
          mode="inline"
          selectedKeys={selectedKeys}
          items={menuItems}
          style={{ borderRight: 'none', paddingTop: 8 }}
        />
      </Sider>

      <Layout
        style={{
          flex: 1,
          minWidth: 0,
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
        }}
      >
        <Header
          className="flex items-center"
          style={{
            flexShrink: 0,
            background: token.colorBgContainer,
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            padding: 0,
          }}
        >
          {/* 项目级导航按钮
              - 仅保留"主页面"与"项目工作台"两项
              - 使用固定宽度按钮；visible=false 时用 visibility:hidden 保留占位
              - enabled=false 时置灰不可点击（进度锁定效果）
          */}
          <div className="flex-1 flex items-stretch h-full">
            {navItems.map(({ key, label, path, visible, enabled }) => {
              const isActive = activeNav === key
              const isHovered = hoveredNavKey === key && enabled && !isActive
              return (
                <button
                  key={key}
                  onClick={() => {
                    if (enabled && path) navigate(path)
                  }}
                  onMouseEnter={() => setHoveredNavKey(key)}
                  onMouseLeave={() => setHoveredNavKey(null)}
                  style={{
                    flex: 1,
                    border: 'none',
                    // 所有背景色均由 React state 驱动，不直接操作 DOM，
                    // 确保导航后 re-render 时旧按钮背景色正确归零
                    background: isHovered ? token.colorBgTextHover : 'transparent',
                    borderBottom: isActive ? `2px solid ${token.colorPrimary}` : '2px solid transparent',
                    color: isActive
                      ? token.colorPrimary
                      : !enabled
                      ? token.colorTextDisabled
                      : isHovered
                      ? token.colorText
                      : token.colorTextSecondary,
                    fontWeight: isActive ? 600 : 400,
                    fontSize: 14,
                    cursor: enabled ? 'pointer' : 'not-allowed',
                    transition: 'all 0.2s',
                    whiteSpace: 'nowrap',
                    // 不可见时保留占位空间，避免项目级导航按钮宽度跳变
                    visibility: visible ? 'visible' : 'hidden',
                  }}
                >
                  {label}
                </button>
              )
            })}
          </div>

          {/* 全局帮助入口与用户信息 */}
          <Space size={8} className="px-4 shrink-0">
            <Button
              type="text"
              icon={<QuestionCircleOutlined />}
              href="/guide"
              target="_blank"
              rel="noreferrer"
              className="hidden sm:inline-flex items-center"
            >
              操作指引
            </Button>
            <Button
              type="text"
              icon={<QuestionCircleOutlined />}
              href="/guide"
              target="_blank"
              rel="noreferrer"
              className="sm:hidden"
              aria-label="操作指引"
            />
            <Dropdown
              menu={{ items: userMenuItems }}
              placement="bottomRight"
              trigger={['hover']}
              onOpenChange={handleUserDropdownOpenChange}
            >
              <div className="flex items-center gap-2 cursor-pointer">
                <Avatar size={32} icon={<UserOutlined />} />
                <div className="hidden md:flex flex-col leading-tight">
                  <span className="text-sm font-medium text-gray-800">{authUser?.username}</span>
                  <span className="text-xs text-gray-500">{authUser?.is_admin ? '管理员' : '成员'}</span>
                </div>
              </div>
            </Dropdown>
          </Space>
        </Header>

        <Content
          style={{
            margin: 0,
            padding: 5,
            background: token.colorBgLayout,
            flex: 1,
            minHeight: 0,
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div className="w-full h-full min-h-0 overflow-hidden flex flex-col">
            <Outlet />
          </div>
        </Content>
        <ChangePasswordModal open={passwordOpen} onClose={() => setPasswordOpen(false)} />
      </Layout>
    </Layout>
  )
}

export default MainLayout
