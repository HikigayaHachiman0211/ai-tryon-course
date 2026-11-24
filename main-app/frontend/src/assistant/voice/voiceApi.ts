/* Voice API client — single source of truth for ASR, TTS, and voice config endpoints */

import axios, { AxiosHeaders } from 'axios';
import type { ASRResult, TTSResult, VoicePublicConfig } from './voiceTypes';
import { getAudioFileInfo } from './audioEncoding';
import i18n from '../../i18n';
import { DEFAULT_LOCALE, normalizeLocale, type AppLocale } from '../../i18n/locale';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
});

api.interceptors.request.use((config) => {
  const headers = AxiosHeaders.from(config.headers);
  headers.set('Accept-Language', normalizeLocale(i18n.resolvedLanguage) ?? DEFAULT_LOCALE);
  config.headers = headers;
  return config;
});

const activeLocale = (): AppLocale => normalizeLocale(i18n.resolvedLanguage) ?? DEFAULT_LOCALE;

/**
 * Fetch public voice configuration (non-sensitive).
 * No API keys returned.
 */
export async function getVoiceConfig(): Promise<VoicePublicConfig> {
  const res = await api.get('/api/assistant/voice/config/public');
  return res.data;
}

/**
 * Upload audio for speech-to-text recognition.
 *
 * The audioBlob should already be WAV (converted by useVoiceRecorder).
 * We detect the real format from the Blob type and set filename/format accordingly.
 * If the blob is not wav or mp3, we return an error rather than upload a fake format.
 */
export async function asrRecognize(
  audioBlob: Blob,
  sessionId: string,
  language: string = 'zh',
): Promise<ASRResult> {
  const { ext, format } = getAudioFileInfo(audioBlob);

  // Strict: only upload real wav or mp3 — null means unsupported
  if (format === null) {
    return {
      success: false,
      text: '',
      provider: 'mimo',
      model: 'mimo-v2.5-asr',
      language,
      error: {
        code: 'UNSUPPORTED_FORMAT',
        message: 'UNSUPPORTED_FORMAT',
      },
    };
  }

  const formData = new FormData();
  formData.append('audio', audioBlob, `recording.${ext}`);
  formData.append('session_id', sessionId);
  formData.append('language', language);
  formData.append('speech_language', language);
  formData.append('locale', activeLocale());
  formData.append('format', format);

  const res = await api.post('/api/assistant/asr', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  });
  return res.data;
}

/**
 * Request text-to-speech synthesis.
 */
export async function ttsSynthesize(params: {
  sessionId: string;
  text: string;
  voice?: string;
  format?: string;
  stylePrompt?: string;
  voiceSource?: string;
  cloneVoiceId?: string;
  tonePreset?: string;
  volume?: number;
}): Promise<TTSResult> {
  // Validate format server-side accepts wav/mp3 only
  const fmt = (params.format === 'mp3') ? 'mp3' : 'wav';

  const res = await api.post('/api/assistant/tts', {
    session_id: params.sessionId,
    locale: activeLocale(),
    text: params.text,
    voice: params.voice,
    format: fmt,
    style_prompt: params.stylePrompt,
    voice_source: params.voiceSource || 'preset',
    clone_voice_id: params.cloneVoiceId,
    tone_preset: params.tonePreset,
    volume: params.volume ?? 1.0,
  }, { timeout: 60000 });
  return res.data;
}

/**
 * Build full URL for a TTS audio path returned by the backend.
 */
export function buildTTSUrl(audioPath: string): string {
  if (!audioPath) return '';
  if (/^https?:\/\//i.test(audioPath)) return audioPath;
  const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  // Vite production often uses '/' for same-origin API; URL() requires absolute base.
  if (baseURL === '/' || baseURL === '') {
    if (typeof window !== 'undefined') {
      return new URL(audioPath, window.location.origin).toString();
    }
    return audioPath;
  }

  return new URL(audioPath, baseURL.endsWith('/') ? baseURL : `${baseURL}/`).toString();
}
