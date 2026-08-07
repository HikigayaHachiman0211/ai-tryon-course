/* Voice settings persistence — localStorage only, no API keys, no audio data */

const STORAGE_KEY = 'assistant_voice_settings';

export interface VoiceSettings {
  tts_enabled: boolean;
  auto_tts_enabled: boolean;
  voice_source: 'preset' | 'clone';
  preset_voice: string;
  clone_voice_id: string | null;
  tone_preset: string;
  custom_style_prompt: string;
  asr_language: string;
  record_mode: 'click' | 'hold';
  auto_send_asr: boolean;
  volume: number;
  max_tts_text_length: number;
}

const DEFAULT_SETTINGS: VoiceSettings = {
  tts_enabled: false,
  auto_tts_enabled: false,
  voice_source: 'preset',
  preset_voice: '茉莉',
  clone_voice_id: null,
  tone_preset: 'natural',
  custom_style_prompt: '',
  asr_language: 'zh',
  record_mode: 'click',
  auto_send_asr: true,
  volume: 1.0,
  max_tts_text_length: 300,
};

export function loadVoiceSettings(): VoiceSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_SETTINGS };
    const parsed = JSON.parse(raw);
    // Merge with defaults to handle missing fields gracefully
    return { ...DEFAULT_SETTINGS, ...parsed };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

export function saveVoiceSettings(settings: Partial<VoiceSettings>): void {
  try {
    const current = loadVoiceSettings();
    const merged = { ...current, ...settings };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

export function clearVoiceSettings(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
