import type { ChangeEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { LOCALE_LABELS, SUPPORTED_LOCALES, type AppLocale } from './locale'

interface LanguageSwitcherProps {
  locale: AppLocale
  onChange: (locale: AppLocale) => void
}

export function LanguageSwitcher({ locale, onChange }: LanguageSwitcherProps) {
  const { t } = useTranslation('common')
  const handleChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const nextLocale = SUPPORTED_LOCALES.find((candidate) => candidate === event.target.value)
    if (nextLocale) onChange(nextLocale)
  }

  return (
    <label className="language-switcher">
      <span className="sr-only">{t('common.language')}</span>
      <select
        aria-label={t('common.language')}
        data-testid="language-switcher"
        value={locale}
        onChange={handleChange}
        className="language-switcher-select"
      >
        {SUPPORTED_LOCALES.map((candidate) => (
          <option key={candidate} value={candidate}>{LOCALE_LABELS[candidate]}</option>
        ))}
      </select>
    </label>
  )
}
