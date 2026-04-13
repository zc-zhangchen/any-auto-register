import { useCallback, useEffect, useState } from 'react'
import { Card, Table, Select, Button, Tag, Space, Popconfirm, Typography, message } from 'antd'
import type { TableColumnsType } from 'antd'
import { ReloadOutlined, DeleteOutlined } from '@ant-design/icons'
import { apiFetch } from '@/lib/utils'
import { useText, useUiLanguage } from '@/lib/uiLanguage'

const { Text } = Typography

interface TaskLogItem {
  id: number
  created_at: string
  platform: string
  email: string
  status: 'success' | 'failed'
  error: string
}

interface TaskLogListResponse {
  total: number
  items: TaskLogItem[]
}

interface TaskLogBatchDeleteResponse {
  deleted: number
  not_found: number[]
  total_requested: number
}

export default function TaskHistory() {
  const t = useText()
  const { language } = useUiLanguage()
  const [logs, setLogs] = useState<TaskLogItem[]>([])
  const [total, setTotal] = useState(0)
  const [platform, setPlatform] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ page: '1', page_size: '50' })
      if (platform) params.set('platform', platform)
      const data = await apiFetch(`/tasks/logs?${params}`) as TaskLogListResponse
      setLogs(data.items || [])
      setTotal(data.total || 0)
      setSelectedRowKeys((prev) => prev.filter((key) => data.items.some((item) => item.id === key)))
    } finally {
      setLoading(false)
    }
  }, [platform])

  useEffect(() => {
    load()
  }, [load])

  const handleBatchDelete = async () => {
    if (selectedRowKeys.length === 0) return

    const result = await apiFetch('/tasks/logs/batch-delete', {
      method: 'POST',
      body: JSON.stringify({ ids: selectedRowKeys }),
    }) as TaskLogBatchDeleteResponse

    message.success(t(`已删除 ${result.deleted} 条任务历史`, `Deleted ${result.deleted} history items`))
    if (result.not_found.length > 0) {
      message.warning(t(`${result.not_found.length} 条记录不存在或已被删除`, `${result.not_found.length} records were missing or already deleted`))
    }
    setSelectedRowKeys([])
    await load()
  }

  const columns: TableColumnsType<TaskLogItem> = [
    {
      title: t('时间', 'Time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (text: string) => (text ? new Date(text).toLocaleString(language === 'zh' ? 'zh-CN' : 'en-US') : '-'),
    },
    {
      title: t('平台', 'Platform'),
      dataIndex: 'platform',
      key: 'platform',
      width: 100,
      render: (text: string) => <Tag>{text}</Tag>,
    },
    {
      title: t('邮箱', 'Email'),
      dataIndex: 'email',
      key: 'email',
      render: (text: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{text}</span>,
    },
    {
      title: t('状态', 'Status'),
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: string) => (
        <Tag color={status === 'success' ? 'success' : 'error'}>
          {status === 'success' ? t('成功', 'Success') : t('失败', 'Failed')}
        </Tag>
      ),
    },
    {
      title: t('错误信息', 'Error'),
      dataIndex: 'error',
      key: 'error',
      render: (text: string) => text || '-',
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 'bold', margin: 0 }}>{t('任务历史', 'Task History')}</h1>
          <p style={{ color: '#7a8ba3', marginTop: 4 }}>{t('注册任务执行记录', 'Registration task execution records')}</p>
        </div>
        <Space>
          <Text type="secondary">{t(`${total} 条记录`, `${total} records`)}</Text>
          {selectedRowKeys.length > 0 && <Text type="success">{t(`已选 ${selectedRowKeys.length} 条`, `${selectedRowKeys.length} selected`)}</Text>}
          {selectedRowKeys.length > 0 && (
            <Popconfirm
              title={t(`确认删除选中的 ${selectedRowKeys.length} 条任务历史？`, `Delete the selected ${selectedRowKeys.length} history items?`)}
              onConfirm={handleBatchDelete}
              okText={t('删除', 'Delete')}
              cancelText={t('取消', 'Cancel')}
              okButtonProps={{ danger: true }}
            >
              <Button danger icon={<DeleteOutlined />}>
                {t(`删除 ${selectedRowKeys.length} 条`, `Delete ${selectedRowKeys.length}`)}
              </Button>
            </Popconfirm>
          )}
          <Select
            value={platform}
            onChange={(value) => {
              setPlatform(value)
              setSelectedRowKeys([])
            }}
            style={{ width: 120 }}
            options={[
              { value: '', label: t('全部平台', 'All platforms') },
              { value: 'trae', label: 'Trae' },
              { value: 'cursor', label: 'Cursor' },
            ]}
          />
          <Button icon={<ReloadOutlined spin={loading} />} onClick={load} loading={loading} />
        </Space>
      </div>

      <Card>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={logs}
          loading={loading}
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys as number[]),
          }}
          pagination={{ pageSize: 20, showSizeChanger: false }}
        />
      </Card>
    </div>
  )
}
