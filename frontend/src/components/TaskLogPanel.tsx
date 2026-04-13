import { useEffect, useRef, useState } from 'react'
import { Button, message, Space, Tag } from 'antd'
import { CopyOutlined, FastForwardOutlined, StopOutlined } from '@ant-design/icons'

import { API_BASE, apiFetch, getToken } from '@/lib/utils'
import { useText, useUiLanguage } from '@/lib/uiLanguage'

interface TaskLogPanelProps {
  taskId: string
  onDone?: () => void
}

type TaskTerminalStatus = 'idle' | 'done' | 'failed' | 'stopped'

interface RegisterSummary {
  success: number
  registered: number
  total: number
}

function parseCounter(value: unknown): number {
  const n = Number(value || 0)
  if (!Number.isFinite(n) || n < 0) return 0
  return Math.floor(n)
}

function normalizeSummary(next: RegisterSummary): RegisterSummary {
  const success = parseCounter(next.success)
  const registered = Math.max(parseCounter(next.registered), success)
  const total = Math.max(parseCounter(next.total), registered)
  return { success, registered, total }
}

function mergeSummary(previous: RegisterSummary, incoming: Partial<RegisterSummary>): RegisterSummary {
  return normalizeSummary({
    success: incoming.success ?? previous.success,
    registered: incoming.registered ?? previous.registered,
    total: incoming.total ?? previous.total,
  })
}

function translateTaskLogLine(line: string, english: boolean): string {
  if (!english) return line
  const replacements: Array<[RegExp, string]> = [
    [/ChatGPT RT 全新主链路启动/g, 'ChatGPT RT new primary flow started'],
    [/请求模式:/g, 'Request mode:'],
    [/实现策略:/g, 'Implementation strategy:'],
    [/注册状态起点:/g, 'Registration state start:'],
    [/注册状态推进:/g, 'Registration state progress:'],
    [/注册状态机参数:/g, 'Registration state machine params:'],
    [/注册链路/g, 'Registration flow'],
    [/开始注册第/g, 'Starting registration for the '],
    [/个账号/g, ' account'],
    [/1\. 创建邮箱\.\.\./g, '1. Create mailbox...'],
    [/2\. 执行注册状态机（interrupt 模式：不在注册阶段提交 about_you）\.\.\./g, '2. Run the registration state machine (interrupt mode: do not submit about_you during registration)...'],
    [/正在创建 custom_provider 邮箱\.\.\./g, 'Creating a custom_provider mailbox...'],
    [/成功创建邮箱:/g, 'Mailbox created successfully:'],
    [/邮箱:/g, 'Email:'],
    [/密码:/g, 'Password:'],
    [/注册信息:/g, 'Registration info:'],
    [/生日:/g, 'Birthday:'],
    [/流程策略:/g, 'Flow strategy:'],
    [/验证码等待策略:/g, 'OTP wait strategy:'],
    [/读取 OAuthClient 配置（默认600s）/g, 'Reading OAuthClient config (default 600s)'],
    [/注册阶段推进到 about_you 后切换到 OAuth 流程继续完成后续步骤/g, 'Advance to about_you, then switch to the OAuth flow to complete the remaining steps'],
    [/执行注册状态机（interrupt 模式：不在注册阶段提交 about_you）/g, 'Executing the registration state machine (interrupt mode: do not submit about_you during registration)'],
    [/访问 ChatGPT 首页/g, 'Visiting ChatGPT homepage'],
    [/获取 CSRF token/g, 'Fetching CSRF token'],
    [/提交邮箱:/g, 'Submitting email:'],
    [/获取到 authorize URL/g, 'Authorize URL obtained'],
    [/访问 authorize URL/g, 'Visiting authorize URL'],
    [/重定向到:/g, 'Redirected to:'],
    [/Authorize → /g, 'Authorize → /'],
    [/全新注册流程/g, 'Fresh registration flow'],
    [/注册用户:/g, 'Registering user:'],
    [/Sentinel Browser 启动:/g, 'Sentinel Browser start:'],
    [/Sentinel Browser 模式:/g, 'Sentinel Browser mode:'],
    [/RT 注册主链路异常:/g, 'RT registration main flow error:'],
    [/注册失败:/g, 'Registration failed:'],
    [/完成: 成功/g, 'Completed: success'],
    [/完成: 成功/g, 'Completed: success'],
    [/跳过/g, 'skipped'],
    [/失败/g, 'failed'],
    [/成功/g, 'success'],
    [/正在注册/g, 'Registering'],
  ]

  return replacements.reduce((acc, [pattern, replacement]) => acc.replace(pattern, replacement), line)
}

export function TaskLogPanel({ taskId, onDone }: TaskLogPanelProps) {
  const t = useText()
  const { language } = useUiLanguage()
  const [lines, setLines] = useState<string[]>([])
  const [summary, setSummary] = useState<RegisterSummary>({ success: 0, registered: 0, total: 0 })
  const [error, setError] = useState('')
  const [terminalStatus, setTerminalStatus] = useState<TaskTerminalStatus>('idle')
  const [skipLoading, setSkipLoading] = useState(false)
  const [stopLoading, setStopLoading] = useState(false)
  const [stopRequested, setStopRequested] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const onDoneRef = useRef(onDone)
  const nextSinceRef = useRef(0)

  const isFinished = terminalStatus !== 'idle' || stopRequested

  const handleCopyAll = async () => {
    try {
      await navigator.clipboard.writeText(lines.join('\n'))
      message.success(t('日志已复制', 'Logs copied'))
    } catch {
      message.error(t('复制失败', 'Copy failed'))
    }
  }

  const handleSkipCurrent = async () => {
    if (isFinished) return
    setSkipLoading(true)
    try {
      const response = await apiFetch(`/tasks/${taskId}/skip-current`, { method: 'POST' }) as {
        control?: { targeted_skip_attempts?: number }
      }
      const targeted = Number(response.control?.targeted_skip_attempts || 0)
      message.success(
        targeted > 1
          ? t(`已发送跳过 ${targeted} 个进行中账号请求`, `Requested skip for ${targeted} running accounts`)
          : t('已发送跳过当前账号请求', 'Requested skip for the current account'),
      )
    } catch (error_: unknown) {
      const detail = error_ instanceof Error ? error_.message : t('请求失败', 'Request failed')
      message.error(detail)
    } finally {
      setSkipLoading(false)
    }
  }

  const handleStopTask = async () => {
    if (isFinished) return
    setStopLoading(true)
    try {
      await apiFetch(`/tasks/${taskId}/stop`, { method: 'POST' })
      setStopRequested(true)
      message.success(t('已发送停止任务请求，正在停止进行中的线程', 'Requested task stop; running threads are shutting down'))
    } catch (error_: unknown) {
      const detail = error_ instanceof Error ? error_.message : t('请求失败', 'Request failed')
      message.error(detail)
    } finally {
      setStopLoading(false)
    }
  }

  useEffect(() => {
    onDoneRef.current = onDone
  }, [onDone])

  useEffect(() => {
    if (!taskId) return
    const controller = new AbortController()
    let cancelled = false
    const baseRetryMs = 1000
    const maxRetryMs = 8000
    nextSinceRef.current = 0
    setLines([])
    setSummary({ success: 0, registered: 0, total: 0 })
    setError('')
    setTerminalStatus('idle')
    setStopRequested(false)

    const sleep = async (ms: number) =>
      new Promise((resolve) => setTimeout(resolve, ms))

    const initSnapshot = async (): Promise<boolean> => {
      try {
        const snapshot = await apiFetch(`/tasks/${taskId}`) as {
          logs?: string[]
          status?: TaskTerminalStatus | string
          success?: number
          registered?: number
          total?: number
          control?: { stop_requested?: boolean }
        }
        if (cancelled) return true

        const snapshotLines = Array.isArray(snapshot.logs) ? snapshot.logs : []
        setLines(snapshotLines)
        setSummary((previous) =>
          mergeSummary(previous, {
            success: snapshot.success,
            registered: snapshot.registered,
            total: snapshot.total,
          }),
        )
        nextSinceRef.current = snapshotLines.length
        setStopRequested(Boolean(snapshot.control?.stop_requested))

        if (snapshot.status === 'done' || snapshot.status === 'failed' || snapshot.status === 'stopped') {
          setTerminalStatus(snapshot.status)
          onDoneRef.current?.()
          return true
        }
      } catch (error_: unknown) {
        if (!cancelled) {
          const detail = error_ instanceof Error ? error_.message : t('获取任务快照失败', 'Failed to fetch task snapshot')
          setError(detail)
        }
      }
      return false
    }

    const connectStreamOnce = async (): Promise<boolean> => {
      try {
        const token = getToken()
        const headers: Record<string, string> = {}
        if (token) headers.Authorization = `Bearer ${token}`

        const since = nextSinceRef.current
        const response = await fetch(`${API_BASE}/tasks/${taskId}/logs/stream?since=${since}`, {
          headers,
          signal: controller.signal,
        })

        if (!response.ok) {
          setError(t(`日志流连接失败 (${response.status})`, `Log stream connection failed (${response.status})`))
          return true
        }

        if (!response.body) {
          setError(t('日志流未返回可读数据', 'Log stream did not return readable data'))
          return false
        }

        setError('')
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (!cancelled) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const parts = buffer.split('\n\n')
          buffer = parts.pop() || ''

          for (const part of parts) {
            const match = part.match(/^data:\s*(.+)$/m)
            if (!match) continue
            try {
              const payload = JSON.parse(match[1]) as {
                line?: string
                done?: boolean
                status?: TaskTerminalStatus
                success?: number
                registered?: number
                total?: number
              }
              setSummary((previous) =>
                mergeSummary(previous, {
                  success: payload.success,
                  registered: payload.registered,
                  total: payload.total,
                }),
              )
              if (payload.line) {
                nextSinceRef.current += 1
                setLines((previous) => [...previous, payload.line!])
              }
              if (payload.done) {
                setTerminalStatus(payload.status || 'done')
                onDoneRef.current?.()
                return true
              }
            } catch {
              // ignore malformed SSE payload
            }
          }
        }

        return false
      } catch (error_: unknown) {
        if (!cancelled && !(error_ instanceof DOMException && error_.name === 'AbortError')) {
          return false
        }
        return true
      }
    }

    const connectStream = async () => {
      const shouldStopImmediately = await initSnapshot()
      if (shouldStopImmediately || cancelled) return

      let retryCount = 0
      while (!cancelled) {
        const shouldStop = await connectStreamOnce()
        if (shouldStop || cancelled) return

        retryCount += 1
        const retryMs = Math.min(baseRetryMs * (2 ** (retryCount - 1)), maxRetryMs)
        setError(t(`日志流连接中断，${retryMs / 1000}s 后重试（第 ${retryCount} 次）`, `Log stream interrupted, retrying in ${retryMs / 1000}s (attempt ${retryCount})`))
        await sleep(retryMs)
      }
    }

    void connectStream()

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [taskId])

  useEffect(() => {
    if (!panelRef.current) return
    panelRef.current.scrollTop = panelRef.current.scrollHeight
  }, [lines])

  const footerText =
    terminalStatus === 'done'
      ? { text: t('注册完成', 'Registration complete'), color: '#10b981' }
      : terminalStatus === 'stopped'
        ? { text: t('任务已停止', 'Task stopped'), color: '#d97706' }
        : terminalStatus === 'failed'
          ? { text: t('任务失败', 'Task failed'), color: '#dc2626' }
          : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Space wrap style={{ marginBottom: 8 }}>
        <Tag color="green">{t('注册成功', 'Success')}: {summary.success}</Tag>
        <Tag color="blue">{t('已注册', 'Registered')}: {summary.registered}</Tag>
        <Tag color="default">{t('总共注册', 'Total')}: {summary.total}</Tag>
      </Space>

      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <Space>
          <Button
            size="small"
            icon={<FastForwardOutlined />}
            onClick={handleSkipCurrent}
            loading={skipLoading}
            disabled={isFinished}
          >
            {t('跳过当前账号', 'Skip current account')}
          </Button>
          <Button
            size="small"
            danger
            icon={<StopOutlined />}
            onClick={handleStopTask}
            loading={stopLoading}
            disabled={isFinished}
          >
            {t('停止任务', 'Stop task')}
          </Button>
        </Space>
        <Button size="small" icon={<CopyOutlined />} onClick={handleCopyAll} disabled={lines.length === 0}>
          {t('复制日志', 'Copy logs')}
        </Button>
      </div>

      <div
        ref={panelRef}
        className="log-panel"
        style={{
          flex: 1,
          overflowY: 'auto',
          overflowX: 'hidden',
          background: '#ffffff',
          border: '1px solid #e5e7eb',
          borderRadius: 8,
          padding: 12,
          fontFamily: 'monospace',
          fontSize: 12,
          minHeight: 320,
          maxHeight: '65vh',
          userSelect: 'text',
          WebkitUserSelect: 'text',
          cursor: 'text',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
      >
        {lines.length === 0 && !error && <div style={{ color: '#9ca3af' }}>{t('等待日志...', 'Waiting for logs...')}</div>}
        {error && <div style={{ color: '#dc2626' }}>{error}</div>}
        {lines.map((line, index) => (
          <div
            key={index}
            style={{
              lineHeight: 1.5,
              color:
                line.includes('✓') || line.includes('成功')
                  ? '#059669'
                  : line.includes('✗') || line.includes('失败') || line.includes('错误')
                    ? '#dc2626'
                    : line.includes('停止') || line.includes('跳过')
                      ? '#d97706'
                      : '#1f2937',
            }}
          >
            {translateTaskLogLine(line, language === 'en')}
          </div>
        ))}
      </div>

      {footerText ? (
        <div style={{ fontSize: 12, color: footerText.color, marginTop: 8 }}>
          {footerText.text}
        </div>
      ) : null}
    </div>
  )
}

export default TaskLogPanel
