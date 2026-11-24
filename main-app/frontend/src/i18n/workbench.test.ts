import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it, vi } from 'vitest'

const workbench = resolve(process.cwd(), '../../tryon-workbench')
const read = (path: string) => readFileSync(resolve(workbench, path), 'utf8')
const bundles = Object.fromEntries(
  ['zh-CN', 'en', 'ja'].map((locale) => [locale, JSON.parse(read(`static/i18n/${locale}.json`))]),
)

describe('workbench Japanese localization', () => {
  it('keeps Japanese dynamic content and translates the actual page across language changes', async () => {
    document.body.innerHTML = new DOMParser().parseFromString(read('static/index.html'), 'text/html').body.innerHTML
    window.history.replaceState({}, '', '/static/index.html?lang=ja')
    const fetchBundle = vi.fn(async (url: string) => ({
      ok: true,
      json: async () => bundles[url.match(/(zh-CN|en|ja)\.json/)?.[1] || 'zh-CN'],
    }))
    const start = new Function('window', 'document', 'NodeFilter', 'MutationObserver', 'CustomEvent', 'fetch', read('static/js/i18n.js'))
    start(window, document, NodeFilter, MutationObserver, CustomEvent, fetchBundle)
    const i18n = (window as unknown as { WorkbenchI18n: {
      ready: Promise<unknown>, setLocale: (locale: string) => Promise<unknown>, apply: (root: Element) => void,
    } }).WorkbenchI18n
    await i18n.ready

    const title = document.querySelector('#hero-product-title')!
    title.textContent = '防水ダウンジャケット'
    const reason = document.querySelector('#hero-recommendation-reason')!
    reason.textContent = '冬の重ね着に適した商品です。'
    i18n.apply(document.body)
    await new Promise((done) => setTimeout(done, 0))

    expect(title.textContent).toBe('防水ダウンジャケット')
    expect(reason.textContent).toBe('冬の重ね着に適した商品です。')
    expect(document.querySelector('option[value="ja"]')?.textContent).toBe('日本語')
    expect(document.querySelector('#workbench-locale-switcher')?.getAttribute('aria-label')).toBe('表示言語')
    expect(document.body.textContent).toContain('試着の調整')
    expect(document.body.textContent).not.toContain('この言語では表示できないメッセージです。')

    await i18n.setLocale('en')
    await i18n.setLocale('ja')
    expect(title.textContent).toBe('防水ダウンジャケット')
    expect(reason.textContent).toBe('冬の重ね着に適した商品です。')
    expect(document.querySelector('#workbench-locale-switcher')).toHaveValue('ja')

    document.head.innerHTML = '<title data-i18n="legacy.errorLogTitle">系统错误日志</title>'
    await i18n.setLocale('ja')
    expect(document.title).toBe(bundles.ja.legacy.errorLogTitle)
  })

  it('has translations for every static workbench text and assistive attribute', () => {
    const page = new DOMParser().parseFromString(read('static/index.html'), 'text/html')
    const sources = new Set<string>(Object.values(bundles['zh-CN'].legacy))
    const missing: string[] = []
    const walker = page.createTreeWalker(page.body, NodeFilter.SHOW_TEXT)
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const value = node.nodeValue?.trim() || ''
      const parent = node.parentElement
      if (!/[\u3400-\u9fff]/.test(value) || !parent || parent.closest('script, style, textarea, pre, #notification-container, #garment-grid, #errorlog-sidebar-list, #error-log-list, [data-i18n], #workbench-locale-switcher')) continue
      if (!sources.has(value)) missing.push(`text: ${value}`)
    }
    page.body.querySelectorAll('[title], [placeholder], [aria-label], [alt]').forEach((element) => {
      for (const attribute of ['title', 'placeholder', 'aria-label', 'alt']) {
        const value = element.getAttribute(attribute)?.trim() || ''
        if (/[\u3400-\u9fff]/.test(value) && !element.hasAttribute(`data-i18n-${attribute}`) && !sources.has(value)) {
          missing.push(`${attribute}: ${value}`)
        }
      }
    })
    expect(missing).toEqual([])
  })
})
