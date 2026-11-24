import { useRef } from 'react';
import { ArrowLeft, ChevronRight, Loader2, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { buildImageURL } from '../api';
import { CatalogPanel } from '../components/CatalogPanel';
import { ErrorBanner } from '../components/ErrorBanner';
import { ProfilePanel } from '../components/ProfilePanel';
import { RadarChart } from '../components/RadarChart';
import { ScoreBreakdown } from '../components/ScoreBreakdown';
import type { CatalogMode, CatalogPlatform, SampleModel } from '../constants/formOptions';
import type {
  ErrorResponse,
  ProductCatalogItem,
  RecommendationRequest,
  StyleLabAnalysisResponse,
} from '../types';
import { formatCurrency } from '../i18n/formatters';
import i18n from '../i18n';
import { DEFAULT_LOCALE, normalizeLocale } from '../i18n/locale';

export interface StyleLabViewProps {
  // ProfilePanel
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
  // CatalogPanel
  catalogMode: CatalogMode;
  catalogPlatform: CatalogPlatform;
  catalogQuery: string;
  catalogItems: ProductCatalogItem[];
  catalogTotal: number;
  catalogLoading: boolean;
  catalogError: string | null;
  catalogGenderFallback: boolean;
  canLoadMoreCatalog: boolean;
  onCatalogModeChange: (mode: CatalogMode) => void;
  onCatalogPlatformChange: (platform: CatalogPlatform) => void;
  onCatalogQueryChange: (query: string) => void;
  onCatalogSelectProduct: (product: ProductCatalogItem) => void;
  onLoadMoreCatalog: () => void;
  // Analysis
  selectedProduct: ProductCatalogItem | null;
  styleLabLoading: boolean;
  styleLabResult: StyleLabAnalysisResponse | null;
  styleLabError: ErrorResponse['error'] | null;
  profileReady: boolean;
  // Handlers
  onAnalyze: () => void;
  onOpenTryOnFromStyleLab: (product: ProductCatalogItem) => void;
  onNavigateToRecommend: () => void;
}

export function StyleLabView({
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
  catalogMode,
  catalogPlatform,
  catalogQuery,
  catalogItems,
  catalogTotal,
  catalogLoading,
  catalogError,
  catalogGenderFallback,
  canLoadMoreCatalog,
  onCatalogModeChange,
  onCatalogPlatformChange,
  onCatalogQueryChange,
  onCatalogSelectProduct,
  onLoadMoreCatalog,
  selectedProduct,
  styleLabLoading,
  styleLabResult,
  styleLabError,
  profileReady,
  onAnalyze,
  onOpenTryOnFromStyleLab,
  onNavigateToRecommend,
}: StyleLabViewProps) {
  const { t } = useTranslation(['styleLab', 'common']);
  const locale = normalizeLocale(i18n.resolvedLanguage) ?? DEFAULT_LOCALE;
  const analysisRef = useRef<HTMLDivElement | null>(null);
  const profileFooter = (
    <div className="glass-panel" style={{ padding: 18 }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>{t('hero.usageTitle')}</div>
      <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
        {t('hero.usage')}
      </p>
    </div>
  );

  return (
    <div className="style-lab-page">
      <div className="glass-panel style-lab-hero" style={{ padding: 24, marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 24, alignItems: 'center', flexWrap: 'wrap' }}>
          <div>
            <div style={{ display: 'inline-flex', gap: 8, alignItems: 'center', fontSize: 12, color: 'var(--accent-blue-text)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              <Sparkles size={14} /> {t('hero.eyebrow')}
            </div>
            <h1 style={{ fontSize: 'clamp(1.5rem, 4vw, 2.125rem)', fontWeight: 600, letterSpacing: '-0.02em', marginBottom: 8 }}>{t('hero.title')}</h1>
            <p style={{ color: 'var(--text-secondary)', maxWidth: 720 }}>{t('hero.description')}</p>
          </div>

          <button type="button" className="btn-secondary" onClick={onNavigateToRecommend} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minHeight: 44 }}>
            <ArrowLeft size={16} /> {t('hero.back')}
          </button>
        </div>
      </div>

      <div className="style-lab-shell">
        <div>
          <ProfilePanel
            eyebrow={t('profile.eyebrow')}
            title={<>{t('profile.title')} <span className="text-gradient">Profile</span></>}
            description={t('profile.description')}
            footer={profileFooter}
            photoPreview={photoPreview}
            fileInputRef={fileInputRef}
            onDragOver={onDragOver}
            onDrop={onDrop}
            onPhotoUpload={onPhotoUpload}
            sampleModelGender={sampleModelGender}
            selectedSampleModel={selectedSampleModel}
            onSampleModelGenderChange={onSampleModelGenderChange}
            onSelectSampleModel={onSelectSampleModel}
            formData={formData}
            onInputChange={onInputChange}
            onColorSelect={onColorSelect}
            onBrandSelect={onBrandSelect}
          />
        </div>

        <CatalogPanel
          catalogMode={catalogMode}
          catalogPlatform={catalogPlatform}
          catalogQuery={catalogQuery}
          catalogItems={catalogItems}
          catalogTotal={catalogTotal}
          catalogLoading={catalogLoading}
          catalogError={catalogError}
          catalogGenderFallback={catalogGenderFallback}
          selectedProduct={selectedProduct}
          canLoadMore={canLoadMoreCatalog}
          onModeChange={onCatalogModeChange}
          onPlatformChange={onCatalogPlatformChange}
          onQueryChange={onCatalogQueryChange}
          onSelectProduct={(product) => {
            onCatalogSelectProduct(product);
            if (typeof window !== 'undefined' && window.innerWidth <= 1024) {
              window.requestAnimationFrame(() => {
                analysisRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
              });
            }
          }}
          onLoadMore={onLoadMoreCatalog}
        />

        <div ref={analysisRef} className="glass-panel style-lab-column style-lab-analysis style-lab-panel" style={{ padding: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 18 }}>
            <div>
              <h3 style={{ fontSize: 18, fontWeight: 600, marginBottom: 6 }}>{t('analysis.title')}</h3>
              <p style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{t('analysis.description')}</p>
            </div>
            {selectedProduct && <span style={{ fontSize: 12, color: 'var(--accent-blue-text)' }}>{t('analysis.selected')}</span>}
          </div>

          {styleLabError && <div style={{ marginBottom: 16 }}><ErrorBanner error={styleLabError} /></div>}

          {!selectedProduct && (
            <div className="catalog-empty-state" style={{ minHeight: 220 }}>
              <Sparkles size={32} style={{ opacity: 0.5, marginBottom: 12 }} />
              <div>{t('analysis.empty')}</div>
            </div>
          )}

          {selectedProduct && (
            <>
              <div className="style-lab-selected-card">
                <div style={{ width: 120, height: 150, flexShrink: 0, borderRadius: 12, overflow: 'hidden', background: '#06070a' }}>
                  <img src={buildImageURL(selectedProduct.image_url)} alt={selectedProduct.display?.title ?? selectedProduct.title} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
                    <h4 style={{ fontSize: 18, lineHeight: 1.5, color: '#F8FAFC' }}>{selectedProduct.display?.title ?? selectedProduct.title}</h4>
                    <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{selectedProduct.gender_label}</span>
                  </div>
                  {selectedProduct.brand && <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-tertiary)' }}>{t('catalog.brand')}: {selectedProduct.brand}</div>}
                  {selectedProduct.platform && <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-tertiary)' }}>{t('catalog.platformLabel')}: {selectedProduct.platform}</div>}
                  <div style={{ marginTop: 10, fontSize: 24, fontWeight: 600, color: 'var(--accent-blue-text)' }}>{formatCurrency(selectedProduct.price, locale)}</div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 12 }}>
                    {selectedProduct.brand && <span className="catalog-tag">{selectedProduct.brand}</span>}
                    {selectedProduct.platform && <span className="catalog-tag">{selectedProduct.platform}</span>}
                    <span className="catalog-tag">{selectedProduct.display?.colorFamily ?? selectedProduct.color_family}</span>
                    <span className="catalog-tag">{selectedProduct.display?.styleType ?? selectedProduct.style_type}</span>
                    {(selectedProduct.display?.functionFeatures ?? selectedProduct.function_features).slice(0, 2).map((feature) => <span key={feature} className="catalog-tag">{feature}</span>)}
                  </div>
                </div>
              </div>

              <button className="btn-primary" style={{ width: '100%', minHeight: 48, marginTop: 18 }} onClick={onAnalyze} disabled={styleLabLoading || !profileReady}>
                {styleLabLoading ? <Loader2 className="animate-spin" /> : <Sparkles size={18} />}
                {styleLabLoading ? t('analysis.analyzing') : t('analysis.analyze')}
              </button>

              <button
                className="btn-glowing"
                style={{ width: '100%', minHeight: 44, marginTop: 10, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8, background: 'linear-gradient(135deg, rgba(99,102,241,0.25), rgba(168,85,247,0.25))', border: '1px solid rgba(139,92,246,0.4)', color: '#c4b5fd', fontWeight: 500, fontSize: 15 }}
                onClick={() => void onOpenTryOnFromStyleLab(selectedProduct)}
              >
                ✨ {t('analysis.tryOn')} <ChevronRight size={16} />
              </button>

              {!styleLabLoading && !styleLabResult && !styleLabError && (
                <div style={{ marginTop: 16, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                  {t('analysis.noResult')}
                </div>
              )}

              {styleLabResult && (
                <div style={{ marginTop: 20, display: 'flex', flexDirection: 'column', gap: 18 }}>
                  <div className="style-lab-score-strip">
                    <div>
                      <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{t('analysis.score')}</div>
                      <div style={{ fontSize: 38, fontWeight: 700, color: '#F8FAFC', lineHeight: 1 }}>{styleLabResult.analysis.total_score.toFixed(1)}</div>
                    </div>
                    <div style={{ display: 'flex', gap: '12px 18px', flexWrap: 'wrap' }}>
                      <div><div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{t('analysis.size')}</div><div style={{ fontSize: 18, fontWeight: 600 }}>{styleLabResult.inference.resolved_size}</div></div>
                      <div><div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{t('analysis.style')}</div><div style={{ fontSize: 18, fontWeight: 600 }}>{styleLabResult.inference.display?.style ?? styleLabResult.inference.resolved_style}</div></div>
                    </div>
                  </div>

                  <div className="glass-panel" style={{ padding: 18 }}>
                    <div style={{ fontSize: 13, color: 'var(--accent-blue-text)', marginBottom: 8 }}>{t('analysis.summary')}</div>
                    <p style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.7 }}>{styleLabResult.analysis.reason}</p>
                  </div>

                  <div className="glass-panel" style={{ padding: 18 }}>
                    <div style={{ fontSize: 13, color: 'var(--accent-blue-text)', marginBottom: 10 }}>{t('analysis.dimensions')}</div>
                    <RadarChart data={styleLabResult.analysis.radar_chart} />
                    <ScoreBreakdown breakdown={styleLabResult.analysis.score_breakdown} />
                    {styleLabResult.analysis.brand_note && (
                      <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-secondary)' }}>{styleLabResult.analysis.brand_note}</div>
                    )}
                  </div>

                  <div className="glass-panel" style={{ padding: 18 }}>
                    <div style={{ fontSize: 13, color: 'var(--accent-blue-text)', marginBottom: 10 }}>{t('analysis.advice')}</div>
                    <div className="analysis-advice-list">
                      {styleLabResult.analysis.styling_advice.map((advice) => (
                        <div key={advice} className="analysis-advice-item">{advice}</div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
