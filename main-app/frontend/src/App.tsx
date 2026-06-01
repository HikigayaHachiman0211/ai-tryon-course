import React, { useCallback, useEffect, useRef, useState } from 'react';
import { isAxiosError } from 'axios';
import { ArrowLeft, ChevronRight, Clock, Loader2, Search, SlidersHorizontal, Sparkles, TriangleAlert, UploadCloud } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { analyzeStyleLab, buildImageURL, getCatalogProducts, getHistoryDetail, getRecommend } from './api';
import type {
  ErrorResponse,
  ProductCatalogItem,
  RecommendationRequest,
  RecommendationResponse,
  StyleLabAnalysisResponse,
} from './types';
import { RadarChart } from './components/RadarChart';
import type { HistoryEntry } from './types';
import './index.css';

const DebugDrawer = React.lazy(async () => ({ default: (await import('./components/DebugDrawer')).DebugDrawer }));
const HistoryDrawer = React.lazy(async () => ({ default: (await import('./components/HistoryDrawer')).HistoryDrawer }));

const MBTI_OPTIONS = [
  'INTJ', 'INTP', 'ENTJ', 'ENTP',
  'INFJ', 'INFP', 'ENFJ', 'ENFP',
  'ISTJ', 'ISFJ', 'ESTJ', 'ESFJ',
  'ISTP', 'ISFP', 'ESTP', 'ESFP',
];

const GENDER_OPTIONS = [
  { value: 'female', label: '女' },
  { value: 'male', label: '男' },
];

const BRAND_SUGGESTIONS = ['阿迪达斯', '骆驼', '波司登', '李宁'];

const SAMPLE_MODELS = [
  { id: 'male-donk', name: 'Donk', gender: 'male' as const, filename: 'Donk.webp' },
  { id: 'male-monesy', name: 'Monesy', gender: 'male' as const, filename: 'Monesy.webp' },
  { id: 'male-niko', name: 'Niko', gender: 'male' as const, filename: 'Niko.webp' },
  { id: 'male-leave7', name: 'Leave7', gender: 'male' as const, filename: 'OA-Leave7.jpg' },
  { id: 'male-zywoo', name: 'ZywOo', gender: 'male' as const, filename: 'ZywOo.webp' },
  { id: 'female-liyuu1', name: 'Liyuu 1', gender: 'female' as const, filename: 'Liyuu_1.jpg' },
  { id: 'female-liyuu2', name: 'Liyuu 2', gender: 'female' as const, filename: 'Liyuu_2.jpg' },
  { id: 'female-liyuu3', name: 'Liyuu 3', gender: 'female' as const, filename: 'Liyuu_3.jpg' },
];

const GENDER_LABELS: Record<string, string> = {
  female: '女性',
  male: '男性',
};

const DEFAULT_TRYON_LOCAL_URL = 'http://127.0.0.1:8080/static/index.html';
const DEFAULT_TRYON_CLOUD_URL = '';
const TRYON_BRIDGE_TYPE = 'DOWN_JACKET_TRYON_INIT';

const DEFAULT_ADMIN_LOCAL_URL = 'http://127.0.0.1:8081';
const DEFAULT_ADMIN_CLOUD_URL = '';
const getAdminUrl = () => import.meta.env.VITE_ADMIN_BASE_URL || (import.meta.env.DEV ? DEFAULT_ADMIN_LOCAL_URL : DEFAULT_ADMIN_CLOUD_URL);

type ViewMode = 'recommend' | 'style-lab';
type CatalogMode = 'gender' | 'all';
type CatalogPlatform = 'all' | 'jd' | 'taobao';

const getInitialView = (): ViewMode => {
  if (typeof window === 'undefined') {
    return 'recommend';
  }

  return window.location.hash === '#style-lab' ? 'style-lab' : 'recommend';
};

const getTryOnBaseUrl = () => import.meta.env.VITE_TRYON_BASE_URL || (import.meta.env.DEV ? DEFAULT_TRYON_LOCAL_URL : DEFAULT_TRYON_CLOUD_URL);

const getTryOnOrigin = () => {
  try {
    return new URL(getTryOnBaseUrl()).origin;
  } catch {
    return '';
  }
};

const postTryOnPayload = (tryonWindow: Window, payload: Record<string, unknown>, origin: string) => {
  const targetOrigin = origin || '*';
  const message = { type: TRYON_BRIDGE_TYPE, payload };
  const attemptDelays = [250, 700, 1400, 2400];
  attemptDelays.forEach((delay) => {
    window.setTimeout(() => {
      try {
        if (!tryonWindow.closed) {
          tryonWindow.postMessage(message, targetOrigin);
        }
      } catch {
        // Ignore cross-window delivery failures and keep the opened workbench usable.
      }
    }, delay);
  });
};

const fileToDataUrl = (file: File) => new Promise<string>((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result : '');
  reader.onerror = () => reject(new Error('用户全身照读取失败'));
  reader.readAsDataURL(file);
});

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
  const displayedRecommendationItems = result ? result.items.slice(0, visibleRecommendationCount) : [];
  const canLoadMoreRecommendations = Boolean(result && visibleRecommendationCount < result.items.length);

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

  const selectSampleModel = async (model: typeof SAMPLE_MODELS[number]) => {
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

  const buildRequestPayload = (): RecommendationRequest => ({
    ...formData,
    photo: photoFile,
  });

  const toApiError = (err: unknown, fallbackMessage = '网络请求失败，请检查后端服务是否已启动'): ErrorResponse['error'] => {
    if (isAxiosError<ErrorResponse>(err) && err.response?.data?.error) {
      return err.response.data.error;
    }
    if (err instanceof Error) {
      return {
        code: 'SYS-XXX',
        message: fallbackMessage,
        request_id: 'unknown',
        details: err.message,
      };
    }
    return {
      code: 'SYS-XXX',
      message: fallbackMessage,
      request_id: 'unknown',
      details: err,
    };
  };

  const runRecommendation = async () => {
    if (!formData.color_preference) {
      setError({ code: 'VAL-001', message: '请先填写颜色偏好', request_id: 'local', details: null });
      return;
    }
    if (!formData.gender) {
      setError({ code: 'VAL-002', message: '请选择性别', request_id: 'local', details: null });
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);
    setTryOnMessage(null);

    try {
      const response = await getRecommend(buildRequestPayload());
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

  const buildTryOnPayload = (item: RecommendationResponse['items'][number], userImageDataUrl?: string) => ({
    source: 'down-jacket-recommendation',
    userImageDataUrl: userImageDataUrl || '',
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
  });

  const openTryOnFromStyleLab = async (product: ProductCatalogItem) => {
    const tryOnBaseUrl = getTryOnBaseUrl();
    const tryOnOrigin = getTryOnOrigin();
    const queryPayload: Record<string, unknown> = {
      source: 'down-jacket-recommendation',
      userImageDataUrl: '',
      garmentImageUrl: buildImageURL(product.image_url),
      productTitle: product.title,
      productId: String(product.id),
      productPrice: product.price,
      productUrl: product.product_url || '',
      styleType: product.style_type,
      colorFamily: product.color_family,
      returnUrl: window.location.href,
    };
    const tryOnUrl = new URL(tryOnBaseUrl);
    tryOnUrl.searchParams.set('tryonPayload', JSON.stringify(queryPayload));
    const tryonWindow = window.open(tryOnUrl.toString(), '_blank');
    if (!tryonWindow) {
      setTryOnMessage('浏览器拦截了试穿工作台弹窗，请允许新窗口后重试。');
      return;
    }
    if (photoFile) {
      try {
        const userImageDataUrl = await fileToDataUrl(photoFile);
        postTryOnPayload(tryonWindow, { ...queryPayload, userImageDataUrl }, tryOnOrigin);
        setTryOnMessage(`已为"${product.title}"打开试穿工作台，并同步你的全身照与商品图。`);
        return;
      } catch {
        postTryOnPayload(tryonWindow, queryPayload, tryOnOrigin);
        setTryOnMessage(`已为"${product.title}"打开试穿工作台。商品图已同步，你的全身照未能自动读取，请在试穿站补传。`);
        return;
      }
    }
    postTryOnPayload(tryonWindow, queryPayload, tryOnOrigin);
    setTryOnMessage(`已为"${product.title}"打开试穿工作台，请在试穿站上传你的全身照后继续。`);
  };

  const openTryOnWorkbench = async (item: RecommendationResponse['items'][number]) => {
    const tryOnBaseUrl = getTryOnBaseUrl();
    const tryOnOrigin = getTryOnOrigin();
    const queryPayload = buildTryOnPayload(item);
    const tryOnUrl = new URL(tryOnBaseUrl);
    tryOnUrl.searchParams.set('tryonPayload', JSON.stringify(queryPayload));

    const tryonWindow = window.open(tryOnUrl.toString(), '_blank');
    if (!tryonWindow) {
      setTryOnMessage('浏览器拦截了试穿工作台弹窗，请允许新窗口后重试。');
      return;
    }

    if (photoFile) {
      try {
        const userImageDataUrl = await fileToDataUrl(photoFile);
        postTryOnPayload(tryonWindow, buildTryOnPayload(item, userImageDataUrl), tryOnOrigin);
        setTryOnMessage(`已为“${item.title}”打开新的试穿工作台，并同步你的全身照与商品图。`);
        return;
      } catch {
        postTryOnPayload(tryonWindow, queryPayload, tryOnOrigin);
        setTryOnMessage(`已为“${item.title}”打开新的试穿工作台。商品图已同步，你的全身照未能自动读取，请在试穿站补传。`);
        return;
      }
    }

    postTryOnPayload(tryonWindow, queryPayload, tryOnOrigin);
    setTryOnMessage(`已为“${item.title}”打开新的试穿工作台，请在试穿站上传你的全身照后继续。`);
  };

  const renderErrorBanner = (bannerError: ErrorResponse['error']) => (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)', padding: 20, borderRadius: 12 }}
    >
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        <TriangleAlert color="#EF4444" size={24} />
        <div>
          <h4 style={{ color: '#F8FAFC', margin: 0, fontSize: 16 }}>{bannerError.message}</h4>
          <p style={{ color: '#FCA5A5', fontSize: 13, margin: '4px 0 0 0' }}>错误码：{bannerError.code}</p>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 11, margin: '8px 0 0 0', fontFamily: 'monospace' }}>请求 ID：{bannerError.request_id}</p>
        </div>
      </div>
    </motion.div>
  );

  const renderScoreBreakdown = (scoreBreakdown: Record<string, number>) => (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
      {Object.entries(scoreBreakdown).map(([label, score]) => (
        <span
          key={label}
          style={{
            fontSize: 11,
            background: 'rgba(56, 189, 248, 0.08)',
            border: '1px solid rgba(56, 189, 248, 0.18)',
            padding: '4px 8px',
            borderRadius: 999,
            color: 'var(--text-secondary)',
          }}
        >
          {label} {score}
        </span>
      ))}
    </div>
  );

  const renderProfilePanel = ({
    eyebrow,
    title,
    description,
    footer,
  }: {
    eyebrow: string;
    title: React.ReactNode;
    description: string;
    footer: React.ReactNode;
  }) => (
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
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input type="file" ref={fileInputRef} hidden accept="image/*" onChange={handlePhotoUpload} />
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
              onClick={() => setSampleModelGender('male')}
              style={{ padding: '5px 14px', borderRadius: 980, border: sampleModelGender === 'male' ? '1px solid #0071e3' : '1px solid var(--border-subtle)', background: sampleModelGender === 'male' ? '#0071e3' : 'transparent', color: sampleModelGender === 'male' ? '#fff' : 'var(--text-secondary)', fontSize: 13, cursor: 'pointer', transition: 'all 0.2s ease' }}
            >
              男性模特
            </button>
            <button
              type="button"
              onClick={() => setSampleModelGender('female')}
              style={{ padding: '5px 14px', borderRadius: 980, border: sampleModelGender === 'female' ? '1px solid #0071e3' : '1px solid var(--border-subtle)', background: sampleModelGender === 'female' ? '#0071e3' : 'transparent', color: sampleModelGender === 'female' ? '#fff' : 'var(--text-secondary)', fontSize: 13, cursor: 'pointer', transition: 'all 0.2s ease' }}
            >
              女性模特
            </button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(72px, 1fr))', gap: 10 }}>
            {SAMPLE_MODELS.filter(m => m.gender === sampleModelGender).map(model => (
              <div
                key={model.id}
                onClick={() => void selectSampleModel(model)}
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
            onChange={handleInputChange}
          />
          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            {['黑色', '白色', '藏青'].map((color) => (
              <div
                key={color}
                onClick={() => setFormData((previous) => ({ ...previous, color_preference: color }))}
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
            onChange={handleInputChange}
          />
          <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
            {BRAND_SUGGESTIONS.map((brand) => (
              <div
                key={brand}
                onClick={() => setFormData((previous) => ({ ...previous, brand_preference: brand }))}
                style={{ fontSize: 11, background: 'rgba(255,255,255,0.05)', padding: '4px 8px', borderRadius: 4, cursor: 'pointer' }}
              >
                {brand}
              </div>
            ))}
          </div>
        </div>

        <div className="bento-item">
          <label className="label">性别 *</label>
          <select name="gender" className="modern-input" value={formData.gender || ''} onChange={handleInputChange} style={{ marginBottom: 16 }}>
            <option value="">请选择</option>
            {GENDER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>

          <label className="label">MBTI 人格</label>
          <select name="mbti" className="modern-input" value={formData.mbti || ''} onChange={handleInputChange}>
            <option value="">请选择（选填）</option>
            {MBTI_OPTIONS.map((mbti) => (
              <option key={mbti} value={mbti}>{mbti}</option>
            ))}
          </select>
        </div>

        <div className="bento-item bento-col-span-2" style={{ display: 'flex', gap: 16 }}>
          <div style={{ flex: 1 }}>
            <label className="label">最低价格（¥）</label>
            <input type="number" name="price_min" className="modern-input" placeholder="0" value={formData.price_min ?? ''} onChange={handleInputChange} />
          </div>
          <div style={{ flex: 1 }}>
            <label className="label">最高价格（¥）</label>
            <input type="number" name="price_max" className="modern-input" placeholder="不限" value={formData.price_max ?? ''} onChange={handleInputChange} />
          </div>
        </div>

        <div className="bento-item bento-col-span-2">
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <label className="label">尺码</label>
            <span style={{ fontSize: 11, color: 'var(--accent-blue-text)' }}>✨ AI 可结合照片辅助识别</span>
          </div>
          <input type="text" name="size" className="modern-input" placeholder="例如 M、L，或留空" value={formData.size || ''} onChange={handleInputChange} style={{ marginBottom: 16 }} />

          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <label className="label">款式偏好</label>
            <span style={{ fontSize: 11, color: 'var(--accent-blue-text)' }}>✨ AI 可智能补全</span>
          </div>
          <input type="text" name="style_preference" className="modern-input" placeholder="例如 极简通勤、工装风" value={formData.style_preference || ''} onChange={handleInputChange} />
        </div>

        <div className="bento-item bento-col-span-2" style={{ background: 'rgba(56, 189, 248, 0.02)', borderColor: 'rgba(56, 189, 248, 0.1)' }}>
          <label className="label" style={{ color: 'var(--accent-blue-text)', marginBottom: 8 }}>AI 引擎选择</label>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            {([['auto', '自动'], ['gemini', 'Gemini'], ['deepseek', 'Deepseek']] as const).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setFormData((prev) => ({ ...prev, ai_provider: value }))}
                style={{
                  padding: '5px 14px',
                  borderRadius: 980,
                  border: (formData.ai_provider || 'auto') === value ? '1px solid #0071e3' : '1px solid var(--border-subtle)',
                  background: (formData.ai_provider || 'auto') === value ? '#0071e3' : 'transparent',
                  color: (formData.ai_provider || 'auto') === value ? '#fff' : 'var(--text-secondary)',
                  fontSize: 13,
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <p style={{ fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 12 }}>
            {(formData.ai_provider || 'auto') === 'auto' && '自动模式：优先 Gemini（图片+文本），不可用时降级 Deepseek（纯文本），最后规则推断。'}
            {formData.ai_provider === 'gemini' && 'Gemini 支持图片分析，需上传全身照效果最佳。'}
            {formData.ai_provider === 'deepseek' && 'Deepseek 为纯文本推断，不分析图片，适合无照片时使用。'}
          </p>

          {(formData.ai_provider || 'auto') !== 'deepseek' && (
            <div style={{ marginBottom: 12 }}>
              <label className="label">Gemini API Key（选填）</label>
              <input type="password" name="gemini_api_key" className="modern-input" placeholder="请输入 Gemini AI Studio 密钥..." value={formData.gemini_api_key || ''} onChange={handleInputChange} />
            </div>
          )}

          {(formData.ai_provider || 'auto') !== 'gemini' && (
            <div style={{ marginBottom: 12 }}>
              <label className="label">Deepseek API Key（选填）</label>
              <input type="password" name="deepseek_api_key" className="modern-input" placeholder="请输入 Deepseek API 密钥..." value={formData.deepseek_api_key || ''} onChange={handleInputChange} />
            </div>
          )}

          {(formData.ai_provider || 'auto') !== 'gemini' && (
            <div>
              <label className="label">Deepseek 模型</label>
              <select name="deepseek_model" className="modern-input" value={formData.deepseek_model || 'deepseek-v4-flash'} onChange={handleInputChange}>
                <option value="deepseek-v4-flash">deepseek-v4-flash（默认，快速）</option>
                <option value="deepseek-v4-pro">deepseek-v4-pro（高质量）</option>
                <option value="deepseek-chat">deepseek-chat（通用对话）</option>
                <option value="deepseek-reasoner">deepseek-reasoner（深度推理）</option>
              </select>
            </div>
          )}
        </div>

        <div className="bento-col-span-2" style={{ marginTop: 8 }}>{footer}</div>
      </div>
    </section>
  );

  const renderRecommendationView = () => (
    <div className="app-container">
      {renderProfilePanel({
        eyebrow: 'Personalized Winter Style',
        title: <>AI 羽绒服推荐</>,
        description: '上传全身照并填写偏好，让 AI 为你精准推荐合适的冬季羽绒服搭配。',
        footer: (
          <button className="btn-primary" style={{ width: '100%', height: 50 }} onClick={runRecommendation} disabled={loading || !profileReady}>
            {loading ? <Loader2 className="animate-spin" /> : <Sparkles size={18} />}
            {loading ? '推荐生成中...' : '开始生成 AI 推荐'}
          </button>
        ),
      })}

      <section className="results-column" style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button className="btn-glowing" style={{ width: 'auto' }} onClick={() => navigateToView('style-lab')}>
            我来自己搭配 <ChevronRight size={16} />
          </button>
        </div>

        <AnimatePresence mode="wait">
          {error && renderErrorBanner(error)}

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
                {displayedRecommendationItems.map((item, index) => (
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
                      {renderScoreBreakdown(item.score_breakdown)}

                      {item.size_notes && (
                        <div style={{ fontSize: 12, background: 'rgba(245, 158, 11, 0.1)', color: 'var(--accent-warm)', padding: '8px 12px', borderRadius: 6, marginBottom: 12 }}>
                          📏 尺码提示：{item.size_notes}
                        </div>
                      )}

                      <div style={{ marginTop: 'auto', alignSelf: 'flex-start', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                        <button className="btn-glowing" style={{ width: 'auto' }} onClick={() => {
                          void openTryOnWorkbench(item);
                        }}>
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
                        <button className="btn-secondary" onClick={() => navigateToView('style-lab')}>我来自己搭配</button>
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
                      已展示 {displayedRecommendationItems.length} / {result.items.length} 条推荐，按分数从高到低排序
                    </div>
                    {canLoadMoreRecommendations && (
                      <button
                        className="btn-secondary"
                        style={{ minWidth: 220 }}
                        onClick={() => setVisibleRecommendationCount((previous) => previous + 6)}
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

  const renderCatalogCard = (product: ProductCatalogItem) => {
    const selected = selectedProduct?.id === product.id;
    return (
      <button
        key={product.id}
        className={`catalog-card ${selected ? 'catalog-card-active' : ''}`}
        onClick={() => {
          setSelectedProduct(product);
          setStyleLabResult(null);
          setStyleLabError(null);
        }}
        type="button"
      >
        <div style={{ width: 84, height: 108, flexShrink: 0, borderRadius: 10, overflow: 'hidden', background: '#08090c' }}>
          <img src={buildImageURL(product.image_url)} alt={product.title} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        </div>

        <div style={{ flex: 1, minWidth: 0, textAlign: 'left' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
            <h4 style={{ fontSize: 14, lineHeight: 1.5, color: '#F8FAFC' }}>{product.title}</h4>
            <span style={{ fontSize: 11, color: selected ? 'var(--accent-blue-text)' : 'var(--text-tertiary)', flexShrink: 0 }}>{product.gender_label}</span>
          </div>
          {product.brand && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-tertiary)' }}>品牌：{product.brand}</div>}
          {product.platform && <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-tertiary)' }}>平台：{product.platform}</div>}
          <div style={{ marginTop: 8, fontSize: 20, fontWeight: 600, color: 'var(--accent-blue-text)' }}>¥{product.price}</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
            {product.brand && <span className="catalog-tag">{product.brand}</span>}
            {product.platform && <span className="catalog-tag">{product.platform}</span>}
            <span className="catalog-tag">{product.color_family}</span>
            <span className="catalog-tag">{product.style_type}</span>
          </div>
        </div>
      </button>
    );
  };

  const renderStyleLabView = () => (
    <div className="style-lab-page">
      <div className="glass-panel style-lab-hero" style={{ padding: 24, marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 24, alignItems: 'center', flexWrap: 'wrap' }}>
          <div>
            <div style={{ display: 'inline-flex', gap: 8, alignItems: 'center', fontSize: 12, color: 'var(--accent-blue-text)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              <Sparkles size={14} /> 自定义搭配实验室
            </div>
            <h1 style={{ fontSize: 34, fontWeight: 600, letterSpacing: '-0.02em', marginBottom: 8 }}>我来自己搭配</h1>
            <p style={{ color: 'var(--text-secondary)', maxWidth: 720 }}>左侧保留你的全身图与偏好信息，中间从数据库里挑选任意羽绒服，右侧查看 AI 对这套搭配的多维评分、穿搭建议与 MBTI 风格分析。</p>
          </div>

          <button className="btn-secondary" onClick={() => navigateToView('recommend')} style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <ArrowLeft size={16} /> 返回智能推荐
          </button>
        </div>
      </div>

      <div className="style-lab-shell">
        <div>
          {renderProfilePanel({
            eyebrow: 'Profile & Inputs',
            title: <>用户画像 <span className="text-gradient">Profile</span></>,
            description: '这里继承主页面的用户图与偏好信息。你可以继续更换照片或微调参数，右侧分析会基于最新资料重新计算。',
            footer: (
              <div className="glass-panel" style={{ padding: 18 }}>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>使用方式</div>
                <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                  先在中间选择一件羽绒服，再点击右侧的“分析这套搭配”。如果你修改了颜色、MBTI、尺码或照片，分析结果会自动失效，需要重新分析一次。
                </p>
              </div>
            ),
          })}
        </div>

        <div className="glass-panel style-lab-column" style={{ padding: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', marginBottom: 16 }}>
            <div>
              <h3 style={{ fontSize: 18, fontWeight: 600, marginBottom: 6 }}>羽绒服库</h3>
              <p style={{ fontSize: 12, color: 'var(--text-secondary)' }}>搜索并选择数据库中的羽绒服进行自定义搭配。</p>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>已加载 {catalogItems.length} / {catalogTotal}</div>
          </div>

          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <button className={catalogMode === 'gender' ? 'btn-secondary' : 'catalog-mode-button'} onClick={() => setCatalogMode('gender')}>更适合你</button>
            <button className={catalogMode === 'all' ? 'btn-secondary' : 'catalog-mode-button'} onClick={() => setCatalogMode('all')}>全部成人款</button>
            <button className={catalogPlatform === 'all' ? 'btn-secondary' : 'catalog-mode-button'} onClick={() => setCatalogPlatform('all')}>全部库</button>
            <button className={catalogPlatform === 'jd' ? 'btn-secondary' : 'catalog-mode-button'} onClick={() => setCatalogPlatform('jd')}>京东库</button>
            <button className={catalogPlatform === 'taobao' ? 'btn-secondary' : 'catalog-mode-button'} onClick={() => setCatalogPlatform('taobao')}>淘宝库</button>
          </div>

          <div style={{ position: 'relative', marginBottom: 16 }}>
            <Search size={16} style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)' }} />
            <input
              className="modern-input"
              value={catalogQuery}
              onChange={(event) => setCatalogQuery(event.target.value)}
              placeholder="搜索品牌、款式、颜色或功能，例如：白色 户外 三防"
              style={{ paddingLeft: 40 }}
            />
          </div>

          {catalogGenderFallback && (
            <div style={{ marginBottom: 12, fontSize: 12, color: 'var(--accent-warm)' }}>
              当前筛选条件下没有更多符合性别偏好的商品，已显示全部成人款供你手动挑选。
            </div>
          )}

          {catalogError && <div style={{ marginBottom: 16 }}>{renderErrorBanner({ code: 'LAB-CATALOG', message: catalogError, request_id: 'local', details: null })}</div>}

          <div className="catalog-list">
            {catalogItems.map(renderCatalogCard)}
            {!catalogLoading && catalogItems.length === 0 && !catalogError && (
              <div className="catalog-empty-state">
                <SlidersHorizontal size={32} style={{ opacity: 0.5, marginBottom: 12 }} />
                <div>当前条件下没有可浏览的羽绒服。</div>
              </div>
            )}
          </div>

          {catalogLoading && (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '18px 0', color: 'var(--text-secondary)' }}>
              <Loader2 className="animate-spin" />
            </div>
          )}

          {!catalogLoading && canLoadMoreCatalog && (
            <button className="btn-secondary" style={{ width: '100%', marginTop: 16 }} onClick={() => void loadCatalog({ reset: false, offset: catalogItems.length })}>
              加载更多羽绒服
            </button>
          )}
        </div>

        <div className="glass-panel style-lab-column style-lab-analysis" style={{ padding: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 18 }}>
            <div>
              <h3 style={{ fontSize: 18, fontWeight: 600, marginBottom: 6 }}>AI 搭配分析</h3>
              <p style={{ fontSize: 12, color: 'var(--text-secondary)' }}>为你分析当前自选单品与个人条件的匹配度。</p>
            </div>
            {selectedProduct && <span style={{ fontSize: 12, color: 'var(--accent-blue-text)' }}>已选择 1 件单品</span>}
          </div>

          {styleLabError && <div style={{ marginBottom: 16 }}>{renderErrorBanner(styleLabError)}</div>}

          {!selectedProduct && (
            <div className="catalog-empty-state" style={{ minHeight: 360 }}>
              <Sparkles size={32} style={{ opacity: 0.5, marginBottom: 12 }} />
              <div>先从中间挑一件羽绒服，再开始分析你的自定义搭配。</div>
            </div>
          )}

          {selectedProduct && (
            <>
              <div className="style-lab-selected-card">
                <div style={{ width: 120, height: 150, flexShrink: 0, borderRadius: 12, overflow: 'hidden', background: '#06070a' }}>
                  <img src={buildImageURL(selectedProduct.image_url)} alt={selectedProduct.title} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
                    <h4 style={{ fontSize: 18, lineHeight: 1.5, color: '#F8FAFC' }}>{selectedProduct.title}</h4>
                    <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{selectedProduct.gender_label}</span>
                  </div>
                  {selectedProduct.brand && <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-tertiary)' }}>品牌：{selectedProduct.brand}</div>}
                  {selectedProduct.platform && <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-tertiary)' }}>平台：{selectedProduct.platform}</div>}
                  <div style={{ marginTop: 10, fontSize: 24, fontWeight: 600, color: 'var(--accent-blue-text)' }}>¥{selectedProduct.price}</div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 12 }}>
                    {selectedProduct.brand && <span className="catalog-tag">{selectedProduct.brand}</span>}
                    {selectedProduct.platform && <span className="catalog-tag">{selectedProduct.platform}</span>}
                    <span className="catalog-tag">{selectedProduct.color_family}</span>
                    <span className="catalog-tag">{selectedProduct.style_type}</span>
                    {selectedProduct.function_features.slice(0, 2).map((feature) => <span key={feature} className="catalog-tag">{feature}</span>)}
                  </div>
                </div>
              </div>

              <button className="btn-primary" style={{ width: '100%', height: 48, marginTop: 18 }} onClick={analyzeCurrentSelection} disabled={styleLabLoading || !profileReady}>
                {styleLabLoading ? <Loader2 className="animate-spin" /> : <Sparkles size={18} />}
                {styleLabLoading ? '分析中...' : '分析这套搭配'}
              </button>

              <button
                className="btn-glowing"
                style={{ width: '100%', height: 44, marginTop: 10, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8, background: 'linear-gradient(135deg, rgba(99,102,241,0.25), rgba(168,85,247,0.25))', border: '1px solid rgba(139,92,246,0.4)', color: '#c4b5fd', fontWeight: 500, fontSize: 15 }}
                onClick={() => void openTryOnFromStyleLab(selectedProduct)}
              >
                ✨ 尝试试穿 <ChevronRight size={16} />
              </button>

              {!styleLabLoading && !styleLabResult && !styleLabError && (
                <div style={{ marginTop: 16, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                  当前已保留你的全身图和资料。点击上方按钮后，右侧会给出多维评分、穿搭建议和基于 MBTI 的风格分析。
                </div>
              )}

              {styleLabResult && (
                <div style={{ marginTop: 20, display: 'flex', flexDirection: 'column', gap: 18 }}>
                  <div className="style-lab-score-strip">
                    <div>
                      <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>综合得分</div>
                      <div style={{ fontSize: 38, fontWeight: 700, color: '#F8FAFC', lineHeight: 1 }}>{styleLabResult.analysis.total_score.toFixed(1)}</div>
                    </div>
                    <div style={{ display: 'flex', gap: 18 }}>
                      <div><div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>推荐尺码</div><div style={{ fontSize: 18, fontWeight: 600 }}>{styleLabResult.inference.resolved_size}</div></div>
                      <div><div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>建议款式</div><div style={{ fontSize: 18, fontWeight: 600 }}>{styleLabResult.inference.resolved_style}</div></div>
                    </div>
                  </div>

                  <div className="glass-panel" style={{ padding: 18 }}>
                    <div style={{ fontSize: 13, color: 'var(--accent-blue-text)', marginBottom: 8 }}>AI 分析摘要</div>
                    <p style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.7 }}>{styleLabResult.analysis.reason}</p>
                  </div>

                  <div className="glass-panel" style={{ padding: 18 }}>
                    <div style={{ fontSize: 13, color: 'var(--accent-blue-text)', marginBottom: 10 }}>多维评分</div>
                    <RadarChart data={styleLabResult.analysis.radar_chart} />
                    {renderScoreBreakdown(styleLabResult.analysis.score_breakdown)}
                    {styleLabResult.analysis.brand_note && (
                      <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-secondary)' }}>{styleLabResult.analysis.brand_note}</div>
                    )}
                  </div>

                  <div className="glass-panel" style={{ padding: 18 }}>
                    <div style={{ fontSize: 13, color: 'var(--accent-blue-text)', marginBottom: 10 }}>穿搭建议</div>
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

  return (
    <>
      <div className="apple-nav">
        <div className="apple-nav-inner">
          <button className="apple-brand" onClick={() => navigateToView('recommend')}>AI 羽绒服推荐平台</button>
          <div className="apple-nav-links">
            <a className="nav-chip nav-chip-tryon" href={getTryOnBaseUrl()} target="_blank" rel="noopener noreferrer">羽绒服试穿</a>
            <button className={`nav-chip ${view === 'recommend' ? 'nav-chip-active' : ''}`} onClick={() => navigateToView('recommend')}>智能推荐</button>
            <button className={`nav-chip ${view === 'style-lab' ? 'nav-chip-active' : ''}`} onClick={() => navigateToView('style-lab')}>自己搭配</button>
            <button className="nav-history-btn" onClick={() => setHistoryOpen(true)}>
              <Clock size={14} />
              历史
            </button>
            <a className="nav-chip nav-chip-admin" href={getAdminUrl()} target="_blank" rel="noopener noreferrer">站长后台</a>
          </div>
        </div>
      </div>

      <div className="app-frame">
        <AnimatePresence mode="wait">
          {view === 'recommend' ? (
            <motion.div key="recommend" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
              {renderRecommendationView()}
            </motion.div>
          ) : (
            <motion.div key="style-lab" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
              {renderStyleLabView()}
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
    </>
  );
}
