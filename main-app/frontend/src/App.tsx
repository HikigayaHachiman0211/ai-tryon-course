import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Clock } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { analyzeStyleLab, buildImageURL, getCatalogProducts, getHistoryDetail, getRecommend } from './api';
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
  type ViewMode,
  type CatalogMode,
  type CatalogPlatform,
  type SampleModel,
  getInitialView,
} from './constants/formOptions';
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
  const [visibleRecommendationCount, setVisibleRecommendationCount] = useState(3);

  const [catalogMode, setCatalogMode] = useState<CatalogMode>('gender');
  const [catalogPlatform, setCatalogPlatform] = useState<CatalogPlatform>('all');
  const [catalogQuery, setCatalogQuery] = useState('');
  const [catalogItems, setCatalogItems] = useState<ProductCatalogItem[]>([]);
  const [catalogTotal, setCatalogTotal] = useState(0);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [catalogGenderFallback, setCatalogGenderFallback] = useState(false);

  const [selectedProduct, setSelectedProduct] = useState<ProductCatalogItem | null>(null);
  const [styleLabLoading, setStyleLabLoading] = useState(false);
  const [styleLabResult, setStyleLabResult] = useState<StyleLabAnalysisResponse | null>(null);
  const [styleLabError, setStyleLabError] = useState<ErrorResponse['error'] | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [sampleModelGender, setSampleModelGender] = useState<'male' | 'female'>('male');
  const [selectedSampleModel, setSelectedSampleModel] = useState<string | null>(null);

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

  const profileReady = Boolean(formData.color_preference && formData.gender);
  const canLoadMoreCatalog = catalogItems.length < catalogTotal;
  const tryOnBaseUrl = getTryOnBaseUrl();
  const adminUrl = getAdminUrl();
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
        setTryOnMessage('已从试穿工作台返回主站推荐页。');
      }
      if (type === 'DOWN_JACKET_TRYON_SWITCH_REQUEST') {
        navigateToView('recommend');
        setTryOnMessage('试穿工作台请求切回主站，方便你更换其他羽绒服。');
      }
    };

    window.addEventListener('message', handler);
    return () => {
      window.removeEventListener('message', handler);
    };
  }, [navigateToView]);

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
      const blob = await response.blob();
      const file = new File([blob], model.filename, { type: blob.type });
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
      setError({ code: 'VAL-001', message: '请先填写颜色偏好', request_id: 'local', details: null });
      return;
    }
    if (!effectiveForm.gender) {
      setError({ code: 'VAL-002', message: '请选择性别', request_id: 'local', details: null });
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);
    setTryOnMessage(null);

    try {
      const response = await getRecommend(buildRequestPayload(override));
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
      setCatalogError(toApiError(err, '商品列表加载失败').message);
    } finally {
      setCatalogLoading(false);
    }
  }, [catalogMode, catalogPlatform, catalogQuery, formData.gender, formData.price_max, formData.price_min]);

  useEffect(() => {
    if (view !== 'style-lab') {
      return undefined;
    }

    const timer = window.setTimeout(() => {
      void loadCatalog({ reset: true, offset: 0 });
    }, 140);

    return () => {
      window.clearTimeout(timer);
    };
  }, [view, loadCatalog]);

  const analyzeCurrentSelection = async () => {
    if (!selectedProduct) {
      setStyleLabError({ code: 'LAB-SELECT', message: '请先在中间选择一件羽绒服', request_id: 'local', details: null });
      return;
    }
    if (!profileReady) {
      setStyleLabError({ code: 'LAB-PROFILE', message: '请先补全颜色偏好和性别信息', request_id: 'local', details: null });
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
      setStyleLabError(toApiError(err, '搭配分析失败，请稍后再试'));
    } finally {
      setStyleLabLoading(false);
    }
  };

  const buildTryOnPayload = (item: RecommendationResponse['items'][number]): TryOnBridgePayload => ({
    source: 'down-jacket-recommendation',
    garmentImageUrl: buildImageURL(item.image_url),
    productTitle: item.title,
    productId: String(item.id),
    productPrice: item.price,
    productUrl: item.product_url || '',
    styleType: item.style_type,
    colorFamily: item.color_family,
    sizeHint: formData.size || result?.inference.resolved_size || '',
    recommendationReason: item.reason,
    score: item.total_score,
    sceneHint: formData.style_preference || result?.inference.resolved_style || '',
    fitNote: item.size_notes || '',
    returnUrl: window.location.href,
    // Pass the already-uploaded photo's public GCS URL via the URL channel so the
    // workbench imports it deterministically (postMessage data URL stays as backup).
    userImageUrl: result?.user_photo_url || '',
  });

  const openTryOnFromStyleLab = async (product: ProductCatalogItem) => {
    if (!tryOnBaseUrl) {
      setTryOnMessage('尚未配置试穿工作台地址，请设置 VITE_TRYON_BASE_URL 后重试。');
      return;
    }
    const tryOnOrigin = getTryOnOrigin();
    const payload: TryOnBridgePayload = {
      source: 'down-jacket-recommendation',
      garmentImageUrl: buildImageURL(product.image_url),
      productTitle: product.title,
      productId: String(product.id),
      productPrice: product.price,
      productUrl: product.product_url || '',
      styleType: product.style_type,
      colorFamily: product.color_family,
      returnUrl: window.location.href,
    };
    const tryonWindow = openTryOnWindow(payload);
    if (!tryonWindow) {
      setTryOnMessage('浏览器拦截了试穿工作台弹窗，请允许新窗口后重试。');
      return;
    }
    if (photoFile) {
      try {
        const userImageDataUrl = await fileToDataUrl(photoFile);
        postTryOnPayloadWithAck(tryonWindow, { ...payload, userImageDataUrl }, tryOnOrigin);
        setTryOnMessage(
          tryOnOrigin
            ? `已为"${product.title}"打开试穿工作台，并同步你的全身照与商品图。`
            : `已为"${product.title}"打开试穿工作台。商品图已同步，你的全身照未能自动同步，请在试穿站补传。`,
        );
        return;
      } catch {
        postTryOnPayloadWithAck(tryonWindow, payload, tryOnOrigin);
        setTryOnMessage(`已为"${product.title}"打开试穿工作台。商品图已同步，你的全身照未能自动读取，请在试穿站补传。`);
        return;
      }
    }
    postTryOnPayloadWithAck(tryonWindow, payload, tryOnOrigin);
    setTryOnMessage(`已为"${product.title}"打开试穿工作台，请在试穿站上传你的全身照后继续。`);
  };

  const openTryOnWorkbench = async (item: RecommendationResponse['items'][number]) => {
    if (!tryOnBaseUrl) {
      setTryOnMessage('尚未配置试穿工作台地址，请设置 VITE_TRYON_BASE_URL 后重试。');
      return;
    }
    const tryOnOrigin = getTryOnOrigin();
    const payload = buildTryOnPayload(item);
    const tryonWindow = openTryOnWindow(payload);
    if (!tryonWindow) {
      setTryOnMessage('浏览器拦截了试穿工作台弹窗，请允许新窗口后重试。');
      return;
    }

    if (photoFile) {
      try {
        const userImageDataUrl = await fileToDataUrl(photoFile);
        postTryOnPayloadWithAck(tryonWindow, { ...payload, userImageDataUrl }, tryOnOrigin);
        setTryOnMessage(
          tryOnOrigin
            ? `已为”${item.title}”打开新的试穿工作台，并同步你的全身照与商品图。`
            : `已为”${item.title}”打开新的试穿工作台。商品图已同步，你的全身照未能自动同步，请在试穿站补传。`,
        );
        return;
      } catch {
        postTryOnPayloadWithAck(tryonWindow, payload, tryOnOrigin);
        setTryOnMessage(`已为”${item.title}”打开新的试穿工作台。商品图已同步，你的全身照未能自动读取，请在试穿站补传。`);
        return;
      }
    }

    postTryOnPayloadWithAck(tryonWindow, payload, tryOnOrigin);
    setTryOnMessage(`已为”${item.title}”打开新的试穿工作台，请在试穿站上传你的全身照后继续。`);
  };

  return (
    <>
      <div className="apple-nav">
        <div className="apple-nav-inner">
          <button className="apple-brand" onClick={() => navigateToView('recommend')}>AI 羽绒服推荐平台</button>
          <div className="apple-nav-links">
            {tryOnBaseUrl ? (
              <a className="nav-chip nav-chip-tryon" href={tryOnBaseUrl} target="_blank" rel="noopener noreferrer">羽绒服试穿</a>
            ) : (
              <span className="nav-chip nav-chip-tryon" aria-disabled="true" title="请配置 VITE_TRYON_BASE_URL">羽绒服试穿</span>
            )}
            <button className={`nav-chip ${view === 'recommend' ? 'nav-chip-active' : ''}`} onClick={() => navigateToView('recommend')}>智能推荐</button>
            <button className={`nav-chip ${view === 'style-lab' ? 'nav-chip-active' : ''}`} onClick={() => navigateToView('style-lab')}>自己搭配</button>
            <button className="nav-history-btn" onClick={() => setHistoryOpen(true)}>
              <Clock size={14} />
              历史
            </button>
            {adminUrl ? (
              <a className="nav-chip nav-chip-admin" href={adminUrl} target="_blank" rel="noopener noreferrer">站长后台</a>
            ) : (
              <span className="nav-chip nav-chip-admin" aria-disabled="true" title="请配置 VITE_ADMIN_BASE_URL">站长后台</span>
            )}
          </div>
        </div>
      </div>

      <div className="app-frame">
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
