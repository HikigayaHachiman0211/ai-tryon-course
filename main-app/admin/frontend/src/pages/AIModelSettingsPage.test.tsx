import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }))
vi.mock('../utils/request', () => ({ default: mocks }))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock('./VideoSettingsTab', () => ({ default: () => <div /> }))
vi.mock('./RealtimeSettingsTab', () => ({ default: () => <div /> }))

import AIModelSettingsPage from './AIModelSettingsPage'

beforeEach(() => {
  vi.clearAllMocks()
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })
  mocks.get.mockImplementation((url: string) => {
    if (url === '/api/ai-config/providers') return Promise.resolve({ data: [] })
    if (url === '/api/ai-config/features') return Promise.resolve({ data: [] })
    if (url === '/api/ai-config/tryon') {
      return Promise.resolve({
        data: {
          feature_key: 'tryon',
          enabled: true,
          provider_key: 'totokens',
          active_provider_key: 'totokens',
          base_url: 'https://totokens.cc',
          provider_enabled: true,
          has_api_key: false,
          key_status: 'ok',
          flash_model: 'gemini-3.1-flash-image',
          pro_model: 'gpt-image-2',
          timeout_seconds: 120,
          retry_count: 0,
          updated_at: null,
          updated_by: null,
          last_test_status: null,
          last_test_message: null,
          last_test_at: null,
          totokens_enabled: true,
          totokens_has_api_key: true,
          totokens_configured_count: 2,
          totokens_apis: [
            {
              id: 'totokens_gemini',
              scope: 'gemini',
              label: 'ToTokens Gemini',
              builtin: true,
              enabled: true,
              base_url: 'https://totokens.cc',
              has_api_key: true,
              key_status: 'ok',
              default_model: 'gemini-3.1-flash-image',
              models: ['gemini-3.1-flash-image'],
              timeout_seconds: 120,
              last_test_status: 'success',
              last_test_message: 'ok',
              last_test_at: null,
            },
            {
              id: 'totokens_gpt_1k',
              scope: 'gpt_1k',
              label: 'ToTokens GPT 1K',
              builtin: true,
              enabled: true,
              base_url: 'https://totokens.cc',
              has_api_key: true,
              key_status: 'ok',
              default_model: 'gpt-image-2',
              models: ['gpt-image-2'],
              timeout_seconds: 120,
              last_test_status: null,
              last_test_message: null,
              last_test_at: null,
            },
            {
              id: 'totokens_gpt_2k4k',
              scope: 'gpt_2k4k',
              label: 'ToTokens GPT 2K/4K',
              builtin: true,
              enabled: true,
              base_url: 'https://totokens.cc',
              has_api_key: false,
              key_status: 'ok',
              default_model: 'gpt-image-2',
              models: ['gpt-image-2'],
              timeout_seconds: 120,
              last_test_status: null,
              last_test_message: null,
              last_test_at: null,
            },
          ],
        },
      })
    }
    return Promise.resolve({ data: {} })
  })
  mocks.put.mockImplementation((_url: string, body: unknown) => {
    const sentApis = ((body as { totokens_apis?: Array<{ id: string; api_key?: string; clear_api_key?: boolean }> })?.totokens_apis) || []
    return Promise.resolve({
      data: {
        feature_key: 'tryon',
        enabled: true,
        provider_key: 'totokens',
        active_provider_key: 'totokens',
        base_url: 'https://totokens.cc',
        provider_enabled: true,
        has_api_key: false,
        key_status: 'ok',
        flash_model: 'gemini-3.1-flash-image',
        pro_model: 'gpt-image-2',
        timeout_seconds: 120,
        retry_count: 0,
        updated_at: null,
        updated_by: 'admin',
        last_test_status: null,
        last_test_message: null,
        last_test_at: null,
        totokens_enabled: true,
        totokens_has_api_key: true,
        totokens_apis: [
          {
            id: 'totokens_gemini', scope: 'gemini', label: 'ToTokens Gemini', builtin: true, enabled: true,
            base_url: 'https://totokens.cc', has_api_key: true, key_status: 'ok',
            default_model: 'gemini-3.1-flash-image', models: ['gemini-3.1-flash-image'], timeout_seconds: 120,
            last_test_status: null, last_test_message: null, last_test_at: null,
          },
          {
            id: 'totokens_gpt_1k', scope: 'gpt_1k', label: 'ToTokens GPT 1K', builtin: true, enabled: true,
            base_url: 'https://totokens.cc', has_api_key: true, key_status: 'ok',
            default_model: 'gpt-image-2', models: ['gpt-image-2'], timeout_seconds: 120,
            last_test_status: null, last_test_message: null, last_test_at: null,
          },
          {
            id: 'totokens_gpt_2k4k', scope: 'gpt_2k4k', label: 'ToTokens GPT 2K/4K', builtin: true, enabled: true,
            base_url: 'https://totokens.cc', has_api_key: Boolean(sentApis.find(a => a.id === 'totokens_gpt_2k4k')?.api_key), key_status: 'ok',
            default_model: 'gpt-image-2', models: ['gpt-image-2'], timeout_seconds: 120,
            last_test_status: null, last_test_message: null, last_test_at: null,
          },
        ],
      },
    })
  })
  mocks.post.mockResolvedValue({ data: { success: true, latency_ms: 88, status_code: 200, message: 'OK', model_check: { flash_found: true, pro_found: true }, models_matched: ['gpt-image-2'] } })
})

afterEach(cleanup)

it('renders multi-API ToTokens cards, submits typed profile key, and tests a profile key independently', async () => {
  render(<AIModelSettingsPage />)
  fireEvent.click(screen.getByText('ai.tryon'))

  expect(await screen.findByText('tryonRelay.builtinLabelGemini')).toBeInTheDocument()
  expect(screen.getByText('tryonRelay.builtinLabelGpt1k')).toBeInTheDocument()
  expect(screen.getByText('tryonRelay.builtinLabelGpt2k4k')).toBeInTheDocument()

  const newKeyInput = screen.getByPlaceholderText('tryonRelay.keyPlaceholderNew')
  fireEvent.change(newKeyInput, { target: { value: 'sk-2k4k-secret' } })
  fireEvent.click(screen.getByRole('button', { name: /ai\.saveConfig/ }))

  await waitFor(() => expect(mocks.put).toHaveBeenCalled())
  const putPayload = mocks.put.mock.calls[0][1] as { totokens_apis: Array<{ id: string; api_key?: string }> }
  const sent2k = putPayload.totokens_apis.find(p => p.id === 'totokens_gpt_2k4k')
  expect(sent2k?.api_key).toBe('sk-2k4k-secret')
  const sent1k = putPayload.totokens_apis.find(p => p.id === 'totokens_gpt_1k')
  expect(sent1k?.api_key).toBeUndefined()

  const testButtons = screen.getAllByRole('button', { name: /tryonRelay\.testProfile/ })
  fireEvent.click(testButtons[0])
  await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
    '/api/ai-config/tryon/test',
    undefined,
    { params: { provider_key: 'totokens', profile_id: 'totokens_gemini' } },
  ))
})
