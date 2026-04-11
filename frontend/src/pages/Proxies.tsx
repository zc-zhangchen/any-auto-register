import { useEffect, useState, type Key } from 'react'
import { Card, Table, Button, Input, Tag, Space, Popconfirm, message, Modal } from 'antd'
import {
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SwapRightOutlined,
  SwapLeftOutlined,
} from '@ant-design/icons'
import { apiFetch } from '@/lib/utils'

export default function Proxies() {
  const [proxies, setProxies] = useState<any[]>([])
  const [newProxy, setNewProxy] = useState('')
  const [region, setRegion] = useState('')
  const [checking, setChecking] = useState(false)
  const [loading, setLoading] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([])

  const load = async () => {
    setLoading(true)
    try {
      const data = await apiFetch('/proxies')
      setProxies(data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
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
    try {
      await apiFetch(`/proxies/${id}`, { method: 'DELETE' })
      message.success('删除成功')
      setSelectedRowKeys((prev) => prev.filter((key) => key !== id))
      load()
    } catch (e: any) {
      message.error(`删除失败: ${e.message || '未知错误'}`)
    }
  }

  const batchDel = async () => {
    if (selectedRowKeys.length === 0) return
    const ids = selectedRowKeys.map((key) => Number(key)).filter((v) => Number.isFinite(v))
    try {
      const result = await apiFetch('/proxies/batch-delete', {
        method: 'POST',
        body: JSON.stringify({ ids }),
      }) as { deleted: number; not_found?: number[]; total_requested?: number }
      setSelectedRowKeys([])
      load()

      const notFound = (result.not_found || []) as number[]
      Modal.success({
        title: '批量删除结果',
        okText: '知道了',
        content: (
          <div>
            <div>请求删除：{result.total_requested ?? ids.length} 条</div>
            <div>成功删除：{result.deleted ?? 0} 条</div>
            <div>未找到：{notFound.length} 条</div>
            {notFound.length > 0 && (
              <div style={{ marginTop: 8, maxHeight: 120, overflow: 'auto', fontFamily: 'monospace' }}>
                {notFound.join(', ')}
              </div>
            )}
          </div>
        ),
      })
    } catch (e: any) {
      message.error(`批量删除失败: ${e.message || '未知错误'}`)
    }
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
          <Popconfirm
            title="确认删除该代理吗？"
            onConfirm={() => del(record.id)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
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

      <Card>
        <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between' }}>
          <div style={{ color: '#7a8ba3' }}>
            已选中 {selectedRowKeys.length} 条
          </div>
          <Popconfirm
            title={`确认删除选中的 ${selectedRowKeys.length} 条代理？`}
            onConfirm={batchDel}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            disabled={selectedRowKeys.length === 0}
          >
            <Button danger icon={<DeleteOutlined />} disabled={selectedRowKeys.length === 0}>
              批量删除
            </Button>
          </Popconfirm>
        </div>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={proxies}
          loading={loading}
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys),
          }}
          pagination={false}
        />
      </Card>
    </div>
  )
}
