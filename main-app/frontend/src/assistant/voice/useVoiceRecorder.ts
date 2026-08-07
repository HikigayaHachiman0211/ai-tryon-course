/* Hook for browser audio recording — supports click and hold-to-talk modes.
 *
 * Records using MediaRecorder (browser-native format, typically webm/opus).
 * On stop, converts the recording to 16-bit PCM WAV via Web Audio API
 * before calling onRecordingComplete — ensuring MiMo ASR compatibility.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { convertToWav, isWavBlob } from './audioEncoding';

export interface UseVoiceRecorderOptions {
  maxRecordSeconds?: number;
  hardMaxRecordSeconds?: number;
  recordMode?: 'click' | 'hold';
  onRecordingComplete?: (audioBlob: Blob, durationMs: number) => void;
  onError?: (error: string) => void;
}

export interface UseVoiceRecorderReturn {
  isRecording: boolean;
  isSupported: boolean;
  startRecording: () => Promise<void>;
  stopRecording: () => void;
  cancelRecording: () => void;
  durationMs: number;
}

function checkSupport(): boolean {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
    return false;
  }
  if (typeof MediaRecorder === 'undefined') {
    return false;
  }
  return true;
}

export function useVoiceRecorder(options: UseVoiceRecorderOptions = {}): UseVoiceRecorderReturn {
  const {
    maxRecordSeconds = 15,
    hardMaxRecordSeconds = 55,
    onRecordingComplete,
    onError,
  } = options;

  const [isRecording, setIsRecording] = useState(false);
  const [durationMs, setDurationMs] = useState(0);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const softTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hardTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startTimeRef = useRef<number>(0);
  const mountedRef = useRef(true);
  const processingRef = useRef(false);
  const startGuardRef = useRef(false);

  const cleanup = useCallback(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    if (softTimerRef.current) { clearTimeout(softTimerRef.current); softTimerRef.current = null; }
    if (hardTimerRef.current) { clearTimeout(hardTimerRef.current); hardTimerRef.current = null; }
    if (recorderRef.current) {
      // Detach handlers before stopping tracks — stopping tracks fires onstop
      // asynchronously, which would report a spurious empty-recording error
      recorderRef.current.ondataavailable = null;
      recorderRef.current.onstop = null;
      recorderRef.current.onerror = null;
      recorderRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    chunksRef.current = [];
    startGuardRef.current = false;
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      cleanup();
    };
  }, [cleanup]);

  const processRecording = useCallback(async (rawBlob: Blob, duration: number) => {
    if (processingRef.current) return;
    processingRef.current = true;

    try {
      let wavBlob: Blob;

      if (isWavBlob(rawBlob)) {
        // Already WAV — use directly
        wavBlob = rawBlob;
      } else {
        // Convert webm/ogg/mp4 to WAV via Web Audio API
        wavBlob = await convertToWav(rawBlob);
      }

      if (mountedRef.current) {
        setIsRecording(false);
        setDurationMs(duration);
        onRecordingComplete?.(wavBlob, duration);
      }
    } catch (err: unknown) {
      if (mountedRef.current) {
        setIsRecording(false);
        setDurationMs(0);
        const msg = err instanceof Error ? err.message : String(err);
        if (msg === 'DECODE_FAILED') {
          onError?.('当前浏览器录音格式暂不支持，请切换浏览器或使用文字输入。');
        } else {
          onError?.('录音处理失败，请重试或使用文字输入。');
        }
      }
    } finally {
      processingRef.current = false;
    }
  }, [onRecordingComplete, onError]);

  const startRecording = useCallback(async () => {
    // Ref-based guard: state updates lag double-clicks, which would open two
    // concurrent getUserMedia flows and leak the first stream's tracks
    if (isRecording || startGuardRef.current) return;
    startGuardRef.current = true;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Record in whatever format the browser supports
      const mimeType = pickBestMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        const chunks = [...chunksRef.current];
        const duration = Date.now() - startTimeRef.current;
        cleanup();

        if (chunks.length === 0) {
          if (mountedRef.current) {
            setIsRecording(false);
            setDurationMs(0);
            onError?.('录音为空，请重试。');
          }
          return;
        }

        const rawBlob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
        void processRecording(rawBlob, duration);
      };

      recorder.onerror = () => {
        cleanup();
        if (mountedRef.current) {
          setIsRecording(false);
          setDurationMs(0);
          onError?.('录音出错，请重试。');
        }
      };

      startTimeRef.current = Date.now();
      recorder.start(100);
      setIsRecording(true);
      setDurationMs(0);

      // Duration display timer
      timerRef.current = setInterval(() => {
        if (mountedRef.current) {
          setDurationMs(Date.now() - startTimeRef.current);
        }
      }, 200);

      // Soft limit — auto-stop at maxRecordSeconds
      softTimerRef.current = setTimeout(() => {
        if (recorderRef.current?.state === 'recording') {
          recorderRef.current.stop();
        }
      }, maxRecordSeconds * 1000);

      // Hard limit — absolute maximum
      hardTimerRef.current = setTimeout(() => {
        if (recorderRef.current?.state === 'recording') {
          recorderRef.current.stop();
        }
      }, hardMaxRecordSeconds * 1000);

    } catch (err: unknown) {
      cleanup();
      if (mountedRef.current) {
        setIsRecording(false);
        setDurationMs(0);
      }
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes('NotAllowedError') || msg.includes('Permission')) {
        onError?.('无法使用麦克风。请在浏览器地址栏允许麦克风权限，或改用文字聊天。');
      } else if (msg.includes('NotFoundError')) {
        onError?.('未检测到麦克风设备，请检查设备连接。');
      } else {
        onError?.('录音启动失败，请重试或使用文字输入。');
      }
    }
  }, [isRecording, maxRecordSeconds, hardMaxRecordSeconds, cleanup, processRecording, onError]);

  const stopRecording = useCallback(() => {
    if (recorderRef.current?.state === 'recording') {
      recorderRef.current.stop();
    }
  }, []);

  const cancelRecording = useCallback(() => {
    cleanup();
    processingRef.current = false;
    if (mountedRef.current) {
      setIsRecording(false);
      setDurationMs(0);
    }
  }, [cleanup]);

  return {
    isRecording,
    isSupported: checkSupport(),
    startRecording,
    stopRecording,
    cancelRecording,
    durationMs,
  };
}

function pickBestMimeType(): string | undefined {
  // Prefer formats that decodeAudioData can handle well
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4',
  ];
  for (const type of candidates) {
    if (MediaRecorder.isTypeSupported(type)) return type;
  }
  return undefined;
}
