import i18n from 'i18next'

export const SUPPORTED_LOCALES = ['zh-CN', 'en', 'ja'] as const
export type AppLocale = (typeof SUPPORTED_LOCALES)[number]
export const DEFAULT_LOCALE: AppLocale = 'zh-CN'
export const LOCALE_STORAGE_KEY = 'ai-tryon.admin.locale'

export function normalizeLocale(input?: string | null): AppLocale | null {
  if (!input) return null
  const value = input.trim().toLowerCase().replace('_', '-')
  if (value === 'zh' || value === 'zh-cn' || value === 'zh-hans' || value.startsWith('zh-hans-')) return 'zh-CN'
  if (value === 'en' || value.startsWith('en-')) return 'en'
  if (value === 'ja' || value.startsWith('ja-')) return 'ja'
  return null
}

function readStorage(): string | null {
  try { return localStorage.getItem(LOCALE_STORAGE_KEY) } catch { return null }
}

function parseQualityLanguage(header: string | null | undefined): AppLocale | null {
  if (!header) return null
  const choices = header.split(',').map((part, index) => {
    const [raw, ...params] = part.trim().split(';')
    const q = params.find((param) => param.trim().toLowerCase().startsWith('q='))?.split('=')[1]
    const quality = q ? Number.parseFloat(q) : 1
    return { locale: normalizeLocale(raw), quality: Number.isFinite(quality) ? quality : 0, index }
  }).filter((item): item is { locale: AppLocale; quality: number; index: number } => Boolean(item.locale) && item.quality > 0)
  choices.sort((a, b) => b.quality - a.quality || a.index - b.index)
  return choices[0]?.locale ?? null
}

export function detectInitialLocale(): AppLocale {
  const query = new URLSearchParams(window.location.search).get('lang')
  return normalizeLocale(query) ?? normalizeLocale(readStorage()) ?? parseQualityLanguage(navigator.languages?.join(',') || navigator.language) ?? DEFAULT_LOCALE
}

export function persistLocale(locale: AppLocale): void {
  try { localStorage.setItem(LOCALE_STORAGE_KEY, locale) } catch { /* privacy mode */ }
}

export function withLocaleQuery(rawUrl: string, locale: AppLocale): string {
  try {
    const url = new URL(rawUrl, window.location.origin)
    url.searchParams.set('lang', locale)
    return `${url.pathname}${url.search}${url.hash}`
  } catch {
    return rawUrl
  }
}

export async function setAdminLocale(locale: AppLocale): Promise<void> {
  persistLocale(locale)
  if (i18n.isInitialized) await i18n.changeLanguage(locale)
  document.documentElement.lang = locale
  const url = new URL(window.location.href)
  url.searchParams.set('lang', locale)
  window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
  window.dispatchEvent(new CustomEvent('admin-localechange', { detail: locale }))
}
