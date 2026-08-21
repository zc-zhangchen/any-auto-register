import { apiFetch } from '@/lib/utils'

export type ICloudRegion = 'global' | 'china'

export interface ICloudCredentialState {
  has_session_cookies?: boolean
  has_dsid?: boolean
  has_hme_service_url?: boolean
  has_mail_gateway?: boolean
  has_web_auth_token?: boolean
  has_imap_credentials?: boolean
  credentials_unreadable?: boolean
}

export interface ICloudQuota {
  limit: number
  used: number
  remaining: number
  reset_at: string | null
}

export interface ICloudAccount {
  id: number
  email: string
  display_name: string
  region: ICloudRegion
  status: string
  enabled: boolean
  alias_count: number
  sync_error: string
  last_sync_at: string | null
  created_at: string | null
  credential_state: ICloudCredentialState
  quota: ICloudQuota
}

export interface ICloudAlias {
  id: number
  account_id: number
  account_email: string
  address: string
  label: string
  note: string
  status: string
  provider_id: string
  created_at: string | null
}

export interface ICloudTrustedPhone {
  id: number
  number: string
  push_mode: string
}

/** 验证码投递方式：受信任设备推送、短信，或需要先选择手机号。 */
export type ICloudLoginDelivery = 'trusted_devices' | 'sms' | 'sms_selection_required' | ''

export interface ICloudLoginState {
  login_id: string
  status: 'verification_required' | 'completed'
  expires_at: number
  delivery: ICloudLoginDelivery
  trusted_phone_numbers: ICloudTrustedPhone[]
  email: string
  display_name: string
  region: ICloudRegion
  account?: ICloudAccount
}

export interface ICloudMailAddress {
  email: string
  name: string
}

export interface ICloudMessage {
  id: string
  mailbox: string
  subject: string
  snippet: string
  text_body: string
  html_body: string
  from: ICloudMailAddress
  to: ICloudMailAddress[]
  received_at: string
  alias_address: string
  is_read: boolean
  has_attachments: boolean
}

export interface ICloudLoginPayload {
  email: string
  password: string
  display_name?: string
  region?: ICloudRegion
  imap_host?: string
  imap_port?: number
  imap_username?: string
  imap_password?: string
}

export interface ICloudCookieImportPayload {
  email?: string
  display_name?: string
  region?: ICloudRegion
  cookie_header?: string
  cookies_json?: unknown
  imap_host?: string
  imap_port?: number
  imap_username?: string
  imap_password?: string
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return apiFetch(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

export async function listICloudAccounts(): Promise<ICloudAccount[]> {
  const data = await apiFetch('/icloud/accounts')
  return data?.items ?? []
}

export function startICloudLogin(payload: ICloudLoginPayload): Promise<ICloudLoginState> {
  return post('/icloud/login-sessions', payload)
}

export function verifyICloudLogin(loginId: string, code: string): Promise<ICloudLoginState> {
  return post(`/icloud/login-sessions/${loginId}/verify`, { code })
}

export function resendICloudLoginCode(loginId: string): Promise<ICloudLoginState> {
  return post(`/icloud/login-sessions/${loginId}/resend`)
}

export function sendICloudLoginSMS(
  loginId: string,
  phoneId: number,
  mode = '',
): Promise<ICloudLoginState> {
  return post(`/icloud/login-sessions/${loginId}/sms`, { phone_id: phoneId, mode })
}

export function cancelICloudLogin(loginId: string): Promise<{ ok: boolean }> {
  return apiFetch(`/icloud/login-sessions/${loginId}`, { method: 'DELETE' })
}

export function importICloudCookie(payload: ICloudCookieImportPayload): Promise<ICloudAccount> {
  return post('/icloud/accounts/import-cookie', payload)
}

export function setICloudAccountEnabled(id: number, enabled: boolean): Promise<ICloudAccount> {
  return apiFetch(`/icloud/accounts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled }),
  })
}

export function deleteICloudAccount(id: number): Promise<{ ok: boolean }> {
  return apiFetch(`/icloud/accounts/${id}`, { method: 'DELETE' })
}

export function syncICloudAccount(id: number): Promise<{
  fetched: number
  created: number
  updated: number
}> {
  return post(`/icloud/accounts/${id}/sync`)
}

export async function listICloudAliases(accountId?: number): Promise<ICloudAlias[]> {
  const query = accountId ? `?account_id=${accountId}` : ''
  const data = await apiFetch(`/icloud/aliases${query}`)
  return data?.items ?? []
}

export async function generateICloudAliases(payload: {
  account_id: number
  label?: string
  note?: string
  count?: number
}): Promise<ICloudAlias[]> {
  const data = await post<{ items: ICloudAlias[] }>('/icloud/aliases', payload)
  return data?.items ?? []
}

export function deleteICloudAlias(id: number, remote = true): Promise<{ ok: boolean }> {
  return apiFetch(`/icloud/aliases/${id}?remote=${remote}`, { method: 'DELETE' })
}

/**
 * limit 是主号收件箱的倒序扫描窗口，不是"返回几封"——主号收件箱里混着所有
 * 隐私邮箱的信，窗口开太窄会把这个地址的最新一封漏在窗口外，所以取服务端默认的 50。
 */
export async function listICloudAliasMessages(
  aliasId: number,
  limit = 50,
): Promise<ICloudMessage[]> {
  const data = await apiFetch(`/icloud/aliases/${aliasId}/messages?limit=${limit}`)
  return data?.items ?? []
}
