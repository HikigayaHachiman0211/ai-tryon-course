import type { AppLocale } from './i18n/locale';

export type { AppLocale } from './i18n/locale';

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
  photo?: File | null;
  color_preference: string;
  brand_preference?: string;
  gender?: string;
  price_min?: number;
  price_max?: number;
  mbti?: string;
  size?: string;
  style_preference?: string;
  gemini_api_key?: string;
  gemini_model?: string;
  deepseek_api_key?: string;
  deepseek_model?: string;
  mimo_api_key?: string;
  mimo_model?: string;
  opencode_go_api_key?: string;
  opencode_go_model?: string;
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

export interface ErrorResponse {
  success: boolean;
  error: {
    code: string;
    message: string;
    request_id: string;
    details: unknown;
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
}
