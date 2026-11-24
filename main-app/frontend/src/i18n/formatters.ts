import type { AppLocale } from './locale'

export const formatCurrency = (value: number, locale: AppLocale): string =>
  new Intl.NumberFormat(locale, { style: 'currency', currency: 'CNY' }).format(value)

export const formatNumber = (value: number, locale: AppLocale, options?: Intl.NumberFormatOptions): string =>
  new Intl.NumberFormat(locale, options).format(value)

export const formatDateTime = (
  value: string | number | Date,
  locale: AppLocale,
  options: Intl.DateTimeFormatOptions = { dateStyle: 'medium', timeStyle: 'short' },
): string => new Intl.DateTimeFormat(locale, options).format(new Date(value))

export const formatRelative = (
  amount: number,
  unit: Intl.RelativeTimeFormatUnit,
  locale: AppLocale,
): string => new Intl.RelativeTimeFormat(locale, { numeric: 'auto' }).format(amount, unit)
