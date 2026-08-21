export type PlatformName = 'chatgpt' | 'icloud'

export type ExecutorType = 'protocol' | 'headless' | 'headed'

export interface PlatformMeta {
  name: PlatformName
  label: string
  color: string
  executors: ExecutorType[]
  /** 该平台的“注册”是否消耗外部邮箱池。iCloud 自带隐私邮箱，无需临时邮箱。 */
  usesMailbox: boolean
  /** 注册流程是否会遇到人机验证。iCloud 走 Apple 私有协议，不需要打码服务。 */
  usesCaptcha: boolean
}

export const EXECUTOR_LABELS: Record<ExecutorType, string> = {
  protocol: '纯协议',
  headless: '无头浏览器',
  headed: '有头浏览器',
}

export const PLATFORMS: Record<PlatformName, PlatformMeta> = {
  chatgpt: {
    name: 'chatgpt',
    label: 'ChatGPT',
    color: '#6d90c7',
    executors: ['protocol', 'headless', 'headed'],
    usesMailbox: true,
    usesCaptcha: true,
  },
  icloud: {
    name: 'icloud',
    label: 'iCloud 隐私邮箱',
    color: '#5b8db3',
    executors: ['protocol'],
    usesMailbox: false,
    usesCaptcha: false,
  },
}

export const PLATFORM_OPTIONS = Object.values(PLATFORMS).map(({ name, label }) => ({
  value: name,
  label,
}))

export const PLATFORM_FILTER_OPTIONS = [{ value: '', label: '全部平台' }, ...PLATFORM_OPTIONS]

export function getPlatformMeta(platform?: string): PlatformMeta | undefined {
  return PLATFORMS[(platform || '') as PlatformName]
}

export function getPlatformLabel(platform?: string): string {
  return getPlatformMeta(platform)?.label ?? (platform || '-')
}

export function getPlatformColor(platform?: string): string {
  return getPlatformMeta(platform)?.color ?? '#7b8595'
}

export function getSupportedExecutors(platform?: string): ExecutorType[] {
  return getPlatformMeta(platform)?.executors ?? ['protocol']
}

export function getExecutorOptions(platform?: string) {
  return getSupportedExecutors(platform).map((value) => ({ value, label: EXECUTOR_LABELS[value] }))
}

export function normalizeExecutorForPlatform(platform?: string, executor?: string): ExecutorType {
  const supported = getSupportedExecutors(platform)
  return supported.includes(executor as ExecutorType) ? (executor as ExecutorType) : supported[0]
}
