/* Hook for per-message TTS playback — manages single-message audio lifecycle */

import { useCallback, useEffect, useRef, useState } from 'react';
import { ttsSynthesize, buildTTSUrl } from './voiceApi';
import { loadVoiceSettings } from './voiceSettingsStorage';

export interface UseMessageTTSReturn {
  /** ID of the message currently being loaded (TTS request in flight) */
  loadingMessageId: string | null;
  /** ID of the message currently playing */
  playingMessageId: string | null;
  /** Whether any message TTS is active (loading or playing) */
  isBusy: boolean;
  /** Play a specific message by ID and text */
  playMessage: (messageId: string, text: string) => Promise<void>;
  /** Stop current playback */
  stop: () => void;
}

export function useMessageTTS(sessionId: string): UseMessageTTSReturn {
  const [loadingMessageId, setLoadingMessageId] = useState<string | null>(null);
  const [playingMessageId, setPlayingMessageId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const mountedRef = useRef(true);
  const activeMessageRef = useRef<string | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      stopInternal();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stopInternal = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current.src = '';
      audioRef.current = null;
    }
    activeMessageRef.current = null;
  }, []);

  const stop = useCallback(() => {
    stopInternal();
    if (mountedRef.current) {
      setLoadingMessageId(null);
      setPlayingMessageId(null);
    }
  }, [stopInternal]);

  const playMessage = useCallback(async (messageId: string, text: string) => {
    if (!text.trim()) return;

    // If clicking same message that's playing, stop it
    if (playingMessageId === messageId) {
      stop();
      return;
    }

    // If clicking same message that's loading, ignore
    if (loadingMessageId === messageId) return;

    // Stop any current playback
    stopInternal();
    if (mountedRef.current) {
      setLoadingMessageId(messageId);
      setPlayingMessageId(null);
    }
    activeMessageRef.current = messageId;

    const settings = loadVoiceSettings();

    // Truncate text to max length
    let ttsText = text.trim();
    const maxLen = settings.max_tts_text_length || 300;
    if (ttsText.length > maxLen) {
      ttsText = ttsText.slice(0, maxLen) + '……';
    }

    try {
      const result = await ttsSynthesize({
        sessionId,
        text: ttsText,
        voice: settings.preset_voice,
        format: 'wav',
        voiceSource: settings.voice_source,
        cloneVoiceId: settings.clone_voice_id || undefined,
        tonePreset: settings.tone_preset,
        volume: settings.volume,
      });

      if (!mountedRef.current || activeMessageRef.current !== messageId) return;

      if (!result.success || !result.audio_url) {
        const errMsg = result.error?.message || '语音播报暂不可用，文字回复仍可查看。';
        // Dispatch a custom event so the UI can show the error
        window.dispatchEvent(new CustomEvent('message-tts-error', { detail: { messageId, error: errMsg } }));
        if (mountedRef.current) {
          setLoadingMessageId(null);
        }
        return;
      }

      const fullUrl = buildTTSUrl(result.audio_url);
      const audio = new Audio(fullUrl);
      audio.volume = settings.volume;
      audioRef.current = audio;

      audio.onplay = () => {
        if (mountedRef.current && activeMessageRef.current === messageId) {
          setLoadingMessageId(null);
          setPlayingMessageId(messageId);
        }
      };

      audio.onended = () => {
        stopInternal();
        if (mountedRef.current) {
          setLoadingMessageId(null);
          setPlayingMessageId(null);
        }
      };

      audio.onerror = () => {
        stopInternal();
        if (mountedRef.current) {
          setLoadingMessageId(null);
          setPlayingMessageId(null);
          window.dispatchEvent(new CustomEvent('message-tts-error', { detail: { messageId, error: '音频播放失败。' } }));
        }
      };

      try {
        await audio.play();
      } catch {
        // Autoplay blocked
        if (mountedRef.current && activeMessageRef.current === messageId) {
          setLoadingMessageId(null);
          window.dispatchEvent(new CustomEvent('message-tts-error', { detail: { messageId, error: '浏览器拦截了自动播放，请点击消息播报按钮重试。' } }));
        }
      }
    } catch {
      if (mountedRef.current && activeMessageRef.current === messageId) {
        setLoadingMessageId(null);
        window.dispatchEvent(new CustomEvent('message-tts-error', { detail: { messageId, error: '语音播报暂不可用，文字回复仍可查看。' } }));
      }
    }
  }, [sessionId, playingMessageId, loadingMessageId, stopInternal, stop]);

  return {
    loadingMessageId,
    playingMessageId,
    isBusy: loadingMessageId !== null || playingMessageId !== null,
    playMessage,
    stop,
  };
}
