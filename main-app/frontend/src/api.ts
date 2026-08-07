import axios, { isAxiosError } from 'axios';
import type {
  HistoryListResponse,
  ProductCatalogResponse,
  RecommendationRequest,
  RecommendationResponse,
  StyleLabAnalysisResponse,
} from './types';

const resolveApiBaseURL = (): string => {
  const configuredBaseURL = import.meta.env.VITE_API_BASE_URL?.trim();
  const isHttpURL = /^https?:\/\//i.test(configuredBaseURL || '');
  const isSameOriginPath = configuredBaseURL?.startsWith('/');

  if (configuredBaseURL && (isHttpURL || isSameOriginPath)) {
    return configuredBaseURL;
  }

  return import.meta.env.PROD ? '/' : 'http://localhost:8000';
};

const API_BASE_URL = resolveApiBaseURL();

const api = axios.create({
  baseURL: API_BASE_URL,
});

export const getHealth = async () => {
  const res = await api.get('/health');
  return res.data;
};

const appendProfileFields = (formData: FormData, data: RecommendationRequest) => {
  if (data.photo) formData.append('photo', data.photo);
  formData.append('color_preference', data.color_preference);
  if (data.brand_preference) formData.append('brand_preference', data.brand_preference);
  if (data.gender) formData.append('gender', data.gender);
  if (data.price_min !== undefined) formData.append('price_min', data.price_min.toString());
  if (data.price_max !== undefined) formData.append('price_max', data.price_max.toString());
  if (data.mbti) formData.append('mbti', data.mbti);
  if (data.size) formData.append('size', data.size);
  if (data.style_preference) formData.append('style_preference', data.style_preference);
  if (data.gemini_api_key) formData.append('gemini_api_key', data.gemini_api_key);
  if (data.gemini_model) formData.append('gemini_model', data.gemini_model);
  if (data.deepseek_api_key) formData.append('deepseek_api_key', data.deepseek_api_key);
  if (data.deepseek_model) formData.append('deepseek_model', data.deepseek_model);
  if (data.mimo_api_key) formData.append('mimo_api_key', data.mimo_api_key);
  if (data.mimo_model) formData.append('mimo_model', data.mimo_model);
  if (data.ai_provider) formData.append('ai_provider', data.ai_provider);
  if (data.vision_provider) formData.append('vision_provider', data.vision_provider);
};

export const getRecommend = async (data: RecommendationRequest): Promise<RecommendationResponse> => {
  const formData = new FormData();
  appendProfileFields(formData, data);

  const res = await api.post('/api/recommend', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return res.data;
};

export const getDebugErrorCodes = async () => {
  try {
    const res = await api.get('/api/debug/error-codes');
    return res.data;
  } catch (err: unknown) {
    if (isAxiosError(err) && err.response?.status === 404) {
      const res = await api.get('/debug/error-codes');
      return res.data;
    }
    throw err;
  }
};

export const getDebugRecentErrors = async (limit = 50) => {
  const res = await api.get('/api/debug/errors/recent', { params: { limit } });
  return res.data;
};

export const getCatalogProducts = async (params: {
  query?: string;
  gender?: string;
  platform?: string;
  mode?: string;
  offset?: number;
  limit?: number;
  price_min?: number;
  price_max?: number;
}): Promise<ProductCatalogResponse> => {
  const res = await api.get('/api/products', { params });
  return res.data;
};

export const analyzeStyleLab = async (
  productId: number,
  data: RecommendationRequest,
): Promise<StyleLabAnalysisResponse> => {
  const formData = new FormData();
  formData.append('product_id', String(productId));
  appendProfileFields(formData, data);

  const res = await api.post('/api/style-lab/analyze', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return res.data;
};

export const buildImageURL = (path: string) => {
  if (!path) {
    return '';
  }

  if (/^https?:\/\//i.test(path)) {
    return path;
  }

  const baseURL = API_BASE_URL;
  if (baseURL === '/' || baseURL === '') {
    if (typeof window !== 'undefined') {
      return new URL(path, window.location.origin).toString();
    }
    return path;
  }

  return new URL(path, baseURL.endsWith('/') ? baseURL : `${baseURL}/`).toString();
};

export const getHistory = async (limit = 50): Promise<HistoryListResponse> => {
  const res = await api.get('/api/history', { params: { limit } });
  return res.data;
};

export const getHistoryDetail = async (resultId: string) => {
  const res = await api.get(`/api/history/${resultId}`);
  return res.data;
};

// ---- Assistant API ----

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
    vision_provider: string;
    mimo_model: string;
  };
}

export interface AssistantPageContext {
  view?: string;
  current_form?: Record<string, unknown>;
}

export interface AssistantChatRequest {
  session_id: string;
  message: string;
  page_context?: AssistantPageContext;
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

export interface AssistantChatResponse {
  reply: string;
  intent: string;
  action: AssistantAction;
  sources: string[];
  debug: AssistantDebugInfo;
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
}

export const getAssistantConfig = async (): Promise<AssistantPublicConfig> => {
  const res = await api.get('/api/assistant/config/public');
  return res.data;
};

export const postAssistantChat = async (data: AssistantChatRequest): Promise<AssistantChatResponse> => {
  const res = await api.post('/api/assistant/chat', data);
  return res.data;
};

export const searchAssistantKnowledge = async (q: string, limit = 5): Promise<KnowledgeSearchResponse> => {
  const res = await api.get('/api/assistant/knowledge/search', { params: { q, limit } });
  return res.data;
};
