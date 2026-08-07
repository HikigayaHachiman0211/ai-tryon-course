import { ChevronRight, Loader2, SlidersHorizontal, Sparkles } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
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
  const displayedItems = result ? result.items.slice(0, visibleItemCount) : [];
  const canLoadMore = Boolean(result && visibleItemCount < result.items.length);

  return (
    <div className="app-container">
      <ProfilePanel
        eyebrow="Personalized Winter Style"
        title={<>AI 羽绒服推荐</>}
        description="上传全身照并填写偏好，让 AI 为你精准推荐合适的冬季羽绒服搭配。"
        footer={
          <button className="btn-primary" style={{ width: '100%', height: 50 }} onClick={onRunRecommendation} disabled={loading || !profileReady}>
            {loading ? <Loader2 className="animate-spin" /> : <Sparkles size={18} />}
            {loading ? '推荐生成中...' : '开始生成 AI 推荐'}
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
            我来自己搭配 <ChevronRight size={16} />
          </button>
        </div>

        <AnimatePresence mode="wait">
          {error && <ErrorBanner error={error} />}

          {!result && !loading && !error && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', border: '1px dashed var(--border-subtle)', borderRadius: 12, color: 'var(--text-tertiary)' }}>
              <SlidersHorizontal size={48} style={{ marginBottom: 16, opacity: 0.5 }} />
              <p>填写左侧条件后即可开始智能推荐。</p>
            </motion.div>
          )}

          {result && (
            <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              <div className="glass-panel recommendation-summary-panel" style={{ padding: 24, position: 'relative', overflow: 'hidden' }}>
                <div style={{ position: 'absolute', top: -50, right: -50, width: 150, height: 150, background: 'var(--accent-blue-glow)', filter: 'blur(50px)', borderRadius: '50%', opacity: result.inference.ai_provider && result.inference.ai_provider !== 'none' ? 1 : 0.2 }} />

                <h3 style={{ fontSize: 14, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent-blue-text)', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Sparkles size={16} />
                  AI 推断摘要
                  {result.inference.ai_provider === 'gemini' && <span style={{ fontSize: 10, background: 'rgba(56,189,248,0.2)', padding: '2px 6px', borderRadius: 10 }}>Gemini 增强</span>}
                  {result.inference.ai_provider === 'mimo' && <span style={{ fontSize: 10, background: 'rgba(255,107,0,0.2)', padding: '2px 6px', borderRadius: 10, color: '#ff6b00' }}>MiMo 增强</span>}
                  {result.inference.ai_provider === 'deepseek' && <span style={{ fontSize: 10, background: 'rgba(74,222,128,0.2)', padding: '2px 6px', borderRadius: 10, color: '#4ade80' }}>Deepseek 增强</span>}
                  {(!result.inference.ai_provider || result.inference.ai_provider === 'none') && <span style={{ fontSize: 10, background: 'rgba(255,255,255,0.08)', padding: '2px 6px', borderRadius: 10 }}>规则推断</span>}
                </h3>

                <div style={{ display: 'flex', gap: 24, marginBottom: 16 }}>
                  <div><span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>推荐尺码</span><div style={{ fontSize: 24, fontWeight: 600 }}>{result.inference.resolved_size}</div></div>
                  <div><span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>身型判断</span><div style={{ fontSize: 16, fontWeight: 500, marginTop: 6 }}>{result.inference.body_shape}</div></div>
                  <div><span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>推荐款式</span><div style={{ fontSize: 16, fontWeight: 500, marginTop: 6 }}>{result.inference.resolved_style}</div></div>
                </div>

                <div style={{ background: 'rgba(255,255,255,0.03)', padding: 16, borderRadius: 8, fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6, borderLeft: '3px solid var(--accent-blue-text)' }}>
                  "{result.inference.reasoning}"
                </div>

                <div style={{ marginTop: 16, fontSize: 11, color: 'var(--text-tertiary)' }}>
                  已按{GENDER_LABELS[result.filters.user_gender || ''] || '当前'}条件匹配出 {result.filters.matched_after_gender_filter ?? result.filters.matched_after_price_filter} / {result.filters.catalog_total} 件商品
                </div>

                {result.filters.brand_preference && (
                  <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
                    当前品牌偏好：{result.filters.brand_preference}
                  </div>
                )}

                {result.filters.gender_fallback && (
                  <div style={{ marginTop: 8, fontSize: 11, color: 'var(--accent-warm)' }}>
                    当前价位下未找到明确标注所选性别的商品，已放宽到未标注性别的商品。
                  </div>
                )}

                {tryOnMessage && (
                  <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-secondary)' }}>{tryOnMessage}</div>
                )}
              </div>

              {result.items.length === 0 && (
                <div className="bento-item" style={{ padding: 24 }}>
                  <h3 style={{ fontSize: 18, marginBottom: 8 }}>暂无匹配推荐</h3>
                  <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>{result.message || '可以尝试放宽价格区间或减少可选筛选条件。'}</p>
                </div>
              )}

              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                {displayedItems.map((item, index) => (
                  <motion.div key={item.id} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.1 }} className="bento-item recommend-card" style={{ display: 'flex', gap: 20, padding: 20 }}>
                    <div style={{ width: 140, height: 180, borderRadius: 8, overflow: 'hidden', background: '#000', flexShrink: 0 }}>
                      <img src={buildImageURL(item.image_url)} alt={item.title} style={{ width: '100%', height: '100%', objectFit: 'cover' }} onError={(event) => { event.currentTarget.src = 'https://via.placeholder.com/140x180?text=%E6%9A%82%E6%97%A0%E5%9B%BE%E7%89%87'; }} />
                    </div>

                    <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <h3 style={{ fontSize: 18, fontWeight: 600, color: '#F8FAFC', marginBottom: 4 }}>{item.title}</h3>
                          {item.brand && <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 4 }}>品牌：{item.brand}</div>}
                          {item.platform && <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 4 }}>平台：{item.platform}</div>}
                          <div style={{ fontSize: 20, fontWeight: 500, color: 'var(--accent-blue-text)' }}>¥{item.price}</div>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'rgba(56,189,248,0.1)', padding: '6px 10px', borderRadius: 20, color: 'var(--accent-blue-text)', fontWeight: 600 }}>
                          总分：{item.total_score.toFixed(1)}
                        </div>
                      </div>

                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', margin: '12px 0' }}>
                        {item.brand && <span style={{ fontSize: 11, background: 'rgba(56,189,248,0.08)', border: '1px solid rgba(56,189,248,0.18)', padding: '2px 8px', borderRadius: 4 }}>品牌：{item.brand}</span>}
                        {item.style_features.map((feature) => <span key={feature} style={{ fontSize: 11, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', padding: '2px 8px', borderRadius: 4 }}>{feature}</span>)}
                        {item.function_features.map((feature) => <span key={feature} style={{ fontSize: 11, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', padding: '2px 8px', borderRadius: 4 }}>{feature}</span>)}
                        <span style={{ fontSize: 11, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', padding: '2px 8px', borderRadius: 4 }}>{item.style_type}</span>
                        {item.platform && <span style={{ fontSize: 11, background: 'rgba(16,185,129,0.12)', border: '1px solid rgba(16,185,129,0.22)', color: '#A7F3D0', padding: '2px 8px', borderRadius: 4 }}>{item.platform}</span>}
                      </div>

                      <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 8, lineHeight: 1.5, flex: 1 }}>{item.reason}</p>
                      <ScoreBreakdown breakdown={item.score_breakdown} />

                      {item.size_notes && (
                        <div style={{ fontSize: 12, background: 'rgba(245, 158, 11, 0.1)', color: 'var(--accent-warm)', padding: '8px 12px', borderRadius: 6, marginBottom: 12 }}>
                          📏 尺码提示：{item.size_notes}
                        </div>
                      )}

                      <div style={{ marginTop: 'auto', alignSelf: 'flex-start', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                        <button className="btn-glowing" style={{ width: 'auto' }} onClick={() => onOpenTryOnWorkbench(item)}>
                          ✨ 尝试这件衣服 <ChevronRight size={16} />
                        </button>
                        {item.product_url && (
                          <a
                            href={item.product_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="btn-secondary"
                            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, textDecoration: 'none' }}
                          >
                            🛒 去{item.platform || '商城'}选购
                          </a>
                        )}
                        <button className="btn-secondary" onClick={onNavigateToStyleLab}>我来自己搭配</button>
                      </div>
                    </div>

                    <div style={{ width: 220, flexShrink: 0, display: 'flex', alignItems: 'center' }}>
                      <RadarChart data={item.radar_chart} />
                    </div>
                  </motion.div>
                ))}

                {result.items.length > 0 && (
                  <div className="load-more-panel" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, paddingBottom: 8 }}>
                    <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                      已展示 {displayedItems.length} / {result.items.length} 条推荐，按分数从高到低排序
                    </div>
                    {canLoadMore && (
                      <button
                        className="btn-secondary"
                        style={{ minWidth: 220 }}
                        onClick={onLoadMoreItems}
                      >
                        加载更多推荐
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
