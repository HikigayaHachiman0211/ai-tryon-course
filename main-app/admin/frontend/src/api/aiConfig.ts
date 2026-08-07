import request from '../utils/request'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AIAPIProvider {
  id: number
  provider_key: string
  display_name: string
  category: string
  enabled: boolean
  is_default: boolean
  base_url: string | null
  api_key_masked: string
  has_api_key: boolean
  auth_type: string
  auth_header_name: string | null
  default_model: string | null
  model_options: string[] | null
  timeout_seconds: number
  retry_count: number
  rate_limit_per_minute: number | null
  daily_quota_limit: number | null
  cost_note: string | null
  notes: string | null
  last_test_status: string | null
  last_test_message: string | null
  last_test_at: string | null
  created_at: string | null
  updated_at: string | null
  updated_by: string | null
}

export interface AIFeatureConfig {
  id: number
  feature_key: string
  enabled: boolean
  default_provider: string
  fallback_order: string[] | null
  default_model: string | null
  config: Record<string, unknown> | null
  created_at: string | null
  updated_at: string | null
  updated_by: string | null
}

export interface ProviderCreatePayload {
  provider_key: string
  display_name: string
  category?: string
  enabled?: boolean
  is_default?: boolean
  base_url?: string
  api_key?: string
  auth_type?: string
  auth_header_name?: string
  default_model?: string
  model_options?: string[]
  timeout_seconds?: number
  retry_count?: number
  rate_limit_per_minute?: number
  daily_quota_limit?: number
  cost_note?: string
  notes?: string
}

export interface ProviderUpdatePayload extends Partial<ProviderCreatePayload> {
  clear_api_key?: boolean
}

export interface FeatureUpdatePayload {
  enabled?: boolean
  default_provider?: string
  fallback_order?: string[]
  default_model?: string
  config?: Record<string, unknown>
}

export interface TestResult {
  success: boolean
  latency_ms: number
  status_code: number
  message: string
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

export function getProviders() {
  return request.get<AIAPIProvider[]>('/api/ai-config/providers')
}

export function createProvider(data: ProviderCreatePayload) {
  return request.post<AIAPIProvider>('/api/ai-config/providers', data)
}

export function updateProvider(id: number, data: ProviderUpdatePayload) {
  return request.put<AIAPIProvider>(`/api/ai-config/providers/${id}`, data)
}

export function deleteProvider(id: number) {
  return request.delete(`/api/ai-config/providers/${id}`)
}

export function testProvider(id: number) {
  return request.post<TestResult>(`/api/ai-config/providers/${id}/test`)
}

export function getFeatures() {
  return request.get<AIFeatureConfig[]>('/api/ai-config/features')
}

export function updateFeature(key: string, data: FeatureUpdatePayload) {
  return request.put<AIFeatureConfig>(`/api/ai-config/features/${key}`, data)
}

export function getPublicRuntime() {
  return request.get('/api/ai-config/public-runtime')
}

// ---------------------------------------------------------------------------
// Tryon-specific types and API calls
// ---------------------------------------------------------------------------

export interface TryonAIConfig {
  feature_key: string
  enabled: boolean
  provider_key: string
  provider_enabled: boolean
  has_api_key: boolean
  key_status: string
  flash_model: string
  pro_model: string
  timeout_seconds: number
  retry_count: number
  updated_at: string | null
  updated_by: string | null
  last_test_status: string | null
  last_test_message: string | null
  last_test_at: string | null
}

export interface TryonAIConfigUpdatePayload {
  enabled?: boolean
  api_key?: string
  clear_api_key?: boolean
  flash_model?: string
  pro_model?: string
  timeout_seconds?: number
  retry_count?: number
}

export interface TryonAIConfigTestResult {
  success: boolean
  latency_ms: number
  status_code: number
  message: string
  model_check: {
    flash_found: boolean
    pro_found: boolean
  }
}

export function getTryonAIConfig() {
  return request.get<TryonAIConfig>('/api/ai-config/tryon')
}

export function updateTryonAIConfig(data: TryonAIConfigUpdatePayload) {
  return request.put<TryonAIConfig>('/api/ai-config/tryon', data)
}

export function testTryonAIConfig() {
  return request.post<TryonAIConfigTestResult>('/api/ai-config/tryon/test')
}
