import { theme } from 'antd'

export type ThemeMode = 'dark' | 'light'

/**
 * 界面用色统一在这里定义：antd token 与 CSS 变量共用同一份，
 * 页面里的内联样式一律写 var(--x)，切主题时不用改组件。
 */
interface Palette {
  bgLayout: string
  bgContainer: string
  bgElevated: string
  bgSubtle: string
  border: string
  borderStrong: string
  text: string
  textSecondary: string
  textMuted: string
  accent: string
  accentHover: string
  accentSoft: string
  success: string
  successSoft: string
  warning: string
  warningSoft: string
  danger: string
  dangerSoft: string
  logBg: string
  logBorder: string
  logText: string
  logMuted: string
  logSuccess: string
  logWarning: string
  logDanger: string
  selectionBg: string
  spotlightBg: string
}

const darkPalette: Palette = {
  bgLayout: '#161922',
  bgContainer: '#1e212c',
  bgElevated: '#262a36',
  bgSubtle: 'rgba(255,255,255,0.045)',
  border: 'rgba(255,255,255,0.09)',
  borderStrong: 'rgba(255,255,255,0.14)',
  text: '#d7dce5',
  textSecondary: '#a4adbd',
  textMuted: '#7b8595',
  accent: '#5f82b8',
  accentHover: '#7396c8',
  accentSoft: 'rgba(95,130,184,0.16)',
  success: '#6cbf9a',
  successSoft: 'rgba(108,191,154,0.14)',
  warning: '#d3a26b',
  warningSoft: 'rgba(211,162,107,0.14)',
  danger: '#cf8181',
  dangerSoft: 'rgba(207,129,129,0.14)',
  logBg: '#191c24',
  logBorder: 'rgba(255,255,255,0.07)',
  logText: '#c3cad6',
  logMuted: '#79828f',
  logSuccess: '#7fc2a1',
  logWarning: '#d7a86e',
  logDanger: '#d48c8c',
  selectionBg: 'rgba(95,130,184,0.38)',
  spotlightBg: '#2b3040',
}

const lightPalette: Palette = {
  bgLayout: '#f5f6f8',
  bgContainer: '#ffffff',
  bgElevated: '#ffffff',
  bgSubtle: 'rgba(15,23,42,0.035)',
  border: 'rgba(15,23,42,0.09)',
  borderStrong: 'rgba(15,23,42,0.14)',
  text: '#2c3440',
  textSecondary: '#5b6675',
  textMuted: '#8a94a3',
  accent: '#4a6fa5',
  accentHover: '#5b81b8',
  accentSoft: 'rgba(74,111,165,0.12)',
  success: '#3f9b76',
  successSoft: 'rgba(63,155,118,0.12)',
  warning: '#b0803a',
  warningSoft: 'rgba(176,128,58,0.12)',
  danger: '#c06a6a',
  dangerSoft: 'rgba(192,106,106,0.12)',
  logBg: '#fbfcfd',
  logBorder: 'rgba(15,23,42,0.08)',
  logText: '#3a4351',
  logMuted: '#8a94a3',
  logSuccess: '#3f8f6d',
  logWarning: '#a97b34',
  logDanger: '#b46060',
  selectionBg: 'rgba(74,111,165,0.22)',
  spotlightBg: '#3a4353',
}

function buildTheme(palette: Palette, algorithm: typeof theme.darkAlgorithm) {
  return {
    token: {
      colorPrimary: palette.accent,
      colorInfo: palette.accent,
      colorSuccess: palette.success,
      colorWarning: palette.warning,
      colorError: palette.danger,
      colorBgBase: palette.bgContainer,
      colorTextBase: palette.text,
      colorBgContainer: palette.bgContainer,
      colorBgElevated: palette.bgElevated,
      colorBgLayout: palette.bgLayout,
      colorBorder: palette.borderStrong,
      colorBorderSecondary: palette.border,
      borderRadius: 10,
      colorText: palette.text,
      colorTextSecondary: palette.textSecondary,
      colorTextTertiary: palette.textMuted,
      colorBgSpotlight: palette.spotlightBg,
      controlOutline: palette.accentSoft,
    },
    components: {
      Layout: {
        siderBg: palette.bgContainer,
        triggerBg: palette.bgElevated,
        triggerColor: palette.textSecondary,
      },
      Menu: {
        itemColor: palette.textSecondary,
        itemHoverBg: palette.bgSubtle,
        itemHoverColor: palette.text,
        itemSelectedBg: palette.accentSoft,
        itemSelectedColor: palette.text,
        subMenuItemBg: 'transparent',
      },
      Card: {
        headerBg: 'transparent',
        colorBorderSecondary: palette.border,
      },
      Table: {
        headerBg: palette.bgSubtle,
        headerColor: palette.textSecondary,
        headerSplitColor: 'transparent',
        rowHoverBg: palette.bgSubtle,
        borderColor: palette.border,
      },
      Modal: {
        contentBg: palette.bgElevated,
        headerBg: palette.bgElevated,
        titleColor: palette.text,
      },
      Tag: {
        defaultBg: palette.bgSubtle,
        defaultColor: palette.textSecondary,
      },
      Button: {
        primaryShadow: 'none',
        defaultShadow: 'none',
        dangerShadow: 'none',
      },
      Segmented: {
        itemSelectedBg: palette.accentSoft,
        itemSelectedColor: palette.text,
      },
    },
    algorithm,
  }
}

const darkTheme = buildTheme(darkPalette, theme.darkAlgorithm)
const lightTheme = buildTheme(lightPalette, theme.defaultAlgorithm)

const CSS_VAR_NAMES: Record<keyof Palette, string> = {
  bgLayout: '--bg-layout',
  bgContainer: '--bg-container',
  bgElevated: '--bg-elevated',
  bgSubtle: '--bg-subtle',
  border: '--border',
  borderStrong: '--border-strong',
  text: '--text',
  textSecondary: '--text-secondary',
  textMuted: '--text-muted',
  accent: '--accent',
  accentHover: '--accent-hover',
  accentSoft: '--accent-soft',
  success: '--success',
  successSoft: '--success-soft',
  warning: '--warning',
  warningSoft: '--warning-soft',
  danger: '--danger',
  dangerSoft: '--danger-soft',
  logBg: '--log-bg',
  logBorder: '--log-border',
  logText: '--log-text',
  logMuted: '--log-muted',
  logSuccess: '--log-success',
  logWarning: '--log-warning',
  logDanger: '--log-danger',
  selectionBg: '--selection-bg',
  spotlightBg: '--spotlight-bg',
}

/** 把当前主题写成 CSS 变量，登录页等没有 ConfigProvider 的地方也能取到同一套色。 */
export function applyThemeVars(mode: ThemeMode) {
  const palette = mode === 'light' ? lightPalette : darkPalette
  const root = document.documentElement
  for (const [key, name] of Object.entries(CSS_VAR_NAMES)) {
    root.style.setProperty(name, palette[key as keyof Palette])
  }
  root.style.setProperty('--sider-trigger-border', palette.border)
  root.classList.toggle('light', mode === 'light')
  root.style.colorScheme = mode
}

export { darkTheme, lightTheme, darkPalette, lightPalette }
