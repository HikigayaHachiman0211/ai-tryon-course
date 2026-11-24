import type { AppLocale } from '../types/api';
import { getStoredLocale, setStoredLocale } from '../utils/storage';
import zhCN, { type TranslationSchema } from './zh-CN';
import en from './en';
import ja from './ja';

const BUNDLES: Record<AppLocale, TranslationSchema> = {
  'zh-CN': zhCN,
  en,
  ja,
};

export const LOCALE_OPTIONS: Array<{ value: AppLocale; label: string; shortLabel: string }> = [
  { value: 'zh-CN', label: '简体中文', shortLabel: '中' },
  { value: 'en', label: 'English', shortLabel: 'EN' },
  { value: 'ja', label: '日本語', shortLabel: '日' },
];

type LocaleListener = (locale: AppLocale) => void;
const listeners = new Set<LocaleListener>();

let currentLocale: AppLocale = getStoredLocale() || 'zh-CN';

export function normalizeAppLocale(raw: unknown): AppLocale {
  const s = String(raw || '').trim().toLowerCase().replace('_', '-');
  if (s === 'en' || s.startsWith('en-')) return 'en';
  if (s === 'ja' || s.startsWith('ja-')) return 'ja';
  return 'zh-CN';
}

export function getLocale(): AppLocale {
  return currentLocale;
}

export function setLocale(next: AppLocale): AppLocale {
  const normalized = normalizeAppLocale(next);
  currentLocale = normalized;
  setStoredLocale(normalized);
  listeners.forEach((fn) => {
    try {
      fn(normalized);
    } catch {
      // Ignore individual listener failures
    }
  });
  return normalized;
}

export function subscribeLocale(fn: LocaleListener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function getBundle(locale: AppLocale = currentLocale): TranslationSchema {
  return BUNDLES[locale] || zhCN;
}

function lookupPath(obj: Record<string, unknown>, path: string): unknown {
  const parts = path.split('.');
  let cursor: unknown = obj;
  for (const part of parts) {
    if (!cursor || typeof cursor !== 'object') return undefined;
    cursor = (cursor as Record<string, unknown>)[part];
  }
  return cursor;
}

export function t(
  key: string,
  vars?: Record<string, string | number | null | undefined>,
  locale: AppLocale = currentLocale,
): string {
  const bundle = getBundle(locale) as unknown as Record<string, unknown>;
  let raw = lookupPath(bundle, key);
  if (typeof raw !== 'string') {
    raw = lookupPath(zhCN as unknown as Record<string, unknown>, key);
  }
  if (typeof raw !== 'string') {
    return key;
  }
  if (!vars) return raw;
  return raw.replace(/\{\{(\w+)\}\}/g, (_, name: string) => {
    const value = vars[name];
    return value === undefined || value === null ? '' : String(value);
  });
}

export { BUNDLES };
