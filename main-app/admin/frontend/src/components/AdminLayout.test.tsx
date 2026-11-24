import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { resolvedLanguage: 'zh-CN' },
  }),
}))

vi.mock('../i18n/LanguageSwitcher', () => ({
  default: () => <div data-testid="language-switcher" />,
}))

import AdminLayout from './AdminLayout'

function renderLayout(width: number) {
  Object.defineProperty(window, 'innerWidth', {
    writable: true,
    configurable: true,
    value: width,
  })
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<AdminLayout />}>
          <Route index element={<div>dashboard-body</div>} />
          <Route path="products" element={<div>products-body</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('AdminLayout responsive shell', () => {
  afterEach(() => {
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 1280,
    })
  })

  it('renders desktop sider on wide viewports', () => {
    const { container } = renderLayout(1280)
    expect(container.querySelector('.ant-layout-sider')).not.toBeNull()
    expect(screen.queryByRole('button', { name: 'Menu' })).toBeNull()
  })

  it('renders hamburger drawer navigation on mobile viewports', async () => {
    const { container } = renderLayout(390)
    expect(container.querySelector('.ant-layout-sider')).toBeNull()

    const menuButton = screen.getByRole('button', { name: 'Menu' })
    fireEvent.click(menuButton)

    const productsItem = await screen.findByText('nav.products')
    fireEvent.click(productsItem)
    expect(await screen.findByText('products-body')).toBeInTheDocument()
  })
})
