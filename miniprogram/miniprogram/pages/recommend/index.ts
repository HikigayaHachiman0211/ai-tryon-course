import { getLocale, subscribeLocale, t } from '../../i18n';
import { getRecommend, localizeResult } from '../../services/mainApi';
import {
  clearUserPhoto,
  consumePendingAutoRecommend,
  getState,
  setActiveStyleLabProduct,
  setLastRecommendResult,
  setPendingTryOnHandoff,
  setUserPhoto,
  updateProfileForm,
} from '../../store/appStore';
import type {
  AppLocale,
  ProductCatalogItem,
  RecommendationRequest,
  RecommendationResponse,
  RecommendedItem,
} from '../../types/api';
import {
  BRAND_SUGGESTIONS,
  COLOR_SUGGESTIONS,
  GENDER_OPTIONS,
  MBTI_OPTIONS,
  SIZE_OPTIONS,
  STYLE_SUGGESTIONS,
} from '../../utils/formOptions';

interface TabBarInstance {
  syncTabState(index: number): void;
}

function buildOptionViews() {
  return {
    colors: COLOR_SUGGESTIONS.map((c) => ({
      value: c.value,
      swatch: c.swatch,
      label: t(c.labelKey),
    })),
    genders: GENDER_OPTIONS.map((g) => ({
      value: g.value,
      label: t(g.labelKey),
    })),
    brands: BRAND_SUGGESTIONS.map((b) => ({
      value: b.value,
      label: t(b.labelKey),
    })),
    styles: STYLE_SUGGESTIONS.map((s) => ({
      value: s.value,
      label: t(s.labelKey),
    })),
    mbtiRange: [t('profile.mbtiNone'), ...MBTI_OPTIONS],
    sizeRange: [t('profile.sizeAuto'), ...SIZE_OPTIONS],
  };
}

function buildTexts(result: RecommendationResponse | null) {
  const totalCount = result?.items.length || 0;
  return {
    eyebrow: t('profile.eyebrow'),
    heroTitle: t('profile.heroTitle'),
    heroCopy: t('profile.heroCopy'),
    colorLabel: t('profile.colorLabel'),
    colorRequired: t('profile.colorRequired'),
    colorPlaceholder: t('profile.colorPlaceholder'),
    genderLabel: t('profile.genderLabel'),
    brandLabel: t('profile.brandLabel'),
    brandPlaceholder: t('profile.brandPlaceholder'),
    priceMin: t('profile.priceMin'),
    priceMax: t('profile.priceMax'),
    priceUnlimited: t('profile.priceUnlimited'),
    mbtiLabel: t('profile.mbtiLabel'),
    sizeLabel: t('profile.sizeLabel'),
    sizeAuto: t('profile.sizeAuto'),
    styleLabel: t('profile.styleLabel'),
    stylePlaceholder: t('profile.stylePlaceholder'),
    submitBtn: t('profile.submitBtn'),
    submittingBtn: t('profile.submittingBtn'),
    inferenceTitle: t('recommend.inferenceTitle'),
    resolvedSize: t('recommend.resolvedSize'),
    resolvedStyle: t('recommend.resolvedStyle'),
    bodyShape: t('recommend.bodyShape'),
    engineUsed: t('recommend.engineUsed'),
    ruleFallback: t('recommend.ruleFallback'),
    catalogSummary: result
      ? t('recommend.catalogSummary', {
          total: result.filters.catalog_total,
          matched: result.filters.matched_after_price_filter,
        })
      : '',
    genderFallbackNotice: t('recommend.genderFallbackNotice'),
    resultsTitle: t('recommend.resultsTitle'),
    showAll: t('recommend.showAll', { count: totalCount }),
    showTop3: t('recommend.showTop3'),
    emptyHint: t('recommend.emptyHint'),
  };
}

Page({
  data: {
    locale: getLocale(),
    formData: getState().profileForm as RecommendationRequest,
    photoPreview: getState().userPhoto.previewUrl,
    sampleModelId: getState().userPhoto.sampleModelId || '',
    loading: false,
    errorMsg: '',
    result: getState().lastRecommendResult as RecommendationResponse | null,
    visibleCount: 3,
    showAllItems: false,
    mbtiIndex: 0,
    sizeIndex: 0,
    options: buildOptionViews(),
    texts: buildTexts(getState().lastRecommendResult),
  },
  _unsubLocale: undefined as undefined | (() => void),

  onLoad() {
    this._unsubLocale = subscribeLocale((nextLocale) => {
      this.handleLocaleUpdated(nextLocale);
    });
  },

  onUnload() {
    if (this._unsubLocale) {
      this._unsubLocale();
    }
  },

  onShow() {
    const tabBar = typeof this.getTabBar === 'function' ? (this.getTabBar() as unknown as TabBarInstance | null) : null;
    if (tabBar && typeof tabBar.syncTabState === 'function') {
      tabBar.syncTabState(0);
    }
    this.syncFromStore();
    if (consumePendingAutoRecommend()) {
      void this.onSubmitRecommend();
    }
  },

  syncFromStore() {
    const snap = getState();
    const locale = getLocale();
    wx.setNavigationBarTitle({ title: t('tabs.recommend') });
    const mbtiIdx = snap.profileForm.mbti ? MBTI_OPTIONS.indexOf(snap.profileForm.mbti) + 1 : 0;
    const sizeIdx = snap.profileForm.size ? SIZE_OPTIONS.indexOf(snap.profileForm.size) + 1 : 0;
    this.setData({
      locale,
      formData: snap.profileForm,
      photoPreview: snap.userPhoto.previewUrl,
      sampleModelId: snap.userPhoto.sampleModelId || '',
      result: snap.lastRecommendResult,
      mbtiIndex: Math.max(0, mbtiIdx),
      sizeIndex: Math.max(0, sizeIdx),
      options: buildOptionViews(),
      texts: buildTexts(snap.lastRecommendResult),
    });
    if (snap.lastRecommendResult && snap.lastRecommendResult.locale && snap.lastRecommendResult.locale !== locale) {
      void this.relocalizeCurrentResult(snap.lastRecommendResult, locale);
    }
  },

  async handleLocaleUpdated(nextLocale: AppLocale) {
    wx.setNavigationBarTitle({ title: t('tabs.recommend') });
    const current = this.data.result;
    this.setData({
      locale: nextLocale,
      options: buildOptionViews(),
      texts: buildTexts(current),
    });
    if (current && current.locale !== nextLocale) {
      await this.relocalizeCurrentResult(current, nextLocale);
    }
  },

  async relocalizeCurrentResult(current: RecommendationResponse, targetLocale: AppLocale) {
    try {
      const localized = await localizeResult('recommend', current, targetLocale);
      setLastRecommendResult(localized);
      this.setData({
        result: localized,
        texts: buildTexts(localized),
      });
    } catch {
      // Keep previous result visible if relocalization request fails
    }
  },

  onLocaleChange() {
    this.syncFromStore();
  },

  onPhotoChange(e: WechatMiniprogram.CustomEvent<{ localPath: string; previewUrl: string; sampleModelId: string; gender: string }>) {
    const { localPath, previewUrl, sampleModelId, gender } = e.detail;
    setUserPhoto({
      localPath,
      previewUrl,
      sampleModelId: sampleModelId || null,
      remoteUrl: '',
    });
    if ((gender === 'male' || gender === 'female') && !this.data.formData.gender) {
      updateProfileForm({ gender });
    }
    this.syncFromStore();
  },

  onPhotoClear() {
    clearUserPhoto();
    this.syncFromStore();
  },

  onInputField(e: WechatMiniprogram.Input) {
    const field = String(e.currentTarget.dataset.field || '');
    const value = String(e.detail.value || '');
    if (field === 'price_min' || field === 'price_max') {
      const num = value.trim() === '' ? undefined : Number(value);
      updateProfileForm({
        [field]: num !== undefined && Number.isFinite(num) ? num : undefined,
      });
    } else {
      updateProfileForm({ [field]: value });
    }
    this.setData({ formData: getState().profileForm, errorMsg: '' });
  },

  onPickChip(e: WechatMiniprogram.TouchEvent) {
    const field = String(e.currentTarget.dataset.field || '');
    const value = String(e.currentTarget.dataset.value || '');
    if (!field) return;
    updateProfileForm({ [field]: value });
    this.setData({ formData: getState().profileForm, errorMsg: '' });
  },

  onPickMbti(e: WechatMiniprogram.PickerChange) {
    const idx = Number(e.detail.value) || 0;
    const mbti = idx === 0 ? '' : MBTI_OPTIONS[idx - 1] || '';
    updateProfileForm({ mbti: mbti || undefined });
    this.setData({
      mbtiIndex: idx,
      formData: getState().profileForm,
    });
  },

  onPickSize(e: WechatMiniprogram.PickerChange) {
    const idx = Number(e.detail.value) || 0;
    const size = idx === 0 ? '' : SIZE_OPTIONS[idx - 1] || '';
    updateProfileForm({ size: size || undefined });
    this.setData({
      sizeIndex: idx,
      formData: getState().profileForm,
    });
  },

  async onSubmitRecommend() {
    const snap = getState();
    const form = snap.profileForm;
    if (!form.color_preference?.trim() || !form.gender) {
      this.setData({ errorMsg: t('profile.missingRequired') });
      wx.showToast({ title: t('profile.missingRequired'), icon: 'none' });
      return;
    }

    this.setData({ loading: true, errorMsg: '', showAllItems: false });
    try {
      const res = await getRecommend(form, snap.userPhoto.localPath || undefined);
      setLastRecommendResult(res);
      if (res.user_photo_url) {
        setUserPhoto({ remoteUrl: res.user_photo_url });
      }
      this.setData({
        result: res,
        texts: buildTexts(res),
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : t('common.unknownError');
      this.setData({ errorMsg: msg });
    } finally {
      this.setData({ loading: false });
    }
  },

  onToggleShowAll() {
    this.setData({ showAllItems: !this.data.showAllItems });
  },

  onCardTryOn(e: WechatMiniprogram.CustomEvent<{ item: RecommendedItem }>) {
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
      sizeHint: snap.lastRecommendResult?.inference?.resolved_size || snap.profileForm.size || '',
      reason: item.reason,
      userPhotoLocalPath: snap.userPhoto.localPath || undefined,
      userPhotoPreviewUrl: snap.userPhoto.previewUrl || undefined,
      userPhotoRemoteUrl: snap.lastRecommendResult?.user_photo_url || snap.userPhoto.remoteUrl || undefined,
    });
    wx.switchTab({ url: '/pages/tryon/index' });
  },

  onCardStyleLab(e: WechatMiniprogram.CustomEvent<{ item: RecommendedItem }>) {
    const item = e.detail.item;
    const snap = getState();
    const genderVal = snap.profileForm.gender || 'female';
    const catalogItem: ProductCatalogItem = {
      ...item,
      product_gender: genderVal,
      gender_label: genderVal === 'male' ? t('profile.genderMale') : t('profile.genderFemale'),
      is_child_product: false,
    };
    setActiveStyleLabProduct(catalogItem);
    wx.navigateTo({ url: '/pages/style-lab/index' });
  },
});
