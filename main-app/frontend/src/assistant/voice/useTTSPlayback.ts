/* Hook for TTS audio playback — manages Audio element lifecycle */

import { useCallback, useEffect, useRef, useState } from 'react';
import { ttsSynthesize, buildTTSUrl } from './voiceApi';
import { loadVoiceSettings } from './voiceSettingsStorage';
import { useTranslation } from 'react-i18next';

export interface UseTTSPlaybackOptions {
  sessionId: string;
  onPlayStart?: () => void;
  onPlayEnd?: () => void;
  onError?: (error: string) => void;
}

export interface UseTTSPlaybackReturn {
  isPlaying: boolean;
  /** If autoplay was blocked, this holds the URL the user must click to play */
  pendingPlayUrl: string | null;
  speak: (text: string) => Promise<void>;
  stop: () => void;
  /** Call when user clicks the "play" button after autoplay blocked */
  playPending: () => void;
}

export function useTTSPlayback(options: UseTTSPlaybackOptions): UseTTSPlaybackReturn {
  const { t } = useTranslation('voice');
  const { sessionId, onPlayStart, onPlayEnd, onError } = options;
  const [isPlaying, setIsPlaying] = useState(false);
  const [pendingPlayUrl, setPendingPlayUrl] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const mountedRef = useRef(true);
  const lastTextRef = useRef<string>('');
  // Incremented on every speak() and stop() so stale async responses are discarded
  const seqRef = useRef(0);

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
  }, []);

  const stop = useCallback(() => {
    seqRef.current += 1;
    stopInternal();
    if (mountedRef.current) {
      setIsPlaying(false);
      setPendingPlayUrl(null);
    }
  }, [stopInternal]);

  const speak = useCallback(async (text: string) => {
    if (!text.trim()) return;
    // Avoid re-speaking same text if already playing
    if (text === lastTextRef.current && isPlaying) return;
    lastTextRef.current = text;

    // Bump generation and stop any current playback
    seqRef.current += 1;
    const mySeq = seqRef.current;
    stopInternal();
    setPendingPlayUrl(null);

    const settings = loadVoiceSettings();
    if (!settings.tts_enabled) return;

    try {
      const result = await ttsSynthesize({
        sessionId,
        text: text.trim(),
        voice: settings.preset_voice,
        format: 'wav',
        voiceSource: settings.voice_source,
        cloneVoiceId: settings.clone_voice_id || undefined,
        tonePreset: settings.tone_preset,
        volume: settings.volume,
      });

      // Discard if a newer speak()/stop() arrived while awaiting
      if (!mountedRef.current || seqRef.current !== mySeq) return;

      if (!result.success || !result.audio_url) {
        const errMsg = result.error?.message || t('errors.network');
        onError?.(errMsg);
        return;
      }

      const fullUrl = buildTTSUrl(result.audio_url);
      const audio = new Audio(fullUrl);
      audio.volume = settings.volume;
      audioRef.current = audio;

      audio.onplay = () => {
        if (mountedRef.current && seqRef.current === mySeq) {
          setIsPlaying(true);
          onPlayStart?.();
        }
      };

      audio.onended = () => {
        if (mountedRef.current && seqRef.current === mySeq) {
          stopInternal();
          setIsPlaying(false);
          onPlayEnd?.();
        }
      };

      audio.onerror = () => {
        if (mountedRef.current && seqRef.current === mySeq) {
          stopInternal();
          setIsPlaying(false);
          onError?.(t('errors.network'));
          onPlayEnd?.();
        }
      };

      try {
        await audio.play();
      } catch {
        // Autoplay blocked by browser — show "click to play" button cleanly without false network error
        if (mountedRef.current && seqRef.current === mySeq) {
          setPendingPlayUrl(fullUrl);
          onPlayEnd?.();
        }
        return;
      }
    } catch {
      if (mountedRef.current && seqRef.current === mySeq) {
        stopInternal();
        setIsPlaying(false);
        onError?.(t('errors.network'));
      }
    }
  }, [sessionId, isPlaying, stopInternal, onPlayStart, onPlayEnd, onError, t]);

  const playPending = useCallback(() => {
    if (!pendingPlayUrl) return;
    const url = pendingPlayUrl;
    setPendingPlayUrl(null);
    seqRef.current += 1;
    const mySeq = seqRef.current;

    const audio = new Audio(url);
    const settings = loadVoiceSettings();
    audio.volume = settings.volume;
    audioRef.current = audio;

    audio.onplay = () => {
      if (mountedRef.current && seqRef.current === mySeq) { setIsPlaying(true); onPlayStart?.(); }
    };
    audio.onended = () => {
      if (mountedRef.current && seqRef.current === mySeq) { stopInternal(); setIsPlaying(false); onPlayEnd?.(); }
    };
    audio.onerror = () => {
      if (mountedRef.current && seqRef.current === mySeq) { stopInternal(); setIsPlaying(false); onError?.(t('errors.network')); onPlayEnd?.(); }
    };

    audio.play().catch(() => {
      if (mountedRef.current && seqRef.current === mySeq) { onError?.(t('errors.network')); }
    });
  }, [pendingPlayUrl, stopInternal, onPlayStart, onPlayEnd, onError, t]);

  return { isPlaying, pendingPlayUrl, speak, stop, playPending };
}
