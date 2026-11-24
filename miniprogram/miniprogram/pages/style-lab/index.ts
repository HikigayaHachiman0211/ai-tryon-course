import { getEndpointConfig } from '../../config/env';
import { getLocale, subscribeLocale, t } from '../../i18n';
import { analyzeStyleLab, localizeResult } from '../../services/mainApi';
import {
  clearUserPhoto,
  getState,
  setActiveStyleLabProduct,
  setPendingTryOnHandoff,
  setUserPhoto,
  updateProfileForm,
} from '../../store/appStore';
import type {
  AppLocale,
  ProductCatalogItem,
  RecommendationRequest,
  StyleLabAnalysisResponse,
} from '../../types/api';
import {
  COLOR_SUGGESTIONS,
  GENDER_OPTIONS,
  MBTI_OPTIONS,
  SIZE_OPTIONS,
} from '../../utils/formOptions';
import { buildMainMediaUrl } from '../../utils/url';

function buildTexts() {
  return {
    title: t('styleLab.title'),
    subtitle: t('styleLab.subtitle'),
    noProduct: t('styleLab.noProduct'),
    goCatalog: t('styleLab.goCatalog'),
    editProfile: t('styleLab.editProfile'),
    hideProfile: t('styleLab.hideProfile'),
    runAnalyze: t('styleLab.runAnalyze'),
    analyzing: t('styleLab.analyzing'),
    adviceTitle: t('styleLab.adviceTitle'),
    notesTitle: t('styleLab.notesTitle'),
    tryOnThis: t('styleLab.tryOnThis'),
    matchScore: t('score.matchScore'),
    scoreUnit: t('common.scoreUnit'),
    inferenceTitle: t('recommend.inferenceTitle'),
    resolvedSize: t('recommend.resolvedSize'),
    resolvedStyle: t('recommend.resolvedStyle'),
    bodyShape: t('recommend.bodyShape'),
    colorLabel: t('profile.colorLabel'),
    colorRequired: t('profile.colorRequired'),
    colorPlaceholder: t('profile.colorPlaceholder'),
    genderLabel: t('profile.genderLabel'),
    priceMin: t('profile.priceMin'),
    priceMax: t('profile.priceMax'),
    priceUnlimited: t('profile.priceUnlimited'),
    mbtiLabel: t('profile.mbtiLabel'),
    sizeLabel: t('profile.sizeLabel'),
    styleLabel: t('profile.styleLabel'),
    stylePlaceholder: t('profile.stylePlaceholder'),
  };
}

Page({
  data: {
    locale: getLocale(),
    product: null as ProductCatalogItem | null,
    productImageUrl: '',
    displayTitle: '',
    displayStyle: '',
    displayColor: '',
    displayFit: '',
    formData: getState().profileForm as RecommendationRequest,
    photoPreview: getState().userPhoto.previewUrl,
    sampleModelId: getState().userPhoto.sampleModelId || '',
    profileOpen: true,
    loading: false,
    errorMsg: '',
    analysisResult: null as StyleLabAnalysisResponse | null,
    notes: [] as string[],
    mbtiIndex: 0,
    sizeIndex: 0,
    mbtiRange: [t('profile.mbtiNone'), ...MBTI_OPTIONS],
    sizeRange: [t('profile.sizeAuto'), ...SIZE_OPTIONS],
    colors: COLOR_SUGGESTIONS.map((c) => ({ value: c.value, swatch: c.swatch, label: t(c.labelKey) })),
    genders: GENDER_OPTIONS.map((g) => ({ value: g.value, label: t(g.labelKey) })),
    texts: buildTexts(),
  },
  _unsubLocale: undefined as undefined | (() => void),

  onLoad() {
    this._unsubLocale = subscribeLocale((nextLocale) => {
      void this.handleLocaleUpdate(nextLocale);
    });
  },

  onUnload() {
    if (this._unsubLocale) this._unsubLocale();
  },

  onShow() {
    this.syncState();
  },

  syncState() {
    const snap = getState();
    const locale = getLocale();
    wx.setNavigationBarTitle({ title: 'Style Lab' });
    const product = snap.activeStyleLabProduct;
    const rawImg = product ? product.canonical?.image_url || product.image_url : '';
    const mbtiIdx = snap.profileForm.mbti ? MBTI_OPTIONS.indexOf(snap.profileForm.mbti) + 1 : 0;
    const sizeIdx = snap.profileForm.size ? SIZE_OPTIONS.indexOf(snap.profileForm.size) + 1 : 0;

    this.setData({
      locale,
      product,
      productImageUrl: buildMainMediaUrl(rawImg, getEndpointConfig().mainApiBaseUrl),
      displayTitle: product ? product.display?.title || product.title : '',
      displayStyle: product ? product.display?.styleType || product.style_type : '',
      displayColor: product ? product.display?.colorFamily || product.color_family : '',
      displayFit: product ? product.display?.bodyFit || product.body_fit : '',
      formData: snap.profileForm,
      photoPreview: snap.userPhoto.previewUrl,
      sampleModelId: snap.userPhoto.sampleModelId || '',
      mbtiIndex: Math.max(0, mbtiIdx),
      sizeIndex: Math.max(0, sizeIdx),
      mbtiRange: [t('profile.mbtiNone'), ...MBTI_OPTIONS],
      sizeRange: [t('profile.sizeAuto'), ...SIZE_OPTIONS],
      colors: COLOR_SUGGESTIONS.map((c) => ({ value: c.value, swatch: c.swatch, label: t(c.labelKey) })),
      genders: GENDER_OPTIONS.map((g) => ({ value: g.value, label: t(g.labelKey) })),
      texts: buildTexts(),
    });
  },

  async handleLocaleUpdate(nextLocale: AppLocale) {
    this.syncState();
    const currentRes = this.data.analysisResult;
    if (currentRes && currentRes.locale !== nextLocale) {
      try {
        const localized = await localizeResult('style-lab', currentRes, nextLocale);
        setActiveStyleLabProduct(localized.product);
        this.applyAnalysisResult(localized);
      } catch {
        // Keep current result if relocalize fails
      }
      return;
    }
    const product = this.data.product;
    if (product && product.locale !== nextLocale) {
      try {
        const localizedProduct = await localizeResult('product', product, nextLocale);
        setActiveStyleLabProduct(localizedProduct);
        this.syncState();
      } catch {
        // Keep current product if relocalize fails
      }
    }
  },

  applyAnalysisResult(res: StyleLabAnalysisResponse) {
    const notes = [
      res.analysis.budget_note,
      res.analysis.brand_note,
      res.analysis.gender_note,
      res.analysis.personality_note,
    ].filter((v): v is string => Boolean(v && v.trim()));
    this.setData({
      analysisResult: res,
      notes,
      profileOpen: false,
    });
    this.syncState();
  },

  onLocaleChange() {
    void this.handleLocaleUpdate(getLocale());
  },

  onToggleProfile() {
    this.setData({ profileOpen: !this.data.profileOpen });
  },

  onGoCatalog() {
    wx.switchTab({ url: '/pages/catalog/index' });
  },

  onPhotoChange(e: WechatMiniprogram.CustomEvent<{ localPath: string; previewUrl: string; sampleModelId: string; gender: string }>) {
    const { localPath, previewUrl, sampleModelId, gender } = e.detail;
    setUserPhoto({ localPath, previewUrl, sampleModelId: sampleModelId || null, remoteUrl: '' });
    if ((gender === 'male' || gender === 'female') && !this.data.formData.gender) {
      updateProfileForm({ gender });
    }
    this.syncState();
  },

  onPhotoClear() {
    clearUserPhoto();
    this.syncState();
  },

  onInputField(e: WechatMiniprogram.Input) {
    const field = String(e.currentTarget.dataset.field || '');
    const value = String(e.detail.value || '');
    if (field === 'price_min' || field === 'price_max') {
      const num = value.trim() === '' ? undefined : Number(value);
      updateProfileForm({ [field]: num !== undefined && Number.isFinite(num) ? num : undefined });
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
    this.setData({ mbtiIndex: idx, formData: getState().profileForm });
  },

  onPickSize(e: WechatMiniprogram.PickerChange) {
    const idx = Number(e.detail.value) || 0;
    const size = idx === 0 ? '' : SIZE_OPTIONS[idx - 1] || '';
    updateProfileForm({ size: size || undefined });
    this.setData({ sizeIndex: idx, formData: getState().profileForm });
  },

  async onRunAnalysis() {
    const product = this.data.product;
    if (!product) return;
    const snap = getState();
    const form = snap.profileForm;
    if (!form.color_preference?.trim() || !form.gender) {
      this.setData({ errorMsg: t('profile.missingRequired'), profileOpen: true });
      wx.showToast({ title: t('profile.missingRequired'), icon: 'none' });
      return;
    }

    this.setData({ loading: true, errorMsg: '' });
    try {
      const res = await analyzeStyleLab(product.id, form, snap.userPhoto.localPath || undefined);
      setActiveStyleLabProduct(res.product);
      if (res.user_photo_url) {
        setUserPhoto({ remoteUrl: res.user_photo_url });
      }
      this.applyAnalysisResult(res);
    } catch (err) {
      const msg = err instanceof Error ? err.message : t('common.unknownError');
      this.setData({ errorMsg: msg });
    } finally {
      this.setData({ loading: false });
    }
  },

  onTryOnThis() {
    const product = this.data.product;
    if (!product) return;
    const snap = getState();
    const rawImg = product.canonical?.image_url || product.image_url;
    setPendingTryOnHandoff({
      productId: product.id,
      productTitle: product.display?.title || product.title,
      productPrice: product.price,
      garmentImageUrl: rawImg,
      styleType: product.display?.styleType || product.style_type,
      colorFamily: product.display?.colorFamily || product.color_family,
      sizeHint: this.data.analysisResult?.inference?.resolved_size || snap.profileForm.size || '',
      reason: this.data.analysisResult?.analysis?.reason,
      userPhotoLocalPath: snap.userPhoto.localPath || undefined,
      userPhotoPreviewUrl: snap.userPhoto.previewUrl || undefined,
      userPhotoRemoteUrl: this.data.analysisResult?.user_photo_url || snap.userPhoto.remoteUrl || undefined,
    });
    wx.switchTab({ url: '/pages/tryon/index' });
  },
});
