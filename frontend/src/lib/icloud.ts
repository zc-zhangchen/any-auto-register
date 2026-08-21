import type { ICloudRegion } from '@/api/icloud'

export const DEFAULT_ICLOUD_IMAP_HOST = 'imap.mail.me.com'
export const DEFAULT_ICLOUD_IMAP_PORT = 993

/** Apple 对每个主号限制每滚动小时最多成功生成 5 个隐私邮箱。 */
export const ICLOUD_HOURLY_ALIAS_LIMIT = 5

export const ICLOUD_REGION_OPTIONS: { value: ICloudRegion; label: string }[] = [
  { value: 'global', label: '国际版（icloud.com）' },
  { value: 'china', label: '中国大陆（icloud.com.cn）' },
]

export function getICloudRegionLabel(region?: string): string {
  return ICLOUD_REGION_OPTIONS.find((item) => item.value === region)?.label ?? region ?? '-'
}

/**
 * 隐私邮箱的固定收件链接：打开就是这个地址的最新一封邮件。
 * 拿去贴到别处也能用，不用先进 iCloud 页再翻列表。
 */
export function aliasMailPath(aliasId: number): string {
  return `/icloud/mail/${aliasId}`
}

export function aliasMailUrl(aliasId: number): string {
  return `${window.location.origin}${aliasMailPath(aliasId)}`
}

export function formatDateTime(value?: string | null): string {
  if (!value) return '-'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '-' : parsed.toLocaleString()
}

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

/** 邮件列表里用相对时间，扫起来比一串完整时间戳快得多。 */
export function formatRelativeTime(value?: string | null): string {
  if (!value) return '-'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '-'
  const diff = Date.now() - parsed.getTime()
  if (diff < 0) return parsed.toLocaleDateString()
  if (diff < MINUTE) return '刚刚'
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)} 分钟前`
  if (diff < DAY) return `${Math.floor(diff / HOUR)} 小时前`
  if (diff < 7 * DAY) return `${Math.floor(diff / DAY)} 天前`
  return parsed.toLocaleDateString()
}
