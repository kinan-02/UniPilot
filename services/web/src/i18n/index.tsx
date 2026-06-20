import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { he } from './locales/he'
import { en } from './locales/en'
import type { Locale, TranslationTree } from './types'

const STORAGE_KEY = 'unipilot_locale'

const translations: Record<Locale, TranslationTree> = { he, en }

function getNestedValue(tree: TranslationTree, key: string): string {
  const parts = key.split('.')
  let current: unknown = tree
  for (const part of parts) {
    if (current && typeof current === 'object' && part in current) {
      current = (current as Record<string, unknown>)[part]
    } else {
      return key
    }
  }
  return typeof current === 'string' ? current : key
}

type I18nContextValue = {
  locale: Locale
  dir: 'rtl' | 'ltr'
  setLocale: (locale: Locale) => void
  t: (key: string) => string
}

const I18nContext = createContext<I18nContextValue | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored === 'en' ? 'en' : 'he'
  })

  const setLocale = useCallback((next: Locale) => {
    localStorage.setItem(STORAGE_KEY, next)
    setLocaleState(next)
  }, [])

  const dir: 'rtl' | 'ltr' = locale === 'he' ? 'rtl' : 'ltr'

  useEffect(() => {
    document.documentElement.lang = locale
    document.documentElement.dir = dir
  }, [locale, dir])

  const t = useCallback((key: string) => getNestedValue(translations[locale], key), [locale])

  const value = useMemo(() => ({ locale, dir, setLocale, t }), [locale, dir, setLocale, t])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useTranslation() {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useTranslation must be used within I18nProvider')
  return ctx
}
