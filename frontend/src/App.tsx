import { useEffect, useState } from 'react'
import { BrowserRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { App as AntdApp, Button, ConfigProvider, Layout, Menu, Spin } from 'antd'
import {
  DashboardOutlined,
  GlobalOutlined,
  HistoryOutlined,
  InboxOutlined,
  LogoutOutlined,
  MoonOutlined,
  PlayCircleOutlined,
  SettingOutlined,
  SunOutlined,
  UserOutlined,
} from '@ant-design/icons'
import zhCN from 'antd/locale/zh_CN'

import Accounts from '@/pages/Accounts'
import Dashboard from '@/pages/Dashboard'
import Login from '@/pages/Login'
import MailRecoveryPool from '@/pages/MailRecoveryPool'
import Proxies from '@/pages/Proxies'
import RegisterTaskPage from '@/pages/RegisterTaskPage'
import Settings from '@/pages/Settings'
import TaskHistory from '@/pages/TaskHistory'
import { apiFetch, clearToken, getToken } from '@/lib/utils'

import { darkTheme, lightTheme } from './theme'

const { Content, Sider } = Layout

function ProtectedLayout() {
  const navigate = useNavigate()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    fetch('/api/auth/status')
      .then((response) => response.json())
      .then((status) => {
        const token = getToken()
        if (status.has_password && !token) {
          navigate('/login', { replace: true })
          return
        }
        setReady(true)
      })
      .catch(() => setReady(true))
  }, [navigate])

  if (!ready) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin size="large" />
      </div>
    )
  }

  return <AppContent />
}

function AppContent() {
  const [themeMode, setThemeMode] = useState<'dark' | 'light'>(() =>
    (localStorage.getItem('theme') as 'dark' | 'light') || 'dark',
  )
  const [collapsed, setCollapsed] = useState(false)
  const [platforms, setPlatforms] = useState<{ key: string; label: string }[]>([])
  const [hasPassword, setHasPassword] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()

  useEffect(() => {
    document.documentElement.classList.toggle('light', themeMode === 'light')
    document.documentElement.style.setProperty(
      '--sider-trigger-border',
      themeMode === 'light' ? 'rgba(0,0,0,0.1)' : 'rgba(255,255,255,0.15)',
    )
    localStorage.setItem('theme', themeMode)
  }, [themeMode])

  useEffect(() => {
    fetch('/api/auth/status')
      .then((response) => response.json())
      .then((status) => setHasPassword(status.has_password))
      .catch(() => {})
  }, [])

  useEffect(() => {
    apiFetch('/platforms')
      .then((data) => setPlatforms(
        (data || [])
          .filter((platform: any) => !['tavily', 'cursor'].includes(platform.name))
          .map((platform: any) => ({ key: platform.name, label: platform.display_name })),
      ))
      .catch(() => {})
  }, [])

  const isLight = themeMode === 'light'
  const currentTheme = isLight ? lightTheme : darkTheme

  const getSelectedKey = () => {
    const path = location.pathname
    if (path === '/') return ['/']
    if (path === '/register') return ['/register']
    if (path.startsWith('/accounts')) return [path]
    if (path === '/history') return ['/history']
    if (path === '/proxies') return ['/proxies']
    if (path === '/mail-recovery') return ['/mail-recovery']
    if (path === '/settings') return ['/settings']
    return ['/']
  }

  const menuItems = [
    {
      key: '/',
      icon: <DashboardOutlined />,
      label: '仪表盘',
    },
    {
      key: '/register',
      icon: <PlayCircleOutlined />,
      label: '注册任务',
    },
    {
      key: '/accounts',
      icon: <UserOutlined />,
      label: '平台管理',
      children: platforms.map((platform) => ({
        key: `/accounts/${platform.key}`,
        label: platform.label,
      })),
    },
    {
      key: '/history',
      icon: <HistoryOutlined />,
      label: '任务历史',
    },
    {
      key: '/proxies',
      icon: <GlobalOutlined />,
      label: '代理管理',
    },
    {
      key: '/mail-recovery',
      icon: <InboxOutlined />,
      label: '微软恢复池',
    },
    {
      key: '/settings',
      icon: <SettingOutlined />,
      label: '全局配置',
    },
  ]

  return (
    <ConfigProvider theme={currentTheme} locale={zhCN}>
      <AntdApp>
        <Layout style={{ minHeight: '100vh' }}>
          <Sider
            collapsible
            collapsed={collapsed}
            onCollapse={setCollapsed}
            style={{
              background: currentTheme.token?.colorBgContainer,
              borderRight: `1px solid ${currentTheme.token?.colorBorder}`,
            }}
            width={220}
          >
            <div
              style={{
                height: 64,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderBottom: `1px solid ${currentTheme.token?.colorBorder}`,
              }}
            >
              <DashboardOutlined style={{ fontSize: 20, color: currentTheme.token?.colorPrimary }} />
              {!collapsed && (
                <span
                  style={{
                    marginLeft: 8,
                    fontWeight: 600,
                    fontSize: 14,
                    color: currentTheme.token?.colorText,
                  }}
                >
                  Account Manager
                </span>
              )}
            </div>
            <Menu
              mode="inline"
              selectedKeys={getSelectedKey()}
              defaultOpenKeys={['/accounts']}
              items={menuItems}
              onClick={({ key }) => navigate(key)}
              style={{
                borderRight: 0,
                background: 'transparent',
              }}
            />
            <div
              style={{
                position: 'absolute',
                bottom: 56,
                left: 0,
                right: 0,
                padding: '0 16px',
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
              }}
            >
              <Button
                block
                icon={isLight ? <SunOutlined /> : <MoonOutlined />}
                onClick={() => setThemeMode(isLight ? 'dark' : 'light')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: collapsed ? 'center' : 'space-between',
                }}
              >
                {!collapsed && (isLight ? '亮色模式' : '暗色模式')}
              </Button>
              {hasPassword && (
                <Button
                  block
                  danger
                  icon={<LogoutOutlined />}
                  onClick={() => {
                    clearToken()
                    navigate('/login')
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: collapsed ? 'center' : 'space-between',
                  }}
                >
                  {!collapsed && '退出登录'}
                </Button>
              )}
            </div>
          </Sider>
          <Content
            style={{
              padding: 24,
              overflow: 'auto',
              background: currentTheme.token?.colorBgLayout,
            }}
          >
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/accounts" element={<Accounts />} />
              <Route path="/accounts/:platform" element={<Accounts />} />
              <Route path="/register" element={<RegisterTaskPage />} />
              <Route path="/history" element={<TaskHistory />} />
              <Route path="/proxies" element={<Proxies />} />
              <Route path="/mail-recovery" element={<MailRecoveryPool />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </Content>
        </Layout>
      </AntdApp>
    </ConfigProvider>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/*" element={<ProtectedLayout />} />
      </Routes>
    </BrowserRouter>
  )
}
