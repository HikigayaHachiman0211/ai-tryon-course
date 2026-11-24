import { detectInitialLocale, type AppLocale } from './i18n/locale';
import { withLocaleQuery } from './utils/adminUrl';

export interface TryOnBridgePayload {
  source: 'down-jacket-recommendation';
  garmentImageUrl: string;
  productId: string;
  productTitle: string;
  productPrice?: number | string;
  productUrl?: string;
  styleType?: string;
  colorFamily?: string;
  sizeHint?: string;
  recommendationReason?: string;
  score?: number;
  sceneHint?: string;
  fitNote?: string;
  returnUrl?: string;
  locale: AppLocale;
  presentationSource?: { kind: 'recommend' | 'style-lab' | 'product'; result: object };
  // Signed or public URL of the user's full-body photo. Travels via the URL channel
  // (not stripped) so the workbench can import it deterministically on load,
  // independent of the fragile postMessage timing.
  userImageUrl?: string;
  userImageDataUrl?: string;
}

const TRYON_BRIDGE_TYPE = 'DOWN_JACKET_TRYON_INIT';
const TRYON_BRIDGE_VERSION = 1;
const DEFAULT_TRYON_LOCAL_URL = 'http://127.0.0.1:8080/static/index.html';

function sanitizeTryOnUrl(rawUrl: string | undefined, fallback: string): string {
  const value = (rawUrl ?? '').trim();
  if (!value) return fallback;

  const normalized = value
    .replace(/^https;\\\\/i, 'https://')
    .replace(/^http;\\\\/i, 'http://')
    .replace(/^https;\/\//i, 'https://')
    .replace(/^http;\/\//i, 'http://')
    .replace(/^https:\\\\/i, 'https://')
    .replace(/^http:\\\\/i, 'http://');

  try {
    const parsed = new URL(normalized, typeof window !== 'undefined' ? window.location.origin : undefined);
    if (!/^https?:$/.test(parsed.protocol)) return fallback;
    if (!import.meta.env.DEV && typeof window !== 'undefined') {
      const isRootLike = parsed.pathname === '/' || parsed.pathname === '';
      if (parsed.origin === window.location.origin && isRootLike) return fallback;
    }
    return parsed.toString();
  } catch {
    return fallback;
  }
}

export const getTryOnBaseUrl = (locale: AppLocale = detectInitialLocale()): string =>
  withLocaleQuery(sanitizeTryOnUrl(
    import.meta.env.VITE_TRYON_BASE_URL as string | undefined,
    import.meta.env.DEV ? DEFAULT_TRYON_LOCAL_URL : '',
  ), locale);

export const getTryOnOrigin = (): string => {
  try {
    return new URL(getTryOnBaseUrl()).origin;
  } catch {
    return '';
  }
};

// Strips userImageDataUrl before serializing to URL query param (never include photo in URL channel).
export const serializeTryOnPayloadForUrl = (payload: TryOnBridgePayload): string => {
  const urlPayload = { ...payload };
  delete urlPayload.userImageDataUrl;
  return JSON.stringify(urlPayload);
};

export const openTryOnWindow = (payload: TryOnBridgePayload): Window | null => {
  const tryOnBaseUrl = getTryOnBaseUrl();
  if (!tryOnBaseUrl) return null;
  const locale = payload.locale ?? detectInitialLocale();
  const urlPayload = {
    ...payload,
    locale,
    returnUrl: payload.returnUrl ? withLocaleQuery(payload.returnUrl, locale) : payload.returnUrl,
  };
  const tryOnUrl = new URL(tryOnBaseUrl);
  tryOnUrl.searchParams.set('lang', locale);
  tryOnUrl.searchParams.set('tryonPayload', serializeTryOnPayloadForUrl(urlPayload));
  return window.open(tryOnUrl.toString(), '_blank');
};

// Sends payload via postMessage with ACK-aware retry. Skips entirely if origin is unavailable
// (no '*' fallback) to prevent delivering userImageDataUrl to an unverified window.
export const postTryOnPayloadWithAck = (
  tryonWindow: Window,
  payload: TryOnBridgePayload,
  origin: string,
): void => {
  if (!origin) return;

  const message = { type: TRYON_BRIDGE_TYPE, version: TRYON_BRIDGE_VERSION, payload };
  const attemptDelays = [250, 700, 1400, 2400, 4500, 7000, 12000, 20000, 35000, 50000];
  const listenerWindowMs = 120000;
  let acknowledged = false;
  const timers: number[] = [];

  const sendPayload = () => {
    if (acknowledged || tryonWindow.closed) return;
    try {
      tryonWindow.postMessage(message, origin);
    } catch {
      // Ignore cross-window delivery failures; the opened workbench remains usable.
    }
  };

  const cleanup = () => {
    window.removeEventListener('message', onBridgeReply);
    timers.forEach((id) => window.clearTimeout(id));
  };

  const onBridgeReply = (event: MessageEvent) => {
    if (event.origin !== origin) return;
    if (event.source && event.source !== tryonWindow) return;
    const data = event.data as { type?: unknown } | null;
    if (!data || typeof data !== 'object') return;
    const replyType = String(data.type ?? '').toUpperCase();
    if (replyType === 'DOWN_JACKET_TRYON_ACK') {
      acknowledged = true;
      cleanup();
      return;
    }
    if (replyType === 'DOWN_JACKET_TRYON_READY') {
      sendPayload();
    }
  };
  window.addEventListener('message', onBridgeReply);

  attemptDelays.forEach((delay) => {
    timers.push(window.setTimeout(() => {
      if (acknowledged || tryonWindow.closed) {
        if (tryonWindow.closed) cleanup();
        return;
      }
      sendPayload();
    }, delay));
  });

  // Clean up reply listener after the handshake window closes.
  timers.push(window.setTimeout(cleanup, listenerWindowMs));
};
