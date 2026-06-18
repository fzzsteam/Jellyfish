import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Layout, Menu, theme, Dropdown, Space, Avatar } from 'antd'
import {
  SettingOutlined,
  UserOutlined,
  FolderOutlined,
  PictureOutlined,
  FileTextOutlined,
} from '@ant-design/icons'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAppStore } from '../store/useAppStore'
import { useTranslation } from 'react-i18next'
import { TaskCenter } from '../pages/aiStudio/components/TaskCenter'
import { TaskRuntimeProvider } from '../pages/aiStudio/components/TaskRuntimeProvider'

const { Header, Sider, Content } = Layout

const MainLayout: React.FC = () => {
  const { t } = useTranslation('layout')
  const location = useLocation()
  const navigate = useNavigate()
  const { token } = theme.useToken()

  const collapsed = useAppStore((state) => state.siderCollapsed)
  const user = useAppStore((state) => state.user)

  const selectedKeys = useMemo(() => {
    if (location.pathname === '/projects' || location.pathname.startsWith('/projects/')) return ['projects']
    if (location.pathname.startsWith('/assets')) return ['assets']
    if (location.pathname.startsWith('/prompts')) return ['prompts']
    if (location.pathname.startsWith('/files')) return ['files']
    if (location.pathname.startsWith('/agents')) return ['agents']
    if (location.pathname.startsWith('/settings')) return ['settings']
    return []
  }, [location.pathname])

  // 从 URL 提取项目 / 章节上下文，用于顶部导航按钮
  const pathSegments = useMemo(
    () => location.pathname.replace(/^\/+/, '').split('/').filter(Boolean),
    [location.pathname],
  )
  const urlProjectId = useMemo(
    () => (pathSegments[0] === 'projects' && pathSegments[1] ? pathSegments[1] : null),
    [pathSegments],
  )
  const urlChapterId = useMemo(
    () => (pathSegments[2] === 'chapters' && pathSegments[3] ? pathSegments[3] : null),
    [pathSegments],
  )

  // 当前激活的导航项
  const activeNav = useMemo(() => {
    if (!urlProjectId) return 'home'
    if (!urlChapterId) return 'workbench'
    const section = pathSegments[4]
    if (section === 'studio') return 'studio'
    if (section === 'shots') return 'shots'
    return 'workbench'
  }, [urlProjectId, urlChapterId, pathSegments])

  // 持久化记录每个项目最后访问的 chapterId。
  // 一旦某项目到达过章节页，后续在项目任意页面均可直接跳转到分镜列表/工作室。
  const [storedChapterId, setStoredChapterId] = useState<string | null>(() => {
    const segs = location.pathname.replace(/^\/+/, '').split('/').filter(Boolean)
    const pid = segs[0] === 'projects' && segs[1] ? segs[1] : null
    if (!pid) return null
    return localStorage.getItem(`nav_lastChapterId_${pid}`)
  })

  useEffect(() => {
    if (urlProjectId && urlChapterId) {
      localStorage.setItem(`nav_lastChapterId_${urlProjectId}`, urlChapterId)
      setStoredChapterId(urlChapterId)
    } else if (urlProjectId) {
      setStoredChapterId(localStorage.getItem(`nav_lastChapterId_${urlProjectId}`))
    } else {
      setStoredChapterId(null)
    }
  }, [urlProjectId, urlChapterId])

  // 导航时优先用 URL 里的 chapterId，否则回退到上次访问记录
  const effectiveChapterId = urlChapterId ?? storedChapterId

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

  const navItems = useMemo(() => {
    const shotsPath =
      urlProjectId && effectiveChapterId
        ? `/projects/${urlProjectId}/chapters/${effectiveChapterId}/shots`
        : null
    const studioPath =
      urlProjectId && effectiveChapterId
        ? `/projects/${urlProjectId}/chapters/${effectiveChapterId}/studio`
        : null

    return [
      {
        key: 'home',
        label: '主页面',
        path: '/projects',
        // 始终可见、始终可用
        visible: true,
        enabled: true,
      },
      {
        key: 'workbench',
        label: '项目工作台',
        path: urlProjectId ? `/projects/${urlProjectId}` : null,
        // 有项目上下文才显示，进入项目后即解锁
        visible: !!urlProjectId,
        enabled: !!urlProjectId,
      },
      {
        key: 'shots',
        label: '分镜列表',
        path: shotsPath,
        // 有项目上下文才显示；曾到达过章节层级才可用（effectiveChapterId 有值）
        visible: !!urlProjectId,
        enabled: !!effectiveChapterId,
      },
      {
        key: 'studio',
        label: '分镜工作室',
        path: studioPath,
        visible: !!urlProjectId,
        enabled: !!effectiveChapterId,
      },
    ]
  }, [urlProjectId, effectiveChapterId])

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
      key: 'prompts',
      icon: <FileTextOutlined />,
      label: <Link to="/prompts">提示词模板</Link>,
    },
    {
      key: 'settings',
      icon: <SettingOutlined />,
      label: <Link to="/settings">{t('menu.settings')}</Link>,
    },
  ]

  const userMenuItems = [
    {
      key: 'profile',
      label: t('user.profile'),
      onClick: () => navigate('/settings'),
    },
    {
      type: 'divider' as const,
    },
    {
      key: 'logout',
      label: t('user.logout'),
      onClick: () => {
        // 这里保留占位，实际项目中可接入登录逻辑
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
        <div className="flex h-16 items-center px-4 border-b border-solid" style={{ borderColor: token.colorBorderSecondary }}>
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
          style={{ borderRight: 'none', paddingTop: 0 }}
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
          {/* 四个等距导航按钮
              - visible=false 时用 visibility:hidden 占位，保证按钮始终保持等宽
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
                    // 不可见时保留占位空间，让"主页面"始终维持 1/4 宽度
                    visibility: visible ? 'visible' : 'hidden',
                  }}
                >
                  {label}
                </button>
              )
            })}
          </div>

          {/* 用户信息 */}
          <Space size="middle" className="px-4 shrink-0">
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
              <div className="flex items-center gap-2 cursor-pointer">
                <Avatar size={32} icon={<UserOutlined />} />
                <div className="hidden md:flex flex-col leading-tight">
                  <span className="text-sm font-medium text-gray-800">{user.name}</span>
                  <span className="text-xs text-gray-500">{user.role}</span>
                </div>
              </div>
            </Dropdown>
          </Space>
        </Header>

        <TaskRuntimeProvider>
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
          <TaskCenter />
        </TaskRuntimeProvider>
      </Layout>
    </Layout>
  )
}

export default MainLayout
