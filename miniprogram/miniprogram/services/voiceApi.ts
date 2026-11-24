import { getEndpointConfig } from '../config/env';
import { getLocale } from '../i18n';
import type { ASRResult, TTSResult, VoiceCatalogItem, VoicePublicConfig } from '../types/api';
import { requestJson, uploadMultipart } from '../utils/request';
import { buildMainMediaUrl, joinUrl } from '../utils/url';

function mainUrl(path: string): string {
  return joinUrl(getEndpointConfig().mainApiBaseUrl, path);
}

export function getVoiceConfig(): Promise<VoicePublicConfig> {
  return requestJson<VoicePublicConfig>({
    url: mainUrl('/api/assistant/voice/config/public'),
    method: 'GET',
    query: { locale: getLocale() },
    timeout: 10000,
  });
}

export function getVoiceCatalog(): Promise<VoiceCatalogItem[]> {
  return requestJson<VoiceCatalogItem[]>({
    url: mainUrl('/api/assistant/voice/catalog/public'),
    method: 'GET',
    query: { locale: getLocale() },
    timeout: 10000,
  });
}

export function asrRecognize(
  audioFilePath: string,
  sessionId: string,
  language = 'zh',
  format: 'mp3' | 'wav' = 'mp3',
): Promise<ASRResult> {
  return uploadMultipart<ASRResult>({
    url: mainUrl('/api/assistant/asr'),
    filePath: audioFilePath,
    name: 'audio',
    formData: {
      session_id: sessionId,
      language,
      speech_language: language,
      locale: getLocale(),
      format,
    },
    timeout: 60000,
  });
}

export function ttsSynthesize(params: {
  sessionId: string;
  text: string;
  voice?: string;
  stylePrompt?: string;
  voiceSource?: 'preset' | 'clone';
  cloneVoiceId?: string;
  tonePreset?: string;
  volume?: number;
}): Promise<TTSResult> {
  return requestJson<TTSResult>({
    url: mainUrl('/api/assistant/tts'),
    method: 'POST',
    data: {
      session_id: params.sessionId,
      locale: getLocale(),
      text: params.text,
      voice: params.voice,
      format: 'mp3',
      style_prompt: params.stylePrompt,
      voice_source: params.voiceSource || 'preset',
      clone_voice_id: params.cloneVoiceId || undefined,
      tone_preset: params.tonePreset || 'natural',
      volume: params.volume ?? 1.0,
    },
    timeout: 60000,
  });
}

export function resolveTtsAudioUrl(audioPath: string): string {
  return buildMainMediaUrl(audioPath, getEndpointConfig().mainApiBaseUrl);
}
