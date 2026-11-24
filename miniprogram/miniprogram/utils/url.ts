export function trimTrailingSlash(url: string): string {
  return String(url || '').trim().replace(/\/+$/, '');
}

export function joinUrl(baseUrl: string, path: string): string {
  const rawPath = String(path || '').trim();
  if (!rawPath) return trimTrailingSlash(baseUrl);
  if (/^https?:\/\//i.test(rawPath)) {
    return rawPath;
  }
  const cleanBase = trimTrailingSlash(baseUrl);
  if (!cleanBase) return rawPath;
  if (rawPath.startsWith('/')) {
    return `${cleanBase}${rawPath}`;
  }
  return `${cleanBase}/${rawPath}`;
}

export function cleanFormFields(
  fields: Record<string, string | number | boolean | null | undefined>,
): Record<string, string> {
  const out: Record<string, string> = {};
  Object.keys(fields).forEach((key) => {
    const val = fields[key];
    if (val === undefined || val === null) return;
    const str = String(val);
    if (str === '') return;
    out[key] = str;
  });
  return out;
}

export function buildQueryString(
  params?: Record<string, string | number | boolean | null | undefined>,
): string {
  if (!params) return '';
  const parts: string[] = [];
  Object.keys(params).forEach((key) => {
    const val = params[key];
    if (val === undefined || val === null || val === '') return;
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(val))}`);
  });
  return parts.join('&');
}

export function appendQueryParams(
  url: string,
  params?: Record<string, string | number | boolean | null | undefined>,
): string {
  const qs = buildQueryString(params);
  if (!qs) return url;
  return url.includes('?') ? `${url}&${qs}` : `${url}?${qs}`;
}

export function serializeFormUrlEncoded(
  fields: Record<string, string | number | boolean | null | undefined>,
): string {
  const cleaned = cleanFormFields(fields);
  return buildQueryString(cleaned);
}

export function buildMainMediaUrl(path: string | null | undefined, mainBaseUrl: string): string {
  if (!path) return '';
  const raw = String(path).trim();
  if (!raw) return '';
  if (/^(https?:\/\/|data:|wxfile:\/\/)/i.test(raw)) {
    return raw;
  }
  return joinUrl(mainBaseUrl, raw.startsWith('/') ? raw : `/${raw}`);
}

export function buildTryOnMediaUrl(path: string | null | undefined, tryonBaseUrl: string): string {
  if (!path) return '';
  const raw = String(path).trim();
  if (!raw) return '';
  if (/^(https?:\/\/|data:|wxfile:\/\/)/i.test(raw)) {
    return raw;
  }
  return joinUrl(tryonBaseUrl, raw.startsWith('/') ? raw : `/${raw}`);
}

export function buildSampleModelUrl(
  gender: 'male' | 'female',
  filename: string,
  mainBaseUrl: string,
): string {
  return joinUrl(mainBaseUrl, `/sample-models/${encodeURIComponent(gender)}/${encodeURIComponent(filename)}`);
}
