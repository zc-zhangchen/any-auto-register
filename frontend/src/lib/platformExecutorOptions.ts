export const EXECUTOR_OPTIONS = [
  { value: 'protocol', label: 'Protocol only' },
  { value: 'headless', label: 'Headless browser' },
  { value: 'headed', label: 'Headed browser' },
] as const

const PLATFORM_EXECUTORS: Record<string, string[]> = {
  chatgpt: ['protocol', 'headless', 'headed'],
  cursor: ['protocol', 'headless', 'headed'],
  grok: ['protocol', 'headless', 'headed'],
  kiro: ['protocol', 'headless', 'headed'],
  tavily: ['protocol', 'headless', 'headed'],
  trae: ['protocol', 'headless', 'headed'],
  openblocklabs: ['protocol'],
}

export function getSupportedExecutors(platform?: string) {
  if (!platform) return ['protocol']
  return PLATFORM_EXECUTORS[platform] || ['protocol']
}

export function getExecutorOptions(platform?: string) {
  const supported = new Set(getSupportedExecutors(platform))
  return EXECUTOR_OPTIONS.filter((option) => supported.has(option.value))
}

export function normalizeExecutorForPlatform(platform: string | undefined, executor: string | undefined) {
  const supported = getSupportedExecutors(platform)
  if (executor && supported.includes(executor)) return executor
  return supported[0] || 'protocol'
}
