import { describe, expect, it } from 'vitest'
import { formatCurrency, formatNumber, formatRelative } from './formatters'

describe('admin locale formatters', () => {
  it('formats currency and numbers in all locales', () => {
    expect(formatCurrency(1234.5, 'zh-CN')).toContain('1,234.50')
    expect(formatCurrency(1234.5, 'en')).toContain('1,234.50')
    expect(formatCurrency(1234.5, 'ja')).toContain('1,234.50')
    expect(formatNumber(1234567, 'en')).toBe('1,234,567')
  })

  it('uses locale-aware relative time', () => {
    expect(formatRelative(-1, 'day', 'en')).toContain('yesterday')
    expect(formatRelative(-1, 'day', 'ja')).toContain('昨日')
  })
})
