import React from 'react';
import type { AssistantChatMessage } from '../assistantTypes';
import type { UseMessageTTSReturn } from '../voice/useMessageTTS';
import { MessageBubble } from './MessageBubble';

interface Props {
  messages: AssistantChatMessage[];
  messageTTS?: UseMessageTTSReturn;
}

export const MessageList: React.FC<Props> = ({ messages, messageTTS }) => {
  const listRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'rgba(255,255,255,0.4)',
        fontSize: 14,
        padding: 24,
        textAlign: 'center',
      }}>
        你好！我是你的羽绒服 AI 导购助手。告诉我你的穿搭需求吧。
      </div>
    );
  }

  const handlePlayTTS = (messageId: string, text: string) => {
    if (messageTTS) {
      void messageTTS.playMessage(messageId, text);
    }
  };

  return (
    <div ref={listRef} style={{
      flex: 1,
      overflowY: 'auto',
      padding: '16px',
      display: 'flex',
      flexDirection: 'column',
      gap: 12,
      minHeight: 0,
    }}>
      {messages.map((msg) => (
        messageTTS ? (
          <MessageBubble
            key={msg.id}
            message={msg}
            isLoading={messageTTS.loadingMessageId === msg.id}
            isPlaying={messageTTS.playingMessageId === msg.id}
            onPlayTTS={handlePlayTTS}
          />
        ) : (
          /* Fallback: no TTS support (e.g., in call mode) */
          <div
            key={msg.id}
            style={{
              display: 'flex',
              justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
            }}
          >
            <div style={{
              maxWidth: '85%',
              padding: '10px 14px',
              borderRadius: msg.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
              background: msg.role === 'user'
                ? 'rgba(0, 113, 227, 0.6)'
                : 'rgba(255,255,255,0.06)',
              color: '#F8FAFC',
              fontSize: 14,
              lineHeight: 1.6,
              wordBreak: 'break-word',
            }}>
              {msg.content}
            </div>
          </div>
        )
      ))}
    </div>
  );
};
