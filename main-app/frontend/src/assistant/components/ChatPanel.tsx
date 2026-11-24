import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, Settings, Sparkles, Trash2, Maximize2, X } from 'lucide-react';
import type { RecommendFormPatch } from '../assistantTypes';
import { useAssistantChat } from '../hooks/useAssistantChat';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { RecommendActionCard } from './RecommendActionCard';
import { VoiceInputButton } from '../voice/VoiceInputButton';
import { TTSControls } from '../voice/TTSControls';
import { CallButton } from '../voice/CallButton';
import { CallModePanel } from '../voice/CallModePanel';
import { VoiceSettingsPanel } from '../voice/VoiceSettingsPanel';
import { useVoiceRecorder } from '../voice/useVoiceRecorder';
import { useTTSPlayback } from '../voice/useTTSPlayback';
import { useAssistantVoiceConfig } from '../voice/useAssistantVoiceConfig';
import { useVoiceCallSession } from '../voice/useVoiceCallSession';
import { useMessageTTS } from '../voice/useMessageTTS';
import { loadVoiceSettings, saveVoiceSettings } from '../voice/voiceSettingsStorage';
import { asrRecognize } from '../voice/voiceApi';
import { getSessionId } from '../utils/session';
import type { AssistantVoiceState } from '../voice/voiceTypes';
import { useResizablePanel, type PanelSizePreset, type UseResizablePanelReturn } from '../hooks/useResizablePanel';
import { useTranslation } from 'react-i18next';

interface Props {
  currentView: string;
  currentForm: Record<string, unknown>;
  onFormPatch: (patch: RecommendFormPatch) => void;
  onSubmitRecommend: () => void;
  onFillAndSubmit: (patch: RecommendFormPatch) => void;
  onClose: () => void;
  panel?: UseResizablePanelReturn;
  isMobile?: boolean;
}

const SIZE_PRESET_LABELS: Record<PanelSizePreset, string> = {
  compact: 'sizePreset.compact',
  default: 'sizePreset.default',
  large: 'sizePreset.large',
  wide: 'sizePreset.wide',
  custom: 'sizePreset.custom',
};

export const ChatPanel: React.FC<Props> = ({
  currentView,
  currentForm,
  onFormPatch,
  onFillAndSubmit,
  onClose,
  panel: externalPanel,
  isMobile = false,
}) => {
  const { t } = useTranslation(['assistant', 'voice']);
  const { messages, loading, error, sendMessage, clearMessages } = useAssistantChat(currentView, currentForm);
  const { config: voiceConfig } = useAssistantVoiceConfig();

  // Use state for ttsEnabled so TTSControls re-renders properly
  const [ttsEnabled, setTtsEnabled] = useState(() => loadVoiceSettings().tts_enabled);
  const [voiceState, setVoiceState] = useState<AssistantVoiceState>('idle');
  const [showVoiceSettings, setShowVoiceSettings] = useState(false);
  const [showCallMode, setShowCallMode] = useState(false);
  const [showSizePresets, setShowSizePresets] = useState(false);
  const [lastFormPatch, setLastFormPatch] = useState<RecommendFormPatch | null>(null);
  const [ttsError, setTtsError] = useState<string | null>(null);

  const settingsRef = useRef(loadVoiceSettings());
  const lastSpokenIdRef = useRef<string>('');

  // Resizable panel
  const internalPanel = useResizablePanel();
  const panel = externalPanel ?? internalPanel;

  // Per-message TTS
  const messageTTS = useMessageTTS(getSessionId());

  // Listen for message TTS errors
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.error) {
        setTtsError(detail.error);
      }
    };
    window.addEventListener('message-tts-error', handler);
    return () => window.removeEventListener('message-tts-error', handler);
  }, []);

  // TTS playback (auto-speak for new assistant messages)
  const tts = useTTSPlayback({
    sessionId: getSessionId(),
    onPlayStart: () => setVoiceState('speaking'),
    onPlayEnd: () => setVoiceState('idle'),
    onError: (msg) => {
      setTtsError(msg);
      setVoiceState('idle');
    },
  });

  // Voice recorder for normal mode
  const recorder = useVoiceRecorder({
    recordMode: settingsRef.current.record_mode,
    onRecordingComplete: async (audioBlob) => {
      setVoiceState('recognizing');
      try {
        const result = await asrRecognize(audioBlob, getSessionId(), settingsRef.current.asr_language);
        if (result.success && result.text) {
          const text = result.normalized_text || result.text;
          sendMessage(text);
          // If auto-TTS will speak, the auto-TTS effect sets 'thinking'; otherwise stay idle
          // so the mic button is re-enabled immediately
          setVoiceState('idle');
        } else {
          setVoiceState('error');
          setTtsError(result.error?.message || t('voice:errors.asrUnavailable'));
        }
      } catch {
        setVoiceState('error');
        setTtsError(t('voice:errors.network'));
      }
    },
    onError: (msg) => {
      setVoiceState('error');
      setTtsError(msg);
    },
  });

  // Voice call session
  const callSession = useVoiceCallSession({
    currentForm,
    onFormPatch: (patch) => {
      onFormPatch(patch);
      setLastFormPatch(patch);
    },
    onMessageToChat: () => {
      // Optionally add to main chat — for now just keep in call turns
    },
  });

  // Auto-TTS for new assistant messages
  useEffect(() => {
    const settings = loadVoiceSettings();
    settingsRef.current = settings;

    if (!settings.tts_enabled || !settings.auto_tts_enabled) return;
    if (messages.length === 0) return;

    const lastMsg = messages[messages.length - 1];
    if (lastMsg.role !== 'assistant') return;
    if (lastMsg.id === lastSpokenIdRef.current) return;
    if (!lastMsg.content || lastMsg.content.length > settings.max_tts_text_length) return;

    lastSpokenIdRef.current = lastMsg.id;

    // Single-audio policy: stop per-message playback before auto-narration
    messageTTS.stop();
    setVoiceState('thinking');

    void tts.speak(lastMsg.content);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  // Wrap playMessage to enforce single-audio policy: stop auto-narration first
  const handlePlayMessageTTS = useCallback((id: string, text: string) => {
    tts.stop();
    return messageTTS.playMessage(id, text);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messageTTS.playMessage]);

  const messageTTSWithPolicy = { ...messageTTS, playMessage: handlePlayMessageTTS };

  const handleFillForm = useCallback((patch: RecommendFormPatch) => {
    onFormPatch(patch);
  }, [onFormPatch]);

  const handleFillAndSubmit = useCallback((patch: RecommendFormPatch) => {
    onFillAndSubmit(patch);
  }, [onFillAndSubmit]);

  const handleToggleTTS = useCallback(() => {
    const settings = loadVoiceSettings();
    const next = !settings.tts_enabled;
    saveVoiceSettings({ tts_enabled: next, auto_tts_enabled: next });
    settingsRef.current = { ...settings, tts_enabled: next, auto_tts_enabled: next };
    setTtsEnabled(next);
    if (!next) {
      tts.stop();
      messageTTS.stop();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCloseCall = useCallback(() => {
    callSession.endCall();
    setShowCallMode(false);
  }, [callSession]);

  const handleClosePanel = useCallback(() => {
    // Clean up voice resources
    recorder.cancelRecording();
    tts.stop();
    messageTTS.stop();
    if (showCallMode) {
      callSession.endCall();
      setShowCallMode(false);
    }
    onClose();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onClose, showCallMode]);

  const lastAssistantWithAction = [...messages]
    .reverse()
    .find((m) => m.role === 'assistant' && m.action?.type === 'fill_recommend_form' && m.action.form_patch);

  // Call mode overlay
  if (showCallMode) {
    return (
      <CallModePanel
        session={callSession.session}
        voiceState={callSession.voiceState}
        isRecording={callSession.isRecording}
        lastFormPatch={lastFormPatch}
        onStartRecording={callSession.startRecording}
        onStopRecording={callSession.stopRecordingAndSend}
        onCancelRecording={callSession.cancelRecording}
        onMute={callSession.mute}
        onUnmute={callSession.unmute}
        onStopSpeaking={callSession.stopSpeaking}
        onRetry={callSession.retryLastTurn}
        onEndCall={handleCloseCall}
        onBackToChat={() => {
          callSession.endCall();
          setShowCallMode(false);
        }}
        onFillForm={handleFillForm}
        onFillAndSubmit={handleFillAndSubmit}
        onDismissFormPatch={() => setLastFormPatch(null)}
        onSendManualText={(text) => void callSession.sendManualTranscript(text)}
      />
    );
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      width: '100%',
      background: 'rgba(18, 18, 20, 0.98)',
      borderRadius: isMobile ? '20px 20px 0 0' : 20,
      overflow: 'hidden',
      position: 'relative',
    }}>
      {/* Voice settings overlay */}
      {showVoiceSettings && <VoiceSettingsPanel onClose={() => setShowVoiceSettings(false)} />}

      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 8,
        padding: isMobile ? '12px 14px' : '14px 16px',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        background: 'rgba(0,0,0,0.3)',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          <Sparkles size={16} color="#0071e3" style={{ flexShrink: 0 }} />
          <span style={{ fontSize: 14, fontWeight: 600, color: '#F8FAFC', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t('header')}</span>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
          {/* Call button */}
          <CallButton
            isInCall={false}
            isSupported={voiceConfig.asr_enabled}
            disabledReason={voiceConfig.asr_disabled_reason}
            onClick={() => {
              if (!voiceConfig.asr_enabled) {
                return;
              }
              // Single-audio policy: stop any current narration before entering call mode
              tts.stop();
              messageTTS.stop();
              setShowCallMode(true);
              void callSession.startCall();
            }}
          />

          {/* TTS controls */}
          <TTSControls
            ttsEnabled={ttsEnabled}
            isPlaying={tts.isPlaying}
            onToggleTTS={handleToggleTTS}
            onStop={tts.stop}
          />

          {/* Size presets (desktop only) */}
          {!isMobile && (
            <div style={{ position: 'relative' }}>
              <button
                type="button"
                onClick={() => setShowSizePresets(!showSizePresets)}
                title={t('windowSize')}
                aria-label={t('windowSize')}
                style={{
                  width: 36, height: 36, borderRadius: 8,
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid rgba(255,255,255,0.08)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', color: 'rgba(255,255,255,0.5)',
                }}
              >
                <Maximize2 size={14} />
              </button>
              {showSizePresets && (
                <div style={{
                  position: 'absolute',
                  top: '100%',
                  right: 0,
                  marginTop: 4,
                  background: 'rgba(28, 28, 30, 0.98)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: 12,
                  padding: 6,
                  zIndex: 999,
                  minWidth: 120,
                  boxShadow: '0 8px 30px rgba(0,0,0,0.5)',
                }}>
                  {(Object.keys(SIZE_PRESET_LABELS) as PanelSizePreset[])
                    .filter(k => k !== 'custom')
                    .map((preset) => (
                      <button
                        type="button"
                        key={preset}
                        onClick={() => {
                          panel.setPreset(preset);
                          setShowSizePresets(false);
                        }}
                        style={{
                          display: 'block',
                          width: '100%',
                          padding: '8px 12px',
                          borderRadius: 8,
                          border: 'none',
                          background: panel.preset === preset ? 'rgba(0, 113, 227, 0.2)' : 'transparent',
                          color: panel.preset === preset ? '#0071e3' : 'rgba(255,255,255,0.7)',
                          fontSize: 12,
                          cursor: 'pointer',
                          textAlign: 'left',
                        }}
                      >
                        {t(SIZE_PRESET_LABELS[preset])}
                      </button>
                    ))}
                </div>
              )}
            </div>
          )}

          {/* Voice settings */}
          <button
            type="button"
            onClick={() => setShowVoiceSettings(true)}
            title={t('voiceSettings')}
            aria-label={t('voiceSettings')}
            style={{
              width: 36, height: 36, borderRadius: 8,
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid rgba(255,255,255,0.08)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: 'pointer', color: 'rgba(255,255,255,0.6)',
            }}
          >
            <Settings size={15} />
          </button>

          <button
            type="button"
            onClick={clearMessages}
            title={t('clear')}
            aria-label={t('clear')}
            style={{
              width: 36, height: 36, borderRadius: 8,
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid rgba(255,255,255,0.08)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: 'pointer', color: 'rgba(255,255,255,0.6)',
            }}
          >
            <Trash2 size={15} />
          </button>
          <button
            type="button"
            onClick={handleClosePanel}
            title={t('close')}
            aria-label={t('close')}
            style={{
              width: 36, height: 36, borderRadius: 8,
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(255,255,255,0.1)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: 'pointer', color: 'rgba(255,255,255,0.75)',
            }}
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <MessageList
        messages={messages}
        messageTTS={messageTTSWithPolicy}
      />

      {/* Loading indicator */}
      {loading && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 16px 8px', color: 'rgba(255,255,255,0.4)', fontSize: 12, flexShrink: 0 }}>
            <Loader2 size={14} className="animate-spin" />
          {t('thinking')}
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{ padding: '0 16px 8px', color: '#EF4444', fontSize: 12, flexShrink: 0 }}>
          {error}
        </div>
      )}

      {/* TTS / voice error + autoplay blocked play button */}
      {(ttsError || tts.pendingPlayUrl) && (
        <div style={{ padding: '0 16px 8px', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', flexShrink: 0 }}>
          {ttsError && (
            <span style={{ color: '#F59E0B', fontSize: 12, flex: 1, minWidth: 0 }}>{ttsError}</span>
          )}
          {tts.pendingPlayUrl && (
            <button
              type="button"
              onClick={tts.playPending}
              style={{
                padding: '8px 14px', minHeight: 36, borderRadius: 8, fontSize: 12,
                background: 'rgba(0, 113, 227, 0.15)', border: '1px solid rgba(0, 113, 227, 0.3)',
                color: '#0071e3', cursor: 'pointer', whiteSpace: 'nowrap',
              }}
            >
              ▶ {t('playPending')}
            </button>
          )}
          {ttsError && (
            <button
              type="button"
              aria-label={t('close')}
              onClick={() => setTtsError(null)}
              style={{
                background: 'rgba(255,255,255,0.06)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: 8,
                minWidth: 36,
                minHeight: 36,
                color: 'rgba(255,255,255,0.6)',
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <X size={14} />
            </button>
          )}
        </div>
      )}

      {/* Action card */}
      {lastAssistantWithAction?.action?.form_patch && (
        <div style={{ padding: '0 16px 8px', flexShrink: 0 }}>
          <RecommendActionCard
            patch={lastAssistantWithAction.action.form_patch}
            onFillForm={() => handleFillForm(lastAssistantWithAction.action!.form_patch!)}
            onFillAndSubmit={() => handleFillAndSubmit(lastAssistantWithAction.action!.form_patch!)}
            onCancel={() => setLastFormPatch(null)}
          />
        </div>
      )}

      {/* Input area with voice button — single row, flex layout */}
      <div style={{
        display: 'flex',
        gap: 8,
        padding: isMobile ? '10px 12px calc(12px + env(safe-area-inset-bottom, 0px))' : '12px 16px',
        borderTop: '1px solid rgba(255,255,255,0.06)',
        background: 'rgba(0,0,0,0.2)',
        alignItems: 'center',
        flexShrink: 0,
        minWidth: 0,
      }}>
        {/* Voice input button */}
        <div style={{ flexShrink: 0 }}>
          <VoiceInputButton
            voiceState={voiceState}
            isSupported={recorder.isSupported}
            asrEnabled={voiceConfig.asr_enabled}
            onStartRecording={async () => {
              // Single-audio policy: stop any current narration before recording
              tts.stop();
              messageTTS.stop();
              setVoiceState('listening');
              setTtsError(null);
              await recorder.startRecording();
            }}
            onStopRecording={() => {
              recorder.stopRecording();
            }}
            onCancelRecording={() => {
              recorder.cancelRecording();
              setVoiceState('idle');
            }}
            durationMs={recorder.durationMs}
            recordMode={settingsRef.current.record_mode}
          />
        </div>

        {/* Text input + send button — must be flex row so input and button stay on one line */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          flex: '1 1 auto',
          minWidth: 0,
          width: '100%',
          flexWrap: 'nowrap',
        }}>
          <MessageInput onSend={sendMessage} loading={loading} bare />
        </div>
      </div>

      {/* Resize handles (desktop only) */}
      {!isMobile && (
        <>
          <div {...panel.getResizeHandleProps('right')} />
          <div {...panel.getResizeHandleProps('bottom')} />
          <div {...panel.getResizeHandleProps('bottom-right')}>
            <div style={{
              position: 'absolute',
              bottom: 2,
              right: 2,
              width: 10,
              height: 10,
              borderRight: '2px solid rgba(255,255,255,0.2)',
              borderBottom: '2px solid rgba(255,255,255,0.2)',
              borderRadius: '0 0 2px 0',
              pointerEvents: 'none',
            }} />
          </div>
        </>
      )}
    </div>
  );
};
