import React, { useState } from 'react';
import { Send } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface Props {
  onSend: (message: string) => void;
  loading: boolean;
  /** When true, skip internal wrapper — parent controls layout */
  bare?: boolean;
}

export const MessageInput: React.FC<Props> = ({ onSend, loading, bare }) => {
  const { t } = useTranslation('assistant');
  const [text, setText] = useState('');

  const handleSubmit = () => {
    if (text.trim() && !loading) {
      onSend(text.trim());
      setText('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const inner = (
    <>
      <input
        type="text"
        enterKeyHint="send"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={t('inputPlaceholder')}
        aria-label={t('inputPlaceholder')}
        disabled={loading}
        style={{
          flex: '1 1 auto',
          minWidth: 0,
          width: 'auto',
          boxSizing: 'border-box',
          background: 'rgba(255,255,255,0.06)',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: 12,
          padding: '10px 14px',
          minHeight: 44,
          color: '#F8FAFC',
          fontSize: 16,
          outline: 'none',
        }}
      />
      <button
        type="button"
        onClick={handleSubmit}
        disabled={!text.trim() || loading}
        aria-label={t('send')}
        title={t('send')}
        style={{
          flex: '0 0 auto',
          width: 44,
          height: 44,
          borderRadius: 12,
          background: text.trim() && !loading ? '#0071e3' : 'rgba(255,255,255,0.06)',
          border: 'none',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: text.trim() && !loading ? 'pointer' : 'default',
          color: '#fff',
          transition: 'all 0.2s',
        }}
      >
        <Send size={18} />
      </button>
    </>
  );

  if (bare) return inner;

  return (
    <div style={{
      display: 'flex',
      gap: 8,
      padding: '12px 16px',
      borderTop: '1px solid rgba(255,255,255,0.06)',
      background: 'rgba(0,0,0,0.2)',
    }}>
      {inner}
    </div>
  );
};
