import { useEffect, useRef, useState } from 'react'
import { App, Card, Form, Input, Select, Button, message, Tabs, Space, Tag, Typography, Modal, QRCode, Switch, Alert } from 'antd'
import {
  SaveOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  MailOutlined,
  SafetyOutlined,
  ApiOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  PlusOutlined,
  LockOutlined,
} from '@ant-design/icons'
import { parseBooleanConfigValue } from '@/lib/configValueParsers'
import { apiFetch } from '@/lib/utils'

const SELECT_FIELDS: Record<string, { label: string; value: string }[]> = {
  mail_provider: [
    { label: 'LuckMail（订单接码 / 已购邮箱）', value: 'luckmail' },
    { label: 'Outlook（本地导入）', value: 'outlook' },
    { label: 'AppleMail（小苹果 / 本地邮箱池）', value: 'applemail' },
    { label: 'Laoudo（固定邮箱）', value: 'laoudo' },
    { label: 'TempMail.lol（自动生成）', value: 'tempmail_lol' },
    { label: 'SkyMail（CloudMail 接口）', value: 'skymail' },
    { label: 'CloudMail（genToken 口令模式）', value: 'cloudmail' },
    { label: 'DuckMail（自动生成）', value: 'duckmail' },
    { label: 'MoeMail (sall.cc)', value: 'moemail' },
    { label: 'YYDS Mail / MaliAPI', value: 'maliapi' },
    { label: 'GPTMail', value: 'gptmail' },
    { label: 'OpenTrashMail', value: 'opentrashmail' },
    { label: 'Freemail（自建 CF Worker）', value: 'freemail' },
    { label: 'CF Worker（自建域名）', value: 'cfworker' },
  ],
  maliapi_auto_domain_strategy: [
    { label: 'balanced', value: 'balanced' },
    { label: 'prefer_owned', value: 'prefer_owned' },
    { label: 'prefer_public', value: 'prefer_public' },
  ],
  default_executor: [
    { label: 'API 协议（无浏览器）', value: 'protocol' },
    { label: '无头浏览器', value: 'headless' },
    { label: '有头浏览器', value: 'headed' },
  ],
  default_captcha_solver: [
    { label: 'YesCaptcha', value: 'yescaptcha' },
    { label: '本地 Solver (Camoufox)', value: 'local_solver' },
    { label: '手动', value: 'manual' },
  ],
  cpa_cleanup_enabled: [
    { label: '关闭', value: '0' },
    { label: '开启', value: '1' },
  ],
  codex_proxy_upload_type: [
    { label: 'AT（Access Token，推荐）', value: 'at' },
    { label: 'RT（Refresh Token）', value: 'rt' },
  ],
}

const TAB_ITEMS = [
  {
    key: 'register',
    label: '注册设置',
    icon: <ApiOutlined />,
    sections: [
      {
        title: '默认注册方式',
        desc: '控制注册任务如何执行',
        fields: [{ key: 'default_executor', label: '执行器类型', type: 'select' }],
      },
    ],
  },
  {
    key: 'mailbox',
    label: '邮箱服务',
    icon: <MailOutlined />,
    sections: [
      {
        title: '默认邮箱服务',
        desc: '选择注册时使用的邮箱类型',
        fields: [
          { key: 'mail_provider', label: '邮箱服务', type: 'select' },
          { key: 'mailbox_otp_timeout_seconds', label: '邮箱验证码等待秒数', placeholder: '例如 60 / 90 / 120' },
        ],
      },
      {
        title: 'Laoudo',
        desc: '固定邮箱，手动配置',
        fields: [
          { key: 'laoudo_email', label: '邮箱地址', placeholder: 'xxx@laoudo.com' },
          { key: 'laoudo_account_id', label: 'Account ID', placeholder: '563' },
          { key: 'laoudo_auth', label: 'JWT Token', placeholder: 'eyJ...', secret: true },
        ],
      },
      {
        title: 'Freemail',
        desc: '基于 Cloudflare Worker 的自建邮箱，支持管理员令牌或账号密码认证',
        fields: [
          { key: 'freemail_api_url', label: 'API URL', placeholder: 'https://mail.example.com' },
          { key: 'freemail_admin_token', label: '管理员令牌', secret: true },
          { key: 'freemail_username', label: '用户名（可选）' },
          { key: 'freemail_password', label: '密码（可选）', secret: true },
          { key: 'freemail_domain', label: '邮箱域名（可选）', placeholder: 'example.com' },
        ],
      },
      {
        title: 'MoeMail',
        desc: '自动注册账号并生成临时邮箱',
        fields: [
          { key: 'moemail_api_url', label: 'API URL', placeholder: 'https://sall.cc' },
          { key: 'moemail_api_key', label: 'API Key', secret: true },
        ],
      },
      {
        title: 'SkyMail',
        desc: 'CloudMail 兼容接口（addUser / emailList）',
        fields: [
          { key: 'skymail_api_base', label: 'API Base', placeholder: 'https://api.skymail.ink' },
          { key: 'skymail_token', label: 'Authorization Token', secret: true },
          { key: 'skymail_domain', label: '邮箱域名', placeholder: 'mail.example.com' },
        ],
      },
      {
        title: 'CloudMail',
        desc: 'CloudMail 口令模式（genToken + emailList）',
        fields: [
          { key: 'cloudmail_api_base', label: 'API Base', placeholder: 'https://cloudmail.example.com' },
          { key: 'cloudmail_admin_email', label: '管理员邮箱（可选）', placeholder: 'admin@example.com' },
          { key: 'cloudmail_admin_password', label: '管理员密码', secret: true },
          { key: 'cloudmail_domain', label: '邮箱域名（可选）', placeholder: 'mail.example.com,mail2.example.com' },
          { key: 'cloudmail_subdomain', label: '子域名（可选）', placeholder: 'pool-a' },
          { key: 'cloudmail_timeout', label: '请求超时秒数', placeholder: '30' },
        ],
      },
      {
        title: 'YYDS Mail / MaliAPI',
        desc: '基于 API Key 创建临时邮箱并轮询收件箱消息',
        fields: [
          { key: 'maliapi_base_url', label: 'API URL', placeholder: 'https://maliapi.215.im/v1' },
          { key: 'maliapi_api_key', label: 'API Key', secret: true },
          { key: 'maliapi_domain', label: '邮箱域名（可选）', placeholder: 'example.com' },
          { key: 'maliapi_auto_domain_strategy', label: '自动域名策略', type: 'select' },
        ],
      },
      {
        title: 'AppleMail / 小苹果',
        desc: '读取本地邮箱池文件，通过 refresh_token + client_id 调用小苹果取件接口；支持在本页直接导入 JSON',
        fields: [
          { key: 'applemail_base_url', label: 'API URL', placeholder: 'https://www.appleemail.top' },
          { key: 'applemail_pool_dir', label: '邮箱池目录', placeholder: 'mail' },
          { key: 'applemail_pool_file', label: '当前邮箱池文件（可选）', placeholder: '留空则自动读取目录中最新文件' },
          { key: 'applemail_mailboxes', label: '轮询文件夹', placeholder: 'INBOX,Junk' },
        ],
      },
      {
        title: 'GPTMail',
        desc: '基于 GPTMail API 生成临时邮箱并轮询邮件；若已知本站可用域名，也可本地拼装随机地址',
        fields: [
          { key: 'gptmail_base_url', label: 'API URL', placeholder: 'https://mail.chatgpt.org.uk' },
          { key: 'gptmail_api_key', label: 'API Key', secret: true, placeholder: 'gpt-test' },
          { key: 'gptmail_domain', label: '邮箱域名（可选）', placeholder: 'example.com' },
        ],
      },
      {
        title: 'OpenTrashMail',
        desc: '对接 opentrashmail 服务；可直接轮询 /json/<email>，也支持已知域名时本地拼装随机地址',
        fields: [
          { key: 'opentrashmail_api_url', label: 'API URL', placeholder: 'http://mail.example.com:8085' },
          { key: 'opentrashmail_domain', label: '邮箱域名（可选）', placeholder: 'xiyoufm.com' },
          { key: 'opentrashmail_password', label: '站点密码（可选）', secret: true, placeholder: '启用 PASSWORD 时填写' },
        ],
      },
      {
        title: 'TempMail.lol',
        desc: '自动生成邮箱，无需配置，需要代理访问（CN IP 被封）',
        fields: [],
      },
      {
        title: 'DuckMail',
        desc: '自动生成邮箱，随机创建账号',
        fields: [
          { key: 'duckmail_api_url', label: 'Web URL', placeholder: 'https://www.duckmail.sbs' },
          { key: 'duckmail_provider_url', label: 'Provider URL', placeholder: 'https://api.duckmail.sbs' },
          { key: 'duckmail_bearer', label: 'Bearer Token', placeholder: 'kevin273945', secret: true },
          { key: 'duckmail_domain', label: '自定义域名', placeholder: '留空则从 Provider URL 推导' },
          { key: 'duckmail_api_key', label: 'API Key（私有域名）', placeholder: 'dk_xxx（domain.duckmail.sbs 获取）', secret: true },
        ],
      },
      {
        title: 'CF Worker 自建邮箱',
        desc: '基于 Cloudflare Worker 的自建临时邮箱服务',
        fields: [
          { key: 'cfworker_api_url', label: 'API URL', placeholder: 'https://apimail.example.com' },
          { key: 'cfworker_admin_token', label: '管理员 Token', secret: true },
          { key: 'cfworker_custom_auth', label: '站点密码', secret: true },
          { key: 'cfworker_subdomain', label: '固定子域名', placeholder: 'mail / pool-a' },
          { key: 'cfworker_random_subdomain', label: '随机子域名', type: 'boolean' },
          { key: 'cfworker_random_name_subdomain', label: '随机姓名子域名', type: 'boolean' },
          { key: 'cfworker_fingerprint', label: 'Fingerprint', placeholder: '6703363b...' },
        ],
      },
      {
        title: 'LuckMail',
        desc: 'ChatGPT 走购买邮箱，其他平台继续走订单接码老逻辑',
        fields: [
          { key: 'luckmail_base_url', label: '平台地址', placeholder: 'https://mails.luckyous.com' },
          { key: 'luckmail_api_key', label: 'API Key', secret: true },
          { key: 'luckmail_email_type', label: '邮箱类型（可选）', placeholder: 'ms_graph / ms_imap / self_built' },
          { key: 'luckmail_domain', label: '邮箱域名（可选）', placeholder: 'outlook.com / gmail.com' },
        ],
      },
    ],
  },
  {
    key: 'captcha',
    label: '验证码',
    icon: <SafetyOutlined />,
    sections: [
      {
        title: '验证码服务',
        desc: '用于绕过注册页面的人机验证',
        fields: [
          { key: 'default_captcha_solver', label: '默认服务', type: 'select' },
          { key: 'yescaptcha_key', label: 'YesCaptcha Key', secret: true },
        ],
      },
    ],
  },
  {
    key: 'chatgpt',
    label: 'ChatGPT',
    icon: <ApiOutlined />,
    sections: [
      {
        title: 'CPA 面板',
        desc: '注册完成后自动上传到 CPA 管理平台',
        fields: [
          { key: 'cpa_enabled', label: '启用自动上传', type: 'boolean' },
          { key: 'cpa_api_url', label: 'API URL', placeholder: 'https://your-cpa.example.com' },
          { key: 'cpa_api_key', label: 'API Key', secret: true },
        ],
      },
      {
        title: 'Sub2API 面板',
        desc: '注册完成后自动上传到 Sub2API 管理后台',
        fields: [
          { key: 'sub2api_enabled', label: '启用自动上传', type: 'boolean' },
          { key: 'sub2api_api_url', label: 'API URL', placeholder: 'https://your-sub2api.example.com' },
          { key: 'sub2api_api_key', label: 'API Key', secret: true },
          { key: 'sub2api_group_ids', label: '分组 ID', placeholder: '多个分组用英文逗号分隔，例如 2,4,8' },
        ],
      },
      {
        title: 'CPA 自动维护',
        desc: '定时删除 status=error 的凭证，剩余数量低于阈值时自动按现有配置补注册 ChatGPT',
        fields: [
          { key: 'cpa_cleanup_enabled', label: '自动维护', type: 'select' },
          { key: 'cpa_cleanup_interval_minutes', label: '检查间隔（分钟）', placeholder: '60' },
          { key: 'cpa_cleanup_threshold', label: '最低凭证阈值', placeholder: '5' },
          { key: 'cpa_cleanup_concurrency', label: '补注册并发数', placeholder: '1' },
          { key: 'cpa_cleanup_register_delay_seconds', label: '每个注册延迟（秒）', placeholder: '0' },
        ],
      },
      {
        title: 'Team Manager',
        desc: '上传到自建 Team Manager 系统',
        fields: [
          { key: 'team_manager_url', label: 'API URL', placeholder: 'https://your-tm.example.com' },
          { key: 'team_manager_key', label: 'API Key', secret: true },
        ],
      },
      {
        title: 'CodexProxy',
        desc: '注册完成后自动上传到 CodexProxy 管理平台',
        fields: [
          { key: 'codex_proxy_url', label: 'API URL', placeholder: 'https://your-codex-proxy.example.com' },
          { key: 'codex_proxy_key', label: 'Admin Key', secret: true },
          { key: 'codex_proxy_upload_type', label: '上传类型' },
        ],
      },
      {
        title: 'SMSToMe 手机验证',
        desc: 'ChatGPT add_phone 阶段自动取号并轮询短信验证码',
        fields: [
          { key: 'smstome_cookie', label: 'SMSToMe Cookie', secret: true },
          { key: 'smstome_country_slugs', label: '国家列表', placeholder: 'united-kingdom,poland' },
          { key: 'smstome_phone_attempts', label: '手机号尝试次数', placeholder: '3' },
          { key: 'smstome_otp_timeout_seconds', label: '短信等待秒数', placeholder: '45' },
          { key: 'smstome_poll_interval_seconds', label: '轮询间隔秒数', placeholder: '5' },
          { key: 'smstome_sync_max_pages_per_country', label: '每国同步页数', placeholder: '5' },
        ],
      },
    ],
  },
  {
    key: 'cliproxyapi',
    label: 'CLIProxyAPI',
    icon: <ApiOutlined />,
    sections: [
      {
        title: '管理面板',
        desc: '用于 CLIProxyAPI 管理页登录',
        fields: [
          { key: 'cliproxyapi_base_url', label: 'API URL', placeholder: 'http://127.0.0.1:8317' },
          { key: 'cliproxyapi_management_key', label: '管理口令', secret: true, placeholder: '默认 cliproxyapi' },
        ],
      },
    ],
  },
  {
    key: 'grok',
    label: 'Grok',
    icon: <ApiOutlined />,
    sections: [
      {
        title: 'grok2api',
        desc: '注册成功后自动导入到 grok2api 管理后台',
        fields: [
          { key: 'grok2api_url', label: 'API URL', placeholder: 'http://127.0.0.1:7860' },
          { key: 'grok2api_app_key', label: 'App Key', secret: true },
          { key: 'grok2api_pool', label: 'Token Pool', placeholder: 'ssoBasic 或 ssoSuper' },
          { key: 'grok2api_quota', label: 'Quota（可选）', placeholder: '留空按池默认值' },
        ],
      },
    ],
  },
  {
    key: 'kiro',
    label: 'Kiro',
    icon: <ApiOutlined />,
    sections: [
      {
        title: 'Kiro Account Manager',
        desc: '注册成功后自动写入 kiro-account-manager 的 accounts.json',
        fields: [
          {
            key: 'kiro_manager_path',
            label: 'accounts.json 路径（可选）',
            placeholder: '留空则自动使用系统默认路径',
          },
          {
            key: 'kiro_manager_exe',
            label: 'Kiro Manager 可执行文件（可选）',
            placeholder: '未安装 Rust 时可填写已安装的 KiroAccountManager.exe',
          },
        ],
      },
    ],
  },
  {
    key: 'contribution',
    label: '贡献',
    icon: <PlusOutlined />,
    sections: [],
  },
  {
    key: 'integrations',
    label: '插件',
    icon: <ApiOutlined />,
    sections: [],
  },
  {
    key: 'security',
    label: '安全',
    icon: <LockOutlined />,
    sections: [],
  },
]

interface FieldConfig {
  key: string
  label: string
  placeholder?: string
  type?: 'select' | 'input' | 'boolean'
  secret?: boolean
}

interface SectionConfig {
  title: string
  desc?: string
  fields: FieldConfig[]
}

interface TabConfig {
  key: string
  label: string
  icon: React.ReactNode
  sections: SectionConfig[]
}

interface AppleMailPoolPreviewItem {
  index: number
  email: string
  mailbox: string
}

interface AppleMailPoolSnapshot {
  filename: string
  pool_dir: string
  count: number
  items: AppleMailPoolPreviewItem[]
  truncated: boolean
}

const MAILBOX_SECTION_FIELD_KEY_BY_PROVIDER: Record<string, string> = {
  laoudo: 'laoudo_email',
  freemail: 'freemail_api_url',
  moemail: 'moemail_api_url',
  skymail: 'skymail_api_base',
  cloudmail: 'cloudmail_api_base',
  maliapi: 'maliapi_base_url',
  applemail: 'applemail_base_url',
  gptmail: 'gptmail_base_url',
  opentrashmail: 'opentrashmail_api_url',
  duckmail: 'duckmail_api_url',
  cfworker: 'cfworker_api_url',
  luckmail: 'luckmail_base_url',
}

const MAILBOX_SECTION_INDEX_BY_PROVIDER: Record<string, number> = {
  tempmail_lol: 10,
}

function splitMailboxSections(sections: SectionConfig[], mailProvider: string) {
  const defaultSection = sections[0] || null
  let selectedSection: SectionConfig | null = null

  const byIndex = MAILBOX_SECTION_INDEX_BY_PROVIDER[mailProvider]
  if (Number.isInteger(byIndex)) {
    selectedSection = sections[byIndex] || null
  } else {
    const fieldKey = MAILBOX_SECTION_FIELD_KEY_BY_PROVIDER[mailProvider]
    if (fieldKey) {
      selectedSection = sections.find((section) => section.fields.some((field) => field.key === fieldKey)) || null
    }
  }

  if (selectedSection === defaultSection) {
    selectedSection = null
  }

  const remainingSections = sections.filter((section) => section !== defaultSection && section !== selectedSection)

  return {
    defaultSection,
    selectedSection,
    remainingSections,
  }
}

function formatResultText(data: unknown) {
  if (typeof data === 'string') return data
  try {
    return JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

function normalizeDomainList(input: unknown): string[] {
  const items = Array.isArray(input) ? input : []
  const seen = new Set<string>()
  const domains: string[] = []
  for (const item of items) {
    const domain = String(item || '').trim().toLowerCase().replace(/^@/, '')
    if (!domain || seen.has(domain)) continue
    seen.add(domain)
    domains.push(domain)
  }
  return domains
}

function parseStoredDomainList(value: unknown): string[] {
  if (Array.isArray(value)) return normalizeDomainList(value)
  if (typeof value !== 'string') return []

  const text = value.trim()
  if (!text) return []

  try {
    const parsed = JSON.parse(text)
    if (Array.isArray(parsed)) {
      return normalizeDomainList(parsed)
    }
  } catch {}

  return normalizeDomainList(
    text
      .split('\n')
      .flatMap((line) => line.split(','))
      .map((item) => item.trim()),
  )
}

function resolveFeatureEnabledConfig(value: unknown, fallbackEnabled: boolean): boolean {
  const normalized = String(value ?? '').trim()
  if (!normalized) return fallbackEnabled
  return parseBooleanConfigValue(normalized)
}

const CONTRIBUTION_REDEEM_OPTIONS = [10, 100, 1000]

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function pickRecord(value: Record<string, unknown> | null, keys: string[]): Record<string, unknown> | null {
  if (!value) return null
  for (const key of keys) {
    const record = asRecord(value[key])
    if (record) return record
  }
  return null
}

function pickString(value: Record<string, unknown> | null, keys: string[]): string {
  if (!value) return ''
  for (const key of keys) {
    const text = String(value[key] ?? '').trim()
    if (text) return text
  }
  return ''
}

function pickNumber(value: Record<string, unknown> | null, keys: string[]): number | null {
  if (!value) return null
  for (const key of keys) {
    const raw = value[key]
    if (typeof raw === 'number' && Number.isFinite(raw)) return raw
    if (typeof raw === 'string') {
      const parsed = Number.parseFloat(raw)
      if (Number.isFinite(parsed)) return parsed
    }
  }
  return null
}

function formatDisplayNumber(value: number | null, digits = 0): string {
  if (value === null || !Number.isFinite(value)) return '-'
  return value.toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

function formatDisplayPercent(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '-'
  return `${value.toFixed(2)}%`
}

function ConfigField({ field }: { field: FieldConfig }) {
  const [showSecret, setShowSecret] = useState(false)
  const options = SELECT_FIELDS[field.key]
  const isBooleanField = field.type === 'boolean'
  const helpText =
    field.key === 'default_executor'
      ? '仅对支持的平台生效；ChatGPT、Cursor、Grok、Kiro、Tavily、Trae 支持浏览器模式，OpenBlockLabs 仅支持纯协议。'
      : undefined

  return (
    <Form.Item
      label={field.label}
      name={field.key}
      extra={helpText}
      valuePropName={isBooleanField ? 'checked' : undefined}
    >
      {options ? (
        <Select options={options} style={{ width: '100%' }} />
      ) : isBooleanField ? (
        <Switch checkedChildren="开启" unCheckedChildren="关闭" />
      ) : field.secret ? (
        <Input.Password
          placeholder={field.placeholder}
          visibilityToggle={{
            visible: !showSecret,
            onVisibleChange: setShowSecret,
          }}
          iconRender={(visible) => (visible ? <EyeOutlined /> : <EyeInvisibleOutlined />)}
        />
      ) : (
        <Input placeholder={field.placeholder} />
      )}
    </Form.Item>
  )
}

function ConfigSection({ section }: { section: SectionConfig }) {
  return (
    <Card title={section.title} extra={section.desc && <span style={{ fontSize: 12, color: '#7a8ba3' }}>{section.desc}</span>} style={{ marginBottom: 16 }}>
      {section.fields.map((field) => (
        <ConfigField key={field.key} field={field} />
      ))}
    </Card>
  )
}

function CFWorkerDomainPoolSection({ form }: { form: any }) {
  const watchedDomains = Form.useWatch('cfworker_domains', form) || []
  const watchedEnabledDomains = Form.useWatch('cfworker_enabled_domains', form) || []
  const normalizedDomains = normalizeDomainList(watchedDomains)
  const enabledDomains = normalizeDomainList(watchedEnabledDomains).filter((domain) => normalizedDomains.includes(domain))

  const updateEnabledDomains = (nextDomains: string[]) => {
    form.setFieldValue('cfworker_enabled_domains', normalizeDomainList(nextDomains))
  }

  const toggleEnabledDomain = (domain: string, checked: boolean) => {
    if (checked) {
      updateEnabledDomains([...enabledDomains, domain])
      return
    }
    updateEnabledDomains(enabledDomains.filter((item) => item !== domain))
  }

  return (
    <Card
      title="CF Worker 域名池"
      extra={<span style={{ fontSize: 12, color: '#7a8ba3' }}>注册时会从已启用域名中随机选择一个</span>}
      style={{ marginBottom: 16 }}
    >
      <Form.List name="cfworker_domains">
        {(fields, { add, remove }) => (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {fields.map((field) => (
              <Space key={field.key} align="start" style={{ display: 'flex' }}>
                <Form.Item
                  {...field}
                  label={field.name === 0 ? '全部域名' : ''}
                  style={{ flex: 1, marginBottom: 0 }}
                  rules={[
                    {
                      validator: async (_, value) => {
                        if (!String(value || '').trim()) {
                          throw new Error('请输入域名')
                        }
                      },
                    },
                  ]}
                >
                  <Input placeholder="example.com" />
                </Form.Item>
                <Button
                  danger
                  onClick={() => {
                    const currentDomains = Array.isArray(form.getFieldValue('cfworker_domains'))
                      ? [...form.getFieldValue('cfworker_domains')]
                      : []
                    const removedDomain = String(currentDomains[field.name] || '').trim().toLowerCase().replace(/^@/, '')
                    remove(field.name)
                    if (!removedDomain) return
                    const enabledDomains = normalizeDomainList(form.getFieldValue('cfworker_enabled_domains'))
                    form.setFieldValue(
                      'cfworker_enabled_domains',
                      enabledDomains.filter((domain) => domain !== removedDomain),
                    )
                  }}
                >
                  删除
                </Button>
              </Space>
            ))}
            {fields.length === 0 ? (
              <Typography.Text type="secondary">还没有配置域名。添加后即可在下方选择启用项。</Typography.Text>
            ) : null}
            <Button type="dashed" onClick={() => add('')} icon={<PlusOutlined />} block>
              添加域名
            </Button>
          </div>
        )}
      </Form.List>

      <Form.Item name="cfworker_enabled_domains" hidden>
        <Select mode="multiple" options={normalizedDomains.map((domain) => ({ label: domain, value: domain }))} />
      </Form.Item>

      <div style={{ marginTop: 16 }}>
        <div style={{ marginBottom: 8, fontWeight: 500 }}>已启用域名</div>
        {enabledDomains.length > 0 ? (
          <Space wrap>
            {enabledDomains.map((domain) => (
              <Tag
                key={domain}
                color="blue"
                closable
                onClose={(event) => {
                  event.preventDefault()
                  updateEnabledDomains(enabledDomains.filter((item) => item !== domain))
                }}
              >
                {domain}
              </Tag>
            ))}
          </Space>
        ) : (
          <Typography.Text type="secondary">暂无启用域名，点击下方域名即可启用。</Typography.Text>
        )}
      </div>

      <div style={{ marginTop: 16 }}>
        <div style={{ marginBottom: 8, fontWeight: 500 }}>点击切换启用状态</div>
        {normalizedDomains.length > 0 ? (
          <Space wrap>
            {normalizedDomains.map((domain) => (
              <Tag.CheckableTag
                key={domain}
                checked={enabledDomains.includes(domain)}
                onChange={(checked) => toggleEnabledDomain(domain, checked)}
              >
                {domain}
              </Tag.CheckableTag>
            ))}
          </Space>
        ) : (
          <Typography.Text type="secondary">请先在上方添加域名。</Typography.Text>
        )}
      </div>
      <Typography.Text type="secondary" style={{ display: 'block', marginTop: 12 }}>
        仅已启用域名会参与注册；点击已启用标签可直接移除。
      </Typography.Text>
    </Card>
  )
}

function AppleMailPoolImportSection({ form }: { form: any }) {
  const [content, setContent] = useState('')
  const [filename, setFilename] = useState('')
  const [importing, setImporting] = useState(false)
  const [snapshot, setSnapshot] = useState<AppleMailPoolSnapshot | null>(null)
  const [loadingSnapshot, setLoadingSnapshot] = useState(false)
  const watchedPoolDir = Form.useWatch('applemail_pool_dir', form) || 'mail'
  const watchedPoolFile = Form.useWatch('applemail_pool_file', form) || ''

  const loadSnapshot = async () => {
    setLoadingSnapshot(true)
    try {
      const params = new URLSearchParams()
      if (String(watchedPoolDir || '').trim()) {
        params.set('pool_dir', String(watchedPoolDir || '').trim())
      }
      if (String(watchedPoolFile || '').trim()) {
        params.set('pool_file', String(watchedPoolFile || '').trim())
      }
      const result = await apiFetch(`/config/applemail/pool?${params.toString()}`)
      setSnapshot(result)
    } catch {
      setSnapshot(null)
    } finally {
      setLoadingSnapshot(false)
    }
  }

  useEffect(() => {
    void loadSnapshot()
  }, [watchedPoolDir, watchedPoolFile])

  const handleImport = async () => {
    if (!content.trim()) {
      message.error('请输入 JSON 或 TXT 内容')
      return
    }

    setImporting(true)
    try {
      const poolDir = String(form.getFieldValue('applemail_pool_dir') || 'mail').trim() || 'mail'
      const result = await apiFetch('/config/applemail/import', {
        method: 'POST',
        body: JSON.stringify({
          content,
          filename,
          pool_dir: poolDir,
          bind_to_config: true,
        }),
      })

      form.setFieldsValue({
        mail_provider: 'applemail',
        applemail_pool_dir: result.pool_dir,
        applemail_pool_file: result.filename,
      })
      setSnapshot({
        filename: result.filename,
        pool_dir: result.pool_dir,
        count: result.count,
        items: result.items || [],
        truncated: Boolean(result.truncated),
      })
      setContent('')
      setFilename('')
      message.success(`导入成功，共 ${result.count} 个邮箱，已绑定 ${result.filename}`)
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'AppleMail 内容导入失败'
      message.error(errorMessage || 'AppleMail 内容导入失败')
    } finally {
      setImporting(false)
    }
  }

  return (
    <Card
      title="AppleMail 内容导入"
      extra={<span style={{ fontSize: 12, color: '#7a8ba3' }}>支持 JSON 或 TXT；导入后自动绑定当前邮箱池文件</span>}
      style={{ marginBottom: 16 }}
    >
      <Space direction="vertical" style={{ width: '100%' }} size={12}>
        <Typography.Text type="secondary">
          支持数组/对象 JSON，也支持 `mail/*.txt` 那种每行一条的 `email----password----client_id----refresh_token` 格式。常见字段别名如 `clientId` / `refreshToken` / `folder` 会自动规范化。
        </Typography.Text>
        <Input
          value={filename}
          onChange={(event) => setFilename(event.target.value)}
          placeholder="可选文件名，例如 applemail_hotmail.json；留空自动生成"
        />
        <Input.TextArea
          value={content}
          onChange={(event) => setContent(event.target.value)}
          rows={10}
          placeholder={'[\n  {\n    "email": "demo@example.com",\n    "clientId": "xxxx",\n    "refreshToken": "xxxx",\n    "folder": "INBOX"\n  }\n]\n\n或粘贴 TXT:\ndemo@example.com----password----client_id----refresh_token'}
          style={{ fontFamily: 'monospace' }}
        />
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Button
            danger
            onClick={() => {
              setContent('')
              setFilename('')
            }}
          >
            清空
          </Button>
          <Space>
            <Button onClick={() => void loadSnapshot()} loading={loadingSnapshot}>
              刷新预览
            </Button>
            <Button type="primary" onClick={handleImport} loading={importing}>
              确认导入
            </Button>
          </Space>
        </Space>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <Tag color="blue">已导入: {snapshot?.count || 0} 个邮箱</Tag>
          {snapshot?.filename ? <Typography.Text type="secondary">当前文件: {snapshot.filename}</Typography.Text> : null}
        </div>

        <div
          style={{
            border: '1px solid rgba(127,127,127,0.25)',
            borderRadius: 8,
            padding: 12,
            background: 'rgba(127,127,127,0.06)',
            minHeight: 88,
            maxHeight: 260,
            overflowY: 'auto',
            fontFamily: 'monospace',
            fontSize: 13,
            lineHeight: 1.7,
          }}
        >
          {snapshot?.items?.length ? (
            snapshot.items.map((item) => (
              <div key={`${item.index}-${item.email}`}>
                {item.index}. {item.email}
              </div>
            ))
          ) : (
            <Typography.Text type="secondary">当前还没有可预览的邮箱池内容。</Typography.Text>
          )}
        </div>
        {snapshot?.truncated ? (
          <Typography.Text type="secondary">预览只展示前 100 个邮箱，完整内容以文件为准。</Typography.Text>
        ) : null}
      </Space>
    </Card>
  )
}

function SolverStatus() {
  const [running, setRunning] = useState<boolean | null>(null)

  const checkSolver = async () => {
    try {
      const d = await apiFetch('/solver/status')
      setRunning(d.running)
    } catch {
      setRunning(false)
    }
  }

  const restartSolver = async () => {
    await apiFetch('/solver/restart', { method: 'POST' })
    setRunning(null)
    setTimeout(checkSolver, 2000)
  }

  useEffect(() => {
    checkSolver()
    const timer = window.setInterval(checkSolver, 5000)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <Card title="Turnstile Solver" size="small" style={{ marginBottom: 16 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <Space size={8}>
          {running === null ? (
            <SyncOutlined spin style={{ color: '#7a8ba3' }} />
          ) : running ? (
            <CheckCircleOutlined style={{ color: '#10b981' }} />
          ) : (
            <CloseCircleOutlined style={{ color: '#ef4444' }} />
          )}
          <span style={{ color: running ? '#10b981' : '#7a8ba3', fontWeight: 500 }}>
            {running === null ? '检测中' : running ? '运行中' : '未运行'}
          </span>
        </Space>
        <Button size="small" onClick={restartSolver}>
          重启 Solver
        </Button>
      </div>
    </Card>
  )
}

function IntegrationsPanel() {
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState('')
  const saved = false
  const [resultModal, setResultModal] = useState({
    open: false,
    title: '',
    ok: true,
    content: '',
  })

  const showResultModal = (title: string, data: unknown, ok = true) => {
    setResultModal({
      open: true,
      title,
      ok,
      content: formatResultText(data),
    })
  }

  const load = async () => {
    setLoading(true)
    try {
      const d = await apiFetch('/integrations/services')
      setItems(d.items || [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 5000)
    return () => window.clearInterval(timer)
  }, [])

  const doAction = async (key: string, request: Promise<any>) => {
    setBusy(key)
    try {
      const result = await request
      await load()
      message.success('操作完成')
      showResultModal('操作结果', result, true)
    } catch (e: any) {
      message.error(e?.message || '操作失败')
      showResultModal('操作结果', e?.message || e || '操作失败', false)
      await load()
    } finally {
      setBusy('')
    }
  }

  const backfill = async (platforms: string[], label: string, busyKey: string) => {
    setBusy(busyKey)
    try {
      const d = await apiFetch('/integrations/backfill', {
        method: 'POST',
        body: JSON.stringify({ platforms }),
      })
      message.success(`${label} 回填完成：成功 ${d.success} / ${d.total}`)
      showResultModal(`${label} 回填结果`, d, true)
    } catch (e: any) {
      message.error(e?.message || `${label} 回填失败`)
      showResultModal(`${label} 回填结果`, e?.message || e || `${label} 回填失败`, false)
    } finally {
      setBusy('')
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {false ? (
        <div
          style={{
            position: 'fixed',
            left: '50%',
            bottom: 24,
            transform: 'translateX(-50%)',
            zIndex: 1000,
            width: 'min(720px, calc(100vw - 32px))',
            pointerEvents: 'none',
          }}
        >
          <div
            style={{
              width: '100%',
              padding: 0,
              borderRadius: 0,
              border: 'none',
              background: 'transparent',
              boxShadow: 'none',
              backdropFilter: 'none',
              pointerEvents: 'auto',
            }}
          >
            <Button type="primary" icon={<SaveOutlined />} onClick={() => {}} loading={false} block size="large">
              {saved ? '已保存 ✓' : '保存配置'}
            </Button>
          </div>
        </div>
      ) : null}
      <Modal
        open={resultModal.open}
        title={resultModal.title}
        onCancel={() => setResultModal((v) => ({ ...v, open: false }))}
        onOk={() => setResultModal((v) => ({ ...v, open: false }))}
        width={760}
      >
        <Typography.Paragraph style={{ marginBottom: 8, color: resultModal.ok ? '#10b981' : '#ef4444' }}>
          {resultModal.ok ? '操作已完成。' : '操作失败。'}
        </Typography.Paragraph>
        <pre
          style={{
            margin: 0,
            maxHeight: 420,
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
          {resultModal.content}
        </pre>
      </Modal>

      <Card title="批量操作">
        <Space wrap>
          <Button loading={busy === 'start-all'} onClick={() => doAction('start-all', apiFetch('/integrations/services/start-all', { method: 'POST' }))}>
            启动全部（已安装）
          </Button>
          <Button loading={busy === 'stop-all'} onClick={() => doAction('stop-all', apiFetch('/integrations/services/stop-all', { method: 'POST' }))}>
            停止全部
          </Button>
          <Button loading={loading} onClick={load}>
            刷新状态
          </Button>
        </Space>
      </Card>

      {items.map((item) => (
        <Card key={item.name} title={item.label}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <div>
              状态：
              <Tag color={item.running ? 'green' : 'default'} style={{ marginLeft: 8 }}>
                {item.running ? '运行中' : '未运行'}
              </Tag>
              <Tag color={item.repo_exists ? 'blue' : 'orange'} style={{ marginLeft: 8 }}>
                {item.repo_exists ? '已安装' : '未安装'}
              </Tag>
              {item.pid ? <span style={{ marginLeft: 8 }}>PID: {item.pid}</span> : null}
            </div>
            <div>插件目录：<Typography.Text copyable>{item.repo_path}</Typography.Text></div>
            {item.url ? <div>地址：<Typography.Text copyable>{item.url}</Typography.Text></div> : null}
            {item.management_url ? <div>管理页：<Typography.Text copyable>{item.management_url}</Typography.Text></div> : null}
            {item.management_key ? <div>登录口令：<Typography.Text copyable>{item.management_key}</Typography.Text></div> : null}
            <div>日志：<Typography.Text copyable>{item.log_path}</Typography.Text></div>
            {item.last_error ? <div style={{ color: '#ef4444' }}>最近错误：{item.last_error}</div> : null}
            <Space wrap>
              {item.management_url ? (
                <Button onClick={() => window.open(item.management_url, '_blank')}>
                  打开管理页
                </Button>
              ) : null}
              {!item.repo_exists ? (
                <Button
                  type="primary"
                  loading={busy === `install-${item.name}`}
                  onClick={() => doAction(`install-${item.name}`, apiFetch(`/integrations/services/${item.name}/install`, { method: 'POST' }))}
                >
                  安装
                </Button>
              ) : null}
              <Button
                loading={busy === `start-${item.name}`}
                disabled={!item.repo_exists}
                onClick={() => doAction(`start-${item.name}`, apiFetch(`/integrations/services/${item.name}/start`, { method: 'POST' }))}
              >
                启动
              </Button>
              <Button
                loading={busy === `stop-${item.name}`}
                onClick={() => doAction(`stop-${item.name}`, apiFetch(`/integrations/services/${item.name}/stop`, { method: 'POST' }))}
              >
                停止
              </Button>
              {item.name === 'grok2api' ? (
                <Button
                  loading={busy === 'backfill-grok'}
                  onClick={() => backfill(['grok'], 'Grok', 'backfill-grok')}
                >
                  回填现有 Grok 账号
                </Button>
              ) : null}
              {item.name === 'kiro-manager' ? (
                <Button
                  loading={busy === 'backfill-kiro'}
                  onClick={() => backfill(['kiro'], 'Kiro', 'backfill-kiro')}
                >
                  回填现有 Kiro 账号
                </Button>
              ) : null}
            </Space>
          </Space>
        </Card>
      ))}
    </div>
  )
}

function ContributionPanel({
  form,
  onSave,
  saving,
  saved,
}: {
  form: any
  onSave: () => Promise<void>
  saving: boolean
  saved: boolean
}) {
  const [loadingStats, setLoadingStats] = useState(false)
  const [redeeming, setRedeeming] = useState(false)
  const [creatingKey, setCreatingKey] = useState(false)
  const [redeemAmount, setRedeemAmount] = useState<number>(CONTRIBUTION_REDEEM_OPTIONS[0])
  const [statsResponse, setStatsResponse] = useState<Record<string, unknown> | null>(null)
  const [redeemResponse, setRedeemResponse] = useState<Record<string, unknown> | null>(null)
  const [statsError, setStatsError] = useState('')

  const contributionEnabled = Form.useWatch('contribution_enabled', form)
  const contributionServerUrl = String(Form.useWatch('contribution_server_url', form) || '').trim()
  const contributionKey = String(Form.useWatch('contribution_key', form) || '').trim()

  const rawData = asRecord(statsResponse?.['data'])
  const serverInfo = pickRecord(rawData, ['server_info', 'server', 'server_stats', 'stats']) || rawData
  const keyInfo = pickRecord(rawData, ['key_info', 'keyInfo', 'public_key_info', 'quota']) || rawData

  const keyFromStats = pickString(keyInfo, ['key', 'public_key', 'api_key']) || contributionKey
  const keyBalance =
    pickNumber(keyInfo, ['balance_usd', 'balance', 'current_balance', 'remaining_balance_usd']) ??
    pickNumber(rawData, ['balance_usd', 'balance', 'current_balance'])
  const keySource = pickString(keyInfo, ['source', 'key_source', 'origin']) || '-'
  const boundAccounts =
    pickNumber(keyInfo, ['bound_account_count', 'bind_account_count', 'bound_accounts', 'account_count']) ??
    (Array.isArray(keyInfo?.['accounts']) ? keyInfo['accounts'].length : null)
  const settlementAmount =
    pickNumber(keyInfo, ['settlement_amount_usd', 'settlement_amount', 'settled_amount_usd']) ??
    pickNumber(rawData, ['settlement_amount_usd', 'settlement_amount'])
  const serverQuotaAccountCount = pickNumber(serverInfo, ['quota_account_count'])
  const serverQuotaTotal = pickNumber(serverInfo, ['quota_total'])
  const serverQuotaUsed = pickNumber(serverInfo, ['quota_used'])
  const serverQuotaRemaining = pickNumber(serverInfo, ['quota_remaining'])
  const serverQuotaUsedPercent = pickNumber(serverInfo, ['quota_used_percent'])
  const serverQuotaRemainingPercent = pickNumber(serverInfo, ['quota_remaining_percent'])
  const serverQuotaRemainingAccounts = pickNumber(serverInfo, ['quota_remaining_accounts'])
  const redeemData = asRecord(redeemResponse?.['data']) || asRecord(redeemResponse)
  const redeemCode = pickString(redeemData, ['code', 'redeem_code', 'voucher_code'])
  const redeemedAmountUSD = pickNumber(redeemData, ['redeemed_amount_usd', 'redeemed_amount', 'amount_usd'])
  const redeemSuccessText =
    redeemResponse
      ? `提现成功！额度：${redeemedAmountUSD !== null ? formatDisplayNumber(redeemedAmountUSD, 2) : '-'} 兑换码：${redeemCode || '-'}`
      : ''

  const fetchStats = async (silent = false, keyOverride?: string) => {
    if (!contributionEnabled) {
      if (!silent) message.warning('请先开启贡献功能')
      return
    }
    if (!contributionServerUrl) {
      if (!silent) message.error('请先填写服务器地址')
      return
    }

    setLoadingStats(true)
    setStatsError('')
    try {
      const data = await apiFetch('/contribution/quota-stats', {
        method: 'POST',
        body: JSON.stringify({
          server_url: contributionServerUrl,
          key: keyOverride ?? contributionKey,
        }),
      })
      setStatsResponse(asRecord(data))
      if (!silent) {
        message.success('额度信息已刷新')
      }
    } catch (e: any) {
      const detail = String(e?.message || '获取额度信息失败')
      setStatsError(detail)
      if (!silent) {
        message.error(detail)
      }
    } finally {
      setLoadingStats(false)
    }
  }

  const doRedeem = async () => {
    if (!contributionEnabled) {
      message.warning('请先开启贡献功能')
      return
    }
    if (!contributionServerUrl) {
      message.error('请先填写服务器地址')
      return
    }
    if (!contributionKey) {
      message.error('请先填写 API Key')
      return
    }

    const confirmed = window.confirm(`确认提现吗？\n将按 ${redeemAmount} 发起提现请求`)
    if (!confirmed) return

    setRedeeming(true)
    try {
      const data = await apiFetch('/contribution/redeem', {
        method: 'POST',
        body: JSON.stringify({
          server_url: contributionServerUrl,
          key: contributionKey,
          amount_usd: redeemAmount,
        }),
      })
      const result = asRecord(data)
      const payload = asRecord(result?.['data']) || result
      const code = pickString(payload, ['code', 'redeem_code', 'voucher_code'])
      const amount = pickNumber(payload, ['redeemed_amount_usd', 'redeemed_amount', 'amount_usd'])
      setRedeemResponse(result)
      if (amount !== null || code) {
        message.success(`提现成功！额度：${amount !== null ? formatDisplayNumber(amount, 2) : '-'} 兑换码：${code || '-'}`)
      } else {
        message.success('提现成功')
      }
      await fetchStats(true)
    } catch (e: any) {
      const detail = String(e?.message || '提现失败')
      setRedeemResponse({ ok: false, error: detail })
      message.error(detail)
    } finally {
      setRedeeming(false)
    }
  }

  const doGenerateKey = async () => {
    if (!contributionServerUrl) {
      message.error('请先填写服务器地址')
      return
    }
    setCreatingKey(true)
    try {
      const result = await apiFetch('/contribution/generate-key', {
        method: 'POST',
        body: JSON.stringify({
          server_url: contributionServerUrl,
        }),
      })
      const payload = asRecord(asRecord(result)?.data)
      const generated = pickString(payload, ['key', 'api_key', 'public_key'])
      if (!generated) {
        throw new Error('服务端未返回可用 key')
      }
      form.setFieldValue('contribution_key', generated)
      message.success('已新建并填充 API Key，请点击保存配置')
      if (contributionEnabled) {
        await fetchStats(true, generated)
      }
    } catch (e: any) {
      message.error(String(e?.message || '请求新建 key 失败'))
    } finally {
      setCreatingKey(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card title="配置">
        <Alert
          type="warning"
          showIcon
          banner
          style={{ marginBottom: 12 }}
          message="开启贡献模式后，注册成功账号将只上传到贡献服务器"
          description={(
            <>
              <div>CPA / CodexProxy / Sub2API 自动上传会被停用，避免重复上报。</div>
              <div>目前该功能在xem中转站测试中 有兴趣可以进群了解</div>
              <div>中转站https://ai.xem8k5.top/ 群号634758974</div>
            </>
          )}
        />
        <Form.Item name="contribution_enabled" label="是否开启" valuePropName="checked">
          <Switch checkedChildren="开启" unCheckedChildren="关闭" />
        </Form.Item>
        <Form.Item
          name="contribution_server_url"
          label="服务器地址"
          rules={[{ required: true, message: '请输入服务器地址' }]}
        >
          <Input placeholder="http://new.xem8k5.top:7317/" />
        </Form.Item>
        <Form.Item name="contribution_key" label="API Key">
          <Input
            placeholder="留空可点击右侧按钮自动创建"
            addonAfter={(
              <Button
                type="link"
                size="small"
                loading={creatingKey}
                onClick={() => { void doGenerateKey() }}
                style={{ paddingInline: 0 }}
              >
                没有key?请求新建
              </Button>
            )}
          />
        </Form.Item>
        <Button type="primary" icon={<SaveOutlined />} onClick={onSave} loading={saving} block>
          {saved ? '已保存 ✓' : '保存配置'}
        </Button>
      </Card>

      <Card
        title="信息"
        extra={(
          <Button loading={loadingStats} onClick={() => { void fetchStats() }}>
            刷新信息
          </Button>
        )}
      >
        {!contributionEnabled ? (
          <Alert type="info" showIcon message="贡献功能已关闭，开启后可获取服务器与 key 信息。" />
        ) : (
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            {statsError ? <Alert type="error" showIcon message={statsError} /> : null}
            <div>
              <Typography.Text strong>服务器信息</Typography.Text>
              <div style={{ marginTop: 8, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
                <Tag color="blue">账号数: {formatDisplayNumber(serverQuotaAccountCount)}</Tag>
                <Tag color="geekblue">总额度: {formatDisplayNumber(serverQuotaTotal)}</Tag>
                <Tag color="volcano">已用额度: {formatDisplayNumber(serverQuotaUsed)}</Tag>
                <Tag color="green">剩余额度: {formatDisplayNumber(serverQuotaRemaining)}</Tag>
                <Tag color="orange">已用占比: {formatDisplayPercent(serverQuotaUsedPercent)}</Tag>
                <Tag color="cyan">剩余占比: {formatDisplayPercent(serverQuotaRemainingPercent)}</Tag>
                <Tag color="purple">折算账号数: {formatDisplayNumber(serverQuotaRemainingAccounts, 2)}</Tag>
              </div>
            </div>
            <div>
              <Typography.Text strong>API Key</Typography.Text>
              <Space style={{ marginLeft: 8 }}>
                <Typography.Text copyable={keyFromStats ? { text: keyFromStats } : undefined}>
                  {keyFromStats || '-'}
                </Typography.Text>
              </Space>
            </div>
            <div>
              <Typography.Text strong>key 信息</Typography.Text>
              <div style={{ marginTop: 8, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
                <Tag color="blue">余额: {keyBalance ?? '-'}</Tag>
                <Tag color="geekblue">来源: {keySource}</Tag>
                <Tag color="cyan">绑定账号数: {boundAccounts ?? '-'}</Tag>
                <Tag color="purple">结算金额: {settlementAmount ?? '-'}</Tag>
              </div>
            </div>
          </Space>
        )}
      </Card>

      <Card title="提现">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Text>key 当前额度：{keyBalance ?? '-'}</Typography.Text>
          <Form.Item label="提现金额" style={{ marginBottom: 0 }}>
            <Select
              value={redeemAmount}
              onChange={setRedeemAmount}
              style={{ width: 240 }}
              options={CONTRIBUTION_REDEEM_OPTIONS.map((amount) => ({ label: String(amount), value: amount }))}
            />
          </Form.Item>
          <Button type="primary" danger onClick={() => { void doRedeem() }} loading={redeeming}>
            提现确认
          </Button>
          {redeemResponse ? (
            <Alert
              type={redeemResponse.ok === false ? 'error' : 'success'}
              showIcon
              message={redeemResponse.ok === false ? `提现失败：${String(redeemResponse.error || '-')}` : redeemSuccessText}
              description={<pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{formatResultText(redeemResponse)}</pre>}
            />
          ) : null}
        </Space>
      </Card>
    </div>
  )
}

function OutlookImportSection() {
  const { message: msg } = App.useApp()
  const [value, setValue] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any | null>(null)

  const handleSubmit = async () => {
    const payload = String(value || '').trim()
    if (!payload) {
      msg.error('请输入 Outlook 账号内容')
      return
    }
    setLoading(true)
    try {
      const res = await apiFetch('/outlook/batch-import', {
        method: 'POST',
        body: JSON.stringify({ data: payload, enabled: true }),
      })
      setResult(res)
      msg.success(`导入完成：成功 ${res.success} / 失败 ${res.failed}`)
    } catch (e: any) {
      msg.error(e?.message || '导入失败')
      setResult({ error: e?.message || String(e) })
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card
      title="Outlook 批量导入"
      extra={<span style={{ fontSize: 12, color: '#7a8ba3' }}>每行格式：邮箱----密码 或 邮箱----密码----client_id----refresh_token</span>}
      style={{ marginBottom: 16 }}
    >
      <Input.TextArea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={`example@outlook.com----password\nexample@outlook.com----password----client_id----refresh_token`}
        autoSize={{ minRows: 6, maxRows: 14 }}
      />
      <Space style={{ marginTop: 12 }}>
        <Button type="primary" loading={loading} onClick={handleSubmit}>
          导入
        </Button>
        <Button onClick={() => { setValue(''); setResult(null) }}>
          清空
        </Button>
      </Space>
      {result ? (
        <div style={{ marginTop: 12 }}>
          {'success' in result ? (
            <Alert
              type={result.failed ? 'warning' : 'success'}
              showIcon
              message={`导入完成：成功 ${result.success} / 失败 ${result.failed}`}
              description={result.errors && result.errors.length ? (
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{result.errors.join('\n')}</pre>
              ) : undefined}
            />
          ) : (
            <Alert type="error" showIcon message="导入失败" description={String(result.error || '')} />
          )}
        </div>
      ) : null}
    </Card>
  )
}

type TotpSetupState = 'idle' | 'setup'

function SecurityPanel() {
  const { message: msg } = App.useApp()
  const [status, setStatus] = useState<{ has_password: boolean; has_totp: boolean } | null>(null)
  const [loading, setLoading] = useState(false)

  const [enableForm] = Form.useForm()
  const [pwForm] = Form.useForm()
  const [codeForm] = Form.useForm()

  const [totpSetupState, setTotpSetupState] = useState<TotpSetupState>('idle')
  const [totpSecret, setTotpSecret] = useState('')
  const [totpUri, setTotpUri] = useState('')

  const loadStatus = async () => {
    try {
      const s = await apiFetch('/auth/status')
      setStatus(s)
    } catch {}
  }

  useEffect(() => { loadStatus() }, [])

  const handleEnable = async (values: { password: string; confirm: string }) => {
    if (values.password !== values.confirm) {
      msg.error('两次输入的密码不一致')
      return
    }
    setLoading(true)
    try {
      const d = await apiFetch('/auth/setup', {
        method: 'POST',
        body: JSON.stringify({ password: values.password }),
      })
      localStorage.setItem('auth_token', d.access_token)
      msg.success('密码保护已启用')
      enableForm.resetFields()
      await loadStatus()
    } catch (e: any) {
      msg.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleDisableAuth = async () => {
    setLoading(true)
    try {
      await apiFetch('/auth/disable', { method: 'POST' })
      localStorage.removeItem('auth_token')
      msg.success('密码保护已关闭')
      await loadStatus()
    } catch (e: any) {
      msg.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleChangePassword = async (values: { current_password: string; new_password: string; confirm: string }) => {
    if (values.new_password !== values.confirm) {
      msg.error('两次输入的新密码不一致')
      return
    }
    setLoading(true)
    try {
      await apiFetch('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ current_password: values.current_password, new_password: values.new_password }),
      })
      msg.success('密码已更新')
      pwForm.resetFields()
    } catch (e: any) {
      msg.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleSetupTotp = async () => {
    setLoading(true)
    try {
      const d = await apiFetch('/auth/2fa/setup')
      setTotpSecret(d.secret)
      setTotpUri(d.uri)
      setTotpSetupState('setup')
    } catch (e: any) {
      msg.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleEnableTotp = async (values: { code: string }) => {
    setLoading(true)
    try {
      await apiFetch('/auth/2fa/enable', {
        method: 'POST',
        body: JSON.stringify({ secret: totpSecret, code: values.code }),
      })
      msg.success('双因素认证已启用')
      setTotpSetupState('idle')
      codeForm.resetFields()
      await loadStatus()
    } catch (e: any) {
      msg.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleDisableTotp = async () => {
    setLoading(true)
    try {
      await apiFetch('/auth/2fa/disable', { method: 'POST' })
      msg.success('双因素认证已关闭')
      await loadStatus()
    } catch (e: any) {
      msg.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card
        title="访问密码保护"
        extra={
          status?.has_password
            ? <Tag color="green"><CheckCircleOutlined /> 已启用</Tag>
            : <Tag color="default"><CloseCircleOutlined /> 未启用</Tag>
        }
      >
        {!status?.has_password ? (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Typography.Text type="secondary">
              启用后，访问页面需要输入密码。默认不开启，任何能访问此地址的人均可使用。
            </Typography.Text>
            <Form form={enableForm} layout="vertical" onFinish={handleEnable} requiredMark={false} style={{ maxWidth: 360, marginTop: 8 }}>
              <Form.Item name="password" label="设置访问密码" rules={[{ required: true, message: '请输入密码' }, { min: 6, message: '至少 6 位' }]}>
                <Input.Password placeholder="至少 6 位" />
              </Form.Item>
              <Form.Item name="confirm" label="确认密码" rules={[{ required: true, message: '请再次输入' }]}>
                <Input.Password placeholder="再次输入密码" />
              </Form.Item>
              <Form.Item style={{ marginBottom: 0 }}>
                <Button type="primary" htmlType="submit" loading={loading} icon={<LockOutlined />}>
                  启用密码保护
                </Button>
              </Form.Item>
            </Form>
          </Space>
        ) : (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Typography.Text type="secondary">当前已启用密码保护，关闭后任何人无需密码即可访问。</Typography.Text>
            <Button danger loading={loading} onClick={handleDisableAuth}>
              关闭密码保护
            </Button>
          </Space>
        )}
      </Card>

      {status?.has_password && (
        <>
          <Card title="修改密码">
            <Form form={pwForm} layout="vertical" onFinish={handleChangePassword} requiredMark={false} style={{ maxWidth: 360 }}>
              <Form.Item name="current_password" label="当前密码" rules={[{ required: true, message: '请输入当前密码' }]}>
                <Input.Password placeholder="当前密码" />
              </Form.Item>
              <Form.Item name="new_password" label="新密码" rules={[{ required: true, message: '请输入新密码' }, { min: 6, message: '至少 6 位' }]}>
                <Input.Password placeholder="新密码（至少 6 位）" />
              </Form.Item>
              <Form.Item name="confirm" label="确认新密码" rules={[{ required: true, message: '请再次输入' }]}>
                <Input.Password placeholder="再次输入新密码" />
              </Form.Item>
              <Form.Item style={{ marginBottom: 0 }}>
                <Button type="primary" htmlType="submit" loading={loading} icon={<SaveOutlined />}>
                  更新密码
                </Button>
              </Form.Item>
            </Form>
          </Card>

          <Card
            title="双因素认证 (2FA)"
            extra={
              status?.has_totp
                ? <Tag color="green"><CheckCircleOutlined /> 已启用</Tag>
                : <Tag color="default"><CloseCircleOutlined /> 未启用</Tag>
            }
          >
            {status?.has_totp ? (
              <Space direction="vertical">
                <Typography.Text type="secondary">
                  登录时需输入 Google Authenticator / Authy 等 App 中的 6 位验证码。
                </Typography.Text>
                <Button danger loading={loading} onClick={handleDisableTotp}>
                  关闭双因素认证
                </Button>
              </Space>
            ) : totpSetupState === 'idle' ? (
              <Space direction="vertical">
                <Typography.Text type="secondary">
                  启用后，登录时除密码外还需输入验证器 App 中的 6 位验证码，大幅提升安全性。
                </Typography.Text>
                <Button type="primary" loading={loading} onClick={handleSetupTotp} icon={<SafetyOutlined />}>
                  开启双因素认证
                </Button>
              </Space>
            ) : (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Typography.Text strong>1. 用验证器 App 扫描下方二维码</Typography.Text>
                <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                  <QRCode value={totpUri} size={180} />
                  <div style={{ flex: 1 }}>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>无法扫码？手动输入密钥：</Typography.Text>
                    <Typography.Paragraph copyable style={{ fontFamily: 'monospace', fontSize: 13, marginTop: 4 }}>
                      {totpSecret}
                    </Typography.Paragraph>
                  </div>
                </div>
                <Typography.Text strong>2. 输入 App 中显示的 6 位验证码以确认绑定</Typography.Text>
                <Form form={codeForm} layout="inline" onFinish={handleEnableTotp}>
                  <Form.Item name="code" rules={[{ required: true, message: '请输入验证码' }, { len: 6, message: '6 位数字' }]}>
                    <Input placeholder="000000" maxLength={6} style={{ width: 140, letterSpacing: 4, textAlign: 'center' }} />
                  </Form.Item>
                  <Form.Item>
                    <Button type="primary" htmlType="submit" loading={loading}>确认启用</Button>
                  </Form.Item>
                  <Form.Item>
                    <Button onClick={() => setTotpSetupState('idle')}>取消</Button>
                  </Form.Item>
                </Form>
              </Space>
            )}
          </Card>
        </>
      )}
    </div>
  )
}

export default function Settings() {
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [activeTab, setActiveTab] = useState('register')
  const currentMailProvider = String(Form.useWatch('mail_provider', form) || '')
  const showFloatingSaveButton = activeTab === 'mailbox' || activeTab === 'chatgpt'
  const contentPaneRef = useRef<HTMLDivElement | null>(null)
  const [floatingSaveBounds, setFloatingSaveBounds] = useState<{ left: number; width: number } | null>(null)

  useEffect(() => {
    apiFetch('/config').then((data) => {
      if (!data.mail_provider) {
        data.mail_provider = 'luckmail'
      }
      if (!data.applemail_base_url) {
        data.applemail_base_url = 'https://www.appleemail.top'
      }
      if (!data.applemail_pool_dir) {
        data.applemail_pool_dir = 'mail'
      }
      if (!data.applemail_mailboxes) {
        data.applemail_mailboxes = 'INBOX,Junk'
      }
      if (!data.gptmail_base_url) {
        data.gptmail_base_url = 'https://mail.chatgpt.org.uk'
      }
      if (!data.maliapi_base_url) {
        data.maliapi_base_url = 'https://maliapi.215.im/v1'
      }
      if (!data.luckmail_base_url) {
        data.luckmail_base_url = 'https://mails.luckyous.com/'
      }
      if (!data.contribution_server_url) {
        data.contribution_server_url = 'http://new.xem8k5.top:7317/'
      }
      if (!data.cloudmail_timeout) {
        data.cloudmail_timeout = 30
      }
      data.cpa_enabled = resolveFeatureEnabledConfig(
        data.cpa_enabled,
        Boolean(String(data.cpa_api_url ?? '').trim()),
      )
      data.sub2api_enabled = resolveFeatureEnabledConfig(
        data.sub2api_enabled,
        Boolean(String(data.sub2api_api_url ?? '').trim() && String(data.sub2api_api_key ?? '').trim()),
      )
      data.cfworker_domains = parseStoredDomainList(data.cfworker_domains)
      data.cfworker_enabled_domains = parseStoredDomainList(data.cfworker_enabled_domains)
      data.cfworker_random_subdomain = parseBooleanConfigValue(data.cfworker_random_subdomain)
      data.cfworker_random_name_subdomain = parseBooleanConfigValue(data.cfworker_random_name_subdomain)
      data.contribution_enabled = parseBooleanConfigValue(data.contribution_enabled)
      form.setFieldsValue(data)
    })
  }, [form])

  useEffect(() => {
    if (!showFloatingSaveButton) {
      setFloatingSaveBounds(null)
      return
    }

    const element = contentPaneRef.current
    if (!element) return

    const updateBounds = () => {
      const rect = element.getBoundingClientRect()
      setFloatingSaveBounds({
        left: rect.left,
        width: rect.width,
      })
    }

    updateBounds()

    const observer =
      typeof ResizeObserver !== 'undefined'
        ? new ResizeObserver(() => updateBounds())
        : null

    observer?.observe(element)
    window.addEventListener('resize', updateBounds)

    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', updateBounds)
    }
  }, [showFloatingSaveButton, activeTab])

  const save = async () => {
    setSaving(true)
    try {
      const values = form.getFieldsValue(true)
      const domains = normalizeDomainList(values.cfworker_domains)
      const enabledDomains = normalizeDomainList(values.cfworker_enabled_domains).filter((domain) => domains.includes(domain))

      if (domains.length > 0 && enabledDomains.length === 0) {
        setActiveTab('mailbox')
        message.error('CF Worker 至少需要启用一个域名')
        return
      }

      values.cfworker_domains = JSON.stringify(domains)
      values.cfworker_enabled_domains = JSON.stringify(enabledDomains)
      if (domains.length > 0) {
        values.cfworker_domain = ''
      }
      values.cpa_enabled = parseBooleanConfigValue(values.cpa_enabled)
      values.sub2api_enabled = parseBooleanConfigValue(values.sub2api_enabled)
      values.cfworker_random_subdomain = parseBooleanConfigValue(values.cfworker_random_subdomain)
      values.cfworker_random_name_subdomain = parseBooleanConfigValue(values.cfworker_random_name_subdomain)
      values.contribution_enabled = parseBooleanConfigValue(values.contribution_enabled)

      await apiFetch('/config', { method: 'PUT', body: JSON.stringify({ data: values }) })
      form.setFieldsValue({
        cpa_enabled: values.cpa_enabled,
        sub2api_enabled: values.sub2api_enabled,
        cfworker_domains: domains,
        cfworker_enabled_domains: enabledDomains,
        cfworker_domain: domains.length > 0 ? '' : values.cfworker_domain,
        cfworker_random_subdomain: values.cfworker_random_subdomain,
        cfworker_random_name_subdomain: values.cfworker_random_name_subdomain,
        contribution_enabled: values.contribution_enabled,
      })
      message.success('保存成功')
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  const currentTab = TAB_ITEMS.find((t) => t.key === activeTab) as TabConfig
  const mailboxSections =
    activeTab === 'mailbox'
      ? splitMailboxSections(currentTab.sections, currentMailProvider)
      : { defaultSection: null, selectedSection: null, remainingSections: currentTab.sections }
  const floatingSaveWidth = floatingSaveBounds ? Math.max(floatingSaveBounds.width, 0) : 0
  const floatingSaveLeft =
    floatingSaveBounds && floatingSaveWidth > 0
      ? floatingSaveBounds.left + (floatingSaveBounds.width - floatingSaveWidth) / 2
      : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, paddingBottom: showFloatingSaveButton ? 96 : 0 }}>
      {showFloatingSaveButton && floatingSaveBounds && floatingSaveWidth > 0 ? (
        <div
          style={{
            position: 'fixed',
            left: floatingSaveLeft,
            bottom: 24,
            zIndex: 1000,
            width: floatingSaveWidth,
            pointerEvents: 'none',
          }}
        >
          <div
            style={{
              width: '100%',
              padding: 0,
              borderRadius: 0,
              border: 'none',
              background: 'transparent',
              boxShadow: 'none',
              backdropFilter: 'none',
              pointerEvents: 'auto',
            }}
          >
            <Button type="primary" icon={<SaveOutlined />} onClick={save} loading={saving} block>
              {saved ? '已保存 ✓' : '保存配置'}
            </Button>
          </div>
        </div>
      ) : null}
      <div>
        <h1 style={{ fontSize: 24, fontWeight: 'bold', margin: 0 }}>全局配置</h1>
        <p style={{ color: '#7a8ba3', marginTop: 4 }}>配置将持久化保存，注册任务自动使用</p>
      </div>

      <div style={{ display: 'flex', gap: 24 }}>
        <div style={{ width: 200 }}>
          <Tabs
            tabPosition="left"
            activeKey={activeTab}
            onChange={setActiveTab}
            items={TAB_ITEMS.map((t) => ({
              key: t.key,
              label: (
                <span>
                  {t.icon}
                  <span style={{ marginLeft: 8 }}>{t.label}</span>
                </span>
              ),
            }))}
          />
        </div>

        <div ref={contentPaneRef} style={{ flex: 1 }}>
          {activeTab === 'integrations' ? (
            <IntegrationsPanel />
          ) : activeTab === 'security' ? (
            <SecurityPanel />
          ) : (
            <Form form={form} layout="vertical">
              {activeTab === 'contribution' ? (
                <ContributionPanel form={form} onSave={save} saving={saving} saved={saved} />
              ) : (
                <>
                  {activeTab === 'captcha' ? <SolverStatus /> : null}
                  {activeTab === 'mailbox' ? (
                    <>
                      {mailboxSections.defaultSection ? (
                        <ConfigSection key={mailboxSections.defaultSection.title} section={mailboxSections.defaultSection} />
                      ) : null}
                      {mailboxSections.selectedSection ? (
                        <ConfigSection key={`${mailboxSections.selectedSection.title}-selected`} section={mailboxSections.selectedSection} />
                      ) : null}
                      {currentMailProvider === 'applemail' ? <AppleMailPoolImportSection form={form} /> : null}
                      {currentMailProvider === 'cfworker' ? <CFWorkerDomainPoolSection form={form} /> : null}
                      {currentMailProvider === 'outlook' ? <OutlookImportSection /> : null}
                      {mailboxSections.remainingSections.map((section) => (
                        <ConfigSection key={section.title} section={section} />
                      ))}
                      {currentMailProvider !== 'applemail' ? <AppleMailPoolImportSection form={form} /> : null}
                      {currentMailProvider !== 'cfworker' ? <CFWorkerDomainPoolSection form={form} /> : null}
                      {currentMailProvider !== 'outlook' ? <OutlookImportSection /> : null}
                    </>
                  ) : (
                    currentTab.sections.map((section) => (
                      <ConfigSection key={section.title} section={section} />
                    ))
                  )}
                  {showFloatingSaveButton ? <div style={{ height: 8 }} /> : null}
                  {!showFloatingSaveButton ? (
                    <Button type="primary" icon={<SaveOutlined />} onClick={save} loading={saving} block>
                    {saved ? '已保存 ✓' : '保存配置'}
                    </Button>
                  ) : null}
                </>
              )}
            </Form>
          )}
        </div>
      </div>
    </div>
  )
}
