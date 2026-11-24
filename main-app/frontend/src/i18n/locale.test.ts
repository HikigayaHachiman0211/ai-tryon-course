import { describe, expect, it, afterEach } from 'vitest'
import {
  DEFAULT_LOCALE,
  detectInitialLocale,
  normalizeLocale,
  resolveLocaleFromAcceptLanguage,
} from './locale'

describe('locale normalization', () => {
  it.each([
    ['zh', 'zh-CN'],
    ['zh_CN', 'zh-CN'],
    ['zh-Hans', 'zh-CN'],
    ['en-US', 'en'],
    ['ja-JP', 'ja'],
  ])('normalizes %s to %s', (input, expected) => {
    expect(normalizeLocale(input)).toBe(expected)
  })

  it('rejects unsupported values without reflecting them', () => {
    expect(normalizeLocale('fr-FR')).toBeNull()
    expect(normalizeLocale('')).toBeNull()
    expect(normalizeLocale(null)).toBeNull()
  })
})

describe('locale detection precedence', () => {
  afterEach(() => {
    window.history.replaceState({}, '', '/')
    window.localStorage.clear()
  })

  it('prefers URL, then storage, then navigator, then Chinese', () => {
    window.localStorage.setItem('ai-tryon.locale', 'ja-JP')
    Object.defineProperty(window.navigator, 'languages', { configurable: true, value: ['en-US'] })
    window.history.replaceState({}, '', '/?lang=en-US')
    expect(detectInitialLocale()).toBe('en')

    window.history.replaceState({}, '', '/')
    expect(detectInitialLocale()).toBe('ja')

    window.localStorage.clear()
    expect(detectInitialLocale()).toBe('en')

    Object.defineProperty(window.navigator, 'languages', { configurable: true, value: ['fr-FR'] })
    expect(detectInitialLocale()).toBe(DEFAULT_LOCALE)
  })

  it('falls back safely when localStorage throws', () => {
    const originalStorage = window.localStorage
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get() {
        throw new Error('storage disabled')
      },
    })
    Object.defineProperty(window.navigator, 'languages', { configurable: true, value: ['ja-JP'] })
    expect(detectInitialLocale()).toBe('ja')
    Object.defineProperty(window, 'localStorage', { configurable: true, value: originalStorage })
  })
})

describe('Accept-Language parsing', () => {
  it('uses quality order and ignores malformed or unsupported ranges', () => {
    expect(resolveLocaleFromAcceptLanguage('fr;q=0.9,ja-JP;q=0.8,en;q=0.7')).toBe('ja')
    expect(resolveLocaleFromAcceptLanguage('en;q=0.4,zh-CN;q=0.9')).toBe('zh-CN')
    expect(resolveLocaleFromAcceptLanguage('fr, *;q=0.5')).toBeNull()
  })
})
