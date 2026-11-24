import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, it, vi } from 'vitest'

const root = resolve(process.cwd(), '../../tryon-workbench')
const read = (path: string) => readFileSync(resolve(root, path), 'utf8')

it('relocalizes an already linked recommendation when the workbench language changes', async () => {
  document.body.innerHTML = new DOMParser().parseFromString(read('static/index.html'), 'text/html').body.innerHTML
  const payload = {
    source: 'down-jacket-recommendation', productTitle: 'Black jacket', productId: '12',
    styleType: 'Cropped jacket', colorFamily: 'Black', recommendationReason: 'A warm jacket.',
    presentationSource: { kind: 'recommend', result: { locale: 'en', items: [{ id: 12 }], inference: {} } },
  }
  window.history.replaceState({}, '', `/static/index.html?lang=en&tryonPayload=${encodeURIComponent(JSON.stringify(payload))}`)
  const fetchData = vi.fn(async (input: string) => {
    const url = new URL(input, window.location.origin)
    let data: unknown = {}
    if (url.pathname.startsWith('/static/i18n/')) data = JSON.parse(read(`static/i18n/${url.pathname.split('/').pop()}`))
    else if (url.pathname === '/api/frontend-config') data = { recommend_app_url: 'http://main.example.test/' }
    else if (url.pathname === '/api/products/filters') data = { style_types: [], color_families: [] }
    else if (url.pathname === '/api/products') data = { items: [], total: 0 }
    else if (url.pathname === '/api/runtime-status') data = { tryon_enabled: true, configured: true }
    else if (url.pathname === '/api/errors') data = { errors: [] }
    else if (url.pathname === '/api/localize-result') data = {
      items: [{ title: '防水ダウンジャケット', style_type: 'ショートジャケット', color_family: 'ブラック系', reason: '冬に適した商品です。' }],
      inference: { display: { style: 'ショートジャケット' } },
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
  new Function('window', 'document', 'fetch', 'setInterval', read('static/js/script.js'))(window, document, fetchData, () => 0)
  await vi.waitFor(() => expect(document.querySelector('#hero-product-title')?.textContent).toBe('Black jacket'))
  expect(document.querySelector('#hero-score-value')?.textContent).toBe('--')
  await i18n.setLocale('ja')
  await vi.waitFor(() => expect(document.querySelector('#hero-product-title')?.textContent).toBe('防水ダウンジャケット'))
  expect(document.querySelector('#hero-style-type')?.textContent).toBe('ショートジャケット')
  expect(document.querySelector('#hero-recommendation-reason')?.textContent).toBe('冬に適した商品です。')
})
