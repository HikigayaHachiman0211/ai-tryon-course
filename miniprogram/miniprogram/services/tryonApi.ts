import { getEndpointConfig } from '../config/env';
import { getLocale } from '../i18n';
import type {
  ProductCatalogResponse,
  RuntimeStatusResponse,
  TryOnSubmitResponse,
  TryOnTaskResponse,
  TryOnUploadResponse,
} from '../types/api';
import {
  downloadTempFile,
  requestFormUrlEncoded,
  requestJson,
  uploadMultipart,
} from '../utils/request';
import { getVisitorToken, setVisitorToken } from '../utils/storage';
import { buildTryOnMediaUrl, joinUrl } from '../utils/url';
import { getCatalogProducts } from './mainApi';

function tryonUrl(path: string): string {
  return joinUrl(getEndpointConfig().tryonApiBaseUrl, path);
}

export function workbenchHeaders(extra?: Record<string, string>): Record<string, string> {
  return {
    'X-Task-Token': getVisitorToken(),
    'Accept-Language': getLocale(),
    ...(extra || {}),
  };
}

function captureToken(res: { task_token?: string } | null | undefined): void {
  if (res && res.task_token) {
    setVisitorToken(res.task_token);
  }
}

export function resolveTryOnAssetUrl(path: string | null | undefined): string {
  return buildTryOnMediaUrl(path, getEndpointConfig().tryonApiBaseUrl);
}

export function getRuntimeStatus(): Promise<RuntimeStatusResponse> {
  return requestJson<RuntimeStatusResponse>({
    url: tryonUrl('/api/runtime-status'),
    method: 'GET',
    headers: workbenchHeaders(),
    timeout: 10000,
  });
}

export function getRateStatus(): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>({
    url: tryonUrl('/api/rate-status'),
    method: 'GET',
    headers: workbenchHeaders(),
    timeout: 10000,
  });
}

export async function uploadModelPhoto(filePath: string): Promise<TryOnUploadResponse> {
  const res = await uploadMultipart<TryOnUploadResponse>({
    url: tryonUrl('/upload/model'),
    filePath,
    name: 'file',
    headers: workbenchHeaders(),
    timeout: 90000,
  });
  captureToken(res);
  return res;
}

export async function uploadGarmentPhoto(filePath: string): Promise<TryOnUploadResponse> {
  const res = await uploadMultipart<TryOnUploadResponse>({
    url: tryonUrl('/upload/garment'),
    filePath,
    name: 'file',
    headers: workbenchHeaders(),
    timeout: 90000,
  });
  captureToken(res);
  return res;
}

export async function intakeImageByUrl(
  imageUrl: string,
  role: 'model' | 'garment',
): Promise<TryOnUploadResponse> {
  const res = await requestJson<TryOnUploadResponse>({
    url: tryonUrl('/api/intake-image'),
    method: 'POST',
    data: {
      image_url: imageUrl,
      role,
      locale: getLocale(),
    },
    headers: workbenchHeaders(),
    timeout: 45000,
  });
  captureToken(res);
  return res;
}

/**
 * Import a remote or main-backend image URL into the try-on workbench.
 * Tries server-side /api/intake-image first; if blocked by SSRF/local-network rules
 * (e.g. 127.0.0.1 in local defense demo), downloads on client and uploads multipart.
 */
export async function intakeOrUploadImage(
  imageUrl: string,
  role: 'model' | 'garment',
): Promise<TryOnUploadResponse> {
  try {
    const intake = await intakeImageByUrl(imageUrl, role);
    if (intake && intake.filename) {
      return intake;
    }
  } catch {
    // Fall back to client-side temp download + multipart upload
  }
  const tempPath = await downloadTempFile(imageUrl);
  return role === 'model' ? uploadModelPhoto(tempPath) : uploadGarmentPhoto(tempPath);
}

export async function submitTryOnTask(params: {
  target_image: string;
  reference_image: string;
  model?: string;
  provider?: string;
  model_id?: string;
  totokens_profile?: string;
  freedom?: number;
  aspect_ratio?: string;
  image_size?: string;
  quality?: string;
  temperature?: number | string;
  seed?: number | string;
  garment_type?: string;
  custom_prompt?: string;
  prompt_mode?: 'append' | 'replace';
  target_image_cloud_url?: string;
  reference_image_cloud_url?: string;
  idempotency_key: string;
}): Promise<TryOnSubmitResponse> {
  const res = await requestFormUrlEncoded<TryOnSubmitResponse>({
    url: tryonUrl('/submit-task'),
    fields: {
      target_image: params.target_image,
      reference_image: params.reference_image,
      model: params.model || 'flash',
      freedom: params.freedom ?? 5,
      locale: getLocale(),
      idempotency_key: params.idempotency_key,
      provider: params.provider,
      model_id: params.model_id,
      totokens_profile: params.totokens_profile && params.totokens_profile !== 'auto' ? params.totokens_profile : undefined,
      aspect_ratio: params.aspect_ratio,
      image_size: params.image_size,
      quality: params.quality,
      temperature: params.temperature,
      seed: params.seed,
      garment_type: params.garment_type,
      custom_prompt: params.custom_prompt,
      prompt_mode: params.custom_prompt ? (params.prompt_mode || 'append') : undefined,
      target_image_cloud_url: params.target_image_cloud_url,
      reference_image_cloud_url: params.reference_image_cloud_url,
    },
    headers: workbenchHeaders({
      'X-Idempotency-Key': params.idempotency_key,
    }),
    timeout: 60000,
  });
  captureToken(res);
  return res;
}

export function getTryOnTask(taskId: string): Promise<TryOnTaskResponse> {
  return requestJson<TryOnTaskResponse>({
    url: tryonUrl(`/task/${encodeURIComponent(taskId)}`),
    method: 'GET',
    query: { lang: getLocale() },
    headers: workbenchHeaders(),
    timeout: 20000,
  });
}

export async function getWorkbenchProducts(params: {
  query?: string;
  gender?: string;
  platform?: string;
  offset?: number;
  limit?: number;
}): Promise<ProductCatalogResponse> {
  try {
    return await requestJson<ProductCatalogResponse>({
      url: tryonUrl('/api/products'),
      method: 'GET',
      query: { ...params, locale: getLocale() },
      headers: workbenchHeaders(),
      timeout: 15000,
    });
  } catch {
    return getCatalogProducts({ ...params, mode: params.gender ? 'gender' : 'all' });
  }
}
