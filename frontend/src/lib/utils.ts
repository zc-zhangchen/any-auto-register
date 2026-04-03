export const API = '/api'
export const API_BASE = '/api'

export function getToken(): string {
  return localStorage.getItem('auth_token') || ''
}

export function setToken(token: string): void {
  localStorage.setItem('auth_token', token)
}

export function clearToken(): void {
  localStorage.removeItem('auth_token')
}

export async function apiFetch(path: string, opts?: RequestInit) {
  const token = getToken()
  const baseHeaders: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) baseHeaders['Authorization'] = `Bearer ${token}`
  const res = await fetch(API + path, {
    ...opts,
    headers: { ...baseHeaders, ...(opts?.headers as Record<string, string> || {}) },
  })
  if (res.status === 401) {
    clearToken()
    if (window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
    throw new Error('未认证，请重新登录')
  }
  if (!res.ok) {
    const text = await res.text()
    try {
      const json = JSON.parse(text)
      throw new Error(json.detail || text)
    } catch (e) {
      if (e instanceof SyntaxError) throw new Error(text)
      throw e
    }
  }
  return res.json()
}
