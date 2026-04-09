import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Input,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  theme,
} from 'antd'
import type { TableColumnsType } from 'antd'
import { InboxOutlined, ReloadOutlined } from '@ant-design/icons'

import { apiFetch } from '@/lib/utils'

const { Text, Paragraph } = Typography

type RecoveryMailboxFilter = 'all' | 'outlook' | 'hotmail'
type RecoveryMailboxType = 'outlook' | 'hotmail' | 'other'
type RecoveryStatusFilter = 'all' | 'leased' | 'recoverable'

interface RecoveryPoolItem {
  id: number
  email: string
  mailbox_type: RecoveryMailboxType
  status: string
  has_oauth: boolean
  source_account_id?: number | null
  task_attempt_id: string
  last_error: string
  leased_at?: string | null
  last_failed_at?: string | null
  updated_at?: string | null
}

interface RecoveryPoolSummary {
  total: number
  leased: number
  recoverable: number
  hotmail: number
  outlook: number
  other: number
}

interface RecoveryPoolResponse {
  mailbox_type: RecoveryMailboxFilter
  status: RecoveryStatusFilter
  search: string
  count: number
  items: RecoveryPoolItem[]
  truncated: boolean
  summary: RecoveryPoolSummary
}

function formatDateTime(value?: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN')
}

function getMailboxMeta(type: RecoveryMailboxType) {
  switch (type) {
    case 'hotmail':
      return { color: 'processing' as const, label: 'Hotmail' }
    case 'outlook':
      return { color: 'success' as const, label: 'Outlook' }
    default:
      return { color: 'default' as const, label: '其他' }
  }
}

function getStatusMeta(status: string) {
  if (status === 'recoverable') {
    return { color: 'warning' as const, label: '可恢复' }
  }
  if (status === 'leased') {
    return { color: 'processing' as const, label: '租用中' }
  }
  return { color: 'default' as const, label: status || '未知' }
}

export default function MailRecoveryPool() {
  const { message } = App.useApp()
  const { token } = theme.useToken()
  const [mailboxType, setMailboxType] = useState<RecoveryMailboxFilter>('hotmail')
  const [status, setStatus] = useState<RecoveryStatusFilter>('all')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [restoringId, setRestoringId] = useState<number | null>(null)
  const [snapshot, setSnapshot] = useState<RecoveryPoolResponse | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({
        mailbox_type: mailboxType,
        status,
        limit: '200',
      })
      if (search.trim()) {
        params.set('search', search.trim())
      }
      const data = await apiFetch(`/mail-imports/recovery-pool?${params.toString()}`) as RecoveryPoolResponse
      setSnapshot(data)
    } finally {
      setLoading(false)
    }
  }, [mailboxType, search, status])

  useEffect(() => {
    load()
  }, [load])

  const handleRestore = async (item: RecoveryPoolItem) => {
    setRestoringId(item.id)
    try {
      await apiFetch('/mail-imports/recovery-pool/restore', {
        method: 'POST',
        body: JSON.stringify({ id: item.id }),
      })
      message.success(`已恢复到可用池: ${item.email}`)
      await load()
    } catch (error) {
      const detail = error instanceof Error ? error.message : '恢复微软邮箱失败'
      message.error(detail)
    } finally {
      setRestoringId(null)
    }
  }

  const statCards = useMemo(() => ([
    {
      title: '当前命中',
      value: snapshot?.count ?? 0,
      color: token.colorPrimary,
    },
    {
      title: '可恢复',
      value: snapshot?.summary.recoverable ?? 0,
      color: token.colorWarning,
    },
    {
      title: '租用中',
      value: snapshot?.summary.leased ?? 0,
      color: token.colorInfo,
    },
    {
      title: 'Hotmail',
      value: snapshot?.summary.hotmail ?? 0,
      color: token.colorSuccess,
    },
  ]), [
    snapshot?.count,
    snapshot?.summary.hotmail,
    snapshot?.summary.leased,
    snapshot?.summary.recoverable,
    token.colorInfo,
    token.colorPrimary,
    token.colorSuccess,
    token.colorWarning,
  ])

  const columns: TableColumnsType<RecoveryPoolItem> = [
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
      width: 300,
      render: (_value, record) => {
        const mailboxMeta = getMailboxMeta(record.mailbox_type)
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Space size={[8, 8]} wrap>
              <Text style={{ fontFamily: 'monospace', fontSize: 12 }}>{record.email}</Text>
              <Tag color={mailboxMeta.color}>{mailboxMeta.label}</Tag>
              {record.has_oauth ? <Tag color="success">OAuth</Tag> : <Tag>无 OAuth</Tag>}
            </Space>
            {record.task_attempt_id ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                尝试标识: <span style={{ fontFamily: 'monospace' }}>{record.task_attempt_id}</span>
              </Text>
            ) : null}
          </div>
        )
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (value: string) => {
        const meta = getStatusMeta(value)
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: '最近错误',
      dataIndex: 'last_error',
      key: 'last_error',
      render: (_value, record) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {record.last_error ? (
            <Paragraph
              style={{ marginBottom: 0 }}
              ellipsis={{ rows: 2, tooltip: record.last_error }}
            >
              {record.last_error}
            </Paragraph>
          ) : (
            <Text type="secondary">-</Text>
          )}
          <Text type="secondary" style={{ fontSize: 12 }}>
            最近失败: {formatDateTime(record.last_failed_at)}
          </Text>
        </div>
      ),
    },
    {
      title: '租用时间',
      dataIndex: 'leased_at',
      key: 'leased_at',
      width: 180,
      render: (value?: string | null) => formatDateTime(value),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (value?: string | null) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      fixed: 'right',
      render: (_value, record) => (
        record.status === 'recoverable' ? (
          <Popconfirm
            title="确认恢复到可用池？"
            description="恢复后该邮箱会重新出现在可用池预览里，并可能再次被注册任务取用。"
            onConfirm={() => handleRestore(record)}
          >
            <Button
              type="link"
              size="small"
              loading={restoringId === record.id}
            >
              恢复
            </Button>
          </Popconfirm>
        ) : (
          <Text type="secondary">-</Text>
        )
      ),
    },
  ]

  return (
    <div className="page-enter" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
        <div>
          <Space align="center" size={10}>
            <InboxOutlined style={{ fontSize: 22, color: token.colorPrimary }} />
            <h1 style={{ fontSize: 24, fontWeight: 'bold', margin: 0 }}>微软恢复池</h1>
          </Space>
          <p style={{ color: token.colorTextSecondary, marginTop: 6 }}>
            查看仍可恢复的 Outlook / Hotmail 邮箱。页面默认聚焦 Hotmail。
          </p>
        </div>
        <Button icon={<ReloadOutlined spin={loading} />} onClick={load} loading={loading}>
          刷新
        </Button>
      </div>

      <Alert
        type="info"
        showIcon
        message="恢复池说明"
        description="微软邮箱被取用后会先进入恢复池。只有当 token_exchange 成功并完成账号落库后，恢复记录才会被清理；注册失败或拿不到 token 的邮箱会保留在这里。"
      />

      <Row gutter={[16, 16]}>
        {statCards.map((card) => (
          <Col xs={24} sm={12} xl={6} key={card.title}>
            <Card>
              <Statistic
                title={card.title}
                value={card.value}
                valueStyle={{ color: card.color }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Card>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Space size={[12, 12]} wrap>
            <Select
              value={mailboxType}
              onChange={(value) => setMailboxType(value)}
              style={{ width: 160 }}
              options={[
                { value: 'hotmail', label: 'Hotmail' },
                { value: 'outlook', label: 'Outlook' },
                { value: 'all', label: '全部类型' },
              ]}
            />
            <Select
              value={status}
              onChange={(value) => setStatus(value)}
              style={{ width: 160 }}
              options={[
                { value: 'all', label: '全部状态' },
                { value: 'recoverable', label: '可恢复' },
                { value: 'leased', label: '租用中' },
              ]}
            />
            <Input.Search
              allowClear
              placeholder="搜索邮箱、错误信息或尝试标识"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              onSearch={(value) => setSearch(value.trim())}
              style={{ width: 320 }}
            />
          </Space>
          <Space size={[8, 8]} wrap>
            <Text type="secondary">
              当前筛选命中 {snapshot?.count ?? 0} 条
              {snapshot?.truncated ? '，仅展示前 200 条' : ''}
            </Text>
            <Tag>Hotmail {snapshot?.summary.hotmail ?? 0}</Tag>
            <Tag>Outlook {snapshot?.summary.outlook ?? 0}</Tag>
            {(snapshot?.summary.other ?? 0) > 0 ? <Tag>其他 {snapshot?.summary.other ?? 0}</Tag> : null}
          </Space>
        </div>
      </Card>

      <Card bodyStyle={{ padding: 0 }}>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={snapshot?.items ?? []}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          scroll={{ x: 1080 }}
        />
      </Card>
    </div>
  )
}
