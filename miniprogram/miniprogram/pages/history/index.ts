import { getEndpointConfig } from '../../config/env';
import { getLocale, subscribeLocale, t } from '../../i18n';
import { getHistory, getHistoryDetail } from '../../services/mainApi';
import {
  setActiveStyleLabProduct,
  setLastRecommendResult,
  setPendingTryOnHandoff,
} from '../../store/appStore';
import type {
  HistoryEntry,
  ProductCatalogItem,
  RecommendationResponse,
  RecommendedItem,
  StyleLabAnalysisResponse,
} from '../../types/api';
import { buildMainMediaUrl } from '../../utils/url';

interface HistoryEntryView extends HistoryEntry {
  thumbUrl: string;
  formattedTime: string;
  typeLabel: string;
  itemCountText: string;
  scoreText: string;
}

function formatTime(iso: string): string {
  if (!iso) return '';
  return iso.replace('T', ' ').slice(0, 16);
}

function buildTexts() {
  return {
    title: t('history.title'),
    subtitle: t('history.subtitle'),
    empty: t('history.empty'),
    loading: t('common.loading'),
    detailTitle: t('history.detailTitle'),
    restoreToRecommend: t('history.restoreToRecommend'),
    tryOnBtn: t('recommend.tryOnBtn'),
    styleLabBtn: t('recommend.styleLabBtn'),
    close: t('common.close'),
  };
}

Page({
  data: {
    locale: getLocale(),
    entries: [] as HistoryEntryView[],
    loading: false,
    errorMsg: '',
    detailOpen: false,
    detailLoading: false,
    detailKind: '' as '' | 'recommend' | 'style-lab',
    detailPayload: null as Record<string, unknown> | null,
    detailItems: [] as Array<RecommendedItem & { thumbUrl: string }>,
    detailProduct: null as (ProductCatalogItem & { thumbUrl: string }) | null,
    detailSummary: '',
    texts: buildTexts(),
  },
  _unsubLocale: undefined as undefined | (() => void),

  onLoad() {
    this._unsubLocale = subscribeLocale((nextLocale) => {
      this.setData({ locale: nextLocale, texts: buildTexts() });
      void this.loadList();
    });
  },

  onUnload() {
    if (this._unsubLocale) this._unsubLocale();
  },

  onShow() {
    wx.setNavigationBarTitle({ title: t('history.title') });
    this.setData({ locale: getLocale(), texts: buildTexts() });
    void this.loadList();
  },

  onPullDownRefresh() {
    void this.loadList().finally(() => {
      wx.stopPullDownRefresh();
    });
  },

  async loadList() {
    this.setData({ loading: true, errorMsg: '' });
    try {
      const res = await getHistory(50);
      const base = getEndpointConfig().mainApiBaseUrl;
      const entries: HistoryEntryView[] = (res.items || []).map((entry) => ({
        ...entry,
        thumbUrl: buildMainMediaUrl(entry.thumbnail_url, base),
        formattedTime: formatTime(entry.timestamp),
        typeLabel: entry.type === 'style-lab' ? t('history.typeStyleLab') : t('history.typeRecommend'),
        itemCountText: entry.item_count ? t('history.itemCount', { count: entry.item_count }) : '',
        scoreText: entry.total_score !== null && entry.total_score !== undefined
          ? `${Math.round(entry.total_score)}${t('common.scoreUnit')}`
          : '',
      }));
      this.setData({ entries });
    } catch (err) {
      const msg = err instanceof Error ? err.message : t('common.networkError');
      this.setData({ errorMsg: msg });
    } finally {
      this.setData({ loading: false });
    }
  },

  onLocaleChange() {
    this.setData({ locale: getLocale(), texts: buildTexts() });
    void this.loadList();
  },

  async onOpenEntry(e: WechatMiniprogram.TouchEvent) {
    const id = String(e.currentTarget.dataset.id || '');
    const kind = (String(e.currentTarget.dataset.type || 'recommend') as 'recommend' | 'style-lab');
    if (!id) return;
    this.setData({
      detailOpen: true,
      detailLoading: true,
      detailKind: kind,
      detailPayload: null,
      detailItems: [],
      detailProduct: null,
      detailSummary: '',
    });
    try {
      const detail = await getHistoryDetail(id);
      const base = getEndpointConfig().mainApiBaseUrl;
      if (kind === 'style-lab') {
        const typed = detail as unknown as StyleLabAnalysisResponse;
        const p = typed.product;
        this.setData({
          detailPayload: detail,
          detailProduct: p
            ? {
                ...p,
                thumbUrl: buildMainMediaUrl(p.canonical?.image_url || p.image_url, base),
              }
            : null,
          detailSummary: typed.analysis?.reason || '',
        });
      } else {
        const typed = detail as unknown as RecommendationResponse;
        const items = (typed.items || []).map((item) => ({
          ...item,
          thumbUrl: buildMainMediaUrl(item.canonical?.image_url || item.image_url, base),
        }));
        this.setData({
          detailPayload: detail,
          detailItems: items,
          detailSummary: typed.inference?.reasoning || '',
        });
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : t('common.networkError');
      wx.showToast({ title: msg.slice(0, 28), icon: 'none' });
      this.setData({ detailOpen: false });
    } finally {
      this.setData({ detailLoading: false });
    }
  },

  onCloseDetail() {
    this.setData({ detailOpen: false });
  },

  onRestoreRecommend() {
    if (!this.data.detailPayload) return;
    setLastRecommendResult(this.data.detailPayload as unknown as RecommendationResponse);
    this.setData({ detailOpen: false });
    wx.switchTab({ url: '/pages/recommend/index' });
  },

  onTryOnHistoryItem(e: WechatMiniprogram.TouchEvent) {
    const idx = Number(e.currentTarget.dataset.index);
    const target = Number.isFinite(idx) && idx >= 0
      ? this.data.detailItems[idx]
      : this.data.detailProduct;
    if (!target) return;
    setPendingTryOnHandoff({
      productId: target.id,
      productTitle: target.display?.title || target.title,
      productPrice: target.price,
      garmentImageUrl: target.canonical?.image_url || target.image_url,
      styleType: target.display?.styleType || target.style_type,
      colorFamily: target.display?.colorFamily || target.color_family,
    });
    this.setData({ detailOpen: false });
    wx.switchTab({ url: '/pages/tryon/index' });
  },

  onOpenStyleLabDetail() {
    const product = this.data.detailProduct;
    if (!product) return;
    setActiveStyleLabProduct(product);
    this.setData({ detailOpen: false });
    wx.navigateTo({ url: '/pages/style-lab/index' });
  },
});
