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
  locale?: string;
  available_voice_catalog?: Array<{ id: string; name: string; display_name?: string; display_description?: string; source?: string }>;
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
  locale?: string;
  speech_language?: string;
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
  locale?: string;
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
  { id: 'natural' },
  { id: 'anime' },
  { id: 'gentle' },
  { id: 'professional' },
];
