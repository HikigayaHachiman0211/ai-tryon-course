import { describe, expect, it } from 'vitest'
import { withLocaleQuery } from './adminUrl'

describe('cross-origin locale URLs', () => {
  it('preserves existing query parameters and hash while setting lang', () => {
    expect(withLocaleQuery('https://admin.example.test/products?tab=history#details', 'en'))
      .toBe('https://admin.example.test/products?tab=history&lang=en#details')
  })

  it('replaces an existing lang without duplicating it', () => {
    expect(withLocaleQuery('https://workbench.example.test/?lang=zh-CN&x=1', 'ja'))
      .toBe('https://workbench.example.test/?lang=ja&x=1')
  })
})
