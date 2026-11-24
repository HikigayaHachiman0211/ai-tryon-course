import { AxiosHeaders, type InternalAxiosRequestConfig } from 'axios'
import { describe, expect, it, beforeEach } from 'vitest'
import { getCatalogProducts, getRecommend, api } from './api'
import i18n from './i18n'

describe('main API locale propagation', () => {
  beforeEach(() => {
    if (!i18n.hasResourceBundle('en', 'common')) i18n.addResourceBundle('en', 'common', {})
    Reflect.set(i18n, 'language', 'en')
    Reflect.set(i18n, 'resolvedLanguage', 'en')
  })

  it('adds the active locale to headers and recommendation multipart data', async () => {
    let requestConfig: InternalAxiosRequestConfig | undefined
    api.defaults.adapter = async (config) => {
      requestConfig = config
      return { data: { locale: 'en' }, status: 200, statusText: 'OK', headers: {}, config }
    }

    await getRecommend({ color_preference: 'black', gender: 'female' })

    expect(AxiosHeaders.from(requestConfig?.headers).get('Accept-Language')).toBe('en')
    expect((requestConfig?.data as FormData).get('locale')).toBe('en')
  })

  it('adds the active locale to catalog query parameters', async () => {
    let requestConfig: InternalAxiosRequestConfig | undefined
    api.defaults.adapter = async (config) => {
      requestConfig = config
      return { data: { items: [], total: 0 }, status: 200, statusText: 'OK', headers: {}, config }
    }

    await getCatalogProducts({ limit: 1 })
    expect(requestConfig?.params?.locale).toBe('en')
  })
})
