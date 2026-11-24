import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, it, vi } from 'vitest'

const root = resolve(process.cwd(), '../../tryon-workbench')
const read = (path: string) => readFileSync(resolve(root, path), 'utf8')

it('relocalizes catalog filters without losing their selected canonical values', async () => {
  document.body.innerHTML = new DOMParser().parseFromString(read('static/index.html'), 'text/html').body.innerHTML
  window.history.replaceState({}, '', '/static/index.html?lang=en')
  const fetchData = vi.fn(async (input: string) => {
    const url = new URL(input, window.location.origin)
    let data: unknown = {}
    if (url.pathname.startsWith('/static/i18n/')) {
      data = JSON.parse(read(`static/i18n/${url.pathname.split('/').pop()}`))
    } else if (url.pathname === '/api/products/filters') {
      const ja = url.searchParams.get('lang') === 'ja'
      data = {
        style_types: [{ key: '短款', label: ja ? 'ショートジャケット' : 'Cropped jacket' }],
        color_families: [{ key: '黑色系', label: ja ? 'ブラック系' : 'Black' }],
      }
    } else if (url.pathname === '/api/products') {
      data = { items: [], total: 0 }
    } else if (url.pathname === '/api/runtime-status') {
      data = { tryon_enabled: true, configured: true }
    } else if (url.pathname === '/api/errors') {
      data = { errors: [] }
    }
    return { ok: true, json: async () => data }
  })
  new Function('window', 'document', 'NodeFilter', 'MutationObserver', 'CustomEvent', 'fetch', read('static/js/i18n.js'))(
    window, document, NodeFilter, MutationObserver, CustomEvent, fetchData,
  )
  const i18n = (window as unknown as { WorkbenchI18n: {
    ready: Promise<unknown>, setLocale: (locale: string) => Promise<unknown>,
  } }).WorkbenchI18n
  await i18n.ready
  new Function('window', 'document', 'fetch', 'setInterval', read('static/js/script.js'))(
    window, document, fetchData, () => 0,
  )
  await vi.waitFor(() => expect(document.querySelector('#filter-style [data-value="短款"]')).not.toBeNull())
  ;(document.querySelector('#filter-style [data-value="短款"]') as HTMLElement).click()
  ;(document.querySelector('#filter-color [data-value="黑色系"]') as HTMLElement).click()

  await i18n.setLocale('ja')
  await vi.waitFor(() => expect(document.querySelector('#filter-style [data-value="短款"]')?.textContent).toBe('ショートジャケット'))
  expect(document.querySelector('#target-intake-status')?.textContent).toContain('推薦画像')
  expect(document.querySelector('#result-feedback')?.textContent).toContain('試着開始を待っています')
  expect(document.querySelector('#errorlog-sidebar-list')?.textContent).toContain('エラーはありません')
  expect(document.querySelector('#filter-style [data-value="短款"]')).toHaveClass('active')
  expect(document.querySelector('#filter-color [data-value="黑色系"]')).toHaveClass('active')
  expect(document.querySelector('#filter-color [data-value="黑色系"]')?.textContent).toBe('ブラック系')
  expect(document.querySelectorAll('#filter-style [data-value="短款"]')).toHaveLength(1)
})
