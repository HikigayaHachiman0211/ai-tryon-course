(() => {
    'use strict';

    const state = {
        model: '',
        modelCloudUrl: '',
        garments: [],
        garmentCloudUrls: [],
        results: [],
        resultPreviews: [],
        selected: new Set(),
        modelType: 'flash',
        provider: 'gemini',
        totokensProfile: 'auto',
        modelId: 'gemini-3.1-flash-image-preview',
        useCustomModel: false,
        customModelId: '',
        detailOptions: {
            aspect_ratio: 'auto',
            image_size: 'auto',
            quality: 'auto',
            temperature: '',
            seed: '',
        },
        capabilities: null,
        step3PrefsTouched: false,
        running: false,
        abort: false,
        errors: [],
        rateStatus: null,
        minuteResetSec: null,
        dailyResetSec: null,
        errorAnalyzing: new Set(),
        recommendation: null,
        frontendConfig: null,
        trustedMessageOrigin: '',
        runtimeAvailable: false,
        runtimeStatus: null,
        intakeStatus: {},
        integrationAlert: null,
        feedback: null,
        taskToken: '',
        unloading: false,
    };
    const ACTIVE_TASK_STORAGE_KEY = 'tryon_active_task_v1';

    function generateIdempotencyKey() {
        if (window.crypto && typeof window.crypto.randomUUID === 'function') {
            return window.crypto.randomUUID();
        }
        return `idem-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    }

    function persistActiveTask(taskId, taskToken) {
        try {
            if (!taskId) {
                sessionStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                return;
            }
            sessionStorage.setItem(ACTIVE_TASK_STORAGE_KEY, JSON.stringify({ taskId, taskToken: taskToken || '' }));
        } catch (_) { }
    }

    function readActiveTask() {
        try {
            const raw = sessionStorage.getItem(ACTIVE_TASK_STORAGE_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch (_) {
            return null;
        }
    }

    const MODEL_LIMITS = {
        flash: { name: 'Gemini Flash Image', rpm: 100, tpm: 200000, rpd: 1000 },
        pro: { name: 'Gemini Pro Image', rpm: 20, tpm: 100000, rpd: 250 },
        chatgpt: { name: 'ChatGPT Image', rpm: 30, tpm: 120000, rpd: 300 },
    };

    const SAMPLE_MODELS = [
        { id: 'male-mannequin-1', name: '通用男模 1', gender: 'male', filename: 'mannequin-male-1.png' },
        { id: 'male-mannequin-2', name: '通用男模 2', gender: 'male', filename: 'mannequin-male-2.png' },
        { id: 'female-mannequin-1', name: '通用女模 1', gender: 'female', filename: 'mannequin-female-1.png' },
        { id: 'female-mannequin-2', name: '通用女模 2', gender: 'female', filename: 'mannequin-female-2.png' },
    ];

    const $ = id => document.getElementById(id);
    function uiText(key, params, fallback = '') {
        return window.WorkbenchI18n?.t(key, params) || fallback || key;
    }
    function _clearImgError(img) {
        if (!img) return;
        delete img.dataset.errorHandled;
        img.classList.remove('img-error');
        img.style.removeProperty('display');
        const ph = img.parentNode && img.nextElementSibling;
        if (ph && ph.classList.contains('img-error-placeholder')) ph.remove();
    }
    const el = {
        note: $('notification-container'),
        modelZone: $('drop-zone-target'),
        modelInput: $('file-target'),
        modelImg: $('target-cover-img'),
        modelPh: $('target-placeholder'),
        modelCtl: $('target-controls'),
        modelCnt: $('target-count'),
        modelContinue: $('btn-continue-upload'),
        modelPreview: $('btn-preview-all'),
        modelClear: $('btn-clear-target'),
        refZone: $('drop-zone-reference'),
        refInput: $('file-reference'),
        refImg: $('ref-cover-img'),
        refPh: $('ref-placeholder'),
        refCtl: $('ref-controls'),
        refCnt: $('ref-count'),
        refContinue: $('btn-continue-ref'),
        refPreview: $('btn-preview-ref'),
        refClear: $('btn-clear-reference'),
        genBtn: $('generate-btn'),
        genText: document.querySelector('#generate-btn .btn-text'),
        abortBtn: $('abort-btn'),
        status: $('status-container'),
        batchInfo: $('batch-progress-info'),
        batchText: $('batch-progress-text'),
        fill: $('progress-fill'),
        pct: $('progress-percentage'),
        msg: $('progress-message'),
        logBox: $('console-log'),
        log: $('log-content'),
        freedom: $('freedom-slider'),
        freedomVal: $('freedom-value'),
        freedomRnd: $('freedom-random'),
        providerSelect: $('tryon-provider-select'),
        totokensProfileField: $('tryon-totokens-profile-field'),
        totokensProfileSelect: $('tryon-totokens-profile-select'),
        totokensProfileHint: $('tryon-totokens-profile-hint'),
        modelSelect: $('tryon-model-select'),
        customModelToggle: $('tryon-custom-model-toggle'),
        customModelWrap: $('tryon-custom-model-wrap'),
        customModelInput: $('tryon-custom-model-input'),
        customModelHint: $('tryon-custom-model-hint'),
        modelMeta: $('tryon-model-meta'),
        refreshModelsBtn: $('tryon-refresh-models-btn'),
        resetParamsBtn: $('tryon-reset-params-btn'),
        aspectRatioSelect: $('tryon-aspect-ratio'),
        imageSizeField: $('tryon-image-size-field'),
        imageSizeSelect: $('tryon-image-size'),
        qualityField: $('tryon-quality-field'),
        qualitySelect: $('tryon-quality'),
        temperatureField: $('tryon-temperature-field'),
        temperatureSlider: $('tryon-temperature-slider'),
        temperatureInput: $('tryon-temperature'),
        temperatureVal: $('tryon-temperature-val'),
        temperatureClear: $('tryon-temperature-clear'),
        temperatureHint: $('tryon-temperature-hint'),
        seedField: $('tryon-seed-field'),
        seedInput: $('tryon-seed'),
        seedRandomBtn: $('tryon-seed-random-btn'),
        seedClear: $('tryon-seed-clear'),
        seedHint: $('tryon-seed-hint'),
        effectiveSummary: $('tryon-effective-summary'),
        parallelToggle: $('parallel-gen-toggle'),
        parallelConcurrency: $('parallel-concurrency'),
        parallelConcurrencySlider: $('parallel-concurrency-slider'),
        parallelConcurrencyRow: $('parallel-concurrency-row'),
        batchCount: $('batch-count'),
        minus: $('batch-minus'),
        plus: $('batch-plus'),
        resultPh: $('result-placeholder'),
        resultImg: $('result-img'),
        downOne: $('download-btn'),
        galleryWrap: $('batch-gallery'),
        gallery: $('batch-gallery-grid'),
        galleryCount: $('batch-result-count'),
        selAll: $('select-toggle-btn'),
        downSel: $('download-selected-btn'),
        downSelCount: $('selected-count-badge'),
        downEach: $('download-each-btn'),
        downAll: $('download-all-btn'),
        interval: $('download-interval'),
        intervalVal: $('download-interval-value'),
        footerModel: $('footer-model-name'),
        footerProvider: $('footer-provider-name'),
        promptModal: $('prompt-modal'),
        promptOpen: $('open-prompt-btn'),
        promptClose: $('close-modal-btn'),
        promptToggle: $('modal-prompt-toggle'),
        promptAppendWrap: $('mode-opt-container'),
        promptOverrideWrap: $('mode-override-container'),
        promptAppend: $('model-opt-append'),
        promptOverride: $('model-override-full'),
        promptSystem: $('model-opt-system'),
        garmentTypeInput: $('garment-type-input'),
        garmentTypeClear: $('garment-type-clear'),
        // Sidebar toggles
        errorToggle: $('errorlog-toggle-btn'),

        // Sidebars
        errorSidebar: $('errorlog-sidebar'),
        errorOverlay: $('errorlog-overlay'),
        errorClose: $('errorlog-sidebar-close'),

        // Error log
        errorBadgeIcon: $('errorlog-badge'),
        errorSidebarCount: $('errorlog-sidebar-count'),
        errorSidebarList: $('errorlog-sidebar-list'),
        errorRefresh: $('errorlog-sidebar-refresh'),
        errorClear: $('errorlog-sidebar-clear'),
        errorPanelList: $('error-log-list'),
        errorPanelBadge: $('error-log-badge'),
        errorPanelClear: $('error-log-clear'),
        errorPanelRoot: $('error-log-panel'),
        errorPanelToggle: $('error-log-toggle'),
        errorPanelBody: $('error-log-body'),
        errorPanelChevron: $('error-log-chevron'),

        cacheCountdown: $('cache-countdown-time'),
        rateModelLabel: $('rate-model-label'),
        rateRpmUsed: $('rate-rpm-used'),
        rateRpm: $('rate-rpm'),
        rateTpmUsed: $('rate-tpm-used'),
        rateTpm: $('rate-tpm'),
        rateRpdUsed: $('rate-rpd-used'),
        rateRpd: $('rate-rpd'),
        rateMinuteCountdown: $('rate-minute-countdown'),
        resetCountdown: $('reset-countdown'),

        recommendationEntryBanner: $('recommendation-entry-banner'),
        heroSourceTag: $('hero-source-tag'),
        heroProductTitle: $('hero-product-title'),
        heroSubtitle: $('hero-subtitle'),
        heroProductId: $('hero-product-id'),
        heroSceneHint: $('hero-scene-hint'),
        heroProductPrice: $('hero-product-price'),
        heroProductPriceAside: $('hero-product-price-aside'),
        heroScoreValue: $('hero-score-value'),
        heroStyleType: $('hero-style-type'),
        heroStyleTypeAside: $('hero-style-type-aside'),
        heroColorFamily: $('hero-color-family'),
        heroColorFamilyAside: $('hero-color-family-aside'),
        heroSizeHint: $('hero-size-hint'),
        heroSizeHintAside: $('hero-size-hint-aside'),
        heroReason: $('hero-recommendation-reason'),
        heroProductUrl: $('hero-product-url'),
        returnToRecommendBtn: $('return-to-recommend-btn'),
        switchProductBtn: $('switch-product-btn'),
        integrationAlert: $('integration-alert'),
        targetIntakeStatus: $('target-intake-status'),
        garmentIntakeStatus: $('garment-intake-status'),
        summaryProductTitle: $('summary-product-title'),
        summaryProductId: $('summary-product-id'),
        summaryProductPrice: $('summary-product-price'),
        summaryStyleType: $('summary-style-type'),
        summaryColorFamily: $('summary-color-family'),
        summarySizeHint: $('summary-size-hint'),
        summaryScore: $('summary-score'),
        summaryReason: $('summary-recommendation-reason'),
        resultFeedback: $('result-feedback'),
        compareUserImg: $('compare-user-img'),
        compareUserPlaceholder: $('compare-user-placeholder'),
        compareGarmentImg: $('compare-garment-img'),
        compareGarmentPlaceholder: $('compare-garment-placeholder'),
        compareResultImg: $('compare-result-img'),
        compareResultPlaceholder: $('compare-result-placeholder'),
        resultRetryBtn: $('result-retry-btn'),
    };

    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const clamp = (n, min, max) => Math.max(min, Math.min(max, n));
    const PARALLEL_ENABLED_STORAGE = 'tryon_parallel_enabled_v1';
    const PARALLEL_CONCURRENCY_STORAGE = 'tryon_parallel_concurrency_v1';
    const PARALLEL_CONCURRENCY_MIN = 2;
    const PARALLEL_CONCURRENCY_MAX = 20;
    const PARALLEL_CONCURRENCY_DEFAULT = 3;
    const ERROR_PANEL_EXPANDED_STORAGE = 'tryon_error_panel_expanded_v1';
    const BRIDGE_SOURCE = 'down-jacket-recommendation';
    const BRIDGE_MESSAGE_TYPES = ['DOWN_JACKET_TRYON_INIT', 'RECOMMENDATION_TRYON_INIT'];
    const BRIDGE_ACK_TYPE = 'DOWN_JACKET_TRYON_ACK';
    const BRIDGE_MAX_VERSION = 1;
    const FRONTEND_CONFIG_DEFAULT = {
        recommend_app_url: '',
        tryon_embed_mode: 'standalone',
    };

    function asTrimmedString(value) {
        return String(value ?? '').trim();
    }

    function safeText(value, fallback = uiText('runtime.pending', undefined, 'Pending')) {
        const text = asTrimmedString(value);
        return text || fallback;
    }

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, ch => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }[ch] || ch));
    }

    function numericOrNull(value) {
        if (value === null || value === undefined || asTrimmedString(value) === '') return null;
        const n = Number(value);
        return Number.isFinite(n) ? n : null;
    }

    function formatPrice(value) {
        const text = asTrimmedString(value);
        if (!text) return window.WorkbenchI18n?.t('legacy.pending') || 'Pending';
        const n = numericOrNull(text);
        if (n == null) return text;
        if (window.WorkbenchI18n?.formatCurrency) return window.WorkbenchI18n.formatCurrency(n);
        return `¥${n.toFixed(Number.isInteger(n) ? 0 : 2)}`;
    }

    function formatScore(value) {
        const n = numericOrNull(value);
        if (n == null) return '--';
        return n.toFixed(Number.isInteger(n) ? 0 : 1);
    }

    function normalizeFrontendConfig(payload) {
        const data = (payload && typeof payload === 'object') ? payload : FRONTEND_CONFIG_DEFAULT;
        let mode = asTrimmedString(data.tryon_embed_mode || data.tryonEmbedMode || 'standalone').toLowerCase();
        if (!['standalone', 'embed'].includes(mode)) mode = 'standalone';
        return {
            recommend_app_url: asTrimmedString(data.recommend_app_url || data.recommendAppUrl),
            tryon_embed_mode: mode,
        };
    }

    async function fetchFrontendConfig() {
        try {
            const r = await fetch('/api/frontend-config', { cache: 'no-store' });
            const d = await r.json();
            state.frontendConfig = normalizeFrontendConfig(r.ok ? d : FRONTEND_CONFIG_DEFAULT);
        } catch (_) {
            state.frontendConfig = normalizeFrontendConfig(FRONTEND_CONFIG_DEFAULT);
        }
        document.body.classList.toggle('embed-mode', state.frontendConfig?.tryon_embed_mode === 'embed');
    }

    function recommendOriginFromConfig() {
        const url = asTrimmedString(state.frontendConfig?.recommend_app_url);
        if (!url) return '';
        try {
            return new URL(url).origin;
        } catch (_) {
            return '';
        }
    }

    const BRIDGE_STR_MAX = 2000;

    function isHttpUrl(value) {
        if (!value) return false;
        try {
            const u = new URL(value);
            return u.protocol === 'http:' || u.protocol === 'https:';
        } catch {
            return false;
        }
    }

    function isImageDataUrl(value) {
        return /^data:image\/(png|jpe?g|webp);base64,/i.test(value);
    }

    function capStr(value) {
        const s = asTrimmedString(value);
        return s.length <= BRIDGE_STR_MAX ? s : s.slice(0, BRIDGE_STR_MAX);
    }

    function isTrustedBridgeOrigin(origin) {
        const current = asTrimmedString(origin);
        if (!current) return false;
        // Same-origin is always allowed
        if (current === window.location.origin) return true;
        // Check against the configured recommend app origin only
        const trusted = asTrimmedString(recommendOriginFromConfig());
        if (trusted) return trusted === current;
        return false;
    }

    function normalizeBridgePayload(raw) {
        if (!raw || typeof raw !== 'object') return null;

        // Reject payloads that explicitly claim a wrong source
        const rawSource = asTrimmedString(raw.source);
        if (rawSource && rawSource !== BRIDGE_SOURCE) return null;

        // Resolve alias fields before validation
        const rawUserUrl = asTrimmedString(raw.userImageUrl || raw.userImage || raw.modelImageUrl);
        const rawUserData = asTrimmedString(raw.userImageDataUrl || raw.userImageBase64 || raw.userImageData || raw.modelImageDataUrl);
        const rawGarmentUrl = asTrimmedString(raw.garmentImageUrl || raw.referenceImageUrl || raw.productImageUrl);
        const rawGarmentData = asTrimmedString(raw.garmentImageDataUrl || raw.referenceImageDataUrl || raw.productImageDataUrl || raw.garmentImageBase64);
        const rawReturnUrl = asTrimmedString(raw.returnUrl || raw.recommendationUrl);
        const rawProductUrl = asTrimmedString(raw.productUrl || raw.product_url);

        const source = raw.presentationSource;
        let presentationSource = null;
        if (source && typeof source === 'object' && ['recommend', 'style-lab', 'product'].includes(source.kind)
            && source.result && typeof source.result === 'object') {
            try {
                if (JSON.stringify(source).length <= 50000) presentationSource = source;
            } catch (_) { /* Ignore malformed optional presentation data. */ }
        }
        const payload = {
            source: rawSource || BRIDGE_SOURCE,
            // URL fields: strip if not a valid http/https URL to prevent open redirect
            userImageUrl: isHttpUrl(rawUserUrl) ? capStr(rawUserUrl) : '',
            // Data URL fields: strip if not a recognized image data URL format
            userImageDataUrl: (rawUserData && isImageDataUrl(rawUserData)) ? rawUserData : '',
            garmentImageUrl: isHttpUrl(rawGarmentUrl) ? capStr(rawGarmentUrl) : '',
            garmentImageDataUrl: (rawGarmentData && isImageDataUrl(rawGarmentData)) ? rawGarmentData : '',
            productTitle: capStr(raw.productTitle),
            productId: capStr(raw.productId),
            productPrice: raw.productPrice ?? '',
            styleType: capStr(raw.styleType),
            colorFamily: capStr(raw.colorFamily),
            sizeHint: capStr(raw.sizeHint),
            recommendationReason: capStr(raw.recommendationReason),
            score: raw.score ?? '',
            returnUrl: isHttpUrl(rawReturnUrl) ? capStr(rawReturnUrl) : '',
            sceneHint: capStr(raw.sceneHint || raw.scene || raw.occasionHint),
            fitNote: capStr(raw.fitNote || raw.silhouetteNote),
            productUrl: isHttpUrl(rawProductUrl) ? capStr(rawProductUrl) : '',
            presentationSource,
        };
        const hasValue = Object.entries(payload).some(([key, value]) => {
            if (key === 'source') return false;
            return typeof value === 'number' ? true : Boolean(asTrimmedString(value));
        });
        return hasValue ? payload : null;
    }

    function parseBridgePayloadFromUrl() {
        const params = new URLSearchParams(window.location.search);
        const packed = params.get('tryonPayload') || params.get('payload') || params.get('recommendationPayload');
        if (packed) {
            try {
                return normalizeBridgePayload(JSON.parse(packed));
            } catch (_) {
                try {
                    return normalizeBridgePayload(JSON.parse(decodeURIComponent(packed)));
                } catch (__ ) {
                    return null;
                }
            }
        }
        const keys = ['source', 'userImageUrl', 'userImageDataUrl', 'userImageBase64', 'garmentImageUrl', 'garmentImageDataUrl', 'garmentImageBase64', 'productTitle', 'productId', 'productPrice', 'styleType', 'colorFamily', 'sizeHint', 'recommendationReason', 'score', 'returnUrl', 'sceneHint'];
        const hasAny = keys.some(key => params.has(key));
        if (!hasAny) return null;
        return normalizeBridgePayload({
            source: params.get('source') || BRIDGE_SOURCE,
            userImageUrl: params.get('userImageUrl') || '',
            userImageDataUrl: params.get('userImageDataUrl') || params.get('userImageBase64') || '',
            garmentImageUrl: params.get('garmentImageUrl') || '',
            garmentImageDataUrl: params.get('garmentImageDataUrl') || params.get('garmentImageBase64') || '',
            productTitle: params.get('productTitle') || '',
            productId: params.get('productId') || '',
            productPrice: params.get('productPrice') || '',
            styleType: params.get('styleType') || '',
            colorFamily: params.get('colorFamily') || '',
            sizeHint: params.get('sizeHint') || '',
            recommendationReason: params.get('recommendationReason') || '',
            score: params.get('score') || '',
            returnUrl: params.get('returnUrl') || '',
            sceneHint: params.get('sceneHint') || '',
        });
    }

    function defaultIntakeStatus(kind) {
        return kind === 'model'
            ? 'runtime.modelDefault'
            : 'runtime.garmentDefault';
    }

    function setUploadIntakeStatus(kind, key, tone = 'neutral', params = {}) {
        const node = kind === 'model' ? el.targetIntakeStatus : el.garmentIntakeStatus;
        if (!node) return;
        state.intakeStatus[kind] = { key: key || defaultIntakeStatus(kind), tone, params };
        node.textContent = uiText(state.intakeStatus[kind].key, params);
        node.dataset.tone = tone;
    }

    function setIntegrationAlert(key, tone = 'info') {
        if (!el.integrationAlert) return;
        state.integrationAlert = key ? { key, tone } : null;
        const text = key ? uiText(key) : '';
        el.integrationAlert.textContent = text;
        el.integrationAlert.dataset.tone = tone;
        el.integrationAlert.classList.toggle('hidden', !text);
    }

    function setResultFeedback(tone, titleKey, detailKey = '', params = {}) {
        if (!el.resultFeedback) return;
        state.feedback = { tone, titleKey, detailKey, params };
        const localizedParams = { ...params };
        if (Array.isArray(localizedParams.missing)) {
            localizedParams.missing = localizedParams.missing.map(key => uiText(key)).join(', ');
        }
        const heading = titleKey ? uiText(titleKey, localizedParams) : '';
        const body = detailKey ? uiText(detailKey, localizedParams) : '';
        if (!heading && !body) {
            el.resultFeedback.className = 'result-feedback hidden';
            el.resultFeedback.innerHTML = '';
            return;
        }
        el.resultFeedback.className = `result-feedback is-${tone || 'info'}`;
        el.resultFeedback.innerHTML = `<strong>${escapeHtml(heading)}</strong>${body ? `<span>${escapeHtml(body)}</span>` : ''}`;
    }

    function updateCompareImage(img, placeholder, url, emptyText) {
        if (!img || !placeholder) return;
        _clearImgError(img);
        if (url) {
            img.src = url;
            img.classList.remove('hidden');
            placeholder.classList.add('hidden');
        } else {
            img.removeAttribute('src');
            img.classList.add('hidden');
            placeholder.textContent = emptyText;
            placeholder.classList.remove('hidden');
        }
    }

    function updateCompareStage() {
        updateCompareImage(el.compareUserImg, el.compareUserPlaceholder, _modelDisplayUrl(), uiText('runtime.userPhotoPending', undefined, 'Waiting for a full-body user photo'));
        updateCompareImage(el.compareGarmentImg, el.compareGarmentPlaceholder, _garmentDisplayUrl(0), uiText('runtime.garmentPhotoPending', undefined, 'Waiting for a down-jacket product image'));
        updateCompareImage(el.compareResultImg, el.compareResultPlaceholder, getResultPreviewUrl(0), uiText('runtime.resultPending', undefined, 'Shown after generation'));
    }

    function getResultPreviewUrl(index) {
        return state.resultPreviews[index] || state.results[index] || '';
    }

    function getSessionResultUrls() {
        return state.results.map((url, index) => getResultPreviewUrl(index) || url).filter(Boolean);
    }

    function updateRecommendationUi() {
        const payload = state.recommendation;
        const linked = Boolean(payload);
        const priceText = linked ? formatPrice(payload.productPrice) : uiText('runtime.pending', undefined, 'Pending');
        const scoreText = linked ? formatScore(payload.score) : '--';
        const styleText = linked ? safeText(payload.styleType) : uiText('runtime.pending', undefined, 'Pending');
        const colorText = linked ? safeText(payload.colorFamily) : uiText('runtime.pending', undefined, 'Pending');
        const sizeText = linked ? safeText(payload.sizeHint) : uiText('runtime.pending', undefined, 'Pending');
        const titleText = linked ? safeText(payload.productTitle, uiText('runtime.productReceived', undefined, 'Recommended product received')) : uiText('runtime.recommendTitleFallback', undefined, 'Waiting for a recommended down jacket');
        const idText = linked ? safeText(payload.productId, uiText('runtime.productIdPending', undefined, 'Product ID pending')) : uiText('runtime.productIdPending', undefined, 'Product ID pending');
        const reasonText = linked
            ? safeText(payload.recommendationReason, uiText('runtime.reasonFallback', undefined, 'No recommendation reason was provided.'))
            : uiText('runtime.summaryWaiting', undefined, 'Waiting for the recommendation summary. You can also upload images manually.');
        const sceneText = linked
            ? safeText(payload.sceneHint, uiText('runtime.sceneLinked', undefined, 'Opened from the recommendation result'))
            : uiText('runtime.scenePending', undefined, 'Scene pending');

        if (el.recommendationEntryBanner) el.recommendationEntryBanner.classList.toggle('hidden', !linked);
        if (el.heroSourceTag) el.heroSourceTag.textContent = linked ? uiText('runtime.recommendLinked', undefined, 'Recommendation link connected') : uiText('runtime.manualMode', undefined, 'Manual upload mode');
        if (el.heroProductTitle) el.heroProductTitle.textContent = titleText;
        if (el.heroSubtitle) {
            el.heroSubtitle.textContent = linked
                ? uiText('runtime.subtitleLinked', undefined, 'The recommended product summary and images are ready. Adjust the style and start try-on.')
                : uiText('runtime.subtitleManual', undefined, 'Recommendation images are used first; manual upload is available when no values are provided.');
        }
        if (el.heroProductId) el.heroProductId.textContent = idText;
        if (el.heroSceneHint) el.heroSceneHint.textContent = sceneText;
        if (el.heroProductPrice) el.heroProductPrice.textContent = priceText;
        if (el.heroProductPriceAside) el.heroProductPriceAside.textContent = priceText;
        if (el.heroScoreValue) el.heroScoreValue.textContent = scoreText;
        if (el.heroStyleType) el.heroStyleType.textContent = styleText;
        if (el.heroStyleTypeAside) el.heroStyleTypeAside.textContent = styleText;
        if (el.heroColorFamily) el.heroColorFamily.textContent = colorText;
        if (el.heroColorFamilyAside) el.heroColorFamilyAside.textContent = colorText;
        if (el.heroSizeHint) el.heroSizeHint.textContent = sizeText;
        if (el.heroSizeHintAside) el.heroSizeHintAside.textContent = sizeText;
        if (el.heroReason) el.heroReason.textContent = reasonText;
        if (el.summaryProductTitle) el.summaryProductTitle.textContent = titleText;
        if (el.summaryProductId) el.summaryProductId.textContent = idText;
        if (el.summaryProductPrice) el.summaryProductPrice.textContent = priceText;
        if (el.summaryStyleType) el.summaryStyleType.textContent = styleText;
        if (el.summaryColorFamily) el.summaryColorFamily.textContent = colorText;
        if (el.summarySizeHint) el.summarySizeHint.textContent = sizeText;
        if (el.summaryScore) el.summaryScore.textContent = scoreText;
        if (el.summaryReason) el.summaryReason.textContent = reasonText;
        if (el.heroProductUrl) {
            const productUrl = linked ? asTrimmedString(payload.productUrl) : '';
            if (productUrl) {
                el.heroProductUrl.href = productUrl;
                el.heroProductUrl.textContent = uiText('runtime.shop', undefined, '🛒 Shop now');
                el.heroProductUrl.classList.remove('hidden');
            } else {
                el.heroProductUrl.classList.add('hidden');
            }
        }
        if (el.returnToRecommendBtn) {
            const visible = linked || Boolean(asTrimmedString(state.frontendConfig?.recommend_app_url));
            el.returnToRecommendBtn.classList.toggle('hidden', !visible);
        }
        if (el.switchProductBtn) {
            const visible = linked || Boolean(asTrimmedString(state.frontendConfig?.recommend_app_url));
            el.switchProductBtn.classList.toggle('hidden', !visible);
        }
        if (!linked) {
            setIntegrationAlert('', 'info');
        }
    }

    let recommendationLocaleRequest = 0;
    async function localizeLinkedRecommendation() {
        const payload = state.recommendation;
        const source = payload?.presentationSource;
        if (!source) return;
        const targetLocale = window.WorkbenchI18n?.locale || 'zh-CN';
        const requestId = ++recommendationLocaleRequest;
        const origin = recommendOriginFromConfig();
        try {
            if (!origin) throw new Error('Recommendation service unavailable');
            const response = await fetch(new URL('/api/localize-result', origin).toString(), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Accept-Language': targetLocale },
                body: JSON.stringify({ kind: source.kind, result: source.result, locale: targetLocale }),
            });
            if (!response.ok) throw new Error('Recommendation localization failed');
            const localized = await response.json();
            if (requestId !== recommendationLocaleRequest || state.recommendation !== payload
                || payload.presentationSource !== source || window.WorkbenchI18n?.locale !== targetLocale) return;
            const product = source.kind === 'recommend'
                ? localized.items?.[0]
                : (source.kind === 'style-lab' ? localized.product : localized);
            if (!product) throw new Error('Recommendation localization was empty');
            payload.productTitle = capStr(product.display?.title || product.title);
            payload.styleType = capStr(product.display?.styleType || product.style_type);
            payload.colorFamily = capStr(product.display?.colorFamily || product.color_family);
            payload.fitNote = capStr(product.display?.sizeNotes || product.size_notes);
            if (source.kind === 'recommend') {
                payload.recommendationReason = capStr(product.reason);
                payload.sceneHint = capStr(localized.inference?.display?.style || payload.sceneHint);
            } else if (source.kind === 'style-lab') {
                payload.recommendationReason = capStr(localized.analysis?.reason || payload.recommendationReason);
                payload.sceneHint = capStr(localized.inference?.display?.style || payload.sceneHint);
            }
            updateRecommendationUi();
        } catch (_) {
            if (requestId === recommendationLocaleRequest && state.recommendation === payload) {
                notify(uiText('runtime.recommendRelocalizeFailed'), 'warning');
            }
        }
    }

    async function importBridgeImage(kind, imageUrl, imageDataUrl) {
        const r = await fetch('/api/intake-image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source: state.recommendation?.source || BRIDGE_SOURCE,
                role: kind,
                locale: window.WorkbenchI18n?.locale || 'zh-CN',
                image_url: asTrimmedString(imageUrl),
                image_data_url: asTrimmedString(imageDataUrl),
            }),
        });
        const d = await r.json().catch(() => ({}));
        if (!r.ok || !d?.ok || !d?.filename) {
            throw new Error(d?.error || uiText('runtime.autoImportFailed', undefined, 'Automatic import failed'));
        }
        return { filename: d.filename, cloud_url: d.cloud_url || '' };
    }

    let _applyChain = Promise.resolve();
    const _appliedBridgeState = {
        hasPostMessage: false,
        productId: '',
        userImageUrl: '',
        userImageDataUrl: '',
        garmentImageUrl: '',
        garmentImageDataUrl: '',
    };

    function mergeBridgePayload(existing, incoming) {
        if (!existing) return incoming;
        return {
            ...existing,
            ...incoming,
            userImageUrl: incoming.userImageUrl || existing.userImageUrl || '',
            userImageDataUrl: incoming.userImageDataUrl || existing.userImageDataUrl || '',
            garmentImageUrl: incoming.garmentImageUrl || existing.garmentImageUrl || '',
            garmentImageDataUrl: incoming.garmentImageDataUrl || existing.garmentImageDataUrl || '',
            sizeHint: incoming.sizeHint || existing.sizeHint || '',
            recommendationReason: incoming.recommendationReason || existing.recommendationReason || '',
            score: numericOrNull(incoming.score) !== null ? incoming.score : (existing.score ?? ''),
            sceneHint: incoming.sceneHint || existing.sceneHint || '',
            fitNote: incoming.fitNote || existing.fitNote || '',
            presentationSource: incoming.presentationSource || existing.presentationSource || null,
        };
    }

    async function tryImportLocalSampleFallback(userImageUrl) {
        const raw = asTrimmedString(userImageUrl);
        if (!raw) return null;
        const match = raw.match(/\/sample-models\/(male|female)\/([^/?#]+)$/i);
        if (!match) return null;
        const gender = match[1].toLowerCase();
        const filename = match[2];
        const sample = SAMPLE_MODELS.find(m => m.gender === gender && m.filename.toLowerCase() === filename.toLowerCase());
        if (!sample) return null;
        const resp = await fetch(`/static/sample-models/${sample.gender}/${sample.filename}`);
        if (!resp.ok) return null;
        const blob = await resp.blob();
        const file = new File([blob], sample.filename, { type: blob.type || 'image/jpeg' });
        return await upload(file, '/upload/model');
    }

    function applyRecommendationPayload(rawPayload, meta = {}) {
        const task = _applyChain.then(() => _applyRecommendationPayloadImpl(rawPayload, meta));
        _applyChain = task.catch(() => {});
        return task;
    }

    async function _applyRecommendationPayloadImpl(rawPayload, meta = {}) {
        const payload = normalizeBridgePayload(rawPayload);
        if (!payload) return;

        const isQueryChannel = meta.channel === 'query';
        const isPostMessage = meta.channel === 'postMessage';
        const sameProductContext = Boolean(state.recommendation)
            && ((payload.productId && payload.productId === _appliedBridgeState.productId)
                || (payload.garmentImageUrl && payload.garmentImageUrl === _appliedBridgeState.garmentImageUrl));

        // Do not let a late query-channel run overwrite an already-applied postMessage payload.
        if (isQueryChannel && _appliedBridgeState.hasPostMessage && sameProductContext) {
            state.recommendation = mergeBridgePayload(state.recommendation, payload);
            updateRecommendationUi();
            updateCompareStage();
            ready();
            return;
        }
        if (isPostMessage) {
            _appliedBridgeState.hasPostMessage = true;
        }

        const hasUserInput = Boolean(payload.userImageUrl || payload.userImageDataUrl);
        const hasGarmentInput = Boolean(payload.garmentImageUrl || payload.garmentImageDataUrl);
        const sameModelInput = payload.userImageUrl === _appliedBridgeState.userImageUrl
            && (!payload.userImageDataUrl || payload.userImageDataUrl === _appliedBridgeState.userImageDataUrl);
        const sameGarmentInput = payload.garmentImageUrl === _appliedBridgeState.garmentImageUrl
            && payload.garmentImageDataUrl === _appliedBridgeState.garmentImageDataUrl;
        const modelAlreadyReady = Boolean(state.model) && (sameModelInput || (Boolean(payload.userImageUrl) && payload.userImageUrl === _appliedBridgeState.userImageUrl));
        const garmentAlreadyReady = state.garments.length > 0 && sameGarmentInput;

        if (sameProductContext && (!hasUserInput || modelAlreadyReady) && (!hasGarmentInput || garmentAlreadyReady)) {
            state.recommendation = mergeBridgePayload(state.recommendation, payload);
            updateRecommendationUi();
            updateCompareStage();
            ready();
            return;
        }

        const mergedPayload = sameProductContext ? mergeBridgePayload(state.recommendation, payload) : payload;
        state.recommendation = mergedPayload;
        if (!sameProductContext) {
            state.results = [];
            state.resultPreviews = [];
            state.selected.clear();
            resetResult();
            renderGallery();
        }
        updateRecommendationUi();

        if (el.garmentTypeInput && !asTrimmedString(el.garmentTypeInput.value)) {
            el.garmentTypeInput.value = '外套';
        }

        let modelReady = Boolean(state.model);
        let garmentReady = state.garments.length > 0;
        const needModelImport = hasUserInput && !modelAlreadyReady;
        const needGarmentImport = hasGarmentInput && !garmentAlreadyReady;

        if (needModelImport) {
            state.model = '';
            state.modelCloudUrl = '';
            updateModel();
            setUploadIntakeStatus('model', 'runtime.modelImporting', 'loading');
            try {
                let modelResult;
                try {
                    modelResult = await importBridgeImage('model', payload.userImageUrl, payload.userImageDataUrl);
                } catch (firstErr) {
                    modelResult = await tryImportLocalSampleFallback(payload.userImageUrl);
                    if (!modelResult) throw firstErr;
                }
                state.model = modelResult.filename;
                state.modelCloudUrl = modelResult.cloud_url;
                _appliedBridgeState.userImageUrl = payload.userImageUrl;
                _appliedBridgeState.userImageDataUrl = payload.userImageDataUrl;
                modelReady = true;
                updateModel();
                setUploadIntakeStatus('model', 'runtime.modelImported', 'success');
            } catch (e) {
                state.model = '';
                state.modelCloudUrl = '';
                modelReady = false;
                updateModel();
                setUploadIntakeStatus('model', 'runtime.modelImportError', 'error', { error: e.message || e });
                notify(uiText('runtime.modelImportError', { error: e.message || e }), 'warning');
                reportError(e.message || uiText('runtime.autoImportFailed'), 'recommendation-user-image');
            }
        } else if (!state.model) {
            setUploadIntakeStatus('model', 'runtime.modelMissing', 'warning');
        } else {
            setUploadIntakeStatus('model', 'runtime.modelRetained', 'info');
        }

        if (needGarmentImport) {
            state.garments = [];
            state.garmentCloudUrls = [];
            updateGarments();
            setUploadIntakeStatus('garment', 'runtime.garmentImporting', 'loading');
            try {
                const garmentResult = await importBridgeImage('garment', payload.garmentImageUrl, payload.garmentImageDataUrl);
                state.garments = [garmentResult.filename];
                state.garmentCloudUrls = [garmentResult.cloud_url];
                _appliedBridgeState.garmentImageUrl = payload.garmentImageUrl;
                _appliedBridgeState.garmentImageDataUrl = payload.garmentImageDataUrl;
                garmentReady = true;
                updateGarments();
                setUploadIntakeStatus('garment', 'runtime.garmentImported', 'success');
            } catch (e) {
                state.garments = [];
                state.garmentCloudUrls = [];
                garmentReady = false;
                updateGarments();
                setUploadIntakeStatus('garment', 'runtime.garmentImportError', 'error', { error: e.message || e });
                notify(uiText('runtime.garmentImportError', { error: e.message || e }), 'warning');
                reportError(e.message || uiText('runtime.autoImportFailed'), 'recommendation-product-image');
            }
        } else if (state.garments.length === 0) {
            setUploadIntakeStatus('garment', 'runtime.garmentMissing', 'warning');
        } else {
            setUploadIntakeStatus('garment', 'runtime.garmentRetained', 'info');
        }

        _appliedBridgeState.productId = mergedPayload.productId || '';
        setIntegrationAlert('runtime.recommendBridgeInfo', 'info');

        if (modelReady && garmentReady) {
            setResultFeedback('info', 'runtime.recommendReadyTitle', 'runtime.recommendReadyDetail');
        } else {
            const missing = [];
            if (!modelReady) missing.push('legacy.userPhoto');
            if (!garmentReady) missing.push('legacy.referencePhoto');
            setResultFeedback('warning', 'runtime.recommendIncompleteTitle', 'runtime.recommendIncompleteDetail', { missing });
        }

        updateCompareStage();
        ready();
        if (needModelImport || needGarmentImport || !sameProductContext) {
            notify(uiText('runtime.recommendSynced'), 'success');
        }
    }

    function bridgeTargetWindow() {
        if (window.opener && !window.opener.closed) return window.opener;
        if (window.parent && window.parent !== window) return window.parent;
        return null;
    }

    function postBridgeEvent(type) {
        const target = bridgeTargetWindow();
        if (!target) return false;
        const origin = asTrimmedString(recommendOriginFromConfig());
        if (!origin) return false;
        try {
            target.postMessage({
                type,
                source: 'tryon-workbench',
                productId: asTrimmedString(state.recommendation?.productId),
                productTitle: asTrimmedString(state.recommendation?.productTitle),
            }, origin);
            return true;
        } catch (_) {
            return false;
        }
    }

    function navigateToRecommendation(mode = 'return') {
        const raw = asTrimmedString(state.recommendation?.returnUrl || state.frontendConfig?.recommend_app_url);
        // Validate scheme before assigning to location.href to prevent open redirect / XSS
        const url = isHttpUrl(raw) ? raw : '';
        postBridgeEvent(mode === 'switch' ? 'DOWN_JACKET_TRYON_SWITCH_REQUEST' : 'DOWN_JACKET_TRYON_BACK');
        if (url) {
            window.location.href = url;
            return;
        }
        if (window.history.length > 1) {
            window.history.back();
            return;
        }
        notify(uiText('runtime.recommendListMissing'), 'warning');
    }


    async function handleBridgeMessage(event) {
        if (!isTrustedBridgeOrigin(event.origin)) return;
        const data = event?.data;
        if (!data || typeof data !== 'object') return;
        const type = asTrimmedString(data.type).toUpperCase();
        // Accept legacy messages (no version field) or version 1; reject future unknown versions
        const version = data.version;
        if (version !== undefined && version !== null && Number(version) > BRIDGE_MAX_VERSION) return;
        const rawPayload = (data.payload && typeof data.payload === 'object') ? data.payload : data;
        const payload = normalizeBridgePayload(rawPayload);
        if (!payload) return;
        if (type && !BRIDGE_MESSAGE_TYPES.includes(type) && payload.source !== BRIDGE_SOURCE) return;
        try {
            await applyRecommendationPayload(payload, { channel: 'postMessage', origin: event.origin });
            // Send ACK so the sender can stop retrying
            if (event.source && typeof event.source.postMessage === 'function') {
                const ackOrigin = asTrimmedString(event.origin);
                if (!ackOrigin) return;
                try {
                    event.source.postMessage({
                        type: BRIDGE_ACK_TYPE,
                        version: 1,
                        productId: asTrimmedString(payload.productId),
                    }, ackOrigin);
                } catch (_) { /* ignore ACK delivery failure */ }
            }
        } catch (e) {
            notify(e.message || uiText('runtime.bridgeFailed'), 'error');
            reportError(e.message || uiText('runtime.bridgeFailed'), 'recommendation-postMessage');
        }
    }

    function setErrorPanelExpanded(expanded, persist = true) {
        const isExpanded = Boolean(expanded);
        if (el.errorPanelBody) {
            el.errorPanelBody.classList.toggle('hidden', !isExpanded);
        }
        if (el.errorPanelChevron) {
            el.errorPanelChevron.classList.toggle('expanded', isExpanded);
        }
        if (persist) {
            localStorage.setItem(ERROR_PANEL_EXPANDED_STORAGE, isExpanded ? '1' : '0');
        }
    }

    function initErrorPanelState() {
        const expanded = localStorage.getItem(ERROR_PANEL_EXPANDED_STORAGE) === '1';
        setErrorPanelExpanded(expanded, false);
    }


    function syncParallelUi() {
        if (!el.parallelConcurrencyRow) return;
        const enabled = Boolean(el.parallelToggle?.checked);
        el.parallelConcurrencyRow.classList.toggle('visible', enabled);
        if (el.parallelConcurrency) el.parallelConcurrency.disabled = !enabled;
        if (el.parallelConcurrencySlider) el.parallelConcurrencySlider.disabled = !enabled;
    }

    function normalizeParallelConcurrency(value) {
        const raw = Number(value);
        return clamp(
            Number.isFinite(raw) ? raw : PARALLEL_CONCURRENCY_DEFAULT,
            PARALLEL_CONCURRENCY_MIN,
            PARALLEL_CONCURRENCY_MAX,
        );
    }

    function syncParallelConcurrencyControls(value, persist = false) {
        const next = normalizeParallelConcurrency(value);
        if (el.parallelConcurrency) el.parallelConcurrency.value = String(next);
        if (el.parallelConcurrencySlider) el.parallelConcurrencySlider.value = String(next);
        if (persist) {
            localStorage.setItem(PARALLEL_CONCURRENCY_STORAGE, String(next));
        }
        return next;
    }

    function getParallelSettings(totalTasks) {
        const enabled = Boolean(el.parallelToggle?.checked);
        const max = syncParallelConcurrencyControls(el.parallelConcurrency?.value || PARALLEL_CONCURRENCY_DEFAULT, true);
        if (!enabled) return { enabled: false, concurrency: 1 };
        return { enabled: true, concurrency: Math.max(1, Math.min(max, totalTasks || 1)) };
    }

    function notify(text, type = 'info') {
        if (!el.note) return;
        const div = document.createElement('div');
        div.className = `notification notification-${type}`;
        div.textContent = text;
        el.note.appendChild(div);
        requestAnimationFrame(() => div.classList.add('show'));
        setTimeout(() => {
            div.classList.remove('show');
            setTimeout(() => div.remove(), 240);
        }, 2600);
    }

    function writeLog(text) {
        if (!el.log || !el.logBox) return;
        el.logBox.classList.remove('hidden');
        el.log.textContent += `[${new Date().toLocaleTimeString()}] ${text}\n`;
        el.log.scrollTop = el.log.scrollHeight;
    }

    function setText(sel, value) {
        const n = document.querySelector(sel);
        if (n) n.textContent = value;
    }

    function applyCopy() {
        const i18n = window.WorkbenchI18n;
        document.title = i18n ? i18n.t('meta.title') : 'AI Down Jacket Try-On Workbench';
        if (el.genText) el.genText.textContent = i18n ? i18n.t('legacy.generate') : 'Generate try-on result';
        if (el.resultImg) el.resultImg.alt = i18n ? i18n.t('legacy.result') : 'Try-on result';
        if (el.downOne) el.downOne.innerHTML = `<i class="fas fa-download"></i> ${i18n ? i18n.t('legacy.downloadMain') : 'Download main result'}`;
        if (el.errorToggle) el.errorToggle.title = i18n ? i18n.t('legacy.errorLog') : 'Error log';
        if (el.modelInput) el.modelInput.multiple = false;
    }

    function ready() {
        const canGenerate = state.runtimeAvailable && !state.running && Boolean(state.model) && state.garments.length > 0;
        if (el.genBtn) el.genBtn.disabled = !canGenerate;
        if (el.resultRetryBtn) el.resultRetryBtn.disabled = !canGenerate;
        if (el.downOne) el.downOne.disabled = !(getResultPreviewUrl(0) || el.resultImg?.src);
        updateCompareStage();
    }

    function _modelDisplayUrl() {
        return state.modelCloudUrl || (state.model ? `/uploads/${state.model}` : '');
    }
    function _garmentDisplayUrl(index) {
        return state.garmentCloudUrls[index] || (state.garments[index] ? `/uploads/${state.garments[index]}` : '');
    }

    function updateModel() {
        const ok = Boolean(state.model);
        if (el.modelImg) {
            _clearImgError(el.modelImg);
            if (ok) {
                el.modelImg.src = _modelDisplayUrl();
                el.modelImg.classList.remove('hidden');
            } else {
                el.modelImg.removeAttribute('src');
                el.modelImg.classList.add('hidden');
            }
        }
        if (el.modelPh) el.modelPh.classList.toggle('hidden', ok);
        if (el.modelCtl) el.modelCtl.classList.toggle('hidden', !ok);
        if (el.modelCnt) el.modelCnt.textContent = ok ? '1' : '0';
        updateCompareStage();
        ready();
    }

    function updateGarments() {
        const ok = state.garments.length > 0;
        if (el.refImg) {
            _clearImgError(el.refImg);
            if (ok) {
                el.refImg.src = _garmentDisplayUrl(0);
                el.refImg.classList.remove('hidden');
            } else {
                el.refImg.removeAttribute('src');
                el.refImg.classList.add('hidden');
            }
        }
        if (el.refPh) el.refPh.classList.toggle('hidden', ok);
        if (el.refCtl) el.refCtl.classList.toggle('hidden', !ok);
        if (el.refCnt) el.refCnt.textContent = String(state.garments.length);
        window.dispatchEvent(new CustomEvent('workbench:garmentchange', { detail: _garmentDisplayUrl(0) }));
        window.dispatchEvent(new CustomEvent('workbench:productchange', {
            detail: {
                garmentUrl: _garmentDisplayUrl(0),
                productTitle: state.recommendation?.productTitle || '',
                styleType: state.recommendation?.styleType || '',
                colorFamily: state.recommendation?.colorFamily || '',
            },
        }));
        updateCompareStage();
        ready();
    }

    function setRunning(v) {
        state.running = v;
        if (el.abortBtn) el.abortBtn.classList.toggle('hidden', !v);
        ready();
    }

    function progress(p, m, i, t) {
        const pct = clamp(Math.round(p), 0, 100);
        if (el.status) el.status.classList.remove('hidden');
        if (el.batchInfo) el.batchInfo.classList.remove('hidden');
        if (el.fill) el.fill.style.width = `${pct}%`;
        if (el.pct) el.pct.textContent = `${pct}%`;
        if (el.msg) el.msg.textContent = m || uiText('legacy.processing');
        if (el.batchText) el.batchText.textContent = uiText('legacy.batchProgress', { done: Math.min(i, t), total: t });
    }

    function syncFreedom() {
        if (!el.freedom || !el.freedomVal) return;
        el.freedomVal.textContent = String(clamp(Number(el.freedom.value || '5'), 0, 10));
    }

    function syncInterval() {
        if (!el.interval || !el.intervalVal) return;
        el.intervalVal.textContent = `${el.interval.value}ms`;
    }

    function pad2(v) {
        return String(Math.max(0, v | 0)).padStart(2, '0');
    }

    function formatHms(ms) {
        const total = Math.max(0, Math.floor(ms / 1000));
        const h = Math.floor(total / 3600);
        const m = Math.floor((total % 3600) / 60);
        const s = total % 60;
        return `${pad2(h)}:${pad2(m)}:${pad2(s)}`;
    }

    function formatMsNoHour(ms) {
        const total = Math.max(0, Math.floor(ms / 1000));
        const m = Math.floor(total / 60);
        const s = total % 60;
        return `${pad2(m)}:${pad2(s)}`;
    }

    function formatCompact(num) {
        const n = Number(num || 0);
        if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 2)}M`;
        if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 2)}K`;
        return String(Math.round(n));
    }

    function getZoneClockParts(timeZone) {
        const parts = new Intl.DateTimeFormat('en-US', {
            timeZone,
            hourCycle: 'h23',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        }).formatToParts(new Date());
        const map = {};
        for (const p of parts) {
            if (p.type !== 'literal') map[p.type] = Number(p.value);
        }
        return {
            hour: map.hour || 0,
            minute: map.minute || 0,
            second: map.second || 0,
        };
    }

    function msUntilTimeZoneMidnight(timeZone) {
        const clock = getZoneClockParts(timeZone);
        const passed = (clock.hour * 3600) + (clock.minute * 60) + clock.second;
        return Math.max(0, (24 * 3600 - passed) * 1000);
    }

    function msUntilNextMinute() {
        const now = Date.now();
        return 60000 - (now % 60000);
    }

    function refreshCountdowns() {
        const cacheLeft = msUntilTimeZoneMidnight('Asia/Shanghai');
        const minuteLeft = Number.isFinite(state.minuteResetSec)
            ? Math.max(0, Math.floor(state.minuteResetSec * 1000))
            : msUntilNextMinute();
        const dailyLeft = Number.isFinite(state.dailyResetSec)
            ? Math.max(0, Math.floor(state.dailyResetSec * 1000))
            : msUntilTimeZoneMidnight('America/Los_Angeles');

        if (el.cacheCountdown) el.cacheCountdown.textContent = formatHms(cacheLeft);
        if (el.rateMinuteCountdown) el.rateMinuteCountdown.textContent = formatMsNoHour(minuteLeft);
        if (el.resetCountdown) el.resetCountdown.textContent = formatHms(dailyLeft);

        if (Number.isFinite(state.minuteResetSec)) {
            state.minuteResetSec = state.minuteResetSec <= 0
                ? Math.ceil(msUntilNextMinute() / 1000)
                : state.minuteResetSec - 1;
        }
        if (Number.isFinite(state.dailyResetSec)) {
            state.dailyResetSec = state.dailyResetSec <= 0
                ? Math.ceil(msUntilTimeZoneMidnight('America/Los_Angeles') / 1000)
                : state.dailyResetSec - 1;
        }
    }

    function refreshModelRateUi() {
        const cfg = MODEL_LIMITS[state.modelType] || MODEL_LIMITS.flash;
        if (el.footerModel) el.footerModel.textContent = cfg.name;
        if (el.rateModelLabel) el.rateModelLabel.textContent = cfg.name;
        if (el.rateRpmUsed) el.rateRpmUsed.textContent = '0';
        if (el.rateRpm) el.rateRpm.textContent = String(cfg.rpm);
        if (el.rateTpmUsed) el.rateTpmUsed.textContent = '0';
        if (el.rateTpm) el.rateTpm.textContent = formatCompact(cfg.tpm);
        if (el.rateRpdUsed) el.rateRpdUsed.textContent = '0';
        if (el.rateRpd) el.rateRpd.textContent = String(cfg.rpd);
    }

    function renderRateStatus(payload) {
        const cfg = MODEL_LIMITS[state.modelType] || MODEL_LIMITS.flash;
        const data = payload || {};
        const modelName = data.model_name || cfg.name;
        const rpmLimit = Number(data.rpm_limit || cfg.rpm);
        const tpmLimit = Number(data.tpm_limit || cfg.tpm);
        const rpdLimit = Number(data.rpd_limit || cfg.rpd);
        const rpmUsed = Number(data.rpm_used || 0);
        const tpmUsed = Number(data.tpm_used || 0);
        const rpdUsed = Number(data.rpd_used || 0);

        if (el.footerModel) el.footerModel.textContent = modelName;
        if (el.rateModelLabel) el.rateModelLabel.textContent = modelName;
        if (el.rateRpmUsed) el.rateRpmUsed.textContent = String(rpmUsed);
        if (el.rateRpm) el.rateRpm.textContent = String(rpmLimit);
        if (el.rateTpmUsed) el.rateTpmUsed.textContent = formatCompact(tpmUsed);
        if (el.rateTpm) el.rateTpm.textContent = formatCompact(tpmLimit);
        if (el.rateRpdUsed) el.rateRpdUsed.textContent = String(rpdUsed);
        if (el.rateRpd) el.rateRpd.textContent = String(rpdLimit);
    }

    async function refreshRateStatus(silent = true) {
        try {
            const params = new URLSearchParams();
            params.set('model', state.modelType);
            if (state.modelId) params.set('model_id', state.modelId);

            const r = await fetch(`/api/rate-status?${params.toString()}`, { cache: 'no-store' });
            if (!r.ok) throw new Error(uiText('runtime.limitRequestFailed', { status: r.status }));
            const d = await r.json();
            if (!d || !d.ok) throw new Error(d?.error || uiText('runtime.limitResponseInvalid'));

            state.rateStatus = d;
            state.minuteResetSec = Number.isFinite(Number(d.minute_reset_seconds))
                ? Number(d.minute_reset_seconds)
                : null;
            state.dailyResetSec = Number.isFinite(Number(d.daily_reset_seconds))
                ? Number(d.daily_reset_seconds)
                : null;
            renderRateStatus(d);
            refreshCountdowns();
        } catch (e) {
            if (!silent) writeLog(e.message || uiText('runtime.limitRefreshFailed'));
        }
    }

    function closeAllSidebars() {
        el.errorSidebar?.classList.remove('open');
        el.errorOverlay?.classList.add('hidden');
        document.body.classList.remove('sidebar-open');
    }

    function openSidebar(which) {
        closeAllSidebars();
        const map = {
            error: [el.errorSidebar, el.errorOverlay],
        };
        const pair = map[which];
        if (!pair) return;
        pair[0]?.classList.add('open');
        pair[1]?.classList.remove('hidden');
        document.body.classList.add('sidebar-open');
        if (which === 'error') refreshErrors();
    }

    async function reportError(message, context = 'frontend') {
        try {
            const fd = new FormData();
            fd.append('message', String(message || ''));
            fd.append('context', String(context || ''));
            await fetch('/api/errors/report', { method: 'POST', body: fd });
        } catch (_) { }
    }

    async function analyzeErrorItem(errorId) {
        const id = String(errorId || '').trim();
        if (!id || state.errorAnalyzing.has(id)) return;
        const item = (state.errors || []).find(e => e.id === id);
        if (!item) return;

        state.errorAnalyzing.add(id);
        try {
            const fd = new FormData();
            fd.append('error_message', String(item.message || ''));
            fd.append('error_detail', String(item.detail || ''));

            const r = await fetch('/analyze-error', { method: 'POST', body: fd });
            const d = await r.json();
            const analysis = String(d?.analysis || '').trim();
            if (!analysis) throw new Error(uiText('runtime.analysisEmpty'));

            const fd2 = new FormData();
            fd2.append('analysis', analysis);
            await fetch(`/api/errors/${encodeURIComponent(id)}/analysis`, { method: 'PUT', body: fd2 });
            await refreshErrors();
            notify(uiText('runtime.analysisComplete'), 'success');
        } catch (e) {
            notify(e.message || uiText('runtime.analysisFailed'), 'error');
        } finally {
            state.errorAnalyzing.delete(id);
            renderErrors();
        }
    }

    function renderErrors() {
        const list = state.errors || [];
        const html = list.length === 0
            ? `<div class="usage-empty"><i class="fas fa-check-circle"></i> ${uiText('legacy.emptyError')}</div>`
            : list.map(e => `
                <div class="errorlog-item">
                    <div class="errorlog-time">${escapeHtml(e.time)} ${e.context ? `· ${escapeHtml(e.context)}` : ''}</div>
                    <div class="errorlog-msg">${escapeHtml(e.message)}</div>
                    <div class="errorlog-actions">
                        <button type="button" data-analyze-error="${escapeHtml(e.id)}" class="errorlog-action-btn">
                            <i class="fas fa-robot"></i> ${state.errorAnalyzing.has(e.id) ? uiText('legacy.errorAnalyze') : (e.analysis ? uiText('legacy.retry') : uiText('legacy.aiAnalyze'))}
                        </button>
                    </div>
                    ${e.analysis ? `<div class="errorlog-analysis"><i class="fas fa-robot"></i> ${escapeHtml(e.analysis)}</div>` : ''}
                </div>`).join('');
        if (el.errorSidebarList) el.errorSidebarList.innerHTML = html;
        if (el.errorPanelList) el.errorPanelList.innerHTML = html;
        const count = list.length;
        if (el.errorBadgeIcon) {
            el.errorBadgeIcon.textContent = String(count);
            el.errorBadgeIcon.classList.toggle('hidden', count === 0);
        }
        if (el.errorSidebarCount) el.errorSidebarCount.textContent = String(count);
        if (el.errorPanelBadge) el.errorPanelBadge.textContent = String(count);
        if (el.errorPanelRoot) el.errorPanelRoot.classList.toggle('hidden', count === 0);
        [el.errorSidebarList, el.errorPanelList].forEach(container => {
            if (!container) return;
            [...container.querySelectorAll('[data-analyze-error]')].forEach(btn => {
                const id = btn.getAttribute('data-analyze-error') || '';
                const running = state.errorAnalyzing.has(id);
                btn.disabled = running;
                btn.addEventListener('click', () => analyzeErrorItem(id));
            });
        });
    }

    async function refreshErrors() {
        try {
            const r = await fetch('/api/errors', { cache: 'no-store' });
            const d = await r.json();
            state.errors = Array.isArray(d.errors) ? d.errors : [];
        } catch (_) {
            state.errors = [];
        }
        renderErrors();
    }

    async function clearErrors() {
        try { await fetch('/api/errors', { method: 'DELETE' }); } catch (_) { }
        state.errors = [];
        renderErrors();
    }



    function resetResult() {
        if (el.resultImg) {
            _clearImgError(el.resultImg);
            el.resultImg.removeAttribute('src');
            el.resultImg.classList.add('hidden');
        }
        if (el.resultPh) el.resultPh.classList.remove('hidden');
        if (el.downOne) el.downOne.classList.add('hidden');
        updateCompareStage();
    }

    function showResult(url) {
        if (!el.resultImg || !el.resultPh) return;
        _clearImgError(el.resultImg);
        el.resultImg.src = url;
        el.resultImg.classList.remove('hidden');
        el.resultPh.classList.add('hidden');
        if (el.downOne) el.downOne.classList.remove('hidden');
        updateCompareStage();
    }

    async function upload(file, endpoint) {
        const fd = new FormData();
        fd.append('file', file);
        const r = await fetch(endpoint, { method: 'POST', body: fd });
        if (!r.ok) {
            let msg = uiText('runtime.uploadFailed', { status: r.status });
            try {
                const d = await r.json();
                msg = d.error || msg;
            } catch (_) { }
            throw new Error(msg);
        }
        const d = await r.json();
        if (!d.filename) throw new Error(uiText('runtime.filenameMissing'));
        return { filename: d.filename, cloud_url: d.cloud_url || '' };
    }

    async function onModel(files) {
        const list = Array.from(files || []).filter(f => f.type.startsWith('image/'));
        if (list.length === 0) return;
        if (list.length > 1) notify(uiText('runtime.modelOnlyOne'), 'warning');
        try {
            notify(uiText('runtime.modelUploading'), 'info');
            const result = await upload(list[0], '/upload/model');
            state.model = result.filename;
            state.modelCloudUrl = result.cloud_url;
            updateModel();
            setUploadIntakeStatus('model', 'runtime.modelUploaded', 'success');
            notify(uiText('runtime.modelUploadSuccess'), 'success');
        } catch (e) {
            notify(e.message || uiText('runtime.modelUploadFailed'), 'error');
            writeLog(e.message || uiText('runtime.modelUploadFailed'));
            reportError(e.message || uiText('runtime.modelUploadFailed'), 'model-upload');
        }
    }

    async function onGarments(files) {
        const list = Array.from(files || []).filter(f => f.type.startsWith('image/'));
        if (list.length === 0) return;
        if (state.garments.length + list.length > 50) {
            notify(uiText('runtime.garmentMax', { count: state.garments.length }), 'warning');
            return;
        }
        try {
            notify(uiText('runtime.garmentUploading', { count: list.length }), 'info');
            for (const f of list) {
                const result = await upload(f, '/upload/garment');
                state.garments.push(result.filename);
                state.garmentCloudUrls.push(result.cloud_url);
            }
            updateGarments();
            setUploadIntakeStatus('garment', 'runtime.garmentUploaded', 'success', { count: state.garments.length });
            notify(uiText('runtime.garmentUploadComplete', { count: state.garments.length }), 'success');
        } catch (e) {
            notify(e.message || uiText('runtime.garmentUploadFailed'), 'error');
            writeLog(e.message || uiText('runtime.garmentUploadFailed'));
            reportError(e.message || uiText('runtime.garmentUploadFailed'), 'garment-upload');
        }
    }

    function bindDrop(zone, input, handler) {
        if (!zone || !input) return;
        zone.addEventListener('click', e => {
            if (e.target.closest('button')) return;
            input.click();
        });
        input.addEventListener('change', async () => {
            await handler(input.files);
            input.value = '';
        });
        ['dragenter', 'dragover'].forEach(n => zone.addEventListener(n, e => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.add('dragover');
        }));
        ['dragleave', 'drop'].forEach(n => zone.addEventListener(n, e => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.remove('dragover');
        }));
        zone.addEventListener('drop', async e => {
            await handler(e.dataTransfer.files);
        });
    }

    function getBatchCount() {
        if (!el.batchCount) return 1;
        const n = clamp(Number(el.batchCount.value || '1'), 1, 50);
        el.batchCount.value = String(n);
        return n;
    }

    function getFreedom() {
        const base = el.freedom ? clamp(Number(el.freedom.value || '5'), 0, 10) : 5;
        if (el.freedomRnd && el.freedomRnd.checked) return Math.floor(Math.random() * 11);
        return base;
    }

    function getGarmentType() {
        return String(el.garmentTypeInput?.value || '').trim();
    }

    const TRYON_PREFS_STORAGE = 'tryon_step3_prefs_v1';

    function loadStep3Prefs() {
        try {
            const raw = localStorage.getItem(TRYON_PREFS_STORAGE);
            if (!raw) return;
            const prefs = JSON.parse(raw);
            if (!prefs || typeof prefs !== 'object') return;
            if (typeof prefs.provider === 'string' && prefs.provider) state.provider = prefs.provider;
            if (typeof prefs.totokensProfile === 'string' && prefs.totokensProfile) state.totokensProfile = prefs.totokensProfile;
            if (typeof prefs.modelId === 'string' && prefs.modelId) state.modelId = prefs.modelId;
            if (typeof prefs.useCustomModel === 'boolean') state.useCustomModel = prefs.useCustomModel;
            if (typeof prefs.customModelId === 'string') state.customModelId = prefs.customModelId;
            if (prefs.detailOptions && typeof prefs.detailOptions === 'object') {
                state.detailOptions = { ...state.detailOptions, ...prefs.detailOptions };
            }
        } catch (_) { }
    }

    function saveStep3Prefs() {
        try {
            localStorage.setItem(TRYON_PREFS_STORAGE, JSON.stringify({
                provider: state.provider,
                totokensProfile: state.totokensProfile,
                modelId: state.modelId,
                useCustomModel: state.useCustomModel,
                customModelId: state.customModelId,
                detailOptions: state.detailOptions,
            }));
        } catch (_) { }
    }

    function getProviderDisplayLabel(providerKey, fallbackLabel = '') {
        if (providerKey === 'totokens') return uiText('runtime.providerTotokensLabel', undefined, fallbackLabel || 'ToTokens Relay');
        if (providerKey === 'gemini') return uiText('runtime.providerGeminiLabel', undefined, fallbackLabel || 'Google Gemini Direct');
        return fallbackLabel || providerKey;
    }

    function getAspectOptionLabel(value) {
        const keyMap = {
            'auto': 'runtime.aspectAuto',
            '3:4': 'runtime.aspect34',
            '4:5': 'runtime.aspect45',
            '9:16': 'runtime.aspect916',
            '1:1': 'runtime.aspect11',
            '4:3': 'runtime.aspect43',
            '3:2': 'runtime.aspect32',
            '2:3': 'runtime.aspect23',
            '5:4': 'runtime.aspect54',
            '16:9': 'runtime.aspect169',
            '21:9': 'runtime.aspect219',
        };
        const key = keyMap[value];
        return key ? uiText(key, undefined, value) : value;
    }

    function getSizeOptionLabel(value) {
        const keyMap = {
            'auto': 'runtime.sizeAuto',
            '1K': 'runtime.size1K',
            '2K': 'runtime.size2K',
            '4K': 'runtime.size4K',
        };
        const key = keyMap[value];
        return key ? uiText(key, undefined, value) : value;
    }

    function getQualityOptionLabel(value) {
        const keyMap = {
            'auto': 'runtime.qualityAuto',
            'low': 'runtime.qualityLow',
            'medium': 'runtime.qualityMedium',
            'high': 'runtime.qualityHigh',
        };
        const key = keyMap[value];
        return key ? uiText(key, undefined, value) : value;
    }

    function syncFooterProvider() {
        if (!el.footerProvider) return;
        const relay = state.provider === 'totokens' || state.modelType === 'chatgpt';
        el.footerProvider.textContent = relay ? 'ToTokens' : 'Google AI Studio';
    }

    function setModel(type, skipRateFetch = false) {
        state.modelType = (type === 'pro' || type === 'chatgpt') ? type : 'flash';
        syncFooterProvider();
        refreshModelRateUi();
        if (!skipRateFetch) refreshRateStatus(true);
    }

    function renderEffectiveSummary(providerObj) {
        if (!el.effectiveSummary) return;
        const providerLabel = getProviderDisplayLabel(state.provider, providerObj?.label);
        const activeModel = state.modelId || state.modelType;
        const opts = state.detailOptions || {};
        const specParts = [];
        if (opts.aspect_ratio && opts.aspect_ratio !== 'auto') specParts.push(opts.aspect_ratio);
        if (state.capabilities?.supports_image_size && opts.image_size && opts.image_size !== 'auto') {
            specParts.push(opts.image_size);
        }
        if (state.capabilities?.supports_quality && opts.quality && opts.quality !== 'auto') {
            specParts.push(opts.quality.toUpperCase());
        }
        if (state.capabilities?.supports_temperature && opts.temperature !== '') {
            specParts.push(`T=${opts.temperature}`);
        }
        if (state.capabilities?.supports_seed && opts.seed !== '') {
            specParts.push(`Seed=${opts.seed}`);
        }
        const specsText = specParts.length ? specParts.join(' · ') : uiText('runtime.sizeAuto', undefined, 'Auto specs');
        const freedomVal = el.freedom?.value ?? '5';
        el.effectiveSummary.textContent = uiText(
            'runtime.summaryTemplate',
            { provider: providerLabel, model: activeModel, specs: specsText, freedom: freedomVal },
            `${providerLabel} / ${activeModel} · ${specsText}`
        );
    }

    function syncTryonRoutingUi(options = {}) {
        const tf = window.TryonForm;
        if (!tf) return;
        const resolved = tf.resolveSelectionState(state.runtimeStatus, {
            provider: state.provider,
            totokensProfile: state.totokensProfile,
            modelId: state.modelId,
            useCustomModel: state.useCustomModel,
            customModelId: state.customModelId,
            detailOptions: state.detailOptions,
        });

        state.provider = resolved.provider;
        state.modelId = resolved.effectiveModelId;
        state.capabilities = resolved.capabilities;
        state.detailOptions = tf.sanitizeOptionsForCapabilities(state.detailOptions, state.capabilities);
        const matchInfo = tf.resolveTotokensRouteMatch
            ? (resolved.provider === 'totokens'
                ? tf.resolveTotokensRouteMatch(resolved.providerObj, resolved.effectiveModelId, state.detailOptions, state.totokensProfile)
                : null)
            : resolved.totokensMatch;
        if (matchInfo) {
            state.totokensProfile = matchInfo.selectedProfileId || 'auto';
        }

        if (MODEL_LIMITS[resolved.presetKey] && state.modelId) {
            MODEL_LIMITS[resolved.presetKey].name = state.modelId;
        }

        // 1. Provider select
        if (el.providerSelect) {
            el.providerSelect.innerHTML = '';
            resolved.providers.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.key;
                const tags = [];
                if (p.is_default) tags.push(uiText('runtime.providerDefaultTag', undefined, 'Default'));
                if (!p.configured) tags.push(uiText('runtime.providerUnconfiguredTag', undefined, 'Not configured'));
                const label = getProviderDisplayLabel(p.key, p.label);
                opt.textContent = tags.length ? `${label} (${tags.join(' · ')})` : label;
                el.providerSelect.appendChild(opt);
            });
            el.providerSelect.value = resolved.provider;
        }

        // 1b. ToTokens API key group selector
        if (el.totokensProfileField && el.totokensProfileSelect) {
            const showProfiles = resolved.provider === 'totokens' && Boolean(matchInfo?.profiles?.length);
            el.totokensProfileField.classList.toggle('hidden', !showProfiles);
            if (showProfiles && matchInfo) {
                el.totokensProfileSelect.innerHTML = '';
                const autoOpt = document.createElement('option');
                autoOpt.value = 'auto';
                autoOpt.textContent = uiText('runtime.totokensAutoRoute', undefined, 'Auto-match key group');
                el.totokensProfileSelect.appendChild(autoOpt);
                matchInfo.profiles.forEach(prof => {
                    const opt = document.createElement('option');
                    opt.value = prof.id;
                    const tag = prof.configured
                        ? uiText('runtime.totokensRouteConfigured', undefined, 'Configured')
                        : uiText('runtime.totokensRouteUnconfigured', undefined, 'No key');
                    opt.textContent = `${prof.label || prof.id} (${tag})`;
                    el.totokensProfileSelect.appendChild(opt);
                });
                el.totokensProfileSelect.value = matchInfo.selectedProfileId || 'auto';
                if (el.totokensProfileHint) {
                    el.totokensProfileHint.classList.toggle('is-error', matchInfo.issue === 'mismatch');
                    if (matchInfo.issue === 'mismatch') {
                        el.totokensProfileHint.textContent = uiText('runtime.totokensRouteMismatchHint', undefined, 'Incompatible route');
                    } else if (matchInfo.issue === 'missing') {
                        const lbl = matchInfo.matchedProfile?.label || 'ToTokens';
                        el.totokensProfileHint.textContent = uiText('runtime.totokensRouteMissingHint', { label: lbl }, `Missing ${lbl} key`);
                    } else {
                        el.totokensProfileHint.textContent = uiText('runtime.totokensRouteAutoHint', undefined, 'Auto route enabled');
                    }
                }
            }
        }

        // 2. Model select
        if (el.modelSelect) {
            el.modelSelect.innerHTML = '';
            resolved.models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m.id;
                const badgeText = m.badge ? ` [${m.badge}]` : '';
                opt.textContent = `${m.id}${badgeText}`;
                el.modelSelect.appendChild(opt);
            });
            if (resolved.selectedListModelId) {
                el.modelSelect.value = resolved.selectedListModelId;
            }
            el.modelSelect.disabled = Boolean(state.useCustomModel);
        }

        // 3. Custom Model ID controls
        if (el.customModelToggle) el.customModelToggle.checked = Boolean(state.useCustomModel);
        if (el.customModelWrap) el.customModelWrap.classList.toggle('hidden', !state.useCustomModel);
        if (el.customModelInput && el.customModelInput.value !== state.customModelId) {
            el.customModelInput.value = state.customModelId;
        }
        if (el.customModelInput && el.customModelHint) {
            if (state.useCustomModel) {
                const v = resolved.customModelValidation;
                el.customModelInput.setAttribute('aria-invalid', String(!v.valid));
                el.customModelHint.classList.toggle('is-error', !v.valid);
                if (!v.valid) {
                    el.customModelHint.textContent = v.reason === 'empty'
                        ? uiText('runtime.customModelEmptyTip')
                        : uiText('runtime.customModelInvalidTip');
                } else {
                    el.customModelHint.textContent = '';
                }
            } else {
                el.customModelInput.removeAttribute('aria-invalid');
                el.customModelHint.textContent = '';
                el.customModelHint.classList.remove('is-error');
            }
        }

        // 4. Capability metadata pills
        const caps = state.capabilities;
        const selectedModelObj = resolved.models.find(m => m.id === resolved.selectedListModelId);
        const maxConcurrency = Number(selectedModelObj?.max_concurrency || (resolved.presetKey === 'flash' ? 5 : 3));
        if (el.modelMeta) {
            el.modelMeta.innerHTML = '';
            const addPill = (text, tone = 'neutral') => {
                const span = document.createElement('span');
                span.className = `tryon-meta-pill tone-${tone}`;
                span.textContent = text;
                el.modelMeta.appendChild(span);
            };
            addPill(
                caps.protocol === 'openai_images_edit'
                    ? uiText('runtime.protocolOpenaiEdit')
                    : uiText('runtime.protocolGeminiNative'),
                'accent'
            );
            addPill(
                resolved.providerObj?.configured
                    ? getProviderDisplayLabel(resolved.provider, resolved.providerObj?.label)
                    : `${getProviderDisplayLabel(resolved.provider)} · ${uiText('runtime.providerUnconfiguredTag')}`,
                resolved.providerObj?.configured ? 'ok' : 'warn'
            );
            if (resolved.provider === 'totokens' && matchInfo) {
                if (matchInfo.issue === 'mismatch') {
                    addPill(uiText('runtime.totokensRouteMismatchPill', undefined, 'Route mismatch'), 'warn');
                } else if (matchInfo.issue === 'missing') {
                    addPill(uiText('runtime.totokensRouteMissingPill', { label: matchInfo.matchedProfile?.label || 'ToTokens' }, 'Key missing'), 'warn');
                } else if (matchInfo.matchedProfile) {
                    addPill(uiText('runtime.totokensRouteActivePill', { label: matchInfo.matchedProfile.label }, matchInfo.matchedProfile.label), 'ok');
                }
            }
            addPill(uiText('runtime.capAspectRatio'));
            addPill(caps.supports_image_size ? uiText('runtime.capResolution1to4k') : uiText('runtime.capResolution1kOnly'));
            if (caps.supports_quality) {
                addPill(uiText('runtime.capQualityTiers'));
                addPill(uiText('runtime.capGptNoSeed'), 'warn');
            } else {
                addPill(uiText('runtime.capTempSeed'));
            }
            addPill(uiText('runtime.concurrencyHintShort', { max: maxConcurrency }));
        }

        // 5. Detail parameters UI & capability gating
        if (el.aspectRatioSelect) {
            el.aspectRatioSelect.innerHTML = '';
            (caps.aspect_ratio_options || tf.ASPECT_RATIOS).forEach(val => {
                const opt = document.createElement('option');
                opt.value = val;
                opt.textContent = getAspectOptionLabel(val);
                el.aspectRatioSelect.appendChild(opt);
            });
            el.aspectRatioSelect.value = state.detailOptions.aspect_ratio || 'auto';
        }

        if (el.imageSizeField && el.imageSizeSelect) {
            const showImageSize = Boolean(caps.supports_image_size || !caps.supports_quality);
            el.imageSizeField.classList.toggle('hidden', !showImageSize);
            el.imageSizeSelect.innerHTML = '';
            const optionsList = caps.supports_image_size ? (caps.image_size_options || tf.GEMINI_IMAGE_SIZES) : ['auto', '1K'];
            optionsList.forEach(val => {
                const opt = document.createElement('option');
                opt.value = val;
                opt.textContent = getSizeOptionLabel(val);
                el.imageSizeSelect.appendChild(opt);
            });
            el.imageSizeSelect.value = state.detailOptions.image_size || 'auto';
            el.imageSizeSelect.disabled = !caps.supports_image_size;
            el.imageSizeField.classList.toggle('is-disabled', !caps.supports_image_size);
            el.imageSizeSelect.title = caps.supports_image_size
                ? ''
                : uiText(caps.protocol === 'openai_images_edit' ? 'runtime.sizeGpt1kHint' : 'runtime.size25FlashHint');
        }

        if (el.qualityField && el.qualitySelect) {
            el.qualityField.classList.toggle('hidden', !caps.supports_quality);
            el.qualitySelect.innerHTML = '';
            (caps.quality_options || tf.GPT_QUALITIES).forEach(val => {
                const opt = document.createElement('option');
                opt.value = val;
                opt.textContent = getQualityOptionLabel(val);
                el.qualitySelect.appendChild(opt);
            });
            el.qualitySelect.value = state.detailOptions.quality || 'auto';
        }

        if (el.temperatureField) {
            const canTemp = Boolean(caps.supports_temperature);
            el.temperatureField.classList.toggle('is-disabled', !canTemp);
            if (el.temperatureSlider) {
                el.temperatureSlider.disabled = !canTemp;
                el.temperatureSlider.value = state.detailOptions.temperature !== '' ? state.detailOptions.temperature : '1';
            }
            if (el.temperatureInput) {
                el.temperatureInput.disabled = !canTemp;
                el.temperatureInput.value = canTemp ? (state.detailOptions.temperature || '') : '';
            }
            if (el.temperatureClear) el.temperatureClear.disabled = !canTemp;
            if (el.temperatureVal) {
                el.temperatureVal.textContent = canTemp && state.detailOptions.temperature !== ''
                    ? String(state.detailOptions.temperature)
                    : uiText('runtime.tempDefaultPill', undefined, 'Default');
            }
            if (el.temperatureHint) {
                el.temperatureHint.textContent = canTemp
                    ? uiText('tryon.temperatureHint')
                    : uiText('runtime.tempUnsupportedHint');
            }
        }

        if (el.seedField) {
            const canSeed = Boolean(caps.supports_seed);
            el.seedField.classList.toggle('is-disabled', !canSeed);
            if (el.seedInput) {
                el.seedInput.disabled = !canSeed;
                el.seedInput.value = canSeed ? (state.detailOptions.seed || '') : '';
            }
            if (el.seedRandomBtn) el.seedRandomBtn.disabled = !canSeed;
            if (el.seedClear) el.seedClear.disabled = !canSeed;
            if (el.seedHint) {
                el.seedHint.textContent = canSeed
                    ? uiText('tryon.seedHint')
                    : uiText('runtime.seedUnsupportedHint');
            }
        }

        setModel(resolved.presetKey, Boolean(options.skipRateFetch));
        renderEffectiveSummary(resolved.providerObj);
        if (!options.skipSavePrefs) saveStep3Prefs();
    }

    function promptPayload() {
        if (!el.promptToggle) {
            return { mode: 'append', text: '' };
        }
        if (el.promptToggle.checked) {
            const base = (el.promptOverride?.value || '').trim();
            return { mode: 'override', text: base };
        }
        const extra = (el.promptAppend?.value || '').trim();
        return { mode: 'append', text: extra };
    }

    function syncSelUi() {
        const total = state.results.length;
        const selected = state.selected.size;
        const all = total > 0 && selected === total;
        if (el.downSelCount) el.downSelCount.textContent = `(${selected})`;
        if (el.downSel) el.downSel.classList.toggle('hidden', selected === 0);
        if (el.selAll) {
            el.selAll.innerHTML = all
                ? `<i class="fas fa-times"></i> ${uiText('legacy.cancelSelect')}`
                : `<i class="fas fa-check-double"></i> ${uiText('legacy.selectAll')}`;
        }
    }

    function toggleSel(i) {
        if (state.selected.has(i)) state.selected.delete(i);
        else state.selected.add(i);
        renderGallery();
    }

    function renderGallery() {
        if (!el.galleryWrap || !el.gallery || !el.galleryCount) return;
        el.gallery.innerHTML = '';
        if (state.results.length === 0) {
            el.galleryWrap.classList.add('hidden');
            el.galleryCount.textContent = '(0/0)';
            syncSelUi();
            return;
        }
        el.galleryWrap.classList.remove('hidden');
        el.galleryCount.textContent = `(${state.results.length}/${state.results.length})`;
        state.results.forEach((url, i) => {
            const previewUrl = getResultPreviewUrl(i);
            const item = document.createElement('div');
            item.className = 'batch-gallery-item';
            if (state.selected.has(i)) item.classList.add('selected');
            item.innerHTML = `
                <img src="${previewUrl}" alt="${uiText('runtime.resultAlt', { index: i + 1 })}" loading="lazy" width="140" height="140">
                <button class="select-check" type="button" title="${uiText('runtime.select')}"><i class="fas fa-check"></i></button>
                <div class="item-overlay">
                    <span class="item-index">#${i + 1}</span>
                    <button class="item-download" type="button" title="${uiText('runtime.download')}"><i class="fas fa-download"></i></button>
                </div>
            `;
            item.addEventListener('click', () => toggleSel(i));
            item.querySelector('.select-check')?.addEventListener('click', e => {
                e.stopPropagation();
                toggleSel(i);
            });
            item.querySelector('.item-download')?.addEventListener('click', async e => {
                e.stopPropagation();
                await downloadImage(url, uiText('legacy.result'), i + 1);
            });
            el.gallery.appendChild(item);
        });
        syncSelUi();
    }

    function selectedUrls() {
        if (state.selected.size === 0) return [];
        return [...state.selected].sort((a, b) => a - b).map(i => getResultPreviewUrl(i) || state.results[i]).filter(Boolean);
    }

    let downloadNonce = 0;

    function padNumber(value, size = 2) {
        return String(value).padStart(size, '0');
    }

    function buildDownloadTimestamp() {
        const now = new Date();
        downloadNonce = (downloadNonce + 1) % 1000;
        return [
            now.getFullYear(),
            padNumber(now.getMonth() + 1),
            padNumber(now.getDate()),
        ].join('') + '_' + [
            padNumber(now.getHours()),
            padNumber(now.getMinutes()),
            padNumber(now.getSeconds()),
        ].join('') + '_' + padNumber(now.getMilliseconds(), 3) + '_' + padNumber(downloadNonce, 3);
    }

    function buildDownloadFilename(baseName, ext, index = null) {
        const safeBase = String(baseName || 'ai-tryon-result')
            .replace(/\.[^.]+$/, '')
            .replace(/[\\/:*?"<>|]+/g, '_')
            .trim() || 'ai-tryon-result';
        const suffix = index == null ? '' : `_${padNumber(index)}`;
        return `${safeBase}_${buildDownloadTimestamp()}${suffix}.${ext}`;
    }

    let completionAudioContext = null;

    function primeCompletionAudio() {
        try {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (!AudioCtx) return null;
            if (!completionAudioContext) {
                completionAudioContext = new AudioCtx();
            }
            if (completionAudioContext.state === 'suspended') {
                completionAudioContext.resume().catch(() => { });
            }
            return completionAudioContext;
        } catch (_) {
            return null;
        }
    }

    function playCompletionSound(kind = 'success') {
        const ctx = primeCompletionAudio();
        if (!ctx) return;
        const notes = kind === 'warning' ? [523.25, 659.25] : [659.25, 783.99, 987.77];
        const durations = kind === 'warning' ? [0.12, 0.16] : [0.1, 0.12, 0.18];
        const start = ctx.currentTime + 0.03;
        notes.forEach((freq, idx) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = kind === 'warning' ? 'triangle' : 'sine';
            osc.frequency.value = freq;
            gain.gain.setValueAtTime(0.0001, start + idx * 0.16);
            gain.gain.exponentialRampToValueAtTime(kind === 'warning' ? 0.08 : 0.06, start + idx * 0.16 + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.0001, start + idx * 0.16 + durations[idx]);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start(start + idx * 0.16);
            osc.stop(start + idx * 0.16 + durations[idx] + 0.02);
        });
    }

    function saveBlob(blob, name) {
        const u = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = u;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(u);
    }

    async function downloadImage(url, baseName, index = null) {
        let blob;
        try {
            // 优先直接 fetch（同源 URL 会成功）
            const r = await fetch(url);
            if (!r.ok) throw new Error(`${r.status}`);
            blob = await r.blob();
        } catch (_directErr) {
            // 跨域 URL（如 GCS）直接 fetch 会被 CORS 拦截，
            // 回退到后端代理 /download-single 端点
            const r2 = await fetch('/download-single?url=' + encodeURIComponent(url));
            if (!r2.ok) throw new Error(uiText('runtime.uploadFailed', { status: r2.status }));
            blob = await r2.blob();
        }
        saveBlob(blob, buildDownloadFilename(baseName, 'png', index));
    }

    async function downloadZip(urls, baseName) {
        if (!urls || urls.length === 0) {
            notify(uiText('runtime.zipUnavailable'), 'warning');
            return;
        }
        const fd = new FormData();
        fd.append('filenames', JSON.stringify(urls));
        const r = await fetch('/download-batch', { method: 'POST', body: fd });
        if (!r.ok) {
            let msg = uiText('runtime.zipFailed');
            try {
                const d = await r.json();
                msg = d.error || msg;
            } catch (_) { }
            throw new Error(msg);
        }
        saveBlob(await r.blob(), buildDownloadFilename(baseName, 'zip'));
    }

    async function downloadAll() {
        try {
            await downloadZip(getSessionResultUrls(), `${uiText('legacy.result')}_${state.results.length}`);
            notify(uiText('runtime.downloadStarted'), 'success');
        } catch (e) {
            notify(e.message || uiText('runtime.zipFailed'), 'error');
            reportError(e.message || uiText('runtime.zipFailed'), 'batch-download');
        }
    }

    async function downloadSelected() {
        const urls = selectedUrls();
        if (urls.length === 0) {
            notify(uiText('runtime.selectionRequired'), 'warning');
            return;
        }
        try {
            await downloadZip(urls, `${uiText('legacy.result')}_${urls.length}`);
            notify(uiText('runtime.selectedPacked', { count: urls.length }), 'success');
        } catch (e) {
            notify(e.message || uiText('runtime.zipFailed'), 'error');
        }
    }

    async function downloadEach() {
        const urls = selectedUrls().length > 0 ? selectedUrls() : state.results;
        if (urls.length === 0) {
            notify(uiText('runtime.downloadUnavailable'), 'warning');
            return;
        }
        const ms = el.interval ? clamp(Number(el.interval.value || '1500'), 500, 5000) : 1500;
        for (let i = 0; i < urls.length; i++) {
            try {
                await downloadImage(urls[i], uiText('legacy.result'), i + 1);
            } catch (e) {
                writeLog(uiText('runtime.downloadItemFailed', { index: i + 1, error: e.message || e }));
            }
            if (i < urls.length - 1) await sleep(ms);
        }
        notify(uiText('runtime.downloadComplete', { count: urls.length }), 'success');
    }

    async function submitTask(garment, freedom, idempotencyKey = '') {
        const idemKey = idempotencyKey || generateIdempotencyKey();
        const fd = new FormData();
        fd.append('target_image', state.model);
        fd.append('reference_image', garment);
        fd.append('model', state.modelType);
        fd.append('freedom', String(freedom));
        fd.append('locale', window.WorkbenchI18n?.locale || 'zh-CN');
        fd.append('idempotency_key', idemKey);
        if (state.provider) fd.append('provider', state.provider);
        if (state.provider === 'totokens' && state.totokensProfile && state.totokensProfile !== 'auto') {
            fd.append('totokens_profile', state.totokensProfile);
        }
        if (state.modelId) fd.append('model_id', state.modelId);
        const detailOpts = window.TryonForm?.collectSubmissionOptions(state.detailOptions, state.capabilities) || {};
        ['aspect_ratio', 'image_size', 'quality', 'temperature', 'seed'].forEach(key => {
            if (detailOpts[key] !== undefined && detailOpts[key] !== '') {
                fd.append(key, String(detailOpts[key]));
            }
        });
        if (state.modelCloudUrl) fd.append('target_image_cloud_url', state.modelCloudUrl);
        const garmentIdx = state.garments.indexOf(garment);
        const garmentCloudUrl = garmentIdx >= 0 ? state.garmentCloudUrls[garmentIdx] : '';
        if (garmentCloudUrl) fd.append('reference_image_cloud_url', garmentCloudUrl);
        const garmentType = getGarmentType();
        if (garmentType) fd.append('garment_type', garmentType);
        const p = promptPayload();
        if (p.text) {
            fd.append('custom_prompt', p.text);
            fd.append('prompt_mode', p.mode);
        }
        const headers = {
            'Accept-Language': window.WorkbenchI18n?.locale || 'zh-CN',
            'X-Idempotency-Key': idemKey,
        };
        if (state.taskToken) headers['X-Task-Token'] = state.taskToken;

        let r;
        try {
            r = await fetch('/submit-task', { method: 'POST', body: fd, headers, credentials: 'same-origin' });
        } catch (_netErr) {
            // Retry once with the exact same idempotency key on transient network interruption
            r = await fetch('/submit-task', { method: 'POST', body: fd, headers, credentials: 'same-origin' });
        }
        if (!r.ok) {
            let msg = uiText('runtime.taskSubmitFailed', { status: r.status });
            try {
                const d = await r.json();
                msg = d.error || d.detail || msg;
            } catch (_) { }
            throw new Error(msg);
        }
        const d = await r.json();
        if (!d.task_id) throw new Error(uiText('runtime.taskIdMissing'));
        if (d.task_token) state.taskToken = String(d.task_token);
        persistActiveTask(d.task_id, state.taskToken);
        return d.task_id;
    }

    async function waitForPollInterval(ms) {
        if (!document.hidden) {
            await sleep(ms);
            return;
        }
        await new Promise(resolve => {
            const timer = setTimeout(() => {
                document.removeEventListener('visibilitychange', onVis);
                resolve();
            }, Math.max(ms, 6000));
            const onVis = () => {
                if (!document.hidden) {
                    clearTimeout(timer);
                    document.removeEventListener('visibilitychange', onVis);
                    resolve();
                }
            };
            document.addEventListener('visibilitychange', onVis);
        });
    }

    async function pollTask(taskId, index, total) {
        let logged = 0;
        let transientErrors = 0;
        for (let t = 0; t < 240; t++) {
            if (state.unloading) return null;
            if (state.abort) {
                persistActiveTask('', '');
                throw new Error(uiText('runtime.userAborted'));
            }
            let d;
            try {
                const taskLocale = window.WorkbenchI18n?.locale || 'zh-CN';
                const headers = { 'Accept-Language': taskLocale };
                if (state.taskToken) headers['X-Task-Token'] = state.taskToken;
                const r = await fetch(
                    `/task/${encodeURIComponent(taskId)}?lang=${encodeURIComponent(taskLocale)}`,
                    { cache: 'no-store', headers, credentials: 'same-origin' }
                );
                if (r.status === 403 || r.status === 404) {
                    persistActiveTask('', '');
                    throw new Error(uiText('runtime.pollFailed', { status: r.status }));
                }
                if (!r.ok) throw new Error(uiText('runtime.pollFailed', { status: r.status }));
                d = await r.json();
                transientErrors = 0;
            } catch (err) {
                if (String(err.message || '').includes('403') || String(err.message || '').includes('404')) {
                    throw err;
                }
                transientErrors += 1;
                writeLog(uiText('runtime.transientPollError', { count: transientErrors, error: err.message || err }));
                if (transientErrors >= 3) throw err;
                await waitForPollInterval(1500);
                continue;
            }

            const tp = clamp(Number(d.progress || 0), 0, 100);
            const op = ((index + tp / 100) / total) * 100;
            progress(op, d.message || uiText('legacy.processing'), index + 1, total);
            if (Array.isArray(d.logs) && d.logs.length > logged) {
                for (let i = logged; i < d.logs.length; i++) writeLog(d.logs[i]);
                logged = d.logs.length;
            }
            if (d.status === 'completed') {
                persistActiveTask('', '');
                return d;
            }
            if (d.status === 'failed') {
                persistActiveTask('', '');
                throw new Error(d.error || d.message || uiText('task.failed'));
            }
            if (d.status === 'unknown') {
                persistActiveTask('', '');
                throw new Error(d.error || d.message || uiText('task.unknown'));
            }
            await waitForPollInterval(1500);
        }
        throw new Error(uiText('runtime.pollTimeout'));
    }

    async function generate() {
        if (state.running) return;
        if (!state.model) {
            notify(uiText('runtime.modelRequired'), 'warning');
            return;
        }
        if (state.garments.length === 0) {
            notify(uiText('runtime.garmentRequired'), 'warning');
            return;
        }
        const tf = window.TryonForm;
        if (tf && state.useCustomModel) {
            const customCheck = tf.validateCustomModelId(state.customModelId);
            if (!customCheck.valid) {
                notify(
                    customCheck.reason === 'empty'
                        ? uiText('runtime.customModelEmptyTip')
                        : uiText('runtime.customModelInvalidTip'),
                    'warning'
                );
                return;
            }
        }
        const providersList = Array.isArray(state.runtimeStatus?.providers) ? state.runtimeStatus.providers : [];
        if (providersList.length > 0) {
            const selectedProvider = providersList.find(p => p.key === state.provider);
            if (selectedProvider && (!selectedProvider.configured || selectedProvider.enabled === false)) {
                notify(
                    selectedProvider.key === 'totokens' && state.modelType === 'chatgpt'
                        ? uiText('runtime.chatgptKeyMissingTip')
                        : uiText('runtime.providerDisabledError'),
                    'warning'
                );
                return;
            }
        }
        if (tf) {
            try {
                tf.collectSubmissionOptions(state.detailOptions, state.capabilities);
            } catch (err) {
                notify(err.message || uiText('runtime.providerDisabledError'), 'warning');
                return;
            }
        }
        const batch = getBatchCount();
        const list = [];
        state.garments.forEach(g => {
            for (let i = 0; i < batch; i++) list.push(g);
        });
        if (list.length === 0) return;

        state.results = [];
        state.resultPreviews = [];
        state.selected.clear();
        state.abort = false;
        resetResult();
        renderGallery();
        if (el.log) el.log.textContent = '';
        if (el.logBox) el.logBox.classList.add('hidden');
        setRunning(true);
        primeCompletionAudio();
        let ok = 0;
        let fail = 0;
        const parallel = getParallelSettings(list.length);

        writeLog(uiText('runtime.generationStarted', { count: list.length }));
        if (parallel.enabled) {
            writeLog(uiText('runtime.generationParallel', { count: parallel.concurrency }));
        }
        setResultFeedback('info', 'runtime.generationStarted', 'runtime.generationStartedDetail');

        const runOneTask = async (i) => {
            if (state.abort) return;
            const g = list[i];
            const f = getFreedom();
            const garmentType = getGarmentType();
            const garmentTypeLabel = garmentType ? `, type=${garmentType}` : '';
            writeLog(uiText('runtime.generationItem', { index: i + 1, total: list.length, garment: g, freedom: f, type: garmentTypeLabel }));
            try {
                const id = await submitTask(g, f);
                const t = await pollTask(id, i, list.length);
                if (!t) return;
                const stableUrl = String(t.result_display_url || t.result_cloud_url || t.result_url || '').trim();
                const previewUrl = String(t.result_data_url || stableUrl || '').trim();
                if (!previewUrl) throw new Error(uiText('runtime.generationNone'));
                state.results.push(stableUrl || previewUrl);
                state.resultPreviews.push(previewUrl);
                ok += 1;
                if (state.results.length === 1) showResult(previewUrl);
                renderGallery();
                refreshRateStatus(true);
            } catch (e) {
                fail += 1;
                writeLog(uiText('runtime.generationItemFailed', { index: i + 1, error: e.message || e }));
                notify(uiText('runtime.generationItemFailed', { index: i + 1, error: e.message || e }), 'error');
                reportError(e.message || uiText('task.failed'), 'generation-task');
                refreshRateStatus(true);
            }
            if (parallel.enabled) {
                const done = ok + fail;
                progress((done / list.length) * 100, uiText('runtime.generationParallelProgress'), done, list.length);
            }
        };

        try {
            if (parallel.enabled && list.length > 1) {
                let nextIndex = 0;
                const worker = async () => {
                    while (!state.abort) {
                        const i = nextIndex;
                        nextIndex += 1;
                        if (i >= list.length) break;
                        await runOneTask(i);
                    }
                };
                const workers = Array.from({ length: parallel.concurrency }, () => worker());
                await Promise.all(workers);
            } else {
                for (let i = 0; i < list.length; i++) {
                    if (state.abort) break;
                    await runOneTask(i);
                }
            }
        } finally {
            setRunning(false);
        }

        if (state.abort) {
            notify(uiText('runtime.generationAborted', { success: ok, failed: fail }), 'warning');
            setResultFeedback('warning', 'runtime.userAborted', 'runtime.generationAbortedDetail', { done: ok, failed: fail });
        } else if (ok > 0) {
            progress(100, uiText('task.completed'), list.length, list.length);
            notify(uiText('runtime.generationFinished', { success: ok, failed: fail }), fail > 0 ? 'warning' : 'success');
            playCompletionSound(fail > 0 ? 'warning' : 'success');
            writeLog(uiText('runtime.generationFinished', { success: ok, failed: fail }));
            setResultFeedback(
                fail > 0 ? 'warning' : 'success',
                fail > 0 ? 'runtime.generationPartial' : 'task.completed',
                fail > 0 ? 'runtime.generationPartial' : 'runtime.generationFinished',
                { success: ok, failed: fail }
            );
        } else {
            notify(uiText('runtime.generationNone'), 'error');
            playCompletionSound('warning');
            writeLog(uiText('runtime.generationNone'));
            setResultFeedback('error', 'runtime.generationNone', 'runtime.generationNone');
        }
    }

    function initSampleModelPicker() {
        const grid = $('sample-model-grid');
        const tabs = document.querySelectorAll('#sample-model-picker .picker-tab');
        if (!grid || tabs.length === 0) return;

        let currentGender = 'male';

        function renderGrid() {
            grid.innerHTML = '';
            SAMPLE_MODELS.filter(m => m.gender === currentGender).forEach(model => {
                const card = document.createElement('div');
                card.className = 'sample-model-card';
                card.dataset.id = model.id;
                card.innerHTML = `<img src="/static/sample-models/${model.gender}/${model.filename}" alt="${model.name}" loading="lazy"><span>${model.name}</span>`;
                card.addEventListener('click', () => selectSampleModel(model, card));
                grid.appendChild(card);
            });
        }

        async function selectSampleModel(model, card) {
            grid.querySelectorAll('.sample-model-card').forEach(c => c.classList.remove('selected'));
            card.classList.add('selected');
            try {
                const resp = await fetch(`/static/sample-models/${model.gender}/${model.filename}`);
                const blob = await resp.blob();
                const file = new File([blob], model.filename, { type: blob.type });
                notify(uiText('runtime.sampleUploading'), 'info');
                const result = await upload(file, '/upload/model');
                state.model = result.filename;
                state.modelCloudUrl = result.cloud_url;
                updateModel();
                setUploadIntakeStatus('model', 'runtime.sampleSelected', 'success', { name: model.name });
                notify(uiText('runtime.sampleSelected', { name: model.name }), 'success');
            } catch (e) {
                card.classList.remove('selected');
                notify(e.message || uiText('runtime.sampleLoadFailed'), 'error');
            }
        }

        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                currentGender = tab.dataset.gender || 'male';
                renderGrid();
            });
        });

        renderGrid();
    }

    function bind() {
        bindDrop(el.modelZone, el.modelInput, onModel);
        bindDrop(el.refZone, el.refInput, onGarments);

        el.modelContinue?.addEventListener('click', e => { e.stopPropagation(); el.modelInput?.click(); });
        el.refContinue?.addEventListener('click', e => { e.stopPropagation(); el.refInput?.click(); });

        el.modelClear?.addEventListener('click', e => {
            e.stopPropagation();
            state.model = '';
            state.modelCloudUrl = '';
            updateModel();
            setUploadIntakeStatus('model', defaultIntakeStatus('model'), 'neutral');
            notify(uiText('runtime.clearedModel'), 'info');
        });
        el.refClear?.addEventListener('click', e => {
            e.stopPropagation();
            state.garments = [];
            state.garmentCloudUrls = [];
            updateGarments();
            setUploadIntakeStatus('garment', defaultIntakeStatus('garment'), 'neutral');
            notify(uiText('runtime.clearedGarment'), 'info');
        });

        el.modelPreview?.addEventListener('click', e => {
            e.stopPropagation();
            if (!state.model) return notify(uiText('runtime.noModel'), 'warning');
            window.open(_modelDisplayUrl(), '_blank');
        });
        el.refPreview?.addEventListener('click', e => {
            e.stopPropagation();
            if (state.garments.length === 0) return notify(uiText('runtime.noGarment'), 'warning');
            window.open(_garmentDisplayUrl(0), '_blank');
            notify(uiText('runtime.openedGarment', { count: state.garments.length }), 'info');
        });

        el.minus?.addEventListener('click', () => { if (el.batchCount) el.batchCount.value = String(clamp(Number(el.batchCount.value || '1') - 1, 1, 50)); });
        el.plus?.addEventListener('click', () => { if (el.batchCount) el.batchCount.value = String(clamp(Number(el.batchCount.value || '1') + 1, 1, 50)); });
        el.batchCount?.addEventListener('change', getBatchCount);
        el.garmentTypeClear?.addEventListener('click', () => {
            if (!el.garmentTypeInput) return;
            el.garmentTypeInput.value = '';
            el.garmentTypeInput.focus();
        });

        el.freedom?.addEventListener('input', syncFreedom);
        el.interval?.addEventListener('input', syncInterval);

        el.genBtn?.addEventListener('click', generate);
        el.abortBtn?.addEventListener('click', () => {
            state.abort = true;
            notify(uiText('runtime.stopRequested'), 'warning');
        });

        el.selAll?.addEventListener('click', () => {
            const total = state.results.length;
            if (total === 0) return;
            if (state.selected.size === total) state.selected.clear();
            else state.selected = new Set(state.results.map((_, i) => i));
            renderGallery();
        });
        el.downAll?.addEventListener('click', downloadAll);
        el.downSel?.addEventListener('click', downloadSelected);
        el.downEach?.addEventListener('click', downloadEach);
        el.downOne?.addEventListener('click', async () => {
            if (!el.resultImg?.src) return;
            try { await downloadImage(el.resultImg.src, 'ai-tryon-result'); }
            catch (e) { notify(e.message || uiText('runtime.downloadUnavailable'), 'error'); }
        });
        el.resultRetryBtn?.addEventListener('click', generate);
        el.returnToRecommendBtn?.addEventListener('click', () => navigateToRecommendation('return'));
        el.switchProductBtn?.addEventListener('click', () => navigateToRecommendation('switch'));

        const setPromptModalOpen = (open) => {
            el.promptModal?.classList.toggle('hidden', !open);
            document.body.classList.toggle('modal-open', Boolean(open));
        };
        el.promptOpen?.addEventListener('click', () => setPromptModalOpen(true));
        el.promptClose?.addEventListener('click', () => setPromptModalOpen(false));
        el.promptModal?.addEventListener('click', e => { if (e.target === el.promptModal) setPromptModalOpen(false); });

        const syncPromptMode = () => {
            const over = Boolean(el.promptToggle?.checked);
            el.promptAppendWrap?.classList.toggle('hidden-mode', over);
            el.promptOverrideWrap?.classList.toggle('hidden-mode', !over);
        };
        el.promptToggle?.addEventListener('change', syncPromptMode);
        syncPromptMode();

        el.parallelToggle?.addEventListener('change', () => {
            localStorage.setItem(PARALLEL_ENABLED_STORAGE, el.parallelToggle?.checked ? '1' : '0');
            syncParallelUi();
        });
        el.parallelConcurrencySlider?.addEventListener('input', () => {
            syncParallelConcurrencyControls(el.parallelConcurrencySlider?.value || PARALLEL_CONCURRENCY_DEFAULT, true);
        });
        el.parallelConcurrency?.addEventListener('input', () => {
            const raw = Number(el.parallelConcurrency?.value || '');
            if (!Number.isFinite(raw)) return;
            syncParallelConcurrencyControls(raw, true);
        });
        el.parallelConcurrency?.addEventListener('change', () => {
            syncParallelConcurrencyControls(el.parallelConcurrency?.value || PARALLEL_CONCURRENCY_DEFAULT, true);
        });
        syncParallelUi();

        loadStep3Prefs();
        const urlModelHint = new URLSearchParams(window.location.search).get('model');
        if (urlModelHint) {
            state.step3PrefsTouched = true;
            const hint = urlModelHint.trim();
            const low = hint.toLowerCase();
            if (low === 'chatgpt') {
                state.provider = 'totokens';
                state.modelId = 'gpt-image-2';
                state.useCustomModel = false;
            } else if (low === 'pro') {
                state.provider = 'gemini';
                state.modelId = 'gemini-3-pro-image-preview';
                state.useCustomModel = false;
            } else if (low === 'flash') {
                state.provider = 'gemini';
                state.modelId = 'gemini-3.1-flash-image-preview';
                state.useCustomModel = false;
            } else if (hint) {
                state.modelId = hint;
            }
        }

        el.providerSelect?.addEventListener('change', () => {
            state.step3PrefsTouched = true;
            state.provider = el.providerSelect.value;
            state.useCustomModel = false;
            state.modelId = '';
            syncTryonRoutingUi();
        });
        el.totokensProfileSelect?.addEventListener('change', () => {
            state.step3PrefsTouched = true;
            state.totokensProfile = el.totokensProfileSelect.value || 'auto';
            syncTryonRoutingUi({ skipRateFetch: true });
        });
        el.modelSelect?.addEventListener('change', () => {
            state.step3PrefsTouched = true;
            state.modelId = el.modelSelect.value;
            state.useCustomModel = false;
            syncTryonRoutingUi();
        });
        el.customModelToggle?.addEventListener('change', () => {
            state.step3PrefsTouched = true;
            state.useCustomModel = Boolean(el.customModelToggle.checked);
            if (state.useCustomModel && !String(state.customModelId || '').trim()) {
                state.customModelId = state.modelId || '';
            }
            syncTryonRoutingUi();
            if (state.useCustomModel) el.customModelInput?.focus();
        });
        el.customModelInput?.addEventListener('input', () => {
            state.step3PrefsTouched = true;
            state.customModelId = el.customModelInput.value;
            syncTryonRoutingUi();
        });
        el.refreshModelsBtn?.addEventListener('click', async () => {
            el.refreshModelsBtn.disabled = true;
            try {
                const ok = await fetchRuntimeStatus(true);
                if (ok) {
                    notify(uiText('runtime.modelCatalogRefreshed'), 'success');
                } else {
                    notify(uiText('runtime.modelCatalogRefreshFailed'), 'warning');
                }
            } finally {
                el.refreshModelsBtn.disabled = false;
            }
        });
        el.resetParamsBtn?.addEventListener('click', () => {
            state.step3PrefsTouched = true;
            state.totokensProfile = 'auto';
            const tf = window.TryonForm;
            state.detailOptions = tf
                ? tf.defaultDetailOptions()
                : { aspect_ratio: 'auto', image_size: 'auto', quality: 'auto', temperature: '', seed: '' };
            syncTryonRoutingUi();
            notify(uiText('runtime.paramsResetDone'), 'info');
        });
        el.aspectRatioSelect?.addEventListener('change', () => {
            state.step3PrefsTouched = true;
            state.detailOptions.aspect_ratio = el.aspectRatioSelect.value || 'auto';
            renderEffectiveSummary();
            saveStep3Prefs();
        });
        el.imageSizeSelect?.addEventListener('change', () => {
            state.step3PrefsTouched = true;
            state.detailOptions.image_size = el.imageSizeSelect.value || 'auto';
            syncTryonRoutingUi({ skipRateFetch: true });
        });
        el.qualitySelect?.addEventListener('change', () => {
            state.step3PrefsTouched = true;
            state.detailOptions.quality = el.qualitySelect.value || 'auto';
            renderEffectiveSummary();
            saveStep3Prefs();
        });
        el.temperatureSlider?.addEventListener('input', () => {
            state.step3PrefsTouched = true;
            state.detailOptions.temperature = el.temperatureSlider.value;
            if (el.temperatureInput) el.temperatureInput.value = el.temperatureSlider.value;
            if (el.temperatureVal) el.temperatureVal.textContent = el.temperatureSlider.value;
            renderEffectiveSummary();
            saveStep3Prefs();
        });
        el.temperatureInput?.addEventListener('input', () => {
            state.step3PrefsTouched = true;
            const raw = el.temperatureInput.value.trim();
            if (raw === '') {
                state.detailOptions.temperature = '';
                if (el.temperatureSlider) el.temperatureSlider.value = '1';
                if (el.temperatureVal) el.temperatureVal.textContent = uiText('runtime.tempDefaultPill', undefined, 'Default');
            } else {
                const num = Number(raw);
                if (Number.isFinite(num)) {
                    const clamped = Math.min(2, Math.max(0, Math.round(num * 100) / 100));
                    state.detailOptions.temperature = String(clamped);
                    if (el.temperatureSlider) el.temperatureSlider.value = String(clamped);
                    if (el.temperatureVal) el.temperatureVal.textContent = String(clamped);
                } else {
                    state.detailOptions.temperature = raw;
                }
            }
            renderEffectiveSummary();
            saveStep3Prefs();
        });
        el.temperatureClear?.addEventListener('click', () => {
            state.step3PrefsTouched = true;
            state.detailOptions.temperature = '';
            if (el.temperatureInput) el.temperatureInput.value = '';
            if (el.temperatureSlider) el.temperatureSlider.value = '1';
            if (el.temperatureVal) el.temperatureVal.textContent = uiText('runtime.tempDefaultPill', undefined, 'Default');
            renderEffectiveSummary();
            saveStep3Prefs();
        });
        el.seedInput?.addEventListener('input', () => {
            state.step3PrefsTouched = true;
            const cleaned = el.seedInput.value.replace(/[^\d]/g, '');
            if (el.seedInput.value !== cleaned) el.seedInput.value = cleaned;
            state.detailOptions.seed = cleaned;
            renderEffectiveSummary();
            saveStep3Prefs();
        });
        el.seedRandomBtn?.addEventListener('click', () => {
            state.step3PrefsTouched = true;
            const seedNum = Math.floor(Math.random() * 2147483647);
            state.detailOptions.seed = String(seedNum);
            if (el.seedInput) el.seedInput.value = String(seedNum);
            renderEffectiveSummary();
            saveStep3Prefs();
            notify(uiText('runtime.seedRolled', { seed: seedNum }), 'info');
        });
        el.seedClear?.addEventListener('click', () => {
            state.step3PrefsTouched = true;
            state.detailOptions.seed = '';
            if (el.seedInput) el.seedInput.value = '';
            renderEffectiveSummary();
            saveStep3Prefs();
            notify(uiText('runtime.seedCleared'), 'info');
        });
        el.freedom?.addEventListener('input', () => renderEffectiveSummary());

        syncTryonRoutingUi({ skipRateFetch: true, skipSavePrefs: true });
        refreshRateStatus(true);

        // Sidebar open/close
        const bindSidebar = (toggleBtn, openBtn, closeBtn, overlay, name) => {
            toggleBtn?.addEventListener('click', () => openSidebar(name));
            openBtn?.addEventListener('click', () => openSidebar(name));
            closeBtn?.addEventListener('click', closeAllSidebars);
            overlay?.addEventListener('click', closeAllSidebars);
        };
        bindSidebar(el.errorToggle, null, el.errorClose, el.errorOverlay, 'error');
        document.querySelectorAll('[data-open-sidebar]').forEach(btn => {
            btn.addEventListener('click', () => openSidebar(btn.dataset.openSidebar || 'error'));
        });

        // Error log actions
        el.errorRefresh?.addEventListener('click', refreshErrors);
        el.errorClear?.addEventListener('click', clearErrors);
        el.errorPanelClear?.addEventListener('click', ev => {
            ev.stopPropagation();
            clearErrors();
        });
        el.errorPanelToggle?.addEventListener('click', () => {
            const currentlyExpanded = !(el.errorPanelBody?.classList.contains('hidden'));
            setErrorPanelExpanded(!currentlyExpanded);
        });

        // ESC closes sidebars and dialogs
        document.addEventListener('keydown', ev => {
            if (ev.key !== 'Escape') return;
            closeAllSidebars();
            el.promptModal?.classList.add('hidden');
            document.body.classList.remove('modal-open');
        });
    }

    // ===== Garment Browser Module =====
    const garmentBrowser = (() => {
        let _filters = null;
        let _currentPage = 0;
        const PAGE_SIZE = 24;
        let _currentFilters = { query: '', platform: '', gender: '', style_type: '', color: '', price_min: null, price_max: null };
        let _totalItems = 0;
        let _debounceTimer = null;
        let _filterRequest = 0;
        let _pageRequest = 0;

        function $(id) { return document.getElementById(id); }

        function wbT(key, params) {
            return window.WorkbenchI18n?.t(`legacy.${key}`, params) || key;
        }

        async function fetchFilters() {
            try {
                const lang = window.WorkbenchI18n?.locale || 'zh-CN';
                const resp = await fetch('/api/products/filters?lang=' + encodeURIComponent(lang), { headers: { 'Accept-Language': lang } });
                if (!resp.ok) return null;
                return await resp.json();
            } catch { return null; }
        }

        async function fetchProducts(offset = 0) {
            const params = new URLSearchParams();
            if (_currentFilters.query) params.set('query', _currentFilters.query);
            if (_currentFilters.platform) params.set('platform', _currentFilters.platform);
            if (_currentFilters.gender) params.set('gender', _currentFilters.gender);
            if (_currentFilters.style_type) params.set('style_type', _currentFilters.style_type);
            if (_currentFilters.color) params.set('color', _currentFilters.color);
            if (_currentFilters.price_min != null) params.set('price_min', String(_currentFilters.price_min));
            if (_currentFilters.price_max != null) params.set('price_max', String(_currentFilters.price_max));
            params.set('offset', String(offset));
            params.set('limit', String(PAGE_SIZE));
            params.set('lang', window.WorkbenchI18n?.locale || 'zh-CN');
            try {
                const lang = window.WorkbenchI18n?.locale || 'zh-CN';
                const resp = await fetch(`/api/products?${params.toString()}`, { headers: { 'Accept-Language': lang } });
                if (!resp.ok) return { items: [], total: 0 };
                return await resp.json();
            } catch { return { items: [], total: 0 }; }
        }

        function renderFilterChips(containerId, options, onChange) {
            const container = $(containerId);
            if (!container) return;
            options.forEach(opt => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'filter-chip';
                btn.dataset.value = opt.key || opt;
                btn.textContent = opt.label || opt;
                container.appendChild(btn);
            });
            container.addEventListener('click', (e) => {
                const chip = e.target.closest('.filter-chip');
                if (!chip) return;
                container.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
                chip.classList.add('active');
                onChange(chip.dataset.value || '');
            });
        }

        function renderCard(item) {
            const card = document.createElement('div');
            card.className = 'garment-card';
            card.dataset.id = item.id;
            const imgUrl = item.image_url || '';
            card.innerHTML = `
                <img class="garment-card-img" src="${imgUrl}" alt="" loading="lazy" onerror="this.style.display='none'">
                <div class="garment-card-body">
                    <div class="garment-card-title">${item.title || ''}</div>
                    <div class="garment-card-meta">
                        <span class="garment-card-price">${window.WorkbenchI18n?.formatCurrency ? window.WorkbenchI18n.formatCurrency(item.price || 0) : `¥${item.price || 0}`}</span>
                        <span class="garment-card-tag">${item.platform || ''}</span>
                    </div>
                    <div class="garment-card-tags">
                        ${item.color_family ? `<span class="garment-card-tag">${item.color_family}</span>` : ''}
                        ${item.style_type ? `<span class="garment-card-tag">${item.style_type}</span>` : ''}
                        ${item.gender_label ? `<span class="garment-card-tag">${item.gender_label}</span>` : ''}
                    </div>
                </div>
            `;
            card.addEventListener('click', () => selectGarment(item));
            return card;
        }

        async function selectGarment(item) {
            // Import the selected garment image into the workbench
            const imageUrl = item.image_url || '';
            if (!imageUrl) {
                notify(uiText('runtime.catalogNoImage'), 'warning');
                return;
            }
            try {
                const shortTitle = (item.title || '').slice(0, 20);
                notify(uiText('runtime.catalogImporting', { title: shortTitle }), 'info');
                const result = await importBridgeImage('garment', imageUrl, '');
                state.garments = [result.filename];
                state.garmentCloudUrls = [result.cloud_url || ''];
                updateGarments();
                setUploadIntakeStatus('garment', 'runtime.catalogImported', 'success', { title: (item.title || '').slice(0, 30) });
                // Also update recommendation info
                state.recommendation = state.recommendation || {};
                state.recommendation.productTitle = item.title || '';
                state.recommendation.presentationSource = null;
                state.recommendation.productId = String(item.id || '');
                state.recommendation.productPrice = item.price;
                state.recommendation.styleType = item.style_type || '';
                state.recommendation.colorFamily = item.color_family || '';
                state.recommendation.garmentImageUrl = imageUrl;
                updateRecommendationUi();
                updateCompareStage();
                notify(uiText('runtime.catalogSelected', { title: (item.title || '').slice(0, 25) }), 'success');
                // Highlight selected card
                document.querySelectorAll('.garment-card').forEach(c => c.classList.remove('selected'));
                const selectedCard = document.querySelector(`.garment-card[data-id="${item.id}"]`);
                if (selectedCard) selectedCard.classList.add('selected');
            } catch (e) {
                notify(uiText('runtime.catalogImportFailed', { error: e.message || e }), 'error');
            }
        }

        async function loadPage() {
            const grid = $('garment-grid');
            const countEl = $('garment-grid-count');
            const pageInfo = $('garment-grid-page-info');
            const prevBtn = $('garment-grid-prev');
            const nextBtn = $('garment-grid-next');
            if (!grid) return;

            grid.innerHTML = `<div class="garment-grid-loading"><i class="fas fa-spinner fa-spin"></i> ${wbT('loading')}</div>`;

            const offset = _currentPage * PAGE_SIZE;
            const requestId = ++_pageRequest;
            const data = await fetchProducts(offset);
            if (requestId !== _pageRequest) return;
            _totalItems = data.total || 0;

            if (countEl) countEl.textContent = wbT('productCount', { count: _totalItems });
            const totalPages = Math.max(1, Math.ceil(_totalItems / PAGE_SIZE));
            if (pageInfo) pageInfo.textContent = wbT('page', { page: _currentPage + 1, total: totalPages });
            if (prevBtn) prevBtn.disabled = _currentPage === 0;
            if (nextBtn) nextBtn.disabled = _currentPage >= totalPages - 1;

            grid.innerHTML = '';
            if (!data.items || data.items.length === 0) {
                grid.innerHTML = `<div class="garment-grid-loading">${wbT('noProducts')}</div>`;
                return;
            }
            data.items.forEach(item => grid.appendChild(renderCard(item)));
        }

        function onFilterChange() {
            _currentPage = 0;
            clearTimeout(_debounceTimer);
            _debounceTimer = setTimeout(() => loadPage(), 200);
        }

        async function initFilters() {
            const requestId = ++_filterRequest;
            const filters = await fetchFilters();
            if (requestId !== _filterRequest) return;
            _filters = filters;
            if (!_filters) return;

            // Populate style type chips
            const styleContainer = $('filter-style');
            if (styleContainer && _filters.style_types) {
                styleContainer.querySelectorAll('.filter-chip[data-value]:not([data-value=""])').forEach(chip => chip.remove());
                styleContainer.querySelector('.filter-chip[data-value=""]')?.classList.toggle('active', !_currentFilters.style_type);
                _filters.style_types.forEach(st => {
                    const btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'filter-chip';
                    btn.dataset.value = st.key || st;
                    btn.textContent = st.label || st;
                    btn.classList.toggle('active', btn.dataset.value === _currentFilters.style_type);
                    styleContainer.appendChild(btn);
                });
            }

            // Populate color chips
            const colorContainer = $('filter-color');
            if (colorContainer && _filters.color_families) {
                colorContainer.querySelectorAll('.filter-chip[data-value]:not([data-value=""])').forEach(chip => chip.remove());
                colorContainer.querySelector('.filter-chip[data-value=""]')?.classList.toggle('active', !_currentFilters.color);
                // Only show top colors (limit to avoid overflow)
                const topColors = _filters.color_families.slice(0, 15);
                topColors.forEach(c => {
                    const btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'filter-chip';
                    btn.dataset.value = c.key || c;
                    btn.textContent = c.label || c;
                    btn.classList.toggle('active', btn.dataset.value === _currentFilters.color);
                    colorContainer.appendChild(btn);
                });
            }
        }

        function bindEvents() {
            // Toggle panel
            const toggleBtn = $('garment-browser-toggle');
            const panel = $('garment-browser-panel');
            if (toggleBtn && panel) {
                toggleBtn.addEventListener('click', () => {
                    const isHidden = panel.classList.contains('hidden');
                    panel.classList.toggle('hidden');
                    toggleBtn.classList.toggle('active');
                    if (isHidden && _totalItems === 0) {
                        loadPage();
                    }
                });
            }

            // Search input
            const searchInput = $('garment-search-input');
            if (searchInput) {
                searchInput.addEventListener('input', () => {
                    _currentFilters.query = searchInput.value.trim();
                    onFilterChange();
                });
            }

            // Platform chips
            const platformChips = $('filter-platform');
            if (platformChips) {
                platformChips.addEventListener('click', (e) => {
                    const chip = e.target.closest('.filter-chip');
                    if (!chip) return;
                    platformChips.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
                    chip.classList.add('active');
                    _currentFilters.platform = chip.dataset.value || '';
                    onFilterChange();
                });
            }

            // Gender chips
            const genderChips = $('filter-gender');
            if (genderChips) {
                genderChips.addEventListener('click', (e) => {
                    const chip = e.target.closest('.filter-chip');
                    if (!chip) return;
                    genderChips.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
                    chip.classList.add('active');
                    _currentFilters.gender = chip.dataset.value || '';
                    onFilterChange();
                });
            }

            // Style chips (dynamically populated)
            const styleChips = $('filter-style');
            if (styleChips) {
                styleChips.addEventListener('click', (e) => {
                    const chip = e.target.closest('.filter-chip');
                    if (!chip) return;
                    styleChips.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
                    chip.classList.add('active');
                    _currentFilters.style_type = chip.dataset.value || '';
                    onFilterChange();
                });
            }

            // Color chips (dynamically populated)
            const colorChips = $('filter-color');
            if (colorChips) {
                colorChips.addEventListener('click', (e) => {
                    const chip = e.target.closest('.filter-chip');
                    if (!chip) return;
                    colorChips.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
                    chip.classList.add('active');
                    _currentFilters.color = chip.dataset.value || '';
                    onFilterChange();
                });
            }

            // Price inputs
            const priceMin = $('filter-price-min');
            const priceMax = $('filter-price-max');
            if (priceMin) {
                priceMin.addEventListener('input', () => {
                    const val = parseFloat(priceMin.value);
                    _currentFilters.price_min = isNaN(val) ? null : val;
                    onFilterChange();
                });
            }
            if (priceMax) {
                priceMax.addEventListener('input', () => {
                    const val = parseFloat(priceMax.value);
                    _currentFilters.price_max = isNaN(val) ? null : val;
                    onFilterChange();
                });
            }

            // Pagination
            const prevBtn = $('garment-grid-prev');
            const nextBtn = $('garment-grid-next');
            if (prevBtn) {
                prevBtn.addEventListener('click', () => {
                    if (_currentPage > 0) { _currentPage--; loadPage(); }
                });
            }
            if (nextBtn) {
                nextBtn.addEventListener('click', () => {
                    const totalPages = Math.ceil(_totalItems / PAGE_SIZE);
                    if (_currentPage < totalPages - 1) { _currentPage++; loadPage(); }
                });
            }

            // Refresh
            const refreshBtn = $('garment-grid-refresh');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => loadPage());
            }
        }

        return {
            async init() {
                await initFilters();
                bindEvents();
            },
            async refreshLocale() {
                await initFilters();
                await loadPage();
            },
            loadPage,
        };
    })();

    function applyRuntimeModels(status) {
        const prevName = MODEL_LIMITS[state.modelType]?.name;
        state.runtimeStatus = status || null;
        if (!state.step3PrefsTouched) {
            loadStep3Prefs();
        }
        const providers = Array.isArray(status?.providers) ? status.providers : [];
        const rawLabels = status?.model_labels || {};
        const findModelName = (presetKey, fallbackName) => {
            for (const p of providers) {
                const match = (p.models || []).find(m => m.preset_key === presetKey);
                if (match?.id) return match.id;
            }
            return rawLabels[presetKey] || fallbackName;
        };

        const flashTechName = findModelName('flash', 'Gemini Flash Image');
        const proTechName = findModelName('pro', 'Gemini Pro Image');
        const chatgptModelId = String(status?.chatgpt_model || findModelName('chatgpt', 'gpt-image-2')).trim();
        const chatgptTechName = chatgptModelId ? `ChatGPT Image (${chatgptModelId})` : 'ChatGPT Image';

        if (MODEL_LIMITS.flash) MODEL_LIMITS.flash.name = flashTechName;
        if (MODEL_LIMITS.pro) MODEL_LIMITS.pro.name = proTechName;
        if (MODEL_LIMITS.chatgpt) MODEL_LIMITS.chatgpt.name = chatgptTechName;

        syncTryonRoutingUi({ skipRateFetch: true });

        const nextName = MODEL_LIMITS[state.modelType]?.name;
        if (nextName !== prevName) {
            refreshModelRateUi();
            refreshRateStatus(true);
        } else {
            refreshModelRateUi();
        }
    }

    async function fetchRuntimeStatus(silent = false) {
        try {
            const r = await fetch('/api/runtime-status', { cache: 'no-store' });
            const d = await r.json();
            state.runtimeAvailable = Boolean(
                r.ok && d.tryon_enabled === true && d.configured === true
            );
            applyRuntimeModels(d);
            if (!silent && d.tryon_enabled === false) {
                notify(uiText('runtime.servicePaused'), 'warning');
            } else if (!silent && d.configured === false) {
                notify(uiText('runtime.serviceConfigured'), 'warning');
            }
            ready();
            return Boolean(r.ok);
        } catch (_) {
            state.runtimeAvailable = false;
            if (!silent) notify(uiText('runtime.serviceStatusFailed'), 'warning');
            ready();
            return false;
        }
    }

    const _pendingBridgeEvents = [];
    let _bridgeConfigReady = false;
    window.addEventListener('message', event => {
        if (!_bridgeConfigReady) {
            if (event?.data && typeof event.data === 'object') {
                _pendingBridgeEvents.push(event);
            }
            return;
        }
        void handleBridgeMessage(event);
    });

    async function init() {
        applyCopy();
        state.frontendConfig = normalizeFrontendConfig(FRONTEND_CONFIG_DEFAULT);
        const urlPayload = parseBridgePayloadFromUrl();
        if (urlPayload) {
            state.recommendation = urlPayload;
        }
        initErrorPanelState();
        if (el.parallelToggle) {
            el.parallelToggle.checked = localStorage.getItem(PARALLEL_ENABLED_STORAGE) === '1';
        }
        syncParallelConcurrencyControls(localStorage.getItem(PARALLEL_CONCURRENCY_STORAGE) || PARALLEL_CONCURRENCY_DEFAULT, false);
        if (el.promptSystem) {
            fetch('/prompt').then(r => r.json()).then(d => { el.promptSystem.value = d.prompt || ''; }).catch(() => {
                el.promptSystem.value = uiText('runtime.promptLoadFailed');
            });
        }
        bind();
        initSampleModelPicker();
        updateRecommendationUi();
        syncFreedom();
        syncInterval();
        updateModel();
        updateGarments();
        resetResult();
        renderGallery();
        refreshModelRateUi();
        await fetchFrontendConfig();
        _bridgeConfigReady = true;
        while (_pendingBridgeEvents.length > 0) {
            const queuedEvent = _pendingBridgeEvents.shift();
            void handleBridgeMessage(queuedEvent);
        }
        postBridgeEvent('DOWN_JACKET_TRYON_READY');
        await garmentBrowser.init();
        refreshCountdowns();
        const countdownTimer = setInterval(refreshCountdowns, 1000);
        refreshRateStatus(true);
        const rateTimer = setInterval(() => {
            if (!document.hidden && !state.unloading) refreshRateStatus(true);
        }, 8000);
        refreshErrors();
        await fetchRuntimeStatus();
        const runtimeTimer = setInterval(() => {
            if (!document.hidden && !state.unloading) fetchRuntimeStatus(true);
        }, 15000);
        const stopBackgroundTimers = () => {
            state.unloading = true;
            clearInterval(countdownTimer);
            clearInterval(rateTimer);
            clearInterval(runtimeTimer);
        };
        window.addEventListener('pagehide', stopBackgroundTimers);
        window.addEventListener('beforeunload', stopBackgroundTimers);
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && !state.unloading) {
                refreshRateStatus(true);
                fetchRuntimeStatus(true);
            }
        });
        const pendingSaved = readActiveTask();
        if (pendingSaved && pendingSaved.taskId && !state.running) {
            if (pendingSaved.taskToken) state.taskToken = pendingSaved.taskToken;
            setRunning(true);
            pollTask(pendingSaved.taskId, 0, 1).then(t => {
                if (t) {
                    const url = String(t.result_display_url || t.result_cloud_url || t.result_url || '').trim();
                    if (url) {
                        state.results = [url];
                        state.resultPreviews = [url];
                        showResult(url);
                        renderGallery();
                    }
                }
            }).catch(() => { }).finally(() => setRunning(false));
        }
        if (urlPayload) {
            await applyRecommendationPayload(urlPayload, { channel: 'query' });
        } else {
            setUploadIntakeStatus('model', defaultIntakeStatus('model'), 'neutral');
            setUploadIntakeStatus('garment', defaultIntakeStatus('garment'), 'neutral');
            setResultFeedback('info', 'legacy.feedbackStart', 'legacy.feedbackStartHelp');
        }
        ready();
        const modeParam = new URLSearchParams(window.location.search).get('mode');
        if (window.location.hash === '#section-realtime' || modeParam === 'realtime') {
            document.getElementById('section-realtime')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }

    const start = window.WorkbenchI18n?.ready || Promise.resolve();
    start.then(() => init()).catch(err => {
        notify(err.message || 'Page initialization failed', 'error');
        reportError(err.message || 'Page initialization failed', 'initialization');
    });
    window.addEventListener('localechange', () => {
        applyCopy();
        if (state.runtimeStatus) {
            applyRuntimeModels(state.runtimeStatus);
        } else {
            syncTryonRoutingUi({ skipRateFetch: true, skipSavePrefs: true });
        }
        void garmentBrowser.refreshLocale();
        updateRecommendationUi();
        void localizeLinkedRecommendation();
        updateCompareStage();
        renderGallery();
        Object.entries(state.intakeStatus).forEach(([kind, status]) => setUploadIntakeStatus(kind, status.key, status.tone, status.params));
        if (state.integrationAlert) setIntegrationAlert(state.integrationAlert.key, state.integrationAlert.tone);
        if (state.feedback) setResultFeedback(state.feedback.tone, state.feedback.titleKey, state.feedback.detailKey, state.feedback.params);
        renderErrors();
    });
})();

