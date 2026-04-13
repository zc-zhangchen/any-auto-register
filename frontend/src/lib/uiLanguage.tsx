import { createContext, useContext, type ReactNode } from 'react'

export type UiLanguage = 'zh' | 'en'

type UiLanguageContextValue = {
  language: UiLanguage
  setLanguage: (language: UiLanguage) => void
}

const UiLanguageContext = createContext<UiLanguageContextValue | null>(null)

export function UiLanguageProvider({
  value,
  children,
}: {
  value: UiLanguageContextValue
  children: ReactNode
}) {
  return <UiLanguageContext.Provider value={value}>{children}</UiLanguageContext.Provider>
}

export function useUiLanguage() {
  const context = useContext(UiLanguageContext)
  if (!context) {
    throw new Error('useUiLanguage must be used within UiLanguageProvider')
  }
  return context
}

const TRANSLATIONS: Record<UiLanguage, Record<string, string>> = {
  zh: {},
  en: {
    Dashboard: 'Dashboard',
    'Running Tasks': 'Running Tasks',
    'Platform Management': 'Platform Management',
    'Task History': 'Task History',
    'Proxy Management': 'Proxy Management',
    'Global Settings': 'Global Settings',
    'Light Mode': 'Light Mode',
    'Dark Mode': 'Dark Mode',
    'Log out': 'Log out',
    'Language': 'Language',
  },
}

export function useText() {
  const { language } = useUiLanguage()
  return (zhText: string, enText?: string) => {
    if (language === 'en') {
      return enText || TRANSLATIONS.en[zhText] || zhText
    }
    return zhText
  }
}
