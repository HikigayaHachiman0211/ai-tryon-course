import { getEndpointConfig } from '../config/env';
import { getLocale } from '../i18n';
import type {
  AppLocale,
  HistoryListResponse,
  ProductCatalogItem,
  ProductCatalogResponse,
  RecommendationRequest,
  RecommendationResponse,
  StyleLabAnalysisResponse,
} from '../types/api';
import { requestFormUrlEncoded, requestJson, uploadMultipart } from '../utils/request';
import { joinUrl } from '../utils/url';

function mainUrl(path: string): string {
  return joinUrl(getEndpointConfig().mainApiBaseUrl, path);
}

function buildProfileFields(
  req: RecommendationRequest,
  locale: AppLocale = getLocale(),
): Record<string, string | number | boolean | null | undefined> {
  return {
    locale,
    color_preference: req.color_preference,
    brand_preference: req.brand_preference,
    gender: req.gender,
    price_min: req.price_min,
    price_max: req.price_max,
    mbti: req.mbti,
    size: req.size,
    style_preference: req.style_preference,
    ai_provider: req.ai_provider,
    vision_provider: req.vision_provider,
  };
}

export function getHealth(): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>({
    url: mainUrl('/health'),
    method: 'GET',
    timeout: 8000,
  });
}

export function getRecommend(
  data: RecommendationRequest,
  photoLocalPath?: string,
): Promise<RecommendationResponse> {
  const fields = buildProfileFields(data);
  if (photoLocalPath) {
    return uploadMultipart<RecommendationResponse>({
      url: mainUrl('/api/recommend'),
      filePath: photoLocalPath,
      name: 'photo',
      formData: fields,
      timeout: 120000,
    });
  }
  return requestFormUrlEncoded<RecommendationResponse>({
    url: mainUrl('/api/recommend'),
    fields,
    timeout: 120000,
  });
}

export function getCatalogProducts(params: {
  query?: string;
  gender?: string;
  platform?: string;
  mode?: string;
  offset?: number;
  limit?: number;
  price_min?: number;
  price_max?: number;
}): Promise<ProductCatalogResponse> {
  return requestJson<ProductCatalogResponse>({
    url: mainUrl('/api/products'),
    method: 'GET',
    query: {
      ...params,
      locale: getLocale(),
    },
  });
}

export function analyzeStyleLab(
  productId: number,
  data: RecommendationRequest,
  photoLocalPath?: string,
): Promise<StyleLabAnalysisResponse> {
  const fields = {
    product_id: productId,
    ...buildProfileFields(data),
  };
  if (photoLocalPath) {
    return uploadMultipart<StyleLabAnalysisResponse>({
      url: mainUrl('/api/style-lab/analyze'),
      filePath: photoLocalPath,
      name: 'photo',
      formData: fields,
      timeout: 120000,
    });
  }
  return requestFormUrlEncoded<StyleLabAnalysisResponse>({
    url: mainUrl('/api/style-lab/analyze'),
    fields,
    timeout: 120000,
  });
}

export function localizeResult<T extends RecommendationResponse | StyleLabAnalysisResponse | ProductCatalogItem>(
  kind: 'recommend' | 'style-lab' | 'product',
  result: T,
  locale: AppLocale,
): Promise<T> {
  return requestJson<T>({
    url: mainUrl('/api/localize-result'),
    method: 'POST',
    data: { kind, result, locale },
  });
}

export function getHistory(limit = 50): Promise<HistoryListResponse> {
  return requestJson<HistoryListResponse>({
    url: mainUrl('/api/history'),
    method: 'GET',
    query: { limit, locale: getLocale() },
  });
}

export function getHistoryDetail(resultId: string): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>({
    url: mainUrl(`/api/history/${encodeURIComponent(resultId)}`),
    method: 'GET',
    query: { locale: getLocale() },
  });
}
