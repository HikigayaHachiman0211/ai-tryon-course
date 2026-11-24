import { UploadCloud } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { RecommendationRequest } from '../types';
import {
  MBTI_OPTIONS,
  GENDER_OPTIONS,
  BRAND_SUGGESTIONS,
  SAMPLE_MODELS,
  type SampleModel,
} from '../constants/formOptions';

export interface ProfilePanelProps {
  photoPreview: string | null;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  onDragOver: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent) => void;
  onPhotoUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  sampleModelGender: 'male' | 'female';
  selectedSampleModel: string | null;
  onSampleModelGenderChange: (gender: 'male' | 'female') => void;
  onSelectSampleModel: (model: SampleModel) => void;
  formData: RecommendationRequest;
  onInputChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => void;
  onColorSelect: (color: string) => void;
  onBrandSelect: (brand: string) => void;
  eyebrow: string;
  title: React.ReactNode;
  description: string;
  footer: React.ReactNode;
}

export function ProfilePanel({
  photoPreview,
  fileInputRef,
  onDragOver,
  onDrop,
  onPhotoUpload,
  sampleModelGender,
  selectedSampleModel,
  onSampleModelGenderChange,
  onSelectSampleModel,
  formData,
  onInputChange,
  onColorSelect,
  onBrandSelect,
  eyebrow,
  title,
  description,
  footer,
}: ProfilePanelProps) {
  const { t } = useTranslation(['recommend', 'common']);
  const colorSuggestions = [
    { value: '黑色', labelKey: 'profile.color.black' },
    { value: '白色', labelKey: 'profile.color.white' },
    { value: '藏青', labelKey: 'profile.color.navy' },
  ];

  return (
    <section className="profile-panel-shell">
      <div className="section-hero">
        <div className="section-eyebrow">{eyebrow}</div>
        <h1 className="hero-display">{title}</h1>
        <p className="section-copy">{description}</p>
      </div>

      <div className="bento-grid">
        <div
          className="bento-item bento-col-span-2"
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: 180,
            borderStyle: 'dashed',
            cursor: 'pointer',
            background: photoPreview ? 'transparent' : 'var(--bg-card)',
          }}
          onDragOver={onDragOver}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input type="file" ref={fileInputRef} hidden accept="image/*" onChange={onPhotoUpload} />
          {photoPreview ? (
            <div className="photo-preview-frame">
              <img src={photoPreview} alt={t('profile.photoPreviewAlt')} className="photo-preview-image" />
              <div style={{ position: 'absolute', bottom: 12, right: 12, background: 'rgba(0,0,0,0.6)', padding: '6px 12px', borderRadius: 8, backdropFilter: 'blur(10px)', fontSize: 12 }}>
                {t('profile.changePhoto')}
              </div>
            </div>
          ) : (
            <>
              <UploadCloud size={32} color="var(--text-tertiary)" style={{ marginBottom: 12 }} />
              <div style={{ fontWeight: 500, marginBottom: 4 }}>{t('profile.uploadPhoto')}</div>
              <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{t('profile.uploadPhotoHint')}</div>
            </>
          )}
        </div>

        <div className="bento-item bento-col-span-2" style={{ padding: 16 }}>
          <div style={{ fontSize: 13, color: 'var(--text-tertiary)', marginBottom: 12 }}>{t('profile.sampleModel.choose')}</div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <button
              type="button"
              onClick={() => onSampleModelGenderChange('male')}
              style={{ padding: '8px 16px', minHeight: 44, borderRadius: 980, border: sampleModelGender === 'male' ? '1px solid #0071e3' : '1px solid var(--border-subtle)', background: sampleModelGender === 'male' ? '#0071e3' : 'transparent', color: sampleModelGender === 'male' ? '#fff' : 'var(--text-secondary)', fontSize: 13, cursor: 'pointer', transition: 'all 0.2s ease' }}
            >
              {t('profile.sampleModel.male')}
            </button>
            <button
              type="button"
              onClick={() => onSampleModelGenderChange('female')}
              style={{ padding: '8px 16px', minHeight: 44, borderRadius: 980, border: sampleModelGender === 'female' ? '1px solid #0071e3' : '1px solid var(--border-subtle)', background: sampleModelGender === 'female' ? '#0071e3' : 'transparent', color: sampleModelGender === 'female' ? '#fff' : 'var(--text-secondary)', fontSize: 13, cursor: 'pointer', transition: 'all 0.2s ease' }}
            >
              {t('profile.sampleModel.female')}
            </button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(72px, 1fr))', gap: 10 }}>
            {SAMPLE_MODELS.filter(m => m.gender === sampleModelGender).map(model => (
              <div
                key={model.id}
                onClick={() => void onSelectSampleModel(model)}
                style={{
                  cursor: 'pointer',
                  textAlign: 'center',
                  borderRadius: 10,
                  overflow: 'hidden',
                  border: selectedSampleModel === model.id ? '2px solid #0071e3' : '2px solid transparent',
                  boxShadow: selectedSampleModel === model.id ? '0 0 0 2px rgba(0,113,227,0.2)' : 'none',
                  transition: 'all 0.2s ease',
                }}
              >
                <img
                  src={`/sample-models/${model.gender}/${model.filename}`}
                  alt={model.name}
                  loading="lazy"
                  style={{ width: '100%', aspectRatio: '3/4', objectFit: 'cover', display: 'block' }}
                />
                <span style={{ display: 'block', padding: 3, fontSize: 11, color: 'var(--text-secondary)' }}>{model.name}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="bento-item">
          <label className="label">{t('profile.color.label')} *</label>
          <input
            type="text"
            name="color_preference"
            className="modern-input"
            placeholder={t('profile.color.placeholder')}
            value={formData.color_preference}
            onChange={onInputChange}
          />
          <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
            {colorSuggestions.map((color) => (
              <div
                key={color.value}
                onClick={() => onColorSelect(color.value)}
                className="suggestion-chip"
              >
                {t(color.labelKey)}
              </div>
            ))}
          </div>

          <label className="label" style={{ marginTop: 16 }}>{t('profile.brand.label')}</label>
          <input
            type="text"
            name="brand_preference"
            className="modern-input"
            placeholder={t('profile.brand.placeholder')}
            value={formData.brand_preference || ''}
            onChange={onInputChange}
          />
          <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
            {BRAND_SUGGESTIONS.map((brand) => (
              <div
                key={brand.value}
                onClick={() => onBrandSelect(brand.value)}
                className="suggestion-chip"
              >
                {t(brand.labelKey)}
              </div>
            ))}
          </div>
        </div>

        <div className="bento-item">
          <label className="label">{t('profile.gender.label')} *</label>
          <select name="gender" className="modern-input" value={formData.gender || ''} onChange={onInputChange} style={{ marginBottom: 16 }}>
            <option value="">{t('profile.select')}</option>
            {GENDER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{t(option.labelKey)}</option>
            ))}
          </select>

          <label className="label">{t('profile.mbti.label')}</label>
          <select name="mbti" className="modern-input" value={formData.mbti || ''} onChange={onInputChange}>
            <option value="">{t('profile.optionalSelect')}</option>
            {MBTI_OPTIONS.map((mbti) => (
              <option key={mbti} value={mbti}>{mbti}</option>
            ))}
          </select>
        </div>

        <div className="bento-item bento-col-span-2 price-range-grid">
          <div style={{ minWidth: 0 }}>
            <label className="label">{t('profile.price.min')}</label>
            <input type="number" inputMode="numeric" name="price_min" className="modern-input" placeholder="0" value={formData.price_min ?? ''} onChange={onInputChange} />
          </div>
          <div style={{ minWidth: 0 }}>
            <label className="label">{t('profile.price.max')}</label>
            <input type="number" inputMode="numeric" name="price_max" className="modern-input" placeholder={t('profile.price.unlimited')} value={formData.price_max ?? ''} onChange={onInputChange} />
          </div>
        </div>

        <div className="bento-item bento-col-span-2">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '4px 8px', flexWrap: 'wrap' }}>
            <label className="label">{t('profile.size.label')}</label>
            <span style={{ fontSize: 11, color: 'var(--accent-blue-text)' }}>✨ {t('profile.aiSizeHint')}</span>
          </div>
          <input type="text" name="size" className="modern-input" placeholder={t('profile.size.placeholder')} value={formData.size || ''} onChange={onInputChange} style={{ marginBottom: 16 }} />

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '4px 8px', flexWrap: 'wrap' }}>
            <label className="label">{t('profile.style.label')}</label>
            <span style={{ fontSize: 11, color: 'var(--accent-blue-text)' }}>✨ {t('profile.aiStyleHint')}</span>
          </div>
          <input type="text" name="style_preference" className="modern-input" placeholder={t('profile.style.placeholder')} value={formData.style_preference || ''} onChange={onInputChange} />
        </div>

        <div className="bento-item bento-col-span-2" style={{ background: 'rgba(56, 189, 248, 0.02)', borderColor: 'rgba(56, 189, 248, 0.1)', display: 'flex', alignItems: 'center', gap: 12, padding: '16px 20px' }}>
          <span style={{ fontSize: 14, color: 'var(--accent-blue-text)' }}>⚙️</span>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0 }}>
            {t('profile.aiConfigHint')}
          </p>
        </div>

        <div className="bento-col-span-2" style={{ marginTop: 8 }}>{footer}</div>
      </div>
    </section>
  );
}
