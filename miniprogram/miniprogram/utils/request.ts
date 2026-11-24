import { getLocale, t } from '../i18n';
import { appendQueryParams, cleanFormFields, serializeFormUrlEncoded } from './url';

export class ApiError extends Error {
  statusCode: number;
  code: string;
  details?: unknown;

  constructor(message: string, statusCode = 0, code = 'REQUEST_ERROR', details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
  }
}

function parseErrorPayload(raw: unknown, statusCode: number): { code: string; message: string; details?: unknown } {
  let parsed: unknown = raw;
  if (typeof raw === 'string') {
    const trimmed = raw.trim();
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      try {
        parsed = JSON.parse(trimmed);
      } catch {
        parsed = trimmed;
      }
    }
  }
  if (parsed && typeof parsed === 'object') {
    const obj = parsed as Record<string, unknown>;
    if (obj.error && typeof obj.error === 'object') {
      const inner = obj.error as Record<string, unknown>;
      return {
        code: String(inner.code || `HTTP_${statusCode}`),
        message: String(inner.message || inner.detail || `HTTP ${statusCode}`),
        details: inner.details,
      };
    }
    if (typeof obj.error === 'string' && obj.error) {
      return { code: String(obj.error_code || `HTTP_${statusCode}`), message: obj.error };
    }
    if (typeof obj.detail === 'string' && obj.detail) {
      return { code: `HTTP_${statusCode}`, message: obj.detail };
    }
    if (typeof obj.message === 'string' && obj.message) {
      return { code: String(obj.code || `HTTP_${statusCode}`), message: obj.message };
    }
  }
  if (typeof parsed === 'string' && parsed.trim()) {
    return { code: `HTTP_${statusCode}`, message: parsed.trim().slice(0, 220) };
  }
  return { code: `HTTP_${statusCode}`, message: `HTTP ${statusCode}` };
}

export interface RequestJsonOptions {
  url: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  data?: unknown;
  query?: Record<string, string | number | boolean | null | undefined>;
  headers?: Record<string, string>;
  timeout?: number;
}

export function requestJson<T>(options: RequestJsonOptions): Promise<T> {
  const fullUrl = appendQueryParams(options.url, options.query);
  const method = options.method || 'GET';
  const headers: Record<string, string> = {
    'Accept-Language': getLocale(),
    ...(options.headers || {}),
  };
  if (method !== 'GET' && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  return new Promise<T>((resolve, reject) => {
    wx.request({
      url: fullUrl,
      method,
      data: options.data as WechatMiniprogram.IAnyObject | string | ArrayBuffer | undefined,
      header: headers,
      timeout: options.timeout ?? 60000,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          if (typeof res.data === 'string') {
            try {
              resolve(JSON.parse(res.data) as T);
              return;
            } catch {
              resolve(res.data as unknown as T);
              return;
            }
          }
          resolve(res.data as T);
          return;
        }
        const info = parseErrorPayload(res.data, res.statusCode);
        reject(new ApiError(info.message, res.statusCode, info.code, info.details));
      },
      fail(err) {
        reject(new ApiError(err.errMsg || t('common.networkError'), 0, 'NETWORK_ERROR', err));
      },
    });
  });
}

export interface RequestFormOptions {
  url: string;
  fields: Record<string, string | number | boolean | null | undefined>;
  headers?: Record<string, string>;
  timeout?: number;
}

export function requestFormUrlEncoded<T>(options: RequestFormOptions): Promise<T> {
  const encoded = serializeFormUrlEncoded(options.fields);
  return requestJson<T>({
    url: options.url,
    method: 'POST',
    data: encoded,
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      ...(options.headers || {}),
    },
    timeout: options.timeout ?? 90000,
  });
}

export interface UploadMultipartOptions {
  url: string;
  filePath: string;
  name: string;
  formData?: Record<string, string | number | boolean | null | undefined>;
  headers?: Record<string, string>;
  timeout?: number;
}

export function uploadMultipart<T>(options: UploadMultipartOptions): Promise<T> {
  const cleanedForm = cleanFormFields(options.formData || {});
  const headers: Record<string, string> = {
    'Accept-Language': getLocale(),
    ...(options.headers || {}),
  };

  return new Promise<T>((resolve, reject) => {
    wx.uploadFile({
      url: options.url,
      filePath: options.filePath,
      name: options.name,
      formData: cleanedForm,
      header: headers,
      timeout: options.timeout ?? 90000,
      success(res) {
        let parsed: unknown = res.data;
        if (typeof res.data === 'string') {
          try {
            parsed = JSON.parse(res.data);
          } catch {
            parsed = res.data;
          }
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(parsed as T);
          return;
        }
        const info = parseErrorPayload(parsed, res.statusCode);
        reject(new ApiError(info.message, res.statusCode, info.code, info.details));
      },
      fail(err) {
        reject(new ApiError(err.errMsg || t('common.networkError'), 0, 'UPLOAD_FAILED', err));
      },
    });
  });
}

export function downloadTempFile(
  url: string,
  headers?: Record<string, string>,
  timeout = 60000,
): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    wx.downloadFile({
      url,
      header: headers || {},
      timeout,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300 && res.tempFilePath) {
          resolve(res.tempFilePath);
          return;
        }
        reject(new ApiError(`Download failed (HTTP ${res.statusCode})`, res.statusCode, 'DOWNLOAD_FAILED'));
      },
      fail(err) {
        reject(new ApiError(err.errMsg || t('common.networkError'), 0, 'DOWNLOAD_FAILED', err));
      },
    });
  });
}
