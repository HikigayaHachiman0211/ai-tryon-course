const DEFAULT_ADMIN_LOCAL_URL = 'http://127.0.0.1:8081';

export const sanitizeExternalUrl = (rawUrl: string | undefined, fallback: string) => {
  const value = (rawUrl || '').trim();
  if (!value) {
    return fallback;
  }

  const normalized = value
    .replace(/^https;\\\\/i, 'https://')
    .replace(/^http;\\\\/i, 'http://')
    .replace(/^https;\/\//i, 'https://')
    .replace(/^http;\/\//i, 'http://')
    .replace(/^https:\\\\/i, 'https://')
    .replace(/^http:\\\\/i, 'http://');

  try {
    const parsed = new URL(normalized, typeof window !== 'undefined' ? window.location.origin : undefined);
    if (!/^https?:$/.test(parsed.protocol)) {
      return fallback;
    }

    if (!import.meta.env.DEV && typeof window !== 'undefined') {
      const isRootLike = parsed.pathname === '/' || parsed.pathname === '';
      if (parsed.origin === window.location.origin && isRootLike) {
        return fallback;
      }
    }

    return parsed.toString();
  } catch {
    return fallback;
  }
};

export const getAdminUrl = () => sanitizeExternalUrl(
  import.meta.env.VITE_ADMIN_BASE_URL,
  import.meta.env.DEV ? DEFAULT_ADMIN_LOCAL_URL : '',
);
