import i18n from 'i18next'
import HttpBackend from 'i18next-http-backend'
import { initReactI18next } from 'react-i18next'
import {
  DEFAULT_LOCALE,
  detectInitialLocale,
  normalizeLocale,
  persistLocale,
  SUPPORTED_LOCALES,
  type AppLocale,
} from './locale'

export interface DocumentMetadata {
  title: string
  description: string
}

export const applyDocumentMetadata = (locale: AppLocale, metadata: DocumentMetadata): void => {
  if (typeof document === 'undefined') return
  document.documentElement.lang = locale
  document.documentElement.dir = 'ltr'
  document.title = metadata.title
  let description = document.querySelector<HTMLMetaElement>('meta[name="description"]')
  if (!description) {
    description = document.createElement('meta')
    description.name = 'description'
    document.head.appendChild(description)
  }
  description.content = metadata.description
}

const updateUrlLocale = (locale: AppLocale): void => {
  if (typeof window === 'undefined') return
  const url = new URL(window.location.href)
  url.searchParams.set('lang', locale)
  window.history.replaceState(window.history.state, document.title, `${url.pathname}${url.search}${url.hash}`)
}

const metadataFor = (locale: AppLocale): DocumentMetadata => ({
  title: i18n.t('meta.title', { lng: locale }),
  description: i18n.t('meta.description', { lng: locale }),
})

export const i18nReady = i18n
  .use(HttpBackend)
  .use(initReactI18next)
  .init({
    lng: detectInitialLocale(),
    supportedLngs: [...SUPPORTED_LOCALES],
    load: 'currentOnly',
    fallbackLng: DEFAULT_LOCALE,
    defaultNS: 'common',
    ns: ['common'],
    backend: {
      loadPath: '/locales/{{lng}}/{{ns}}.json',
      requestOptions: { cache: 'no-store' },
    },
    interpolation: { escapeValue: false },
    returnEmptyString: false,
    saveMissing: false,
    missingKeyHandler: (_languages, namespace, key) => {
      if (import.meta.env.MODE === 'test') throw new Error(`Missing translation key: ${namespace}:${key}`)
    },
    react: { useSuspense: true },
  })
  .then(() => {
    const locale = normalizeLocale(i18n.resolvedLanguage) ?? DEFAULT_LOCALE
    applyDocumentMetadata(locale, metadataFor(locale))
  })

export const setAppLocale = async (input: string): Promise<AppLocale> => {
  const nextLocale = normalizeLocale(input)
  if (!nextLocale) throw new Error('Unsupported locale')

  const previousLocale = normalizeLocale(i18n.resolvedLanguage) ?? DEFAULT_LOCALE
  if (nextLocale !== previousLocale) {
    await i18n.loadLanguages(nextLocale)
    await i18n.changeLanguage(nextLocale)
  }

  persistLocale(nextLocale)
  applyDocumentMetadata(nextLocale, metadataFor(nextLocale))
  updateUrlLocale(nextLocale)
  window.dispatchEvent(new CustomEvent('localechange', { detail: nextLocale }))
  return nextLocale
}

export default i18n
