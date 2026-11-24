import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Clock } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { analyzeStyleLab, buildImageURL, getCatalogProducts, getHistoryDetail, getRecommend, localizeResult } from './api';
import {
  type TryOnBridgePayload,
  getTryOnBaseUrl,
  getTryOnOrigin,
  openTryOnWindow,
  postTryOnPayloadWithAck,
} from './tryonBridge';
import type {
  ErrorResponse,
  HistoryEntry,
  ProductCatalogItem,
  RecommendationRequest,
  RecommendationResponse,
  StyleLabAnalysisResponse,
} from './types';
import { applyAssistantFormPatch } from './assistant/utils/formPatch';
import type { RecommendFormPatch } from './assistant/assistantTypes';
import {
  SAMPLE_MODELS,
  type ViewMode,
  type CatalogMode,
  type CatalogPlatform,
  type SampleModel,
  getInitialView,
} from './constants/formOptions';
import { LanguageSwitcher } from './i18n/LanguageSwitcher';
import i18n, { setAppLocale } from './i18n';
import { DEFAULT_LOCALE, normalizeLocale, type AppLocale } from './i18n/locale';
import { getAdminUrl } from './utils/adminUrl';
import { toApiError } from './utils/apiError';
import { fileToDataUrl } from './utils/fileUtils';
import { RecommendView } from './views/RecommendView';
import { StyleLabView } from './views/StyleLabView';
import './index.css';

const DebugDrawer = React.lazy(async () => ({ default: (await import('./components/DebugDrawer')).DebugDrawer }));
const HistoryDrawer = React.lazy(async () => ({ default: (await import('./components/HistoryDrawer')).HistoryDrawer }));
const FloatingAssistant = React.lazy(async () => ({ default: (await import('./assistant/components/FloatingAssistant')).FloatingAssistant }));


export default function App() {
  const { t } = useTranslation('common');
  const locale = normalizeLocale(i18n.resolvedLanguage) ?? DEFAULT_LOCALE;
  const [view, setView] = useState<ViewMode>(getInitialView);
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);

  const [formData, setFormData] = useState<RecommendationRequest>({
    color_preference: '',
  });

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RecommendationResponse | null>(null);
  const [error, setError] = useState<ErrorResponse['error'] | null>(null);
  const [tryOnMessage, setTryOnMessage] = useState<string | null>(null);
  const [tryOnFallbackUrl, setTryOnFallbackUrl] = useState<string | null>(null);
  const [visibleRecommendationCount, setVisibleRecommendationCount] = useState(3);

  const [catalogMode, setCatalogMode] = useState<CatalogMode>('gender');
  const [catalogPlatform, setCatalogPlatform] = useState<CatalogPlatform>('all');
  const [catalogQuery, setCatalogQuery] = useState('');
  const [catalogItems, setCatalogItems] = useState<ProductCatalogItem[]>([]);
  const [catalogTotal, setCatalogTotal] = useState(0);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [catalogGenderFallback, setCatalogGenderFallback] = useState(false);
  const catalogGenerationRef = useRef(0);
  const catalogRequestRef = useRef(0);
  const catalogReadyRef = useRef(false);

  const [selectedProduct, setSelectedProduct] = useState<ProductCatalogItem | null>(null);
  const [styleLabLoading, setStyleLabLoading] = useState(false);
  const [styleLabResult, setStyleLabResult] = useState<StyleLabAnalysisResponse | null>(null);
  const [styleLabError, setStyleLabError] = useState<ErrorResponse['error'] | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const recommendPhotoFileRef = useRef<File | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [sampleModelGender, setSampleModelGender] = useState<'male' | 'female'>('male');
  const [selectedSampleModel, setSelectedSampleModel] = useState<string | null>(null);

  const handleLocaleChange = useCallback(async (nextLocale: AppLocale) => {
    try {
      await setAppLocale(nextLocale);
    } catch {
      setTryOnMessage(t('common.localeSwitchFailed'));
    }
  }, [t]);

  useEffect(() => {
    const syncView = () => {
      setView(getInitialView());
    };

    window.addEventListener('hashchange', syncView);
    return () => {
      window.removeEventListener('hashchange', syncView);
    };
  }, []);

  useEffect(() => {
    return () => {
      if (photoPreview?.startsWith('blob:')) {
        URL.revokeObjectURL(photoPreview);
      }
    };
  }, [photoPreview]);

  useEffect(() => {
    setStyleLabResult(null);
    setStyleLabError(null);
  }, [photoFile, formData.color_preference, formData.brand_preference, formData.gender, formData.mbti, formData.size, formData.style_preference, formData.price_min, formData.price_max]);

  useEffect(() => {
    if (!result || result.locale === locale) return;
    let cancelled = false;
    void localizeResult('recommend', result, locale).then((localized) => {
      if (!cancelled) setResult((current) => current === result ? localized : current);
    }).catch(() => { /* Keep the previous result available if localization fails. */ });
    return () => { cancelled = true; };
  }, [locale, result]);

  useEffect(() => {
    if (!styleLabResult || styleLabResult.locale === locale) return;
    let cancelled = false;
    void localizeResult('style-lab', styleLabResult, locale).then((localized) => {
      if (cancelled) return;
      setStyleLabResult((current) => current === styleLabResult ? localized : current);
      setSelectedProduct((current) => current?.id === localized.product.id ? localized.product : current);
    }).catch(() => { /* Keep the previous analysis available if localization fails. */ });
    return () => { cancelled = true; };
  }, [locale, styleLabResult]);

  useEffect(() => {
    if (!selectedProduct || selectedProduct.locale === locale || styleLabResult?.product.id === selectedProduct.id) return;
    let cancelled = false;
    void localizeResult('product', selectedProduct, locale).then((localized) => {
      if (!cancelled) setSelectedProduct((current) => current === selectedProduct ? localized : current);
    }).catch(() => { /* Keep the selected product available if localization fails. */ });
    return () => { cancelled = true; };
  }, [locale, selectedProduct, styleLabResult]);

  const profileReady = Boolean(formData.color_preference && formData.gender);
  const canLoadMoreCatalog = catalogItems.length < catalogTotal;
  const assistantCurrentForm = {
    ...formData,
    photo_uploaded: Boolean(photoFile),
    photo_name: photoFile?.name || null,
    photo_type: photoFile?.type || null,
    recommendation_inference: result?.inference
      ? {
          resolved_size: result.inference.resolved_size,
          resolved_style: result.inference.resolved_style,
          body_shape: result.inference.body_shape,
          reasoning: result.inference.reasoning,
          ai_provider: result.inference.ai_provider,
          vision_provider_used: result.inference.vision_provider_used,
          mimo_used: result.inference.mimo_used,
          mimo_multimodal_used: result.inference.mimo_multimodal_used,
          rule_fallback_used: result.inference.rule_fallback_used,
        }
      : null,
    recommendation_items: result?.items.slice(0, 3).map((item) => ({
      id: item.id,
      title: item.title,
      price: item.price,
      brand: item.brand,
      style_type: item.style_type,
      color_family: item.color_family,
      total_score: item.total_score,
      reason: item.reason,
    })) || [],
  };

  const navigateToView = useCallback((nextView: ViewMode) => {
    if (nextView === 'style-lab') {
      window.location.hash = 'style-lab';
      setView('style-lab');
      return;
    }

    window.history.pushState({}, document.title, window.location.pathname + window.location.search);
    setView('recommend');
  }, []);

  useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (event.origin !== getTryOnOrigin()) {
        return;
      }

      const message = event.data;
      if (!message || typeof message !== 'object') {
        return;
      }

      const type = String((message as { type?: string }).type || '').toUpperCase();
      if (type === 'DOWN_JACKET_TRYON_BACK') {
        navigateToView('recommend');
        setTryOnMessage(t('common.tryOnReturned'));
      }
      if (type === 'DOWN_JACKET_TRYON_SWITCH_REQUEST') {
        navigateToView('recommend');
        setTryOnMessage(t('common.tryOnSwitchRequested'));
      }
    };

    window.addEventListener('message', handler);
    return () => {
      window.removeEventListener('message', handler);
    };
  }, [navigateToView, t]);

  const updatePhotoFile = (file: File) => {
    if (photoPreview?.startsWith('blob:')) {
      URL.revokeObjectURL(photoPreview);
    }

    setPhotoFile(file);
    setPhotoPreview(URL.createObjectURL(file));
    setSelectedSampleModel(null);
  };

  const selectSampleModel = async (model: SampleModel) => {
    const imageUrl = `/sample-models/${model.gender}/${model.filename}`;
    try {
      const response = await fetch(imageUrl);
      if (!response.ok) return;
      const blob = await response.blob();
      const file = new File([blob], model.filename, { type: blob.type || 'image/jpeg' });
      updatePhotoFile(file);
      setSelectedSampleModel(model.id);
    } catch {
      // Silently fail if sample model cannot be loaded
    }
  };

  const handlePhotoUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      updatePhotoFile(file);
    }
  };

  const handleDragOver = (event: React.DragEvent) => {
    event.preventDefault();
  };

  const handleDrop = (event: React.DragEvent) => {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file) {
      updatePhotoFile(file);
    }
  };

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = event.target;
    if (name === 'price_min' || name === 'price_max') {
      setFormData((previous) => ({
        ...previous,
        [name]: value === '' ? undefined : Number(value),
      }));
      return;
    }

    setFormData((previous) => ({ ...previous, [name]: value }));
  };

  const buildRequestPayload = (override?: RecommendationRequest): RecommendationRequest => ({
    ...(override || formData),
    photo: photoFile,
  });


  const runRecommendation = async (override?: RecommendationRequest) => {
    const effectiveForm = override || formData;
    if (!effectiveForm.color_preference) {
      setError({ code: 'VAL-001', message: t('common.validationColor'), request_id: 'local', details: null });
      return;
    }
    if (!effectiveForm.gender) {
      setError({ code: 'VAL-002', message: t('common.validationGender'), request_id: 'local', details: null });
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);
    setTryOnMessage(null);
    setTryOnFallbackUrl(null);

    const submittedPhoto = photoFile;
    try {
      const response = await getRecommend(buildRequestPayload(override));
      recommendPhotoFileRef.current = submittedPhoto;
      setResult(response);
      setVisibleRecommendationCount(3);
    } catch (err: unknown) {
      setError(toApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleHistorySelect = async (entry: HistoryEntry) => {
    setHistoryOpen(false);
    try {
      const detail = await getHistoryDetail(entry.id);
      if (entry.type === 'recommend' && detail.items) {
        recommendPhotoFileRef.current = null;
        setResult(detail);
        setVisibleRecommendationCount(3);
        setError(null);
        navigateToView('recommend');
      } else if (entry.type === 'style-lab' && detail.analysis) {
        setStyleLabResult(detail);
        setStyleLabError(null);
        if (detail.product) {
          setSelectedProduct(detail.product);
        }
        navigateToView('style-lab');
      }
    } catch {
      // Silently fail — the drawer has already closed
    }
  };

  const loadCatalog = useCallback(async ({ reset, offset }: { reset: boolean; offset: number }) => {
    if (!reset && !catalogReadyRef.current) return;
    const generation = catalogGenerationRef.current;
    const request = ++catalogRequestRef.current;
    const isCurrent = () => generation === catalogGenerationRef.current && request === catalogRequestRef.current;
    setCatalogLoading(true);
    setCatalogError(null);

    try {
      const response = await getCatalogProducts({
        query: catalogQuery || undefined,
        gender: formData.gender,
        platform: catalogPlatform,
        mode: catalogMode,
        offset: reset ? 0 : offset,
        limit: 24,
        price_min: formData.price_min,
        price_max: formData.price_max,
      });

      if (!isCurrent()) return;
      if (reset) catalogReadyRef.current = true;
      setCatalogItems((previous) => (reset ? response.items : [...previous, ...response.items]));
      setCatalogTotal(response.total);
      setCatalogGenderFallback(Boolean(response.gender_fallback));

      if (reset) {
        setSelectedProduct((previous) => {
          if (!previous) {
            return previous;
          }

          const matched = response.items.find((item) => item.id === previous.id);
          return matched ?? previous;
        });
      }
    } catch (err: unknown) {
      if (isCurrent()) setCatalogError(toApiError(err, t('common.catalogLoadFailed')).message);
    } finally {
      if (isCurrent()) setCatalogLoading(false);
    }
  }, [catalogMode, catalogPlatform, catalogQuery, formData.gender, formData.price_max, formData.price_min, t]);

  useEffect(() => {
    const generation = ++catalogGenerationRef.current;
    catalogRequestRef.current += 1;
    catalogReadyRef.current = false;
    if (view !== 'style-lab') {
      return undefined;
    }

    const timer = window.setTimeout(() => {
      void loadCatalog({ reset: true, offset: 0 });
    }, 140);

    return () => {
      window.clearTimeout(timer);
      if (catalogGenerationRef.current === generation) catalogGenerationRef.current += 1;
    };
  }, [view, loadCatalog, locale]);

  const analyzeCurrentSelection = async () => {
    if (!selectedProduct) {
      setStyleLabError({ code: 'LAB-SELECT', message: t('common.selectProduct'), request_id: 'local', details: null });
      return;
    }
    if (!profileReady) {
      setStyleLabError({ code: 'LAB-PROFILE', message: t('common.completeProfile'), request_id: 'local', details: null });
      return;
    }

    setStyleLabLoading(true);
    setStyleLabError(null);
    setStyleLabResult(null);

    try {
      const response = await analyzeStyleLab(selectedProduct.id, buildRequestPayload());
      setSelectedProduct(response.product);
      setStyleLabResult(response);
    } catch (err: unknown) {
      setStyleLabError(toApiError(err, t('common.analysisFailed')));
    } finally {
      setStyleLabLoading(false);
    }
  };

  const resolveBridgeUserImageUrl = (backendPhotoUrl?: string | null): string => {
    if (backendPhotoUrl) {
      return buildImageURL(backendPhotoUrl);
    }
    if (selectedSampleModel) {
      const model = SAMPLE_MODELS.find((entry) => entry.id === selectedSampleModel);
      if (model) {
        return buildImageURL(`/sample-models/${model.gender}/${model.filename}`);
      }
    }
    return '';
  };

  const buildTryOnFallbackUrl = (payload: TryOnBridgePayload): string | null => {
    try {
      const targetUrl = new URL(getTryOnBaseUrl(payload.locale));
      const cleanPayload = { ...payload };
      delete cleanPayload.userImageDataUrl;
      targetUrl.searchParams.set('lang', payload.locale);
      targetUrl.searchParams.set('tryonPayload', JSON.stringify(cleanPayload));
      return targetUrl.toString();
    } catch {
      return null;
    }
  };

  const dispatchTryOnWindow = async (payload: TryOnBridgePayload, title: string) => {
    const tryOnOrigin = getTryOnOrigin();
    if (!tryOnOrigin) {
      setTryOnMessage(t('common.tryOnUnavailable'));
      setTryOnFallbackUrl(null);
      return;
    }
    const tryonWindow = openTryOnWindow(payload);
    if (!tryonWindow) {
      setTryOnMessage(t('common.popupBlocked'));
      setTryOnFallbackUrl(buildTryOnFallbackUrl(payload));
      return;
    }
    setTryOnFallbackUrl(null);

    if (photoFile) {
      try {
        const userImageDataUrl = await fileToDataUrl(photoFile);
        postTryOnPayloadWithAck(tryonWindow, { ...payload, userImageDataUrl }, tryOnOrigin);
        setTryOnMessage(
          tryOnOrigin
            ? t('common.tryOnOpenedWithPhoto', { title })
            : t('common.tryOnOpenedWithoutPhoto', { title }),
        );
        return;
      } catch {
        postTryOnPayloadWithAck(tryonWindow, payload, tryOnOrigin);
        setTryOnMessage(t('common.tryOnOpenedWithoutPhoto', { title }));
        return;
      }
    }

    postTryOnPayloadWithAck(tryonWindow, payload, tryOnOrigin);
    setTryOnMessage(
      payload.userImageUrl
        ? t('common.tryOnOpenedWithPhoto', { title })
        : t('common.tryOnOpenedRequestPhoto', { title }),
    );
  };

  const buildTryOnPayload = (item: RecommendationResponse['items'][number]): TryOnBridgePayload => {
    const recommendPhotoValid = !photoFile || recommendPhotoFileRef.current === photoFile;
    return {
      source: 'down-jacket-recommendation',
      garmentImageUrl: buildImageURL(item.image_url),
      productTitle: item.display?.title ?? item.title,
      productId: String(item.id),
      productPrice: item.price,
      productUrl: item.product_url || '',
      styleType: item.display?.styleType ?? item.style_type,
      colorFamily: item.display?.colorFamily ?? item.color_family,
      sizeHint: formData.size || result?.inference.resolved_size || '',
      recommendationReason: item.reason,
      score: item.total_score,
      sceneHint: result?.inference.display?.style || formData.style_preference || result?.inference.resolved_style || '',
      fitNote: item.display?.sizeNotes || item.size_notes || '',
      returnUrl: window.location.href,
      locale,
      presentationSource: result ? {
        kind: 'recommend',
        result: {
          locale: result.locale,
          inference: { resolved_style: result.inference.resolved_style, resolved_size: result.inference.resolved_size },
          items: [item],
        },
      } : undefined,
      // Pass a signed/public URL via the URL channel so the workbench imports it
      // deterministically on load (postMessage data URL stays as backup).
      userImageUrl: resolveBridgeUserImageUrl(recommendPhotoValid ? result?.user_photo_url : undefined),
    };
  };

  const openTryOnFromStyleLab = async (product: ProductCatalogItem) => {
    const matchedAnalysis = styleLabResult && styleLabResult.product.id === product.id ? styleLabResult : null;
    const effectiveProduct = matchedAnalysis?.product ?? product;
    const payload: TryOnBridgePayload = {
      source: 'down-jacket-recommendation',
      garmentImageUrl: buildImageURL(effectiveProduct.image_url),
      productTitle: effectiveProduct.display?.title ?? effectiveProduct.title,
      productId: String(effectiveProduct.id),
      productPrice: effectiveProduct.price,
      productUrl: effectiveProduct.product_url || '',
      styleType: effectiveProduct.display?.styleType ?? effectiveProduct.style_type,
      colorFamily: effectiveProduct.display?.colorFamily ?? effectiveProduct.color_family,
      sizeHint: formData.size || matchedAnalysis?.inference.resolved_size || '',
      recommendationReason: matchedAnalysis?.analysis.reason || '',
      score: matchedAnalysis?.analysis.total_score,
      sceneHint:
        matchedAnalysis?.inference.display?.style
        || formData.style_preference
        || matchedAnalysis?.inference.resolved_style
        || '',
      fitNote: effectiveProduct.display?.sizeNotes || effectiveProduct.size_notes || '',
      returnUrl: window.location.href,
      locale,
      presentationSource: matchedAnalysis
        ? {
            kind: 'style-lab',
            result: {
              locale: matchedAnalysis.locale,
              product: effectiveProduct,
              inference: {
                resolved_style: matchedAnalysis.inference.resolved_style,
                resolved_size: matchedAnalysis.inference.resolved_size,
                display: matchedAnalysis.inference.display,
              },
              analysis: {
                total_score: matchedAnalysis.analysis.total_score,
                reason: matchedAnalysis.analysis.reason,
              },
            },
          }
        : { kind: 'product', result: effectiveProduct },
      userImageUrl: resolveBridgeUserImageUrl(matchedAnalysis?.user_photo_url),
    };
    await dispatchTryOnWindow(payload, effectiveProduct.display?.title ?? effectiveProduct.title);
  };

  const openTryOnWorkbench = async (item: RecommendationResponse['items'][number]) => {
    const payload = buildTryOnPayload(item);
    await dispatchTryOnWindow(payload, item.display?.title ?? item.title);
  };

  const tryOnUrl = getTryOnBaseUrl(locale);
  const adminUrl = getAdminUrl(locale);

  return (
    <>
      <div className="apple-nav">
        <div className="apple-nav-inner">
          <button className="apple-brand" onClick={() => navigateToView('recommend')}>{t('navigation.brand')}</button>
          <div className="apple-nav-links">
            {tryOnUrl && <a className="nav-chip nav-chip-tryon" href={tryOnUrl} target="_blank" rel="noopener noreferrer">{t('navigation.tryOn')}</a>}
            <button aria-current={view === 'recommend' ? 'page' : undefined} className={`nav-chip ${view === 'recommend' ? 'nav-chip-active' : ''}`} onClick={() => navigateToView('recommend')}>{t('navigation.recommend')}</button>
            <button aria-current={view === 'style-lab' ? 'page' : undefined} className={`nav-chip ${view === 'style-lab' ? 'nav-chip-active' : ''}`} onClick={() => navigateToView('style-lab')}>{t('navigation.styleLab')}</button>
            <button className="nav-history-btn" onClick={() => setHistoryOpen(true)} aria-label={t('navigation.history')}>
              <Clock size={14} />
              {t('navigation.history')}
            </button>
            {adminUrl && <a className="nav-chip nav-chip-admin" href={adminUrl} target="_blank" rel="noopener noreferrer">{t('navigation.admin')}</a>}
            <LanguageSwitcher locale={locale} onChange={(nextLocale) => void handleLocaleChange(nextLocale)} />
          </div>
        </div>
      </div>

      <div className="app-frame">
        {tryOnMessage && (
          <div className="tryon-status-banner" role="status">
            <span>{tryOnMessage}</span>
            <div className="tryon-status-banner-actions">
              {tryOnFallbackUrl && (
                <a
                  href={tryOnFallbackUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-secondary"
                  style={{ display: 'inline-flex', alignItems: 'center', minHeight: 36, padding: '6px 12px', textDecoration: 'none' }}
                >
                  {t('navigation.tryOn')}
                </a>
              )}
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  setTryOnMessage(null);
                  setTryOnFallbackUrl(null);
                }}
                style={{ minHeight: 36, padding: '6px 12px' }}
              >
                {t('common.close')}
              </button>
            </div>
          </div>
        )}
        <AnimatePresence mode="wait">
          {view === 'recommend' ? (
            <motion.div key="recommend" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
              <RecommendView
                photoPreview={photoPreview}
                fileInputRef={fileInputRef}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                onPhotoUpload={handlePhotoUpload}
                sampleModelGender={sampleModelGender}
                selectedSampleModel={selectedSampleModel}
                onSampleModelGenderChange={setSampleModelGender}
                onSelectSampleModel={selectSampleModel}
                formData={formData}
                onInputChange={handleInputChange}
                onColorSelect={(color) => setFormData((prev) => ({ ...prev, color_preference: color }))}
                onBrandSelect={(brand) => setFormData((prev) => ({ ...prev, brand_preference: brand }))}
                loading={loading}
                profileReady={profileReady}
                error={error}
                result={result}
                visibleItemCount={visibleRecommendationCount}
                tryOnMessage={tryOnMessage}
                onRunRecommendation={() => void runRecommendation()}
                onNavigateToStyleLab={() => navigateToView('style-lab')}
                onOpenTryOnWorkbench={(item) => void openTryOnWorkbench(item)}
                onLoadMoreItems={() => setVisibleRecommendationCount((prev) => prev + 6)}
              />
            </motion.div>
          ) : (
            <motion.div key="style-lab" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
              <StyleLabView
                photoPreview={photoPreview}
                fileInputRef={fileInputRef}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                onPhotoUpload={handlePhotoUpload}
                sampleModelGender={sampleModelGender}
                selectedSampleModel={selectedSampleModel}
                onSampleModelGenderChange={setSampleModelGender}
                onSelectSampleModel={selectSampleModel}
                formData={formData}
                onInputChange={handleInputChange}
                onColorSelect={(color) => setFormData((prev) => ({ ...prev, color_preference: color }))}
                onBrandSelect={(brand) => setFormData((prev) => ({ ...prev, brand_preference: brand }))}
                catalogMode={catalogMode}
                catalogPlatform={catalogPlatform}
                catalogQuery={catalogQuery}
                catalogItems={catalogItems}
                catalogTotal={catalogTotal}
                catalogLoading={catalogLoading}
                catalogError={catalogError}
                catalogGenderFallback={catalogGenderFallback}
                canLoadMoreCatalog={canLoadMoreCatalog}
                onCatalogModeChange={setCatalogMode}
                onCatalogPlatformChange={setCatalogPlatform}
                onCatalogQueryChange={setCatalogQuery}
                onCatalogSelectProduct={(product) => {
                  setSelectedProduct(product);
                  setStyleLabResult(null);
                  setStyleLabError(null);
                }}
                onLoadMoreCatalog={() => void loadCatalog({ reset: false, offset: catalogItems.length })}
                selectedProduct={selectedProduct}
                styleLabLoading={styleLabLoading}
                styleLabResult={styleLabResult}
                styleLabError={styleLabError}
                profileReady={profileReady}
                onAnalyze={() => void analyzeCurrentSelection()}
                onOpenTryOnFromStyleLab={(product) => void openTryOnFromStyleLab(product)}
                onNavigateToRecommend={() => navigateToView('recommend')}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
      <React.Suspense fallback={null}>
        <DebugDrawer />
      </React.Suspense>
      <React.Suspense fallback={null}>
        <HistoryDrawer
          open={historyOpen}
          onClose={() => setHistoryOpen(false)}
          onSelect={(entry) => void handleHistorySelect(entry)}
        />
      </React.Suspense>
      <React.Suspense fallback={null}>
        <FloatingAssistant
          currentView={view}
          currentForm={assistantCurrentForm as unknown as Record<string, unknown>}
          onFormPatch={(patch: RecommendFormPatch) => {
            setFormData((prev) => {
              const merged = applyAssistantFormPatch(prev as unknown as Record<string, unknown>, patch);
              return { ...prev, ...merged } as typeof prev;
            });
          }}
          onSubmitRecommend={() => void runRecommendation()}
          onFillAndSubmit={(patch: RecommendFormPatch) => {
            const nextForm = applyAssistantFormPatch(formData as unknown as Record<string, unknown>, patch);
            const typedForm = nextForm as unknown as RecommendationRequest;
            setFormData(typedForm);
            void runRecommendation(typedForm);
          }}
        />
      </React.Suspense>
    </>
  );
}
