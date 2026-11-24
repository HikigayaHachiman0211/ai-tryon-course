import { Loader2, Search, SlidersHorizontal } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { buildImageURL } from '../api';
import type { CatalogMode, CatalogPlatform } from '../constants/formOptions';
import type { ProductCatalogItem } from '../types';
import { ErrorBanner } from './ErrorBanner';
import { formatCurrency } from '../i18n/formatters';
import i18n from '../i18n';
import { DEFAULT_LOCALE, normalizeLocale } from '../i18n/locale';

interface CatalogPanelProps {
  catalogMode: CatalogMode;
  catalogPlatform: CatalogPlatform;
  catalogQuery: string;
  catalogItems: ProductCatalogItem[];
  catalogTotal: number;
  catalogLoading: boolean;
  catalogError: string | null;
  catalogGenderFallback: boolean;
  selectedProduct: ProductCatalogItem | null;
  canLoadMore: boolean;
  onModeChange: (mode: CatalogMode) => void;
  onPlatformChange: (platform: CatalogPlatform) => void;
  onQueryChange: (query: string) => void;
  onSelectProduct: (product: ProductCatalogItem) => void;
  onLoadMore: () => void;
}

function CatalogCard({
  product,
  selected,
  onSelect,
}: {
  product: ProductCatalogItem;
  selected: boolean;
  onSelect: (product: ProductCatalogItem) => void;
}) {
  const { t } = useTranslation(['styleLab', 'common']);
  const locale = normalizeLocale(i18n.resolvedLanguage) ?? DEFAULT_LOCALE;
  const display = product.display;
  return (
    <button
      key={product.id}
      className={`catalog-card ${selected ? 'catalog-card-active' : ''}`}
      onClick={() => onSelect(product)}
      type="button"
    >
      <div style={{ width: 84, height: 108, flexShrink: 0, borderRadius: 10, overflow: 'hidden', background: '#08090c' }}>
        <img src={buildImageURL(product.image_url)} alt={display?.title ?? product.title} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      </div>

      <div style={{ flex: 1, minWidth: 0, textAlign: 'left' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
          <h4 style={{ fontSize: 14, lineHeight: 1.5, color: '#F8FAFC' }}>{display?.title ?? product.title}</h4>
          <span style={{ fontSize: 11, color: selected ? 'var(--accent-blue-text)' : 'var(--text-tertiary)', flexShrink: 0 }}>{product.gender_label}</span>
        </div>
        {product.brand && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-tertiary)' }}>{t('catalog.brand')}: {product.brand}</div>}
        {product.platform && <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-tertiary)' }}>{t('catalog.platformLabel')}: {product.platform}</div>}
        <div style={{ marginTop: 8, fontSize: 20, fontWeight: 600, color: 'var(--accent-blue-text)' }}>{formatCurrency(product.price, locale)}</div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
          {product.brand && <span className="catalog-tag">{product.brand}</span>}
          {product.platform && <span className="catalog-tag">{product.platform}</span>}
          <span className="catalog-tag">{display?.colorFamily ?? product.color_family}</span>
          <span className="catalog-tag">{display?.styleType ?? product.style_type}</span>
        </div>
      </div>
    </button>
  );
}

export function CatalogPanel({
  catalogMode,
  catalogPlatform,
  catalogQuery,
  catalogItems,
  catalogTotal,
  catalogLoading,
  catalogError,
  catalogGenderFallback,
  selectedProduct,
  canLoadMore,
  onModeChange,
  onPlatformChange,
  onQueryChange,
  onSelectProduct,
  onLoadMore,
}: CatalogPanelProps) {
  const { t } = useTranslation(['styleLab', 'common']);
  return (
    <div className="glass-panel style-lab-column style-lab-panel" style={{ padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap', marginBottom: 16 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ fontSize: 18, fontWeight: 600, marginBottom: 6 }}>{t('catalog.title')}</h3>
          <p style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{t('catalog.description')}</p>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-tertiary)', flexShrink: 0 }}>{t('catalog.loaded', { loaded: catalogItems.length, total: catalogTotal })}</div>
      </div>

      <div className="catalog-filter-bar">
        <button className={catalogMode === 'gender' ? 'btn-secondary' : 'catalog-mode-button'} onClick={() => onModeChange('gender')}>{t('catalog.mode.forYou')}</button>
        <button className={catalogMode === 'all' ? 'btn-secondary' : 'catalog-mode-button'} onClick={() => onModeChange('all')}>{t('catalog.mode.allAdults')}</button>
        <button className={catalogPlatform === 'all' ? 'btn-secondary' : 'catalog-mode-button'} onClick={() => onPlatformChange('all')}>{t('catalog.platform.all')}</button>
        <button className={catalogPlatform === 'jd' ? 'btn-secondary' : 'catalog-mode-button'} onClick={() => onPlatformChange('jd')}>{t('catalog.platform.jd')}</button>
        <button className={catalogPlatform === 'taobao' ? 'btn-secondary' : 'catalog-mode-button'} onClick={() => onPlatformChange('taobao')}>{t('catalog.platform.taobao')}</button>
      </div>

      <div style={{ position: 'relative', marginBottom: 16 }}>
        <Search size={16} style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)', pointerEvents: 'none' }} />
        <input
          className="modern-input"
          value={catalogQuery}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder={t('catalog.searchPlaceholder')}
          style={{ paddingLeft: 40 }}
        />
      </div>

      {catalogGenderFallback && (
        <div style={{ marginBottom: 12, fontSize: 12, color: 'var(--accent-warm)' }}>
          {t('catalog.genderFallback')}
        </div>
      )}

      {catalogError && (
        <div style={{ marginBottom: 16 }}>
          <ErrorBanner error={{ code: 'LAB-CATALOG', message: catalogError, request_id: 'local', details: null }} />
        </div>
      )}

      <div className="catalog-list">
        {catalogItems.map((product) => (
          <CatalogCard
            key={product.id}
            product={product}
            selected={selectedProduct?.id === product.id}
            onSelect={onSelectProduct}
          />
        ))}
        {!catalogLoading && catalogItems.length === 0 && !catalogError && (
          <div className="catalog-empty-state">
            <SlidersHorizontal size={32} style={{ opacity: 0.5, marginBottom: 12 }} />
            <div>{t('catalog.empty')}</div>
          </div>
        )}
      </div>

      {catalogLoading && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '18px 0', color: 'var(--text-secondary)' }}>
          <Loader2 className="animate-spin" />
        </div>
      )}

      {!catalogLoading && canLoadMore && (
        <button className="btn-secondary" style={{ width: '100%', marginTop: 16 }} onClick={onLoadMore}>
          {t('catalog.loadMore')}
        </button>
      )}
    </div>
  );
}
