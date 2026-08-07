import { Loader2, Search, SlidersHorizontal } from 'lucide-react';
import { buildImageURL } from '../api';
import type { CatalogMode, CatalogPlatform } from '../constants/formOptions';
import type { ProductCatalogItem } from '../types';
import { ErrorBanner } from './ErrorBanner';

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
  return (
    <button
      key={product.id}
      className={`catalog-card ${selected ? 'catalog-card-active' : ''}`}
      onClick={() => onSelect(product)}
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
  return (
    <div className="glass-panel style-lab-column" style={{ padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', marginBottom: 16 }}>
        <div>
          <h3 style={{ fontSize: 18, fontWeight: 600, marginBottom: 6 }}>羽绒服库</h3>
          <p style={{ fontSize: 12, color: 'var(--text-secondary)' }}>搜索并选择数据库中的羽绒服进行自定义搭配。</p>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>已加载 {catalogItems.length} / {catalogTotal}</div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <button className={catalogMode === 'gender' ? 'btn-secondary' : 'catalog-mode-button'} onClick={() => onModeChange('gender')}>更适合你</button>
        <button className={catalogMode === 'all' ? 'btn-secondary' : 'catalog-mode-button'} onClick={() => onModeChange('all')}>全部成人款</button>
        <button className={catalogPlatform === 'all' ? 'btn-secondary' : 'catalog-mode-button'} onClick={() => onPlatformChange('all')}>全部库</button>
        <button className={catalogPlatform === 'jd' ? 'btn-secondary' : 'catalog-mode-button'} onClick={() => onPlatformChange('jd')}>京东库</button>
        <button className={catalogPlatform === 'taobao' ? 'btn-secondary' : 'catalog-mode-button'} onClick={() => onPlatformChange('taobao')}>淘宝库</button>
      </div>

      <div style={{ position: 'relative', marginBottom: 16 }}>
        <Search size={16} style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)' }} />
        <input
          className="modern-input"
          value={catalogQuery}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="搜索品牌、款式、颜色或功能，例如：白色 户外 三防"
          style={{ paddingLeft: 40 }}
        />
      </div>

      {catalogGenderFallback && (
        <div style={{ marginBottom: 12, fontSize: 12, color: 'var(--accent-warm)' }}>
          当前筛选条件下没有更多符合性别偏好的商品，已显示全部成人款供你手动挑选。
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
            <div>当前条件下没有可浏览的羽绒服。</div>
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
          加载更多羽绒服
        </button>
      )}
    </div>
  );
}
