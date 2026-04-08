import { useEffect, useState } from 'react'
import { Alert, Card, Table, Button, Input, Tag, Space, Popconfirm, Switch, message } from 'antd'
import {
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SwapRightOutlined,
  SwapLeftOutlined,
} from '@ant-design/icons'
import { parseBooleanConfigValue } from '@/lib/configValueParsers'
import { apiFetch } from '@/lib/utils'

export default function Proxies() {
  const [proxies, setProxies] = useState<any[]>([])
  const [newProxy, setNewProxy] = useState('')
  const [region, setRegion] = useState('')
  const [checking, setChecking] = useState(false)
  const [loading, setLoading] = useState(false)
  const [autoDisableEnabled, setAutoDisableEnabled] = useState(true)
  const [savingAutoDisable, setSavingAutoDisable] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await apiFetch('/proxies')
      setProxies(data)
    } finally {
      setLoading(false)
    }
  }

  const loadConfig = async () => {
    const data = await apiFetch('/config')
    setAutoDisableEnabled(parseBooleanConfigValue(data.proxy_auto_disable_enabled || '1'))
  }

  useEffect(() => {
    load()
    loadConfig().catch(() => {})
  }, [])

  const add = async () => {
    if (!newProxy.trim()) return
    const lines = newProxy.trim().split('\n').map((l) => l.trim()).filter(Boolean)
    try {
      if (lines.length > 1) {
        await apiFetch('/proxies/bulk', {
          method: 'POST',
          body: JSON.stringify({ proxies: lines, region }),
        })
      } else {
        await apiFetch('/proxies', {
          method: 'POST',
          body: JSON.stringify({ url: lines[0], region }),
        })
      }
      message.success('添加成功')
      setNewProxy('')
      setRegion('')
      load()
    } catch (e: any) {
      message.error(`添加失败: ${e.message}`)
    }
  }

  const del = async (id: number) => {
    await apiFetch(`/proxies/${id}`, { method: 'DELETE' })
    message.success('删除成功')
    load()
  }

  const toggle = async (id: number) => {
    await apiFetch(`/proxies/${id}/toggle`, { method: 'PATCH' })
    load()
  }

  const check = async () => {
    setChecking(true)
    await apiFetch('/proxies/check', { method: 'POST' })
    setTimeout(() => {
      load()
      setChecking(false)
    }, 3000)
  }

  const updateAutoDisable = async (checked: boolean) => {
    setSavingAutoDisable(true)
    try {
      await apiFetch('/config', {
        method: 'PUT',
        body: JSON.stringify({
          data: {
            proxy_auto_disable_enabled: checked ? '1' : '0',
          },
        }),
      })
      setAutoDisableEnabled(checked)
      message.success(checked ? '已开启代理自动禁用' : '已关闭代理自动禁用')
    } finally {
      setSavingAutoDisable(false)
    }
  }

  const columns: any[] = [
    {
      title: '代理地址',
      dataIndex: 'url',
      key: 'url',
      render: (text: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{text}</span>,
    },
    {
      title: '地区',
      dataIndex: 'region',
      key: 'region',
      render: (text: string) => text || '-',
    },
    {
      title: '成功/失败',
      key: 'stats',
      render: (_: any, record: any) => (
        <Space>
          <Tag color="success">{record.success_count}</Tag>
          <span>/</span>
          <Tag color="error">{record.fail_count}</Tag>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (active: boolean) => (
        <Tag color={active ? 'success' : 'error'} icon={active ? <CheckCircleOutlined /> : <CloseCircleOutlined />}>
          {active ? '活跃' : '禁用'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: any) => (
        <Space>
          <Button
            type="text"
            size="small"
            icon={record.is_active ? <SwapLeftOutlined /> : <SwapRightOutlined />}
            onClick={() => toggle(record.id)}
          />
          <Popconfirm title="确认删除？" onConfirm={() => del(record.id)}>
            <Button type="text" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 'bold', margin: 0 }}>代理管理</h1>
          <p style={{ color: '#7a8ba3', marginTop: 4 }}>共 {proxies.length} 个代理</p>
        </div>
        <Button icon={<ReloadOutlined spin={checking} />} onClick={check} loading={checking}>
          检测全部
        </Button>
      </div>

      <Card title="添加代理（每行一个）">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input.TextArea
            value={newProxy}
            onChange={(e) => setNewProxy(e.target.value)}
            placeholder="http://user:pass@host:port"
            rows={3}
            style={{ fontFamily: 'monospace' }}
          />
          <Space>
            <Input
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              placeholder="地区标签 (如 US, SG)"
              style={{ width: 200 }}
            />
            <Button type="primary" icon={<PlusOutlined />} onClick={add}>
              添加
            </Button>
          </Space>
        </Space>
      </Card>

      <Card title="自动禁用策略">
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
            <div>
              <div style={{ fontWeight: 500, marginBottom: 4 }}>代理累计失败且从未成功时自动禁用</div>
              <div style={{ color: '#7a8ba3', fontSize: 12 }}>
                关闭后仍会继续累计成功/失败次数，但不会自动把代理标记为禁用。
              </div>
            </div>
            <Switch
              checked={autoDisableEnabled}
              loading={savingAutoDisable}
              checkedChildren="开启"
              unCheckedChildren="关闭"
              onChange={updateAutoDisable}
            />
          </div>
          <Alert
            showIcon
            type={autoDisableEnabled ? 'warning' : 'info'}
            message={autoDisableEnabled ? '当前已开启代理自动禁用' : '当前已关闭代理自动禁用'}
            description={
              autoDisableEnabled
                ? '命中当前自动禁用条件后，代理会被自动标记为禁用，不再参与轮询。'
                : '命中当前自动禁用条件后，代理仍保持活跃，需要你手动决定是否禁用。'
            }
          />
        </Space>
      </Card>

      <Card>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={proxies}
          loading={loading}
          pagination={false}
        />
      </Card>
    </div>
  )
}
