/* Message bubble with per-message TTS playback button */

import React from 'react';
import { Volume2, Loader2, Square } from 'lucide-react';
import type { AssistantChatMessage } from '../assistantTypes';
import { useTranslation } from 'react-i18next';

interface Props {
  message: AssistantChatMessage;
  isLoading: boolean;
  isPlaying: boolean;
  onPlayTTS: (messageId: string, text: string) => void;
}

export const MessageBubble: React.FC<Props> = ({ message, isLoading, isPlaying, onPlayTTS }) => {
  const { t } = useTranslation('assistant');
  const hasText = Boolean(message.content?.trim());
  const isUser = message.role === 'user';

  const getButtonTitle = () => {
    if (isLoading) return t('ttsGenerating');
    if (isPlaying) return t('ttsStop');
    return t('play');
  };

  const getButtonIcon = () => {
    if (isLoading) return <Loader2 size={12} className="animate-spin" />;
    if (isPlaying) return <Square size={10} fill="currentColor" />;
    return <Volume2 size={12} />;
  };

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
      }}
    >
      <div
        style={{
          maxWidth: '85%',
          padding: '10px 14px',
          borderRadius: isUser ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
          background: isUser
            ? 'rgba(0, 113, 227, 0.6)'
            : 'rgba(255,255,255,0.06)',
          color: '#F8FAFC',
          fontSize: 14,
          lineHeight: 1.6,
          wordBreak: 'break-word',
          position: 'relative',
        }}
      >
        {/* Message text */}
        <div style={{ paddingRight: hasText ? 38 : 0 }}>{message.content}</div>

        {/* TTS button */}
        {hasText && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onPlayTTS(message.id, message.content);
            }}
            title={getButtonTitle()}
            aria-label={getButtonTitle()}
            aria-busy={isLoading}
            aria-pressed={isPlaying}
            style={{
              position: 'absolute',
              top: 4,
              right: 4,
              width: 34,
              height: 34,
              borderRadius: 8,
              background: isPlaying
                ? 'rgba(0, 113, 227, 0.3)'
                : isLoading
                ? 'rgba(245, 158, 11, 0.2)'
                : 'rgba(255,255,255,0.08)',
              border: '1px solid rgba(255,255,255,0.1)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: isLoading ? 'default' : 'pointer',
              color: isPlaying
                ? '#0071e3'
                : isLoading
                ? '#F59E0B'
                : 'rgba(255,255,255,0.5)',
              transition: 'all 0.2s',
              padding: 0,
              lineHeight: 1,
            }}
          >
            {getButtonIcon()}
          </button>
        )}
      </div>
    </div>
  );
};
