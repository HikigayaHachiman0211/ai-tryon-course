import React from 'react';
import type { RecommendFormPatch } from '../assistantTypes';

interface Props {
  patch: RecommendFormPatch;
  onFillForm: () => void;
  onFillAndSubmit: () => void;
  onCancel: () => void;
}

const FIELD_LABELS: Record<string, string> = {
  gender: '性别',
  color_preference: '颜色',
  price_min: '最低价格',
  price_max: '最高价格',
  brand_preference: '品牌',
  size: '尺码',
  mbti: 'MBTI',
  style_preference: '风格',
  ai_provider: 'AI 引擎',
  vision_provider: '图像分析引擎',
  mimo_model: 'MiMo 模型',
};

const GENDER_LABELS: Record<string, string> = { male: '男', female: '女' };
const PROVIDER_LABELS: Record<string, string> = { mimo: 'Xiaomi MiMo', gemini: 'Gemini', deepseek: 'Deepseek', auto: '自动' };

function formatValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '-';
  if (key === 'gender') return GENDER_LABELS[value as string] || String(value);
  if (key === 'ai_provider') return PROVIDER_LABELS[value as string] || String(value);
  if (key === 'price_min' || key === 'price_max') return `¥${value}`;
  return String(value);
}

export const RecommendActionCard: React.FC<Props> = ({ patch, onFillForm, onFillAndSubmit, onCancel }) => {
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
        已提取推荐条件
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
            {FIELD_LABELS[key] || key}: {formatValue(key, value)}
          </span>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button
          onClick={onFillForm}
          style={{
            padding: '6px 14px',
            borderRadius: 980,
            border: '1px solid #0071e3',
            background: '#0071e3',
            color: '#fff',
            fontSize: 13,
            cursor: 'pointer',
          }}
        >
          填入表单
        </button>
        <button
          onClick={onFillAndSubmit}
          style={{
            padding: '6px 14px',
            borderRadius: 980,
            border: '1px solid rgba(16,185,129,0.5)',
            background: 'rgba(16,185,129,0.15)',
            color: '#4ade80',
            fontSize: 13,
            cursor: 'pointer',
          }}
        >
          填入并生成推荐
        </button>
        <button
          onClick={onCancel}
          style={{
            padding: '6px 14px',
            borderRadius: 980,
            border: '1px solid rgba(255,255,255,0.1)',
            background: 'transparent',
            color: 'rgba(255,255,255,0.5)',
            fontSize: 13,
            cursor: 'pointer',
          }}
        >
          取消
        </button>
      </div>
    </div>
  );
};
