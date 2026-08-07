/* Voice module types — shared by voice input, TTS, settings, and call mode */

export type AssistantVoiceState =
  | 'idle'
  | 'listening'
  | 'recognizing'
  | 'thinking'
  | 'speaking'
  | 'error';

export interface VoicePublicConfig {
  asr_enabled: boolean;
  tts_enabled: boolean;
  voice_clone_enabled: boolean;
  asr_disabled_reason?: string;
  tts_disabled_reason?: string;
  default_asr_provider: string;
  default_asr_model: string;
  default_tts_provider: string;
  default_tts_model: string;
  default_voice: string;
  available_voices: string[];
  published_clone_voices: Array<{ id: string; name: string; description?: string }>;
  asr_languages: string[];
  max_record_seconds: number;
  hard_max_record_seconds: number;
  max_audio_base64_mb: number;
  supported_audio_formats: string[];
  default_language: string;
  max_tts_text_length: number;
}

export interface ASRResult {
  success: boolean;
  text: string;
  normalized_text?: string;
  provider: string;
  model: string;
  language: string;
  duration_ms?: number;
  latency_ms?: number;
  error?: { code: string; message: string };
}

export interface TTSResult {
  success: boolean;
  audio_url?: string;
  audio_base64?: string;
  format: string;
  voice: string;
  provider: string;
  model: string;
  error?: { code: string; message: string };
}

export type CallState =
  | 'idle'
  | 'requesting_permission'
  | 'ready'
  | 'listening'
  | 'recording'
  | 'recognizing'
  | 'thinking'
  | 'speaking'
  | 'paused'
  | 'muted'
  | 'error'
  | 'ended';

export interface VoiceCallTurn {
  id: string;
  userText?: string;
  assistantText?: string;
  startedAt: number;
  endedAt?: number;
  asrLatencyMs?: number;
  chatLatencyMs?: number;
  ttsLatencyMs?: number;
  error?: string;
}

export interface VoiceCallSessionState {
  callId: string | null;
  sessionId: string;
  state: CallState;
  startedAt: number | null;
  endedAt: number | null;
  durationSeconds: number;
  turns: VoiceCallTurn[];
  currentTranscript: string;
  currentAssistantText: string;
  isMuted: boolean;
  isAudioPlaying: boolean;
  errorMessage: string | null;
}

/** Map CallState → AssistantVoiceState for unified voice state management */
export function callStateToVoiceState(cs: CallState): AssistantVoiceState {
  switch (cs) {
    case 'idle':
    case 'ready':
    case 'paused':
    case 'muted':
    case 'ended':
      return 'idle';
    case 'listening':
    case 'recording':
      return 'listening';
    case 'requesting_permission':
    case 'recognizing':
      return 'recognizing';
    case 'thinking':
      return 'thinking';
    case 'speaking':
      return 'speaking';
    case 'error':
      return 'error';
    default:
      return 'idle';
  }
}

/** Tone presets for TTS style */
export const TONE_PRESETS = [
  { id: 'natural', label: '自然导购', prompt: '像亲切的导购助手，语速适中，语气自然。' },
  { id: 'anime', label: '活泼二次元', prompt: '像活泼的二次元助手，语速稍快，语气可爱热情。' },
  { id: 'gentle', label: '温柔客服', prompt: '像温柔的客服，语速偏慢，语气耐心温和。' },
  { id: 'professional', label: '专业简洁', prompt: '像专业的顾问，语速适中，语气简洁明确。' },
];
