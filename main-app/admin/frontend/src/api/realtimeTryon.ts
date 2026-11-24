import request from '../utils/request'

export type RealtimeProviderKey = 'decart' | 'xmax' | 'reactor'
export type RealtimeProviderScope = 'all' | RealtimeProviderKey

export interface RealtimeConfig {
  provider_key?: 'decart'
  enabled: boolean
  model: string
  base_url: string
  has_api_key: boolean
  key_decrypt_ok: boolean
  require_access_code: boolean
  has_access_code: boolean
  access_code_decrypt_ok: boolean
  access_code_length: number
  origin: string
  effective_origin: string
  max_seconds: number
  default_seconds: number
  cents_per_second: number
  daily_cents: number
  monthly_cents: number
  visitor_daily_cents: number
  max_active: number
  starts_per_minute: number
  default_prompt: string
  ready_to_serve: boolean
  blocking_reasons: string[]
  last_test_status: string | null
  last_test_message: string | null
  last_test_at: string | null
  updated_at: string | null
  updated_by: string | null
}

export interface XmaxRealtimeConfig {
  provider_key: 'xmax'
  enabled: boolean
  environment: 'global' | 'china'
  base_url: string
  default_model: 'x2.1' | 'x2.1-flash'
  allowed_models: Array<'x2.1' | 'x2.1-flash'>
  camera_preset: string
  face_restoration: boolean
  has_api_key: boolean
  key_decrypt_ok: boolean
  require_access_code: boolean
  has_access_code: boolean
  access_code_decrypt_ok: boolean
  access_code_length: number
  origin: string
  effective_origin: string
  min_seconds: number
  max_seconds: number
  default_seconds: number
  credits_per_second: number
  cents_per_minute: number
  daily_cents: number
  monthly_cents: number
  visitor_daily_cents: number
  min_account_credits: number
  max_active: number
  starts_per_minute: number
  default_prompt: string
  ready_to_serve: boolean
  blocking_reasons: string[]
  last_test_status: string | null
  last_test_message: string | null
  last_test_at: string | null
  updated_at: string | null
  updated_by: string | null
}

export type ReactorModelId = 'reactor/xmax-x2-1' | 'xmax/x2'

export interface ReactorRealtimeConfig {
  provider_key: 'reactor'
  enabled: boolean
  base_url: string
  default_model: ReactorModelId
  allowed_models: ReactorModelId[]
  has_api_key: boolean
  key_decrypt_ok: boolean
  require_access_code: boolean
  has_access_code: boolean
  access_code_decrypt_ok: boolean
  access_code_length: number
  origin: string
  effective_origin: string
  min_seconds: number
  max_seconds: number
  default_seconds: number
  credits_per_second: number
  cents_per_minute: number
  daily_cents: number
  monthly_cents: number
  visitor_daily_cents: number
  min_account_credits: number
  max_active: number
  starts_per_minute: number
  default_prompt: string
  ready_to_serve: boolean
  blocking_reasons: string[]
  last_test_status: string | null
  last_test_message: string | null
  last_test_at: string | null
  updated_at: string | null
  updated_by: string | null
}

export interface RealtimeConfigUpdatePayload {
  enabled?: boolean
  api_key?: string
  clear_api_key?: boolean
  require_access_code?: boolean
  access_code?: string
  clear_access_code?: boolean
  origin?: string
  max_seconds?: number
  default_seconds?: number
  cents_per_second?: number
  daily_cents?: number
  monthly_cents?: number
  visitor_daily_cents?: number
  max_active?: number
  starts_per_minute?: number
  default_prompt?: string
}

export interface XmaxRealtimeConfigUpdatePayload {
  enabled?: boolean
  api_key?: string
  clear_api_key?: boolean
  environment?: 'global' | 'china'
  base_url?: string
  default_model?: 'x2.1' | 'x2.1-flash'
  allowed_models?: Array<'x2.1' | 'x2.1-flash'>
  camera_preset?: string
  face_restoration?: boolean
  require_access_code?: boolean
  access_code?: string
  clear_access_code?: boolean
  origin?: string
  min_seconds?: number
  max_seconds?: number
  default_seconds?: number
  credits_per_second?: number
  cents_per_minute?: number
  daily_cents?: number
  monthly_cents?: number
  visitor_daily_cents?: number
  min_account_credits?: number
  max_active?: number
  starts_per_minute?: number
  default_prompt?: string
}

export interface ReactorRealtimeConfigUpdatePayload {
  enabled?: boolean
  api_key?: string
  clear_api_key?: boolean
  base_url?: string
  default_model?: ReactorModelId
  allowed_models?: ReactorModelId[]
  require_access_code?: boolean
  access_code?: string
  clear_access_code?: boolean
  origin?: string
  min_seconds?: number
  max_seconds?: number
  default_seconds?: number
  credits_per_second?: number
  cents_per_minute?: number
  daily_cents?: number
  monthly_cents?: number
  visitor_daily_cents?: number
  min_account_credits?: number
  max_active?: number
  starts_per_minute?: number
  default_prompt?: string
}

export interface RealtimeTestResult {
  success: boolean
  status_code: number
  latency_ms: number
  message: string
  account_id?: string | null
  current_balance?: number | null
  balance_usd?: number | null
}

export interface OfficialRealtimeDataResponse {
  ok: boolean
  provider: RealtimeProviderKey
  source: 'live_api' | 'live_api+official_catalog' | 'official_catalog' | 'catalog_fallback'
  fetched_at: string
  summary: string
  warning?: string | null
  official_rates: Record<string, unknown>
  account_info: {
    account_id?: string
    balance?: number
    balance_usd?: number
    currency_code?: string
    currency?: string
    environment?: string
    token_probe?: string
    quotas?: Record<string, unknown>
  }
  suggested_fields: Record<string, unknown>
}

export interface EmergencyStopResult {
  ok: boolean
  provider?: RealtimeProviderScope
  disabled: boolean
  canceled_reserved: number
  signaled_active: number
}

export interface RealtimeBudgetWindow {
  limit_cents: number
  accounted_cents: number
  confirmed_cents: number
  held_unconfirmed_cents: number
  remaining_cents: number
  utilization_pct: number
  session_count: number
}

export interface ProviderOverviewSnapshot {
  config: RealtimeConfig | XmaxRealtimeConfig | ReactorRealtimeConfig
  active_sessions: number
  max_active: number
  daily: RealtimeBudgetWindow
  monthly: RealtimeBudgetWindow
}

export interface RealtimeTrendPoint {
  date: string
  sessions: number
  accounted_cents: number
  confirmed_cents: number
  provider_seconds: number
}

export interface RealtimeVisitorUsage {
  visitor_short: string
  sessions: number
  confirmed_sessions: number
  accounted_cents: number
  remaining_cents: number
}

export interface RealtimeOverview {
  currency: string
  unit: string
  timezone: string
  provider?: RealtimeProviderScope
  day: string
  next_daily_reset: string
  config: RealtimeConfig | XmaxRealtimeConfig | ReactorRealtimeConfig
  providers?: {
    decart?: ProviderOverviewSnapshot
    reactor?: ProviderOverviewSnapshot
    xmax?: ProviderOverviewSnapshot
  }
  active_sessions: number
  max_active: number
  starts_last_minute: number
  starts_per_minute: number
  daily: RealtimeBudgetWindow
  monthly: RealtimeBudgetWindow
  trend_14d: RealtimeTrendPoint[]
  reason_distribution: Array<{ reason: string; count: number }>
  visitors_today: RealtimeVisitorUsage[]
}

export interface RealtimeSessionItem {
  id: string
  provider_key?: RealtimeProviderKey
  model_id?: string | null
  visitor_short: string
  budget_day: string
  state: string
  raw_state: string
  is_active: boolean
  stop_requested: boolean
  limit_seconds: number
  cents_per_second: number
  cents_per_minute?: number | null
  credits_per_second?: number | null
  max_credits?: number | null
  max_cents: number
  accounted_cents: number
  provider_seconds: number | null
  provider_credits?: number | null
  provider_session_id: string | null
  provider_temp_key_uid?: string | null
  can_sync_upstream?: boolean
  reason: string | null
  created_at: string
  ended_at: string | null
  hold_remaining_seconds: number
}

export interface RealtimeSessionListResponse {
  total: number
  page: number
  size: number
  items: RealtimeSessionItem[]
}

export interface XmaxAccountBalance {
  ok: boolean
  environment: 'global' | 'china'
  base_url: string
  current_balance: number
  consumed_24h: number | null
  checked_at: string
  message: string
}

export interface ReactorAccountBalance {
  ok: boolean
  account_id: string
  balance: number
  balance_usd: number
  currency_code: string
  quotas?: Record<string, unknown>
  base_url: string
  checked_at: string
  message: string
}

export function getRealtimeConfig() {
  return request.get<RealtimeConfig>('/api/ai-config/realtime')
}

export function updateRealtimeConfig(data: RealtimeConfigUpdatePayload) {
  return request.put<RealtimeConfig>('/api/ai-config/realtime', data)
}

export function generateRealtimeAccessCode() {
  return request.post<{ access_code: string; access_code_length: number; config: RealtimeConfig }>(
    '/api/ai-config/realtime/generate-code',
  )
}

export function testRealtimeConnection() {
  return request.post<RealtimeTestResult>('/api/ai-config/realtime/test')
}

export function getXmaxRealtimeConfig() {
  return request.get<XmaxRealtimeConfig>('/api/ai-config/realtime/xmax')
}

export function updateXmaxRealtimeConfig(data: XmaxRealtimeConfigUpdatePayload) {
  return request.put<XmaxRealtimeConfig>('/api/ai-config/realtime/xmax', data)
}

export function generateXmaxRealtimeAccessCode() {
  return request.post<{ access_code: string; access_code_length: number; config: XmaxRealtimeConfig }>(
    '/api/ai-config/realtime/xmax/generate-code',
  )
}

export function testXmaxRealtimeConnection() {
  return request.post<RealtimeTestResult>('/api/ai-config/realtime/xmax/test')
}

export function emergencyStopXmaxRealtime() {
  return request.post<EmergencyStopResult>('/api/ai-config/realtime/xmax/emergency-stop')
}

export function getReactorRealtimeConfig() {
  return request.get<ReactorRealtimeConfig>('/api/ai-config/realtime/reactor')
}

export function updateReactorRealtimeConfig(data: ReactorRealtimeConfigUpdatePayload) {
  return request.put<ReactorRealtimeConfig>('/api/ai-config/realtime/reactor', data)
}

export function generateReactorRealtimeAccessCode() {
  return request.post<{ access_code: string; access_code_length: number; config: ReactorRealtimeConfig }>(
    '/api/ai-config/realtime/reactor/generate-code',
  )
}

export function testReactorRealtimeConnection() {
  return request.post<RealtimeTestResult>('/api/ai-config/realtime/reactor/test')
}

export function emergencyStopReactorRealtime() {
  return request.post<EmergencyStopResult>('/api/ai-config/realtime/reactor/emergency-stop')
}

export function fetchRealtimeOfficialData(
  provider: RealtimeProviderKey,
  payload?: { base_url?: string; environment?: string; api_key?: string },
) {
  return request.post<OfficialRealtimeDataResponse>(
    `/api/ai-config/realtime/${provider}/fetch-official`,
    payload ?? {},
  )
}

export function emergencyStopRealtime(provider?: RealtimeProviderScope) {
  return request.post<EmergencyStopResult>(
    '/api/admin/realtime-tryon/emergency-stop',
    undefined,
    provider && provider !== 'all' ? { params: { provider } } : undefined,
  )
}

export function getRealtimeOverview(provider?: RealtimeProviderScope) {
  return request.get<RealtimeOverview>(
    '/api/admin/realtime-tryon/overview',
    provider && provider !== 'all' ? { params: { provider } } : undefined,
  )
}

export function listRealtimeSessions(params: {
  page?: number
  size?: number
  provider?: RealtimeProviderScope
  state?: string
  reason?: string
  budget_day?: string
  search?: string
}) {
  return request.get<RealtimeSessionListResponse>('/api/admin/realtime-tryon/sessions', { params })
}

export function forceStopRealtimeSession(sessionId: string) {
  return request.post<{ ok: boolean; session: RealtimeSessionItem }>(
    `/api/admin/realtime-tryon/sessions/${encodeURIComponent(sessionId)}/stop`,
  )
}

export function syncRealtimeSessionUsage(sessionId: string) {
  return request.post<{ ok: boolean; synced: boolean; session: RealtimeSessionItem }>(
    `/api/admin/realtime-tryon/sessions/${encodeURIComponent(sessionId)}/sync-usage`,
  )
}

export function reconcileRealtimeSession(
  sessionId: string,
  payload: { confirmed_seconds?: number; confirmed_credits?: number; provider_session_id?: string },
) {
  return request.post<{ ok: boolean; session: RealtimeSessionItem }>(
    `/api/admin/realtime-tryon/sessions/${encodeURIComponent(sessionId)}/reconcile`,
    payload,
  )
}

export function getXmaxAccountBalance() {
  return request.get<XmaxAccountBalance>('/api/admin/realtime-tryon/xmax/balance')
}

export function getReactorAccountBalance() {
  return request.get<ReactorAccountBalance>('/api/admin/realtime-tryon/reactor/balance')
}
