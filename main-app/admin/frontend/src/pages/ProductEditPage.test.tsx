import { describe, expect, it } from 'vitest'
import { productFormValues } from './ProductEditPage'

describe('product edit values', () => {
  it('uses canonical business values while keeping prices and image paths', () => {
    const value = productFormValues({
      price: 100, image_path: 'old.png', color_family: 'Black', style_type: 'Casual',
      canonical: { color_family: '黑色', style_type: '日常休闲', body_fit: '常规', style_features: ['简约'] },
    })
    expect(value).toMatchObject({ price: 100, image_path: 'old.png', color_family: '黑色', style_type: '日常休闲', body_fit: '常规', style_features: ['简约'] })
  })
  it('supports older responses without canonical fields', () => {
    expect(productFormValues({ color_family: '黑色' }).color_family).toBe('黑色')
  })
})
