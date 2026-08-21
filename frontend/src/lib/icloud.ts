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
 * 导出格式沿用仓库里邮箱池导入那套 `----` 分隔：
 *   self    → 隐私邮箱----隐私邮箱（默认，粘到只认「邮箱----邮箱地址」的地方）
 *   account → 隐私邮箱----所属主号（想知道每个别名挂在哪个 Apple ID 下时用）
 */
export type AliasExportMode = 'self' | 'account'

export const ALIAS_EXPORT_FILENAME = 'icloud_aliases.txt'

export function formatAliasExport(
  aliases: { address: string; account_email: string }[],
  mode: AliasExportMode = 'self',
): string {
  return aliases
    .map((alias) => `${alias.address}----${mode === 'account' ? alias.account_email : alias.address}`)
    .join('\n')
}

export function downloadTextFile(filename: string, content: string): void {
  const url = URL.createObjectURL(new Blob([content], { type: 'text/plain;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
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
