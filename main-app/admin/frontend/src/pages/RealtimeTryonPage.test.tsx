import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../utils/request', () => ({ default: mocks }))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock('echarts-for-react', () => ({ default: () => <div data-testid="echarts-mock" /> }))

import RealtimeTryonPage from './RealtimeTryonPage'

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
    if (url === '/api/admin/realtime-tryon/overview') {
      return Promise.resolve({
        data: {
          currency: 'USD',
          unit: 'cent',
          timezone: 'Asia/Hong_Kong',
          day: '2026-11-22',
          next_daily_reset: '2026-11-23T00:00:00+08:00',
          config: {
            enabled: true,
            ready_to_serve: true,
            blocking_reasons: [],
            cents_per_second: 2,
          },
          providers: {
            decart: {
              config: { enabled: true, ready_to_serve: true, blocking_reasons: [] },
              active_sessions: 1,
              max_active: 1,
              daily: { limit_cents: 200, accounted_cents: 40, confirmed_cents: 12, held_unconfirmed_cents: 28, remaining_cents: 160, utilization_pct: 20, session_count: 2 },
              monthly: { limit_cents: 1000, accounted_cents: 40, confirmed_cents: 12, held_unconfirmed_cents: 28, remaining_cents: 960, utilization_pct: 4, session_count: 2 },
            },
            reactor: {
              config: { enabled: false, ready_to_serve: false, blocking_reasons: ['feature_disabled'] },
              active_sessions: 0,
              max_active: 1,
              daily: { limit_cents: 200, accounted_cents: 6, confirmed_cents: 0, held_unconfirmed_cents: 6, remaining_cents: 194, utilization_pct: 3, session_count: 1 },
              monthly: { limit_cents: 1000, accounted_cents: 6, confirmed_cents: 0, held_unconfirmed_cents: 6, remaining_cents: 994, utilization_pct: 0.6, session_count: 1 },
            },
            xmax: {
              config: { enabled: true, ready_to_serve: true, blocking_reasons: [] },
              active_sessions: 0,
              max_active: 1,
              daily: { limit_cents: 200, accounted_cents: 5, confirmed_cents: 0, held_unconfirmed_cents: 5, remaining_cents: 195, utilization_pct: 2.5, session_count: 1 },
              monthly: { limit_cents: 1000, accounted_cents: 5, confirmed_cents: 0, held_unconfirmed_cents: 5, remaining_cents: 995, utilization_pct: 0.5, session_count: 1 },
            },
          },
          active_sessions: 1,
          max_active: 1,
          starts_last_minute: 1,
          starts_per_minute: 3,
          daily: {
            limit_cents: 200,
            accounted_cents: 40,
            confirmed_cents: 12,
            held_unconfirmed_cents: 28,
            remaining_cents: 160,
            utilization_pct: 20,
            session_count: 2,
          },
          monthly: {
            limit_cents: 1000,
            accounted_cents: 40,
            confirmed_cents: 12,
            held_unconfirmed_cents: 28,
            remaining_cents: 960,
            utilization_pct: 4,
            session_count: 2,
          },
          trend_14d: [
            { date: '2026-11-22', sessions: 2, accounted_cents: 40, confirmed_cents: 12, provider_seconds: 5.4 },
          ],
          reason_distribution: [{ reason: 'timeout', count: 1 }],
          visitors_today: [{ visitor_short: 'abc1234567', sessions: 2, confirmed_sessions: 1, accounted_cents: 40, remaining_cents: 40 }],
        },
      })
    }
    if (url === '/api/admin/realtime-tryon/sessions') {
      return Promise.resolve({
        data: {
          total: 1,
          page: 1,
          size: 20,
          items: [
            {
              id: 'ticket0123456789abcdef0123456789',
              provider_key: 'decart',
              model_id: 'lucy-vton-3.6',
              visitor_short: 'abc1234567',
              budget_day: '2026-11-22',
              state: 'ended',
              raw_state: 'claimed',
              is_active: false,
              stop_requested: false,
              limit_seconds: 20,
              cents_per_second: 2,
              max_cents: 40,
              accounted_cents: 40,
              provider_seconds: null,
              provider_session_id: null,
              reason: 'usage_unconfirmed',
              created_at: '2026-11-22 18:00:00',
              ended_at: null,
              hold_remaining_seconds: 0,
            },
            {
              id: 'xmax0123456789abcdef012345678901',
              provider_key: 'xmax',
              model_id: 'x2.1',
              visitor_short: 'xyz9876543',
              budget_day: '2026-11-22',
              state: 'ended',
              raw_state: 'claimed',
              is_active: false,
              stop_requested: false,
              limit_seconds: 30,
              cents_per_second: 0,
              cents_per_minute: 10,
              credits_per_second: 1,
              max_credits: 30,
              max_cents: 5,
              accounted_cents: 5,
              provider_seconds: null,
              provider_credits: null,
              provider_session_id: 'ums-1',
              can_sync_upstream: true,
              reason: 'usage_unconfirmed',
              created_at: '2026-11-22 18:05:00',
              ended_at: null,
              hold_remaining_seconds: 0,
            },
            {
              id: 'reactor0123456789abcdef012345678',
              provider_key: 'reactor',
              model_id: 'reactor/xmax-x2-1',
              visitor_short: 'rct1122334',
              budget_day: '2026-11-22',
              state: 'ended',
              raw_state: 'claimed',
              is_active: false,
              stop_requested: false,
              limit_seconds: 30,
              cents_per_second: 0,
              cents_per_minute: 11,
              credits_per_second: 17,
              max_credits: 510,
              max_cents: 6,
              accounted_cents: 6,
              provider_seconds: null,
              provider_credits: null,
              provider_session_id: 'rsess-99',
              can_sync_upstream: true,
              reason: 'usage_unconfirmed',
              created_at: '2026-11-22 18:10:00',
              ended_at: null,
              hold_remaining_seconds: 0,
            },
          ],
        },
      })
    }
    if (url === '/api/admin/realtime-tryon/xmax/balance') {
      return Promise.resolve({
        data: {
          ok: true,
          environment: 'global',
          base_url: 'https://api.xmax.ai/open/api/v1',
          current_balance: 777,
          consumed_24h: 15,
          checked_at: '2026-11-23 16:00:00',
          message: 'ok',
        },
      })
    }
    if (url === '/api/admin/realtime-tryon/reactor/balance') {
      return Promise.resolve({
        data: {
          ok: true,
          account_id: 'acct_r_demo',
          balance: 12345,
          balance_usd: 1.2345,
          currency_code: 'USD',
          base_url: 'https://api.reactor.inc',
          checked_at: '2026-11-23 16:05:00',
          message: 'ok',
        },
      })
    }
    return Promise.resolve({ data: {} })
  })
  mocks.post.mockResolvedValue({ data: { ok: true, synced: true } })
})

afterEach(cleanup)

it('renders overview metrics, session ledger, and submits manual reconciliation', async () => {
  render(
    <MemoryRouter>
      <RealtimeTryonPage />
    </MemoryRouter>,
  )

  expect(await screen.findByText('realtimeMonitor.title')).toBeInTheDocument()
  expect((await screen.findAllByText('usage_unconfirmed')).length).toBeGreaterThanOrEqual(1)

  fireEvent.click(screen.getAllByRole('button', { name: 'realtimeMonitor.reconcile' })[0])
  const secInput = await screen.findByLabelText('realtimeMonitor.confirmedSecondsInput')
  fireEvent.change(secInput, { target: { value: '6' } })
  fireEvent.click(screen.getByRole('button', { name: 'actions.save' }))

  await waitFor(() =>
    expect(mocks.post).toHaveBeenCalledWith(
      '/api/admin/realtime-tryon/sessions/ticket0123456789abcdef0123456789/reconcile',
      expect.objectContaining({ confirmed_seconds: 6 }),
    ),
  )
})

it('queries Xmax & Reactor balances and triggers upstream usage sync', async () => {
  render(
    <MemoryRouter>
      <RealtimeTryonPage />
    </MemoryRouter>,
  )

  const balBtn = await screen.findByRole('button', { name: /realtimeMonitor\.checkXmaxBalance/ })
  fireEvent.click(balBtn)
  await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/admin/realtime-tryon/xmax/balance'))
  expect(await screen.findByText('realtimeMonitor.xmaxBalanceBanner')).toBeInTheDocument()

  const rBalBtn = screen.getByRole('button', { name: /realtimeMonitor\.checkReactorBalance/ })
  fireEvent.click(rBalBtn)
  await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/admin/realtime-tryon/reactor/balance'))
  expect(await screen.findByText('realtimeMonitor.reactorBalanceBanner')).toBeInTheDocument()

  const syncBtns = await screen.findAllByRole('button', { name: /realtimeMonitor\.syncUsage/ })
  expect(syncBtns.length).toBe(2)
  fireEvent.click(syncBtns[0])
  await waitFor(() =>
    expect(mocks.post).toHaveBeenCalledWith('/api/admin/realtime-tryon/sessions/xmax0123456789abcdef012345678901/sync-usage'),
  )
  await waitFor(() => {
    const refreshed = screen.getAllByRole('button', { name: /realtimeMonitor\.syncUsage/ })
    expect(refreshed[1]).not.toHaveClass('ant-btn-loading')
    expect(refreshed[1]).not.toBeDisabled()
  })
  fireEvent.click(screen.getAllByRole('button', { name: /realtimeMonitor\.syncUsage/ })[1])
  await waitFor(() =>
    expect(mocks.post).toHaveBeenCalledWith('/api/admin/realtime-tryon/sessions/reactor0123456789abcdef012345678/sync-usage'),
  )
}, 15000)
