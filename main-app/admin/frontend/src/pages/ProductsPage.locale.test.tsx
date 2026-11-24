import { render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ locale: 'zh-CN', list: vi.fn() }))
vi.mock('react-i18next', () => ({ useTranslation: () => ({
  t: (key: string) => key,
  i18n: { language: mocks.locale, resolvedLanguage: mocks.locale },
}) }))
vi.mock('../api/products', () => ({
  listProducts: mocks.list, deleteProduct: vi.fn(), batchDelete: vi.fn(),
  importProducts: vi.fn(), validateLinks: vi.fn(),
}))

import ProductsPage from './ProductsPage'

it('reloads product display data when the administrator changes language', async () => {
  Object.defineProperty(window, 'matchMedia', { configurable: true, value: () => ({
    matches: false, addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {},
  }) })
  mocks.list.mockResolvedValue({ data: { items: [], total: 0 } })
  const view = render(<MemoryRouter><ProductsPage /></MemoryRouter>)
  await waitFor(() => expect(mocks.list).toHaveBeenCalledTimes(1))
  mocks.locale = 'ja'
  view.rerender(<MemoryRouter><ProductsPage /></MemoryRouter>)
  await waitFor(() => expect(mocks.list).toHaveBeenCalledTimes(2))
})
