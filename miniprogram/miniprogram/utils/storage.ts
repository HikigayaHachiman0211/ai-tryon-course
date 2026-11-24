import type { AppLocale, VoiceSettings } from '../types/api';

const memoryStorage = new Map<string, unknown>();

const STORAGE_KEYS = {
  locale: 'ai_tryon_mp_locale_v1',
  endpoints: 'ai_tryon_mp_endpoints_v1',
  sessionId: 'ai_tryon_mp_session_id_v1',
  visitorToken: 'ai_tryon_mp_visitor_token_v1',
  voiceSettings: 'ai_tryon_mp_voice_settings_v1',
  profileDraft: 'ai_tryon_mp_profile_draft_v1',
} as const;

function hasWxStorage(): boolean {
  return typeof wx !== 'undefined' && typeof wx.getStorageSync === 'function';
}

export function getStorageItem<T>(key: string): T | null {
  try {
    if (hasWxStorage()) {
      const value = wx.getStorageSync(key);
      return value === '' || value === undefined ? null : (value as T);
    }
    return memoryStorage.has(key) ? (memoryStorage.get(key) as T) : null;
  } catch {
    return memoryStorage.has(key) ? (memoryStorage.get(key) as T) : null;
  }
}

export function setStorageItem<T>(key: string, value: T): void {
  memoryStorage.set(key, value);
  try {
    if (hasWxStorage()) {
      wx.setStorageSync(key, value);
    }
  } catch {
    // Ignore storage quota or sandbox errors in restricted previews
  }
}

export function generateClientUuid(prefix: string): string {
  const rand = () => Math.floor((1 + Math.random()) * 0x10000).toString(16).slice(1);
  const ts = Date.now().toString(16);
  return `${prefix}-${ts}-${rand()}${rand()}-${rand()}`;
}

export function getStoredLocale(): AppLocale | null {
  const raw = getStorageItem<string>(STORAGE_KEYS.locale);
  if (raw === 'zh-CN' || raw === 'en' || raw === 'ja') {
    return raw;
  }
  return null;
}

export function setStoredLocale(locale: AppLocale): void {
  setStorageItem(STORAGE_KEYS.locale, locale);
}

export function getOrCreateSessionId(): string {
  const existing = getStorageItem<string>(STORAGE_KEYS.sessionId);
  if (existing && existing.trim()) {
    return existing;
  }
  const created = generateClientUuid('mp-sess');
  setStorageItem(STORAGE_KEYS.sessionId, created);
  return created;
}

export function getVisitorToken(): string {
  const existing = getStorageItem<string>(STORAGE_KEYS.visitorToken);
  if (existing && existing.trim()) {
    return existing;
  }
  const created = generateClientUuid('mp-visitor');
  setStorageItem(STORAGE_KEYS.visitorToken, created);
  return created;
}

export function setVisitorToken(token: string): void {
  const cleaned = String(token || '').trim();
  if (cleaned) {
    setStorageItem(STORAGE_KEYS.visitorToken, cleaned);
  }
}

export const DEFAULT_VOICE_SETTINGS: VoiceSettings = {
  autoPlayTts: false,
  autoSendAsr: false,
  voice: 'mimo_default',
  voiceSource: 'preset',
  cloneVoiceId: '',
  tonePreset: 'natural',
  asrLanguage: 'zh',
  volume: 1.0,
};

export function getStoredVoiceSettings(): VoiceSettings {
  const saved = getStorageItem<Partial<VoiceSettings>>(STORAGE_KEYS.voiceSettings);
  if (!saved || typeof saved !== 'object') {
    return { ...DEFAULT_VOICE_SETTINGS };
  }
  return {
    ...DEFAULT_VOICE_SETTINGS,
    ...saved,
    volume: typeof saved.volume === 'number' && saved.volume >= 0.1 && saved.volume <= 1 ? saved.volume : 1.0,
  };
}

export function setStoredVoiceSettings(settings: VoiceSettings): void {
  setStorageItem(STORAGE_KEYS.voiceSettings, settings);
}

export { STORAGE_KEYS };
