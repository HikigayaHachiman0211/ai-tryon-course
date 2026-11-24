import { render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ locale: 'ja', t: (key: string) => key }))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: mocks.t, i18n: { resolvedLanguage: mocks.locale } }) }))
vi.mock('./components/AuthGuard', () => ({ default: () => null }))

import App from './App'

it('keeps the document language synchronized when a stale route query remains mounted', async () => {
  const view = render(<MemoryRouter initialEntries={['/?lang=ja']}><App /></MemoryRouter>)
  await waitFor(() => expect(document.documentElement.lang).toBe('ja'))
  mocks.locale = 'en'
  view.rerender(<MemoryRouter initialEntries={['/?lang=ja']}><App /></MemoryRouter>)
  await waitFor(() => expect(document.documentElement.lang).toBe('en'))
})
