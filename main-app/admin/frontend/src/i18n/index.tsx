import i18n from 'i18next'
import HttpBackend from 'i18next-http-backend'
import { initReactI18next } from 'react-i18next'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import 'dayjs/locale/en'
import 'dayjs/locale/ja'
import { DEFAULT_LOCALE, detectInitialLocale, persistLocale, setAdminLocale, type AppLocale } from './locale'
import { dayjsLocales } from './antdLocale'

export const adminI18n = i18n.isInitialized ? i18n : i18n.use(HttpBackend).use(initReactI18next)

export const adminI18nReady = i18n.isInitialized ? Promise.resolve(adminI18n) : adminI18n.init({
    lng: detectInitialLocale(),
    supportedLngs: ['zh-CN', 'en', 'ja'],
    load: 'currentOnly',
    fallbackLng: DEFAULT_LOCALE,
    defaultNS: 'common',
    ns: ['common'],
    backend: { loadPath: '/locales/{{lng}}/{{ns}}.json', requestOptions: { cache: 'no-store' } },
    interpolation: { escapeValue: false },
    saveMissing: false,
    returnNull: false,
    missingKeyHandler: (_languages, namespace, key) => {
      if (import.meta.env.MODE === 'test') throw new Error(`Missing translation key: ${namespace}:${key}`)
    },
  })

function updateMetadata(locale: AppLocale): void {
  document.documentElement.lang = locale
  document.title = i18n.t('meta.title', { lng: locale })
  const description = document.querySelector<HTMLMetaElement>('meta[name="description"]')
  if (description) description.content = i18n.t('meta.description', { lng: locale })
}

dayjs.locale(dayjsLocales[(i18n.language as AppLocale) in dayjsLocales ? i18n.language as AppLocale : DEFAULT_LOCALE])
i18n.on('languageChanged', (language) => {
  const locale = (language as AppLocale) || DEFAULT_LOCALE
  persistLocale(locale)
  dayjs.locale(dayjsLocales[locale in dayjsLocales ? locale : DEFAULT_LOCALE])
  updateMetadata(locale in dayjsLocales ? locale : DEFAULT_LOCALE)
})

export { setAdminLocale }
export type { AppLocale }
export default adminI18n
