import { useState } from 'react'
import { App, Card, ConfigProvider, Form, Input, Button, Typography } from 'antd'
import { LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons'
import { setToken } from '@/lib/utils'
import { darkTheme } from '@/theme'
import { useText } from '@/lib/uiLanguage'

type Step = 'password' | '2fa'

function LoginContent() {
  const { message } = App.useApp()
  const t = useText()
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
      if (!res.ok) throw new Error(data.detail || t('登录失败', 'Login failed'))
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
      if (!res.ok) throw new Error(data.detail || t('验证失败', 'Verification failed'))
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
              <div style={{ fontSize: 18, fontWeight: 700 }}>{t('双因素验证', 'Two-factor verification')}</div>
              <Typography.Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>
                {t('请输入验证器 App 中的 6 位验证码', 'Enter the 6-digit code from your authenticator app')}
              </Typography.Text>
            </div>
          }
        >
          <Form layout="vertical" onFinish={handleTotp} requiredMark={false}>
            <Form.Item
              name="code"
              label={t('验证码', 'Code')}
              rules={[
                { required: true, message: t('请输入验证码', 'Enter the code') },
                { len: 6, message: t('验证码为 6 位数字', 'The code must be 6 digits') },
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
                {t('验证并登录', 'Verify and sign in')}
              </Button>
            </Form.Item>
            <div style={{ textAlign: 'center', marginTop: 12 }}>
              <Button type="link" size="small" onClick={() => setStep('password')}>
                {t('返回密码登录', 'Back to password login')}
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
              {t('请输入密码登录', 'Enter your password to sign in')}
            </Typography.Text>
          </div>
        }
      >
        <Form layout="vertical" onFinish={handleLogin} requiredMark={false}>
          <Form.Item
            name="password"
            label={t('密码', 'Password')}
            rules={[{ required: true, message: t('请输入密码', 'Enter your password') }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder={t('请输入访问密码', 'Enter access password')} size="large" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0, marginTop: 8 }}>
            <Button type="primary" htmlType="submit" block size="large" loading={loading}>
              {t('登录', 'Sign in')}
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
