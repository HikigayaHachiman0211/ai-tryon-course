/* Voice settings panel — accessible from both normal chat and call mode */

import React, { useCallback, useState } from 'react';
import { X } from 'lucide-react';
import { loadVoiceSettings, saveVoiceSettings, type VoiceSettings } from './voiceSettingsStorage';
import { useAssistantVoiceConfig } from './useAssistantVoiceConfig';
import { TONE_PRESETS } from './voiceTypes';
import { useTranslation } from 'react-i18next';

interface Props {
  onClose: () => void;
}

export const VoiceSettingsPanel: React.FC<Props> = ({ onClose }) => {
  const { t } = useTranslation('voice');
  const { config } = useAssistantVoiceConfig();
  const [settings, setSettings] = useState<VoiceSettings>(loadVoiceSettings);

  const update = useCallback((patch: Partial<VoiceSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      saveVoiceSettings(next);
      return next;
    });
  }, []);

  const allVoices = [
    ...config.available_voices.map((v) => ({ id: v, name: v, source: 'preset' as const })),
    ...config.published_clone_voices.map((v) => ({ id: v.id, name: v.name, source: 'clone' as const })),
  ];

  return (
    <div style={{
      position: 'absolute',
      inset: 0,
      background: 'rgba(18, 18, 20, 0.99)',
      zIndex: 10,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'auto',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '14px 16px',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        background: 'rgba(0,0,0,0.3)',
        flexShrink: 0,
      }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: '#F8FAFC' }}>{t('settings.title')}</span>
        <button
          type="button"
          onClick={onClose}
          title={t('common:common.close')}
          aria-label={t('common:common.close')}
          style={{
            width: 40, height: 40, borderRadius: 10,
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.08)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer', color: 'rgba(255,255,255,0.6)',
          }}
        >
          <X size={16} />
        </button>
      </div>

      <div style={{ padding: '16px 16px calc(24px + env(safe-area-inset-bottom, 0px))', display: 'flex', flexDirection: 'column', gap: 16, flex: 1 }}>
        {/* TTS toggle */}
        <ToggleRow
          label={t('settings.tts')}
          description={t('settings.ttsDescription')}
          checked={settings.tts_enabled}
          onChange={(v) => update({ tts_enabled: v, auto_tts_enabled: v })}
        />

        {/* Voice source */}
        {config.voice_clone_enabled && config.published_clone_voices.length > 0 && (
          <SelectRow
            label={t('settings.source')}
            value={settings.voice_source}
            options={[
              { value: 'preset', label: t('settings.preset') },
              { value: 'clone', label: t('settings.clone') },
            ]}
            onChange={(v) => update({ voice_source: v as 'preset' | 'clone' })}
          />
        )}

        {/* Voice selection */}
        <SelectRow
          label={t('settings.voice')}
          value={settings.voice_source === 'clone' ? (settings.clone_voice_id || '') : settings.preset_voice}
          options={allVoices.map((v) => ({
            value: v.id,
            label: v.source === 'clone' ? `${v.name} (${t('settings.clone')})` : v.name,
          }))}
          onChange={(v) => {
            if (settings.voice_source === 'clone') {
              update({ clone_voice_id: v });
            } else {
              update({ preset_voice: v });
            }
          }}
        />

        {/* Tone preset */}
        <SelectRow
          label={t('settings.tone')}
          value={settings.tone_preset}
          options={TONE_PRESETS.map((tone) => ({ value: tone.id, label: t(`tone.${tone.id}`) }))}
          onChange={(v) => update({ tone_preset: v })}
        />

        {/* ASR language */}
        <SelectRow
          label={t('settings.language')}
          value={settings.asr_language}
          options={[
            { value: 'zh', label: t('settings.chinese') },
            { value: 'en', label: t('settings.english') },
            { value: 'ja', label: t('settings.japanese') },
            { value: 'auto', label: t('settings.auto') },
          ]}
          onChange={(v) => update({ asr_language: v })}
        />

        {/* Record mode */}
        <SelectRow
          label={t('settings.recordMode')}
          value={settings.record_mode}
          options={[
            { value: 'click', label: t('settings.clickMode') },
            { value: 'hold', label: t('settings.holdMode') },
          ]}
          onChange={(v) => update({ record_mode: v as 'click' | 'hold' })}
        />

        {/* Auto send ASR */}
        <ToggleRow
          label={t('settings.autoSend')}
          description={t('settings.autoSendDescription')}
          checked={settings.auto_send_asr}
          onChange={(v) => update({ auto_send_asr: v })}
        />

        {/* Volume */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>
            {t('settings.volume', { percent: Math.round(settings.volume * 100) })}
          </span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={settings.volume}
            onChange={(e) => update({ volume: parseFloat(e.target.value) })}
            style={{ width: '100%', accentColor: '#0071e3' }}
          />
        </div>

        {/* Privacy notice */}
        <div style={{
          fontSize: 11,
          color: 'rgba(255,255,255,0.3)',
          padding: '8px 0',
          borderTop: '1px solid rgba(255,255,255,0.04)',
        }}>
          {t('settings.privacy')}
        </div>
      </div>
    </div>
  );
};

/* Helper sub-components */

function ToggleRow({ label, description, checked, onChange }: {
  label: string; description?: string; checked: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, minHeight: 44 }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, color: '#F8FAFC' }}>{label}</div>
        {description && <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>{description}</div>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        style={{
          width: 48, height: 28, borderRadius: 14, flexShrink: 0,
          background: checked ? '#0071e3' : 'rgba(255,255,255,0.12)',
          border: 'none', cursor: 'pointer', position: 'relative',
          transition: 'background 0.2s',
        }}
      >
        <div style={{
          width: 22, height: 22, borderRadius: '50%', background: '#fff',
          position: 'absolute', top: 3, left: checked ? 23 : 3,
          transition: 'left 0.2s',
        }} />
      </button>
    </div>
  );
}

function SelectRow({ label, value, options, onChange }: {
  label: string; value: string; options: Array<{ value: string; label: string }>; onChange: (v: string) => void;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>{label}</span>
      <select
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          background: 'rgba(255,255,255,0.06)',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: 10,
          padding: '10px 12px',
          minHeight: 44,
          color: '#F8FAFC',
          colorScheme: 'dark',
          fontSize: 16,
          outline: 'none',
          cursor: 'pointer',
        }}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value} style={{ background: '#1a1a1e', color: '#F8FAFC' }}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
