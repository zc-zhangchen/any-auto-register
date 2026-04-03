import { useState } from 'react'
import { App, Card, ConfigProvider, Form, Input, Button, Typography } from 'antd'
import { LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons'
import { setToken } from '@/lib/utils'
import { darkTheme } from '@/theme'

type Step = 'password' | '2fa'

function LoginContent() {
  const { message } = App.useApp()
  const [step, setStep] = useState<Step>('password')
  const [tempToken, setTempToken] = useState('')
  const [loading, setLoading] = useState(false)

  const handleLogin = async (values: { password: string }) => {
    setLoading(true)
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: values.password }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || '登录失败')
      if (data.requires_2fa) {
        setTempToken(data.temp_token)
        setStep('2fa')
      } else {
        setToken(data.access_token)
        window.location.href = '/'
      }
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleTotp = async (values: { code: string }) => {
    setLoading(true)
    try {
      const res = await fetch('/api/auth/verify-totp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ temp_token: tempToken, code: values.code }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || '验证失败')
      setToken(data.access_token)
      window.location.href = '/'
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  const cardStyle: React.CSSProperties = {
    width: 380,
    boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
    borderRadius: 12,
  }

  const wrapStyle: React.CSSProperties = {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)',
  }

  if (step === '2fa') {
    return (
      <div style={wrapStyle}>
        <Card
          style={cardStyle}
          title={
            <div style={{ textAlign: 'center', padding: '8px 0' }}>
              <SafetyCertificateOutlined style={{ fontSize: 28, color: '#6366f1', marginBottom: 8, display: 'block' }} />
              <div style={{ fontSize: 18, fontWeight: 700 }}>双因素验证</div>
              <Typography.Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>
                请输入验证器 App 中的 6 位验证码
              </Typography.Text>
            </div>
          }
        >
          <Form layout="vertical" onFinish={handleTotp} requiredMark={false}>
            <Form.Item
              name="code"
              label="验证码"
              rules={[
                { required: true, message: '请输入验证码' },
                { len: 6, message: '验证码为 6 位数字' },
              ]}
            >
              <Input
                prefix={<SafetyCertificateOutlined />}
                placeholder="000000"
                size="large"
                maxLength={6}
                style={{ letterSpacing: 6, textAlign: 'center' }}
              />
            </Form.Item>
            <Form.Item style={{ marginBottom: 0, marginTop: 8 }}>
              <Button type="primary" htmlType="submit" block size="large" loading={loading}>
                验证并登录
              </Button>
            </Form.Item>
            <div style={{ textAlign: 'center', marginTop: 12 }}>
              <Button type="link" size="small" onClick={() => setStep('password')}>
                返回密码登录
              </Button>
            </div>
          </Form>
        </Card>
      </div>
    )
  }

  return (
    <div style={wrapStyle}>
      <Card
        style={cardStyle}
        title={
          <div style={{ textAlign: 'center', padding: '8px 0', background: 'transparent' }}>
            <UserOutlined style={{ fontSize: 28, color: '#6366f1', marginBottom: 8, display: 'block' }} />
            <div style={{ fontSize: 18, fontWeight: 700 }}>Account Manager</div>
            <Typography.Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>
              请输入密码登录
            </Typography.Text>
          </div>
        }
      >
        <Form layout="vertical" onFinish={handleLogin} requiredMark={false}>
          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="请输入访问密码" size="large" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0, marginTop: 8 }}>
            <Button type="primary" htmlType="submit" block size="large" loading={loading}>
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}

export default function Login() {
  return (
    <ConfigProvider theme={darkTheme}>
      <App>
        <LoginContent />
      </App>
    </ConfigProvider>
  )
}
