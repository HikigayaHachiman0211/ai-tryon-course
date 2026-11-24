import type { AppLocale } from './locale'

export function formatCurrency(value: number | null | undefined, locale: AppLocale): string {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return new Intl.NumberFormat(locale, { style: 'currency', currency: 'CNY', minimumFractionDigits: 2 }).format(Number(value))
}

export function formatNumber(value: number | null | undefined, locale: AppLocale): string {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return new Intl.NumberFormat(locale).format(Number(value))
}

export function formatDate(value: string | number | Date | null | undefined, locale: AppLocale): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai' }).format(date)
}

export function formatRelative(value: number, unit: Intl.RelativeTimeFormatUnit, locale: AppLocale): string {
  return new Intl.RelativeTimeFormat(locale, { numeric: 'auto' }).format(value, unit)
}
