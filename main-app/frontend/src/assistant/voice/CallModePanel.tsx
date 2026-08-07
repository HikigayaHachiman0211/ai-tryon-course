/* CallModePanel — full-screen call UI for AI phone shopping guide mode */

import React, { useEffect, useState } from 'react';
import {
  Mic, MicOff, PhoneOff, Volume2, VolumeX, Settings, ArrowLeft, Send,
} from 'lucide-react';
import type { VoiceCallSessionState, AssistantVoiceState } from './voiceTypes';
import type { RecommendFormPatch } from '../assistantTypes';
import { RecommendActionCard } from '../components/RecommendActionCard';
import { VoiceSettingsPanel } from './VoiceSettingsPanel';
import { formatCallDuration } from './callUtils';

/* z-index for call panel — must match CSS variable in index.css */
const Z_CALL_PANEL = 'var(--z-call-panel)'; // 910

const STATE_LABELS: Record<string, string> = {
  idle: '准备就绪',
  requesting_permission: '请求麦克风权限...',
  ready: '等待你说话',
  listening: '正在录音',
  recording: '正在录音',
  recognizing: '正在识别',
  thinking: '正在思考',
  speaking: '正在播报',
  paused: '已暂停',
  muted: '已静音',
  error: '出错',
  ended: '通话已结束',
};

interface Props {
  session: VoiceCallSessionState;
  voiceState: AssistantVoiceState;
  isRecording: boolean;
  lastFormPatch: RecommendFormPatch | null;
  onStartRecording: () => void;
  onStopRecording: () => void;
  onCancelRecording: () => void;
  onMute: () => void;
  onUnmute: () => void;
  onStopSpeaking: () => void;
  onRetry: () => void;
  onEndCall: () => void;
  onBackToChat: () => void;
  onSendManualText?: (text: string) => void;
  onFillForm?: (patch: RecommendFormPatch) => void;
  onFillAndSubmit?: (patch: RecommendFormPatch) => void;
}

export const CallModePanel: React.FC<Props> = ({
  session,
  isRecording,
  lastFormPatch,
  onStartRecording,
  onStopRecording,
  onMute,
  onUnmute,
  onStopSpeaking,
  onRetry,
  onEndCall,
  onBackToChat,
  onSendManualText,
  onFillForm,
  onFillAndSubmit,
}) => {
  const [showSettings, setShowSettings] = useState(false);
  const [manualText, setManualText] = useState('');

  // Pre-fill manualText with ASR transcript when ready (auto_send=false path)
  useEffect(() => {
    if (session.state === 'ready' && session.currentTranscript && !manualText) {
      setManualText(session.currentTranscript);
    }
  // Only sync on transcript change, not on manualText change (avoid loop)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.currentTranscript, session.state]);

  const isEnded = session.state === 'ended';
  const isError = session.state === 'error';
  const isMuted = session.state === 'muted';
  const isSpeaking = session.state === 'speaking';
  const canRecord = session.state === 'ready' || session.state === 'error';

  return (
    <div style={{
      position: 'absolute',
      inset: 0,
      display: 'flex',
      flexDirection: 'column',
      background: 'rgba(12, 12, 14, 0.99)',
      zIndex: Z_CALL_PANEL,
      borderRadius: 20,
      overflow: 'hidden',
    }}>
      {/* Settings overlay */}
      {showSettings && <VoiceSettingsPanel onClose={() => setShowSettings(false)} />}

      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 16px',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        background: 'rgba(0,0,0,0.3)',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: '#F8FAFC' }}>📞 AI 电话导购</span>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{
            fontSize: 12,
            color: 'rgba(255,255,255,0.4)',
            fontVariantNumeric: 'tabular-nums',
          }}>
            {formatCallDuration(session.durationSeconds)}
          </span>
        </div>
      </div>

      {/* Status bar */}
      <div style={{
        padding: '8px 16px',
        background: isError ? 'rgba(239, 68, 68, 0.08)' : isSpeaking ? 'rgba(0, 113, 227, 0.08)' : 'rgba(255,255,255,0.02)',
        borderBottom: '1px solid rgba(255,255,255,0.04)',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        flexShrink: 0,
      }}>
        <div style={{
          width: 8, height: 8, borderRadius: '50%',
          background: isError ? '#EF4444' : isSpeaking ? '#0071e3' : isMuted ? '#F59E0B' : '#4ade80',
        }} />
        <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.7)' }}>
          {STATE_LABELS[session.state] || session.state}
        </span>
      </div>

      {/* Content area */}
      <div style={{ flex: 1, overflow: 'auto', padding: '12px 16px' }}>
        {/* Error display */}
        {session.errorMessage && (
          <div style={{
            padding: '10px 14px',
            background: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.2)',
            borderRadius: 12,
            marginBottom: 12,
            fontSize: 13,
            color: '#FCA5A5',
          }}>
            {session.errorMessage}
            {isError && (
              <button
                onClick={onRetry}
                style={{
                  marginLeft: 8, padding: '2px 8px', borderRadius: 6,
                  background: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)',
                  color: '#FCA5A5', fontSize: 11, cursor: 'pointer',
                }}
              >
                重试
              </button>
            )}
          </div>
        )}

        {/* Current transcript */}
        {session.currentTranscript && (
          <div style={{
            padding: '10px 14px',
            background: 'rgba(255,255,255,0.04)',
            borderRadius: 12,
            marginBottom: 12,
          }}>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginBottom: 4 }}>你说：</div>
            <div style={{ fontSize: 14, color: '#F8FAFC', lineHeight: 1.5 }}>{session.currentTranscript}</div>
          </div>
        )}

        {/* AI reply */}
        {session.currentAssistantText && (
          <div style={{
            padding: '10px 14px',
            background: 'rgba(0, 113, 227, 0.06)',
            borderRadius: 12,
            marginBottom: 12,
          }}>
            <div style={{ fontSize: 11, color: 'rgba(0, 113, 227, 0.6)', marginBottom: 4 }}>AI：</div>
            <div style={{ fontSize: 14, color: '#F8FAFC', lineHeight: 1.5 }}>{session.currentAssistantText}</div>
          </div>
        )}

        {/* Form patch summary */}
        {lastFormPatch && onFillForm && onFillAndSubmit && (
          <div style={{ marginBottom: 12 }}>
            <RecommendActionCard
              patch={lastFormPatch}
              onFillForm={() => onFillForm(lastFormPatch)}
              onFillAndSubmit={() => onFillAndSubmit(lastFormPatch)}
              onCancel={() => {}}
            />
          </div>
        )}

        {/* Turn history */}
        {session.turns.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.3)', marginBottom: 8 }}>对话记录</div>
            {session.turns.slice(-5).map((turn) => (
              <div key={turn.id} style={{ marginBottom: 8 }}>
                {turn.userText && (
                  <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)', marginBottom: 2 }}>
                    你: {turn.userText}
                  </div>
                )}
                {turn.assistantText && (
                  <div style={{ fontSize: 12, color: 'rgba(0, 113, 227, 0.7)' }}>
                    AI: {turn.assistantText}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Manual text input when auto_send is off and transcript exists */}
        {session.state === 'ready' && !isEnded && session.currentTranscript && onSendManualText && (
          <div style={{
            display: 'flex', gap: 8, marginTop: 12,
            padding: '8px 12px', background: 'rgba(255,255,255,0.03)',
            borderRadius: 12, border: '1px solid rgba(255,255,255,0.06)',
          }}>
            <input
              type="text"
              value={manualText}
              onChange={(e) => setManualText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  const toSend = manualText.trim() || session.currentTranscript;
                  if (toSend) {
                    onSendManualText(toSend);
                    setManualText('');
                  }
                }
              }}
              placeholder="识别结果已填入，可编辑后发送..."
              style={{
                flex: 1, background: 'transparent', border: 'none',
                color: '#F8FAFC', fontSize: 13, outline: 'none',
              }}
            />
            <button
              onClick={() => {
                const toSend = manualText.trim() || session.currentTranscript;
                if (toSend) {
                  onSendManualText(toSend);
                  setManualText('');
                }
              }}
              style={{
                width: 32, height: 32, borderRadius: 8,
                background: (manualText.trim() || session.currentTranscript) ? '#0071e3' : 'rgba(255,255,255,0.04)',
                border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: (manualText.trim() || session.currentTranscript) ? 'pointer' : 'default', color: '#fff',
              }}
            >
              <Send size={14} />
            </button>
          </div>
        )}

        {/* Ended state */}
        {isEnded && (
          <div style={{
            textAlign: 'center', padding: 24,
            color: 'rgba(255,255,255,0.4)', fontSize: 14,
          }}>
            通话已结束，时长 {formatCallDuration(session.durationSeconds)}
          </div>
        )}

        {/* Privacy notice */}
        <div style={{
          fontSize: 11, color: 'rgba(255,255,255,0.2)',
          textAlign: 'center', padding: '12px 0',
        }}>
          语音仅用于本次 AI 导购识别，不会保存在浏览器本地。
        </div>
      </div>

      {/* Bottom action bar */}
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        gap: 12,
        padding: '12px 16px calc(16px + env(safe-area-inset-bottom, 0px))',
        borderTop: '1px solid rgba(255,255,255,0.06)',
        background: 'rgba(0,0,0,0.2)',
        flexWrap: 'wrap',
        flexShrink: 0,
      }}>
        {/* Main record button */}
        {!isEnded && (
          <button
            onClick={canRecord ? onStartRecording : isRecording ? onStopRecording : undefined}
            disabled={!canRecord && !isRecording}
            style={{
              width: 56, height: 56, borderRadius: '50%',
              background: isRecording ? '#EF4444' : canRecord ? '#0071e3' : 'rgba(255,255,255,0.06)',
              border: 'none',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: canRecord || isRecording ? 'pointer' : 'default',
              color: '#fff', transition: 'all 0.2s',
              boxShadow: isRecording ? '0 0 20px rgba(239, 68, 68, 0.4)' : '0 0 20px rgba(0, 113, 227, 0.3)',
            }}
          >
            {isRecording ? <MicOff size={24} /> : <Mic size={24} />}
          </button>
        )}

        {/* Secondary buttons */}
        {!isEnded && (
          <>
            <button
              onClick={isMuted ? onUnmute : onMute}
              title={isMuted ? '取消静音' : '静音'}
              style={secondaryBtnStyle(isMuted)}
            >
              {isMuted ? <Volume2 size={16} /> : <VolumeX size={16} />}
            </button>

            {isSpeaking && (
              <button onClick={onStopSpeaking} title="停止播报" style={secondaryBtnStyle(false)}>
                ■
              </button>
            )}

            <button
              onClick={() => setShowSettings(true)}
              title="设置"
              style={secondaryBtnStyle(false)}
            >
              <Settings size={16} />
            </button>
          </>
        )}

        {/* End call */}
        <button
          onClick={onEndCall}
          title="结束通话"
          style={{
            width: 40, height: 40, borderRadius: '50%',
            background: 'rgba(239, 68, 68, 0.15)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer', color: '#EF4444',
          }}
        >
          <PhoneOff size={18} />
        </button>

        {/* Back to chat */}
        <button
          onClick={onBackToChat}
          title="返回聊天"
          style={secondaryBtnStyle(false)}
        >
          <ArrowLeft size={16} />
        </button>
      </div>
    </div>
  );
};

function secondaryBtnStyle(active: boolean): React.CSSProperties {
  return {
    width: 40, height: 40, borderRadius: '50%',
    background: active ? 'rgba(239, 68, 68, 0.15)' : 'rgba(255,255,255,0.04)',
    border: active ? '1px solid rgba(239, 68, 68, 0.3)' : '1px solid rgba(255,255,255,0.08)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    cursor: 'pointer',
    color: active ? '#EF4444' : 'rgba(255,255,255,0.5)',
    fontSize: 12, fontWeight: 700,
  };
}
