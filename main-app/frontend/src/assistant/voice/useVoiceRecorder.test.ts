import { act, renderHook } from '@testing-library/react';
import { expect, it, vi } from 'vitest';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (value: string) => value }) }));
import { useVoiceRecorder } from './useVoiceRecorder';

it('releases a microphone permission response after recording is cancelled', async () => {
  let resolve!: (value: unknown) => void;
  const permission = new Promise(done => { resolve = done; });
  const stop = vi.fn();
  const MediaRecorderMock = vi.fn();
  Object.assign(MediaRecorderMock, { isTypeSupported: () => true });
  vi.stubGlobal('MediaRecorder', MediaRecorderMock);
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: () => permission } });
  const { result, unmount } = renderHook(() => useVoiceRecorder());
  let start!: Promise<void>;
  act(() => { start = result.current.startRecording(); });
  act(() => result.current.cancelRecording());
  await act(async () => { resolve({ getTracks: () => [{ stop }] }); await start; });
  expect(stop).toHaveBeenCalled();
  expect(MediaRecorderMock).not.toHaveBeenCalled();
  expect(result.current.isRecording).toBe(false);
  unmount();
  vi.unstubAllGlobals();
});
