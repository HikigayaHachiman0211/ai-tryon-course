import { describe, expect, it, beforeEach } from 'vitest'
import { applyDocumentMetadata } from './index'

describe('i18n document metadata', () => {
  beforeEach(() => {
    document.head.innerHTML = '<meta name="description" content="old">'
    document.documentElement.lang = 'zh-CN'
    document.documentElement.dir = 'ltr'
  })

  it('updates lang, direction, title, and description atomically', () => {
    applyDocumentMetadata('ja', {
      title: 'AIダウンジャケット推薦プラットフォーム',
      description: '日本語の説明',
    })

    expect(document.documentElement.lang).toBe('ja')
    expect(document.documentElement.dir).toBe('ltr')
    expect(document.title).toBe('AIダウンジャケット推薦プラットフォーム')
    expect(document.querySelector('meta[name="description"]')).toHaveAttribute('content', '日本語の説明')
  })
})
