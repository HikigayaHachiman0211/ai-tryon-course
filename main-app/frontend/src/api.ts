import axios, { isAxiosError } from 'axios';
import type {
  HistoryListResponse,
  ProductCatalogResponse,
  RecommendationRequest,
  RecommendationResponse,
  StyleLabAnalysisResponse,
} from './types';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
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
  if (data.ai_provider) formData.append('ai_provider', data.ai_provider);
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

  const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
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
