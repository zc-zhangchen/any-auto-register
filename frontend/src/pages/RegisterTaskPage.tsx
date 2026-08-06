import { useEffect, useState } from 'react'
import {
  Card,
  Form,
  Input,
  InputNumber,
  Select,
  Button,
  Checkbox,
  Tag,
  Space,
  Typography,
  Descriptions,
} from 'antd'
import {
  PlayCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons'
import { ChatGPTRegistrationModeSwitch } from '@/components/ChatGPTRegistrationModeSwitch'
import { TaskLogPanel } from '@/components/TaskLogPanel'
import { usePersistentChatGPTRegistrationMode } from '@/hooks/usePersistentChatGPTRegistrationMode'
import { parseBooleanConfigValue } from '@/lib/configValueParsers'
import { buildChatGPTRegistrationRequestAdapter } from '@/lib/chatgptRegistrationRequestAdapter'
import { getExecutorOptions, normalizeExecutorForPlatform } from '@/lib/platformExecutorOptions'
import { apiFetch } from '@/lib/utils'

const { Text } = Typography

function resolveEffectiveMailProvider(mailProvider: string, mailImportSource: string) {
  if (mailProvider !== 'mail_import') return mailProvider
  return mailImportSource === 'applemail' ? 'applemail' : 'microsoft'
}

interface RegisterTaskSnapshot {
  id?: string
  task_id?: string
  status?: string
  progress?: string
  skipped?: number
  success?: number
  errors?: string[]
  error?: string
  cashier_urls?: string[]
}

export default function RegisterTaskPage() {
  const [form] = Form.useForm()
  const [task, setTask] = useState<RegisterTaskSnapshot | null>(null)
  const [polling, setPolling] = useState(false)
  const { mode: chatgptRegistrationMode, setMode: setChatgptRegistrationMode } =
    usePersistentChatGPTRegistrationMode()
  const taskErrors = task?.errors ?? []

  useEffect(() => {
    apiFetch('/config').then((cfg) => {
      const currentPlatform = form.getFieldValue('platform') || 'chatgpt'
      const configMailProvider = String(cfg.mail_provider || 'luckmail')
      const isMailImportProvider = configMailProvider === 'microsoft' || configMailProvider === 'outlook' || configMailProvider === 'applemail'
      form.setFieldsValue({
        executor_type: normalizeExecutorForPlatform(currentPlatform, cfg.default_executor),
        captcha_solver: cfg.default_captcha_solver || 'yescaptcha',
        mail_provider: isMailImportProvider ? 'mail_import' : configMailProvider,
        mail_import_source: configMailProvider === 'applemail' ? 'applemail' : 'microsoft',
        applemail_base_url: cfg.applemail_base_url || 'https://www.appleemail.top',
        applemail_pool_dir: cfg.applemail_pool_dir || 'mail',
        applemail_pool_file: cfg.applemail_pool_file || '',
        applemail_mailboxes: cfg.applemail_mailboxes || 'INBOX,Junk',
        yescaptcha_key: cfg.yescaptcha_key || '',
        moemail_api_url: cfg.moemail_api_url || '',
        moemail_api_key: cfg.moemail_api_key || '',
        skymail_api_base: cfg.skymail_api_base || 'https://api.skymail.ink',
        skymail_token: cfg.skymail_token || '',
        skymail_domain: cfg.skymail_domain || '',
        cloudmail_api_base: cfg.cloudmail_api_base || '',
        cloudmail_admin_email: cfg.cloudmail_admin_email || '',
        cloudmail_admin_password: cfg.cloudmail_admin_password || '',
        cloudmail_domain: cfg.cloudmail_domain || '',
        cloudmail_subdomain: cfg.cloudmail_subdomain || '',
        cloudmail_timeout: cfg.cloudmail_timeout || 30,
        outlook_backend: cfg.outlook_backend || 'graph',
        laoudo_auth: cfg.laoudo_auth || '',
        laoudo_email: cfg.laoudo_email || '',
        laoudo_account_id: cfg.laoudo_account_id || '',
        gptmail_base_url: cfg.gptmail_base_url || 'https://mail.chatgpt.org.uk',
        gptmail_api_key: cfg.gptmail_api_key || '',
        gptmail_mode: cfg.gptmail_mode || 'api',
        gptmail_domain: cfg.gptmail_domain || '',
        opentrashmail_api_url: cfg.opentrashmail_api_url || '',
        opentrashmail_domain: cfg.opentrashmail_domain || '',
        opentrashmail_password: cfg.opentrashmail_password || '',
        cfrouting_domain: cfg.cfrouting_domain || '',
        cfrouting_imap_server: cfg.cfrouting_imap_server || '',
        cfrouting_imap_port: Number(cfg.cfrouting_imap_port || 993),
        cfrouting_username: cfg.cfrouting_username || '',
        cfrouting_password: cfg.cfrouting_password || '',
        cfrouting_mailboxes: cfg.cfrouting_mailboxes || 'INBOX',
        maliapi_base_url: cfg.maliapi_base_url || 'https://maliapi.215.im/v1',
        maliapi_api_key: cfg.maliapi_api_key || '',
        maliapi_domain: cfg.maliapi_domain || '',
        maliapi_auto_domain_strategy: cfg.maliapi_auto_domain_strategy || 'balanced',
        duckmail_api_url: cfg.duckmail_api_url || '',
        duckmail_provider_url: cfg.duckmail_provider_url || '',
        duckmail_bearer: cfg.duckmail_bearer || '',
        freemail_api_url: cfg.freemail_api_url || '',
        freemail_admin_token: cfg.freemail_admin_token || '',
        freemail_username: cfg.freemail_username || '',
        freemail_password: cfg.freemail_password || '',
        freemail_domain: cfg.freemail_domain || '',
        cfworker_api_url: cfg.cfworker_api_url || '',
        cfworker_admin_token: cfg.cfworker_admin_token || '',
        cfworker_custom_auth: cfg.cfworker_custom_auth || '',
        cfworker_domain_override: '',
        cfworker_subdomain: cfg.cfworker_subdomain || '',
        cfworker_random_subdomain: parseBooleanConfigValue(cfg.cfworker_random_subdomain),
        cfworker_random_name_subdomain: parseBooleanConfigValue(cfg.cfworker_random_name_subdomain),
        cfworker_fingerprint: cfg.cfworker_fingerprint || '',
        smstome_cookie: cfg.smstome_cookie || '',
        smstome_country_slugs: cfg.smstome_country_slugs || '',
        smstome_phone_attempts: cfg.smstome_phone_attempts || '',
        smstome_otp_timeout_seconds: cfg.smstome_otp_timeout_seconds || '',
        smstome_poll_interval_seconds: cfg.smstome_poll_interval_seconds || '',
        smstome_sync_max_pages_per_country: cfg.smstome_sync_max_pages_per_country || '',
        luckmail_base_url: cfg.luckmail_base_url || 'https://mails.luckyous.com/',
        luckmail_api_key: cfg.luckmail_api_key || '',
        luckmail_email_type: cfg.luckmail_email_type || '',
        luckmail_domain: cfg.luckmail_domain || '',
      })
    })
  }, [form])

  const submit = async () => {
    const values = await form.validateFields()
    const effectiveMailProvider = resolveEffectiveMailProvider(values.mail_provider, values.mail_import_source)
    const registerExtra = {
      mail_provider: effectiveMailProvider,
      applemail_base_url: values.applemail_base_url,
      applemail_pool_dir: values.applemail_pool_dir,
      applemail_pool_file: values.applemail_pool_file,
      applemail_mailboxes: values.applemail_mailboxes,
      laoudo_auth: values.laoudo_auth,
      laoudo_email: values.laoudo_email,
      laoudo_account_id: values.laoudo_account_id,
      gptmail_base_url: values.gptmail_base_url,
      gptmail_api_key: values.gptmail_api_key,
      gptmail_mode: values.gptmail_mode,
      gptmail_domain: values.gptmail_domain,
      opentrashmail_api_url: values.opentrashmail_api_url,
      opentrashmail_domain: values.opentrashmail_domain,
      opentrashmail_password: values.opentrashmail_password,
      cfrouting_domain: values.cfrouting_domain,
      cfrouting_imap_server: values.cfrouting_imap_server,
      cfrouting_imap_port: values.cfrouting_imap_port,
      cfrouting_username: values.cfrouting_username,
      cfrouting_password: values.cfrouting_password,
      cfrouting_mailboxes: values.cfrouting_mailboxes,
      maliapi_base_url: values.maliapi_base_url,
      maliapi_api_key: values.maliapi_api_key,
      maliapi_domain: values.maliapi_domain,
      maliapi_auto_domain_strategy: values.maliapi_auto_domain_strategy,
      moemail_api_url: values.moemail_api_url,
      moemail_api_key: values.moemail_api_key,
      skymail_api_base: values.skymail_api_base,
      skymail_token: values.skymail_token,
      skymail_domain: values.skymail_domain,
      cloudmail_api_base: values.cloudmail_api_base,
      cloudmail_admin_email: values.cloudmail_admin_email,
      cloudmail_admin_password: values.cloudmail_admin_password,
      cloudmail_domain: values.cloudmail_domain,
      cloudmail_subdomain: values.cloudmail_subdomain,
      cloudmail_timeout: values.cloudmail_timeout,
      outlook_backend: values.outlook_backend,
      duckmail_api_url: values.duckmail_api_url,
      duckmail_provider_url: values.duckmail_provider_url,
      duckmail_bearer: values.duckmail_bearer,
      freemail_api_url: values.freemail_api_url,
      freemail_admin_token: values.freemail_admin_token,
      freemail_username: values.freemail_username,
      freemail_password: values.freemail_password,
      freemail_domain: values.freemail_domain,
      cfworker_api_url: values.cfworker_api_url,
      cfworker_admin_token: values.cfworker_admin_token,
      cfworker_custom_auth: values.cfworker_custom_auth,
      cfworker_domain_override: values.cfworker_domain_override,
      cfworker_subdomain: values.cfworker_subdomain,
      cfworker_random_subdomain: values.cfworker_random_subdomain,
      cfworker_random_name_subdomain: values.cfworker_random_name_subdomain,
      cfworker_fingerprint: values.cfworker_fingerprint,
      smstome_cookie: values.smstome_cookie,
      smstome_country_slugs: values.smstome_country_slugs,
      smstome_phone_attempts: values.smstome_phone_attempts,
      smstome_otp_timeout_seconds: values.smstome_otp_timeout_seconds,
      smstome_poll_interval_seconds: values.smstome_poll_interval_seconds,
      smstome_sync_max_pages_per_country: values.smstome_sync_max_pages_per_country,
      luckmail_base_url: values.luckmail_base_url,
      luckmail_api_key: values.luckmail_api_key,
      luckmail_email_type: values.luckmail_email_type,
      luckmail_domain: values.luckmail_domain,
      yescaptcha_key: values.yescaptcha_key,
      solver_url: values.solver_url,
    }
    const chatgptRegistrationRequestAdapter =
      buildChatGPTRegistrationRequestAdapter(
        values.platform,
        chatgptRegistrationMode,
      )
    const adaptedRegisterExtra = chatgptRegistrationRequestAdapter
      ? chatgptRegistrationRequestAdapter.extendExtra(registerExtra)
      : registerExtra

    const res = await apiFetch('/tasks/register', {
      method: 'POST',
      body: JSON.stringify({
        platform: values.platform,
        email: values.email || null,
        password: values.password || null,
        count: values.count,
        concurrency: values.concurrency,
        register_delay_seconds: values.register_delay_seconds || 0,
        proxy: values.proxy || null,
        executor_type: values.executor_type,
        captcha_solver: values.captcha_solver,
        extra: adaptedRegisterExtra,
      }),
    })
    setTask(res)
    setPolling(true)
    pollTask(res.task_id)
  }

  const pollTask = async (id: string) => {
    const interval = setInterval(async () => {
      const t = await apiFetch(`/tasks/${id}`)
      setTask(t)
      if (t.status === 'done' || t.status === 'failed' || t.status === 'stopped') {
        clearInterval(interval)
        setPolling(false)
        if (t.cashier_urls && t.cashier_urls.length > 0) {
          t.cashier_urls.forEach((url: string) => window.open(url, '_blank'))
        }
      }
    }, 2000)
  }

  const mailProviderRaw = Form.useWatch('mail_provider', form)
  const mailImportSource = Form.useWatch('mail_import_source', form)
  const mailProvider = resolveEffectiveMailProvider(String(mailProviderRaw || ''), String(mailImportSource || 'microsoft'))
  const captchaSolver = Form.useWatch('captcha_solver', form)
  const platform = Form.useWatch('platform', form)
  const executorOptions = getExecutorOptions(platform)

  useEffect(() => {
    const currentExecutor = form.getFieldValue('executor_type')
    const normalizedExecutor = normalizeExecutorForPlatform(platform, currentExecutor)
    if (currentExecutor !== normalizedExecutor) {
      form.setFieldValue('executor_type', normalizedExecutor)
    }
  }, [form, platform])

  return (
    <div style={{ maxWidth: 800 }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 'bold', margin: 0 }}>注册任务</h1>
        <p style={{ color: '#7a8ba3', marginTop: 4 }}>创建账号自动注册任务</p>
      </div>

      <Form form={form} layout="vertical" onFinish={submit} initialValues={{
        platform: 'chatgpt',
        executor_type: 'protocol',
        captcha_solver: 'yescaptcha',
        mail_provider: 'luckmail',
        mail_import_source: 'microsoft',
        applemail_base_url: 'https://www.appleemail.top',
        applemail_pool_dir: 'mail',
        applemail_mailboxes: 'INBOX,Junk',
        outlook_backend: 'graph',
        cfrouting_imap_port: 993,
        cfrouting_mailboxes: 'INBOX',
        gptmail_base_url: 'https://mail.chatgpt.org.uk',
        gptmail_mode: 'api',
        cloudmail_timeout: 30,
        count: 1,
        concurrency: 1,
        register_delay_seconds: 0,
        maliapi_base_url: 'https://maliapi.215.im/v1',
        maliapi_auto_domain_strategy: 'balanced',
        solver_url: 'http://localhost:8889',
      }}>
        <Card title="基本配置" style={{ marginBottom: 16 }}>
          <Form.Item name="platform" label="平台" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'chatgpt', label: 'ChatGPT' },
                { value: 'cursor', label: 'Cursor' },
                { value: 'kiro', label: 'Kiro' },
                { value: 'grok', label: 'Grok' },
                { value: 'tavily', label: 'Tavily' },
                { value: 'openblocklabs', label: 'OpenBlockLabs' },
              ]}
            />
          </Form.Item>
          <Form.Item name="executor_type" label="执行器" rules={[{ required: true }]}>
            <Select options={executorOptions} />
          </Form.Item>
          <Form.Item name="captcha_solver" label="验证码" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'yescaptcha', label: 'YesCaptcha' },
                { value: 'local_solver', label: '本地 Solver (Camoufox)' },
                { value: 'manual', label: '手动' },
              ]}
            />
          </Form.Item>
          <Space style={{ width: '100%' }}>
            <Form.Item name="count" label="批量数量" style={{ flex: 1 }}>
              <Input type="number" min={1} />
            </Form.Item>
            <Form.Item name="concurrency" label="并发数" style={{ flex: 1 }}>
              <Input type="number" min={1} />
            </Form.Item>
          </Space>
          <Space style={{ width: '100%' }}>
            <Form.Item name="register_delay_seconds" label="每个注册延迟(秒)" style={{ flex: 1 }}>
              <InputNumber min={0} precision={1} step={0.5} style={{ width: '100%' }} placeholder="0" />
            </Form.Item>
            <Form.Item name="proxy" label="代理 (可选)" style={{ flex: 1 }}>
              <Input placeholder="http://user:pass@host:port" />
            </Form.Item>
          </Space>
          {platform === 'chatgpt' && (
            <Form.Item label="ChatGPT Token 方案">
              <ChatGPTRegistrationModeSwitch
                mode={chatgptRegistrationMode}
                onChange={setChatgptRegistrationMode}
              />
            </Form.Item>
          )}
        </Card>

        <Card title="邮箱配置" style={{ marginBottom: 16 }}>
          <Form.Item name="mail_provider" label="邮箱服务" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'luckmail', label: 'LuckMail' },
                { value: 'mail_import', label: '邮箱导入' },
                { value: 'moemail', label: 'MoeMail (sall.cc)' },
                { value: 'tempmail_lol', label: 'TempMail.lol' },
                { value: 'skymail', label: 'SkyMail (CloudMail)' },
                { value: 'cloudmail', label: 'CloudMail (genToken)' },
                { value: 'maliapi', label: 'YYDS Mail / MaliAPI' },
                { value: 'gptmail', label: 'GPTMail' },
                { value: 'opentrashmail', label: 'OpenTrashMail' },
                { value: 'cfrouting', label: 'Cloudflare 邮件路由（直转邮箱）' },
                { value: 'duckmail', label: 'DuckMail' },
                { value: 'freemail', label: 'Freemail' },
                { value: 'laoudo', label: 'Laoudo' },
                { value: 'cfworker', label: 'CF Worker' },
              ]}
            />
          </Form.Item>
          {mailProviderRaw === 'mail_import' && (
            <Form.Item name="mail_import_source" label="导入类型" rules={[{ required: true }]}>
              <Select
                options={[
                  { value: 'microsoft', label: '微软邮箱（Outlook / Hotmail）' },
                  { value: 'applemail', label: 'AppleMail / 小苹果' },
                ]}
              />
            </Form.Item>
          )}
          {mailProvider === 'microsoft' && (
            <Form.Item
              name="outlook_backend"
              label="微软收信方式"
              extra="默认使用 Graph；若账号没有 OAuth 凭据，运行时会自动回退到 IMAP。"
            >
              <Select
                options={[
                  { value: 'graph', label: 'Graph（默认）' },
                  { value: 'imap', label: 'IMAP' },
                ]}
              />
            </Form.Item>
          )}
          {mailProvider === 'skymail' && (
            <>
              <Form.Item name="skymail_api_base" label="API Base">
                <Input placeholder="https://api.skymail.ink" />
              </Form.Item>
              <Form.Item name="skymail_token" label="Authorization Token">
                <Input.Password placeholder="Bearer xxxxx" />
              </Form.Item>
              <Form.Item name="skymail_domain" label="邮箱域名">
                <Input placeholder="mail.example.com" />
              </Form.Item>
            </>
          )}
          {mailProvider === 'cloudmail' && (
            <>
              <Form.Item name="cloudmail_api_base" label="API Base" rules={[{ required: true, message: '请输入 CloudMail API 地址' }]}>
                <Input placeholder="https://cloudmail.example.com" />
              </Form.Item>
              <Form.Item name="cloudmail_admin_email" label="管理员邮箱（可选）" extra="留空自动使用 admin@域名">
                <Input placeholder="admin@example.com" />
              </Form.Item>
              <Form.Item name="cloudmail_admin_password" label="管理员密码" rules={[{ required: true, message: '请输入 CloudMail 管理员密码' }]}>
                <Input.Password placeholder="admin password" />
              </Form.Item>
              <Form.Item name="cloudmail_domain" label="邮箱域名（可选）" extra="支持单个域名，或逗号分隔多个域名">
                <Input placeholder="mail.example.com,mail2.example.com" />
              </Form.Item>
              <Form.Item name="cloudmail_subdomain" label="子域名（可选）">
                <Input placeholder="pool-a" />
              </Form.Item>
              <Form.Item name="cloudmail_timeout" label="请求超时秒数">
                <InputNumber min={5} max={120} style={{ width: '100%' }} />
              </Form.Item>
            </>
          )}
          {mailProvider === 'laoudo' && (
            <>
              <Form.Item name="laoudo_email" label="邮箱地址">
                <Input placeholder="xxx@laoudo.com" />
              </Form.Item>
              <Form.Item name="laoudo_account_id" label="Account ID">
                <Input placeholder="563" />
              </Form.Item>
              <Form.Item name="laoudo_auth" label="JWT Token">
                <Input placeholder="eyJ..." />
              </Form.Item>
            </>
          )}
          {mailProvider === 'maliapi' && (
            <>
              <Form.Item name="maliapi_base_url" label="API URL">
                <Input placeholder="https://maliapi.215.im/v1" />
              </Form.Item>
              <Form.Item name="maliapi_api_key" label="API Key">
                <Input.Password placeholder="AC-..." />
              </Form.Item>
              <Form.Item name="maliapi_domain" label="邮箱域名（可选）">
                <Input placeholder="example.com" />
              </Form.Item>
              <Form.Item name="maliapi_auto_domain_strategy" label="自动域名策略">
                <Select
                  options={[
                    { value: 'balanced', label: 'balanced' },
                    { value: 'prefer_owned', label: 'prefer_owned' },
                    { value: 'prefer_public', label: 'prefer_public' },
                  ]}
                />
              </Form.Item>
            </>
          )}
          {mailProvider === 'applemail' && (
            <>
              <Form.Item name="applemail_base_url" label="API URL">
                <Input placeholder="https://www.appleemail.top" />
              </Form.Item>
              <Form.Item
                name="applemail_pool_dir"
                label="邮箱池目录"
                extra="默认读取项目根目录下的 mail 目录。"
              >
                <Input placeholder="mail" />
              </Form.Item>
              <Form.Item
                name="applemail_pool_file"
                label="邮箱池文件（可选）"
                extra="留空会自动使用目录中最新的 .json/.txt 文件；JSON 内容导入请到全局配置页操作。"
              >
                <Input placeholder="applemail_20260403.json" />
              </Form.Item>
              <Form.Item name="applemail_mailboxes" label="轮询文件夹">
                <Input placeholder="INBOX,Junk" />
              </Form.Item>
            </>
          )}
          {mailProvider === 'gptmail' && (
            <>
              <Form.Item name="gptmail_base_url" label="API URL">
                <Input placeholder="https://mail.chatgpt.org.uk" />
              </Form.Item>
              <Form.Item name="gptmail_api_key" label="API Key">
                <Input.Password placeholder="gpt-test" />
              </Form.Item>
              <Form.Item
                name="gptmail_mode"
                label="生成模式"
                extra="api 使用站点 API Key；automation 走网页端会话，自动完成 cookie + token 初始化"
              >
                <Select
                  options={[
                    { value: 'api', label: 'API' },
                    { value: 'automation', label: 'Automation' },
                  ]}
                />
              </Form.Item>
              <Form.Item
                name="gptmail_domain"
                label="邮箱域名（可选）"
                extra="已知当前可用域名时可直接本地拼装随机地址，省掉一次 generate-email 请求"
              >
                <Input placeholder="example.com" />
              </Form.Item>
            </>
          )}
          {mailProvider === 'opentrashmail' && (
            <>
              <Form.Item name="opentrashmail_api_url" label="API URL" rules={[{ required: true, message: '请输入 OpenTrashMail 地址' }]}>
                <Input placeholder="http://mail.example.com:8085" />
              </Form.Item>
              <Form.Item
                name="opentrashmail_domain"
                label="邮箱域名（可选）"
                extra="已知 OpenTrashMail 当前启用域名时可直接本地拼装随机地址；留空则调用 /api/random 自动获取"
              >
                <Input placeholder="xiyoufm.com" />
              </Form.Item>
              <Form.Item
                name="opentrashmail_password"
                label="站点密码（可选）"
                extra="当 OpenTrashMail 开启 PASSWORD 保护时填写，会自动追加到 JSON API 查询参数"
              >
                <Input.Password placeholder="留空表示未启用" />
              </Form.Item>
            </>
          )}
          {mailProvider === 'cfrouting' && (
            <>
              <Form.Item
                name="cfrouting_domain"
                label="路由域名"
                rules={[{ required: true, message: '请输入已在 Cloudflare 开启邮件路由的域名' }]}
                extra="支持单个域名，或逗号分隔多个已配置 catch-all / 转发规则的域名。"
              >
                <Input placeholder="example.com,mail.example.com" />
              </Form.Item>
              <Form.Item
                name="cfrouting_imap_server"
                label="目标邮箱 IMAP Server"
                rules={[{ required: true, message: '请输入转发目标邮箱的 IMAP Server' }]}
                extra="常见值：QQ 填 imap.qq.com，Gmail 填 imap.gmail.com。"
              >
                <Input placeholder="imap.qq.com / imap.gmail.com / outlook.office365.com" />
              </Form.Item>
              <Form.Item name="cfrouting_imap_port" label="IMAP Port">
                <InputNumber min={1} max={65535} style={{ width: '100%' }} placeholder="993" />
              </Form.Item>
              <Form.Item
                name="cfrouting_username"
                label="目标邮箱用户名"
                rules={[{ required: true, message: '请输入目标邮箱用户名' }]}
                extra="填写完整邮箱地址，例如 your@qq.com 或 your@gmail.com。"
              >
                <Input placeholder="your@qq.com / your@gmail.com" />
              </Form.Item>
              <Form.Item
                name="cfrouting_password"
                label="目标邮箱密码 / 授权码 / App Password"
                rules={[{ required: true, message: '请输入目标邮箱密码或应用专用密码' }]}
                extra="QQ 通常填邮箱授权码；个人 Gmail 通常填 App Password。"
              >
                <Input.Password placeholder="QQ 授权码 / Gmail App Password" />
              </Form.Item>
              <Form.Item
                name="cfrouting_mailboxes"
                label="轮询文件夹"
                extra="默认只查 INBOX。QQ 和 Gmail 都建议先从 INBOX 开始；若实际落在别处，再填对应 IMAP 文件夹名。"
              >
                <Input placeholder="INBOX" />
              </Form.Item>
            </>
          )}
          {mailProvider === 'cfworker' && (
            <>
              <Form.Item name="cfworker_api_url" label="API URL">
                <Input placeholder="https://apimail.example.com" />
              </Form.Item>
              <Form.Item name="cfworker_admin_token" label="Admin Token">
                <Input placeholder="abc123,,,abc" />
              </Form.Item>
              <Form.Item name="cfworker_custom_auth" label="Site Password">
                <Input.Password placeholder="private site password" />
              </Form.Item>
              <Form.Item
                name="cfworker_domain_override"
                label="单次任务指定域名（可选）"
                extra="留空时将从设置页已启用的域名列表中随机选择。"
              >
                <Input placeholder="example.com" />
              </Form.Item>
              <Form.Item
                name="cfworker_subdomain"
                label="子域名（可选）"
                extra="填写后将生成 xxx@子域名.根域名；若启用随机子域名，则会生成 xxx@随机值.子域名.根域名。"
              >
                <Input placeholder="mail / pool-a" />
              </Form.Item>
              <Form.Item name="cfworker_random_subdomain" valuePropName="checked">
                <Checkbox>每次注册前随机生成一层子域名</Checkbox>
              </Form.Item>
              <Form.Item name="cfworker_random_name_subdomain" valuePropName="checked">
                <Checkbox>使用随机姓名作为子域名</Checkbox>
              </Form.Item>
              <Form.Item name="cfworker_fingerprint" label="Fingerprint (可选)">
                <Input placeholder="cfb82279f..." />
              </Form.Item>
            </>
          )}
          {mailProvider === 'freemail' && (
            <>
              <Form.Item name="freemail_api_url" label="API URL" rules={[{ required: true, message: '请输入 Freemail API 地址' }]}>
                <Input placeholder="https://mail.example.com" />
              </Form.Item>
              <Form.Item name="freemail_admin_token" label="管理员令牌（可选）">
                <Input.Password placeholder="JWT_TOKEN" />
              </Form.Item>
              <Form.Item name="freemail_username" label="用户名（可选）">
                <Input placeholder="admin" />
              </Form.Item>
              <Form.Item name="freemail_password" label="密码（可选）">
                <Input.Password placeholder="password" />
              </Form.Item>
              <Form.Item name="freemail_domain" label="邮箱域名（可选）" extra="填写后会优先使用该域名生成邮箱">
                <Input placeholder="example.com" />
              </Form.Item>
            </>
          )}
          {mailProvider === 'luckmail' && (
            <>
              <Form.Item name="luckmail_base_url" label="平台地址">
                <Input placeholder="https://mails.luckyous.com" />
              </Form.Item>
              <Form.Item name="luckmail_api_key" label="API Key">
                <Input.Password placeholder="ak_..." />
              </Form.Item>
              <Form.Item name="luckmail_email_type" label="邮箱类型（可选）">
                <Select
                  options={[
                    { value: '', label: '自动 / 留空' },
                    { value: 'ms_graph', label: '微软邮箱 - Graph' },
                    { value: 'ms_imap', label: '微软邮箱 - IMAP' },
                    { value: 'self_built', label: '自建邮箱' },
                  ]}
                />
              </Form.Item>
              <Form.Item name="luckmail_domain" label="邮箱域名（可选）">
                <Input placeholder="outlook.com" />
              </Form.Item>
            </>
          )}
        </Card>

        {platform === 'chatgpt' && (
          <Card title="ChatGPT 手机验证" style={{ marginBottom: 16 }}>
            <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
              仅在 OAuth 流程进入 `add_phone` 时使用，用于自动取号并轮询短信验证码。
            </Text>
            <Form.Item name="smstome_cookie" label="SMSToMe Cookie">
              <Input.Password placeholder="cf_clearance=...; PHPSESSID=..." />
            </Form.Item>
            <Form.Item name="smstome_country_slugs" label="国家列表">
              <Input placeholder="united-kingdom,poland,finland" />
            </Form.Item>
            <Form.Item name="smstome_phone_attempts" label="手机号尝试次数">
              <Input placeholder="3" />
            </Form.Item>
            <Form.Item name="smstome_otp_timeout_seconds" label="短信等待秒数">
              <Input placeholder="45" />
            </Form.Item>
            <Form.Item name="smstome_poll_interval_seconds" label="轮询间隔秒数">
              <Input placeholder="5" />
            </Form.Item>
            <Form.Item name="smstome_sync_max_pages_per_country" label="每国同步页数">
              <Input placeholder="5" />
            </Form.Item>
          </Card>
        )}

        {captchaSolver === 'yescaptcha' && (
          <Card title="验证码配置" style={{ marginBottom: 16 }}>
            <Form.Item name="yescaptcha_key" label="YesCaptcha Key">
              <Input />
            </Form.Item>
          </Card>
        )}

        {captchaSolver === 'local_solver' && (
          <Card title="本地 Solver 配置" style={{ marginBottom: 16 }}>
            <Form.Item name="solver_url" label="Solver URL">
              <Input />
            </Form.Item>
            <Text type="secondary" style={{ fontSize: 12 }}>
              启动命令: python services/turnstile_solver/start.py --browser_type camoufox --port 8889
            </Text>
          </Card>
        )}

        <Button type="primary" htmlType="submit" block disabled={polling} icon={polling ? <LoadingOutlined /> : <PlayCircleOutlined />}>
          {polling ? '注册中...' : '开始注册'}
        </Button>
      </Form>

      {task && (
        <Card title={
          <Space>
            <span>任务状态</span>
            <Tag color={
              task.status === 'done' ? 'success' :
              task.status === 'stopped' ? 'warning' :
              task.status === 'failed' ? 'error' : 'processing'
            }>
              {task.status}
            </Tag>
          </Space>
        } style={{ marginTop: 16 }}>
          <Descriptions column={1} size="small">
            <Descriptions.Item label="任务 ID">
              <Text copyable style={{ fontFamily: 'monospace' }}>{task.id}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="进度">{task.progress}</Descriptions.Item>
            <Descriptions.Item label="跳过">{task.skipped ?? 0}</Descriptions.Item>
          </Descriptions>
          {task.success != null && (
            <div style={{ marginTop: 8, color: '#10b981' }}>
              <CheckCircleOutlined /> 成功 {task.success} 个
            </div>
          )}
          {taskErrors.length > 0 && (
            <div style={{ marginTop: 8 }}>
              {taskErrors.map((e: string, i: number) => (
                <div key={i} style={{ color: '#ef4444', marginBottom: 4 }}>
                  <CloseCircleOutlined /> {e}
                </div>
              ))}
            </div>
          )}
          {task.error && (
            <div style={{ marginTop: 8, color: '#ef4444' }}>
              <CloseCircleOutlined /> {task.error}
            </div>
          )}
          {task.id ? (
            <div style={{ marginTop: 16 }}>
              <TaskLogPanel taskId={task.id} />
            </div>
          ) : null}
        </Card>
      )}
    </div>
  )
}
