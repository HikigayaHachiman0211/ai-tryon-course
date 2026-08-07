/* Call button — enters AI phone call mode */

import React from 'react';
import { Phone, PhoneOff } from 'lucide-react';

interface Props {
  isInCall: boolean;
  isSupported: boolean;
  disabledReason?: string;
  onClick: () => void;
}

export const CallButton: React.FC<Props> = ({ isInCall, isSupported, disabledReason, onClick }) => {
  const disabled = !isSupported;

  return (
    <button
      onClick={disabled ? undefined : onClick}
      title={disabled ? (disabledReason || 'AI 电话功能暂不可用') : (isInCall ? '通话中' : 'AI 电话')}
      disabled={disabled}
      style={{
        width: 28,
        height: 28,
        borderRadius: 8,
        background: disabled
          ? 'rgba(255,255,255,0.03)'
          : (isInCall ? 'rgba(16, 185, 129, 0.15)' : 'rgba(255,255,255,0.04)'),
        border: disabled
          ? '1px solid rgba(255,255,255,0.05)'
          : (isInCall ? '1px solid rgba(16, 185, 129, 0.3)' : '1px solid rgba(255,255,255,0.08)'),
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: disabled ? 'not-allowed' : 'pointer',
        color: disabled ? 'rgba(255,255,255,0.28)' : (isInCall ? '#4ade80' : 'rgba(255,255,255,0.5)'),
        opacity: disabled ? 0.9 : 1,
        transition: 'all 0.2s',
      }}
    >
      {isInCall ? <PhoneOff size={14} /> : <Phone size={14} />}
    </button>
  );
};
