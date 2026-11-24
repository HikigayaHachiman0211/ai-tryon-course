import { ChevronRight, Loader2, SlidersHorizontal, Sparkles } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { buildImageURL } from '../api';
import { ErrorBanner } from '../components/ErrorBanner';
import { ProfilePanel } from '../components/ProfilePanel';
import { RadarChart } from '../components/RadarChart';
import { ScoreBreakdown } from '../components/ScoreBreakdown';
import { GENDER_LABELS, type SampleModel } from '../constants/formOptions';
import type {
  ErrorResponse,
  RecommendationRequest,
  RecommendationResponse,
} from '../types';
import { formatCurrency } from '../i18n/formatters';
import i18n from '../i18n';
import { DEFAULT_LOCALE, normalizeLocale } from '../i18n/locale';

export interface RecommendViewProps {
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
  // Recommendation state
  loading: boolean;
  profileReady: boolean;
  error: ErrorResponse['error'] | null;
  result: RecommendationResponse | null;
  visibleItemCount: number;
  tryOnMessage: string | null;
  // Handlers
  onRunRecommendation: () => void;
  onNavigateToStyleLab: () => void;
  onOpenTryOnWorkbench: (item: RecommendationResponse['items'][number]) => void;
  onLoadMoreItems: () => void;
}

export function RecommendView({
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
  loading,
  profileReady,
  error,
  result,
  visibleItemCount,
  tryOnMessage,
  onRunRecommendation,
  onNavigateToStyleLab,
  onOpenTryOnWorkbench,
  onLoadMoreItems,
}: RecommendViewProps) {
  const { t } = useTranslation(['recommend', 'common']);
  const locale = normalizeLocale(i18n.resolvedLanguage) ?? DEFAULT_LOCALE;
  const displayedItems = result ? result.items.slice(0, visibleItemCount) : [];
  const canLoadMore = Boolean(result && visibleItemCount < result.items.length);

  return (
    <div className="app-container">
      <ProfilePanel
        eyebrow={t('hero.eyebrow')}
        title={<>{t('hero.title')}</>}
        description={t('hero.description')}
        footer={
          <button className="btn-primary" style={{ width: '100%', minHeight: 50 }} onClick={onRunRecommendation} disabled={loading || !profileReady}>
            {loading ? <Loader2 className="animate-spin" /> : <Sparkles size={18} />}
            {loading ? t('actions.generating') : t('actions.generate')}
          </button>
        }
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

      <section className="results-column" style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button className="btn-glowing" style={{ width: 'auto' }} onClick={onNavigateToStyleLab}>
            {t('actions.styleLab')} <ChevronRight size={16} />
          </button>
        </div>

        <AnimatePresence mode="wait">
          {error && <ErrorBanner error={error} />}

          {!result && !loading && !error && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ flex: 1, minHeight: 200, padding: '24px 16px', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', textAlign: 'center', border: '1px dashed var(--border-subtle)', borderRadius: 12, color: 'var(--text-tertiary)' }}>
              <SlidersHorizontal size={48} style={{ marginBottom: 16, opacity: 0.5 }} />
              <p>{t('empty.startHint')}</p>
            </motion.div>
          )}

          {result && (
            <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              <div className="glass-panel recommendation-summary-panel" style={{ padding: 24, position: 'relative', overflow: 'hidden' }}>
                <div style={{ position: 'absolute', top: -50, right: -50, width: 150, height: 150, background: 'var(--accent-blue-glow)', filter: 'blur(50px)', borderRadius: '50%', opacity: result.inference.ai_provider && result.inference.ai_provider !== 'none' ? 1 : 0.2 }} />

                <h3 style={{ fontSize: 14, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent-blue-text)', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <Sparkles size={16} />
                  {t('summary.title')}
                  {result.inference.ai_provider === 'gemini' && <span style={{ fontSize: 10, background: 'rgba(56,189,248,0.2)', padding: '2px 6px', borderRadius: 10 }}>{t('summary.provider.gemini')}</span>}
                  {result.inference.ai_provider === 'mimo' && <span style={{ fontSize: 10, background: 'rgba(255,107,0,0.2)', padding: '2px 6px', borderRadius: 10, color: '#ff6b00' }}>{t('summary.provider.mimo')}</span>}
                  {result.inference.ai_provider === 'deepseek' && <span style={{ fontSize: 10, background: 'rgba(74,222,128,0.2)', padding: '2px 6px', borderRadius: 10, color: '#4ade80' }}>{t('summary.provider.deepseek')}</span>}
                  {result.inference.ai_provider === 'opencode_go' && <span style={{ fontSize: 10, background: 'rgba(168,85,247,0.22)', padding: '2px 6px', borderRadius: 10, color: '#c084fc' }}>{t('summary.provider.opencode_go')}</span>}
                  {(!result.inference.ai_provider || result.inference.ai_provider === 'none') && <span style={{ fontSize: 10, background: 'rgba(255,255,255,0.08)', padding: '2px 6px', borderRadius: 10 }}>{t('summary.provider.rules')}</span>}
                </h3>

                <div className="summary-metrics-grid">
                  <div><span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{t('summary.size')}</span><div style={{ fontSize: 24, fontWeight: 600 }}>{result.inference.resolved_size}</div></div>
                  <div><span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{t('summary.bodyShape')}</span><div style={{ fontSize: 16, fontWeight: 500, marginTop: 6 }}>{result.inference.display?.bodyShape ?? result.inference.body_shape}</div></div>
                  <div><span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{t('summary.style')}</span><div style={{ fontSize: 16, fontWeight: 500, marginTop: 6 }}>{result.inference.display?.style ?? result.inference.resolved_style}</div></div>
                </div>

                <div style={{ background: 'rgba(255,255,255,0.03)', padding: 16, borderRadius: 8, fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6, borderLeft: '3px solid var(--accent-blue-text)' }}>
                  "{result.inference.reasoning}"
                </div>

                <div style={{ marginTop: 16, fontSize: 11, color: 'var(--text-tertiary)' }}>
                  {t('summary.matched', { gender: result.filters.user_gender ? t(GENDER_LABELS[result.filters.user_gender] || 'summary.current') : t('summary.current'), matched: result.filters.matched_after_gender_filter ?? result.filters.matched_after_price_filter, total: result.filters.catalog_total })}
                </div>

                {result.filters.brand_preference && (
                  <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
                    {t('summary.brandPreference', { brand: result.filters.brand_preference })}
                  </div>
                )}

                {result.filters.gender_fallback && (
                  <div style={{ marginTop: 8, fontSize: 11, color: 'var(--accent-warm)' }}>
                    {t('summary.genderFallback')}
                  </div>
                )}

                {tryOnMessage && (
                  <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-secondary)' }}>{tryOnMessage}</div>
                )}
              </div>

              {result.items.length === 0 && (
                <div className="bento-item" style={{ padding: 24 }}>
                  <h3 style={{ fontSize: 18, marginBottom: 8 }}>{t('empty.noResults')}</h3>
                  <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>{result.message || t('empty.noResultsHint')}</p>
                </div>
              )}

              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                {displayedItems.map((item, index) => (
                  <motion.div key={item.id} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.1 }} className="bento-item recommend-card recommend-card-layout" style={{ padding: undefined }}>
                    <div className="recommend-card-thumb">
                      <img src={buildImageURL(item.image_url)} alt={item.display?.title ?? item.title} style={{ width: '100%', height: '100%', objectFit: 'cover' }} onError={(event) => { event.currentTarget.src = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='180' viewBox='0 0 140 180'%3E%3Crect width='140' height='180' fill='%23111318'/%3E%3Ctext x='70' y='94' fill='%236b7280' font-family='sans-serif' font-size='12' text-anchor='middle'%3ENo image%3C/text%3E%3C/svg%3E"; }} />
                    </div>

                    <div className="recommend-card-body">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, flexWrap: 'wrap' }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <h3 style={{ fontSize: 18, fontWeight: 600, color: '#F8FAFC', marginBottom: 4 }}>{item.display?.title ?? item.title}</h3>
                          {item.brand && <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 4 }}>{t('product.brand')}: {item.brand}</div>}
                          {item.platform && <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 4 }}>{t('product.platform')}: {item.platform}</div>}
                          <div style={{ fontSize: 20, fontWeight: 500, color: 'var(--accent-blue-text)' }}>{formatCurrency(item.price, locale)}</div>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'rgba(41,151,255,0.14)', border: '1px solid rgba(41,151,255,0.28)', padding: '6px 12px', borderRadius: 999, color: '#60a5fa', fontSize: 13, fontWeight: 600, flexShrink: 0, whiteSpace: 'nowrap' }}>
                          {t('product.score')}: {item.total_score.toFixed(1)}
                        </div>
                      </div>

                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', margin: '12px 0' }}>
                        {item.brand && <span style={{ fontSize: 11, background: 'rgba(56,189,248,0.1)', border: '1px solid rgba(56,189,248,0.22)', color: '#bae6fd', padding: '3px 10px', borderRadius: 999 }}>{t('product.brand')}: {item.brand}</span>}
                        {(item.display?.styleFeatures ?? item.style_features).map((feature) => <span key={feature} className="feature-pill">{feature}</span>)}
                        {(item.display?.functionFeatures ?? item.function_features).map((feature) => <span key={feature} className="feature-pill">{feature}</span>)}
                        <span className="feature-pill">{item.display?.styleType ?? item.style_type}</span>
                        {item.platform && <span style={{ fontSize: 11, background: 'rgba(16,185,129,0.14)', border: '1px solid rgba(16,185,129,0.26)', color: '#A7F3D0', padding: '3px 10px', borderRadius: 999 }}>{item.platform}</span>}
                      </div>

                      <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 8, lineHeight: 1.5, flex: 1 }}>{item.reason}</p>
                      <ScoreBreakdown breakdown={item.score_breakdown} />

                      {item.size_notes && (
                        <div style={{ fontSize: 12, background: 'rgba(245, 158, 11, 0.1)', color: 'var(--accent-warm)', padding: '8px 12px', borderRadius: 6, marginBottom: 12 }}>
                          📏 {t('product.sizeNote')}: {item.display?.sizeNotes ?? item.size_notes}
                        </div>
                      )}

                      <div style={{ marginTop: 'auto', alignSelf: 'stretch', display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                        <button className="btn-glowing" style={{ width: 'auto' }} onClick={() => onOpenTryOnWorkbench(item)}>
                          ✨ {t('product.tryOn')} <ChevronRight size={16} />
                        </button>
                        {item.product_url && (
                          <a
                            href={item.product_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="btn-secondary"
                            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, textDecoration: 'none' }}
                          >
                            🛒 {t('product.shop', { platform: item.platform || t('product.store') })}
                          </a>
                        )}
                        <button className="btn-secondary" onClick={onNavigateToStyleLab}>{t('actions.styleLab')}</button>
                      </div>
                    </div>

                    <div className="recommend-card-radar">
                      <RadarChart data={item.radar_chart} />
                    </div>
                  </motion.div>
                ))}

                {result.items.length > 0 && (
                  <div className="load-more-panel" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, paddingBottom: 8 }}>
                    <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                      {t('product.shown', { shown: displayedItems.length, total: result.items.length })}
                    </div>
                    {canLoadMore && (
                      <button
                        className="btn-secondary"
                        style={{ minWidth: 220 }}
                        onClick={onLoadMoreItems}
                      >
                        {t('actions.loadMore')}
                      </button>
                    )}
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </section>
    </div>
  );
}
