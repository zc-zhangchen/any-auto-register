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
import MailImportPanel from '@/components/settings/MailImportPanel'
import { apiFetch } from '@/lib/utils'
import { useText } from '@/lib/uiLanguage'

const SETTINGS_EN_TRANSLATIONS: Record<string, string> = {
  '注册设置': 'Registration settings',
  '默认注册方式': 'Default registration method',
  '控制注册任务如何执行': 'Controls how registration tasks are executed',
  '执行器类型': 'Executor type',
  '邮箱服务': 'Mailbox service',
  '默认邮箱服务': 'Default mailbox service',
  '选择注册时使用的邮箱类型': 'Choose the mailbox type used during registration',
  '邮箱验证码等待秒数': 'Mailbox OTP wait time (seconds)',
  '固定邮箱，手动配置': 'Fixed mailbox, configured manually',
  '邮箱地址': 'Email address',
  '用户名（可选）': 'Username (optional)',
  '密码（可选）': 'Password (optional)',
  '邮箱域名（可选）': 'Mailbox domain (optional)',
  '自动注册账号并生成临时邮箱': 'Automatically registers an account and generates a temporary mailbox',
  'CloudMail 兼容接口（addUser / emailList）': 'CloudMail-compatible API (addUser / emailList)',
  '邮箱域名': 'Mailbox domain',
  'CloudMail 口令模式（genToken + emailList）': 'CloudMail passcode mode (genToken + emailList)',
  '管理员邮箱（可选）': 'Admin email (optional)',
  '管理员密码': 'Admin password',
  '子域名（可选）': 'Subdomain (optional)',
  '请求超时秒数': 'Request timeout (seconds)',
  '基于 API Key 创建临时邮箱并轮询收件箱消息': 'Creates a temporary mailbox from an API key and polls the inbox for messages',
  '自动域名策略': 'Automatic domain strategy',
  '邮箱导入（微软 / Outlook / Hotmail）': 'Mailbox import (Microsoft / Outlook / Hotmail)',
  '使用本地导入的微软账号池，运行时支持 Graph / IMAP 轮询（默认 Graph）': 'Uses a locally imported Microsoft account pool; runtime supports Graph / IMAP polling (Graph by default)',
  '微软收信方式': 'Microsoft inbox method',
  '邮箱导入（AppleMail / 小苹果）': 'Mailbox import (AppleMail / Little Apple)',
  '读取本地邮箱池文件，通过 refresh_token + client_id 调用小苹果取件接口；支持在本页直接导入 JSON': 'Reads a local mailbox pool file and calls the Little Apple pickup API via refresh_token + client_id; JSON can be imported directly on this page',
  '邮箱池目录': 'Mailbox pool directory',
  '当前邮箱池文件（可选）': 'Current pool file (optional)',
  '轮询文件夹': 'Polling folders',
  '基于 GPTMail API 生成临时邮箱并轮询邮件；若已知本站可用域名，也可本地拼装随机地址': 'Uses the GPTMail API to generate temporary mailboxes and poll messages; if a usable domain is known, a random local address can be assembled instead',
  '对接 opentrashmail 服务；可直接轮询 /json/<email>，也支持已知域名时本地拼装随机地址': 'Connects to the opentrashmail service; can poll /json/<email> directly and can also assemble a local random address when a known domain is available',
  '站点密码（可选）': 'Site password (optional)',
  '启用 PASSWORD 时填写': 'Fill this in when PASSWORD is enabled',
  '自动生成邮箱，无需配置，需要代理访问（CN IP 被封）': 'Auto-generates mailboxes with no configuration required; proxy access is needed (CN IPs are blocked)',
  '自动生成邮箱，随机创建账号': 'Auto-generates mailboxes and creates accounts randomly',
  '自定义域名': 'Custom domain',
  '留空则从 Provider URL 推导': 'Leave empty to derive from the provider URL',
  '私有域名': 'Private domain',
  'CF Worker 自建邮箱': 'CF Worker self-hosted mailbox',
  '基于 Cloudflare Worker 的自建临时邮箱服务': 'Self-hosted temporary mailbox service based on Cloudflare Worker',
  '管理员 Token': 'Admin token',
  '站点密码': 'Site password',
  '固定子域名': 'Fixed subdomain',
  '启用域名规则': 'Enable domain rules',
  '域名级数（N 级）': 'Domain depth (N levels)',
  '随机子域名': 'Random subdomain',
  '随机姓名子域名': 'Random-name subdomain',
  'ChatGPT 走购买邮箱，其他平台继续走订单接码老逻辑': 'ChatGPT uses purchased mailboxes; other platforms continue using the legacy order/SMS flow',
  '平台地址': 'Platform URL',
  '验证码': 'Verification',
  '验证码服务': 'Captcha service',
  '用于绕过注册页面的人机验证': 'Used to bypass human verification on the registration page',
  '默认服务': 'Default service',
  'CPA 面板': 'CPA panel',
  '注册完成后自动上传到 CPA 管理平台': 'Automatically uploads completed registrations to the CPA management platform',
  '启用自动上传': 'Enable auto-upload',
  'Sub2API 面板': 'Sub2API panel',
  '注册完成后自动上传到 Sub2API 管理后台': 'Automatically uploads completed registrations to the Sub2API admin backend',
  '分组 ID': 'Group IDs',
  '多个分组用英文逗号分隔，例如 2,4,8': 'Separate multiple groups with English commas, e.g. 2,4,8',
  'CPA 自动维护': 'CPA auto maintenance',
  '定时删除 status=error 的凭证，剩余数量低于阈值时自动按现有配置补注册 ChatGPT': 'Periodically deletes credentials with status=error and automatically tops up ChatGPT registrations when the remaining count falls below the threshold',
  '自动维护': 'Auto maintenance',
  '检查间隔（分钟）': 'Check interval (minutes)',
  '最低凭证阈值': 'Minimum credential threshold',
  '补注册并发数': 'Top-up concurrency',
  '每个注册延迟（秒）': 'Delay per registration (seconds)',
  '上传到自建 Team Manager 系统': 'Upload to a self-hosted Team Manager system',
  '注册完成后自动上传到 CodexProxy 管理平台': 'Automatically uploads completed registrations to the CodexProxy management platform',
  '上传类型': 'Upload type',
  'SMSToMe 手机验证': 'SMSToMe phone verification',
  'ChatGPT add_phone 阶段自动取号并轮询短信验证码': 'Automatically acquires a phone number and polls SMS codes during the ChatGPT add_phone step',
  '国家列表': 'Country list',
  '手机号尝试次数': 'Phone number attempts',
  '短信等待秒数': 'SMS wait time (seconds)',
  '轮询间隔秒数': 'Polling interval (seconds)',
  '每国同步页数': 'Sync pages per country',
  '管理面板': 'Management panel',
  '用于 CLIProxyAPI 管理页登录': 'Used to sign in to the CLIProxyAPI admin page',
  '管理口令': 'Admin password',
  '注册成功后自动导入到 grok2api 管理后台': 'Automatically imports successful registrations into the grok2api admin backend',
  '注册成功后自动写入 kiro-account-manager 的 accounts.json': 'Automatically writes successful registrations to kiro-account-manager\'s accounts.json',
  'accounts.json 路径（可选）': 'accounts.json path (optional)',
  '留空则自动使用系统默认路径': 'Leave empty to use the system default path',
  'Kiro Manager 可执行文件（可选）': 'Kiro Manager executable (optional)',
  '未安装 Rust 时可填写已安装的 KiroAccountManager.exe': 'If Rust is not installed, you can point to an existing KiroAccountManager.exe',
  '贡献': 'Contribution',
  '插件': 'Plugins',
  '安全': 'Security',
  '检测中': 'Checking',
  '运行中': 'Running',
  '未运行': 'Not running',
  '重启 Solver': 'Restart Solver',
  '操作完成': 'Action completed',
  '操作失败': 'Action failed',
  '操作结果': 'Action result',
  '保存策略': 'Save policy',
  '安装/更新策略': 'Install/update policy',
  '批量操作': 'Bulk actions',
  '启动全部（已安装）': 'Start all installed',
  '停止全部': 'Stop all',
  '刷新状态': 'Refresh status',
  '状态：': 'Status:',
  '已安装': 'Installed',
  '未安装': 'Not installed',
  '插件目录：': 'Plugin directory:',
  '地址：': 'URL:',
  '管理页：': 'Admin page:',
  '登录口令：': 'Login key:',
  '日志：': 'Log:',
  '最近错误：': 'Last error:',
  '打开管理页': 'Open admin page',
  '安装最新版': 'Install latest version',
  '更新到最新版': 'Update to latest version',
  '启动': 'Start',
  '停止': 'Stop',
  '卸载': 'Uninstall',
  '回填现有 Grok 账号': 'Backfill existing Grok accounts',
  '回填现有 Kiro 账号': 'Backfill existing Kiro accounts',
}

function translateSettingsText(text?: string) {
  if (!text) return ''
  return SETTINGS_EN_TRANSLATIONS[text] || text
}

function resolveEffectiveMailProvider(mailProvider: string, mailImportSource: string) {
  if (mailProvider !== 'mail_import') return mailProvider
  return mailImportSource === 'applemail' ? 'applemail' : 'microsoft'
}

const SELECT_FIELDS: Record<string, { label: string; value: string }[]> = {
  mail_provider: [
    { label: 'LuckMail（订单接码 / 已购邮箱）', value: 'luckmail' },
    { label: '邮箱导入', value: 'mail_import' },
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
  outlook_backend: [
    { label: 'Graph（默认）', value: 'graph' },
    { label: 'IMAP', value: 'imap' },
  ],
  luckmail_email_type: [
    { label: '自动 / 留空', value: '' },
    { label: '微软邮箱 - Graph', value: 'ms_graph' },
    { label: '微软邮箱 - IMAP', value: 'ms_imap' },
    { label: '自建邮箱', value: 'self_built' },
  ],
  cpa_cleanup_enabled: [
    { label: '关闭', value: '0' },
    { label: '开启', value: '1' },
  ],
  codex_proxy_upload_type: [
    { label: 'AT（Access Token，推荐）', value: 'at' },
    { label: 'RT（Refresh Token）', value: 'rt' },
  ],
  external_apps_update_mode: [
    { label: 'latest semver tag（推荐）', value: 'tag' },
    { label: '分支 HEAD', value: 'branch' },
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
        title: '邮箱导入（微软 / Outlook / Hotmail）',
        desc: '使用本地导入的微软账号池，运行时支持 Graph / IMAP 轮询（默认 Graph）',
        fields: [
          { key: 'outlook_backend', label: '微软收信方式', type: 'select' },
        ],
      },
      {
        title: '邮箱导入（AppleMail / 小苹果）',
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
          { key: 'email_domain_rule_enabled', label: '启用域名规则', type: 'boolean' },
          { key: 'email_domain_level_count', label: '域名级数（N 级）', placeholder: '例如 2 / 3 / 4' },
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
          { key: 'luckmail_email_type', label: '邮箱类型（可选）', type: 'select' },
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
          { key: 'cliproxyapi_base_url', label: 'API URL', placeholder: 'http://localhost:8317' },
          { key: 'cliproxyapi_management_key', label: '管理口令', secret: true, placeholder: '默认 islam' },
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

const MAILBOX_SECTION_FIELD_KEY_BY_PROVIDER: Record<string, string> = {
  laoudo: 'laoudo_email',
  freemail: 'freemail_api_url',
  moemail: 'moemail_api_url',
  skymail: 'skymail_api_base',
  cloudmail: 'cloudmail_api_base',
  maliapi: 'maliapi_base_url',
  microsoft: 'outlook_backend',
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
  const t = useText()
  const options = SELECT_FIELDS[field.key]?.map((option) => ({
    ...option,
    label: translateSettingsText(option.label),
  }))
  const isBooleanField = field.type === 'boolean'
  const helpText =
    field.key === 'default_executor'
      ? t(
          '仅对支持的平台生效；ChatGPT、Cursor、Grok、Kiro、Tavily、Trae 支持浏览器模式，OpenBlockLabs 仅支持纯协议。',
          'Only applies to supported platforms; ChatGPT, Cursor, Grok, Kiro, Tavily, and Trae support browser mode, while OpenBlockLabs supports protocol mode only.',
        )
      : field.key === 'email_domain_rule_enabled'
      ? t(
          '仅 CF Worker 生效：开启后会校验域名级数，以及域名至少包含 2 个字母和 2 个数字。',
          'CF Worker only: when enabled, the app validates the domain depth and requires at least 2 letters and 2 digits in the domain.',
        )
      : field.key === 'email_domain_level_count'
      ? t(
          '例如 2=example.com，3=a.example.com，4=a.b.example.com。',
          'For example: 2=example.com, 3=a.example.com, 4=a.b.example.com.',
        )
      : undefined

  return (
    <Form.Item
      label={t(field.label, translateSettingsText(field.label))}
      name={field.key}
      extra={helpText}
      valuePropName={isBooleanField ? 'checked' : undefined}
    >
      {options ? (
        <Select options={options} style={{ width: '100%' }} />
      ) : isBooleanField ? (
        <Switch checkedChildren={t('开启', 'On')} unCheckedChildren={t('关闭', 'Off')} />
      ) : field.secret ? (
        <Input.Password
          placeholder={translateSettingsText(field.placeholder)}
          visibilityToggle={{
            visible: !showSecret,
            onVisibleChange: setShowSecret,
          }}
          iconRender={(visible) => (visible ? <EyeOutlined /> : <EyeInvisibleOutlined />)}
        />
      ) : (
        <Input placeholder={translateSettingsText(field.placeholder)} />
      )}
    </Form.Item>
  )
}

function ConfigSection({ section }: { section: SectionConfig }) {
  const t = useText()
  return (
    <Card title={t(section.title, translateSettingsText(section.title))} extra={section.desc && <span style={{ fontSize: 12, color: '#7a8ba3' }}>{t(section.desc, translateSettingsText(section.desc))}</span>} style={{ marginBottom: 16 }}>
      {section.fields.map((field) => (
        <ConfigField key={field.key} field={field} />
      ))}
    </Card>
  )
}

function CFWorkerDomainPoolSection({ form }: { form: any }) {
  const t = useText()
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
      title={t('CF Worker 域名池', 'CF Worker Domain Pool')}
      extra={<span style={{ fontSize: 12, color: '#7a8ba3' }}>{t('注册时会从已启用域名中随机选择一个', 'A random enabled domain will be selected during registration')}</span>}
      style={{ marginBottom: 16 }}
    >
      <Form.List name="cfworker_domains">
        {(fields, { add, remove }) => (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {fields.map((field) => {
              const { key, ...restField } = field
              return (
                <Space key={key} align="start" style={{ display: 'flex' }}>
                  <Form.Item
                    {...restField}
                    label={field.name === 0 ? t('全部域名', 'All domains') : ''}
                    style={{ flex: 1, marginBottom: 0 }}
                    rules={[
                      {
                        validator: async (_, value) => {
                          if (!String(value || '').trim()) {
                            throw new Error(t('请输入域名', 'Enter a domain'))
                          }
                        },
                      },
                    ]}
                  >
                  <Input placeholder={t('example.com', 'example.com')} />
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
                  {t('删除', 'Delete')}
                </Button>
              </Space>
            )})}
            {fields.length === 0 ? (
              <Typography.Text type="secondary">{t('还没有配置域名。添加后即可在下方选择启用项。', 'No domains configured yet. Add one above, then enable it below.')}</Typography.Text>
            ) : null}
            <Button type="dashed" onClick={() => add('')} icon={<PlusOutlined />} block>
              {t('添加域名', 'Add domain')}
            </Button>
          </div>
        )}
      </Form.List>

      <Form.Item name="cfworker_enabled_domains" hidden>
        <Select mode="multiple" options={normalizedDomains.map((domain) => ({ label: domain, value: domain }))} />
      </Form.Item>

      <div style={{ marginTop: 16 }}>
        <div style={{ marginBottom: 8, fontWeight: 500 }}>{t('已启用域名', 'Enabled domains')}</div>
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
          <Typography.Text type="secondary">{t('暂无启用域名，点击下方域名即可启用。', 'No enabled domains yet. Click a domain below to enable it.')}</Typography.Text>
        )}
      </div>

      <div style={{ marginTop: 16 }}>
        <div style={{ marginBottom: 8, fontWeight: 500 }}>{t('点击切换启用状态', 'Click to toggle enabled state')}</div>
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
          <Typography.Text type="secondary">{t('请先在上方添加域名。', 'Add a domain above first.')}</Typography.Text>
        )}
      </div>
      <Typography.Text type="secondary" style={{ display: 'block', marginTop: 12 }}>
        {t('仅已启用域名会参与注册；点击已启用标签可直接移除。', 'Only enabled domains are used for registration; click an enabled tag to remove it.')}
      </Typography.Text>
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
  const [updateMode, setUpdateMode] = useState<'tag' | 'branch'>('tag')
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
      const [d, cfg] = await Promise.all([
        apiFetch('/integrations/services'),
        apiFetch('/config'),
      ])
      setItems(d.items || [])
      const mode = String(cfg?.external_apps_update_mode || 'tag').trim().toLowerCase()
      setUpdateMode(mode === 'branch' ? 'branch' : 'tag')
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

  const updateInstallMode = async (nextMode: 'tag' | 'branch') => {
    setBusy('update-mode')
    try {
      await apiFetch('/config', {
        method: 'PUT',
        body: JSON.stringify({ data: { external_apps_update_mode: nextMode } }),
      })
      setUpdateMode(nextMode)
      message.success(nextMode === 'tag' ? '已切换到 tag 模式' : '已切换到分支模式')
    } catch (e: any) {
      message.error(e?.message || '切换失败')
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

      <Card title="安装/更新策略">
        <Space wrap align="center">
          <Select
            style={{ width: 320 }}
            value={updateMode}
            options={SELECT_FIELDS.external_apps_update_mode}
            onChange={(value) => setUpdateMode(value as 'tag' | 'branch')}
          />
          <Button
            type="primary"
            loading={busy === 'update-mode'}
            onClick={() => updateInstallMode(updateMode)}
          >
            保存策略
          </Button>
        </Space>
      </Card>

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
                  安装最新版
                </Button>
              ) : (
                <Button
                  loading={busy === `install-${item.name}`}
                  onClick={() => doAction(`install-${item.name}`, apiFetch(`/integrations/services/${item.name}/install`, { method: 'POST' }))}
                >
                  更新到最新版
                </Button>
              )}
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
              <Button
                danger
                loading={busy === `uninstall-${item.name}`}
                disabled={!item.repo_exists}
                onClick={() => {
                  const ok = window.confirm(`确认卸载 ${item.label}？\n会停止服务并删除本地插件目录。`)
                  if (!ok) return
                  doAction(
                    `uninstall-${item.name}`,
                    apiFetch(`/integrations/services/${item.name}/uninstall`, { method: 'POST' }),
                  )
                }}
              >
                卸载
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
  const t = useText()
  const [loadingStats, setLoadingStats] = useState(false)
  const [redeeming, setRedeeming] = useState(false)
  const [creatingKey, setCreatingKey] = useState(false)
  const [redeemAmount, setRedeemAmount] = useState<number>(CONTRIBUTION_REDEEM_OPTIONS[0])
  const [statsResponse, setStatsResponse] = useState<Record<string, unknown> | null>(null)
  const [redeemResponse, setRedeemResponse] = useState<Record<string, unknown> | null>(null)
  const [statsError, setStatsError] = useState('')
  const [bindingCustom, setBindingCustom] = useState(false)
  const [customEmail, setCustomEmail] = useState('')
  const [customStatsResponse, setCustomStatsResponse] = useState<Record<string, unknown> | null>(null)
  const [customBalanceResponse, setCustomBalanceResponse] = useState<Record<string, unknown> | null>(null)
  const [loadingCustomStats, setLoadingCustomStats] = useState(false)

  const contributionEnabled = Form.useWatch('contribution_enabled', form)
  const contributionMode = String(Form.useWatch('contribution_mode', form) || 'codex').trim()
  const contributionServerUrl = String(Form.useWatch('contribution_server_url', form) || '').trim()
  const contributionKey = String(Form.useWatch('contribution_key', form) || '').trim()
  const customContributionUrl = String(Form.useWatch('custom_contribution_url', form) || '').trim()
  const customContributionToken = String(Form.useWatch('custom_contribution_token', form) || '').trim()

  const isCustomMode = contributionMode === 'custom'

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
      ? t(
          `提现成功！额度：${redeemedAmountUSD !== null ? formatDisplayNumber(redeemedAmountUSD, 2) : '-'} 兑换码：${redeemCode || '-'}`,
          `Withdrawal successful! Amount: ${redeemedAmountUSD !== null ? formatDisplayNumber(redeemedAmountUSD, 2) : '-'} Code: ${redeemCode || '-'}`,
        )
      : ''

  const fetchStats = async (silent = false, keyOverride?: string) => {
    if (!contributionEnabled) {
      if (!silent) message.warning(t('请先开启贡献功能', 'Enable contribution first'))
      return
    }
    if (!contributionServerUrl) {
      if (!silent) message.error(t('请先填写服务器地址', 'Enter the server URL first'))
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
        message.success(t('额度信息已刷新', 'Quota information refreshed'))
      }
    } catch (e: any) {
      const detail = String(e?.message || t('获取额度信息失败', 'Failed to fetch quota information'))
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
      message.warning(t('请先开启贡献功能', 'Enable contribution first'))
      return
    }
    if (!contributionServerUrl) {
      message.error(t('请先填写服务器地址', 'Enter the server URL first'))
      return
    }
    if (!contributionKey) {
      message.error(t('请先填写 API Key', 'Enter the API key first'))
      return
    }

    const confirmed = window.confirm(t(`确认提现吗？\n将按 ${redeemAmount} 发起提现请求`, `Confirm withdrawal?\nA withdrawal request will be sent for ${redeemAmount}`))
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
        message.success(
          t(
            `提现成功！额度：${amount !== null ? formatDisplayNumber(amount, 2) : '-'} 兑换码：${code || '-'}`,
            `Withdrawal successful! Amount: ${amount !== null ? formatDisplayNumber(amount, 2) : '-'} Code: ${code || '-'}`,
          ),
        )
      } else {
        message.success(t('提现成功', 'Withdrawal successful'))
      }
      await fetchStats(true)
    } catch (e: any) {
      const detail = String(e?.message || t('提现失败', 'Withdrawal failed'))
      setRedeemResponse({ ok: false, error: detail })
      message.error(detail)
    } finally {
      setRedeeming(false)
    }
  }

  const doGenerateKey = async () => {
    if (!contributionServerUrl) {
      message.error(t('请先填写服务器地址', 'Enter the server URL first'))
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
        throw new Error(t('服务端未返回可用 key', 'The server did not return an available key'))
      }
      form.setFieldValue('contribution_key', generated)
      message.success(t('已新建并填充 API Key，请点击保存配置', 'Created and filled the API key. Click save settings.'))
      if (contributionEnabled) {
        await fetchStats(true, generated)
      }
    } catch (e: any) {
      message.error(String(e?.message || t('请求新建 key 失败', 'Failed to request a new key')))
    } finally {
      setCreatingKey(false)
    }
  }

  const doBindCustom = async () => {
    if (!customEmail.trim()) {
      message.error(t('请输入邮箱', 'Enter an email'))
      return
    }
    if (!customContributionUrl) {
      message.error(t('请先填写自定义服务器地址', 'Enter the custom server URL first'))
      return
    }
    setBindingCustom(true)
    try {
      const data = await apiFetch('/contribution/custom/bind', {
        method: 'POST',
        body: JSON.stringify({
          email: customEmail.trim(),
          server_url: customContributionUrl,
        }),
      })
      const token = pickString(asRecord(data), ['token'])
      if (token) {
        form.setFieldValue('custom_contribution_token', token)
        message.success(t('绑定成功！token 已自动填充，请点击保存配置', 'Bound successfully. The token was filled automatically. Click save settings.'))
        setCustomEmail('')
      } else {
        message.success(t('绑定成功', 'Bound successfully'))
      }
    } catch (e: any) {
      message.error(String(e?.message || t('绑定失败', 'Binding failed')))
    } finally {
      setBindingCustom(false)
    }
  }

  const fetchCustomStats = async () => {
    if (!contributionEnabled) {
      message.warning(t('请先开启贡献功能', 'Enable contribution first'))
      return
    }
    if (!customContributionUrl) {
      message.error(t('请先填写自定义服务器地址', 'Enter the custom server URL first'))
      return
    }
    if (!customContributionToken) {
      message.error(t('请先绑定邮箱获取 token', 'Bind an email first to get the token'))
      return
    }
    setLoadingCustomStats(true)
    try {
      const [status, balance] = await Promise.all([
        apiFetch(`/contribution/custom/status?server_url=${encodeURIComponent(customContributionUrl)}&token=${encodeURIComponent(customContributionToken)}`),
        apiFetch(`/contribution/custom/balance?server_url=${encodeURIComponent(customContributionUrl)}&token=${encodeURIComponent(customContributionToken)}`),
      ])
      setCustomStatsResponse(asRecord(status))
      setCustomBalanceResponse(asRecord(balance))
      message.success(t('信息已刷新', 'Information refreshed'))
    } catch (e: any) {
      message.error(String(e?.message || t('获取信息失败', 'Failed to fetch information')))
    } finally {
      setLoadingCustomStats(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card title={t('配置', 'Configuration')}>
        <Alert
          type="warning"
          showIcon
          banner
          style={{ marginBottom: 12 }}
          message={t('开启贡献模式后，注册成功账号将只上传到贡献服务器', 'When contribution mode is enabled, newly registered accounts are uploaded only to the contribution server')}
          description={(
            <>
              <div>{t('CPA / CodexProxy / Sub2API 自动上传会被停用，避免重复上报。', 'CPA / CodexProxy / Sub2API auto-upload will be disabled to avoid duplicate reporting.')}</div>
              <div>{t('目前该功能在xem中转站测试中 有兴趣可以进群了解', 'This feature is currently being tested on the xem relay. Join the group if you are interested.')}</div>
              <div>{t('中转站https://ai.xem8k5.top/ 群号634758974', 'Relay: https://ai.xem8k5.top/  Group: 634758974')}</div>
            </>
          )}
        />
        <Form.Item name="contribution_enabled" label={t('是否开启', 'Enabled')} valuePropName="checked">
          <Switch checkedChildren={t('开启', 'On')} unCheckedChildren={t('关闭', 'Off')} />
        </Form.Item>
        <Form.Item name="contribution_mode" label={t('贡献模式', 'Contribution mode')}>
          <Select>
            <Select.Option value="codex">Codex2API ({t('xem中转站', 'xem relay')})</Select.Option>
            <Select.Option value="custom">{t('自定义贡献系统', 'Custom contribution system')}</Select.Option>
          </Select>
        </Form.Item>

        {!isCustomMode ? (
          <>
            <Form.Item
              name="contribution_server_url"
              label={t('服务器地址', 'Server URL')}
              rules={[{ required: true, message: t('请输入服务器地址', 'Enter the server URL') }]}
            >
              <Input placeholder="http://new.xem8k5.top:7317/" />
            </Form.Item>
            <Form.Item name="contribution_key" label="API Key">
              <Input
                placeholder={t('留空可点击右侧按钮自动创建', 'Leave empty and use the button on the right to create one')}
                addonAfter={(
                  <Button
                    type="link"
                    size="small"
                    loading={creatingKey}
                    onClick={() => { void doGenerateKey() }}
                    style={{ paddingInline: 0 }}
                  >
                    {t('没有key?请求新建', 'No key? Request one')}
                  </Button>
                )}
              />
            </Form.Item>
          </>
        ) : (
          <>
            <Form.Item
              name="custom_contribution_url"
              label={t('自定义服务器地址', 'Custom server URL')}
              rules={[{ required: true, message: t('请输入服务器地址', 'Enter the server URL') }]}
            >
              <Input placeholder="http://127.0.0.1:5000" />
            </Form.Item>
            <Form.Item label={t('绑定邮箱', 'Bind email')}>
              <Space.Compact style={{ width: '100%' }}>
                <Input
                  placeholder={t('输入邮箱以绑定账号', 'Enter an email to bind the account')}
                  value={customEmail}
                  onChange={(e) => setCustomEmail(e.target.value)}
                  onPressEnter={() => { void doBindCustom() }}
                />
                <Button type="primary" loading={bindingCustom} onClick={() => { void doBindCustom() }}>
                  {t('绑定', 'Bind')}
                </Button>
              </Space.Compact>
            </Form.Item>
            <Form.Item name="custom_contribution_token" label="Token">
              <Input.TextArea placeholder={t('绑定邮箱后自动填充', 'Will be filled after binding the email')} rows={3} />
            </Form.Item>
          </>
        )}

        <Button type="primary" icon={<SaveOutlined />} onClick={onSave} loading={saving} block>
          {saved ? t('已保存 ✓', 'Saved ✓') : t('保存配置', 'Save settings')}
        </Button>
      </Card>

      {!isCustomMode ? (
        <>
          <Card
            title={t('信息', 'Information')}
            extra={(
              <Button loading={loadingStats} onClick={() => { void fetchStats() }}>
                {t('刷新信息', 'Refresh information')}
              </Button>
            )}
          >
            {!contributionEnabled ? (
              <Alert
                type="info"
                showIcon
                message={t('贡献功能已关闭，开启后可获取服务器与 key 信息。', 'Contribution mode is disabled. Enable it to view server and key details.')}
              />
            ) : (
              <Space direction="vertical" style={{ width: '100%' }} size={12}>
                {statsError ? <Alert type="error" showIcon message={statsError} /> : null}
                <div>
                  <Typography.Text strong>{t('服务器信息', 'Server information')}</Typography.Text>
                  <div style={{ marginTop: 8, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
                    <Tag color="blue">{t('账号数:', 'Accounts:')} {formatDisplayNumber(serverQuotaAccountCount)}</Tag>
                    <Tag color="geekblue">{t('总额度:', 'Total quota:')} {formatDisplayNumber(serverQuotaTotal)}</Tag>
                    <Tag color="volcano">{t('已用额度:', 'Used quota:')} {formatDisplayNumber(serverQuotaUsed)}</Tag>
                    <Tag color="green">{t('剩余额度:', 'Remaining quota:')} {formatDisplayNumber(serverQuotaRemaining)}</Tag>
                    <Tag color="orange">{t('已用占比:', 'Used percent:')} {formatDisplayPercent(serverQuotaUsedPercent)}</Tag>
                    <Tag color="cyan">{t('剩余占比:', 'Remaining percent:')} {formatDisplayPercent(serverQuotaRemainingPercent)}</Tag>
                    <Tag color="purple">{t('折算账号数:', 'Equivalent accounts:')} {formatDisplayNumber(serverQuotaRemainingAccounts, 2)}</Tag>
                  </div>
                </div>
                <div>
                  <Typography.Text strong>{t('API Key', 'API Key')}</Typography.Text>
                  <Space style={{ marginLeft: 8 }}>
                    <Typography.Text copyable={keyFromStats ? { text: keyFromStats } : undefined}>
                      {keyFromStats || '-'}
                    </Typography.Text>
                  </Space>
                </div>
                <div>
                  <Typography.Text strong>{t('key 信息', 'Key information')}</Typography.Text>
                  <div style={{ marginTop: 8, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
                    <Tag color="blue">{t('余额:', 'Balance:')} {keyBalance ?? '-'}</Tag>
                    <Tag color="geekblue">{t('来源:', 'Source:')} {keySource}</Tag>
                    <Tag color="cyan">{t('绑定账号数:', 'Bound accounts:')} {boundAccounts ?? '-'}</Tag>
                    <Tag color="purple">{t('结算金额:', 'Settlement amount:')} {settlementAmount ?? '-'}</Tag>
                  </div>
                </div>
              </Space>
            )}
          </Card>

          <Card title={t('提现', 'Withdrawal')}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Typography.Text>{t('key 当前额度：', 'Current key balance:')} {keyBalance ?? '-'}</Typography.Text>
              <Form.Item label={t('提现金额', 'Withdrawal amount')} style={{ marginBottom: 0 }}>
                <Select
                  value={redeemAmount}
                  onChange={setRedeemAmount}
                  style={{ width: 240 }}
                  options={CONTRIBUTION_REDEEM_OPTIONS.map((amount) => ({ label: String(amount), value: amount }))}
                />
              </Form.Item>
              <Button type="primary" danger onClick={() => { void doRedeem() }} loading={redeeming}>
                {t('提现确认', 'Confirm withdrawal')}
              </Button>
              {redeemResponse ? (
                <Alert
                  type={redeemResponse.ok === false ? 'error' : 'success'}
                  showIcon
                  message={redeemResponse.ok === false ? t('提现失败：', 'Withdrawal failed: ') + String(redeemResponse.error || '-') : redeemSuccessText}
                  description={<pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{formatResultText(redeemResponse)}</pre>}
                />
              ) : null}
            </Space>
          </Card>
        </>
      ) : (
        <Card
          title={t('信息', 'Information')}
          extra={(
            <Button loading={loadingCustomStats} onClick={() => { void fetchCustomStats() }}>
              {t('刷新信息', 'Refresh information')}
            </Button>
          )}
        >
          {!contributionEnabled ? (
            <Alert
              type="info"
              showIcon
              message={t('贡献功能已关闭，开启后可获取信息。', 'Contribution mode is disabled. Enable it to fetch information.')}
            />
          ) : !customContributionToken ? (
            <Alert type="warning" showIcon message={t('请先绑定邮箱获取 token', 'Bind an email first to obtain a token')} />
          ) : (
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              <div>
                <Typography.Text strong>{t('余额信息', 'Balance information')}</Typography.Text>
                <div style={{ marginTop: 8 }}>
                  <Tag color="blue">{t('余额:', 'Balance:')} {pickNumber(asRecord(customBalanceResponse), ['balance']) ?? '-'}</Tag>
                </div>
              </div>
              <div>
                <Typography.Text strong>{t('贡献记录', 'Contribution records')}</Typography.Text>
                <div style={{ marginTop: 8 }}>
                  <Tag color="green">{t('成功:', 'Success:')} {pickNumber(asRecord(customStatsResponse), ['success_count']) ?? '-'}</Tag>
                  <Tag color="orange">{t('待处理:', 'Pending:')} {pickNumber(asRecord(customStatsResponse), ['pending_count']) ?? '-'}</Tag>
                  <Tag color="red">{t('失败:', 'Failed:')} {pickNumber(asRecord(customStatsResponse), ['failed_count']) ?? '-'}</Tag>
                </div>
              </div>
            </Space>
          )}
        </Card>
      )}
    </div>
  )
}

type TotpSetupState = 'idle' | 'setup'

function SecurityPanel() {
  const { message: msg } = App.useApp()
  const t = useText()
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
      msg.error(t('两次输入的密码不一致', 'The two passwords do not match'))
      return
    }
    setLoading(true)
    try {
      const d = await apiFetch('/auth/setup', {
        method: 'POST',
        body: JSON.stringify({ password: values.password }),
      })
      localStorage.setItem('auth_token', d.access_token)
      msg.success(t('密码保护已启用', 'Password protection enabled'))
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
      msg.success(t('密码保护已关闭', 'Password protection disabled'))
      await loadStatus()
    } catch (e: any) {
      msg.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleChangePassword = async (values: { current_password: string; new_password: string; confirm: string }) => {
    if (values.new_password !== values.confirm) {
      msg.error(t('两次输入的新密码不一致', 'The two new passwords do not match'))
      return
    }
    setLoading(true)
    try {
      await apiFetch('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ current_password: values.current_password, new_password: values.new_password }),
      })
      msg.success(t('密码已更新', 'Password updated'))
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
      msg.success(t('双因素认证已启用', '2FA enabled'))
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
      msg.success(t('双因素认证已关闭', '2FA disabled'))
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
        title={t('访问密码保护', 'Access password protection')}
        extra={
          status?.has_password
            ? <Tag color="green"><CheckCircleOutlined /> {t('已启用', 'Enabled')}</Tag>
            : <Tag color="default"><CloseCircleOutlined /> {t('未启用', 'Disabled')}</Tag>
        }
      >
        {!status?.has_password ? (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Typography.Text type="secondary">
              {t('启用后，访问页面需要输入密码。默认不开启，任何能访问此地址的人均可使用。', 'When enabled, visitors must enter a password to access the page. It is off by default, so anyone who can reach this address can use it.')}
            </Typography.Text>
            <Form form={enableForm} layout="vertical" onFinish={handleEnable} requiredMark={false} style={{ maxWidth: 360, marginTop: 8 }}>
              <Form.Item name="password" label={t('设置访问密码', 'Set access password')} rules={[{ required: true, message: t('请输入密码', 'Enter a password') }, { min: 6, message: t('至少 6 位', 'At least 6 characters') }]}>
                <Input.Password placeholder={t('至少 6 位', 'At least 6 characters')} />
              </Form.Item>
              <Form.Item name="confirm" label={t('确认密码', 'Confirm password')} rules={[{ required: true, message: t('请再次输入', 'Enter it again') }]}>
                <Input.Password placeholder={t('再次输入密码', 'Re-enter the password')} />
              </Form.Item>
              <Form.Item style={{ marginBottom: 0 }}>
                <Button type="primary" htmlType="submit" loading={loading} icon={<LockOutlined />}>
                  {t('启用密码保护', 'Enable password protection')}
                </Button>
              </Form.Item>
            </Form>
          </Space>
        ) : (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Typography.Text type="secondary">{t('当前已启用密码保护，关闭后任何人无需密码即可访问。', 'Password protection is currently enabled. Disable it and anyone can access the page without a password.')}</Typography.Text>
            <Button danger loading={loading} onClick={handleDisableAuth}>
              {t('关闭密码保护', 'Disable password protection')}
            </Button>
          </Space>
        )}
      </Card>

      {status?.has_password && (
        <>
          <Card title={t('修改密码', 'Change password')}>
            <Form form={pwForm} layout="vertical" onFinish={handleChangePassword} requiredMark={false} style={{ maxWidth: 360 }}>
              <Form.Item name="current_password" label={t('当前密码', 'Current password')} rules={[{ required: true, message: t('请输入当前密码', 'Enter the current password') }]}>
                <Input.Password placeholder={t('当前密码', 'Current password')} />
              </Form.Item>
              <Form.Item name="new_password" label={t('新密码', 'New password')} rules={[{ required: true, message: t('请输入新密码', 'Enter a new password') }, { min: 6, message: t('至少 6 位', 'At least 6 characters') }]}>
                <Input.Password placeholder={t('新密码（至少 6 位）', 'New password (at least 6 characters)')} />
              </Form.Item>
              <Form.Item name="confirm" label={t('确认新密码', 'Confirm new password')} rules={[{ required: true, message: t('请再次输入', 'Enter it again') }]}>
                <Input.Password placeholder={t('再次输入新密码', 'Re-enter the new password')} />
              </Form.Item>
              <Form.Item style={{ marginBottom: 0 }}>
                <Button type="primary" htmlType="submit" loading={loading} icon={<SaveOutlined />}>
                  {t('更新密码', 'Update password')}
                </Button>
              </Form.Item>
            </Form>
          </Card>

          <Card
            title={t('双因素认证 (2FA)', 'Two-factor authentication (2FA)')}
            extra={
              status?.has_totp
                ? <Tag color="green"><CheckCircleOutlined /> {t('已启用', 'Enabled')}</Tag>
                : <Tag color="default"><CloseCircleOutlined /> {t('未启用', 'Disabled')}</Tag>
            }
          >
            {status?.has_totp ? (
              <Space direction="vertical">
                <Typography.Text type="secondary">
                  {t('登录时需输入 Google Authenticator / Authy 等 App 中的 6 位验证码。', 'You will need the 6-digit code from an authenticator app such as Google Authenticator or Authy when signing in.')}
                </Typography.Text>
                <Button danger loading={loading} onClick={handleDisableTotp}>
                  {t('关闭双因素认证', 'Disable 2FA')}
                </Button>
              </Space>
            ) : totpSetupState === 'idle' ? (
              <Space direction="vertical">
                <Typography.Text type="secondary">
                  {t('启用后，登录时除密码外还需输入验证器 App 中的 6 位验证码，大幅提升安全性。', 'When enabled, sign-in requires the 6-digit code from your authenticator app in addition to the password, which greatly improves security.')}
                </Typography.Text>
                <Button type="primary" loading={loading} onClick={handleSetupTotp} icon={<SafetyOutlined />}>
                  {t('开启双因素认证', 'Enable 2FA')}
                </Button>
              </Space>
            ) : (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Typography.Text strong>{t('1. 用验证器 App 扫描下方二维码', '1. Scan the QR code below with your authenticator app')}</Typography.Text>
                <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                  <QRCode value={totpUri} size={180} />
                  <div style={{ flex: 1 }}>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>{t('无法扫码？手动输入密钥：', 'Can’t scan it? Enter the secret manually:')}</Typography.Text>
                    <Typography.Paragraph copyable style={{ fontFamily: 'monospace', fontSize: 13, marginTop: 4 }}>
                      {totpSecret}
                    </Typography.Paragraph>
                  </div>
                </div>
                <Typography.Text strong>{t('2. 输入 App 中显示的 6 位验证码以确认绑定', '2. Enter the 6-digit code shown in the app to confirm binding')}</Typography.Text>
                <Form form={codeForm} layout="inline" onFinish={handleEnableTotp}>
                  <Form.Item name="code" rules={[{ required: true, message: t('请输入验证码', 'Enter the verification code') }, { len: 6, message: t('6 位数字', '6 digits') }]}>
                    <Input placeholder="000000" maxLength={6} style={{ width: 140, letterSpacing: 4, textAlign: 'center' }} />
                  </Form.Item>
                  <Form.Item>
                    <Button type="primary" htmlType="submit" loading={loading}>{t('确认启用', 'Confirm enable')}</Button>
                  </Form.Item>
                  <Form.Item>
                    <Button onClick={() => setTotpSetupState('idle')}>{t('取消', 'Cancel')}</Button>
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
  const t = useText()
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [activeTab, setActiveTab] = useState('register')
  const currentMailProviderRaw = String(Form.useWatch('mail_provider', form) || '')
  const currentMailImportSource = String(Form.useWatch('mail_import_source', form) || 'microsoft')
  const currentMailProvider = resolveEffectiveMailProvider(currentMailProviderRaw, currentMailImportSource)
  const showFloatingSaveButton = activeTab === 'mailbox' || activeTab === 'chatgpt'
  const contentPaneRef = useRef<HTMLDivElement | null>(null)
  const [floatingSaveBounds, setFloatingSaveBounds] = useState<{ left: number; width: number } | null>(null)

  useEffect(() => {
    apiFetch('/config').then((data) => {
      const configMailProvider = String(data.mail_provider || 'luckmail')
      const isMailImportProvider = configMailProvider === 'microsoft' || configMailProvider === 'outlook' || configMailProvider === 'applemail'
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
      if (!data.outlook_backend) {
        data.outlook_backend = 'graph'
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
      if (!String(data.contribution_enabled ?? '').trim()) {
        data.contribution_enabled = false
      }
      if (!data.contribution_server_url) {
        data.contribution_server_url = 'http://new.xem8k5.top:7317/'
      }
      if (!data.contribution_mode) {
        data.contribution_mode = 'codex'
      }
      if (!data.custom_contribution_url) {
        data.custom_contribution_url = 'http://127.0.0.1:5000'
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
      data.email_domain_rule_enabled = parseBooleanConfigValue(data.email_domain_rule_enabled)
      if (!String(data.email_domain_level_count ?? '').trim()) {
        data.email_domain_level_count = 2
      }
      data.mail_import_source = configMailProvider === 'applemail' ? 'applemail' : 'microsoft'
      data.mail_provider = isMailImportProvider ? 'mail_import' : configMailProvider
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
      values.mail_provider = resolveEffectiveMailProvider(values.mail_provider, values.mail_import_source)
      delete values.mail_import_source
      const domains = normalizeDomainList(values.cfworker_domains)
      const enabledDomains = normalizeDomainList(values.cfworker_enabled_domains).filter((domain) => domains.includes(domain))

      if (domains.length > 0 && enabledDomains.length === 0) {
        setActiveTab('mailbox')
        message.error(t('CF Worker 至少需要启用一个域名', 'CF Worker needs at least one enabled domain'))
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
      values.email_domain_rule_enabled = parseBooleanConfigValue(values.email_domain_rule_enabled)
      const rawDomainLevelCount = Number.parseInt(String(values.email_domain_level_count ?? '').trim(), 10)
      if (values.mail_provider === 'cfworker' && values.email_domain_rule_enabled) {
        if (!Number.isInteger(rawDomainLevelCount) || rawDomainLevelCount < 2) {
          setActiveTab('mailbox')
          message.error(t('域名级数必须是大于等于 2 的整数', 'Domain depth must be an integer greater than or equal to 2'))
          return
        }
      }
      values.email_domain_level_count =
        Number.isInteger(rawDomainLevelCount) && rawDomainLevelCount >= 2
          ? String(rawDomainLevelCount)
          : '2'

      await apiFetch('/config', { method: 'PUT', body: JSON.stringify({ data: values }) })
      form.setFieldsValue({
        mail_provider: values.mail_provider === 'microsoft' || values.mail_provider === 'applemail' ? 'mail_import' : values.mail_provider,
        mail_import_source: values.mail_provider === 'applemail' ? 'applemail' : 'microsoft',
        cpa_enabled: values.cpa_enabled,
        sub2api_enabled: values.sub2api_enabled,
        cfworker_domains: domains,
        cfworker_enabled_domains: enabledDomains,
        cfworker_domain: domains.length > 0 ? '' : values.cfworker_domain,
        cfworker_random_subdomain: values.cfworker_random_subdomain,
        cfworker_random_name_subdomain: values.cfworker_random_name_subdomain,
        contribution_enabled: values.contribution_enabled,
        contribution_mode: values.contribution_mode,
        custom_contribution_url: values.custom_contribution_url,
        custom_contribution_token: values.custom_contribution_token,
        email_domain_rule_enabled: values.email_domain_rule_enabled,
        email_domain_level_count: values.email_domain_level_count,
      })
      message.success(t('保存成功', 'Saved'))
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
              {saved ? t('已保存 ✓', 'Saved ✓') : t('保存配置', 'Save settings')}
            </Button>
          </div>
        </div>
      ) : null}
      <div>
        <h1 style={{ fontSize: 24, fontWeight: 'bold', margin: 0 }}>{t('全局配置', 'Global Settings')}</h1>
        <p style={{ color: '#7a8ba3', marginTop: 4 }}>{t('配置将持久化保存，注册任务自动使用', 'Settings are persisted and used automatically by registration tasks')}</p>
      </div>

      <div style={{ display: 'flex', gap: 24 }}>
        <div style={{ width: 200 }}>
          <Tabs
            tabPosition="left"
            activeKey={activeTab}
            onChange={setActiveTab}
            items={TAB_ITEMS.map((item) => ({
              key: item.key,
              label: (
                <span>
                  {item.icon}
                  <span style={{ marginLeft: 8 }}>{t(item.label, translateSettingsText(item.label))}</span>
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
                      <MailImportPanel form={form} />
                      {currentMailProviderRaw === 'cfworker' ? <CFWorkerDomainPoolSection form={form} /> : null}
                      {mailboxSections.remainingSections.map((section) => (
                        <ConfigSection key={section.title} section={section} />
                      ))}
                      {currentMailProviderRaw !== 'cfworker' ? <CFWorkerDomainPoolSection form={form} /> : null}
                    </>
                  ) : (
                    currentTab.sections.map((section) => (
                      <ConfigSection key={section.title} section={section} />
                    ))
                  )}
                  {showFloatingSaveButton ? <div style={{ height: 8 }} /> : null}
                  {!showFloatingSaveButton ? (
                    <Button type="primary" icon={<SaveOutlined />} onClick={save} loading={saving} block>
              {saved ? t('已保存 ✓', 'Saved ✓') : t('保存配置', 'Save settings')}
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
