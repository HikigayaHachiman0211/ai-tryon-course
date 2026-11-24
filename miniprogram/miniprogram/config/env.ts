import { getStorageItem, setStorageItem, STORAGE_KEYS } from '../utils/storage';

export type EndpointPresetId = 'local_batch' | 'local_manual' | 'cloud_443' | 'custom';

export interface EndpointConfig {
  presetId: EndpointPresetId;
  mainApiBaseUrl: string;
  tryonApiBaseUrl: string;
}

export interface EndpointPresetOption {
  id: Exclude<EndpointPresetId, 'custom'>;
  mainApiBaseUrl: string;
  tryonApiBaseUrl: string;
}

export const ENDPOINT_PRESETS: EndpointPresetOption[] = [
  {
    id: 'local_batch',
    mainApiBaseUrl: 'http://127.0.0.1:8000',
    tryonApiBaseUrl: 'http://127.0.0.1:8082',
  },
  {
    id: 'local_manual',
    mainApiBaseUrl: 'http://127.0.0.1:8000',
    tryonApiBaseUrl: 'http://127.0.0.1:8080',
  },
  {
    id: 'cloud_443',
    mainApiBaseUrl: 'https://your-domain.example',
    tryonApiBaseUrl: 'https://your-domain.example/mp-tryon',
  },
];

export const DEFAULT_ENDPOINT_CONFIG: EndpointConfig = {
  presetId: 'local_batch',
  mainApiBaseUrl: 'http://127.0.0.1:8000',
  tryonApiBaseUrl: 'http://127.0.0.1:8082',
};

function normalizeBaseUrl(raw: string, fallback: string): string {
  const trimmed = String(raw || '').trim().replace(/\/+$/, '');
  if (!trimmed) return fallback;
  if (/^https?:\/\/[^/\s]+/i.test(trimmed)) {
    return trimmed;
  }
  return fallback;
}

export function getEndpointConfig(): EndpointConfig {
  const saved = getStorageItem<Partial<EndpointConfig>>(STORAGE_KEYS.endpoints);
  if (!saved || typeof saved !== 'object') {
    return { ...DEFAULT_ENDPOINT_CONFIG };
  }
  const presetId = saved.presetId || 'custom';
  return {
    presetId,
    mainApiBaseUrl: normalizeBaseUrl(saved.mainApiBaseUrl || '', DEFAULT_ENDPOINT_CONFIG.mainApiBaseUrl),
    tryonApiBaseUrl: normalizeBaseUrl(saved.tryonApiBaseUrl || '', DEFAULT_ENDPOINT_CONFIG.tryonApiBaseUrl),
  };
}

export function saveEndpointConfig(config: Partial<EndpointConfig>): EndpointConfig {
  const current = getEndpointConfig();
  const next: EndpointConfig = {
    presetId: config.presetId ?? current.presetId,
    mainApiBaseUrl: normalizeBaseUrl(config.mainApiBaseUrl ?? current.mainApiBaseUrl, DEFAULT_ENDPOINT_CONFIG.mainApiBaseUrl),
    tryonApiBaseUrl: normalizeBaseUrl(config.tryonApiBaseUrl ?? current.tryonApiBaseUrl, DEFAULT_ENDPOINT_CONFIG.tryonApiBaseUrl),
  };
  setStorageItem(STORAGE_KEYS.endpoints, next);
  return next;
}

export function applyEndpointPreset(presetId: Exclude<EndpointPresetId, 'custom'>): EndpointConfig {
  const preset = ENDPOINT_PRESETS.find((item) => item.id === presetId) ?? ENDPOINT_PRESETS[0];
  return saveEndpointConfig({
    presetId: preset.id,
    mainApiBaseUrl: preset.mainApiBaseUrl,
    tryonApiBaseUrl: preset.tryonApiBaseUrl,
  });
}

export function resetEndpointConfig(): EndpointConfig {
  return saveEndpointConfig({ ...DEFAULT_ENDPOINT_CONFIG });
}
