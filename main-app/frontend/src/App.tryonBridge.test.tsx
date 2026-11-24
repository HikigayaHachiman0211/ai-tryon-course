import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  catalog: vi.fn(),
  analyze: vi.fn(),
  open: vi.fn(() => ({ closed: false })),
  post: vi.fn(),
  fileToDataUrl: vi.fn(async () => 'data:image/jpeg;base64,sample-photo-bytes'),
}))

vi.mock('./api', () => ({
  getCatalogProducts: mocks.catalog,
  analyzeStyleLab: mocks.analyze,
  localizeResult: vi.fn(async (_kind: string, value: unknown) => value),
  getRecommend: vi.fn(),
  getHistoryDetail: vi.fn(),
  buildImageURL: (value: string) =>
    value.startsWith('http') ? value : `https://main.example.test${value.startsWith('/') ? '' : '/'}${value}`,
}))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock('./i18n', () => ({ default: { get resolvedLanguage() { return 'zh-CN' } }, setAppLocale: vi.fn() }))
vi.mock('./i18n/LanguageSwitcher', () => ({ LanguageSwitcher: () => null }))
vi.mock('./tryonBridge', () => ({
  getTryOnBaseUrl: () => 'https://workbench.example.test/static/index.html',
  getTryOnOrigin: () => 'https://workbench.example.test',
  openTryOnWindow: mocks.open,
  postTryOnPayloadWithAck: mocks.post,
}))
vi.mock('./utils/fileUtils', () => ({ fileToDataUrl: mocks.fileToDataUrl }))
vi.mock('./views/RecommendView', () => ({ RecommendView: () => null }))
vi.mock('./views/StyleLabView', () => ({
  StyleLabView: (props: {
    selectedProduct: { id: number; title: string; image_url: string; price: number; style_type: string; color_family: string } | null
    onSelectSampleModel: (model: { id: string; name: string; gender: 'male' | 'female'; filename: string }) => void
    onColorSelect: (color: string) => void
    onInputChange: (event: { target: { name: string; value: string } }) => void
    onCatalogSelectProduct: (product: unknown) => void
    onAnalyze: () => void
    onOpenTryOnFromStyleLab: (product: unknown) => void
  }) => (
    <div>
      <button onClick={() => props.onSelectSampleModel({ id: 'male-mannequin-1', name: '通用男模 1', gender: 'male', filename: 'mannequin-male-1.png' })}>
        pick-sample
      </button>
      <button onClick={() => props.onColorSelect('黑色')}>pick-color</button>
      <button onClick={() => props.onInputChange({ target: { name: 'gender', value: 'male' } })}>pick-gender</button>
      <button
        onClick={() =>
          props.onCatalogSelectProduct({
            id: 3172,
            locale: 'zh-CN',
            title: '2025轻薄羽绒服',
            price: 67,
            image_url: 'https://cdn.example.test/garment.jpg',
            product_url: 'https://item.example.test/3172',
            style_type: '短款',
            color_family: '黑色系',
            body_fit: '宽松',
            style_features: ['休闲'],
            function_features: ['连帽', '轻薄'],
            size_tags: ['XL'],
            size_notes: '建议XL码',
            product_gender: 'male',
            gender_label: '男款',
            is_child_product: false,
          })
        }
      >
        pick-product
      </button>
      <button onClick={props.onAnalyze}>analyze</button>
      {props.selectedProduct && (
        <button onClick={() => props.onOpenTryOnFromStyleLab(props.selectedProduct)}>tryon</button>
      )}
    </div>
  ),
}))
vi.mock('./components/DebugDrawer', () => ({ DebugDrawer: () => null }))
vi.mock('./components/HistoryDrawer', () => ({ HistoryDrawer: () => null }))
vi.mock('./assistant/components/FloatingAssistant', () => ({ FloatingAssistant: () => null }))
vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: { div: ({ children }: { children: React.ReactNode }) => <div>{children}</div> },
}))

import App from './App'

const originalFetch = globalThis.fetch

beforeEach(() => {
  window.location.hash = '#style-lab'
  mocks.catalog.mockReset()
  mocks.catalog.mockResolvedValue({ items: [], total: 0, gender_fallback: false })
  mocks.analyze.mockReset()
  mocks.open.mockClear()
  mocks.post.mockClear()
  mocks.fileToDataUrl.mockClear()
  globalThis.fetch = vi.fn(async () => ({
    ok: true,
    blob: async () => new Blob([new Uint8Array([1, 2, 3])], { type: 'image/jpeg' }),
  })) as unknown as typeof fetch
})

afterEach(() => {
  globalThis.fetch = originalFetch
})

it('forwards StyleLab analysis score, size, reason, user photo URL, and data URL to try-on', async () => {
  const product = {
    id: 3172,
    title: '2025轻薄羽绒服',
    price: 67,
    image_url: 'https://cdn.example.test/garment.jpg',
    product_url: 'https://item.example.test/3172',
    style_type: '短款',
    color_family: '黑色系',
    body_fit: '宽松',
    style_features: ['休闲'],
    function_features: ['连帽', '轻薄'],
    size_tags: ['XL'],
    size_notes: '建议XL码',
    product_gender: 'male',
    gender_label: '男款',
    is_child_product: false,
  }
  mocks.analyze.mockResolvedValue({
    locale: 'zh-CN',
    product,
    user_photo_url: '/api/media/user-photos/photo123.jpg?st=9999.sig',
    inference: {
      resolved_size: 'XL',
      resolved_style: '常规短外套',
      body_shape: '标准',
      size_source: 'photo',
      style_source: 'ai',
      reasoning: 'ok',
      gemini_model: '',
      gemini_used: false,
      ai_provider: 'mimo',
      display: { size: 'XL', style: '常规短外套', bodyShape: '标准' },
    },
    analysis: {
      total_score: 87.3,
      score_breakdown: {},
      radar_chart: [],
      reason: '商品色系为黑色系，与偏好的黑色更接近',
      styling_advice: [],
    },
  })

  render(<App />)
  await act(async () => {
    fireEvent.click(screen.getByText('pick-sample'))
  })
  fireEvent.click(screen.getByText('pick-color'))
  fireEvent.click(screen.getByText('pick-gender'))
  fireEvent.click(screen.getByText('pick-product'))
  await act(async () => {
    fireEvent.click(screen.getByText('analyze'))
  })
  await waitFor(() => expect(mocks.analyze).toHaveBeenCalledTimes(1))

  await act(async () => {
    fireEvent.click(screen.getByText('tryon'))
  })

  await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1))
  expect(mocks.open).toHaveBeenCalledWith(expect.objectContaining({
    productId: '3172',
    score: 87.3,
    sizeHint: 'XL',
    sceneHint: '常规短外套',
    fitNote: '建议XL码',
    recommendationReason: '商品色系为黑色系，与偏好的黑色更接近',
    userImageUrl: 'https://main.example.test/api/media/user-photos/photo123.jpg?st=9999.sig',
    presentationSource: expect.objectContaining({ kind: 'style-lab' }),
  }))
  expect(mocks.post).toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({
      score: 87.3,
      sizeHint: 'XL',
      userImageUrl: 'https://main.example.test/api/media/user-photos/photo123.jpg?st=9999.sig',
      userImageDataUrl: 'data:image/jpeg;base64,sample-photo-bytes',
    }),
    'https://workbench.example.test',
  )
})

it('forwards selected sample model URL and data URL from StyleLab even before analysis runs', async () => {
  render(<App />)
  await act(async () => {
    fireEvent.click(screen.getByText('pick-sample'))
  })
  fireEvent.click(screen.getByText('pick-product'))

  await act(async () => {
    fireEvent.click(screen.getByText('tryon'))
  })

  await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1))
  expect(mocks.open).toHaveBeenCalledWith(expect.objectContaining({
    productId: '3172',
    score: undefined,
    userImageUrl: 'https://main.example.test/sample-models/male/mannequin-male-1.png',
  }))
  expect(mocks.post).toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({
      userImageUrl: 'https://main.example.test/sample-models/male/mannequin-male-1.png',
      userImageDataUrl: 'data:image/jpeg;base64,sample-photo-bytes',
    }),
    'https://workbench.example.test',
  )
})
