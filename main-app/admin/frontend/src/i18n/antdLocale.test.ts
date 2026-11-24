import { describe, expect, it } from 'vitest'
import { antdLocales, dayjsLocales } from './antdLocale'

describe('Ant Design and dayjs locale mapping', () => {
  it('maps every app locale', () => {
    expect(Object.keys(antdLocales)).toEqual(['zh-CN', 'en', 'ja'])
    expect(dayjsLocales).toEqual({ 'zh-CN': 'zh-cn', en: 'en', ja: 'ja' })
  })
})
