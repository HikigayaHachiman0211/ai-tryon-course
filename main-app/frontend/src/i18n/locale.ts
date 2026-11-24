export const SUPPORTED_LOCALES = ['zh-CN', 'en', 'ja'] as const
export type AppLocale = (typeof SUPPORTED_LOCALES)[number]
export const DEFAULT_LOCALE: AppLocale = 'zh-CN'
export const LOCALE_STORAGE_KEY = 'ai-tryon.locale'

export const LOCALE_LABELS: Record<AppLocale, string> = {
  'zh-CN': '简体中文',
  en: 'English',
  ja: '日本語',
}

export function normalizeLocale(input?: string | null): AppLocale | null {
  if (!input) return null
  const value = input.trim().replace(/_/g, '-').toLowerCase()
  if (value === 'zh' || value === 'zh-cn' || value === 'zh-hans') return 'zh-CN'
  if (value === 'en' || value.startsWith('en-')) return 'en'
  if (value === 'ja' || value.startsWith('ja-')) return 'ja'
  return null
}

export function resolveLocaleFromAcceptLanguage(header?: string | null): AppLocale | null {
  if (!header) return null

  const candidates = header
    .split(',')
    .map((part, index) => {
      const [rangePart, ...parameters] = part.trim().split(';')
      const qParameter = parameters.find((parameter) => parameter.trim().toLowerCase().startsWith('q='))
      const parsedQuality = qParameter ? Number.parseFloat(qParameter.trim().slice(2)) : 1
      return {
        range: rangePart.trim(),
        quality: Number.isFinite(parsedQuality) ? Math.max(0, Math.min(1, parsedQuality)) : 0,
        index,
      }
    })
    .filter((candidate) => candidate.quality > 0 && candidate.range !== '*')
    .sort((left, right) => right.quality - left.quality || left.index - right.index)

  for (const candidate of candidates) {
    const normalized = normalizeLocale(candidate.range)
    if (normalized) return normalized
  }
  return null
}

export function detectInitialLocale(): AppLocale {
  if (typeof window === 'undefined') return DEFAULT_LOCALE

  const query = normalizeLocale(new URL(window.location.href).searchParams.get('lang'))
  if (query) return query

  try {
    const stored = normalizeLocale(window.localStorage.getItem(LOCALE_STORAGE_KEY))
    if (stored) return stored
  } catch {
    // Storage can be unavailable in privacy mode; continue with browser detection.
  }

  const candidates = window.navigator.languages?.length
    ? window.navigator.languages
    : [window.navigator.language]
  for (const candidate of candidates) {
    const detected = normalizeLocale(candidate)
    if (detected) return detected
  }
  return DEFAULT_LOCALE
}

export function persistLocale(locale: AppLocale): void {
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale)
  } catch {
    // A read-only storage implementation must not prevent switching languages.
  }
}
