import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ chat: vi.fn(), asr: vi.fn(), speak: vi.fn(), stop: vi.fn(), translate: (value: string) => value, recorderOptions: null as null | { onRecordingComplete: (blob: Blob, duration: number) => Promise<void> } }));
vi.mock('../../api', () => ({ postAssistantChat: mocks.chat }));
vi.mock('../../i18n', () => ({ default: { resolvedLanguage: 'en' } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: mocks.translate }) }));
vi.mock('./voiceApi', () => ({ asrRecognize: mocks.asr }));
vi.mock('./useVoiceRecorder', () => ({ useVoiceRecorder: (options: { onRecordingComplete: (blob: Blob, duration: number) => Promise<void> }) => {
  mocks.recorderOptions = options;
  return { cancelRecording: vi.fn(), startRecording: vi.fn(), stopRecording: vi.fn(), isRecording: false, isSupported: true };
} }));
vi.mock('./useTTSPlayback', () => ({ useTTSPlayback: (options: { onPlayStart: () => void; onPlayEnd: () => void }) => ({ speak: (text: string) => mocks.speak(text, options), stop: mocks.stop }) }));
vi.mock('./voiceSettingsStorage', () => ({ loadVoiceSettings: () => ({ record_mode: 'hold', tts_enabled: true, auto_send_asr: true, asr_language: 'zh' }) }));

import { useVoiceCallSession } from './useVoiceCallSession';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
const track = { stop: vi.fn() };
const fakeStream = { getTracks: () => [track] };

beforeEach(() => { vi.clearAllMocks(); mocks.speak.mockResolvedValue(undefined); });

describe('voice call generations', () => {
  it('does not revive a call after late microphone permission', async () => {
    const permission = deferred<unknown>();
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: () => permission.promise } });
    const { result, unmount } = renderHook(() => useVoiceCallSession({ currentForm: {} }));
    let start!: Promise<void>;
    act(() => { start = result.current.startCall(); });
    act(() => result.current.endCall());
    await act(async () => { permission.resolve(fakeStream); await start; });
    expect(track.stop).toHaveBeenCalled();
    expect(result.current.session.state).toBe('ended');
    unmount();
  });

  it('ignores old chat responses and keeps a newer request pending', async () => {
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: async () => fakeStream } });
    const oldReply = deferred<unknown>();
    const newReply = deferred<unknown>();
    mocks.chat.mockReturnValueOnce(oldReply.promise).mockReturnValueOnce(newReply.promise);
    const patch = vi.fn(); const message = vi.fn();
    const { result, unmount } = renderHook(() => useVoiceCallSession({ currentForm: {}, onFormPatch: patch, onMessageToChat: message }));
    await act(async () => { await result.current.startCall(); });
    let oldSend!: Promise<void>; let newSend!: Promise<void>;
    act(() => { oldSend = result.current.sendManualTranscript('old call'); });
    act(() => result.current.endCall());
    await act(async () => { await result.current.startCall(); });
    act(() => { newSend = result.current.sendManualTranscript('new call'); });
    await act(async () => { oldReply.resolve({ reply: 'old response', action: { form_patch: { size: 'L' } } }); await oldSend; });
    expect(result.current.session.turns).toHaveLength(0);
    expect(patch).not.toHaveBeenCalled(); expect(message).not.toHaveBeenCalled(); expect(mocks.speak).not.toHaveBeenCalled();
    await act(async () => { await result.current.sendManualTranscript('must wait'); });
    expect(mocks.chat).toHaveBeenCalledTimes(2);
    await act(async () => { newReply.resolve({ reply: 'new response', action: {} }); await newSend; });
    expect(result.current.session.turns[0]?.assistantText).toBe('new response');
    expect(message).toHaveBeenCalledWith('new call', 'new response');
    unmount();
  });

  it('ignores speech recognition completed after a new call starts', async () => {
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: async () => fakeStream } });
    const recognition = deferred<unknown>(); mocks.asr.mockReturnValue(recognition.promise);
    const { result, unmount } = renderHook(() => useVoiceCallSession({ currentForm: {} }));
    await act(async () => { await result.current.startCall(); });
    let recognize!: Promise<void>;
    const recorderOptions = mocks.recorderOptions;
    if (!recorderOptions) throw new Error('recorder was not initialized');
    act(() => { recognize = recorderOptions.onRecordingComplete(new Blob(['audio']), 500); });
    act(() => result.current.endCall());
    await act(async () => { await result.current.startCall(); });
    await act(async () => { recognition.resolve({ success: true, text: 'old speech' }); await recognize; });
    expect(result.current.session.currentTranscript).toBe('');
    expect(mocks.chat).not.toHaveBeenCalled();
    unmount();
  });

  it('uses the current call generation for playback callbacks', async () => {
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: async () => fakeStream } });
    mocks.chat.mockResolvedValue({ reply: 'answer', action: {} });
    mocks.speak.mockImplementation(async (_text: string, options: { onPlayStart: () => void; onPlayEnd: () => void }) => {
      options.onPlayStart();
      options.onPlayEnd();
    });
    const currentForm = {};
    const { result, unmount } = renderHook(() => useVoiceCallSession({ currentForm }));
    await act(async () => { await result.current.startCall(); });
    await act(async () => { await result.current.sendManualTranscript('hello'); });
    expect(result.current.session.state).toBe('ready');
    unmount();
  });
});
