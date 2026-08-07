/* Voice input button — microphone for ASR recording */

import React from 'react';
import { Mic, Loader2, Square } from 'lucide-react';
import type { AssistantVoiceState } from './voiceTypes';

interface Props {
  voiceState: AssistantVoiceState;
  isSupported: boolean;
  asrEnabled: boolean;
  onStartRecording: () => void;
  onStopRecording: () => void;
  onCancelRecording: () => void;
  durationMs: number;
  recordMode: 'click' | 'hold';
}

function formatDuration(ms: number): string {
  const secs = Math.floor(ms / 1000);
  return `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, '0')}`;
}

export const VoiceInputButton: React.FC<Props> = ({
  voiceState,
  isSupported,
  asrEnabled,
  onStartRecording,
  onStopRecording,
  onCancelRecording,
  durationMs,
  recordMode,
}) => {
  if (!isSupported || !asrEnabled) return null;

  const isRecording = voiceState === 'listening';
  const isRecognizing = voiceState === 'recognizing';
  const isDisabled = isRecognizing || voiceState === 'thinking';

  const handleClick = () => {
    if (isDisabled) return;
    if (isRecording) {
      onStopRecording();
    } else {
      onStartRecording();
    }
  };

  const handlePointerDown = () => {
    if (recordMode !== 'hold' || isDisabled) return;
    onStartRecording();
  };

  const handlePointerUp = () => {
    if (recordMode !== 'hold' || !isRecording) return;
    onStopRecording();
  };

  const handlePointerCancel = () => {
    if (recordMode !== 'hold' || !isRecording) return;
    onCancelRecording();
  };

  const getIcon = () => {
    if (isRecognizing) return <Loader2 size={18} className="animate-spin" />;
    if (isRecording) return <Square size={16} fill="currentColor" />;
    return <Mic size={18} />;
  };

  const getTitle = () => {
    if (isRecognizing) return '正在识别...';
    if (isRecording) return recordMode === 'hold' ? '松开结束' : '点击结束录音';
    return recordMode === 'hold' ? '按住说话' : '点击开始录音';
  };

  const getColor = () => {
    if (isRecording) return '#EF4444';
    if (isRecognizing) return '#F59E0B';
    return 'rgba(255,255,255,0.5)';
  };

  return (
    <div style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <button
        onClick={handleClick}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerCancel}
        disabled={isDisabled}
        title={getTitle()}
        style={{
          width: 36,
          height: 36,
          borderRadius: 10,
          background: isRecording ? 'rgba(239, 68, 68, 0.15)' : 'rgba(255,255,255,0.04)',
          border: isRecording ? '1px solid rgba(239, 68, 68, 0.3)' : '1px solid rgba(255,255,255,0.08)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: isDisabled ? 'default' : 'pointer',
          color: getColor(),
          transition: 'all 0.2s',
        }}
      >
        {getIcon()}
      </button>
      {isRecording && (
        <span style={{ fontSize: 11, color: '#EF4444', minWidth: 36, fontVariantNumeric: 'tabular-nums' }}>
          {formatDuration(durationMs)}
        </span>
      )}
    </div>
  );
};
