import { expect, it } from 'vitest'
import { annotationFormValues } from './AnnotationsPage'

it('uses canonical annotation fields when a Japanese display is returned', () => {
  expect(annotationFormValues({
    style_type: 'ショートジャケット', color_family: 'ブラック系', body_fit: '標準',
    canonical: { style_type: '短款', color_family: '黑色系', body_fit: '常规' },
  })).toEqual({ style_type: '短款', color_family: '黑色系', body_fit: '常规' })
})
