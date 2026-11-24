import { getEndpointConfig } from '../config/env';
import type {
  VideoConfigResponse,
  VideoModelItem,
  VideoQuoteResponse,
  VideoTaskResponse,
} from '../types/api';
import { requestJson } from '../utils/request';
import { setVisitorToken } from '../utils/storage';
import { buildTryOnMediaUrl, joinUrl } from '../utils/url';
import { workbenchHeaders } from './tryonApi';

function videoUrl(path: string): string {
  return joinUrl(getEndpointConfig().tryonApiBaseUrl, `/api/video${path}`);
}

export async function getVideoConfig(): Promise<VideoConfigResponse> {
  const res = await requestJson<VideoConfigResponse>({
    url: videoUrl('/config'),
    method: 'GET',
    headers: workbenchHeaders(),
    timeout: 10000,
  });
  if (res && res.task_token) {
    setVisitorToken(res.task_token);
  }
  return res;
}

export async function getVideoModels(refresh = false): Promise<{ data: VideoModelItem[]; project: boolean }> {
  return requestJson<{ data: VideoModelItem[]; project: boolean }>({
    url: videoUrl('/models'),
    method: 'GET',
    query: refresh ? { refresh: 'true' } : undefined,
    headers: workbenchHeaders(),
    timeout: 20000,
  });
}

export function quoteVideo(payload: {
  model: string;
  provider?: string;
  input: Record<string, unknown>;
  idempotency_key?: string;
}): Promise<VideoQuoteResponse> {
  return requestJson<VideoQuoteResponse>({
    url: videoUrl('/quote'),
    method: 'POST',
    data: {
      model: payload.model,
      provider: payload.provider || '',
      input: payload.input,
      idempotency_key: payload.idempotency_key || '',
    },
    headers: workbenchHeaders(),
    timeout: 30000,
  });
}

export function submitVideoTask(payload: {
  model: string;
  provider?: string;
  input: Record<string, unknown>;
  idempotency_key: string;
}): Promise<VideoTaskResponse> {
  return requestJson<VideoTaskResponse>({
    url: videoUrl('/tasks'),
    method: 'POST',
    data: {
      model: payload.model,
      provider: payload.provider || '',
      input: payload.input,
      idempotency_key: payload.idempotency_key,
    },
    headers: workbenchHeaders(),
    timeout: 60000,
  });
}

export function listVideoTasks(): Promise<{ data: VideoTaskResponse[] }> {
  return requestJson<{ data: VideoTaskResponse[] }>({
    url: videoUrl('/tasks'),
    method: 'GET',
    headers: workbenchHeaders(),
    timeout: 15000,
  });
}

export function pollVideoTask(taskId: string): Promise<VideoTaskResponse> {
  return requestJson<VideoTaskResponse>({
    url: videoUrl(`/tasks/${encodeURIComponent(taskId)}`),
    method: 'GET',
    headers: workbenchHeaders(),
    timeout: 20000,
  });
}

export function cancelVideoTask(taskId: string): Promise<VideoTaskResponse> {
  return requestJson<VideoTaskResponse>({
    url: videoUrl(`/tasks/${encodeURIComponent(taskId)}/cancel`),
    method: 'POST',
    data: {},
    headers: workbenchHeaders(),
    timeout: 20000,
  });
}

export function resolveVideoDownloadUrl(task: VideoTaskResponse): string {
  const firstDownload = task.download_urls && task.download_urls[0];
  if (firstDownload) {
    return buildTryOnMediaUrl(firstDownload, getEndpointConfig().tryonApiBaseUrl);
  }
  const firstOutput = task.outputs && task.outputs[0];
  return firstOutput || '';
}
