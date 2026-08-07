/* Voice settings panel — accessible from both normal chat and call mode */

import React, { useCallback, useState } from 'react';
import { X } from 'lucide-react';
import { loadVoiceSettings, saveVoiceSettings, type VoiceSettings } from './voiceSettingsStorage';
import { useAssistantVoiceConfig } from './useAssistantVoiceConfig';
import { TONE_PRESETS } from './voiceTypes';

interface Props {
  onClose: () => void;
}

export const VoiceSettingsPanel: React.FC<Props> = ({ onClose }) => {
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
        <span style={{ fontSize: 14, fontWeight: 600, color: '#F8FAFC' }}>语音设置</span>
        <button
          onClick={onClose}
          style={{
            width: 28, height: 28, borderRadius: 8,
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.08)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer', color: 'rgba(255,255,255,0.5)',
          }}
        >
          <X size={14} />
        </button>
      </div>

      <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: 16, flex: 1 }}>
        {/* TTS toggle */}
        <ToggleRow
          label="语音播报"
          description="AI 回复后自动朗读"
          checked={settings.tts_enabled}
          onChange={(v) => update({ tts_enabled: v, auto_tts_enabled: v })}
        />

        {/* Voice source */}
        {config.voice_clone_enabled && config.published_clone_voices.length > 0 && (
          <SelectRow
            label="音色来源"
            value={settings.voice_source}
            options={[
              { value: 'preset', label: '预置音色' },
              { value: 'clone', label: '克隆音色' },
            ]}
            onChange={(v) => update({ voice_source: v as 'preset' | 'clone' })}
          />
        )}

        {/* Voice selection */}
        <SelectRow
          label="音色"
          value={settings.voice_source === 'clone' ? (settings.clone_voice_id || '') : settings.preset_voice}
          options={allVoices.map((v) => ({
            value: v.id,
            label: v.source === 'clone' ? `${v.name} (克隆)` : v.name,
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
          label="语气预设"
          value={settings.tone_preset}
          options={TONE_PRESETS.map((t) => ({ value: t.id, label: t.label }))}
          onChange={(v) => update({ tone_preset: v })}
        />

        {/* ASR language */}
        <SelectRow
          label="识别语言"
          value={settings.asr_language}
          options={[
            { value: 'zh', label: '中文' },
            { value: 'en', label: 'English' },
            { value: 'auto', label: '自动' },
          ]}
          onChange={(v) => update({ asr_language: v })}
        />

        {/* Record mode */}
        <SelectRow
          label="录音模式"
          value={settings.record_mode}
          options={[
            { value: 'click', label: '点击开始/结束' },
            { value: 'hold', label: '按住说话' },
          ]}
          onChange={(v) => update({ record_mode: v as 'click' | 'hold' })}
        />

        {/* Auto send ASR */}
        <ToggleRow
          label="自动发送识别文本"
          description="识别完成后自动发送给 AI"
          checked={settings.auto_send_asr}
          onChange={(v) => update({ auto_send_asr: v })}
        />

        {/* Volume */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>
            音量: {Math.round(settings.volume * 100)}%
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
          语音仅用于本次 AI 导购识别，不会保存在浏览器本地。
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
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <div>
        <div style={{ fontSize: 13, color: '#F8FAFC' }}>{label}</div>
        {description && <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>{description}</div>}
      </div>
      <button
        onClick={() => onChange(!checked)}
        style={{
          width: 40, height: 22, borderRadius: 11,
          background: checked ? '#0071e3' : 'rgba(255,255,255,0.1)',
          border: 'none', cursor: 'pointer', position: 'relative',
          transition: 'background 0.2s',
        }}
      >
        <div style={{
          width: 16, height: 16, borderRadius: '50%', background: '#fff',
          position: 'absolute', top: 3, left: checked ? 21 : 3,
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
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          background: 'rgba(255,255,255,0.06)',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: 8,
          padding: '8px 10px',
          color: '#F8FAFC',
          fontSize: 13,
          outline: 'none',
          cursor: 'pointer',
        }}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value} style={{ background: '#1a1a1e' }}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
