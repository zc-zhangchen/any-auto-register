import { useEffect, useState } from 'react'
import { Card, Row, Col, Statistic, Progress, Tag, Button, Spin } from 'antd'
import {
  UserOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { apiFetch } from '@/lib/utils'
import { useText } from '@/lib/uiLanguage'

const PLATFORM_COLORS: Record<string, string> = {
  trae: '#3b82f6',
  cursor: '#10b981',
}

const STATUS_COLORS: Record<string, string> = {
  registered: 'default',
  trial: 'success',
  subscribed: 'success',
  expired: 'warning',
  invalid: 'error',
}

export default function Dashboard() {
  const t = useText()
  const [stats, setStats] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await apiFetch('/accounts/stats')
      setStats(data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const statCards = [
    {
      title: t('总账号数', 'Total accounts'),
      value: stats?.total ?? 0,
      icon: <UserOutlined style={{ fontSize: 32 }} />,
      color: '#6366f1',
    },
    {
      title: t('试用中', 'Trial'),
      value: stats?.by_status?.trial ?? 0,
      icon: <ClockCircleOutlined style={{ fontSize: 32 }} />,
      color: '#f59e0b',
    },
    {
      title: t('已订阅', 'Subscribed'),
      value: stats?.by_status?.subscribed ?? 0,
      icon: <CheckCircleOutlined style={{ fontSize: 32 }} />,
      color: '#10b981',
    },
    {
      title: t('已失效', 'Invalid'),
      value: (stats?.by_status?.expired ?? 0) + (stats?.by_status?.invalid ?? 0),
      icon: <CloseCircleOutlined style={{ fontSize: 32 }} />,
      color: '#ef4444',
    },
  ]

  return (
    <div style={{ padding: 0 }}>
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 'bold', margin: 0 }}>{t('仪表盘', 'Dashboard')}</h1>
          <p style={{ color: '#7a8ba3', marginTop: 4 }}>{t('账号总览', 'Account overview')}</p>
        </div>
        <Button icon={<ReloadOutlined spin={loading} />} onClick={load} loading={loading}>
          {t('刷新', 'Refresh')}
        </Button>
      </div>

      <Row gutter={[16, 16]}>
        {statCards.map(({ title, value, icon, color }) => (
          <Col xs={24} sm={12} lg={6} key={title}>
            <Card>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Statistic title={title} value={value} />
                <div style={{ color, opacity: 0.8 }}>{icon}</div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card title={t('平台分布', 'Platform breakdown')}>
            {loading ? (
              <div style={{ textAlign: 'center', padding: 40 }}>
                <Spin />
              </div>
            ) : stats ? (
              Object.entries(stats.by_platform || {}).map(([platform, count]: any) => (
                <div key={platform} style={{ marginBottom: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <Tag color={PLATFORM_COLORS[platform] || 'default'}>{platform}</Tag>
                    <span>{count}</span>
                  </div>
                  <Progress
                    percent={stats.total ? Math.round((count / stats.total) * 100) : 0}
                    strokeColor={PLATFORM_COLORS[platform] || '#6366f1'}
                    showInfo={false}
                  />
                </div>
              ))
            ) : (
                <div style={{ textAlign: 'center', color: '#7a8ba3' }}>{t('加载中...', 'Loading...')}</div>
              )}
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card title={t('状态分布', 'Status breakdown')}>
            {loading ? (
              <div style={{ textAlign: 'center', padding: 40 }}>
                <Spin />
              </div>
            ) : stats ? (
              Object.entries(stats.by_status || {}).map(([status, count]: any) => (
                <div
                  key={status}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '8px 0',
                    borderBottom: '1px solid rgba(255,255,255,0.1)',
                  }}
                >
                  <Tag color={STATUS_COLORS[status] || 'default'}>{status}</Tag>
                  <span>{count}</span>
                </div>
              ))
            ) : (
                <div style={{ textAlign: 'center', color: '#7a8ba3' }}>{t('加载中...', 'Loading...')}</div>
              )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
