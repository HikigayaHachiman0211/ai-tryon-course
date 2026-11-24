import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, it, vi } from 'vitest'

const root = resolve(process.cwd(), '../../tryon-workbench')
const read = (path: string) => readFileSync(resolve(root, path), 'utf8')

it('emits DOWN_JACKET_TRYON_READY and imports postMessage user photo without urlPayload clobbering it', async () => {
  document.body.innerHTML = new DOMParser().parseFromString(read('static/index.html'), 'text/html').body.innerHTML
  const openerPostMessage = vi.fn()
  Object.defineProperty(window, 'opener', {
    configurable: true,
    value: { closed: false, postMessage: openerPostMessage },
  })
  const payload = {
    source: 'down-jacket-recommendation', productTitle: 'Down coat', productId: '3172',
    garmentImageUrl: 'https://cdn.example.test/garment.jpg',
    styleType: '短款', colorFamily: '黑色系', sizeHint: 'XL', score: 87.3,
    recommendationReason: '黑色搭配协调',
    presentationSource: { kind: 'style-lab', result: { locale: 'zh-CN', product: { id: 3172 }, analysis: { reason: '黑色搭配协调' } } },
  }
  window.history.replaceState({}, '', `/static/index.html?lang=zh-CN&tryonPayload=${encodeURIComponent(JSON.stringify(payload))}`)

  const intakeCalls: Array<{ role: string; hasUrl: boolean; hasData: boolean }> = []
  const fetchData = vi.fn(async (input: string, init?: RequestInit) => {
    const url = new URL(input, window.location.origin)
    let data: unknown = {}
    if (url.pathname.startsWith('/static/i18n/')) data = JSON.parse(read(`static/i18n/${url.pathname.split('/').pop()}`))
    else if (url.pathname === '/api/frontend-config') data = { recommend_app_url: 'http://main.example.test/' }
    else if (url.pathname === '/api/products/filters') data = { style_types: [], color_families: [] }
    else if (url.pathname === '/api/products') data = { items: [], total: 0 }
    else if (url.pathname === '/api/runtime-status') data = { tryon_enabled: true, configured: true }
    else if (url.pathname === '/api/errors') data = { errors: [] }
    else if (url.pathname === '/api/intake-image') {
      const body = JSON.parse(String(init?.body || '{}'))
      intakeCalls.push({
        role: body.role,
        hasUrl: Boolean(body.image_url),
        hasData: Boolean(body.image_data_url),
      })
      const fname = body.role === 'model' ? 'user-1.jpg' : 'garment-1.jpg'
      data = { ok: true, filename: fname, cloud_url: `/api/media/uploads/${fname}?st=ok` }
    }
    return { ok: true, json: async () => data }
  })

  new Function('window', 'document', 'NodeFilter', 'MutationObserver', 'CustomEvent', 'fetch', read('static/js/i18n.js'))(
    window, document, NodeFilter, MutationObserver, CustomEvent, fetchData,
  )
  const i18n = (window as unknown as { WorkbenchI18n: { ready: Promise<unknown> } }).WorkbenchI18n
  await i18n.ready
  new Function('window', 'document', 'fetch', 'setInterval', read('static/js/script.js'))(window, document, fetchData, () => 0)

  // Early message dispatched before /api/frontend-config resolves should be buffered and processed.
  window.dispatchEvent(new MessageEvent('message', {
    origin: 'http://main.example.test',
    data: {
      type: 'DOWN_JACKET_TRYON_INIT',
      version: 1,
      payload: { ...payload, userImageDataUrl: 'data:image/jpeg;base64,abc123' },
    },
  }))

  await vi.waitFor(() => {
    expect(openerPostMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'DOWN_JACKET_TRYON_READY' }),
      'http://main.example.test',
    )
  })
  await vi.waitFor(() => {
    expect(document.querySelector('#target-cover-img')?.getAttribute('src')).toContain('user-1.jpg')
    expect(document.querySelector('#ref-cover-img')?.getAttribute('src')).toContain('garment-1.jpg')
  })
  expect(document.querySelector('#hero-score-value')?.textContent).toBe('87.3')
  expect(document.querySelector('#hero-size-hint')?.textContent).toBe('XL')
  expect(intakeCalls.filter((c) => c.role === 'model')).toHaveLength(1)
  expect(intakeCalls.filter((c) => c.role === 'garment')).toHaveLength(1)
})
