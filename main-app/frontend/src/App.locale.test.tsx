import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  locale: 'zh-CN',
  recommend: vi.fn(),
  localize: vi.fn(),
  open: vi.fn(() => ({})),
  post: vi.fn(),
}))
vi.mock('./api', () => ({
  getRecommend: mocks.recommend, localizeResult: mocks.localize, getCatalogProducts: vi.fn(),
  analyzeStyleLab: vi.fn(), buildImageURL: (value: string) => value, getHistoryDetail: vi.fn(),
}))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock('./i18n', () => ({ default: { get resolvedLanguage() { return mocks.locale } }, setAppLocale: vi.fn() }))
vi.mock('./i18n/LanguageSwitcher', () => ({ LanguageSwitcher: () => null }))
vi.mock('./tryonBridge', () => ({
  getTryOnBaseUrl: () => 'https://workbench.example', getTryOnOrigin: () => 'https://workbench.example',
  openTryOnWindow: mocks.open, postTryOnPayloadWithAck: mocks.post,
}))
vi.mock('./views/RecommendView', () => ({ RecommendView: (props: {
  result: { items: { title: string }[] } | null
  onColorSelect: (value: string) => void
  onInputChange: (event: { target: { name: string, value: string } }) => void
  onRunRecommendation: () => void
  onOpenTryOnWorkbench: (item: unknown) => void
}) => <div>
  <button onClick={() => props.onColorSelect('黑色')}>color</button>
  <button onClick={() => props.onInputChange({ target: { name: 'gender', value: 'female' } })}>gender</button>
  <button onClick={props.onRunRecommendation}>recommend</button>
  <div data-testid="result-title">{props.result?.items[0]?.title}</div>
  {props.result && <button onClick={() => props.onOpenTryOnWorkbench(props.result!.items[0])}>try on</button>}
</div> }))
vi.mock('./views/StyleLabView', () => ({ StyleLabView: () => null }))
vi.mock('./components/DebugDrawer', () => ({ DebugDrawer: () => null }))
vi.mock('./components/HistoryDrawer', () => ({ HistoryDrawer: () => null }))
vi.mock('./assistant/components/FloatingAssistant', () => ({ FloatingAssistant: () => null }))
vi.mock('framer-motion', () => ({ AnimatePresence: ({ children }: { children: React.ReactNode }) => children, motion: { div: ({ children }: { children: React.ReactNode }) => <div>{children}</div> } }))

import App from './App'

it('relocalizes an existing recommendation and sends localized display fields to try-on', async () => {
  mocks.locale = 'zh-CN'
  window.history.replaceState({}, '', '/')
  const original = {
    locale: 'zh-CN', inference: { resolved_style: '短款' },
    items: [{ id: 1, title: '中文商品', price: 100, image_url: '', style_type: '短款', color_family: '黑色系', reason: '中文理由' }],
  }
  const japanese = {
    ...original, locale: 'ja', inference: { resolved_style: '短款', display: { style: 'ショートジャケット' } },
    items: [{ ...original.items[0], title: '日本語の商品', reason: '冬に適した商品です。', display: { title: '日本語の商品', styleType: 'ショートジャケット', colorFamily: 'ブラック系' } }],
  }
  mocks.recommend.mockResolvedValue(original)
  mocks.localize.mockResolvedValue(japanese)
  const view = render(<App />)
  fireEvent.click(screen.getByText('color'))
  fireEvent.click(screen.getByText('gender'))
  fireEvent.click(screen.getByText('recommend'))
  await screen.findByText('中文商品')
  mocks.locale = 'ja'
  view.rerender(<App />)
  await waitFor(() => expect(mocks.localize).toHaveBeenCalledWith('recommend', original, 'ja'))
  await screen.findByText('日本語の商品')
  fireEvent.click(screen.getByText('try on'))
  expect(mocks.open).toHaveBeenCalledWith(expect.objectContaining({
    locale: 'ja', productTitle: '日本語の商品', styleType: 'ショートジャケット',
    colorFamily: 'ブラック系', sceneHint: 'ショートジャケット', recommendationReason: '冬に適した商品です。',
  }))
})
