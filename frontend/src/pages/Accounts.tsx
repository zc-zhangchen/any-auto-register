import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import {
  Table,
  Button,
  Input,
  InputNumber,
  Select,
  Tag,
  Space,
  Modal,
  Form,
  message,
  Popconfirm,
  Dropdown,
  Typography,
  Alert,
  DatePicker,
  theme,
} from 'antd'
import type { MenuProps } from 'antd'
import {
  ReloadOutlined,
  CopyOutlined,
  LinkOutlined,
  PlusOutlined,
  DownloadOutlined,
  UploadOutlined,
  MoreOutlined,
  DeleteOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import { ChatGPTRegistrationModeSwitch } from '@/components/ChatGPTRegistrationModeSwitch'
import { TaskLogPanel } from '@/components/TaskLogPanel'
import { usePersistentChatGPTRegistrationMode } from '@/hooks/usePersistentChatGPTRegistrationMode'
import { parseBooleanConfigValue } from '@/lib/configValueParsers'
import { buildChatGPTRegistrationRequestAdapter } from '@/lib/chatgptRegistrationRequestAdapter'
import { apiFetch } from '@/lib/utils'
import { normalizeExecutorForPlatform } from '@/lib/platformExecutorOptions'
import { useText, useUiLanguage } from '@/lib/uiLanguage'

const { Text } = Typography

const STATUS_COLORS: Record<string, string> = {
  registered: 'default',
  trial: 'success',
  subscribed: 'success',
  expired: 'warning',
  invalid: 'error',
}

function parseExtraJson(raw: string | undefined) {
  if (!raw) return {}
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function normalizeAccount(account: any) {
  const extra = parseExtraJson(account.extra_json)
  const syncStatuses = extra.sync_statuses && typeof extra.sync_statuses === 'object' ? extra.sync_statuses : {}
  const cpaSync = syncStatuses.cpa && typeof syncStatuses.cpa === 'object' ? syncStatuses.cpa : {}
  const sub2apiSync = syncStatuses.sub2api && typeof syncStatuses.sub2api === 'object' ? syncStatuses.sub2api : {}
  const cliproxySync = syncStatuses.cliproxyapi && typeof syncStatuses.cliproxyapi === 'object' ? syncStatuses.cliproxyapi : {}
  const chatgptLocal = extra.chatgpt_local && typeof extra.chatgpt_local === 'object' ? extra.chatgpt_local : {}
  return { ...account, extra, cpaSync, sub2apiSync, cliproxySync, chatgptLocal }
}

function formatSyncTime(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function formatCreatedAt(value?: string) {
  if (!value) return { date: '-', time: '' }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return { date: value, time: '' }
  }
  return {
    date: date.toLocaleDateString(),
    time: date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  }
}

function translateAccountActionLabel(label: string, english: boolean) {
  if (!english) return label
  const normalized = String(label || '').trim()
  const translations: Record<string, string> = {
    '探测本地状态': 'Probe local status',
    '同步 CLIProxyAPI 状态': 'Sync CLIProxyAPI status',
    '刷新 Token': 'Refresh token',
    '生成支付链接': 'Generate payment link',
    '上传 CPA': 'Upload to CPA',
    '上传 Sub2API': 'Upload to Sub2API',
    '上传 Team Manager': 'Upload to Team Manager',
    '上传 CodexProxy': 'Upload to CodexProxy',
    '上传到 CPA': 'Upload to CPA',
    '上传到 Sub2API': 'Upload to Sub2API',
    '上传到 Team Manager': 'Upload to Team Manager',
    '上传到 CodexProxy': 'Upload to CodexProxy',
    '探测本地状态并同步': 'Probe local status and sync',
  }
  return translations[normalized] || normalized
}

function translateAccountActionMessage(message: string, english: boolean) {
  if (!english) return message
  return String(message || '')
    .replaceAll('操作完成', 'Action completed')
    .replaceAll('操作失败', 'Action failed')
    .replaceAll('链接已复制', 'Link copied')
    .replaceAll('复制失败', 'Copy failed')
    .replaceAll('链接已生成', 'Link generated')
    .replaceAll('操作成功，请在弹窗中打开或复制链接。', 'Action successful. Open or copy the link in the dialog.')
    .replaceAll('操作成功', 'Action successful')
    .replaceAll('请求失败', 'Request failed')
    .replaceAll('未在 CLIProxyAPI 找到匹配的 Codex auth-file', 'No matching Codex auth-file was found in CLIProxyAPI')
    .replaceAll('未在 CLIProxyAPI 找到匹配', 'No match found in CLIProxyAPI')
    .replaceAll('远端未发现', 'Not found remotely')
    .replaceAll('未发现', 'Not found')
    .replaceAll('同步 CLIProxyAPI 状态', 'Sync CLIProxyAPI status')
}

function authStateMeta(state?: string, english = false) {
  switch (state) {
    case 'access_token_valid':
      return { color: 'success', label: english ? 'AT valid' : 'AT有效' }
    case 'account_deactivated':
      return { color: 'error', label: english ? 'Disabled' : '已失效' }
    case 'access_token_invalidated':
      return { color: 'error', label: english ? 'AT invalid' : 'AT失效' }
    case 'unauthorized':
      return { color: 'error', label: english ? 'Unauthorized' : '未授权' }
    case 'missing_access_token':
      return { color: 'default', label: english ? 'Missing AT' : '缺少AT' }
    case 'banned_like':
      return { color: 'error', label: english ? 'Possibly banned' : '疑似封禁' }
    case 'probe_failed':
      return { color: 'warning', label: english ? 'Probe failed' : '探测失败' }
    default:
      return { color: 'default', label: english ? 'Not probed' : '未探测' }
  }
}

function codexStateMeta(state?: string, english = false) {
  switch (state) {
    case 'usable':
      return { color: 'success', label: english ? 'Usable' : '可用' }
    case 'account_deactivated':
      return { color: 'error', label: english ? 'Disabled' : '已失效' }
    case 'access_token_invalidated':
      return { color: 'error', label: english ? 'AT invalid' : 'AT失效' }
    case 'unauthorized':
      return { color: 'error', label: english ? 'Unauthorized' : '未授权' }
    case 'payment_required':
      return { color: 'warning', label: english ? 'Payment/permission required' : '需付费/权限' }
    case 'quota_exhausted':
      return { color: 'warning', label: english ? 'Quota exhausted' : '额度耗尽' }
    case 'skipped_auth_invalid':
      return { color: 'default', label: english ? 'Not checked' : '未测' }
    case 'probe_failed':
      return { color: 'warning', label: english ? 'Probe failed' : '探测失败' }
    default:
      return { color: 'default', label: english ? 'Not probed' : '未探测' }
  }
}

function planMeta(plan?: string, english = false) {
  switch ((plan || '').toLowerCase()) {
    case 'plus':
      return { color: 'success', label: 'Plus' }
    case 'team':
      return { color: 'processing', label: 'Team' }
    case 'enterprise':
      return { color: 'processing', label: 'Enterprise' }
    case 'pro':
      return { color: 'processing', label: 'Pro' }
    case 'free':
      return { color: 'default', label: 'Free' }
    default:
      return { color: 'default', label: english ? 'Unknown' : '未知' }
  }
}

function formatStructuredText(value?: string) {
  if (!value) return ''
  const trimmed = String(value).trim()
  if (!trimmed) return ''
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      return JSON.stringify(JSON.parse(trimmed), null, 2)
    } catch {
      return trimmed
    }
  }
  return trimmed
}

function SummaryField({
  label,
  value,
  code = false,
}: {
  label: string
  value?: string
  code?: boolean
}) {
  const { token } = theme.useToken()
  if (!value) return null

  const content = code ? formatStructuredText(value) : value
  const isBlock = code || content.length > 96 || content.includes('\n')

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '104px minmax(0, 1fr)',
        gap: 12,
        alignItems: 'start',
      }}
    >
      <Text type="secondary" style={{ fontSize: 12, lineHeight: '20px' }}>
        {label}
      </Text>
      {isBlock ? (
        <pre
          style={{
            margin: 0,
            padding: code ? '8px 10px' : 0,
            borderRadius: code ? token.borderRadius : 0,
            border: code ? `1px solid ${token.colorBorder}` : 'none',
            background: code ? token.colorBgElevated : 'transparent',
            color: code ? token.colorText : token.colorTextSecondary,
            fontFamily: code ? 'SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace' : 'inherit',
            fontSize: 12,
            lineHeight: 1.6,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            overflowWrap: 'anywhere',
            maxHeight: code ? 160 : 'none',
            overflow: code ? 'auto' : 'visible',
          }}
        >
          {content}
        </pre>
      ) : (
        <Text style={{ display: 'block', color: token.colorTextSecondary, lineHeight: '20px' }}>
          {content}
        </Text>
      )}
    </div>
  )
}

function DetailSection({ title, children }: { title: string; children: React.ReactNode }) {
  const { token } = theme.useToken()

  return (
    <div
      style={{
        marginTop: 16,
        padding: 14,
        borderRadius: token.borderRadiusLG,
        border: `1px solid ${token.colorBorder}`,
        background: token.colorFillAlter,
      }}
    >
      <div style={{ marginBottom: 10, fontWeight: 600, color: token.colorText }}>{title}</div>
      {children}
    </div>
  )
}

function LocalProbeSummary({ probe }: { probe: any }) {
  const { language } = useUiLanguage()
  const english = language === 'en'
  const checkedAt = probe?.checked_at || probe?.auth?.checked_at || probe?.subscription?.checked_at || probe?.codex?.checked_at
  const auth = probe?.auth || {}
  const subscription = probe?.subscription || {}
  const codex = probe?.codex || {}

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        <Tag color={authStateMeta(auth.state, english).color}>{english ? 'Auth' : '认证'}: {authStateMeta(auth.state, english).label}</Tag>
        <Tag color={planMeta(subscription.plan).color}>{english ? 'Subscription' : '订阅'}: {planMeta(subscription.plan).label}</Tag>
        <Tag color={codexStateMeta(codex.state, english).color}>Codex: {codexStateMeta(codex.state, english).label}</Tag>
      </div>
      <SummaryField label={english ? 'Probe time' : '探测时间'} value={checkedAt ? formatSyncTime(checkedAt) : ''} />
      <SummaryField label={english ? 'Auth info' : '认证信息'} value={auth.message} code />
      <SummaryField label={english ? 'Workspace plan' : '工作区套餐'} value={subscription.workspace_plan_type} />
      <SummaryField label={english ? 'Codex info' : 'Codex 信息'} value={codex.message} code />
    </div>
  )
}

function cliproxyStateMeta(sync: any, english = false) {
  if (!sync || Object.keys(sync).length === 0) {
    return { color: 'default', label: english ? 'Not synced' : '未同步' }
  }
  if (sync.remote_state === 'unreachable') {
    return { color: 'error', label: english ? 'Unreachable' : '不可连接' }
  }
  if (sync.remote_state === 'not_found') {
    return { color: 'default', label: english ? 'Not found remotely' : '远端未发现' }
  }
  if (!sync.uploaded) {
    return { color: 'default', label: english ? 'Not found' : '未发现' }
  }
  if (sync.remote_state === 'usable') {
    return { color: 'success', label: english ? 'Remote usable' : '远端可用' }
  }
  if (sync.remote_state === 'account_deactivated') {
    return { color: 'error', label: english ? 'Remote disabled' : '远端已失效' }
  }
  if (sync.remote_state === 'access_token_invalidated') {
    return { color: 'error', label: english ? 'Remote AT invalid' : '远端AT失效' }
  }
  if (sync.remote_state === 'unauthorized') {
    return { color: 'error', label: english ? 'Remote unauthorized' : '远端未授权' }
  }
  if (sync.remote_state === 'payment_required') {
    return { color: 'warning', label: english ? 'Remote payment/permission required' : '远端需付费/权限' }
  }
  if (sync.remote_state === 'quota_exhausted') {
    return { color: 'warning', label: english ? 'Remote quota exhausted' : '远端额度耗尽' }
  }
  if (sync.status === 'active') {
    return { color: 'processing', label: english ? 'Remote active' : '远端Active' }
  }
  if (sync.status === 'refreshing') {
    return { color: 'processing', label: english ? 'Remote refreshing' : '远端刷新中' }
  }
  if (sync.status === 'pending') {
    return { color: 'default', label: english ? 'Remote pending' : '远端待处理' }
  }
  if (sync.status === 'error') {
    return { color: 'error', label: english ? 'Remote error' : '远端错误' }
  }
  if (sync.status === 'disabled') {
    return { color: 'default', label: english ? 'Remote disabled' : '远端禁用' }
  }
  return { color: 'default', label: english ? 'Not synced' : '未同步' }
}

function uploadSyncMeta(sync: any, english = false) {
  if (!sync || Object.keys(sync).length === 0) {
    return { color: 'default', label: english ? 'Not uploaded' : '未上传' }
  }
  if (sync.uploaded || sync.uploaded_at) {
    return { color: 'success', label: english ? 'Uploaded' : '已上传' }
  }
  if (sync.last_attempt_ok === false) {
    return { color: 'error', label: english ? 'Failed' : '失败' }
  }
  if (sync.last_attempt_ok === true || sync.last_attempt_at) {
    return { color: 'processing', label: english ? 'Attempted' : '已尝试' }
  }
  return { color: 'default', label: english ? 'Not uploaded' : '未上传' }
}

function uploadSyncTitle(name: string, sync: any, english = false) {
  if (!sync || Object.keys(sync).length === 0) {
    return english ? `${name} not uploaded` : `${name} 未上传`
  }

  const parts: string[] = []
  if (sync.uploaded_at) {
    parts.push(english ? `Uploaded at: ${formatSyncTime(sync.uploaded_at)}` : `成功时间: ${formatSyncTime(sync.uploaded_at)}`)
  }
  if (sync.last_attempt_at) {
    parts.push(english ? `Last attempt: ${formatSyncTime(sync.last_attempt_at)}` : `最近尝试: ${formatSyncTime(sync.last_attempt_at)}`)
  }
  if (sync.last_message) {
    parts.push(english ? `Result: ${sync.last_message}` : `结果: ${sync.last_message}`)
  }
  return parts.join('\n') || (english ? `${name} status recorded` : `${name} 已记录状态`)
}

function CliproxySyncSummary({ sync }: { sync: any }) {
  const { language } = useUiLanguage()
  const english = language === 'en'
  const meta = cliproxyStateMeta(sync, english)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        <Tag color={meta.color}>{meta.label}</Tag>
        {sync?.status ? <Tag>{english ? `Status: ${sync.status}` : `status: ${sync.status}`}</Tag> : null}
      </div>
      <SummaryField label={english ? 'Status info' : '状态信息'} value={sync?.status_message} code />
      <SummaryField label="auth-file" value={sync?.name} />
      <SummaryField label={english ? 'API URL' : 'API URL'} value={sync?.base_url} />
      <SummaryField label={english ? 'Sync time' : '同步时间'} value={sync?.last_synced_at ? formatSyncTime(sync.last_synced_at) : ''} />
      <SummaryField label={english ? 'Remote refresh time' : '远端刷新时间'} value={sync?.last_refresh ? formatSyncTime(sync.last_refresh) : ''} />
      <SummaryField label={english ? 'Next retry time' : '下次重试时间'} value={sync?.next_retry_after ? formatSyncTime(sync.next_retry_after) : ''} />
      <SummaryField label={english ? 'Probe info' : '探测信息'} value={sync?.last_probe_message} code />
    </div>
  )
}

function ActionMenu({ acc, onRefresh, actions }: { acc: any; onRefresh: () => void; actions: any[] }) {
  const { language } = useUiLanguage()
  const english = language === 'en'
  const [resultOpen, setResultOpen] = useState(false)
  const [resultTitle, setResultTitle] = useState('')
  const [resultStatus, setResultStatus] = useState<'success' | 'error'>('success')
  const [resultText, setResultText] = useState('')
  const [resultUrl, setResultUrl] = useState('')
  const [resultProbe, setResultProbe] = useState<any>(null)
  const [resultCliproxySync, setResultCliproxySync] = useState<any>(null)

  const showResult = (title: string, status: 'success' | 'error', text: string, url = '', probe: any = null, cliproxySync: any = null) => {
    setResultTitle(title)
    setResultStatus(status)
    setResultText(text)
    setResultUrl(url)
    setResultProbe(probe)
    setResultCliproxySync(cliproxySync)
    setResultOpen(true)
  }

  const copyResultUrl = async () => {
    if (!resultUrl) return
    try {
      await navigator.clipboard.writeText(resultUrl)
      message.success(translateAccountActionMessage('链接已复制', english))
    } catch {
      message.error(translateAccountActionMessage('复制失败', english))
    }
  }

  const handleAction = async (actionId: string) => {
    const actionLabel = translateAccountActionLabel(actions.find((item) => item.id === actionId)?.label || actionId, english)

    try {
      const r = await apiFetch(`/actions/${acc.platform}/${acc.id}/${actionId}`, {
        method: 'POST',
        body: JSON.stringify({ params: {} }),
      })
      if (!r.ok) {
        const data = r.data || {}
        const probe = typeof data === 'object' && data ? data.probe || null : null
        const cliproxySync = typeof data === 'object' && data ? data.sync || null : null
        showResult(actionLabel, 'error', translateAccountActionMessage(r.error || data.message || '操作失败', english), '', probe, cliproxySync)
        onRefresh()
        return
      }
      const data = r.data || {}
      if (data.url || data.checkout_url || data.cashier_url) {
        const targetUrl = data.url || data.checkout_url || data.cashier_url
        message.success(translateAccountActionMessage('链接已生成', english))
        showResult(actionLabel, 'success', translateAccountActionMessage('操作成功，请在弹窗中打开或复制链接。', english), targetUrl)
      } else {
        message.success(translateAccountActionMessage(data.message || '操作成功', english))
        const probe = typeof data === 'object' && data ? data.probe || null : null
        const cliproxySync = typeof data === 'object' && data ? data.sync || null : null
        const text =
          probe
            ? translateAccountActionMessage(String(data.message || '操作成功'), english)
            : cliproxySync
            ? translateAccountActionMessage(String(data.message || '操作成功'), english)
            : typeof data === 'string'
            ? translateAccountActionMessage(data, english)
            : Object.keys(data).length > 0
              ? JSON.stringify(data, null, 2)
              : translateAccountActionMessage('操作成功', english)
        showResult(actionLabel, 'success', text, '', probe, cliproxySync)
      }
      onRefresh()
    } catch (e: any) {
      const detail = e?.message ? translateAccountActionMessage(String(e.message), english) : translateAccountActionMessage('请求失败', english)
      message.error(detail)
      showResult(actionLabel, 'error', detail)
    }
  }

  const menuItems: MenuProps['items'] = actions.map((a) => ({
    key: a.id,
    label: translateAccountActionLabel(a.label, english),
  }))

  if (actions.length === 0) return null

  return (
    <>
      <Dropdown
        menu={{
          items: menuItems,
          onClick: ({ key }) => handleAction(String(key)),
        }}
      >
        <Button type="link" size="small" icon={<MoreOutlined />} />
      </Dropdown>
      <Modal
        title={resultTitle}
        open={resultOpen}
        onCancel={() => setResultOpen(false)}
        footer={[
          resultUrl ? (
            <Button key="copy" onClick={copyResultUrl}>
              {english ? 'Copy link' : '复制链接'}
            </Button>
          ) : null,
          resultUrl ? (
            <Button
              key="open"
              type="primary"
              onClick={() => window.open(resultUrl, '_blank', 'noopener,noreferrer')}
            >
              {english ? 'Open link' : '打开链接'}
            </Button>
          ) : null,
          <Button key="ok" type={resultUrl ? 'default' : 'primary'} onClick={() => setResultOpen(false)}>
            {english ? 'OK' : '确定'}
          </Button>,
        ].filter(Boolean)}
        maskClosable={false}
      >
        <Alert
          type={resultStatus}
          showIcon
          message={resultStatus === 'success' ? (english ? 'Action completed' : '操作完成') : (english ? 'Action failed' : '操作失败')}
          style={{ marginBottom: 12 }}
        />
        {resultProbe ? (
          <div style={{ marginBottom: 12 }}>
            <LocalProbeSummary probe={resultProbe} />
          </div>
        ) : null}
        {resultCliproxySync ? (
          <div style={{ marginBottom: 12 }}>
            <CliproxySyncSummary sync={resultCliproxySync} />
          </div>
        ) : null}
        {resultUrl ? (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Text copyable={{ text: resultUrl }} style={{ wordBreak: 'break-all' }}>
              {resultUrl}
            </Text>
          </Space>
        ) : null}
        {resultText ? (
          <pre
            style={{
              margin: 0,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              fontFamily: 'monospace',
              fontSize: 12,
            }}
          >
            {resultText}
          </pre>
        ) : null}
      </Modal>
    </>
  )
}

export default function Accounts() {
  const t = useText()
  const { language } = useUiLanguage()
  const english = language === 'en'
  const { platform } = useParams<{ platform: string }>()
  const { token } = theme.useToken()
  const [currentPlatform, setCurrentPlatform] = useState(platform || 'trae')
  const [accounts, setAccounts] = useState<any[]>([])
  const [platformActions, setPlatformActions] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [createdAtStart, setCreatedAtStart] = useState('')
  const [createdAtEnd, setCreatedAtEnd] = useState('')
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])

  const [registerModalOpen, setRegisterModalOpen] = useState(false)
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [importModalOpen, setImportModalOpen] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [currentAccount, setCurrentAccount] = useState<any>(null)

  const [registerForm] = Form.useForm()
  const [addForm] = Form.useForm()
  const [detailForm] = Form.useForm()
  const { mode: chatgptRegistrationMode, setMode: setChatgptRegistrationMode } =
    usePersistentChatGPTRegistrationMode()
  const [importText, setImportText] = useState('')
  const [importLoading, setImportLoading] = useState(false)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [registerLoading, setRegisterLoading] = useState(false)
  const [cpaSyncLoading, setCpaSyncLoading] = useState<'pending' | 'selected' | ''>('')
  const [statusSyncLoading, setStatusSyncLoading] = useState<'probe_selected' | 'probe_all' | 'remote_selected' | 'remote_all' | ''>('')

  useEffect(() => {
    if (platform) setCurrentPlatform(platform)
  }, [platform])

  useEffect(() => {
    if (!detailModalOpen || !currentAccount) return
    detailForm.setFieldsValue({
      status: currentAccount.status,
      token: currentAccount.token,
    })
  }, [detailModalOpen, currentAccount, detailForm])

  const load = useCallback(async () => {
    if (createdAtStart && createdAtEnd && new Date(createdAtStart).getTime() > new Date(createdAtEnd).getTime()) {
      message.warning('开始时间不能晚于结束时间')
      setAccounts([])
      setTotal(0)
      return
    }

    setLoading(true)
    try {
      const params = new URLSearchParams({ platform: currentPlatform, page: String(page), page_size: String(pageSize) })
      if (search) params.set('email', search)
      if (filterStatus) params.set('status', filterStatus)
      if (createdAtStart) params.set('created_at_start', createdAtStart)
      if (createdAtEnd) params.set('created_at_end', createdAtEnd)
      const data = await apiFetch(`/accounts?${params}`)
      setAccounts((data.items || []).map(normalizeAccount))
      setTotal(data.total)
    } finally {
      setLoading(false)
    }
  }, [currentPlatform, search, filterStatus, createdAtStart, createdAtEnd, page, pageSize])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    apiFetch(`/actions/${currentPlatform}`)
      .then((data) => setPlatformActions(data.actions || []))
      .catch(() => setPlatformActions([]))
  }, [currentPlatform])

  const copyText = (text: string) => {
    navigator.clipboard.writeText(text)
    message.success(t('已复制', 'Copied'))
  }

  const getRefreshToken = (record: any): string => {
    try {
      const extra = JSON.parse(record.extra_json || '{}')
      return extra.refresh_token || extra.refreshToken || ''
    } catch {
      return ''
    }
  }

  const exportCsv = () => {
    const quoteCsv = (value: any) => {
      const text = value == null ? '' : String(value)
      return `"${text.replace(/"/g, '""')}"`
    }

    const downloadCsv = (content: string) => {
      const blob = new Blob([`\uFEFF${content}`], { type: 'text/csv;charset=utf-8;' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${currentPlatform}_accounts.csv`
      a.click()
      URL.revokeObjectURL(url)
    }

    if (currentPlatform === 'kiro') {
      const header = [t('邮箱', 'Email'), t('昵称', 'Nickname'), t('登录方式', 'Login method'), 'RefreshToken', 'ClientId', 'ClientSecret', 'Region']
      const rows = accounts.map((a) => {
        const nickname = a.extra?.name || String(a.email || '').split('@')[0] || ''
        const provider = a.extra?.provider || 'BuilderId'
        const refreshToken = a.extra?.refreshToken || ''
        const clientId = a.extra?.clientId || ''
        const clientSecret = a.extra?.clientSecret || ''
        const region = a.extra?.region || 'us-east-1'

        return [
          a.email || '',
          nickname,
          provider,
          refreshToken,
          clientId,
          clientSecret,
          region,
        ].map(quoteCsv).join(',')
      })

      downloadCsv([header.map(quoteCsv).join(','), ...rows].join('\r\n'))
      return
    }

    const header = ['email', 'password', 'status', 'region', 'cashier_url', 'created_at']
    if (currentPlatform === 'kiro') {
      header.push('accessToken', 'refreshToken', 'clientId', 'clientSecret')
    } else if (currentPlatform === 'chatgpt') {
      header.push('token', 'refresh_token')
    } else {
      header.push('token')
    }

    const rows = accounts.map((a) => {
      const baseRow = [a.email, a.password, a.status, a.region, a.cashier_url, a.created_at].map(quoteCsv)
      if (currentPlatform === 'kiro') {
        baseRow.push(quoteCsv(a.extra?.accessToken || a.extra?.webAccessToken || a.token))
        baseRow.push(quoteCsv(a.extra?.refreshToken))
        baseRow.push(quoteCsv(a.extra?.clientId))
        baseRow.push(quoteCsv(a.extra?.clientSecret))
      } else if (currentPlatform === 'chatgpt') {
        baseRow.push(quoteCsv(a.token))
        baseRow.push(quoteCsv(getRefreshToken(a)))
      } else {
        baseRow.push(quoteCsv(a.token))
      }
      return baseRow.join(',')
    })

    downloadCsv([header.map(quoteCsv).join(','), ...rows].join('\r\n'))
  }

  const handleDelete = async (id: number) => {
    await apiFetch(`/accounts/${id}`, { method: 'DELETE' })
    message.success(t('删除成功', 'Deleted'))
    load()
  }

  const handleBatchDelete = async () => {
    if (selectedRowKeys.length === 0) return
    await apiFetch('/accounts/batch-delete', {
      method: 'POST',
      body: JSON.stringify({ ids: Array.from(selectedRowKeys) }),
    })
    message.success(t('批量删除成功', 'Batch deleted'))
    setSelectedRowKeys([])
    load()
  }

  const handleAdd = async () => {
    const values = await addForm.validateFields()
    await apiFetch('/accounts', {
      method: 'POST',
      body: JSON.stringify({ ...values, platform: currentPlatform }),
    })
    message.success(t('添加成功', 'Added'))
    setAddModalOpen(false)
    addForm.resetFields()
    load()
  }

  const handleImport = async () => {
    if (!importText.trim()) return
    setImportLoading(true)
    try {
      const lines = importText.trim().split('\n').filter(Boolean)
      const res = await apiFetch('/accounts/import', {
        method: 'POST',
        body: JSON.stringify({ platform: currentPlatform, lines }),
      })
      message.success(t(`导入成功 ${res.created} 个`, `Imported ${res.created}`))
      setImportModalOpen(false)
      setImportText('')
      load()
    } catch (e: any) {
      message.error(t(`导入失败: ${e.message}`, `Import failed: ${e.message}`))
    } finally {
      setImportLoading(false)
    }
  }

  const handleRegister = async () => {
    const values = await registerForm.validateFields()
    setRegisterLoading(true)
    try {
      const cfg = await apiFetch('/config')
      const executorType = normalizeExecutorForPlatform(currentPlatform, cfg.default_executor)
      const registerExtra = {
        mail_provider: cfg.mail_provider || 'luckmail',
        applemail_base_url: cfg.applemail_base_url,
        applemail_pool_dir: cfg.applemail_pool_dir,
        applemail_pool_file: cfg.applemail_pool_file,
        applemail_mailboxes: cfg.applemail_mailboxes,
        laoudo_auth: cfg.laoudo_auth,
        laoudo_email: cfg.laoudo_email,
        laoudo_account_id: cfg.laoudo_account_id,
        gptmail_base_url: cfg.gptmail_base_url,
        gptmail_api_key: cfg.gptmail_api_key,
        gptmail_domain: cfg.gptmail_domain,
        maliapi_base_url: cfg.maliapi_base_url,
        maliapi_api_key: cfg.maliapi_api_key,
        maliapi_domain: cfg.maliapi_domain,
        maliapi_auto_domain_strategy: cfg.maliapi_auto_domain_strategy,
        yescaptcha_key: cfg.yescaptcha_key,
        moemail_api_url: cfg.moemail_api_url,
        moemail_api_key: cfg.moemail_api_key,
        skymail_api_base: cfg.skymail_api_base,
        skymail_token: cfg.skymail_token,
        skymail_domain: cfg.skymail_domain,
        cloudmail_api_base: cfg.cloudmail_api_base,
        cloudmail_admin_email: cfg.cloudmail_admin_email,
        cloudmail_admin_password: cfg.cloudmail_admin_password,
        cloudmail_domain: cfg.cloudmail_domain,
        cloudmail_subdomain: cfg.cloudmail_subdomain,
        cloudmail_timeout: cfg.cloudmail_timeout,
        duckmail_address: cfg.duckmail_address,
        duckmail_password: cfg.duckmail_password,
        duckmail_api_url: cfg.duckmail_api_url,
        duckmail_provider_url: cfg.duckmail_provider_url,
        duckmail_bearer: cfg.duckmail_bearer,
        freemail_api_url: cfg.freemail_api_url,
        freemail_admin_token: cfg.freemail_admin_token,
        freemail_username: cfg.freemail_username,
        freemail_password: cfg.freemail_password,
        freemail_domain: cfg.freemail_domain,
        cfworker_api_url: cfg.cfworker_api_url,
        cfworker_admin_token: cfg.cfworker_admin_token,
        cfworker_custom_auth: cfg.cfworker_custom_auth,
        cfworker_domain: cfg.cfworker_domain,
        cfworker_subdomain: cfg.cfworker_subdomain,
        cfworker_random_subdomain: parseBooleanConfigValue(cfg.cfworker_random_subdomain),
        cfworker_random_name_subdomain: parseBooleanConfigValue(cfg.cfworker_random_name_subdomain),
        cfworker_fingerprint: cfg.cfworker_fingerprint,
        smstome_cookie: cfg.smstome_cookie,
        smstome_country_slugs: cfg.smstome_country_slugs,
        smstome_phone_attempts: cfg.smstome_phone_attempts,
        smstome_otp_timeout_seconds: cfg.smstome_otp_timeout_seconds,
        smstome_poll_interval_seconds: cfg.smstome_poll_interval_seconds,
        smstome_sync_max_pages_per_country: cfg.smstome_sync_max_pages_per_country,
        luckmail_base_url: cfg.luckmail_base_url,
        luckmail_api_key: cfg.luckmail_api_key,
        luckmail_email_type: cfg.luckmail_email_type,
        luckmail_domain: cfg.luckmail_domain,
      }
      const chatgptRegistrationRequestAdapter =
        buildChatGPTRegistrationRequestAdapter(
          currentPlatform,
          chatgptRegistrationMode,
        )
      const adaptedRegisterExtra = chatgptRegistrationRequestAdapter
        ? chatgptRegistrationRequestAdapter.extendExtra(registerExtra)
        : registerExtra

      const res = await apiFetch('/tasks/register', {
        method: 'POST',
        body: JSON.stringify({
          platform: currentPlatform,
          count: values.count,
          concurrency: values.concurrency,
          register_delay_seconds: values.register_delay_seconds || 0,
          executor_type: executorType,
          captcha_solver: cfg.default_captcha_solver || 'yescaptcha',
          proxy: null,
          extra: adaptedRegisterExtra,
        }),
      })
      setTaskId(res.task_id)
    } finally {
      setRegisterLoading(false)
    }
  }

  const handleDetailSave = async () => {
    const values = await detailForm.validateFields()
    await apiFetch(`/accounts/${currentAccount.id}`, {
      method: 'PATCH',
      body: JSON.stringify(values),
    })
    message.success('保存成功')
    setDetailModalOpen(false)
    load()
  }

  const showCpaSyncResult = (title: string, result: any) => {
    const lines = (result.items || [])
      .flatMap((item: any) =>
        (item.results || []).map((syncResult: any) => ({
          email: item.email,
          platform: item.platform,
          ok: Boolean(syncResult.ok),
          name: syncResult.name || 'CPA',
          msg: syncResult.msg || '',
        })),
      )
      .filter((item: any) => !item.ok)
      .map((item: any) => `[${item.platform}] ${item.email || '-'} / ${item.name}: ${item.msg || '失败'}`)

    if (lines.length === 0) return

    Modal.info({
      title,
      width: 760,
      content: (
        <pre
          style={{
            margin: 0,
            maxHeight: 360,
            overflow: 'auto',
            padding: 12,
            borderRadius: 8,
            background: 'rgba(127,127,127,0.08)',
            fontSize: 12,
            lineHeight: 1.5,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {lines.join('\n')}
        </pre>
      ),
    })
  }

  const showBatchActionResult = (title: string, result: any) => {
    const lines = (result.items || [])
      .filter((item: any) => !item.ok)
      .map((item: any) => `[${item.id || '-'}] ${item.email || '-'}: ${item.message || '失败'}`)

    if (lines.length === 0) return

    Modal.info({
      title,
      width: 760,
      content: (
        <pre
          style={{
            margin: 0,
            maxHeight: 360,
            overflow: 'auto',
            padding: 12,
            borderRadius: 8,
            background: 'rgba(127,127,127,0.08)',
            fontSize: 12,
            lineHeight: 1.5,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {lines.join('\n')}
        </pre>
      ),
    })
  }

  const handleCpaBackfill = async (mode: 'pending' | 'selected') => {
    if (currentPlatform !== 'chatgpt') return

    const body: Record<string, unknown> = {
      platforms: ['chatgpt'],
    }

    if (mode === 'selected') {
      const accountIds = Array.from(selectedRowKeys)
        .map((value) => Number(value))
        .filter((value) => Number.isInteger(value) && value > 0)

      if (accountIds.length === 0) {
        message.warning('请先选择要上传的账号')
        return
      }
      body.account_ids = accountIds
    } else {
      body.pending_only = true
      if (filterStatus) body.status = filterStatus
      if (search) body.email = search
    }

    setCpaSyncLoading(mode)
    try {
      const result = await apiFetch('/integrations/backfill', {
        method: 'POST',
        body: JSON.stringify(body),
      })

      const actionLabel = mode === 'selected'
        ? t('所选账号远端补传', 'Backfill selected accounts')
        : t('远端未发现账号补传', 'Backfill accounts missing remotely')
      if (!result.total) {
        message.info(t('没有可处理的账号', 'No accounts to process'))
      } else if (!result.failed && !result.skipped) {
        message.success(t(`${actionLabel}完成：成功 ${result.success} / ${result.total}`, `${actionLabel} completed: success ${result.success} / ${result.total}`))
      } else if (!result.failed) {
        message.success(t(`${actionLabel}完成：成功 ${result.success}，跳过 ${result.skipped} / ${result.total}`, `${actionLabel} completed: success ${result.success}, skipped ${result.skipped} / ${result.total}`))
      } else if (!result.success) {
        message.error(t(`${actionLabel}失败：成功 ${result.success}，跳过 ${result.skipped} / ${result.total}`, `${actionLabel} failed: success ${result.success}, skipped ${result.skipped} / ${result.total}`))
      } else {
        message.warning(t(`${actionLabel}部分完成：成功 ${result.success}，跳过 ${result.skipped} / ${result.total}`, `${actionLabel} partially completed: success ${result.success}, skipped ${result.skipped} / ${result.total}`))
      }

      showCpaSyncResult(t(`${actionLabel}结果`, `${actionLabel} result`), result)
      await load()
    } catch (e: any) {
      message.error(t(`CPA 上传失败: ${e.message}`, `CPA upload failed: ${e.message}`))
    } finally {
      setCpaSyncLoading('')
    }
  }

  const handleBatchStatusSync = async (kind: 'probe' | 'remote', scope: 'selected' | 'all') => {
    if (currentPlatform !== 'chatgpt') return

    const loadingKey = `${kind}_${scope}` as typeof statusSyncLoading
    const actionId = kind === 'probe' ? 'probe_local_status' : 'sync_cliproxyapi_status'
    const actionLabel = kind === 'probe'
      ? t('本地状态同步', 'Local status sync')
      : t('CLIProxyAPI 状态同步', 'CLIProxyAPI status sync')
    const scopeLabel = scope === 'selected' ? t('所选账号', 'Selected accounts') : t('当前筛选账号', 'Current filtered accounts')
    const toastKey = `status-sync:${loadingKey}`

    const body: Record<string, unknown> = {
      params: {},
    }

    if (scope === 'selected') {
      const accountIds = Array.from(selectedRowKeys)
        .map((value) => Number(value))
        .filter((value) => Number.isInteger(value) && value > 0)

      if (accountIds.length === 0) {
        message.warning(t('请先选择要同步的账号', 'Select accounts to sync first'))
        return
      }
      body.account_ids = accountIds
    } else {
      body.all_filtered = true
      if (search) body.email = search
      if (filterStatus) body.status = filterStatus
    }

    setStatusSyncLoading(loadingKey)
    message.loading({ content: `${scopeLabel}${actionLabel}进行中...`, key: toastKey, duration: 0 })
    try {
      const result = await apiFetch(`/actions/${currentPlatform}/${actionId}/batch`, {
        method: 'POST',
        body: JSON.stringify(body),
      })

      if (!result.total) {
        message.info({ content: '没有可处理的账号', key: toastKey })
      } else if (!result.failed) {
        message.success({ content: `${scopeLabel}${actionLabel}完成：成功 ${result.success} / ${result.total}`, key: toastKey })
      } else if (!result.success) {
        message.error({ content: `${scopeLabel}${actionLabel}失败：成功 ${result.success} / ${result.total}`, key: toastKey })
      } else {
        message.warning({ content: `${scopeLabel}${actionLabel}部分完成：成功 ${result.success} / ${result.total}`, key: toastKey })
      }

      showBatchActionResult(`${scopeLabel}${actionLabel}结果`, result)
      await load()
    } catch (e: any) {
      message.error({ content: `${actionLabel}失败: ${e.message}`, key: toastKey })
    } finally {
      setStatusSyncLoading('')
    }
  }

  const getStatusSyncScope = (): 'selected' | 'all' => (selectedRowKeys.length > 0 ? 'selected' : 'all')

  const getBackfillScope = (): 'selected' | 'pending' => (selectedRowKeys.length > 0 ? 'selected' : 'pending')

  const backfillButtonLabel = () => {
    const scope = getBackfillScope()
    const count = scope === 'selected' ? selectedRowKeys.length : total
    return scope === 'selected' ? `补传所选远端未发现 (${count})` : `补传远端未发现 (${count})`
  }

  const isChatgptPlatform = currentPlatform === 'chatgpt'
  const monospaceStyle: React.CSSProperties = {
    fontFamily: 'SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
    fontSize: 12,
  }
  const secondaryTextStyle: React.CSSProperties = {
    fontSize: 12,
    color: token.colorTextSecondary,
  }
  const cellStackStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
    minWidth: 0,
  }
  const secretPreviewStyle: React.CSSProperties = {
    ...monospaceStyle,
    filter: 'blur(4px)',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    maxWidth: '100%',
    opacity: 0.9,
  }
  const compactPanelStyle: React.CSSProperties = {
    padding: '8px 10px',
    borderRadius: token.borderRadiusLG,
    border: `1px solid ${token.colorBorder}`,
    background: token.colorFillAlter,
  }

  const columns: any[] = [
    {
      title: t('邮箱', 'Email'),
      dataIndex: 'email',
      key: 'email',
      width: 260,
      render: (text: string, record: any) => (
        <div style={cellStackStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
            <Text
              style={{ ...monospaceStyle, flex: 1, minWidth: 0, whiteSpace: 'nowrap' }}
              ellipsis={{ tooltip: text }}
            >
              {text}
            </Text>
            <Button type="text" size="small" icon={<CopyOutlined />} onClick={() => copyText(text)} />
          </div>
          <Text type="secondary" style={secondaryTextStyle} ellipsis={{ tooltip: record.user_id || `账号 #${record.id}` }}>
            {record.user_id ? `UID: ${record.user_id}` : `账号 #${record.id}`}
          </Text>
        </div>
      ),
    },
    {
      title: t('密码', 'Password'),
      dataIndex: 'password',
      key: 'password',
      width: 150,
      render: (text: string) => (
        <Space size={6} style={{ width: '100%', justifyContent: 'space-between' }}>
          <Text style={{ ...secretPreviewStyle, maxWidth: 90 }} title={text}>
            {text}
          </Text>
          <Button type="text" size="small" icon={<CopyOutlined />} onClick={() => copyText(text)} />
        </Space>
      ),
    },
    {
      title: t('RT', 'RT'),
      key: 'refresh_token',
      width: 120,
      render: (_: any, record: any) => {
        const rt = getRefreshToken(record)
        if (!rt) return <span style={{ color: '#ccc' }}>-</span>
        return (
          <Space size={6} style={{ width: '100%', justifyContent: 'space-between' }}>
            <Text style={{ ...secretPreviewStyle, fontSize: 11, maxWidth: 58 }} title={rt}>
              {rt}
            </Text>
            <Button type="text" size="small" icon={<CopyOutlined />} onClick={() => copyText(rt)} />
          </Space>
        )
      },
    },
    {
      title: t('状态', 'Status'),
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (status: string) => <Tag color={STATUS_COLORS[status] || 'default'}>{status}</Tag>,
    },
  ]

  if (isChatgptPlatform) {
    columns.push(
      {
        title: t('本地状态', 'Local status'),
        key: 'chatgpt_local_state',
        width: 320,
        render: (_: any, record: any) => {
          const auth = record.chatgptLocal?.auth || {}
          const subscription = record.chatgptLocal?.subscription || {}
          const codex = record.chatgptLocal?.codex || {}
          const cpaSync = record.cpaSync || {}
          const sub2apiSync = record.sub2apiSync || {}
          const authMeta = authStateMeta(auth.state, english)
          const planTag = planMeta(subscription.plan, english)
          const codexMeta = codexStateMeta(codex.state, english)
          const cpaMeta = uploadSyncMeta(cpaSync, english)
          const sub2apiMeta = uploadSyncMeta(sub2apiSync, english)

          return (
            <div style={{ ...cellStackStyle, ...compactPanelStyle }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                <Tag color={authMeta.color}>{authMeta.label}</Tag>
                <Tag color={planTag.color}>{planTag.label}</Tag>
                <Tag color={codexMeta.color}>Codex {codexMeta.label}</Tag>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                <Tag color={cpaMeta.color} title={uploadSyncTitle('CPA', cpaSync, english)}>
                  CPA {cpaMeta.label}
                </Tag>
                <Tag color={sub2apiMeta.color} title={uploadSyncTitle('Sub2API', sub2apiSync, english)}>
                  Sub2API {sub2apiMeta.label}
                </Tag>
              </div>
            </div>
          )
        },
      },
      {
        title: 'CLIProxyAPI',
        key: 'cliproxy_sync',
        width: 170,
        render: (_: any, record: any) => {
          const sync = record.cliproxySync || {}
          const meta = cliproxyStateMeta(sync, english)

          return (
            <div style={{ ...cellStackStyle, ...compactPanelStyle }}>
              <Tag color={meta.color}>{meta.label}</Tag>
            </div>
          )
        },
      },
    )
  } else {
    columns.push(
      {
        title: t('地区', 'Region'),
        dataIndex: 'region',
        key: 'region',
        width: 100,
        render: (text: string) => text || '-',
      },
      {
        title: t('试用链接', 'Trial link'),
        dataIndex: 'cashier_url',
        key: 'cashier_url',
        width: 120,
        render: (url: string) =>
          url ? (
            <Space size={0}>
              <Button type="text" size="small" icon={<CopyOutlined />} onClick={() => copyText(url)} />
              <Button type="text" size="small" icon={<LinkOutlined />} onClick={() => window.open(url, '_blank')} />
            </Space>
          ) : (
            '-'
          ),
      },
    )
  }

  columns.push(
    {
      title: t('注册时间', 'Registration time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 132,
      render: (text: string) => {
        const formatted = formatCreatedAt(text)
        return (
          <div style={cellStackStyle}>
            <Text style={{ fontSize: 13 }}>{formatted.date}</Text>
            {formatted.time ? <Text type="secondary" style={secondaryTextStyle}>{formatted.time}</Text> : null}
          </div>
        )
      },
    },
    {
      title: t('操作', 'Actions'),
      key: 'action',
      width: 150,
        fixed: isChatgptPlatform ? 'right' : undefined,
        render: (_: any, record: any) => (
        <Space size={4} wrap>
          <Button type="link" size="small" onClick={() => { setCurrentAccount(record); setDetailModalOpen(true); }}>
            {t('详情', 'Details')}
          </Button>
          <Popconfirm
            title={t('确认删除该账号吗？', 'Delete this account?')}
            onConfirm={() => handleDelete(record.id)}
            okText={t('删除', 'Delete')}
            cancelText={t('取消', 'Cancel')}
            okButtonProps={{ danger: true }}
          >
            <Button type="link" size="small" danger>
              {t('删除', 'Delete')}
            </Button>
          </Popconfirm>
          <ActionMenu acc={record} onRefresh={load} actions={platformActions} />
        </Space>
      ),
    },
  )

  const statusSyncMenuItems: MenuProps['items'] = [
    {
      key: `probe:${getStatusSyncScope()}`,
      label:
        getStatusSyncScope() === 'selected'
          ? t(`同步所选本地状态 (${selectedRowKeys.length})`, `Sync selected local status (${selectedRowKeys.length})`)
          : t(`同步当前筛选本地状态 (${total})`, `Sync current filtered local status (${total})`),
      disabled: getStatusSyncScope() === 'selected' ? selectedRowKeys.length === 0 : total === 0,
    },
    {
      key: `remote:${getStatusSyncScope()}`,
      label:
        getStatusSyncScope() === 'selected'
          ? t(`同步所选 CLIProxyAPI 状态 (${selectedRowKeys.length})`, `Sync selected CLIProxyAPI status (${selectedRowKeys.length})`)
          : t(`同步当前筛选 CLIProxyAPI 状态 (${total})`, `Sync current filtered CLIProxyAPI status (${total})`),
      disabled: getStatusSyncScope() === 'selected' ? selectedRowKeys.length === 0 : total === 0,
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <Space>
          <Input.Search
            placeholder={t('搜索邮箱...', 'Search email...')}
            allowClear
            onSearch={(v) => { setPage(1); setSearch(v) }}
            style={{ width: 200 }}
          />
          <Select
            placeholder={t('状态筛选', 'Status filter')}
            allowClear
            style={{ width: 120 }}
            onChange={(v) => { setPage(1); setFilterStatus(v) }}
            options={[
              { value: 'registered', label: t('已注册', 'Registered') },
              { value: 'trial', label: t('试用中', 'Trial') },
              { value: 'subscribed', label: t('已订阅', 'Subscribed') },
              { value: 'expired', label: t('已过期', 'Expired') },
              { value: 'invalid', label: t('已失效', 'Invalid') },
            ]}
          />
          <DatePicker
            showTime
            allowClear
            placeholder={t('开始时间', 'Start time')}
            onChange={(value) => { setPage(1); setCreatedAtStart(value ? value.toISOString() : '') }}
          />
          <DatePicker
            showTime
            allowClear
            placeholder={t('结束时间', 'End time')}
            onChange={(value) => { setPage(1); setCreatedAtEnd(value ? value.toISOString() : '') }}
          />
          <Text type="secondary">{t(`${total} 个账号`, `${total} accounts`)}</Text>
          {selectedRowKeys.length > 0 && (
            <Text type="success">{t(`已选 ${selectedRowKeys.length} 个`, `${selectedRowKeys.length} selected`)}</Text>
          )}
        </Space>
        <Space>
          {currentPlatform === 'chatgpt' && (
            <Dropdown
              trigger={['click']}
              menu={{
                items: statusSyncMenuItems,
                onClick: ({ key }) => {
                  const [kind, scope] = String(key).split(':') as ['probe' | 'remote', 'selected' | 'all']
                  handleBatchStatusSync(kind, scope)
                },
              }}
            >
              <Button
                icon={<SyncOutlined />}
                loading={statusSyncLoading !== ''}
                disabled={total === 0}
              >
                {t('状态同步', 'Sync status')}
              </Button>
            </Dropdown>
          )}
          {currentPlatform === 'chatgpt' && (
            <Popconfirm
              title={
                getBackfillScope() === 'selected'
                  ? t(`确认补传所选 ${selectedRowKeys.length} 个账号中远端未发现的 auth-file？`, `Backfill auth-file for the ${selectedRowKeys.length} selected accounts not found remotely?`)
                  : t('确认补传当前筛选范围内远端未发现且本地状态有效的账号？', 'Backfill accounts in the current filter that are missing remotely and still valid locally?')
              }
              onConfirm={() => handleCpaBackfill(getBackfillScope())}
              okText={t('确认', 'Confirm')}
              cancelText={t('取消', 'Cancel')}
            >
              <Button
                loading={cpaSyncLoading === 'pending' || cpaSyncLoading === 'selected'}
                icon={<UploadOutlined />}
                disabled={getBackfillScope() === 'selected' ? selectedRowKeys.length === 0 : total === 0}
              >
                {backfillButtonLabel()}
              </Button>
            </Popconfirm>
          )}
          {selectedRowKeys.length > 0 && (
            <Popconfirm
              title={t(`确认删除选中的 ${selectedRowKeys.length} 个账号？`, `Delete the selected ${selectedRowKeys.length} accounts?`)}
              onConfirm={handleBatchDelete}
              okText={t('删除', 'Delete')}
              cancelText={t('取消', 'Cancel')}
              okButtonProps={{ danger: true }}
            >
              <Button danger icon={<DeleteOutlined />}>{t(`删除 ${selectedRowKeys.length} 个`, `Delete ${selectedRowKeys.length}`)}</Button>
            </Popconfirm>
          )}
          <Button icon={<UploadOutlined />} onClick={() => setImportModalOpen(true)}>{t('导入', 'Import')}</Button>
          <Button icon={<DownloadOutlined />} onClick={exportCsv} disabled={accounts.length === 0}>{t('导出', 'Export')}</Button>
          <Button icon={<PlusOutlined />} onClick={() => setAddModalOpen(true)}>{t('新增', 'Add')}</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setRegisterModalOpen(true)}>{t('注册', 'Register')}</Button>
          <Button icon={<ReloadOutlined spin={loading} />} onClick={load} />
        </Space>
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={accounts}
        loading={loading}
        size="middle"
        rowSelection={{
          selectedRowKeys,
          onChange: setSelectedRowKeys,
        }}
        pagination={{ total, current: page, pageSize, showSizeChanger: true, pageSizeOptions: ['20', '50', '100'], onChange: (p, ps) => { setPage(p); setPageSize(ps) } }}
        scroll={{ x: isChatgptPlatform ? 1440 : 980 }}
        onRow={(record) => ({
          onDoubleClick: () => {
            setCurrentAccount(record)
            setDetailModalOpen(true)
          },
        })}
      />

      <Modal
        title={t(`注册 ${currentPlatform}`, `Register ${currentPlatform}`)}
        open={registerModalOpen}
        onCancel={() => { setRegisterModalOpen(false); setTaskId(null); registerForm.resetFields(); }}
        footer={null}
        width={500}
        maskClosable={false}
      >
        {!taskId ? (
          <Form form={registerForm} layout="vertical" onFinish={handleRegister}>
            <Form.Item name="count" label={t('注册数量', 'Quantity')} initialValue={1} rules={[{ required: true }]}>
              <Input type="number" min={1} />
            </Form.Item>
            <Form.Item name="concurrency" label={t('并发数', 'Concurrency')} initialValue={1} rules={[{ required: true }]}>
              <Input type="number" min={1} />
            </Form.Item>
            <Form.Item name="register_delay_seconds" label={t('每个注册延迟(秒)', 'Delay per registration (s)')} initialValue={0}>
              <InputNumber min={0} precision={1} step={0.5} style={{ width: '100%' }} placeholder={t('0 = 不延迟', '0 = no delay')} />
            </Form.Item>
            {currentPlatform === 'chatgpt' && (
              <Form.Item label={t('ChatGPT Token 方案', 'ChatGPT token mode')}>
                <ChatGPTRegistrationModeSwitch
                  mode={chatgptRegistrationMode}
                  onChange={setChatgptRegistrationMode}
                />
              </Form.Item>
            )}
            <Form.Item>
              <Button type="primary" htmlType="submit" block loading={registerLoading}>
                {t('开始注册', 'Start registration')}
              </Button>
            </Form.Item>
          </Form>
        ) : (
          <TaskLogPanel taskId={taskId} onDone={() => { load(); }} />
        )}
      </Modal>

      <Modal
        title={t('手动新增账号', 'Add account manually')}
        open={addModalOpen}
        onCancel={() => { setAddModalOpen(false); addForm.resetFields(); }}
        onOk={handleAdd}
        maskClosable={false}
      >
        <Form form={addForm} layout="vertical">
          <Form.Item name="email" label={t('邮箱', 'Email')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="password" label={t('密码', 'Password')} rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="token" label="Token">
            <Input />
          </Form.Item>
          <Form.Item name="cashier_url" label={t('试用链接', 'Trial link')}>
            <Input />
          </Form.Item>
          <Form.Item name="status" label={t('状态', 'Status')} initialValue="registered">
            <Select
              options={[
                { value: 'registered', label: t('已注册', 'Registered') },
                { value: 'trial', label: t('试用中', 'Trial') },
                { value: 'subscribed', label: t('已订阅', 'Subscribed') },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t('批量导入', 'Bulk import')}
        open={importModalOpen}
        onCancel={() => { setImportModalOpen(false); setImportText(''); }}
        onOk={handleImport}
        confirmLoading={importLoading}
        maskClosable={false}
      >
        <p style={{ marginBottom: 8, fontSize: 12, color: '#7a8ba3' }}>
          {t('每行格式:', 'Format per line:')} <code style={{ background: 'rgba(255,255,255,0.1)', padding: '2px 4px', borderRadius: 4 }}>email password [cashier_url]</code>
        </p>
        <Input.TextArea
          value={importText}
          onChange={(e) => setImportText(e.target.value)}
          rows={8}
          style={{ fontFamily: 'monospace' }}
        />
      </Modal>

      <Modal
        title={t('账号详情', 'Account details')}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        onOk={handleDetailSave}
        maskClosable={false}
        width={760}
        styles={{ body: { maxHeight: '72vh', overflowY: 'auto' } }}
      >
        {currentAccount && (
          <>
            <Form form={detailForm} layout="vertical" initialValues={currentAccount}>
              <Form.Item name="status" label={t('状态', 'Status')}>
                <Select
                  options={[
                    { value: 'registered', label: t('已注册', 'Registered') },
                    { value: 'trial', label: t('试用中', 'Trial') },
                    { value: 'subscribed', label: t('已订阅', 'Subscribed') },
                    { value: 'expired', label: t('已过期', 'Expired') },
                    { value: 'invalid', label: t('已失效', 'Invalid') },
                  ]}
                />
              </Form.Item>
              <Form.Item name="token" label="Access Token">
                <Input.TextArea rows={2} style={{ fontFamily: 'monospace' }} />
              </Form.Item>
            </Form>
            {(() => {
              const rt = getRefreshToken(currentAccount)
              if (!rt) return null
              return (
                <div style={{ marginTop: 8 }}>
                  <div style={{ marginBottom: 4, fontWeight: 500, fontSize: 13 }}>{t('Refresh Token', 'Refresh Token')}</div>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 8,
                      background: token.colorFillAlter,
                      border: `1px solid ${token.colorBorder}`,
                      borderRadius: token.borderRadius,
                      padding: '8px 10px',
                    }}
                  >
                    <Text
                      style={{ fontFamily: 'monospace', fontSize: 11, wordBreak: 'break-all', flex: 1, userSelect: 'text' }}
                      copyable={{ text: rt, tooltips: [t('复制 RT', 'Copy RT'), t('已复制', 'Copied')] }}
                    >
                      {rt}
                    </Text>
                  </div>
                </div>
              )
            })()}
            {currentPlatform === 'kiro' && currentAccount?.extra ? (
              <DetailSection title={t('Kiro 客户端信息', 'Kiro client info')}>
                <SummaryField label="Client ID" value={currentAccount.extra?.clientId} code />
                <SummaryField label="Client Secret" value={currentAccount.extra?.clientSecret} code />
              </DetailSection>
            ) : null}
            {currentPlatform === 'chatgpt' ? (
              <DetailSection title={t('本地真实状态', 'Local real status')}>
                {currentAccount.chatgptLocal && Object.keys(currentAccount.chatgptLocal).length > 0 ? (
                  <LocalProbeSummary probe={currentAccount.chatgptLocal} />
                ) : (
                  <Text type="secondary">{t('尚未探测。可在操作菜单中点击“探测本地状态”。', 'Not probed yet. Use the action menu to probe local status.')}</Text>
                )}
              </DetailSection>
            ) : null}
            {currentPlatform === 'chatgpt' ? (
              <DetailSection title={t('CLIProxyAPI 状态', 'CLIProxyAPI status')}>
                {currentAccount.cliproxySync && Object.keys(currentAccount.cliproxySync).length > 0 ? (
                  <CliproxySyncSummary sync={currentAccount.cliproxySync} />
                ) : (
                  <Text type="secondary">{t('尚未同步。可在操作菜单中点击“同步 CLIProxyAPI 状态”。', 'Not synced yet. Use the action menu to sync CLIProxyAPI status.')}</Text>
                )}
              </DetailSection>
            ) : null}
          </>
        )}
      </Modal>
    </div>
  )
}
