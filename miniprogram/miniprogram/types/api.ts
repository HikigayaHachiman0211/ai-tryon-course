export type AppLocale = 'zh-CN' | 'en' | 'ja';

export interface LocalizedText {
  title: string;
  styleType: string;
  colorFamily: string;
  bodyFit: string;
  styleFeatures: string[];
  functionFeatures: string[];
  sizeNotes: string;
}

export interface RecommendationRequest {
  color_preference: string;
  brand_preference?: string;
  gender?: string;
  price_min?: number;
  price_max?: number;
  mbti?: string;
  size?: string;
  style_preference?: string;
  ai_provider?: string;
  vision_provider?: 'mimo' | 'gemini' | 'deepseek' | 'opencode_go' | 'auto';
}

export interface RadarData {
  dimension: string;
  code?: 'style' | 'color' | 'size' | 'brand' | 'gender' | 'price' | 'personality';
  label?: string;
  score: number;
}

export interface ProfileInference {
  resolved_size: string;
  resolved_style: string;
  body_shape: string;
  size_source: string;
  style_source: string;
  reasoning: string;
  gemini_model: string;
  gemini_used: boolean;
  ai_provider: string;
  vision_provider?: string;
  vision_provider_used?: string;
  mimo_model?: string;
  mimo_used?: boolean;
  mimo_multimodal_used?: boolean;
  ai_attempted?: boolean;
  rule_fallback_used?: boolean;
  provider_error_summary?: string | null;
  display?: {
    size: string;
    style: string;
    bodyShape: string;
  };
}

export interface ProductCardBase {
  id: number;
  product_key?: string;
  locale?: AppLocale;
  canonical?: {
    id: number;
    product_key: string;
    price: number;
    image_url: string;
    product_url?: string | null;
    platform?: string;
    gender?: string;
  };
  display?: LocalizedText;
  title: string;
  price: number;
  image_url: string;
  brand?: string | null;
  platform?: string | null;
  product_url?: string | null;
  style_type: string;
  color_family: string;
  body_fit: string;
  style_features: string[];
  function_features: string[];
  size_tags: string[];
  size_notes?: string;
}

export interface RecommendedItem extends ProductCardBase {
  total_score: number;
  brand_score?: number | null;
  score_breakdown: Record<string, number>;
  radar_chart: RadarData[];
  reason: string;
}

export interface ProductCatalogItem extends ProductCardBase {
  product_gender: string;
  gender_label: string;
  is_child_product: boolean;
}

export interface RecommendationResponse {
  locale?: AppLocale;
  filters: {
    price_min: number | null;
    price_max: number | null;
    catalog_total: number;
    matched_after_price_filter: number;
    matched_after_gender_filter?: number;
    user_gender?: string | null;
    brand_preference?: string | null;
    gender_fallback?: boolean;
  };
  inference: ProfileInference;
  items: RecommendedItem[];
  message?: string;
  user_photo_url?: string;
}

export interface ProductCatalogResponse {
  locale?: AppLocale;
  items: ProductCatalogItem[];
  total: number;
  offset: number;
  limit: number;
  mode: string;
  user_gender?: string | null;
  gender_fallback?: boolean;
}

export interface StyleLabAnalysisResponse {
  locale?: AppLocale;
  product: ProductCatalogItem;
  inference: ProfileInference;
  user_photo_url?: string;
  analysis: {
    total_score: number;
    brand_score?: number | null;
    score_breakdown: Record<string, number>;
    radar_chart: RadarData[];
    reason: string;
    styling_advice: string[];
    budget_note?: string | null;
    brand_note?: string | null;
    gender_note?: string | null;
    personality_note?: string | null;
  };
}

export interface HistoryEntry {
  id: string;
  timestamp: string;
  type: 'recommend' | 'style-lab';
  summary: string;
  thumbnail_url: string | null;
  item_count: number;
  total_score: number | null;
}

export interface HistoryListResponse {
  items: HistoryEntry[];
  total: number;
  locale?: AppLocale;
}

export interface AssistantPublicConfig {
  enabled: boolean;
  welcome_message: string;
  features: {
    text_chat: boolean;
    auto_fill: boolean;
    auto_submit: boolean;
    style_lab_guide: boolean;
    tryon_guide: boolean;
  };
  defaults: {
    ai_provider: string;
    vision_provider?: string;
    mimo_model: string;
  };
}

export interface RecommendFormPatch {
  color_preference?: string;
  brand_preference?: string;
  gender?: string;
  price_min?: number | null;
  price_max?: number | null;
  mbti?: string;
  size?: string;
  style_preference?: string;
  ai_provider?: string;
  vision_provider?: string;
  mimo_model?: string;
  gemini_model?: string;
  deepseek_model?: string;
  opencode_go_model?: string;
}

export interface AssistantAction {
  type: string;
  form_patch?: RecommendFormPatch;
  confidence?: number;
  requires_confirmation?: boolean;
}

export interface AssistantDebugInfo {
  provider: string;
  fallback_used: boolean;
  latency_ms: number;
}

export interface AssistantChatRequest {
  session_id: string;
  message: string;
  page_context?: {
    view?: string;
    current_form?: Record<string, unknown>;
  };
  locale?: AppLocale;
}

export interface AssistantChatResponse {
  reply: string;
  intent: string;
  action: AssistantAction;
  sources: string[];
  debug: AssistantDebugInfo;
}

export interface AssistantChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  action?: AssistantAction;
  intent?: string;
  debug?: AssistantDebugInfo;
  timestamp: number;
  patchLabels?: Array<{ key: string; value: string }>;
}

export interface KnowledgeSearchItem {
  id: number;
  question: string;
  answer: string;
  score: number;
}

export interface KnowledgeSearchResponse {
  items: KnowledgeSearchItem[];
  total: number;
  locale?: AppLocale;
}

export interface VoiceCatalogItem {
  id: string;
  name: string;
  display_name?: string;
  display_description?: string;
  source?: string;
}

export interface VoicePublicConfig {
  asr_enabled: boolean;
  tts_enabled: boolean;
  voice_clone_enabled: boolean;
  asr_disabled_reason?: string;
  tts_disabled_reason?: string;
  default_asr_provider?: string;
  default_asr_model?: string;
  default_tts_provider?: string;
  default_tts_model?: string;
  default_voice: string;
  available_voices: string[];
  published_clone_voices: Array<{
    id: string;
    name: string;
    description?: string;
    display_name?: string;
    display_description?: string;
  }>;
  asr_languages?: string[];
  max_record_seconds?: number;
  hard_max_record_seconds?: number;
  max_audio_base64_mb?: number;
  supported_audio_formats?: string[];
  default_language?: string;
  max_tts_text_length?: number;
  locale?: AppLocale;
  available_voice_catalog?: VoiceCatalogItem[];
}

export interface ASRResult {
  success: boolean;
  text: string;
  normalized_text?: string;
  provider?: string;
  model?: string;
  language?: string;
  duration_ms?: number;
  latency_ms?: number;
  error?: { code: string; message: string };
  locale?: string;
  speech_language?: string;
}

export interface TTSResult {
  success: boolean;
  audio_url?: string;
  audio_base64?: string;
  format: string;
  voice: string;
  provider?: string;
  model?: string;
  error?: { code: string; message: string };
  locale?: string;
}

export type CallState =
  | 'idle'
  | 'ready'
  | 'recording'
  | 'recognizing'
  | 'thinking'
  | 'speaking'
  | 'muted'
  | 'error'
  | 'ended';

export interface VoiceCallTurn {
  id: string;
  userText?: string;
  assistantText?: string;
  startedAt: number;
  endedAt?: number;
  error?: string;
}

export interface VoiceSettings {
  autoPlayTts: boolean;
  autoSendAsr: boolean;
  voice: string;
  voiceSource: 'preset' | 'clone';
  cloneVoiceId: string;
  tonePreset: 'natural' | 'anime' | 'gentle' | 'professional';
  asrLanguage: 'zh' | 'en' | 'ja' | 'auto';
  volume: number;
}

export interface TryOnModelCapabilities {
  protocol: string;
  supports_aspect_ratio: boolean;
  aspect_ratio_options: string[];
  supports_image_size: boolean;
  image_size_options: string[];
  supports_quality: boolean;
  quality_options: string[];
  supports_temperature: boolean;
  supports_seed: boolean;
}

export interface TryOnModelEntry {
  id: string;
  label: string;
  preset_key: string;
  protocol: string;
  speed_tier: string;
  badge: string;
  max_concurrency: number;
  is_default: boolean;
  capabilities: TryOnModelCapabilities;
}

export interface TryOnToTokensProfile {
  id: string;
  scope?: string;
  label: string;
  enabled: boolean;
  configured: boolean;
  default_model?: string;
  models?: string[];
}

export interface TryOnProviderCatalog {
  key: string;
  label: string;
  protocol_summary: string;
  enabled: boolean;
  configured: boolean;
  is_default: boolean;
  default_model_id: string;
  models: TryOnModelEntry[];
  totokens_profiles?: TryOnToTokensProfile[];
}

export interface RuntimeStatusResponse {
  tryon_enabled: boolean;
  configured: boolean;
  available_models: string[];
  config_source: string;
  provider_key?: string;
  relay_enabled?: boolean;
  relay_configured?: boolean;
  chatgpt_configured?: boolean;
  chatgpt_model?: string;
  model_labels?: Record<string, string>;
  providers?: TryOnProviderCatalog[];
}

export interface TryOnUploadResponse {
  filename: string;
  cloud_url?: string;
  url?: string;
  task_token?: string;
  ok?: boolean;
  role?: string;
  source_type?: string;
}

export interface TryOnSubmitResponse {
  task_id: string;
  status: string;
  task_token?: string;
  idempotent_reused?: boolean;
}

export interface TryOnTaskResponse {
  locale?: string;
  status: string;
  status_code?: string;
  message_code?: string | null;
  progress: number;
  message: string;
  result_url?: string | null;
  result_cloud_url?: string | null;
  result_display_url?: string | null;
  result_data_url?: string | null;
  freedom?: number;
  logs?: string[];
  error?: string | null;
  error_detail?: string | null;
  error_code?: string | null;
  created_at?: number;
  provider?: string;
  model_id?: string;
}

export interface TryOnHandoffPayload {
  productId: string | number;
  productTitle: string;
  productPrice?: number;
  garmentImageUrl: string;
  styleType?: string;
  colorFamily?: string;
  sizeHint?: string;
  reason?: string;
  userPhotoLocalPath?: string;
  userPhotoPreviewUrl?: string;
  userPhotoRemoteUrl?: string;
}

export interface VideoParamSpec {
  name: string;
  type: 'string' | 'text' | 'enum' | 'boolean' | 'integer' | 'number' | 'image' | 'images' | 'video' | 'videos' | 'audio' | 'audios';
  label?: string;
  description?: string;
  required?: boolean;
  default?: unknown;
  options?: Array<string | number | boolean>;
  min?: number;
  max?: number;
  maxItems?: number;
  maxLength?: number;
}

export interface VideoModelProviderOption {
  provider: string;
  params?: VideoParamSpec[];
}

export interface VideoModelItem {
  slug: string;
  name?: string;
  type?: string;
  provider?: string;
  params?: VideoParamSpec[];
  providers?: VideoModelProviderOption[];
}

export interface VideoConfigResponse {
  enabled: boolean;
  configured: boolean;
  task_token?: string;
  sandbox?: boolean;
  project_id?: string;
  source?: string;
  poll_interval_ms?: number;
}

export interface VideoQuoteResponse {
  price_usd?: number;
  credits?: number;
  currency?: string;
  estimated_seconds?: number;
  [key: string]: unknown;
}

export interface VideoTaskResponse {
  id: string;
  upstream_id?: string | null;
  model: string;
  provider?: string;
  status: 'submitting' | 'queued' | 'processing' | 'succeeded' | 'failed' | 'unknown' | string;
  outputs?: string[];
  download_urls?: string[];
  error?: string | null;
  error_code?: string | null;
  price_usd?: number | null;
  credits?: number | null;
  created_at?: number;
  completed_at?: number | null;
}
