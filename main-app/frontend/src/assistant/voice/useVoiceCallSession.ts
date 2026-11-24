/* Hook managing the full voice call session lifecycle — state machine, ASR, chat, TTS */

import { useCallback, useEffect, useRef, useState } from 'react';
import { postAssistantChat } from '../../api';
import type { RecommendFormPatch } from '../assistantTypes';
import { getSessionId } from '../utils/session';
import { asrRecognize } from './voiceApi';
import { generateCallId, generateTurnId } from './callUtils';
import { loadVoiceSettings } from './voiceSettingsStorage';
import { useVoiceRecorder } from './useVoiceRecorder';
import { useTTSPlayback } from './useTTSPlayback';
import type { VoiceCallTurn, VoiceCallSessionState } from './voiceTypes';
import { callStateToVoiceState } from './voiceTypes';
import { useTranslation } from 'react-i18next';
import i18n from '../../i18n';
import { DEFAULT_LOCALE, normalizeLocale } from '../../i18n/locale';

export interface UseVoiceCallSessionOptions {
  currentForm: Record<string, unknown>;
  onFormPatch?: (patch: RecommendFormPatch) => void;
  onMessageToChat?: (userText: string, assistantText: string) => void;
}

export interface UseVoiceCallSessionReturn {
  session: VoiceCallSessionState;
  voiceState: ReturnType<typeof callStateToVoiceState>;
  startCall: () => Promise<void>;
  endCall: () => void;
  startRecording: () => Promise<void>;
  stopRecordingAndSend: () => void;
  cancelRecording: () => void;
  sendManualTranscript: (text?: string) => Promise<void>;
  mute: () => void;
  unmute: () => void;
  stopSpeaking: () => void;
  retryLastTurn: () => void;
  openSettings: () => void;
  isRecording: boolean;
  isSupported: boolean;
}

const INITIAL_STATE: VoiceCallSessionState = {
  callId: null,
  sessionId: '',
  state: 'idle',
  startedAt: null,
  endedAt: null,
  durationSeconds: 0,
  turns: [],
  currentTranscript: '',
  currentAssistantText: '',
  isMuted: false,
  isAudioPlaying: false,
  errorMessage: null,
};

export function useVoiceCallSession(options: UseVoiceCallSessionOptions): UseVoiceCallSessionReturn {
  const { t } = useTranslation(['voice', 'common']);
  const { currentForm, onFormPatch, onMessageToChat } = options;

  const [session, setSession] = useState<VoiceCallSessionState>(INITIAL_STATE);
  const sessionRef = useRef(session);
  sessionRef.current = session;

  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);
  const pendingRequestRef = useRef<number | null>(null);
  const requestSequenceRef = useRef(0);
  const callGenerationRef = useRef(0);
  const callActiveRef = useRef(false);
  const renderGeneration = callGenerationRef.current;
  const isCurrentCall = (generation: number) => mountedRef.current && callActiveRef.current && callGenerationRef.current === generation;

  const sessionId = useRef(getSessionId());

  // TTS playback
  const tts = useTTSPlayback({
    sessionId: sessionId.current,
    onPlayStart: () => {
      if (isCurrentCall(renderGeneration)) {
        setSession((s) => ({ ...s, state: 'speaking', isAudioPlaying: true }));
      }
    },
    onPlayEnd: () => {
      if (isCurrentCall(renderGeneration)) {
        setSession((s) => ({ ...s, state: 'ready', isAudioPlaying: false }));
      }
    },
    onError: () => {
      if (isCurrentCall(renderGeneration)) {
        // TTS error doesn't block the conversation
        setSession((s) => ({ ...s, state: 'ready', isAudioPlaying: false }));
      }
    },
  });

  // Voice recorder
  const recorder = useVoiceRecorder({
    recordMode: loadVoiceSettings().record_mode,
    onRecordingComplete: async (audioBlob, durationMs) => {
      if (!mountedRef.current) return;
      const settings = loadVoiceSettings();
      await handleASR(audioBlob, durationMs, settings.asr_language, settings.auto_send_asr);
    },
    onError: (error) => {
      if (mountedRef.current && callActiveRef.current) {
        setSession((s) => ({ ...s, state: 'error', errorMessage: error }));
      }
    },
  });
  const stopTts = tts.stop;
  const cancelRecorder = recorder.cancelRecording;

  // Cleanup on unmount
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      callActiveRef.current = false;
      callGenerationRef.current += 1;
      pendingRequestRef.current = null;
      if (durationTimerRef.current) clearInterval(durationTimerRef.current);
      tts.stop();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Duration timer
  const startDurationTimer = useCallback((generation: number) => {
    if (durationTimerRef.current) clearInterval(durationTimerRef.current);
    durationTimerRef.current = setInterval(() => {
      if (isCurrentCall(generation)) {
        setSession((s) => {
          if (!s.startedAt) return s;
          return { ...s, durationSeconds: Math.floor((Date.now() - s.startedAt) / 1000) };
        });
      }
    }, 1000);
  }, []);

  // Always points to the latest sendToChat so handleASR uses current form state
  const sendToChatRef = useRef<(text: string, generation?: number) => Promise<void>>(() => Promise.resolve());

  // ASR handler
  const handleASR = useCallback(async (audioBlob: Blob, _durationMs: number, language: string, autoSend: boolean) => {
    const generation = callGenerationRef.current;
    if (!isCurrentCall(generation)) return;

    setSession((s) => ({ ...s, state: 'recognizing', errorMessage: null }));

    try {
      const result = await asrRecognize(audioBlob, sessionId.current, language);

      if (!isCurrentCall(generation)) return;

      if (!result.success || !result.text) {
        const errMsg = result.error?.message || t('voice:errors.asrUnavailable');
        setSession((s) => ({ ...s, state: 'error', errorMessage: errMsg }));
        return;
      }

      const text = result.normalized_text || result.text;
      setSession((s) => ({ ...s, currentTranscript: text }));

      if (autoSend) {
        await sendToChatRef.current(text, generation);
      } else {
        setSession((s) => ({ ...s, state: 'ready' }));
      }
    } catch {
      if (isCurrentCall(generation)) {
        setSession((s) => ({ ...s, state: 'error', errorMessage: t('voice:errors.network') }));
      }
    }
  }, [t]);

  // Send ASR text to AI chat
  const sendToChat = useCallback(async (text: string, generation = callGenerationRef.current) => {
    if (!text.trim() || !isCurrentCall(generation) || pendingRequestRef.current !== null) return;
    const requestId = ++requestSequenceRef.current;
    pendingRequestRef.current = requestId;

    setSession((s) => ({ ...s, state: 'thinking', errorMessage: null }));

    const turnId = generateTurnId();
    const turn: VoiceCallTurn = {
      id: turnId,
      userText: text.trim(),
      startedAt: Date.now(),
    };

    try {
      const response = await postAssistantChat({
        session_id: sessionId.current,
        message: text.trim(),
        page_context: {
          view: 'voice_call',
          current_form: currentForm,
        },
        locale: normalizeLocale(i18n.resolvedLanguage) ?? DEFAULT_LOCALE,
      });

      if (!isCurrentCall(generation)) return;

      turn.assistantText = response.reply;
      turn.chatLatencyMs = Date.now() - turn.startedAt;
      turn.endedAt = Date.now();

      // Handle form_patch
      if (response.action?.form_patch) {
        onFormPatch?.(response.action.form_patch);
      }
      if (!isCurrentCall(generation)) return;

      // Add to chat history
      onMessageToChat?.(text.trim(), response.reply);
      if (!isCurrentCall(generation)) return;

      setSession((s) => ({
        ...s,
        turns: [...s.turns, turn],
        currentAssistantText: response.reply,
      }));

      // Auto-TTS if enabled
      const settings = loadVoiceSettings();
      if (settings.tts_enabled && response.reply) {
        await tts.speak(response.reply);
        // TTS callbacks will handle state transitions
      } else {
        setSession((s) => ({ ...s, state: 'ready' }));
      }
    } catch {
      if (isCurrentCall(generation)) {
        turn.error = t('voice:errors.network');
        turn.endedAt = Date.now();
        setSession((s) => ({
          ...s,
          state: 'error',
          errorMessage: t('voice:errors.network'),
          turns: [...s.turns, turn],
        }));
      }
    } finally {
      if (pendingRequestRef.current === requestId) pendingRequestRef.current = null;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentForm, onFormPatch, onMessageToChat, t, tts.speak]);

  // Keep ref current so handleASR always calls with latest currentForm
  sendToChatRef.current = sendToChat;

  // Public API
  const startCall = useCallback(async () => {
    const curState = sessionRef.current.state;
    if (curState !== 'idle' && curState !== 'ended' && curState !== 'error') return;

    // Request microphone permission
    stopTts();
    cancelRecorder();
    if (durationTimerRef.current) clearInterval(durationTimerRef.current);
    const generation = ++callGenerationRef.current;
    callActiveRef.current = true;
    pendingRequestRef.current = null;
    setSession({
      ...INITIAL_STATE,
      state: 'requesting_permission',
      sessionId: sessionId.current,
    });

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop()); // Release immediately

      if (!isCurrentCall(generation)) return;

      const callId = generateCallId();
      setSession((s) => ({
        ...s,
        callId,
        state: 'ready',
        startedAt: Date.now(),
      }));
      startDurationTimer(generation);
    } catch (err: unknown) {
      if (!isCurrentCall(generation)) return;
      const msg = err instanceof Error ? err.message : String(err);
      let errorMsg = t('voice:errors.micPermission');
      if (msg.includes('NotFoundError')) {
        errorMsg = t('voice:errors.unsupported');
      }
      setSession((s) => ({ ...s, state: 'error', errorMessage: errorMsg }));
    }
  }, [startDurationTimer, t, stopTts, cancelRecorder]);

  const endCall = useCallback(() => {
    callActiveRef.current = false;
    callGenerationRef.current += 1;
    pendingRequestRef.current = null;
    if (durationTimerRef.current) {
      clearInterval(durationTimerRef.current);
      durationTimerRef.current = null;
    }
    stopTts();
    cancelRecorder();

    setSession((s) => ({
      ...s,
      state: 'ended',
      endedAt: Date.now(),
      isAudioPlaying: false,
    }));
  }, [stopTts, cancelRecorder]);

  const startRecordingFn = useCallback(async () => {
    if (!callActiveRef.current) return;
    const s = sessionRef.current.state;
    if (s !== 'ready' && s !== 'error') return;
    if (s === 'error') {
      setSession((prev) => ({ ...prev, errorMessage: null }));
    }
    tts.stop();
    setSession((prev) => ({ ...prev, state: 'listening', currentTranscript: '' }));
    await recorder.startRecording();
  }, [recorder, tts]);

  const stopRecordingAndSend = useCallback(() => {
    recorder.stopRecording();
  }, [recorder]);

  const cancelRecordingFn = useCallback(() => {
    recorder.cancelRecording();
    setSession((prev) => ({ ...prev, state: 'ready', currentTranscript: '' }));
  }, [recorder]);

  const mute = useCallback(() => {
    tts.stop();
    setSession((prev) => ({ ...prev, isMuted: true, state: 'muted', isAudioPlaying: false }));
  }, [tts]);

  const unmute = useCallback(() => {
    setSession((prev) => ({ ...prev, isMuted: false, state: 'ready' }));
  }, []);

  const stopSpeaking = useCallback(() => {
    tts.stop();
    setSession((prev) => ({ ...prev, state: 'ready', isAudioPlaying: false }));
  }, [tts]);

  const retryLastTurn = useCallback(() => {
    const turns = sessionRef.current.turns;
    if (turns.length === 0) return;
    const lastTurn = turns[turns.length - 1];
    if (lastTurn.userText) {
      void sendToChat(lastTurn.userText);
    }
  }, [sendToChat]);

  const openSettings = useCallback(() => {
    // Settings panel is toggled externally; this is a no-op signal
  }, []);

  const sendManualTranscript = useCallback(async (text?: string) => {
    const textToSend = text?.trim() || sessionRef.current.currentTranscript.trim();
    if (!textToSend) return;
    await sendToChat(textToSend);
  }, [sendToChat]);

  return {
    session,
    voiceState: callStateToVoiceState(session.state),
    startCall,
    endCall,
    startRecording: startRecordingFn,
    stopRecordingAndSend,
    cancelRecording: cancelRecordingFn,
    sendManualTranscript,
    mute,
    unmute,
    stopSpeaking,
    retryLastTurn,
    openSettings,
    isRecording: recorder.isRecording,
    isSupported: recorder.isSupported,
  };
}
