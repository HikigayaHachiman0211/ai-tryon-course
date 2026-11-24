import { useTranslation } from 'react-i18next'
import { setAdminLocale, SUPPORTED_LOCALES, type AppLocale } from './locale'

export default function LanguageSwitcher() {
  const { t, i18n } = useTranslation('common')
  const locale = (SUPPORTED_LOCALES.includes(i18n.language as AppLocale) ? i18n.language : 'zh-CN') as AppLocale
  return (
    <label className="admin-language-switcher">
      <span className="sr-only">{t('language.label')}</span>
    <select data-testid="language-switcher" aria-label={t('language.label')} value={locale} onChange={(event) => void setAdminLocale(event.target.value as AppLocale)}>
        <option value="zh-CN">简体中文</option>
        <option value="en">English</option>
        <option value="ja">日本語</option>
      </select>
    </label>
  )
}
