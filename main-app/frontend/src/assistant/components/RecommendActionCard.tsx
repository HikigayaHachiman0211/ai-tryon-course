import React from 'react';
import type { RecommendFormPatch } from '../assistantTypes';
import { useTranslation } from 'react-i18next';

interface Props {
  patch: RecommendFormPatch;
  onFillForm: () => void;
  onFillAndSubmit: () => void;
  onCancel: () => void;
}

const FIELD_LABELS: Record<string, string> = {
  gender: 'field.gender',
  color_preference: 'field.color_preference',
  price_min: 'field.price_min',
  price_max: 'field.price_max',
  brand_preference: 'field.brand_preference',
  size: 'field.size',
  mbti: 'field.mbti',
  style_preference: 'field.style_preference',
  ai_provider: 'field.ai_provider',
  vision_provider: 'field.vision_provider',
  mimo_model: 'field.mimo_model',
  opencode_go_model: 'field.opencode_go_model',
};

const GENDER_LABELS: Record<string, string> = { male: 'gender.male', female: 'gender.female' };
const PROVIDER_LABELS: Record<string, string> = { mimo: 'provider.mimo', gemini: 'provider.gemini', deepseek: 'provider.deepseek', opencode_go: 'provider.opencode_go', auto: 'provider.auto' };

function formatValue(key: string, value: unknown, t: (key: string, options?: Record<string, unknown>) => string): string {
  if (value === null || value === undefined || value === '') return t('emptyValue');
  if (key === 'gender') return GENDER_LABELS[value as string] ? t(GENDER_LABELS[value as string]) : String(value);
  if (key === 'ai_provider' || key === 'vision_provider') return PROVIDER_LABELS[value as string] ? t(PROVIDER_LABELS[value as string]) : String(value);
  if (key === 'price_min' || key === 'price_max') return t('price', { value });
  return String(value);
}

export const RecommendActionCard: React.FC<Props> = ({ patch, onFillForm, onFillAndSubmit, onCancel }) => {
  const { t } = useTranslation('assistant');
  const fields = Object.entries(patch).filter(
    ([, value]) => value !== null && value !== undefined && value !== ''
  );

  return (
    <div style={{
      background: 'rgba(0, 113, 227, 0.08)',
      border: '1px solid rgba(0, 113, 227, 0.2)',
      borderRadius: 14,
      padding: 14,
      marginTop: 8,
    }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#0071e3', marginBottom: 10 }}>
        {t('action.extracted')}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
        {fields.map(([key, value]) => (
          <span key={key} style={{
            fontSize: 11,
            background: 'rgba(255,255,255,0.05)',
            border: '1px solid rgba(255,255,255,0.1)',
            padding: '3px 8px',
            borderRadius: 999,
            color: 'rgba(255,255,255,0.7)',
          }}>
            {FIELD_LABELS[key] ? t(FIELD_LABELS[key]) : key}: {formatValue(key, value, t)}
          </span>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button
          type="button"
          onClick={onFillForm}
          style={{
            padding: '8px 16px',
            minHeight: 40,
            borderRadius: 980,
            border: '1px solid #0071e3',
            background: '#0071e3',
            color: '#fff',
            fontSize: 13,
            cursor: 'pointer',
          }}
        >
          {t('action.fill')}
        </button>
        <button
          type="button"
          onClick={onFillAndSubmit}
          style={{
            padding: '8px 16px',
            minHeight: 40,
            borderRadius: 980,
            border: '1px solid rgba(16,185,129,0.5)',
            background: 'rgba(16,185,129,0.15)',
            color: '#4ade80',
            fontSize: 13,
            cursor: 'pointer',
          }}
        >
          {t('action.fillAndSubmit')}
        </button>
        <button
          type="button"
          onClick={onCancel}
          style={{
            padding: '8px 16px',
            minHeight: 40,
            borderRadius: 980,
            border: '1px solid rgba(255,255,255,0.1)',
            background: 'transparent',
            color: 'rgba(255,255,255,0.6)',
            fontSize: 13,
            cursor: 'pointer',
          }}
        >
          {t('action.cancel')}
        </button>
      </div>
    </div>
  );
};
