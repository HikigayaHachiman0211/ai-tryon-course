/* TTS controls — toggle auto-TTS and stop playback */

import React from 'react';
import { Volume2, VolumeX } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface Props {
  ttsEnabled: boolean;
  isPlaying: boolean;
  onToggleTTS: () => void;
  onStop: () => void;
}

export const TTSControls: React.FC<Props> = ({ ttsEnabled, isPlaying, onToggleTTS, onStop }) => {
  const { t } = useTranslation('voice');
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
      <button
        onClick={onToggleTTS}
        title={ttsEnabled ? t('action.stop') : t('settings.tts')}
        aria-label={ttsEnabled ? t('action.stop') : t('settings.tts')}
        style={{
          width: 36,
          height: 36,
          borderRadius: 8,
          background: ttsEnabled ? 'rgba(0, 113, 227, 0.15)' : 'rgba(255,255,255,0.04)',
          border: ttsEnabled ? '1px solid rgba(0, 113, 227, 0.3)' : '1px solid rgba(255,255,255,0.08)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          color: ttsEnabled ? '#0071e3' : 'rgba(255,255,255,0.4)',
          transition: 'all 0.2s',
        }}
      >
        {ttsEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
      </button>
      {isPlaying && (
        <button
          type="button"
          onClick={onStop}
          title={t('action.stop')}
          aria-label={t('action.stop')}
          style={{
            width: 36,
            height: 36,
            borderRadius: 8,
            background: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            color: '#EF4444',
            fontSize: 10,
            fontWeight: 700,
          }}
        >
          ■
        </button>
      )}
    </div>
  );
};
