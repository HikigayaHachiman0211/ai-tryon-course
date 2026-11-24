import { describe, expect, it } from 'vitest'
import { formatCurrency, formatDateTime, formatNumber, formatRelative } from './formatters'

describe('locale-aware formatters', () => {
  it.each(['zh-CN', 'en', 'ja'] as const)('formats CNY with %s', (locale) => {
    expect(formatCurrency(1234.5, locale)).toBe(
      new Intl.NumberFormat(locale, { style: 'currency', currency: 'CNY' }).format(1234.5),
    )
  })

  it('formats date, number, and relative time using the active locale', () => {
    expect(formatNumber(1234567, 'en')).toBe(new Intl.NumberFormat('en').format(1234567))
    expect(formatDateTime('2026-01-02T03:04:05Z', 'ja')).toBe(
      new Intl.DateTimeFormat('ja', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date('2026-01-02T03:04:05Z')),
    )
    expect(formatRelative(-2, 'day', 'en')).toBe(
      new Intl.RelativeTimeFormat('en', { numeric: 'auto' }).format(-2, 'day'),
    )
  })
})
