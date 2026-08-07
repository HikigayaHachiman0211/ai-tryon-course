import { UploadCloud } from 'lucide-react';
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
              <img src={photoPreview} alt="用户上传预览" className="photo-preview-image" />
              <div style={{ position: 'absolute', bottom: 12, right: 12, background: 'rgba(0,0,0,0.6)', padding: '6px 12px', borderRadius: 8, backdropFilter: 'blur(10px)', fontSize: 12 }}>
                点击更换照片
              </div>
            </div>
          ) : (
            <>
              <UploadCloud size={32} color="var(--text-tertiary)" style={{ marginBottom: 12 }} />
              <div style={{ fontWeight: 500, marginBottom: 4 }}>拖拽或点击上传全身照</div>
              <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>选填，但建议上传以提升推荐与分析准确度</div>
            </>
          )}
        </div>

        <div className="bento-item bento-col-span-2" style={{ padding: 16 }}>
          <div style={{ fontSize: 13, color: 'var(--text-tertiary)', marginBottom: 12 }}>或选择一位示例模特：</div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <button
              type="button"
              onClick={() => onSampleModelGenderChange('male')}
              style={{ padding: '5px 14px', borderRadius: 980, border: sampleModelGender === 'male' ? '1px solid #0071e3' : '1px solid var(--border-subtle)', background: sampleModelGender === 'male' ? '#0071e3' : 'transparent', color: sampleModelGender === 'male' ? '#fff' : 'var(--text-secondary)', fontSize: 13, cursor: 'pointer', transition: 'all 0.2s ease' }}
            >
              男性模特
            </button>
            <button
              type="button"
              onClick={() => onSampleModelGenderChange('female')}
              style={{ padding: '5px 14px', borderRadius: 980, border: sampleModelGender === 'female' ? '1px solid #0071e3' : '1px solid var(--border-subtle)', background: sampleModelGender === 'female' ? '#0071e3' : 'transparent', color: sampleModelGender === 'female' ? '#fff' : 'var(--text-secondary)', fontSize: 13, cursor: 'pointer', transition: 'all 0.2s ease' }}
            >
              女性模特
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
          <label className="label">颜色偏好 *</label>
          <input
            type="text"
            name="color_preference"
            className="modern-input"
            placeholder="例如 黑色、米白、雾蓝"
            value={formData.color_preference}
            onChange={onInputChange}
          />
          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            {['黑色', '白色', '藏青'].map((color) => (
              <div
                key={color}
                onClick={() => onColorSelect(color)}
                style={{ fontSize: 11, background: 'rgba(255,255,255,0.05)', padding: '4px 8px', borderRadius: 4, cursor: 'pointer' }}
              >
                {color}
              </div>
            ))}
          </div>

          <label className="label" style={{ marginTop: 16 }}>品牌偏好</label>
          <input
            type="text"
            name="brand_preference"
            className="modern-input"
            placeholder="例如 阿迪达斯、骆驼，支持多个品牌"
            value={formData.brand_preference || ''}
            onChange={onInputChange}
          />
          <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
            {BRAND_SUGGESTIONS.map((brand) => (
              <div
                key={brand}
                onClick={() => onBrandSelect(brand)}
                style={{ fontSize: 11, background: 'rgba(255,255,255,0.05)', padding: '4px 8px', borderRadius: 4, cursor: 'pointer' }}
              >
                {brand}
              </div>
            ))}
          </div>
        </div>

        <div className="bento-item">
          <label className="label">性别 *</label>
          <select name="gender" className="modern-input" value={formData.gender || ''} onChange={onInputChange} style={{ marginBottom: 16 }}>
            <option value="">请选择</option>
            {GENDER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>

          <label className="label">MBTI 人格</label>
          <select name="mbti" className="modern-input" value={formData.mbti || ''} onChange={onInputChange}>
            <option value="">请选择（选填）</option>
            {MBTI_OPTIONS.map((mbti) => (
              <option key={mbti} value={mbti}>{mbti}</option>
            ))}
          </select>
        </div>

        <div className="bento-item bento-col-span-2" style={{ display: 'flex', gap: 16 }}>
          <div style={{ flex: 1 }}>
            <label className="label">最低价格（¥）</label>
            <input type="number" name="price_min" className="modern-input" placeholder="0" value={formData.price_min ?? ''} onChange={onInputChange} />
          </div>
          <div style={{ flex: 1 }}>
            <label className="label">最高价格（¥）</label>
            <input type="number" name="price_max" className="modern-input" placeholder="不限" value={formData.price_max ?? ''} onChange={onInputChange} />
          </div>
        </div>

        <div className="bento-item bento-col-span-2">
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <label className="label">尺码</label>
            <span style={{ fontSize: 11, color: 'var(--accent-blue-text)' }}>✨ AI 可结合照片辅助识别</span>
          </div>
          <input type="text" name="size" className="modern-input" placeholder="例如 M、L，或留空" value={formData.size || ''} onChange={onInputChange} style={{ marginBottom: 16 }} />

          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <label className="label">款式偏好</label>
            <span style={{ fontSize: 11, color: 'var(--accent-blue-text)' }}>✨ AI 可智能补全</span>
          </div>
          <input type="text" name="style_preference" className="modern-input" placeholder="例如 极简通勤、工装风" value={formData.style_preference || ''} onChange={onInputChange} />
        </div>

        <div className="bento-item bento-col-span-2" style={{ background: 'rgba(56, 189, 248, 0.02)', borderColor: 'rgba(56, 189, 248, 0.1)', display: 'flex', alignItems: 'center', gap: 12, padding: '16px 20px' }}>
          <span style={{ fontSize: 14, color: 'var(--accent-blue-text)' }}>⚙️</span>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0 }}>
            AI 引擎由管理员后台统一配置。
          </p>
        </div>

        <div className="bento-col-span-2" style={{ marginTop: 8 }}>{footer}</div>
      </div>
    </section>
  );
}
