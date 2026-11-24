import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }))
vi.mock('../utils/request', () => ({ default: mocks }))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))

import RealtimeSettingsTab from './RealtimeSettingsTab'

const baseConfig = {
  enabled: false,
  model: 'lucy-vton-3.6',
  base_url: 'https://api.decart.ai',
  has_api_key: true,
  key_decrypt_ok: true,
  require_access_code: true,
  has_access_code: true,
  access_code_decrypt_ok: true,
  access_code_length: 24,
  origin: 'https://workbench.example.test',
  effective_origin: 'https://workbench.example.test',
  max_seconds: 20,
  default_seconds: 15,
  cents_per_second: 2,
  daily_cents: 200,
  monthly_cents: 1000,
  visitor_daily_cents: 80,
  max_active: 1,
  starts_per_minute: 3,
  default_prompt: '',
  ready_to_serve: false,
  blocking_reasons: ['feature_disabled'],
  last_test_status: null,
  last_test_message: null,
  last_test_at: null,
  updated_at: null,
  updated_by: null,
}

const xmaxConfig = {
  provider_key: 'xmax',
  enabled: false,
  environment: 'global',
  base_url: 'https://api.xmax.ai/open/api/v1',
  default_model: 'x2.1',
  allowed_models: ['x2.1', 'x2.1-flash'],
  camera_preset: '1080x1920',
  face_restoration: true,
  has_api_key: true,
  key_decrypt_ok: true,
  require_access_code: true,
  has_access_code: true,
  access_code_decrypt_ok: true,
  access_code_length: 24,
  origin: 'https://workbench.example.test',
  effective_origin: 'https://workbench.example.test',
  min_seconds: 10,
  max_seconds: 60,
  default_seconds: 30,
  credits_per_second: 1,
  cents_per_minute: 10,
  daily_cents: 200,
  monthly_cents: 1000,
  visitor_daily_cents: 50,
  min_account_credits: 60,
  max_active: 1,
  starts_per_minute: 3,
  default_prompt: '',
  ready_to_serve: false,
  blocking_reasons: ['feature_disabled'],
  last_test_status: null,
  last_test_message: null,
  last_test_at: null,
  updated_at: null,
  updated_by: null,
}

const reactorConfig = {
  provider_key: 'reactor',
  enabled: false,
  base_url: 'https://api.reactor.inc',
  default_model: 'reactor/xmax-x2-1',
  allowed_models: ['reactor/xmax-x2-1', 'xmax/x2'],
  has_api_key: true,
  key_decrypt_ok: true,
  require_access_code: true,
  has_access_code: true,
  access_code_decrypt_ok: true,
  access_code_length: 24,
  origin: 'https://workbench.example.test',
  effective_origin: 'https://workbench.example.test',
  min_seconds: 10,
  max_seconds: 60,
  default_seconds: 30,
  credits_per_second: 17,
  cents_per_minute: 11,
  daily_cents: 200,
  monthly_cents: 1000,
  visitor_daily_cents: 50,
  min_account_credits: 1000,
  max_active: 1,
  starts_per_minute: 3,
  default_prompt: '',
  ready_to_serve: false,
  blocking_reasons: ['feature_disabled'],
  last_test_status: null,
  last_test_message: null,
  last_test_at: null,
  updated_at: null,
  updated_by: null,
}

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
    if (url === '/api/ai-config/realtime/xmax') return Promise.resolve({ data: xmaxConfig })
    if (url === '/api/ai-config/realtime/reactor') return Promise.resolve({ data: reactorConfig })
    return Promise.resolve({ data: baseConfig })
  })
  mocks.put.mockImplementation((url: string) => {
    if (url === '/api/ai-config/realtime/xmax') return Promise.resolve({ data: { ...xmaxConfig, daily_cents: 400 } })
    if (url === '/api/ai-config/realtime/reactor') return Promise.resolve({ data: { ...reactorConfig, daily_cents: 350 } })
    return Promise.resolve({ data: { ...baseConfig, daily_cents: 300 } })
  })
})

afterEach(cleanup)

it('prefills all numeric defaults even when GET fails (regression for empty InputNumber fields)', async () => {
  mocks.get.mockRejectedValueOnce(new Error('temporary offline'))
  render(
    <MemoryRouter>
      <RealtimeSettingsTab />
    </MemoryRouter>,
  )

  expect(await screen.findByDisplayValue('2')).toBeInTheDocument()
  expect(screen.getByDisplayValue('20')).toBeInTheDocument()
  expect(screen.getByDisplayValue('15')).toBeInTheDocument()
  expect(screen.getByDisplayValue('200')).toBeInTheDocument()
  expect(screen.getByDisplayValue('1000')).toBeInTheDocument()
  expect(screen.getByDisplayValue('80')).toBeInTheDocument()
  expect(await screen.findByText(/temporary offline/)).toBeInTheDocument()
})

it('saves budget updates without overwriting saved keys and runs zero-cost connection test', async () => {
  mocks.post.mockResolvedValueOnce({ data: { success: true, status_code: 200, latency_ms: 95, message: 'OK' } })
  render(
    <MemoryRouter>
      <RealtimeSettingsTab />
    </MemoryRouter>,
  )

  const originInput = await screen.findByLabelText('realtimeSettings.origin')
  await waitFor(() => expect(originInput).toHaveValue('https://workbench.example.test'))
  fireEvent.change(originInput, { target: { value: 'https://tryon.example.test' } })
  fireEvent.click(screen.getByRole('button', { name: /actions\.save/ }))

  await waitFor(() => expect(mocks.put).toHaveBeenCalled())
  expect(mocks.put.mock.calls[0][0]).toBe('/api/ai-config/realtime')
  expect(mocks.put.mock.calls[0][1]).toMatchObject({ origin: 'https://tryon.example.test', enabled: false })
  expect(mocks.put.mock.calls[0][1].api_key).toBeUndefined()

  fireEvent.click(screen.getByRole('button', { name: /realtimeSettings\.test/ }))
  await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/ai-config/realtime/test'))
  expect(await screen.findByText(/95 ms/)).toBeInTheDocument()
})

it('generates an access code and displays it once', async () => {
  mocks.post.mockResolvedValueOnce({
    data: { access_code: 'generated-strong-code-1234', access_code_length: 26, config: baseConfig },
  })
  render(
    <MemoryRouter>
      <RealtimeSettingsTab />
    </MemoryRouter>,
  )

  const genBtn = await screen.findByRole('button', { name: /realtimeSettings\.generateCode/ })
  fireEvent.click(genBtn)
  await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/ai-config/realtime/generate-code'))
  expect(await screen.findByText('generated-strong-code-1234')).toBeInTheDocument()
})

it('switches to Xmax X2.1 settings panel, saves config, and tests zero-cost balance', async () => {
  mocks.post.mockResolvedValueOnce({
    data: { success: true, status_code: 200, latency_ms: 68, message: 'OK (balance=980.0)', current_balance: 980 },
  })
  render(
    <MemoryRouter>
      <RealtimeSettingsTab />
    </MemoryRouter>,
  )

  fireEvent.click(await screen.findByText('realtimeSettings.engineXmax'))
  expect(await screen.findByText('realtimeSettings.xmaxTitle')).toBeInTheDocument()

  const saveBtn = await screen.findByRole('button', { name: /actions\.save/ })
  fireEvent.click(saveBtn)
  await waitFor(() => expect(mocks.put.mock.calls.some((c) => c[0] === '/api/ai-config/realtime/xmax')).toBe(true))

  fireEvent.click(screen.getByRole('button', { name: /realtimeSettings\.xmaxTest/ }))
  await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/ai-config/realtime/xmax/test'))
  expect(await screen.findByText(/68 ms/)).toBeInTheDocument()
})

it('switches to Reactor panel, fetches official pricing data, saves config, and tests zero-cost connectivity', async () => {
  mocks.post.mockImplementation((url: string) => {
    if (url === '/api/ai-config/realtime/reactor/fetch-official') {
      return Promise.resolve({
        data: {
          ok: true,
          provider: 'reactor',
          source: 'live_api',
          fetched_at: '2026-11-23T12:00:00+00:00',
          summary: 'X2.1=17 credits/s ($0.0017/s, 11¢/min)',
          warning: null,
          official_rates: {},
          account_info: { account_id: 'acct-1', balance: 4200, balance_usd: 0.42 },
          suggested_fields: {
            base_url: 'https://api.reactor.inc',
            default_model: 'reactor/xmax-x2-1',
            allowed_models: ['reactor/xmax-x2-1', 'xmax/x2'],
            credits_per_second: 17,
            cents_per_minute: 12,
            min_seconds: 10,
            max_seconds: 60,
            default_seconds: 30,
            daily_cents: 250,
            monthly_cents: 1200,
            visitor_daily_cents: 50,
            min_account_credits: 1000,
            max_active: 1,
            starts_per_minute: 3,
            default_prompt: 'Reactor official prompt',
          },
        },
      })
    }
    return Promise.resolve({
      data: { success: true, status_code: 200, latency_ms: 42, message: 'OK (balance=4200 credits)', current_balance: 4200 },
    })
  })

  render(
    <MemoryRouter>
      <RealtimeSettingsTab />
    </MemoryRouter>,
  )

  fireEvent.click(await screen.findByText('realtimeSettings.engineReactor'))
  expect(await screen.findByText('realtimeSettings.reactorTitle')).toBeInTheDocument()

  // All key numeric inputs pre-filled with Reactor defaults
  expect(await screen.findByDisplayValue('17')).toBeInTheDocument()
  expect(screen.getByDisplayValue('11')).toBeInTheDocument()
  expect(screen.getAllByDisplayValue('1000').length).toBeGreaterThanOrEqual(2)

  // Fetch official data (zero cost) pre-fills updated rates & shows summary
  fireEvent.click(screen.getByRole('button', { name: /realtimeSettings\.fetchOfficial/ }))
  await waitFor(() =>
    expect(mocks.post).toHaveBeenCalledWith('/api/ai-config/realtime/reactor/fetch-official', expect.any(Object)),
  )
  expect(await screen.findByText(/X2\.1=17 credits\/s/)).toBeInTheDocument()
  expect(await screen.findByDisplayValue('12')).toBeInTheDocument()
  expect(screen.getByDisplayValue('250')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: /actions\.save/ }))
  await waitFor(() => expect(mocks.put.mock.calls.some((c) => c[0] === '/api/ai-config/realtime/reactor')).toBe(true))

  fireEvent.click(screen.getByRole('button', { name: /realtimeSettings\.reactorTest/ }))
  await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/ai-config/realtime/reactor/test'))
  expect(await screen.findByText(/42 ms/)).toBeInTheDocument()
})
