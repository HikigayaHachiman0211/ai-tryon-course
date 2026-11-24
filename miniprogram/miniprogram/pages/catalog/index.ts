import { getLocale, subscribeLocale, t } from '../../i18n';
import { getCatalogProducts } from '../../services/mainApi';
import { getState, setActiveStyleLabProduct, setPendingTryOnHandoff } from '../../store/appStore';
import type { AppLocale, ProductCatalogItem } from '../../types/api';

interface TabBarInstance {
  syncTabState(index: number): void;
}

const PAGE_LIMIT = 20;

function buildTexts(total: number) {
  return {
    title: t('catalog.title'),
    subtitle: t('catalog.subtitle'),
    searchPlaceholder: t('catalog.searchPlaceholder'),
    searchBtn: t('common.search'),
    platformAll: t('catalog.platformAll'),
    platformJd: t('catalog.platformJd'),
    platformTaobao: t('catalog.platformTaobao'),
    modeAll: t('catalog.modeAll'),
    modeGender: t('catalog.modeGender'),
    genderAll: t('catalog.genderAll'),
    genderFemale: t('profile.genderFemale'),
    genderMale: t('profile.genderMale'),
    totalCount: t('catalog.totalCount', { total }),
    loadingMore: t('catalog.loadingMore'),
    noMore: t('catalog.noMore'),
    empty: t('catalog.empty'),
    loading: t('common.loading'),
  };
}

Page({
  data: {
    locale: getLocale(),
    query: '',
    platform: 'all' as 'all' | 'jd' | 'taobao',
    mode: 'all' as 'all' | 'gender',
    gender: '' as '' | 'female' | 'male',
    items: [] as ProductCatalogItem[],
    total: 0,
    loading: false,
    loadingMore: false,
    errorMsg: '',
    lastFetchedLocale: '' as '' | AppLocale,
    texts: buildTexts(0),
  },
  _unsubLocale: undefined as undefined | (() => void),

  onLoad() {
    this._unsubLocale = subscribeLocale((nextLocale) => {
      wx.setNavigationBarTitle({ title: t('tabs.catalog') });
      this.setData({
        locale: nextLocale,
        texts: buildTexts(this.data.total),
      });
      if (this.data.lastFetchedLocale !== nextLocale) {
        void this.loadProducts(true);
      }
    });
  },

  onUnload() {
    if (this._unsubLocale) this._unsubLocale();
  },

  onShow() {
    const tabBar = typeof this.getTabBar === 'function' ? (this.getTabBar() as unknown as TabBarInstance | null) : null;
    if (tabBar && typeof tabBar.syncTabState === 'function') {
      tabBar.syncTabState(1);
    }
    const locale = getLocale();
    wx.setNavigationBarTitle({ title: t('tabs.catalog') });
    this.setData({
      locale,
      texts: buildTexts(this.data.total),
    });
    if (this.data.items.length === 0 || this.data.lastFetchedLocale !== locale) {
      void this.loadProducts(true);
    }
  },

  onPullDownRefresh() {
    void this.loadProducts(true).finally(() => {
      wx.stopPullDownRefresh();
    });
  },

  onReachBottom() {
    if (this.data.loading || this.data.loadingMore) return;
    if (this.data.items.length >= this.data.total) return;
    void this.loadProducts(false);
  },

  async loadProducts(reset: boolean) {
    const offset = reset ? 0 : this.data.items.length;
    this.setData({
      loading: reset,
      loadingMore: !reset,
      errorMsg: '',
    });
    const profileGender = getState().profileForm.gender || '';
    const effectiveGender =
      this.data.gender || (this.data.mode === 'gender' ? profileGender : '');

    try {
      const res = await getCatalogProducts({
        query: this.data.query.trim() || undefined,
        platform: this.data.platform === 'all' ? undefined : this.data.platform,
        mode: this.data.mode,
        gender: effectiveGender || undefined,
        offset,
        limit: PAGE_LIMIT,
      });
      const nextItems = reset ? res.items : [...this.data.items, ...res.items];
      this.setData({
        items: nextItems,
        total: res.total,
        lastFetchedLocale: getLocale(),
        texts: buildTexts(res.total),
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : t('common.networkError');
      this.setData({ errorMsg: msg });
    } finally {
      this.setData({ loading: false, loadingMore: false });
    }
  },

  onLocaleChange() {
    const locale = getLocale();
    this.setData({ locale, texts: buildTexts(this.data.total) });
    void this.loadProducts(true);
  },

  onQueryInput(e: WechatMiniprogram.Input) {
    this.setData({ query: String(e.detail.value || '') });
  },

  onSearchConfirm() {
    void this.loadProducts(true);
  },

  onSelectPlatform(e: WechatMiniprogram.TouchEvent) {
    const platform = e.currentTarget.dataset.platform as 'all' | 'jd' | 'taobao';
    if (!platform || platform === this.data.platform) return;
    this.setData({ platform });
    void this.loadProducts(true);
  },

  onSelectGenderFilter(e: WechatMiniprogram.TouchEvent) {
    const gender = String(e.currentTarget.dataset.gender || '') as '' | 'female' | 'male';
    this.setData({
      gender,
      mode: gender ? 'gender' : 'all',
    });
    void this.loadProducts(true);
  },

  onCardTryOn(e: WechatMiniprogram.CustomEvent<{ item: ProductCatalogItem }>) {
    const item = e.detail.item;
    const snap = getState();
    const rawImg = item.canonical?.image_url || item.image_url;
    setPendingTryOnHandoff({
      productId: item.id,
      productTitle: item.display?.title || item.title,
      productPrice: item.price,
      garmentImageUrl: rawImg,
      styleType: item.display?.styleType || item.style_type,
      colorFamily: item.display?.colorFamily || item.color_family,
      sizeHint: snap.profileForm.size || '',
      userPhotoLocalPath: snap.userPhoto.localPath || undefined,
      userPhotoPreviewUrl: snap.userPhoto.previewUrl || undefined,
      userPhotoRemoteUrl: snap.userPhoto.remoteUrl || undefined,
    });
    wx.switchTab({ url: '/pages/tryon/index' });
  },

  onCardStyleLab(e: WechatMiniprogram.CustomEvent<{ item: ProductCatalogItem }>) {
    setActiveStyleLabProduct(e.detail.item);
    wx.navigateTo({ url: '/pages/style-lab/index' });
  },
});
