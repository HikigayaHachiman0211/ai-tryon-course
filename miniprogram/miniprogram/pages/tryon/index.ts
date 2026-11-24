import { getEndpointConfig } from '../../config/env';
import { getLocale, subscribeLocale, t } from '../../i18n';
import {
  getRateStatus,
  getRuntimeStatus,
  getTryOnTask,
  getWorkbenchProducts,
  intakeOrUploadImage,
  resolveTryOnAssetUrl,
  submitTryOnTask,
  uploadGarmentPhoto,
  uploadModelPhoto,
  workbenchHeaders,
} from '../../services/tryonApi';
import {
  cancelVideoTask,
  getVideoConfig,
  getVideoModels,
  listVideoTasks,
  pollVideoTask,
  quoteVideo,
  resolveVideoDownloadUrl,
  submitVideoTask,
} from '../../services/videoApi';
import {
  consumePendingTryOnHandoff,
  getState,
  setLastTryOnResult,
} from '../../store/appStore';
import type {
  AppLocale,
  ProductCatalogItem,
  RuntimeStatusResponse,
  TryOnModelEntry,
  TryOnProviderCatalog,
  TryOnTaskResponse,
  VideoConfigResponse,
  VideoModelItem,
  VideoParamSpec,
  VideoTaskResponse,
} from '../../types/api';
import {
  SAMPLE_MODELS,
  TRYON_GARMENT_TYPES,
  VIDEO_PRESET_PROMPTS,
} from '../../utils/formOptions';
import { downloadTempFile } from '../../utils/request';
import { generateClientUuid } from '../../utils/storage';
import { buildMainMediaUrl, buildSampleModelUrl } from '../../utils/url';
import {
  adaptiveAspectRatio,
  bindSourceImage,
  collectInput,
  defaultsFor,
  parametersFor,
  pickDefaultVideoModel,
} from '../../utils/videoForm';

interface TabBarInstance {
  syncTabState(index: number): void;
}

interface DynamicParamView {
  name: string;
  type: VideoParamSpec['type'];
  required: boolean;
  isSelect: boolean;
  isTextarea: boolean;
  isNumber: boolean;
  displayOptions: string[];
  rawOptions: Array<string | number | boolean>;
  selectedIndex: number;
  valueStr: string;
  placeholder: string;
}

interface VideoTaskView extends VideoTaskResponse {
  playbackUrl: string;
  createdAtText: string;
}

function formatTs(sec?: number): string {
  if (!sec) return '';
  const d = new Date(sec * 1000);
  const pad = (n: number) => (n < 10 ? `0${n}` : String(n));
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function buildProvidersFromStatus(status: RuntimeStatusResponse): TryOnProviderCatalog[] {
  if (Array.isArray(status.providers) && status.providers.length > 0) {
    return status.providers;
  }
  const models: TryOnModelEntry[] = (status.available_models || ['flash']).map((m) => ({
    id: status.model_labels?.[m] || m,
    label: status.model_labels?.[m] ? `${m} (${status.model_labels[m]})` : m,
    preset_key: m,
    protocol: m === 'chatgpt' ? 'openai_images_edit' : 'gemini_generate_content',
    speed_tier: m === 'pro' ? 'quality' : 'fast',
    badge: m,
    max_concurrency: 5,
    is_default: m === 'flash',
    capabilities: {
      protocol: m === 'chatgpt' ? 'openai_images_edit' : 'gemini_generate_content',
      supports_aspect_ratio: true,
      aspect_ratio_options: ['auto', '3:4', '4:5', '9:16', '1:1', '16:9'],
      supports_image_size: true,
      image_size_options: ['auto', '1K', '2K', '4K'],
      supports_quality: m === 'chatgpt',
      quality_options: m === 'chatgpt' ? ['auto', 'low', 'medium', 'high'] : ['auto'],
      supports_temperature: m !== 'chatgpt',
      supports_seed: m !== 'chatgpt',
    },
  }));
  return [
    {
      key: status.provider_key || 'gemini',
      label: status.provider_key || 'Default Provider',
      protocol_summary: '',
      enabled: Boolean(status.tryon_enabled),
      configured: Boolean(status.configured),
      is_default: true,
      default_model_id: models[0]?.id || 'flash',
      models,
    },
  ];
}

function buildDynamicParamViews(
  specs: VideoParamSpec[],
  values: Record<string, unknown>,
): DynamicParamView[] {
  return specs
    .filter((spec) => spec.type !== 'image' && spec.type !== 'images')
    .map((spec) => {
      const isSelect = Boolean((spec.options && spec.options.length > 0) || spec.type === 'boolean');
      const rawOptions: Array<string | number | boolean> = spec.options?.length
        ? spec.options
        : spec.type === 'boolean'
          ? [true, false]
          : [];
      const displayOptions = isSelect
        ? [t('tryon.garmentAuto'), ...rawOptions.map((o) => String(o))]
        : [];
      const currentVal = values[spec.name];
      let selectedIndex = 0;
      if (isSelect && currentVal !== undefined && currentVal !== '') {
        const idx = rawOptions.findIndex((o) => o === currentVal);
        if (idx >= 0) selectedIndex = idx + 1;
      }
      const valueStr = currentVal === undefined || currentVal === null ? '' : String(currentVal);
      return {
        name: spec.name,
        type: spec.type,
        required: Boolean(spec.required),
        isSelect,
        isTextarea: spec.type === 'text' || spec.name === 'prompt',
        isNumber: spec.type === 'integer' || spec.type === 'number',
        displayOptions,
        rawOptions,
        selectedIndex,
        valueStr,
        placeholder: spec.description || spec.label || spec.name,
      };
    });
}

function buildTexts() {
  return {
    modeImage: t('tryon.modeImage'),
    modeVideo: t('tryon.modeVideo'),
    statusConnected: t('tryon.statusConnected'),
    statusUnavailable: t('tryon.statusUnavailable'),
    modelCardTitle: t('tryon.modelCardTitle'),
    modelUpload: t('tryon.modelUpload'),
    modelSample: t('tryon.modelSample'),
    modelEmpty: t('tryon.modelEmpty'),
    garmentCardTitle: t('tryon.garmentCardTitle'),
    garmentUpload: t('tryon.garmentUpload'),
    garmentCatalog: t('tryon.garmentCatalog'),
    garmentEmpty: t('tryon.garmentEmpty'),
    controlsTitle: t('tryon.controlsTitle'),
    providerLabel: t('tryon.providerLabel'),
    modelLabel: t('tryon.modelLabel'),
    totokensProfileLabel: t('tryon.totokensProfileLabel'),
    freedomLabel: t('tryon.freedomLabel'),
    freedomHint: t('tryon.freedomHint'),
    advancedToggle: t('tryon.advancedToggle'),
    aspectRatioLabel: t('tryon.aspectRatioLabel'),
    imageSizeLabel: t('tryon.imageSizeLabel'),
    qualityLabel: t('tryon.qualityLabel'),
    garmentTypeLabel: t('tryon.garmentTypeLabel'),
    promptModeLabel: t('tryon.promptModeLabel'),
    promptAppend: t('tryon.promptAppend'),
    promptReplace: t('tryon.promptReplace'),
    customPromptLabel: t('tryon.customPromptLabel'),
    customPromptPlaceholder: t('tryon.customPromptPlaceholder'),
    submitBtn: t('tryon.submitBtn'),
    submitting: t('tryon.submitting'),
    resultTitle: t('tryon.resultTitle'),
    viewResult: t('tryon.viewResult'),
    viewModel: t('tryon.viewModel'),
    viewGarment: t('tryon.viewGarment'),
    saveAlbum: t('tryon.saveAlbum'),
    regenerate: t('tryon.regenerate'),
    toVideoBtn: t('tryon.toVideoBtn'),
    pickCatalogTitle: t('tryon.pickCatalogTitle'),
    pickSampleTitle: t('tryon.pickSampleTitle'),
    logsTitle: t('tryon.logsTitle'),
    searchPlaceholder: t('catalog.searchPlaceholder'),
    search: t('common.search'),
    close: t('common.close'),
    loading: t('common.loading'),
    videoNotConfigured: t('tryon.videoNotConfigured'),
    videoSandbox: t('tryon.videoSandbox'),
    videoSourceTitle: t('tryon.videoSourceTitle'),
    videoUseLatestTryon: t('tryon.videoUseLatestTryon'),
    videoUploadSource: t('tryon.videoUploadSource'),
    videoSourcePlaceholder: t('tryon.videoSourcePlaceholder'),
    videoSourceReady: t('tryon.videoSourceReady'),
    videoModelTitle: t('tryon.videoModelTitle'),
    videoModelLabel: t('tryon.videoModelLabel'),
    videoProviderLabel: t('tryon.videoProviderLabel'),
    videoPresetTurn: t('tryon.videoPresetTurn'),
    videoPresetWalk: t('tryon.videoPresetWalk'),
    videoPresetDetail: t('tryon.videoPresetDetail'),
    videoPresetStudio: t('tryon.videoPresetStudio'),
    videoParamsTitle: t('tryon.videoParamsTitle'),
    videoQuoteBtn: t('tryon.videoQuoteBtn'),
    videoSubmitBtn: t('tryon.videoSubmitBtn'),
    videoCancelBtn: t('tryon.videoCancelBtn'),
    videoQuotePending: t('tryon.videoQuotePending'),
    videoStatusTitle: t('tryon.videoStatusTitle'),
    videoSaveAlbum: t('tryon.videoSaveAlbum'),
    videoHistoryTitle: t('tryon.videoHistoryTitle'),
  };
}

function saveLocalPhotoToAlbum(filePath: string): void {
  wx.saveImageToPhotosAlbum({
    filePath,
    success() {
      wx.showToast({ title: t('common.savedToAlbum'), icon: 'success' });
    },
    fail() {
      wx.showModal({
        title: t('common.albumDenied'),
        showCancel: false,
        confirmText: t('common.confirm'),
      });
    },
  });
}

function saveLocalVideoToAlbum(filePath: string): void {
  wx.saveVideoToPhotosAlbum({
    filePath,
    success() {
      wx.showToast({ title: t('common.savedToAlbum'), icon: 'success' });
    },
    fail() {
      wx.showModal({
        title: t('common.albumDenied'),
        showCancel: false,
        confirmText: t('common.confirm'),
      });
    },
  });
}

Page({
  data: {
    locale: getLocale(),
    mode: 'image' as 'image' | 'video',
    texts: buildTexts(),

    // Try-on status & controls
    runtimeStatus: null as RuntimeStatusResponse | null,
    rateSummary: '',
    providers: [] as TryOnProviderCatalog[],
    providerNames: [] as string[],
    providerIndex: 0,
    models: [] as TryOnModelEntry[],
    modelNames: [] as string[],
    modelIndex: 0,
    totokensProfileLabels: [] as string[],
    totokensProfileIndex: 0,
    freedom: 5,
    advancedOpen: false,
    aspectRatioOptions: ['auto', '3:4', '4:5', '9:16', '1:1', '16:9'],
    aspectRatioIndex: 0,
    imageSizeOptions: ['auto', '1K', '2K', '4K'],
    imageSizeIndex: 0,
    supportsImageSize: true,
    qualityOptions: ['auto'],
    qualityIndex: 0,
    supportsQuality: false,
    garmentTypeLabels: TRYON_GARMENT_TYPES.map((g) => t(g.labelKey)),
    garmentTypeIndex: 0,
    promptMode: 'append' as 'append' | 'replace',
    customPrompt: '',

    // Try-on slots & handoff
    handoffTitle: '',
    handoffMeta: '',
    modelFilename: '',
    modelCloudUrl: '',
    modelPreview: '',
    garmentFilename: '',
    garmentCloudUrl: '',
    garmentPreview: '',
    importingModel: false,
    importingGarment: false,

    // Try-on execution
    submittingTryon: false,
    tryonError: '',
    activeTaskId: '',
    taskStatus: '',
    taskProgress: 0,
    taskMessage: '',
    taskLogs: [] as string[],
    resultRelativePath: '',
    resultDisplayUrl: '',
    resultViewMode: 'result' as 'result' | 'model' | 'garment',

    // Pickers
    sampleModalOpen: false,
    sampleItems: [] as Array<{ id: string; name: string; gender: 'male' | 'female'; thumbUrl: string }>,
    catalogModalOpen: false,
    catalogQuery: '',
    catalogLoading: false,
    catalogItems: [] as Array<ProductCatalogItem & { thumbUrl: string }>,

    // Video studio state
    videoLoaded: false,
    videoConfig: null as VideoConfigResponse | null,
    videoModels: [] as VideoModelItem[],
    videoModelLabels: [] as string[],
    videoModelIndex: 0,
    videoProviderList: [] as string[],
    videoProviderIndex: 0,
    videoDynamicSpecs: [] as VideoParamSpec[],
    videoValues: {} as Record<string, unknown>,
    videoParamViews: [] as DynamicParamView[],
    videoSourceInput: '',
    videoSourcePreview: '',
    videoQuoteText: '',
    videoBusy: false,
    videoError: '',
    activeVideoTask: null as VideoTaskView | null,
    videoHistory: [] as VideoTaskView[],
  },

  _unsubLocale: undefined as undefined | (() => void),
  _tryonPollTimer: 0 as number,
  _videoPollTimer: 0 as number,

  onLoad() {
    this._unsubLocale = subscribeLocale((nextLocale) => {
      this.setData({
        locale: nextLocale,
        texts: buildTexts(),
        garmentTypeLabels: TRYON_GARMENT_TYPES.map((g) => t(g.labelKey)),
      });
    });
  },

  onHide() {
    this.clearTimers();
  },

  onUnload() {
    this.clearTimers();
    if (this._unsubLocale) this._unsubLocale();
  },

  onShow() {
    const tabBar = typeof this.getTabBar === 'function' ? (this.getTabBar() as unknown as TabBarInstance | null) : null;
    if (tabBar && typeof tabBar.syncTabState === 'function') {
      tabBar.syncTabState(2);
    }
    wx.setNavigationBarTitle({ title: t('tabs.tryon') });
    this.setData({
      locale: getLocale(),
      texts: buildTexts(),
      garmentTypeLabels: TRYON_GARMENT_TYPES.map((g) => t(g.labelKey)),
    });
    void this.loadRuntime();
    void this.handlePendingHandoff();
    if (this.data.mode === 'video' && !this.data.videoLoaded) {
      void this.loadVideoStudio();
    }
  },

  clearTimers() {
    if (this._tryonPollTimer) {
      clearTimeout(this._tryonPollTimer);
      this._tryonPollTimer = 0;
    }
    if (this._videoPollTimer) {
      clearTimeout(this._videoPollTimer);
      this._videoPollTimer = 0;
    }
  },

  onLocaleChange() {
    this.setData({
      locale: getLocale(),
      texts: buildTexts(),
      garmentTypeLabels: TRYON_GARMENT_TYPES.map((g) => t(g.labelKey)),
    });
  },

  onSwitchMode(e: WechatMiniprogram.TouchEvent) {
    const mode = e.currentTarget.dataset.mode as 'image' | 'video';
    if (!mode || mode === this.data.mode) return;
    this.setData({ mode });
    if (mode === 'video') {
      void this.loadVideoStudio();
    }
  },

  async loadRuntime() {
    try {
      const [status, rate] = await Promise.all([
        getRuntimeStatus(),
        getRateStatus().catch(() => ({} as Record<string, unknown>)),
      ]);
      const providers = buildProvidersFromStatus(status);
      const defaultIdx = Math.max(0, providers.findIndex((p) => p.is_default));
      const rateLimitText = rate && typeof rate.remaining_today === 'number'
        ? `Quota: ${rate.remaining_today}`
        : '';
      this.setData({
        runtimeStatus: status,
        rateSummary: rateLimitText,
        providers,
        providerNames: providers.map((p) => p.label || p.key),
      });
      this.applyProviderSelection(defaultIdx);
    } catch {
      this.setData({
        runtimeStatus: {
          tryon_enabled: false,
          configured: false,
          available_models: [],
          config_source: 'unreachable',
        },
      });
    }
  },

  applyProviderSelection(providerIndex: number) {
    const provider = this.data.providers[providerIndex];
    if (!provider) return;
    const models = provider.models || [];
    const modelIndex = Math.max(0, models.findIndex((m) => m.is_default || m.id === provider.default_model_id));
    const profiles = provider.totokens_profiles || [];
    const profileLabels = profiles.length > 0
      ? [t('tryon.garmentAuto'), ...profiles.map((p) => p.label || p.id)]
      : [];
    this.setData({
      providerIndex,
      models,
      modelNames: models.map((m) => m.badge ? `${m.label} [${m.badge}]` : m.label),
      totokensProfileLabels: profileLabels,
      totokensProfileIndex: 0,
    });
    this.applyModelSelection(modelIndex);
  },

  applyModelSelection(modelIndex: number) {
    const model = this.data.models[modelIndex];
    if (!model) return;
    const caps = model.capabilities;
    this.setData({
      modelIndex,
      aspectRatioOptions: caps?.aspect_ratio_options?.length ? caps.aspect_ratio_options : ['auto', '3:4', '1:1'],
      aspectRatioIndex: 0,
      imageSizeOptions: caps?.image_size_options?.length ? caps.image_size_options : ['auto', '1K', '2K'],
      imageSizeIndex: 0,
      supportsImageSize: caps?.supports_image_size ?? true,
      qualityOptions: caps?.quality_options?.length ? caps.quality_options : ['auto'],
      qualityIndex: 0,
      supportsQuality: caps?.supports_quality ?? false,
    });
  },

  async handlePendingHandoff() {
    const handoff = consumePendingTryOnHandoff();
    if (!handoff) {
      // Also prefill model photo from global userPhoto if try-on model slot is empty
      const snap = getState();
      if (!this.data.modelFilename && snap.userPhoto.localPath) {
        await this.uploadLocalModel(snap.userPhoto.localPath);
      }
      return;
    }

    const mainBase = getEndpointConfig().mainApiBaseUrl;
    const metaParts = [
      handoff.productPrice !== undefined ? `¥${handoff.productPrice}` : '',
      handoff.styleType || '',
      handoff.colorFamily || '',
      handoff.sizeHint ? `${t('recommend.resolvedSize')}: ${handoff.sizeHint}` : '',
    ].filter(Boolean);
    const fullGarmentUrl = buildMainMediaUrl(handoff.garmentImageUrl, mainBase);

    this.setData({
      mode: 'image',
      handoffTitle: handoff.productTitle,
      handoffMeta: metaParts.join(' · '),
      garmentPreview: fullGarmentUrl,
      importingGarment: true,
      tryonError: '',
    });

    const tasks: Array<Promise<void>> = [];

    if (fullGarmentUrl) {
      tasks.push(
        intakeOrUploadImage(fullGarmentUrl, 'garment')
          .then((res) => {
            const proxy = res.url || res.cloud_url || '';
            this.setData({
              garmentFilename: res.filename,
              garmentCloudUrl: proxy,
              garmentPreview: resolveTryOnAssetUrl(proxy) || fullGarmentUrl,
            });
          })
          .catch((err) => {
            this.setData({
              tryonError: err instanceof Error ? err.message : t('common.networkError'),
            });
          })
          .finally(() => {
            this.setData({ importingGarment: false });
          }),
      );
    } else {
      this.setData({ importingGarment: false });
    }

    if (handoff.userPhotoLocalPath) {
      tasks.push(this.uploadLocalModel(handoff.userPhotoLocalPath));
    } else if (handoff.userPhotoRemoteUrl) {
      const remoteModelUrl = buildMainMediaUrl(handoff.userPhotoRemoteUrl, mainBase);
      this.setData({ importingModel: true, modelPreview: remoteModelUrl });
      tasks.push(
        intakeOrUploadImage(remoteModelUrl, 'model')
          .then((res) => {
            const proxy = res.url || res.cloud_url || '';
            this.setData({
              modelFilename: res.filename,
              modelCloudUrl: proxy,
              modelPreview: resolveTryOnAssetUrl(proxy) || remoteModelUrl,
            });
          })
          .catch(() => {
            // Non-blocking: user can still choose photo manually
          })
          .finally(() => {
            this.setData({ importingModel: false });
          }),
      );
    }

    await Promise.all(tasks);
  },

  async uploadLocalModel(filePath: string) {
    this.setData({
      importingModel: true,
      modelPreview: filePath,
      tryonError: '',
    });
    try {
      const res = await uploadModelPhoto(filePath);
      this.setData({
        modelFilename: res.filename,
        modelCloudUrl: res.url || res.cloud_url || '',
        modelPreview: filePath,
      });
    } catch (err) {
      this.setData({
        tryonError: err instanceof Error ? err.message : t('common.networkError'),
      });
    } finally {
      this.setData({ importingModel: false });
    }
  },

  onChooseLocalModel() {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const file = res.tempFiles && res.tempFiles[0];
        if (file?.tempFilePath) {
          void this.uploadLocalModel(file.tempFilePath);
        }
      },
    });
  },

  onOpenSampleModal() {
    const mainBase = getEndpointConfig().mainApiBaseUrl;
    this.setData({
      sampleModalOpen: true,
      sampleItems: SAMPLE_MODELS.map((m) => ({
        id: m.id,
        name: m.name,
        gender: m.gender,
        thumbUrl: buildSampleModelUrl(m.gender, m.filename, mainBase),
      })),
    });
  },

  onCloseSampleModal() {
    this.setData({ sampleModalOpen: false });
  },

  async onPickSampleModel(e: WechatMiniprogram.TouchEvent) {
    const idx = Number(e.currentTarget.dataset.index);
    const item = this.data.sampleItems[idx];
    if (!item) return;
    this.setData({ sampleModalOpen: false, importingModel: true });
    try {
      const tempPath = await downloadTempFile(item.thumbUrl);
      await this.uploadLocalModel(tempPath);
    } catch (err) {
      this.setData({
        importingModel: false,
        tryonError: err instanceof Error ? err.message : t('common.networkError'),
      });
    }
  },

  onChooseLocalGarment() {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      success: async (res) => {
        const file = res.tempFiles && res.tempFiles[0];
        if (!file?.tempFilePath) return;
        this.setData({
          importingGarment: true,
          garmentPreview: file.tempFilePath,
          handoffTitle: '',
          handoffMeta: '',
          tryonError: '',
        });
        try {
          const uploaded = await uploadGarmentPhoto(file.tempFilePath);
          this.setData({
            garmentFilename: uploaded.filename,
            garmentCloudUrl: uploaded.url || uploaded.cloud_url || '',
            garmentPreview: file.tempFilePath,
          });
        } catch (err) {
          this.setData({
            tryonError: err instanceof Error ? err.message : t('common.networkError'),
          });
        } finally {
          this.setData({ importingGarment: false });
        }
      },
    });
  },

  onOpenCatalogModal() {
    this.setData({ catalogModalOpen: true });
    if (this.data.catalogItems.length === 0) {
      void this.searchCatalogPicker();
    }
  },

  onCloseCatalogModal() {
    this.setData({ catalogModalOpen: false });
  },

  onCatalogQueryInput(e: WechatMiniprogram.Input) {
    this.setData({ catalogQuery: String(e.detail.value || '') });
  },

  async searchCatalogPicker() {
    this.setData({ catalogLoading: true });
    try {
      const res = await getWorkbenchProducts({
        query: this.data.catalogQuery.trim() || undefined,
        limit: 20,
      });
      const mainBase = getEndpointConfig().mainApiBaseUrl;
      this.setData({
        catalogItems: (res.items || []).map((item) => ({
          ...item,
          thumbUrl: buildMainMediaUrl(item.canonical?.image_url || item.image_url, mainBase),
        })),
      });
    } catch (err) {
      wx.showToast({
        title: (err instanceof Error ? err.message : t('common.networkError')).slice(0, 28),
        icon: 'none',
      });
    } finally {
      this.setData({ catalogLoading: false });
    }
  },

  onSearchCatalogConfirm() {
    void this.searchCatalogPicker();
  },

  async onPickCatalogGarment(e: WechatMiniprogram.TouchEvent) {
    const idx = Number(e.currentTarget.dataset.index);
    const item = this.data.catalogItems[idx];
    if (!item) return;
    this.setData({
      catalogModalOpen: false,
      importingGarment: true,
      handoffTitle: item.display?.title || item.title,
      handoffMeta: `¥${item.price} · ${item.display?.styleType || item.style_type || ''}`,
      garmentPreview: item.thumbUrl,
      tryonError: '',
    });
    try {
      const imported = await intakeOrUploadImage(item.thumbUrl, 'garment');
      const proxy = imported.url || imported.cloud_url || '';
      this.setData({
        garmentFilename: imported.filename,
        garmentCloudUrl: proxy,
        garmentPreview: resolveTryOnAssetUrl(proxy) || item.thumbUrl,
      });
    } catch (err) {
      this.setData({
        tryonError: err instanceof Error ? err.message : t('common.networkError'),
      });
    } finally {
      this.setData({ importingGarment: false });
    }
  },

  onPickProvider(e: WechatMiniprogram.PickerChange) {
    this.applyProviderSelection(Number(e.detail.value) || 0);
  },

  onPickModel(e: WechatMiniprogram.PickerChange) {
    this.applyModelSelection(Number(e.detail.value) || 0);
  },

  onPickTotokensProfile(e: WechatMiniprogram.PickerChange) {
    this.setData({ totokensProfileIndex: Number(e.detail.value) || 0 });
  },

  onFreedomChange(e: WechatMiniprogram.SliderChange) {
    this.setData({ freedom: Number(e.detail.value) });
  },

  onToggleAdvanced() {
    this.setData({ advancedOpen: !this.data.advancedOpen });
  },

  onPickAspectRatio(e: WechatMiniprogram.PickerChange) {
    this.setData({ aspectRatioIndex: Number(e.detail.value) || 0 });
  },

  onPickImageSize(e: WechatMiniprogram.PickerChange) {
    this.setData({ imageSizeIndex: Number(e.detail.value) || 0 });
  },

  onPickQuality(e: WechatMiniprogram.PickerChange) {
    this.setData({ qualityIndex: Number(e.detail.value) || 0 });
  },

  onPickGarmentType(e: WechatMiniprogram.PickerChange) {
    this.setData({ garmentTypeIndex: Number(e.detail.value) || 0 });
  },

  onSelectPromptMode(e: WechatMiniprogram.TouchEvent) {
    const promptMode = e.currentTarget.dataset.mode as 'append' | 'replace';
    if (promptMode) this.setData({ promptMode });
  },

  onCustomPromptInput(e: WechatMiniprogram.TextareaInput) {
    this.setData({ customPrompt: String(e.detail.value || '') });
  },

  async onSubmitTryOn() {
    if (!this.data.modelFilename || !this.data.garmentFilename) {
      const msg = t('tryon.needBothImages');
      this.setData({ tryonError: msg });
      wx.showToast({ title: msg, icon: 'none' });
      return;
    }

    this.clearTimers();
    const provider = this.data.providers[this.data.providerIndex];
    const modelEntry = this.data.models[this.data.modelIndex];
    const profiles = provider?.totokens_profiles || [];
    const selectedProfile = this.data.totokensProfileIndex > 0
      ? profiles[this.data.totokensProfileIndex - 1]?.id
      : undefined;

    const aspect = this.data.aspectRatioOptions[this.data.aspectRatioIndex];
    const imgSize = this.data.imageSizeOptions[this.data.imageSizeIndex];
    const quality = this.data.qualityOptions[this.data.qualityIndex];
    const garmentType = TRYON_GARMENT_TYPES[this.data.garmentTypeIndex]?.value || '';

    this.setData({
      submittingTryon: true,
      tryonError: '',
      taskStatus: 'submitting',
      taskProgress: 8,
      taskMessage: t('tryon.submitting'),
      taskLogs: [],
      resultDisplayUrl: '',
      resultRelativePath: '',
      resultViewMode: 'result',
    });

    try {
      const submitted = await submitTryOnTask({
        target_image: this.data.modelFilename,
        reference_image: this.data.garmentFilename,
        model: modelEntry?.preset_key || 'flash',
        provider: provider?.key,
        model_id: modelEntry?.id,
        totokens_profile: selectedProfile,
        freedom: this.data.freedom,
        aspect_ratio: aspect && aspect !== 'auto' ? aspect : undefined,
        image_size: this.data.supportsImageSize && imgSize && imgSize !== 'auto' ? imgSize : undefined,
        quality: this.data.supportsQuality && quality && quality !== 'auto' ? quality : undefined,
        garment_type: garmentType || undefined,
        custom_prompt: this.data.customPrompt.trim() || undefined,
        prompt_mode: this.data.promptMode,
        target_image_cloud_url: this.data.modelCloudUrl || undefined,
        reference_image_cloud_url: this.data.garmentCloudUrl || undefined,
        idempotency_key: generateClientUuid('tryon'),
      });
      this.setData({
        activeTaskId: submitted.task_id,
        taskStatus: submitted.status,
      });
      this.scheduleTryOnPoll(submitted.task_id);
    } catch (err) {
      this.setData({
        submittingTryon: false,
        tryonError: err instanceof Error ? err.message : t('common.unknownError'),
      });
    }
  },

  scheduleTryOnPoll(taskId: string) {
    this._tryonPollTimer = setTimeout(async () => {
      try {
        const task: TryOnTaskResponse = await getTryOnTask(taskId);
        const logs = Array.isArray(task.logs) ? task.logs.slice(-12) : [];
        this.setData({
          taskStatus: task.status,
          taskProgress: Math.max(0, Math.min(100, task.progress || 0)),
          taskMessage: task.message || task.status,
          taskLogs: logs,
        });
        if (task.status === 'completed') {
          const rel = task.result_url || task.result_cloud_url || task.result_display_url || '';
          const display = (rel ? resolveTryOnAssetUrl(rel) : '') || task.result_data_url || '';
          setLastTryOnResult({ relativePath: rel, displayUrl: display });
          this.setData({
            submittingTryon: false,
            resultRelativePath: rel,
            resultDisplayUrl: display,
            resultViewMode: 'result',
          });
          return;
        }
        if (task.status === 'failed' || task.status === 'unknown') {
          this.setData({
            submittingTryon: false,
            tryonError: task.error || task.error_detail || task.message || t('common.unknownError'),
          });
          return;
        }
        this.scheduleTryOnPoll(taskId);
      } catch (err) {
        this.setData({
          submittingTryon: false,
          tryonError: err instanceof Error ? err.message : t('common.networkError'),
        });
      }
    }, 2500) as unknown as number;
  },

  onSelectResultView(e: WechatMiniprogram.TouchEvent) {
    const view = e.currentTarget.dataset.view as 'result' | 'model' | 'garment';
    if (view) this.setData({ resultViewMode: view });
  },

  onPreviewResult() {
    const url = this.data.resultViewMode === 'model'
      ? this.data.modelPreview
      : this.data.resultViewMode === 'garment'
        ? this.data.garmentPreview
        : this.data.resultDisplayUrl;
    if (!url) return;
    wx.previewImage({
      current: url,
      urls: [this.data.resultDisplayUrl, this.data.modelPreview, this.data.garmentPreview].filter(Boolean),
    });
  },

  async onSaveTryOnAlbum() {
    const url = this.data.resultDisplayUrl;
    if (!url) return;
    wx.showLoading({ title: t('common.loading') });
    try {
      let localPath = '';
      if (url.startsWith('data:image/')) {
        const commaIdx = url.indexOf(',');
        const b64 = commaIdx >= 0 ? url.slice(commaIdx + 1) : '';
        const target = `${wx.env.USER_DATA_PATH}/tryon_${Date.now()}.png`;
        wx.getFileSystemManager().writeFileSync(target, b64, 'base64');
        localPath = target;
      } else {
        localPath = await downloadTempFile(url, workbenchHeaders());
      }
      wx.hideLoading();
      saveLocalPhotoToAlbum(localPath);
    } catch (err) {
      wx.hideLoading();
      wx.showToast({
        title: (err instanceof Error ? err.message : t('common.networkError')).slice(0, 28),
        icon: 'none',
      });
    }
  },

  onAnimateResultToVideo() {
    const rel = this.data.resultRelativePath;
    this.setData({ mode: 'video' });
    void this.loadVideoStudio(rel || undefined);
  },

  // ---------------- Video Studio ----------------

  async loadVideoStudio(bindRelPath?: string) {
    this.setData({ videoError: '' });
    try {
      const [cfg, modelsRes, historyRes] = await Promise.all([
        getVideoConfig(),
        getVideoModels().catch(() => ({ data: [] as VideoModelItem[], project: false })),
        listVideoTasks().catch(() => ({ data: [] as VideoTaskResponse[] })),
      ]);
      const models = modelsRes.data || [];
      const defaultModel = pickDefaultVideoModel(models);
      const defaultIdx = defaultModel ? Math.max(0, models.findIndex((m) => m.slug === defaultModel.slug)) : 0;
      const historyViews: VideoTaskView[] = (historyRes.data || []).map((task) => ({
        ...task,
        playbackUrl: resolveVideoDownloadUrl(task),
        createdAtText: formatTs(task.created_at),
      }));

      this.setData({
        videoLoaded: true,
        videoConfig: cfg,
        videoModels: models,
        videoModelLabels: models.map((m) => m.name || m.slug),
        videoHistory: historyViews,
      });

      if (models.length > 0) {
        this.applyVideoModelSelection(defaultIdx);
      }

      const relToBind = bindRelPath || getState().lastTryOnResult?.relativePath || this.data.resultRelativePath;
      if (relToBind) {
        this.bindVideoSource(relToBind);
      }
    } catch (err) {
      this.setData({
        videoLoaded: true,
        videoError: err instanceof Error ? err.message : t('common.networkError'),
      });
    }
  },

  applyVideoModelSelection(modelIdx: number) {
    const model = this.data.videoModels[modelIdx];
    if (!model) return;
    const providerList = (model.providers || []).map((p) => p.provider);
    const selectedProvider = providerList[0] || model.provider || '';
    const specs = parametersFor(model, providerList.length ? selectedProvider : '');
    const nextValues = { ...defaultsFor(specs) };
    if (this.data.videoSourceInput) {
      try {
        Object.assign(nextValues, bindSourceImage(specs, nextValues, this.data.videoSourceInput));
      } catch {
        // Model may not accept image input
      }
    }
    this.setData({
      videoModelIndex: modelIdx,
      videoProviderList: providerList,
      videoProviderIndex: 0,
      videoDynamicSpecs: specs,
      videoValues: nextValues,
      videoParamViews: buildDynamicParamViews(specs, nextValues),
      videoQuoteText: '',
    });
  },

  onPickVideoModel(e: WechatMiniprogram.PickerChange) {
    this.applyVideoModelSelection(Number(e.detail.value) || 0);
  },

  onPickVideoProvider(e: WechatMiniprogram.PickerChange) {
    const idx = Number(e.detail.value) || 0;
    const model = this.data.videoModels[this.data.videoModelIndex];
    const provider = this.data.videoProviderList[idx] || '';
    if (!model) return;
    const specs = parametersFor(model, provider);
    const nextValues = { ...defaultsFor(specs) };
    if (this.data.videoSourceInput) {
      try {
        Object.assign(nextValues, bindSourceImage(specs, nextValues, this.data.videoSourceInput));
      } catch {
        // Ignore if not supported
      }
    }
    this.setData({
      videoProviderIndex: idx,
      videoDynamicSpecs: specs,
      videoValues: nextValues,
      videoParamViews: buildDynamicParamViews(specs, nextValues),
      videoQuoteText: '',
    });
  },

  bindVideoSource(sourceUrlOrPath: string) {
    const clean = String(sourceUrlOrPath || '').trim();
    const preview = resolveTryOnAssetUrl(clean) || clean;
    let nextValues = { ...this.data.videoValues };
    if (clean && this.data.videoDynamicSpecs.length > 0) {
      try {
        nextValues = bindSourceImage(this.data.videoDynamicSpecs, nextValues, clean);
      } catch {
        // Ignore if current model has no image param
      }
    }
    this.setData({
      videoSourceInput: clean,
      videoSourcePreview: preview,
      videoValues: nextValues,
      videoParamViews: buildDynamicParamViews(this.data.videoDynamicSpecs, nextValues),
      videoQuoteText: '',
    });

    if (preview) {
      wx.getImageInfo({
        src: preview,
        success: (info) => {
          if (info.width > 0 && info.height > 0 && this.data.videoDynamicSpecs.length > 0) {
            const adapted = adaptiveAspectRatio(this.data.videoDynamicSpecs, info.width, info.height);
            if (adapted !== undefined) {
              const updated = { ...this.data.videoValues, aspect_ratio: adapted };
              this.setData({
                videoValues: updated,
                videoParamViews: buildDynamicParamViews(this.data.videoDynamicSpecs, updated),
              });
            }
          }
        },
      });
    }
  },

  onUseLatestTryOnForVideo() {
    const rel = this.data.resultRelativePath || getState().lastTryOnResult?.relativePath;
    if (!rel) {
      wx.showToast({ title: t('tryon.videoNoSource'), icon: 'none' });
      return;
    }
    this.bindVideoSource(rel);
  },

  onUploadLocalVideoSource() {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      success: async (res) => {
        const file = res.tempFiles && res.tempFiles[0];
        if (!file?.tempFilePath) return;
        wx.showLoading({ title: t('common.loading') });
        try {
          const uploaded = await uploadModelPhoto(file.tempFilePath);
          const url = uploaded.url || uploaded.cloud_url || '';
          if (url) {
            this.bindVideoSource(url);
          }
        } catch (err) {
          this.setData({
            videoError: err instanceof Error ? err.message : t('common.networkError'),
          });
        } finally {
          wx.hideLoading();
        }
      },
    });
  },

  onInputVideoSource(e: WechatMiniprogram.Input) {
    this.bindVideoSource(String(e.detail.value || ''));
  },

  onApplyVideoPreset(e: WechatMiniprogram.TouchEvent) {
    const preset = e.currentTarget.dataset.preset as 'turn' | 'walk' | 'detail' | 'studio';
    if (!preset) return;
    const text = VIDEO_PRESET_PROMPTS[preset][getLocale()];
    const nextValues = { ...this.data.videoValues, prompt: text };
    this.setData({
      videoValues: nextValues,
      videoParamViews: buildDynamicParamViews(this.data.videoDynamicSpecs, nextValues),
      videoQuoteText: '',
    });
  },

  onVideoParamInput(e: WechatMiniprogram.Input | WechatMiniprogram.TextareaInput) {
    const name = String(e.currentTarget.dataset.name || '');
    if (!name) return;
    const nextValues = { ...this.data.videoValues, [name]: String(e.detail.value || '') };
    this.setData({
      videoValues: nextValues,
      videoParamViews: buildDynamicParamViews(this.data.videoDynamicSpecs, nextValues),
      videoQuoteText: '',
    });
  },

  onVideoParamSelect(e: WechatMiniprogram.PickerChange) {
    const name = String(e.currentTarget.dataset.name || '');
    const pickIdx = Number(e.detail.value) || 0;
    const view = this.data.videoParamViews.find((v) => v.name === name);
    if (!view) return;
    const val = pickIdx === 0 ? undefined : view.rawOptions[pickIdx - 1];
    const nextValues = { ...this.data.videoValues, [name]: val };
    this.setData({
      videoValues: nextValues,
      videoParamViews: buildDynamicParamViews(this.data.videoDynamicSpecs, nextValues),
      videoQuoteText: '',
    });
  },

  buildVideoRequestPayload() {
    const model = this.data.videoModels[this.data.videoModelIndex];
    if (!model) {
      throw new Error(t('tryon.videoModelLabel'));
    }
    const provider = this.data.videoProviderList[this.data.videoProviderIndex] || model.provider || '';
    const input = collectInput(this.data.videoDynamicSpecs, this.data.videoValues);
    return { model: model.slug, provider, input };
  },

  async onQuoteVideo() {
    this.setData({ videoBusy: true, videoError: '' });
    try {
      const payload = this.buildVideoRequestPayload();
      const q = await quoteVideo(payload);
      const priceLabel = q.price_usd !== undefined
        ? `$${q.price_usd}`
        : q.credits !== undefined
          ? `${q.credits} credits`
          : JSON.stringify(q);
      this.setData({
        videoQuoteText: t('tryon.videoQuoteReady', { price: priceLabel }),
      });
    } catch (err) {
      this.setData({
        videoError: err instanceof Error ? err.message : t('common.unknownError'),
      });
    } finally {
      this.setData({ videoBusy: false });
    }
  },

  async onSubmitVideo() {
    if (!this.data.videoSourceInput) {
      this.setData({ videoError: t('tryon.videoNoSource') });
      return;
    }
    if (this._videoPollTimer) {
      clearTimeout(this._videoPollTimer);
      this._videoPollTimer = 0;
    }
    this.setData({ videoBusy: true, videoError: '' });
    try {
      const payload = this.buildVideoRequestPayload();
      const task = await submitVideoTask({
        ...payload,
        idempotency_key: generateClientUuid('video'),
      });
      const taskView: VideoTaskView = {
        ...task,
        playbackUrl: resolveVideoDownloadUrl(task),
        createdAtText: formatTs(task.created_at),
      };
      this.setData({ activeVideoTask: taskView });
      if (['submitting', 'queued', 'processing'].includes(task.status)) {
        this.scheduleVideoPoll(task.id);
      } else {
        this.setData({ videoBusy: false });
      }
    } catch (err) {
      this.setData({
        videoBusy: false,
        videoError: err instanceof Error ? err.message : t('common.unknownError'),
      });
    }
  },

  scheduleVideoPoll(taskId: string) {
    const interval = this.data.videoConfig?.poll_interval_ms || 4000;
    this._videoPollTimer = setTimeout(async () => {
      try {
        const task = await pollVideoTask(taskId);
        const taskView: VideoTaskView = {
          ...task,
          playbackUrl: resolveVideoDownloadUrl(task),
          createdAtText: formatTs(task.created_at),
        };
        this.setData({ activeVideoTask: taskView });
        if (['queued', 'processing', 'submitting'].includes(task.status)) {
          this.scheduleVideoPoll(taskId);
          return;
        }
        this.setData({ videoBusy: false });
        if (task.error) {
          this.setData({ videoError: task.error });
        }
        const historyRes = await listVideoTasks().catch(() => ({ data: [] as VideoTaskResponse[] }));
        this.setData({
          videoHistory: (historyRes.data || []).map((row) => ({
            ...row,
            playbackUrl: resolveVideoDownloadUrl(row),
            createdAtText: formatTs(row.created_at),
          })),
        });
      } catch (err) {
        this.setData({
          videoBusy: false,
          videoError: err instanceof Error ? err.message : t('common.networkError'),
        });
      }
    }, interval) as unknown as number;
  },

  async onCancelVideo() {
    const active = this.data.activeVideoTask;
    if (!active) return;
    try {
      const updated = await cancelVideoTask(active.id);
      if (this._videoPollTimer) {
        clearTimeout(this._videoPollTimer);
        this._videoPollTimer = 0;
      }
      this.setData({
        videoBusy: false,
        activeVideoTask: {
          ...updated,
          playbackUrl: resolveVideoDownloadUrl(updated),
          createdAtText: formatTs(updated.created_at),
        },
      });
    } catch (err) {
      this.setData({
        videoError: err instanceof Error ? err.message : t('common.networkError'),
      });
    }
  },

  async onSaveVideoAlbum() {
    const task = this.data.activeVideoTask;
    if (!task || !task.playbackUrl) return;
    wx.showLoading({ title: t('common.loading') });
    try {
      const tempPath = await downloadTempFile(task.playbackUrl, workbenchHeaders(), 120000);
      wx.hideLoading();
      saveLocalVideoToAlbum(tempPath);
    } catch (err) {
      wx.hideLoading();
      wx.showToast({
        title: (err instanceof Error ? err.message : t('common.networkError')).slice(0, 28),
        icon: 'none',
      });
    }
  },

  onSelectHistoryVideo(e: WechatMiniprogram.TouchEvent) {
    const idx = Number(e.currentTarget.dataset.index);
    const task = this.data.videoHistory[idx];
    if (task) {
      this.setData({ activeVideoTask: task });
    }
  },
});
