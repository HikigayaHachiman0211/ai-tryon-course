import { describe, expect, it } from 'vitest'
import {
  DEFAULT_LOCALE,
  detectInitialLocale,
  normalizeLocale,
  setAdminLocale,
  SUPPORTED_LOCALES,
} from './locale'

describe('admin locale contract', () => {
  it('accepts only the three normalized locales', () => {
    expect(SUPPORTED_LOCALES).toEqual(['zh-CN', 'en', 'ja'])
    expect(normalizeLocale('zh')).toBe('zh-CN')
    expect(normalizeLocale('zh-Hans-CN')).toBe('zh-CN')
    expect(normalizeLocale('en-US')).toBe('en')
    expect(normalizeLocale('ja-JP')).toBe('ja')
    expect(normalizeLocale('fr-FR')).toBeNull()
  })

  it('uses explicit URL locale before storage and browser hints', () => {
    window.history.replaceState({}, '', '/?lang=ja')
    localStorage.setItem('ai-tryon.admin.locale', 'en')
    Object.defineProperty(navigator, 'language', { configurable: true, value: 'zh-CN' })
    expect(detectInitialLocale()).toBe('ja')
  })

  it('falls back safely when storage is unavailable', () => {
    window.history.replaceState({}, '', '/')
    Object.defineProperty(navigator, 'languages', { configurable: true, value: ['zh-CN'] })
    Object.defineProperty(navigator, 'language', { configurable: true, value: 'zh-CN' })
    const original = Storage.prototype.getItem
    Storage.prototype.getItem = () => { throw new Error('privacy mode') }
    try {
      expect(detectInitialLocale()).toBe(DEFAULT_LOCALE)
    } finally {
      Storage.prototype.getItem = original
    }
  })

  it('preserves unrelated query and hash while switching', async () => {
    window.history.replaceState({}, '', '/products?filter=active#table')
    await setAdminLocale('en')
    expect(window.location.href).toContain('/products?filter=active&lang=en#table')
    expect(localStorage.getItem('ai-tryon.admin.locale')).toBe('en')
    expect(document.documentElement.lang).toBe('en')
  })
})
