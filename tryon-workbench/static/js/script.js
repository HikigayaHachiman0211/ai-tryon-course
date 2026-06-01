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
        running: false,
        abort: false,
        history: [],
        activeHistoryId: '',
        historySelected: new Set(),
        errors: [],
        rateStatus: null,
        minuteResetSec: null,
        dailyResetSec: null,
        extraKeysExpanded: false,
        stylePreset: 'default',
        providerMode: 'direct',
        proxyConfig: null,
        aiStudioConfig: null,
        authUser: '',
        savedKeys: [],
        savedKeySelection: new Set(),
        errorAnalyzing: new Set(),
        recommendation: null,
        frontendConfig: null,
        trustedMessageOrigin: '',
    };

    const MODEL_LIMITS = {
        flash: { name: 'Nano Banana 2', rpm: 100, tpm: 200000, rpd: 1000 },
        pro: { name: 'Nano Banana Pro', rpm: 20, tpm: 100000, rpd: 250 },
    };

    const SAMPLE_MODELS = [
        { id: 'male-donk', name: 'Donk', gender: 'male', filename: 'Donk.webp' },
        { id: 'male-monesy', name: 'Monesy', gender: 'male', filename: 'Monesy.webp' },
        { id: 'male-niko', name: 'Niko', gender: 'male', filename: 'Niko.webp' },
        { id: 'male-leave7', name: 'Leave7', gender: 'male', filename: 'OA-Leave7.jpg' },
        { id: 'male-zywoo', name: 'ZywOo', gender: 'male', filename: 'ZywOo.webp' },
        { id: 'female-liyuu1', name: 'Liyuu 1', gender: 'female', filename: 'Liyuu_1.jpg' },
        { id: 'female-liyuu2', name: 'Liyuu 2', gender: 'female', filename: 'Liyuu_2.jpg' },
        { id: 'female-liyuu3', name: 'Liyuu 3', gender: 'female', filename: 'Liyuu_3.jpg' },
    ];

    const $ = id => document.getElementById(id);
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
        apiKey: $('api-key'),
        extraKeysWrap: $('extra-api-keys'),
        extraKey2: $('api-key-2'),
        extraKey3: $('api-key-3'),
        extraKey4: $('api-key-4'),
        extraKey5: $('api-key-5'),
        toggleExtraKeys: $('toggle-extra-keys'),
        fillSavedKeysBtn: $('fill-saved-keys-btn'),
        nanoKey: $('nanobanana-api-key'),
        nanoSave: $('nanobanana-save-btn'),
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
        stylePresets: $('style-presets'),
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
        authForm: $('auth-form'),
        authStatus: $('auth-status'),
        authUsername: $('auth-username'),
        authPassword: $('auth-password'),
        authError: $('auth-error'),
        authLoginBtn: $('auth-login-btn'),
        authRegisterBtn: $('auth-register-btn'),
        authLogoutBtn: $('auth-logout-btn'),
        authUsernameDisplay: $('auth-username-display'),
        manageKeysBtn: $('manage-keys-btn'),
        keysModalOverlay: $('keys-modal-overlay'),
        keysModalClose: $('keys-modal-close'),
        savedKeysList: $('saved-keys-list'),
        newKeyName: $('new-key-name'),
        newKeyValue: $('new-key-value'),
        addKeyBtn: $('add-key-btn'),
        addKeyError: $('add-key-error'),
        keysFillSelected: $('keys-fill-selected'),
        keysFillAll: $('keys-fill-all'),

        // Sidebar toggles
        historyToggle: $('history-toggle-btn'),
        openHistory: $('open-history-btn'),
        usageToggle: $('usage-toggle-btn'),
        errorToggle: $('errorlog-toggle-btn'),
        nanobananaToggle: $('nanobanana-toggle-btn'),
        vertexToggle: $('vertex-toggle-btn'),
        aistudioToggle: $('aistudio-toggle-btn'),
        proxyToggle: $('proxy-toggle-btn'),

        // Sidebars
        historySidebar: $('history-sidebar'),
        historyOverlay: $('history-overlay'),
        historyClose: $('history-sidebar-close'),
        usageSidebar: $('usage-sidebar'),
        usageOverlay: $('usage-overlay'),
        usageClose: $('usage-sidebar-close'),
        errorSidebar: $('errorlog-sidebar'),
        errorOverlay: $('errorlog-overlay'),
        errorClose: $('errorlog-sidebar-close'),
        nanobananaSidebar: $('nanobanana-sidebar'),
        nanobananaOverlay: $('nanobanana-overlay'),
        nanobananaClose: $('nanobanana-sidebar-close'),
        vertexSidebar: $('vertex-sidebar'),
        vertexOverlay: $('vertex-overlay'),
        vertexClose: $('vertex-sidebar-close'),
        aistudioSidebar: $('aistudio-sidebar'),
        aistudioOverlay: $('aistudio-overlay'),
        aistudioClose: $('aistudio-sidebar-close'),
        proxySidebar: $('proxy-sidebar'),
        proxyOverlay: $('proxy-overlay'),
        proxyClose: $('proxy-sidebar-close'),

        // Local proxy config
        proxyEnabled: $('proxy-enabled'),
        proxyBaseUrl: $('proxy-base-url'),
        proxyApiKey: $('proxy-api-key'),
        proxyTimeout: $('proxy-timeout'),
        proxyFlashModel: $('proxy-flash-model'),
        proxyProModel: $('proxy-pro-model'),
        proxySave: $('proxy-save-btn'),
        proxyTest: $('proxy-test-btn'),
        proxyTestResult: $('proxy-test-result'),
        aistudioApiKey: $('aistudio-api-key'),
        aistudioFlashModel: $('aistudio-flash-model'),
        aistudioProModel: $('aistudio-pro-model'),
        aistudioSave: $('aistudio-save-btn'),
        providerSelector: $('provider-selector'),
        providerHint: $('provider-mode-hint'),

        // Usage query
        usageKeyA: $('usage-query-key'),
        usageBtnA: $('usage-query-btn'),
        usageResA: $('usage-query-result'),
        usageKeyB: $('usage-sidebar-key'),
        usageBtnB: $('usage-sidebar-query-btn'),
        usageResB: $('usage-sidebar-result'),

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

        // History views
        historyBadge: $('history-badge'),
        historyListView: $('history-list-view'),
        historyDetailView: $('history-detail-view'),
        historyList: $('history-list'),
        historyBack: $('history-back-btn'),
        historyTime: $('history-detail-time'),
        historyRef: $('history-ref-images'),
        historyTgt: $('history-tgt-images'),
        historyGen: $('history-gen-images'),
        historyGenCount: $('history-gen-count'),
        historyClearAll: $('history-clear-all'),
        historyDelete: $('history-delete-session'),
        historyDownloadAll: $('history-download-all'),
        historyDownloadSelected: $('history-download-selected'),
        historySelCount: $('history-sel-count'),

        // Vertex
        vertexFile: $('vertex-key-file'),
        vertexSave: $('vertex-save-btn'),
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
        cycleStyleBtn: $('cycle-style-btn'),
        saveHistoryBtn: $('save-history-btn'),
    };

    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const clamp = (n, min, max) => Math.max(min, Math.min(max, n));
    const EXTRA_KEYS_STORAGE = 'tryon_api_keys_extra_v1';
    const EXTRA_KEYS_EXPANDED_STORAGE = 'tryon_api_keys_expanded_v1';
    const STYLE_STORAGE = 'tryon_style_preset_v1';
    const PROVIDER_MODE_STORAGE = 'tryon_provider_mode_v1';
    const PARALLEL_ENABLED_STORAGE = 'tryon_parallel_enabled_v1';
    const PARALLEL_CONCURRENCY_STORAGE = 'tryon_parallel_concurrency_v1';
    const PARALLEL_CONCURRENCY_MIN = 2;
    const PARALLEL_CONCURRENCY_MAX = 20;
    const PARALLEL_CONCURRENCY_DEFAULT = 3;
    const AUTH_USERS_STORAGE = 'tryon_auth_users_v1';
    const AUTH_CURRENT_STORAGE = 'tryon_auth_current_v1';
    const USER_KEYS_PREFIX = 'tryon_user_keys_';
    const ERROR_PANEL_EXPANDED_STORAGE = 'tryon_error_panel_expanded_v1';
    const HISTORY_TTL_MS = 24 * 60 * 60 * 1000;
    const BRIDGE_SOURCE = 'down-jacket-recommendation';
    const BRIDGE_MESSAGE_TYPES = ['DOWN_JACKET_TRYON_INIT', 'RECOMMENDATION_TRYON_INIT'];
    const FRONTEND_CONFIG_DEFAULT = {
        recommend_app_url: '',
        tryon_embed_mode: 'standalone',
    };
    const STYLE_PRESETS = {
        default: { name: '推荐同款还原', prompt: 'Render a premium winter fashion try-on that faithfully preserves identity, garment silhouette, down volume, quilting detail, hardware, and the recommended color balance.' },
        urban: { name: '都市通勤', prompt: 'Style the down jacket as polished winter commute photography with refined city context, crisp daylight, and practical premium styling.' },
        minimal: { name: '高级极简', prompt: 'Create a quiet luxury winter look with restrained palette, precise silhouette, premium fabric texture, and minimalist editorial framing.' },
        outdoor: { name: '轻户外', prompt: 'Add a light outdoor winter atmosphere with natural daylight, breathable layering, and functional outerwear styling while keeping the garment accurate.' },
        street: { name: '冬季街头', prompt: 'Give the outfit contemporary winter street energy with realistic city texture and confident styling while preserving the down jacket design.' },
        layered: { name: '轻薄内搭', prompt: 'Emphasize balanced winter layering, a slimmer silhouette, and refined inner-layer detail at the collar and cuffs.' },
        puffer: { name: '面包服氛围', prompt: 'Highlight plush puffer volume, soft loft, tactile quilting, and cozy premium winter styling while keeping garment structure faithful.' },
        editorial: { name: '杂志大片', prompt: 'Render as a luxury fashion magazine editorial with premium set design, crisp lighting, and high-end outerwear campaign composition.' },
        cinematic: { name: '电影质感', prompt: 'Use cinematic lighting and dramatic film-style color grading while preserving identity and garment details.' },
        anime: { name: '二次元融合', prompt: 'Blend stylized anime aesthetics with realistic identity and garment structure.' },
        fantasy: { name: '奇幻史诗', prompt: 'Add epic fantasy atmosphere, magical scene accents, and volumetric light.' },
        cyberpunk: { name: '赛博朋克', prompt: 'Add cyberpunk neon city mood, futuristic tone, and high-contrast lighting.' },
        elegant: { name: '优雅写真', prompt: 'Render as elegant fashion editorial photography with premium magazine quality.' },
    };
    const STYLE_CYCLE_ORDER = Object.keys(STYLE_PRESETS);

    function asTrimmedString(value) {
        return String(value ?? '').trim();
    }

    function safeText(value, fallback = '待传入') {
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
        const n = Number(value);
        return Number.isFinite(n) ? n : null;
    }

    function formatPrice(value) {
        const text = asTrimmedString(value);
        if (!text) return '待传入';
        const n = numericOrNull(text);
        if (n == null) return text;
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

    function isTrustedBridgeOrigin(origin) {
        const current = asTrimmedString(origin);
        if (!current) return true;
        const trusted = asTrimmedString(state.trustedMessageOrigin || recommendOriginFromConfig());
        return !trusted || trusted === current;
    }

    function normalizeBridgePayload(raw) {
        if (!raw || typeof raw !== 'object') return null;
        const payload = {
            source: asTrimmedString(raw.source) || BRIDGE_SOURCE,
            userImageUrl: asTrimmedString(raw.userImageUrl || raw.userImage || raw.modelImageUrl),
            userImageDataUrl: asTrimmedString(raw.userImageDataUrl || raw.userImageBase64 || raw.userImageData || raw.modelImageDataUrl),
            garmentImageUrl: asTrimmedString(raw.garmentImageUrl || raw.referenceImageUrl || raw.productImageUrl),
            garmentImageDataUrl: asTrimmedString(raw.garmentImageDataUrl || raw.referenceImageDataUrl || raw.productImageDataUrl || raw.garmentImageBase64),
            productTitle: asTrimmedString(raw.productTitle),
            productId: asTrimmedString(raw.productId),
            productPrice: raw.productPrice ?? '',
            styleType: asTrimmedString(raw.styleType),
            colorFamily: asTrimmedString(raw.colorFamily),
            sizeHint: asTrimmedString(raw.sizeHint),
            recommendationReason: asTrimmedString(raw.recommendationReason),
            score: raw.score ?? '',
            returnUrl: asTrimmedString(raw.returnUrl || raw.recommendationUrl),
            sceneHint: asTrimmedString(raw.sceneHint || raw.scene || raw.occasionHint),
            fitNote: asTrimmedString(raw.fitNote || raw.silhouetteNote),
            productUrl: asTrimmedString(raw.productUrl || raw.product_url),
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
            ? '支持自动接收推荐系统传来的用户全身照；若自动注入失败，会明确提示重新上传。'
            : '优先导入推荐系统传来的商品图；未收到推荐图时自动回退为手动上传模式。';
    }

    function setUploadIntakeStatus(kind, text, tone = 'neutral') {
        const node = kind === 'model' ? el.targetIntakeStatus : el.garmentIntakeStatus;
        if (!node) return;
        node.textContent = asTrimmedString(text) || defaultIntakeStatus(kind);
        node.dataset.tone = tone;
    }

    function setIntegrationAlert(message, tone = 'info') {
        if (!el.integrationAlert) return;
        const text = asTrimmedString(message);
        el.integrationAlert.textContent = text;
        el.integrationAlert.dataset.tone = tone;
        el.integrationAlert.classList.toggle('hidden', !text);
    }

    function setResultFeedback(tone, title, detail = '') {
        if (!el.resultFeedback) return;
        const heading = asTrimmedString(title);
        const body = asTrimmedString(detail);
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
        updateCompareImage(el.compareUserImg, el.compareUserPlaceholder, _modelDisplayUrl(), '等待用户全身照');
        updateCompareImage(el.compareGarmentImg, el.compareGarmentPlaceholder, _garmentDisplayUrl(0), '等待羽绒服商品图');
        updateCompareImage(el.compareResultImg, el.compareResultPlaceholder, getResultPreviewUrl(0), '生成后自动展示');
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
        const priceText = linked ? formatPrice(payload.productPrice) : '待传入';
        const scoreText = linked ? formatScore(payload.score) : '--';
        const styleText = linked ? safeText(payload.styleType) : '待传入';
        const colorText = linked ? safeText(payload.colorFamily) : '待传入';
        const sizeText = linked ? safeText(payload.sizeHint) : '待传入';
        const titleText = linked ? safeText(payload.productTitle, '已接收推荐商品') : '等待推荐系统传入羽绒服商品';
        const idText = linked ? safeText(payload.productId, '商品 ID 待传入') : '商品 ID 待传入';
        const reasonText = linked
            ? safeText(payload.recommendationReason, '推荐系统未附带推荐理由。')
            : '等待推荐系统传入本次商品摘要。未联动时也可直接上传用户图与羽绒服商品图进行手动试穿。';
        const sceneText = linked
            ? safeText(payload.sceneHint, '已从推荐结果进入当前试穿工作台')
            : '适合场景待补充';

        if (el.recommendationEntryBanner) el.recommendationEntryBanner.classList.toggle('hidden', !linked);
        if (el.heroSourceTag) el.heroSourceTag.textContent = linked ? '已接入推荐链路' : '手动上传模式';
        if (el.heroProductTitle) el.heroProductTitle.textContent = titleText;
        if (el.heroSubtitle) {
            el.heroSubtitle.textContent = linked
                ? '已同步推荐商品摘要、用户图与商品图。你可以直接微调风格并开始试穿。'
                : '优先读取推荐系统传来的用户全身照与商品图，自动预填后直接进入试穿流程；若未传值，则回退到手动上传模式。';
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
                el.heroProductUrl.textContent = '🛒 去选购';
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

    async function importBridgeImage(kind, imageUrl, imageDataUrl) {
        const r = await fetch('/api/intake-image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source: state.recommendation?.source || BRIDGE_SOURCE,
                role: kind,
                image_url: asTrimmedString(imageUrl),
                image_data_url: asTrimmedString(imageDataUrl),
            }),
        });
        const d = await r.json().catch(() => ({}));
        if (!r.ok || !d?.ok || !d?.filename) {
            throw new Error(d?.error || '自动导入失败');
        }
        return { filename: d.filename, cloud_url: d.cloud_url || '' };
    }

    let _applyGen = 0;
    let _lastAppliedPayloadKey = '';

    async function applyRecommendationPayload(rawPayload, meta = {}) {
        const payload = normalizeBridgePayload(rawPayload);
        if (!payload) return;

        // Deduplicate: skip if same payload already applied (postMessage retries)
        const payloadKey = JSON.stringify([payload.userImageUrl, payload.userImageDataUrl, payload.garmentImageUrl, payload.garmentImageDataUrl]);
        if (payloadKey === _lastAppliedPayloadKey && state.model) return;
        _lastAppliedPayloadKey = payloadKey;

        // Generation counter: if a newer call starts, earlier calls discard their results
        const gen = ++_applyGen;

        state.recommendation = payload;
        if (asTrimmedString(meta.origin)) state.trustedMessageOrigin = asTrimmedString(meta.origin);
        state.results = [];
        state.resultPreviews = [];
        state.selected.clear();
        resetResult();
        renderGallery();
        updateRecommendationUi();

        if (el.garmentTypeInput && !asTrimmedString(el.garmentTypeInput.value)) {
            el.garmentTypeInput.value = '外套';
        }

        let modelReady = Boolean(state.model);
        let garmentReady = state.garments.length > 0;

        if (payload.userImageUrl || payload.userImageDataUrl) {
            state.model = '';
            state.modelCloudUrl = '';
            updateModel();
            setUploadIntakeStatus('model', '正在自动导入推荐系统传来的用户全身照...', 'loading');
            try {
                const modelResult = await importBridgeImage('model', payload.userImageUrl, payload.userImageDataUrl);
                if (gen !== _applyGen) return; // superseded by newer call
                state.model = modelResult.filename;
                state.modelCloudUrl = modelResult.cloud_url;
                modelReady = true;
                updateModel();
                setUploadIntakeStatus('model', '已自动导入推荐系统用户全身照。', 'success');
            } catch (e) {
                if (gen !== _applyGen) return;
                state.model = '';
                state.modelCloudUrl = '';
                modelReady = false;
                updateModel();
                setUploadIntakeStatus('model', `自动导入失败：${e.message || e}。请重新上传用户全身照。`, 'error');
                notify('推荐用户图自动导入失败，请重新上传。', 'warning');
                reportError(e.message || '推荐用户图自动导入失败', '推荐联动-用户图');
            }
        } else if (!state.model) {
            setUploadIntakeStatus('model', '推荐系统未提供用户图，请手动上传用户全身照。', 'warning');
        } else {
            setUploadIntakeStatus('model', '未收到新的用户图，继续沿用当前全身照。', 'info');
        }

        if (payload.garmentImageUrl || payload.garmentImageDataUrl) {
            state.garments = [];
            state.garmentCloudUrls = [];
            updateGarments();
            setUploadIntakeStatus('garment', '正在自动导入推荐商品图...', 'loading');
            try {
                const garmentResult = await importBridgeImage('garment', payload.garmentImageUrl, payload.garmentImageDataUrl);
                if (gen !== _applyGen) return; // superseded by newer call
                state.garments = [garmentResult.filename];
                state.garmentCloudUrls = [garmentResult.cloud_url];
                garmentReady = true;
                updateGarments();
                setUploadIntakeStatus('garment', '已自动导入推荐商品图。', 'success');
            } catch (e) {
                if (gen !== _applyGen) return;
                state.garments = [];
                state.garmentCloudUrls = [];
                garmentReady = false;
                updateGarments();
                setUploadIntakeStatus('garment', `自动导入失败：${e.message || e}。请重新上传羽绒服商品图。`, 'error');
                notify('推荐商品图自动导入失败，请重新上传。', 'warning');
                reportError(e.message || '推荐商品图自动导入失败', '推荐联动-商品图');
            }
        } else if (state.garments.length === 0) {
            setUploadIntakeStatus('garment', '推荐系统未提供商品图，请手动上传羽绒服商品图。', 'warning');
        } else {
            setUploadIntakeStatus('garment', '未收到新的商品图，继续沿用当前羽绒服图片。', 'info');
        }

        setIntegrationAlert(
            '已从羽绒服推荐结果进入试穿。若用户图或商品图未能自动注入，页面会明确提示你重新上传，而不会静默失败。',
            'info'
        );

        if (modelReady && garmentReady) {
            setResultFeedback('info', '推荐链路已接通', '用户全身照与羽绒服商品图已预填，可以直接开始生成试穿结果。');
        } else {
            const missing = [];
            if (!modelReady) missing.push('用户全身照');
            if (!garmentReady) missing.push('羽绒服商品图');
            setResultFeedback('warning', '推荐链路已接通，但仍需补齐素材', `${missing.join('、')} 未成功自动导入，请根据卡片提示重新上传后再开始试穿。`);
        }

        updateCompareStage();
        ready();
        notify('推荐系统联动信息已同步到试穿工作台。', 'success');
    }

    function bridgeTargetWindow() {
        if (window.opener && !window.opener.closed) return window.opener;
        if (window.parent && window.parent !== window) return window.parent;
        return null;
    }

    function postBridgeEvent(type) {
        const target = bridgeTargetWindow();
        if (!target) return false;
        const origin = asTrimmedString(state.trustedMessageOrigin || recommendOriginFromConfig()) || '*';
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
        const url = asTrimmedString(state.recommendation?.returnUrl || state.frontendConfig?.recommend_app_url);
        postBridgeEvent(mode === 'switch' ? 'DOWN_JACKET_TRYON_SWITCH_REQUEST' : 'DOWN_JACKET_TRYON_BACK');
        if (url) {
            window.location.href = url;
            return;
        }
        if (window.history.length > 1) {
            window.history.back();
            return;
        }
        notify('未配置推荐列表地址。', 'warning');
    }

    function cycleStylePreset() {
        const currentIndex = STYLE_CYCLE_ORDER.indexOf(state.stylePreset);
        const next = STYLE_CYCLE_ORDER[(currentIndex + 1 + STYLE_CYCLE_ORDER.length) % STYLE_CYCLE_ORDER.length] || 'default';
        setStylePreset(next);
    }

    async function handleBridgeMessage(event) {
        if (!isTrustedBridgeOrigin(event.origin)) return;
        const data = event?.data;
        if (!data || typeof data !== 'object') return;
        const type = asTrimmedString(data.type).toUpperCase();
        const rawPayload = (data.payload && typeof data.payload === 'object') ? data.payload : data;
        const payload = normalizeBridgePayload(rawPayload);
        if (!payload) return;
        if (type && !BRIDGE_MESSAGE_TYPES.includes(type) && payload.source !== BRIDGE_SOURCE) return;
        try {
            await applyRecommendationPayload(payload, { channel: 'postMessage', origin: event.origin });
        } catch (e) {
            notify(e.message || '推荐系统联动失败', 'error');
            reportError(e.message || '推荐系统联动失败', '推荐联动-postMessage');
        }
    }

    function getExtraInputs() {
        return [el.extraKey2, el.extraKey3, el.extraKey4, el.extraKey5].filter(Boolean);
    }

    function normalizeKeyList(keys) {
        const seen = new Set();
        const out = [];
        (keys || []).forEach(k => {
            const key = String(k || '').trim();
            if (!key || seen.has(key)) return;
            seen.add(key);
            out.push(key);
        });
        return out;
    }

    function readExtraApiKeysFromInputs() {
        return normalizeKeyList(getExtraInputs().map(input => input?.value || ''));
    }

    function writeExtraApiKeysToInputs(keys) {
        const arr = normalizeKeyList(keys).slice(0, 4);
        const inputs = getExtraInputs();
        for (let i = 0; i < inputs.length; i++) {
            inputs[i].value = arr[i] || '';
        }
    }

    function maskApiKey(key) {
        const k = String(key || '').trim();
        if (!k) return 'N/A';
        if (k.length <= 8) return `${k.slice(0, 2)}***${k.slice(-2)}`;
        return `${k.slice(0, 4)}...${k.slice(-4)}`;
    }

    function getApiKeyPool() {
        const primary = (el.apiKey?.value || '').trim();
        const extra = readExtraApiKeysFromInputs();
        const keys = [];
        if (primary) keys.push(primary);
        keys.push(...extra);
        return normalizeKeyList(keys);
    }

    function saveExtraApiKeys() {
        const extra = readExtraApiKeysFromInputs();
        localStorage.setItem(EXTRA_KEYS_STORAGE, JSON.stringify(extra));
    }

    function updateExtraKeysToggleLabel() {
        if (!el.toggleExtraKeys) return;
        const extraCount = readExtraApiKeysFromInputs().length;
        const expanded = Boolean(state.extraKeysExpanded);
        if (expanded) {
            el.toggleExtraKeys.innerHTML = `<i class="fas fa-minus"></i> 收起额外 API Key（已启用 ${extraCount} 个）`;
        } else {
            el.toggleExtraKeys.innerHTML = '<i class="fas fa-plus"></i> 添加更多 API Key（分散限额）';
        }
    }

    function setExtraKeysExpanded(expanded) {
        state.extraKeysExpanded = Boolean(expanded);
        if (el.extraKeysWrap) el.extraKeysWrap.classList.toggle('hidden', !state.extraKeysExpanded);
        localStorage.setItem(EXTRA_KEYS_EXPANDED_STORAGE, state.extraKeysExpanded ? '1' : '0');
        updateExtraKeysToggleLabel();
    }

    function loadExtraApiKeys() {
        let keys = [];
        try {
            keys = JSON.parse(localStorage.getItem(EXTRA_KEYS_STORAGE) || '[]');
        } catch (_) {
            keys = [];
        }
        writeExtraApiKeysToInputs(Array.isArray(keys) ? keys : []);
        const expanded = localStorage.getItem(EXTRA_KEYS_EXPANDED_STORAGE) === '1';
        setExtraKeysExpanded(expanded);
    }

    function readJsonStorage(key, fallback) {
        try {
            const raw = localStorage.getItem(key);
            if (!raw) return fallback;
            const parsed = JSON.parse(raw);
            return parsed == null ? fallback : parsed;
        } catch (_) {
            return fallback;
        }
    }

    function writeJsonStorage(key, value) {
        localStorage.setItem(key, JSON.stringify(value));
    }

    function normalizeUsername(username) {
        return String(username || '').trim();
    }

    function authUsers() {
        const users = readJsonStorage(AUTH_USERS_STORAGE, {});
        return (users && typeof users === 'object') ? users : {};
    }

    function saveAuthUsers(users) {
        writeJsonStorage(AUTH_USERS_STORAGE, users || {});
    }

    function userKeysStorageKey() {
        const user = normalizeUsername(state.authUser);
        return `${USER_KEYS_PREFIX}${user || 'guest'}_v1`;
    }

    function updateAuthUi() {
        const loggedIn = Boolean(state.authUser);
        if (el.authForm) el.authForm.classList.toggle('hidden', loggedIn);
        if (el.authStatus) el.authStatus.classList.toggle('hidden', !loggedIn);
        if (el.authUsernameDisplay) el.authUsernameDisplay.textContent = loggedIn ? state.authUser : '';
        if (el.fillSavedKeysBtn) el.fillSavedKeysBtn.classList.toggle('hidden', !loggedIn || state.savedKeys.length === 0);
    }

    function setAuthError(message) {
        if (!el.authError) return;
        const msg = String(message || '').trim();
        el.authError.textContent = msg;
        el.authError.classList.toggle('hidden', !msg);
    }

    function loadSavedKeys() {
        const list = readJsonStorage(userKeysStorageKey(), []);
        state.savedKeys = Array.isArray(list) ? list : [];
        state.savedKeySelection.clear();
    }

    function saveSavedKeys() {
        writeJsonStorage(userKeysStorageKey(), state.savedKeys);
    }

    function fillApiInputsFromKeys(keys) {
        const arr = normalizeKeyList(keys).slice(0, 5);
        const slots = [el.apiKey, ...getExtraInputs()];
        for (let i = 0; i < slots.length; i++) {
            if (slots[i]) slots[i].value = arr[i] || '';
        }
        onAnyApiKeyChanged();
    }

    function renderSavedKeysList() {
        if (!el.savedKeysList) return;
        if (!state.authUser) {
            el.savedKeysList.innerHTML = '<div class="usage-empty">请先登录后管理 API Key</div>';
            if (el.keysFillSelected) el.keysFillSelected.disabled = true;
            if (el.keysFillAll) el.keysFillAll.disabled = true;
            return;
        }
        if (state.savedKeys.length === 0) {
            el.savedKeysList.innerHTML = '<div class="usage-empty">暂无已保存 Key</div>';
            if (el.keysFillSelected) el.keysFillSelected.disabled = true;
            if (el.keysFillAll) el.keysFillAll.disabled = true;
            return;
        }
        el.savedKeysList.innerHTML = state.savedKeys.map(item => `
            <label class="saved-key-row" style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.08);">
                <input type="checkbox" data-key-select="${item.id}" ${state.savedKeySelection.has(item.id) ? 'checked' : ''}>
                <div style="flex:1;min-width:0;">
                    <div style="font-size:12px;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${item.name || '未命名 Key'}</div>
                    <div style="font-size:11px;color:rgba(255,255,255,0.6);">${maskApiKey(item.key)}</div>
                </div>
                <button type="button" data-key-del="${item.id}" class="errorlog-action-btn danger" style="padding:4px 8px;">删除</button>
            </label>
        `).join('');

        [...el.savedKeysList.querySelectorAll('[data-key-select]')].forEach(node => {
            node.addEventListener('change', () => {
                const id = node.getAttribute('data-key-select') || '';
                if (!id) return;
                if (node.checked) state.savedKeySelection.add(id);
                else state.savedKeySelection.delete(id);
                if (el.keysFillSelected) {
                    el.keysFillSelected.disabled = state.savedKeySelection.size === 0;
                }
            });
        });
        [...el.savedKeysList.querySelectorAll('[data-key-del]')].forEach(node => {
            node.addEventListener('click', () => {
                const id = node.getAttribute('data-key-del') || '';
                if (!id) return;
                state.savedKeys = state.savedKeys.filter(item => item.id !== id);
                state.savedKeySelection.delete(id);
                saveSavedKeys();
                renderSavedKeysList();
                updateAuthUi();
            });
        });
        if (el.keysFillSelected) el.keysFillSelected.disabled = state.savedKeySelection.size === 0;
        if (el.keysFillAll) el.keysFillAll.disabled = state.savedKeys.length === 0;
    }

    function openKeysModal() {
        if (!state.authUser) {
            notify('请先登录后再管理 API Key。', 'warning');
            return;
        }
        if (!el.keysModalOverlay) return;
        if (el.addKeyError) {
            el.addKeyError.textContent = '';
            el.addKeyError.classList.add('hidden');
        }
        renderSavedKeysList();
        el.keysModalOverlay.classList.remove('hidden');
    }

    function closeKeysModal() {
        el.keysModalOverlay?.classList.add('hidden');
    }

    function setAddKeyError(message) {
        if (!el.addKeyError) return;
        const msg = String(message || '').trim();
        el.addKeyError.textContent = msg;
        el.addKeyError.classList.toggle('hidden', !msg);
    }

    function addSavedKey() {
        if (!state.authUser) {
            setAddKeyError('请先登录后再保存 Key');
            return;
        }
        const key = String(el.newKeyValue?.value || '').trim();
        const name = String(el.newKeyName?.value || '').trim();
        if (!key) {
            setAddKeyError('请输入 API Key');
            return;
        }
        if (state.savedKeys.some(item => String(item.key || '').trim() === key)) {
            setAddKeyError('该 API Key 已存在');
            return;
        }
        if (state.savedKeys.length >= 50) {
            setAddKeyError('最多可保存 50 个 API Key');
            return;
        }

        const id = `key_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
        const nextName = name || `接口密钥 #${state.savedKeys.length + 1}`;
        state.savedKeys.unshift({
            id,
            name: nextName.slice(0, 50),
            key,
            createdAt: Date.now(),
        });
        state.savedKeySelection.add(id);
        saveSavedKeys();
        renderSavedKeysList();
        updateAuthUi();
        if (el.newKeyName) el.newKeyName.value = '';
        if (el.newKeyValue) el.newKeyValue.value = '';
        setAddKeyError('');
        notify('API Key 已保存', 'success');
    }

    function getSelectedSavedKeyValues() {
        if (state.savedKeySelection.size === 0) return [];
        const byId = new Map(state.savedKeys.map(item => [item.id, String(item.key || '').trim()]));
        return normalizeKeyList(
            [...state.savedKeySelection]
                .map(id => byId.get(id) || '')
                .filter(Boolean)
        );
    }

    function fillSavedKeysToInputs(fillAll = false) {
        if (!state.authUser) {
            notify('请先登录后再填充 Key。', 'warning');
            return;
        }
        const keys = fillAll
            ? normalizeKeyList(state.savedKeys.map(item => item.key))
            : getSelectedSavedKeyValues();
        if (!keys.length) {
            notify(fillAll ? '暂无可填充的 Key。' : '请先勾选要填充的 Key。', 'warning');
            return;
        }
        fillApiInputsFromKeys(keys);
        notify(`已填充 ${Math.min(keys.length, 5)} 个 Key 到输入框。`, 'success');
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

    function onAnyApiKeyChanged() {
        localStorage.setItem('tryon_api_key', (el.apiKey?.value || '').trim());
        saveExtraApiKeys();
        updateExtraKeysToggleLabel();
        renderProviderCards();
        refreshRateStatus(true);
    }

    function initAuthState() {
        state.authUser = normalizeUsername(localStorage.getItem(AUTH_CURRENT_STORAGE) || '');
        loadSavedKeys();
        updateAuthUi();
    }

    function loginUser() {
        const username = normalizeUsername(el.authUsername?.value || '');
        const password = String(el.authPassword?.value || '');
        if (!username || !password) {
            setAuthError('请输入用户名和密码');
            return;
        }
        const users = authUsers();
        if (!users[username] || users[username].password !== password) {
            setAuthError('用户名或密码错误');
            return;
        }
        state.authUser = username;
        localStorage.setItem(AUTH_CURRENT_STORAGE, username);
        loadSavedKeys();
        loadHistory();
        renderHistoryList();
        updateAuthUi();
        setAuthError('');
        notify(`欢迎回来，${username}`, 'success');
    }

    function registerUser() {
        const username = normalizeUsername(el.authUsername?.value || '');
        const password = String(el.authPassword?.value || '');
        if (username.length < 3 || password.length < 4) {
            setAuthError('用户名至少 3 位，密码至少 4 位');
            return;
        }
        const users = authUsers();
        if (users[username]) {
            setAuthError('用户名已存在');
            return;
        }
        users[username] = { password, createdAt: Date.now() };
        saveAuthUsers(users);
        setAuthError('');
        notify('注册成功，请登录', 'success');
    }

    function logoutUser() {
        state.authUser = '';
        localStorage.removeItem(AUTH_CURRENT_STORAGE);
        loadSavedKeys();
        closeKeysModal();
        loadHistory();
        renderHistoryList();
        updateAuthUi();
        notify('已退出登录', 'info');
    }

    function normalizeStyle(style) {
        return Object.prototype.hasOwnProperty.call(STYLE_PRESETS, style) ? style : 'default';
    }

    function setStylePreset(style, silent = false) {
        state.stylePreset = normalizeStyle(style);
        localStorage.setItem(STYLE_STORAGE, state.stylePreset);
        const cards = [...document.querySelectorAll('#style-presets .style-card')];
        cards.forEach(card => card.classList.toggle('active', card.dataset.style === state.stylePreset));
        if (!silent) {
            const label = STYLE_PRESETS[state.stylePreset]?.name || '经典还原';
            notify(`已切换生成风格：${label}`, 'info');
        }
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

    function readProxyConfigFromUi() {
        return {
            enabled: Boolean(el.proxyEnabled?.checked),
            base_url: String(el.proxyBaseUrl?.value || '').trim(),
            api_key: String(el.proxyApiKey?.value || '').trim(),
            timeout_seconds: Number(el.proxyTimeout?.value || '180') || 180,
            flash_model: String(el.proxyFlashModel?.value || '').trim(),
            pro_model: String(el.proxyProModel?.value || '').trim(),
        };
    }

    function readAiStudioConfigFromUi() {
        return {
            api_key: String(el.aistudioApiKey?.value || '').trim(),
            flash_model: String(el.aistudioFlashModel?.value || '').trim(),
            pro_model: String(el.aistudioProModel?.value || '').trim(),
        };
    }

    function getAiStudioModelDefaults() {
        const flashCard = document.querySelector('#model-selector .model-card[data-model="flash"]');
        const proCard = document.querySelector('#model-selector .model-card[data-model="pro"]');
        return {
            flash: {
                id: String(flashCard?.dataset.aistudioModel || 'gemini-3.1-flash-image-preview').trim(),
                label: String(flashCard?.dataset.modelAlias || 'Nano Banana 2').trim(),
            },
            pro: {
                id: String(proCard?.dataset.aistudioModel || 'gemini-3-pro-image-preview').trim(),
                label: String(proCard?.dataset.modelAlias || 'Nano Banana Pro').trim(),
            },
        };
    }

    function fillProxyConfigForm(config) {
        const cfg = config || {};
        if (el.proxyEnabled) el.proxyEnabled.checked = Boolean(cfg.enabled);
        if (el.proxyBaseUrl) el.proxyBaseUrl.value = String(cfg.base_url || 'http://127.0.0.1:8045');
        if (el.proxyApiKey) el.proxyApiKey.value = String(cfg.api_key || '');
        if (el.proxyTimeout) el.proxyTimeout.value = String(cfg.timeout_seconds || 180);
        if (el.proxyFlashModel) el.proxyFlashModel.value = String(cfg.flash_model || 'gemini-3.1-flash-image');
        if (el.proxyProModel) el.proxyProModel.value = String(cfg.pro_model || 'gemini-3-pro-image');
    }

    function fillAiStudioConfigForm(config) {
        const cfg = config || {};
        const defaults = getAiStudioModelDefaults();
        const flashModel = String(cfg.flash_model || '').trim();
        const proModel = String(cfg.pro_model || '').trim();
        const resolvedFlashModel = (!flashModel || flashModel === 'gemini-2.5-flash-image') ? defaults.flash.id : flashModel;
        const resolvedProModel = proModel || defaults.pro.id;
        if (el.aistudioApiKey) el.aistudioApiKey.value = String(cfg.api_key || '');
        if (el.aistudioFlashModel) {
            el.aistudioFlashModel.value = resolvedFlashModel;
            el.aistudioFlashModel.placeholder = `例如 ${defaults.flash.id}`;
        }
        if (el.aistudioProModel) {
            el.aistudioProModel.value = resolvedProModel;
            el.aistudioProModel.placeholder = `例如 ${defaults.pro.id}`;
        }
    }

    function effectiveProviderMode() {
        const selected = String(state.providerMode || 'direct').trim().toLowerCase();
        if (selected && selected !== 'auto') return selected;
        const proxyEnabled = Boolean(state.proxyConfig?.enabled);
        const nanoConfigured = Boolean((el.nanoKey?.value || localStorage.getItem('nanobanana_api_key') || '').trim());
        if (proxyEnabled) return 'proxy';
        if (nanoConfigured) return 'nanobanana';
        return 'direct';
    }

    function updateApiKeyPlaceholders() {
        const mode = effectiveProviderMode();
        let primary = 'API 密钥 #1（主用）';
        let restPrefix = 'API Key';
        if (mode === 'proxy') {
            primary = '反代 Token #1（可选覆盖）';
            restPrefix = '反代 Token';
        } else if (mode === 'aistudio') {
            primary = 'AI Studio API 密钥 #1（可覆盖侧边栏默认值）';
            restPrefix = 'AI Studio API 密钥';
        }
        if (el.apiKey) el.apiKey.placeholder = primary;
        getExtraInputs().forEach((input, idx) => {
            input.placeholder = `${restPrefix} #${idx + 2}`;
        });
    }

    function renderProviderCards() {
        const selected = String(state.providerMode || 'direct').trim().toLowerCase();
        const effective = effectiveProviderMode();
        [...document.querySelectorAll('#provider-selector .provider-card')].forEach(card => {
            const mode = card.dataset.provider || '';
            card.classList.toggle('active', mode === selected);
            card.classList.toggle('provider-effective', mode === effective);
        });
        if (el.providerHint) {
            const proxyEnabled = Boolean(state.proxyConfig?.enabled);
            const baseUrl = String(state.proxyConfig?.base_url || '').trim();
            const tokenMasked = maskApiKey(state.proxyConfig?.api_key || '');
            const hints = {
                auto: proxyEnabled
                    ? `自动模式当前会优先使用本地反代：${baseUrl || '未配置'}。如果你在主面板填写了密钥，本次请求会优先使用主面板中的反代 Token。`
                    : `自动模式当前会回退到 ${effective === 'nanobanana' ? 'Nano Banana' : 'Vertex AI API'}。`,
                direct: 'Vertex AI API 通道使用服务端 Vertex 凭据。主面板中的普通 API 密钥不会作为 Vertex 认证；如果你的密钥来自 Google AI Studio，请切换到 Google AI Studio 接口。',
                aistudio: `Google AI Studio 接口会优先使用主面板中的 API 密钥；如果主面板为空，则回退到左侧侧边栏保存的默认密钥：${state.aiStudioConfig?.api_key ? maskApiKey(state.aiStudioConfig.api_key) : '未设置'}。`,
                proxy: `本地反代通道将调用 ${baseUrl || '未配置接口地址'}，默认 Token：${state.proxyConfig?.api_key ? tokenMasked : '未设置'}。`,
                nanobanana: 'Nano Banana 通道会使用左侧保存的第三方密钥，不会读取本地反代设置。',
            };
            el.providerHint.textContent = hints[selected] || hints.auto;
        }
        updateApiKeyPlaceholders();
    }

    function setProviderMode(mode, skipPersist = false) {
        const next = ['auto', 'direct', 'aistudio', 'proxy', 'nanobanana'].includes(mode) ? mode : 'auto';
        state.providerMode = next;
        if (!skipPersist) localStorage.setItem(PROVIDER_MODE_STORAGE, next);
        renderProviderCards();
        refreshRateStatus(true);
    }

    async function fetchProxyConfig() {
        try {
            const r = await fetch('/api/local-proxy-config', { cache: 'no-store' });
            const d = await r.json();
            if (!r.ok || !d?.ok) throw new Error(d?.error || `本地反代配置读取失败 (${r.status})`);
            state.proxyConfig = d.config || null;
            fillProxyConfigForm(state.proxyConfig || {});
            renderProviderCards();
        } catch (e) {
            notify(e.message || '本地反代配置读取失败', 'warning');
            state.proxyConfig = null;
            fillProxyConfigForm({});
            renderProviderCards();
        }
    }

    async function fetchAiStudioConfig() {
        try {
            const r = await fetch('/api/ai-studio-config', { cache: 'no-store' });
            const d = await r.json();
            if (!r.ok || !d?.ok) throw new Error(d?.error || `Google AI Studio 配置读取失败（${r.status}）`);
            state.aiStudioConfig = d.config || null;
            fillAiStudioConfigForm(state.aiStudioConfig || {});
            renderProviderCards();
        } catch (e) {
            notify(e.message || 'Google AI Studio 配置读取失败', 'warning');
            state.aiStudioConfig = null;
            fillAiStudioConfigForm({});
            renderProviderCards();
        }
    }

    function renderProxyTestResult(payload, ok) {
        if (!el.proxyTestResult) return;
        const health = payload?.health || {};
        const models = payload?.models || {};
        const tryon = payload?.tryon || {};
        const localAg = payload?.local_antigravity || {};
        const items = Array.isArray(models.items) ? models.items : [];
        const flashCandidates = Array.isArray(models.candidate_flash_models) ? models.candidate_flash_models : [];
        const proCandidates = Array.isArray(models.candidate_pro_models) ? models.candidate_pro_models : [];
        const enabledAccounts = Array.isArray(localAg.enabled_accounts) ? localAg.enabled_accounts : [];
        const enabledImageModels = Array.isArray(localAg.enabled_image_models) ? localAg.enabled_image_models : [];
        const localAgBaseDir = String(localAg.base_dir || '').trim();
        const flashFallback = Boolean(models.flash_fallback_to_pro);
        const effectiveFlash = String(models.effective_flash_model || '').trim();
        const effectivePro = String(models.effective_pro_model || '').trim();
        el.proxyTestResult.classList.remove('hidden');
        el.proxyTestResult.innerHTML = `
            <div class="usage-query-summary">
                <div class="usage-query-key-label">${ok ? '连接成功' : '连接异常'}</div>
                <div style="margin-top:8px;font-size:12px;color:rgba(255,255,255,0.78);line-height:1.6;">
                    <div>健康检查：${health.ok ? '正常' : '失败'}${health.status_code ? ` · HTTP ${health.status_code}` : ''}</div>
                    <div>模型列表：${models.ok ? '正常' : '失败'}${models.status_code ? ` · HTTP ${models.status_code}` : ''}</div>
                    <div>Flash 模型是否存在：${models.contains_flash_model ? '是' : '否'} · Pro 模型是否存在：${models.contains_pro_model ? '是' : '否'}</div>
                    ${(effectiveFlash || effectivePro) ? `<div>试衣实际模型：Flash 路径 -> ${effectiveFlash || '未找到'} · Pro 路径 -> ${effectivePro || '未找到'}</div>` : ''}
                    ${flashCandidates.length ? `<div>Flash 尝试顺序：${flashCandidates.join(' -> ')}</div>` : ''}
                    ${proCandidates.length ? `<div>Pro 尝试顺序：${proCandidates.join(' -> ')}</div>` : ''}
                    ${flashFallback ? `<div style="margin-top:6px;color:#fde68a;">当前反代未暴露 Flash 图片模型，试衣任务会自动回退到 Pro 模型。</div>` : ''}
                    ${tryon.strategy ? `<div style="margin-top:6px;">试衣调用链路: ${tryon.strategy}</div>` : ''}
                    ${tryon.warning ? `<div style="margin-top:6px;color:#fde68a;">${tryon.warning}</div>` : ''}
                    ${tryon.note ? `<div style="margin-top:6px;color:rgba(255,255,255,0.66);">${tryon.note}</div>` : ''}
                    ${localAg.found ? `<div style="margin-top:6px;word-break:break-all;">账号池来源目录: ${localAgBaseDir || '未知'}</div>` : ''}
                    ${localAg.found ? `<div style="margin-top:6px;">本机 Antigravity 反代池已启用账号: ${enabledAccounts.length} 个</div>` : ''}
                    ${enabledAccounts.length ? `<div style="margin-top:6px;word-break:break-all;">已启用账号: ${enabledAccounts.map(item => item.email || item.id || '未知账号').join(', ')}</div>` : ''}
                    ${enabledImageModels.length ? `<div style="margin-top:6px;word-break:break-all;">已启用账号的图片模型: ${enabledImageModels.join(', ')}</div>` : ''}
                    <div>已发现模型数: ${Number(models.count || 0)}</div>
                    ${items.length ? `<div style="margin-top:6px;word-break:break-all;">样例: ${items.slice(0, 8).join(', ')}</div>` : ''}
                    ${health.error ? `<div style="margin-top:6px;color:#fda4af;">Health 错误: ${health.error}</div>` : ''}
                    ${models.error ? `<div style="margin-top:6px;color:#fda4af;">Models 错误: ${models.error}</div>` : ''}
                </div>
            </div>`;
    }

    async function saveProxyConfig() {
        const payload = readProxyConfigFromUi();
        try {
            const r = await fetch('/api/local-proxy-config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const d = await r.json();
            if (!r.ok || !d?.ok) throw new Error(d?.error || '保存失败');
            state.proxyConfig = d.config || payload;
            fillProxyConfigForm(state.proxyConfig);
            renderProviderCards();
            notify('本地反代配置已保存。', 'success');
        } catch (e) {
            notify(e.message || '本地反代配置保存失败', 'error');
            reportError(e.message || '本地反代配置保存失败', '本地反代配置');
        }
    }

    async function testProxyConfig() {
        const payload = readProxyConfigFromUi();
        try {
            const r = await fetch('/api/local-proxy-config/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const d = await r.json();
            renderProxyTestResult(d, r.ok && Boolean(d?.ok));
            if (!r.ok || !d?.ok) throw new Error(d?.error || '测试失败');
            notify('本地反代连接测试通过。', 'success');
        } catch (e) {
            notify(e.message || '本地反代连接测试失败', 'error');
            reportError(e.message || '本地反代连接测试失败', '本地反代测试');
        }
    }

    async function saveAiStudioConfig() {
        const payload = readAiStudioConfigFromUi();
        try {
            const r = await fetch('/api/ai-studio-config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const d = await r.json();
            if (!r.ok || !d?.ok) throw new Error(d?.error || '保存失败');
            state.aiStudioConfig = d.config || payload;
            fillAiStudioConfigForm(state.aiStudioConfig);
            renderProviderCards();
            notify('Google AI Studio 配置已保存。', 'success');
        } catch (e) {
            notify(e.message || 'Google AI Studio 配置保存失败', 'error');
            reportError(e.message || 'Google AI Studio 配置保存失败', 'Google AI Studio 配置');
        }
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
        document.title = 'AI 羽绒服试穿工作台';
        if (el.genText) el.genText.textContent = '一键生成试穿结果';
        if (el.resultImg) el.resultImg.alt = '羽绒服试穿结果';
        if (el.downOne) el.downOne.innerHTML = '<i class="fas fa-download"></i> 下载主结果';
        if (el.historyToggle) el.historyToggle.title = '历史记录';
        if (el.usageToggle) el.usageToggle.title = 'API 用量追踪';
        if (el.errorToggle) el.errorToggle.title = '系统错误日志';
        if (el.nanobananaToggle) el.nanobananaToggle.title = 'Nano Banana 配置';
        if (el.vertexToggle) el.vertexToggle.title = 'Vertex AI 凭证';
        if (el.modelInput) el.modelInput.multiple = false;
        if (el.apiKey) el.apiKey.placeholder = '接口密钥 #1（主）';
        if (el.extraKey2) el.extraKey2.placeholder = '接口密钥 #2';
        if (el.extraKey3) el.extraKey3.placeholder = '接口密钥 #3';
        if (el.extraKey4) el.extraKey4.placeholder = '接口密钥 #4';
        if (el.extraKey5) el.extraKey5.placeholder = '接口密钥 #5';
        updateExtraKeysToggleLabel();
    }

    function ready() {
        const canGenerate = !state.running && Boolean(state.model) && state.garments.length > 0;
        if (el.genBtn) el.genBtn.disabled = !canGenerate;
        if (el.resultRetryBtn) el.resultRetryBtn.disabled = !canGenerate;
        if (el.saveHistoryBtn) el.saveHistoryBtn.disabled = state.results.length === 0;
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
        if (el.msg) el.msg.textContent = m || '处理中...';
        if (el.batchText) el.batchText.textContent = `批量进度: ${Math.min(i, t)} / ${t}`;
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
            const keyPool = getApiKeyPool();
            const key = keyPool[0] || '';
            const mode = effectiveProviderMode();
            params.set('provider_mode', state.providerMode || 'direct');
            if (mode === 'proxy') {
                if (key) params.set('proxy_api_key', key);
            } else if (key) {
                params.set('api_key', key);
            }
            const nk = (el.nanoKey?.value || localStorage.getItem('nanobanana_api_key') || '').trim();
            if (nk) params.set('nanobanana_api_key', nk);

            const r = await fetch(`/api/rate-status?${params.toString()}`, { cache: 'no-store' });
            if (!r.ok) throw new Error(`限额状态请求失败 (${r.status})`);
            const d = await r.json();
            if (!d || !d.ok) throw new Error(d?.error || '限额状态返回异常');

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
            if (!silent) writeLog(e.message || '限额状态刷新失败');
        }
    }

    function historyStorageKey() {
        const user = normalizeUsername(state.authUser || 'guest');
        return `tryon_history_${user}_v1`;
    }

    function loadHistory() {
        try {
            const raw = localStorage.getItem(historyStorageKey());
            if (!raw) {
                state.history = [];
                return;
            }
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed)) {
                state.history = parsed;
                return;
            }
            const savedAt = Number(parsed?.savedAt || 0);
            const items = Array.isArray(parsed?.items) ? parsed.items : [];
            const expired = Boolean(state.authUser) && savedAt > 0 && (Date.now() - savedAt > HISTORY_TTL_MS);
            if (expired) {
                state.history = [];
                saveHistory();
                return;
            }
            state.history = items;
        } catch (_) {
            state.history = [];
        }
    }

    function saveHistory() {
        const payload = {
            savedAt: Date.now(),
            items: state.history.slice(0, 80),
        };
        localStorage.setItem(historyStorageKey(), JSON.stringify(payload));
    }

    function setHistoryView(detailMode) {
        if (el.historyListView) el.historyListView.classList.toggle('hidden', detailMode);
        if (el.historyDetailView) el.historyDetailView.classList.toggle('hidden', !detailMode);
    }

    function updateHistorySelectionUi() {
        const sel = state.historySelected.size;
        if (el.historySelCount) el.historySelCount.textContent = String(sel);
        if (el.historyDownloadSelected) el.historyDownloadSelected.style.display = sel > 0 ? '' : 'none';
    }

    function renderHistoryList() {
        if (!el.historyList || !el.historyBadge) return;
        if (state.history.length === 0) {
            const tip = state.authUser ? '生成完成后会自动保存（24h）' : '请先登录，生成后可保存 24h';
            el.historyList.innerHTML = `
                <div class="history-empty">
                    <i class="fas fa-inbox"></i>
                    <p>暂无历史记录</p>
                    <span>${tip}</span>
                </div>`;
            el.historyBadge.style.display = 'none';
            return;
        }
        el.historyList.innerHTML = state.history.map(item => {
            const thumb = item.resultDisplayUrls?.[0] || item.results?.[0] || (item.garmentCloudUrls?.[0] || (item.garments?.[0] ? `/uploads/${item.garments[0]}` : '')) || (item.modelCloudUrl || (item.model ? `/uploads/${item.model}` : ''));
            const time = new Date(item.createdAt || Date.now()).toLocaleString('zh-CN', { hour12: false });
            return `
                <div class="history-item" data-id="${item.id}">
                    <img class="history-item-thumb" src="${thumb}" alt="历史">
                    <div class="history-item-info">
                        <div class="history-item-time">${time}</div>
                        <div class="history-item-summary">${item.modelType === 'pro' ? 'Nano Banana Pro' : 'Nano Banana 2'}</div>
                        <div class="history-item-count">结果 ${item.results?.length || 0} 张</div>
                    </div>
                    <div class="history-item-arrow"><i class="fas fa-chevron-right"></i></div>
                </div>`;
        }).join('');
        el.historyBadge.style.display = '';
        el.historyBadge.textContent = String(state.history.length);
        [...el.historyList.querySelectorAll('.history-item')].forEach(n => n.addEventListener('click', () => showHistoryDetail(n.dataset.id)));
    }

    function showHistoryDetail(id) {
        const item = state.history.find(x => x.id === id);
        if (!item) return;
        state.activeHistoryId = id;
        state.historySelected.clear();
        setHistoryView(true);
        if (el.historyTime) el.historyTime.textContent = new Date(item.createdAt || Date.now()).toLocaleString('zh-CN', { hour12: false });
        if (el.historyGenCount) el.historyGenCount.textContent = String(item.results?.length || 0);
        if (el.historyRef) {
            const modelSrc = item.modelCloudUrl || (item.model ? `/uploads/${item.model}` : '');
            el.historyRef.innerHTML = modelSrc ? `<img src="${modelSrc}" alt="模特" loading="lazy">` : '<div class="usage-empty">无模特图</div>';
        }
        if (el.historyTgt) {
            el.historyTgt.innerHTML = (item.garments || []).map((name, idx) => {
                const src = (item.garmentCloudUrls && item.garmentCloudUrls[idx]) || `/uploads/${name}`;
                return `<img src="${src}" alt="服装" loading="lazy">`;
            }).join('') || '<div class="usage-empty">无服装图</div>';
        }
        if (el.historyGen) {
            el.historyGen.innerHTML = '';
            const historyResults = Array.isArray(item.resultDisplayUrls) && item.resultDisplayUrls.length ? item.resultDisplayUrls : (item.results || []);
            historyResults.forEach((url, idx) => {
                const wrap = document.createElement('div');
                wrap.className = 'history-gen-item';
                wrap.innerHTML = `<img src="${url}" alt="结果 ${idx + 1}" data-i="${idx}" loading="lazy">`;
                const img = wrap.querySelector('img');
                img?.addEventListener('click', () => {
                    if (state.historySelected.has(idx)) {
                        state.historySelected.delete(idx);
                        img.classList.remove('selected');
                    } else {
                        state.historySelected.add(idx);
                        img.classList.add('selected');
                    }
                    updateHistorySelectionUi();
                });
                img?.addEventListener('dblclick', () => window.open(url, '_blank'));
                el.historyGen.appendChild(wrap);
            });
        }
        updateHistorySelectionUi();
    }

    function storeCurrentToHistory() {
        if (!state.model || state.results.length === 0) return;
        if (!state.authUser) {
            notify('未登录，历史记录不会持久保存。登录后可保存 24 小时。', 'warning');
            return;
        }
        state.history.unshift({
            id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            createdAt: Date.now(),
            modelType: state.modelType,
            model: state.model,
            modelCloudUrl: state.modelCloudUrl,
            garments: [...state.garments],
            garmentCloudUrls: [...state.garmentCloudUrls],
            results: [...state.results],
            resultDisplayUrls: getSessionResultUrls(),
        });
        saveHistory();
        renderHistoryList();
    }

    function closeAllSidebars() {
        [el.historySidebar, el.usageSidebar, el.errorSidebar, el.nanobananaSidebar, el.vertexSidebar, el.aistudioSidebar, el.proxySidebar]
            .forEach(n => n?.classList.remove('open'));
        [el.historyOverlay, el.usageOverlay, el.errorOverlay, el.nanobananaOverlay, el.vertexOverlay, el.aistudioOverlay, el.proxyOverlay]
            .forEach(n => n?.classList.add('hidden'));
    }

    function openSidebar(which) {
        closeAllSidebars();
        const map = {
            history: [el.historySidebar, el.historyOverlay],
            usage: [el.usageSidebar, el.usageOverlay],
            error: [el.errorSidebar, el.errorOverlay],
            nanobanana: [el.nanobananaSidebar, el.nanobananaOverlay],
            vertex: [el.vertexSidebar, el.vertexOverlay],
            aistudio: [el.aistudioSidebar, el.aistudioOverlay],
            proxy: [el.proxySidebar, el.proxyOverlay],
        };
        const pair = map[which];
        if (!pair) return;
        pair[0]?.classList.add('open');
        pair[1]?.classList.remove('hidden');
        if (which === 'history') renderHistoryList();
        if (which === 'error') refreshErrors();
        if (which === 'proxy') fetchProxyConfig();
        if (which === 'aistudio') fetchAiStudioConfig();
    }

    async function reportError(message, context = '前端') {
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
            const key = (el.apiKey?.value || '').trim()
                || normalizeKeyList(state.savedKeys.map(row => row.key))[0]
                || '';
            if (key) fd.append('api_key', key);

            const r = await fetch('/analyze-error', { method: 'POST', body: fd });
            const d = await r.json();
            const analysis = String(d?.analysis || '').trim();
            if (!analysis) throw new Error('分析结果为空');

            const fd2 = new FormData();
            fd2.append('analysis', analysis);
            await fetch(`/api/errors/${encodeURIComponent(id)}/analysis`, { method: 'PUT', body: fd2 });
            await refreshErrors();
            notify('错误日志 AI 分析完成', 'success');
        } catch (e) {
            notify(e.message || '错误日志分析失败', 'error');
        } finally {
            state.errorAnalyzing.delete(id);
            renderErrors();
        }
    }

    function renderErrors() {
        const list = state.errors || [];
        const html = list.length === 0
            ? '<div class="usage-empty"><i class="fas fa-check-circle"></i> 暂无错误</div>'
            : list.map(e => `
                <div class="errorlog-item" style="padding:10px;border:1px solid rgba(239,68,68,0.2);border-radius:10px;background:rgba(239,68,68,0.06);margin-bottom:8px;">
                    <div style="font-size:11px;color:rgba(255,255,255,0.45);">${e.time || ''} ${e.context ? `· ${e.context}` : ''}</div>
                    <div style="font-size:12px;color:rgba(255,255,255,0.85);margin-top:4px;word-break:break-word;">${e.message || ''}</div>
                    <div style="margin-top:8px;">
                        <button type="button" data-analyze-error="${e.id}" class="errorlog-action-btn" style="padding:4px 8px;">
                            <i class="fas fa-robot"></i> ${state.errorAnalyzing.has(e.id) ? '分析中...' : (e.analysis ? '重新分析' : 'AI分析')}
                        </button>
                    </div>
                    ${e.analysis ? `<div style="font-size:12px;color:#93c5fd;margin-top:6px;white-space:pre-wrap;"><i class="fas fa-robot"></i> ${e.analysis}</div>` : ''}
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

    async function queryUsage(inputEl, resultEl) {
        const key = (inputEl?.value || '').trim();
        if (!key) {
            notify('请先输入 API Key。', 'warning');
            return;
        }
        try {
            const r = await fetch(`/api/key-usage?api_key=${encodeURIComponent(key)}`);
            const d = await r.json();
            resultEl?.classList.remove('hidden');
            if (!d.found) {
                if (resultEl) resultEl.innerHTML = '<div class="usage-empty">未找到该 Key 的用量记录</div>';
                return;
            }
            if (resultEl) {
                resultEl.innerHTML = `
                    <div class="usage-query-summary">
                        <div class="usage-query-key-label">${d.key_masked || 'Key'}</div>
                        <div class="usage-query-stats">
                            <div class="usage-stat-item"><span class="usage-stat-value">${d.calls || 0}</span><span class="usage-stat-label">调用</span></div>
                            <div class="usage-stat-item"><span class="usage-stat-value">${d.success || 0}</span><span class="usage-stat-label">成功</span></div>
                            <div class="usage-stat-item"><span class="usage-stat-value">${d.failed || 0}</span><span class="usage-stat-label">失败</span></div>
                        </div>
                        <div style="margin-top:8px;font-size:12px;color:rgba(255,255,255,0.65)">估算费用: $${Number(d.cost || 0).toFixed(4)}</div>
                    </div>`;
            }
        } catch (e) {
            notify(e.message || '查询用量失败', 'error');
        }
    }

    async function uploadVertexCredentials() {
        const file = el.vertexFile?.files?.[0];
        if (!file) {
            notify('请先选择 JSON 凭证文件。', 'warning');
            return;
        }
        try {
            const fd = new FormData();
            fd.append('file', file);
            const r = await fetch('/api/vertex-credentials', { method: 'POST', body: fd });
            const d = await r.json();
            if (!r.ok) throw new Error(d.error || '上传失败');
            notify(d.message || 'Vertex 凭证已更新', 'success');
        } catch (e) {
            notify(e.message || 'Vertex 凭证上传失败', 'error');
            reportError(e.message || 'Vertex 凭证上传失败', 'Vertex 凭证上传');
        }
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
            let msg = `上传失败 (${r.status})`;
            try {
                const d = await r.json();
                msg = d.error || msg;
            } catch (_) { }
            throw new Error(msg);
        }
        const d = await r.json();
        if (!d.filename) throw new Error('服务器未返回文件名');
        return { filename: d.filename, cloud_url: d.cloud_url || '' };
    }

    async function onModel(files) {
        const list = Array.from(files || []).filter(f => f.type.startsWith('image/'));
        if (list.length === 0) return;
        if (list.length > 1) notify('模特照片只能上传 1 张，已自动使用第一张。', 'warning');
        try {
            notify('正在上传模特照片...', 'info');
            const result = await upload(list[0], '/upload/model');
            state.model = result.filename;
            state.modelCloudUrl = result.cloud_url;
            updateModel();
            setUploadIntakeStatus('model', '已手动上传用户全身照。', 'success');
            notify('模特照片上传成功。', 'success');
        } catch (e) {
            notify(e.message || '模特照片上传失败。', 'error');
            writeLog(e.message || '模特照片上传失败。');
            reportError(e.message || '模特照片上传失败', '上传模特');
        }
    }

    async function onGarments(files) {
        const list = Array.from(files || []).filter(f => f.type.startsWith('image/'));
        if (list.length === 0) return;
        if (state.garments.length + list.length > 50) {
            notify(`服装照片最多 50 张，当前已上传 ${state.garments.length} 张。`, 'warning');
            return;
        }
        try {
            notify(`正在上传 ${list.length} 张服装照片...`, 'info');
            for (const f of list) {
                const result = await upload(f, '/upload/garment');
                state.garments.push(result.filename);
                state.garmentCloudUrls.push(result.cloud_url);
            }
            updateGarments();
            setUploadIntakeStatus('garment', `已手动上传 ${state.garments.length} 张商品图。`, 'success');
            notify(`服装照片上传完成，共 ${state.garments.length} 张。`, 'success');
        } catch (e) {
            notify(e.message || '服装照片上传失败。', 'error');
            writeLog(e.message || '服装照片上传失败。');
            reportError(e.message || '服装照片上传失败', '上传服装');
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

    function setModel(type) {
        state.modelType = type === 'pro' ? 'pro' : 'flash';
        refreshModelRateUi();
        refreshRateStatus(true);
    }

    function promptPayload() {
        const stylePrompt = (STYLE_PRESETS[state.stylePreset] || STYLE_PRESETS.default).prompt || '';
        if (!el.promptToggle) {
            return { mode: 'append', text: stylePrompt };
        }
        if (el.promptToggle.checked) {
            const base = (el.promptOverride?.value || '').trim();
            const merged = [base, stylePrompt].filter(Boolean).join('\n\n');
            return { mode: 'override', text: merged };
        }
        const extra = (el.promptAppend?.value || '').trim();
        const merged = [extra, stylePrompt].filter(Boolean).join('\n');
        return { mode: 'append', text: merged };
    }

    function syncSelUi() {
        const total = state.results.length;
        const selected = state.selected.size;
        const all = total > 0 && selected === total;
        if (el.downSelCount) el.downSelCount.textContent = `(${selected})`;
        if (el.downSel) el.downSel.classList.toggle('hidden', selected === 0);
        if (el.selAll) {
            el.selAll.innerHTML = all
                ? '<i class="fas fa-times"></i> 取消全选'
                : '<i class="fas fa-check-double"></i> 全选';
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
                <img src="${previewUrl}" alt="试衣结果 ${i + 1}" loading="lazy" width="140" height="140">
                <button class="select-check" type="button" title="选择"><i class="fas fa-check"></i></button>
                <div class="item-overlay">
                    <span class="item-index">#${i + 1}</span>
                    <button class="item-download" type="button" title="下载"><i class="fas fa-download"></i></button>
                </div>
            `;
            item.addEventListener('click', () => toggleSel(i));
            item.querySelector('.select-check')?.addEventListener('click', e => {
                e.stopPropagation();
                toggleSel(i);
            });
            item.querySelector('.item-download')?.addEventListener('click', async e => {
                e.stopPropagation();
                await downloadImage(url, '试衣结果', i + 1);
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
        const safeBase = String(baseName || '试衣结果')
            .replace(/\.[^.]+$/, '')
            .replace(/[\\/:*?"<>|]+/g, '_')
            .trim() || '试衣结果';
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
            if (!r2.ok) throw new Error(`下载失败 (${r2.status})`);
            blob = await r2.blob();
        }
        saveBlob(blob, buildDownloadFilename(baseName, 'png', index));
    }

    async function downloadZip(urls, baseName) {
        if (!urls || urls.length === 0) {
            notify('没有可打包下载的图片。', 'warning');
            return;
        }
        const fd = new FormData();
        fd.append('filenames', JSON.stringify(urls));
        const r = await fetch('/download-batch', { method: 'POST', body: fd });
        if (!r.ok) {
            let msg = `ZIP 下载失败 (${r.status})`;
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
            await downloadZip(getSessionResultUrls(), `试衣结果_${state.results.length}张`);
            notify('ZIP 下载已开始。', 'success');
        } catch (e) {
            notify(e.message || 'ZIP 下载失败。', 'error');
            reportError(e.message || 'ZIP 下载失败', '批量下载');
        }
    }

    async function downloadSelected() {
        const urls = selectedUrls();
        if (urls.length === 0) {
            notify('请先选择至少 1 张图片。', 'warning');
            return;
        }
        try {
            await downloadZip(urls, `选中结果_${urls.length}张`);
            notify(`已打包 ${urls.length} 张选中图片。`, 'success');
        } catch (e) {
            notify(e.message || '选中 ZIP 下载失败。', 'error');
        }
    }

    async function downloadEach() {
        const urls = selectedUrls().length > 0 ? selectedUrls() : state.results;
        if (urls.length === 0) {
            notify('没有可下载的图片。', 'warning');
            return;
        }
        const ms = el.interval ? clamp(Number(el.interval.value || '1500'), 500, 5000) : 1500;
        for (let i = 0; i < urls.length; i++) {
            try {
                await downloadImage(urls[i], '试衣结果', i + 1);
            } catch (e) {
                writeLog(`第 ${i + 1} 张下载失败: ${e.message || e}`);
            }
            if (i < urls.length - 1) await sleep(ms);
        }
        notify(`已完成逐张下载，共 ${urls.length} 张。`, 'success');
    }

    async function submitTask(garment, freedom, selectedApiKey) {
        const fd = new FormData();
        fd.append('target_image', state.model);
        fd.append('reference_image', garment);
        fd.append('model', state.modelType);
        fd.append('freedom', String(freedom));
        fd.append('provider_mode', state.providerMode || 'direct');
        if (state.modelCloudUrl) fd.append('target_image_cloud_url', state.modelCloudUrl);
        const garmentIdx = state.garments.indexOf(garment);
        const garmentCloudUrl = garmentIdx >= 0 ? state.garmentCloudUrls[garmentIdx] : '';
        if (garmentCloudUrl) fd.append('reference_image_cloud_url', garmentCloudUrl);
        const garmentType = getGarmentType();
        if (garmentType) fd.append('garment_type', garmentType);
        const chosenKey = String(selectedApiKey || '').trim();
        if (effectiveProviderMode() === 'proxy') {
            if (chosenKey) fd.append('proxy_api_key', chosenKey);
        } else if (chosenKey) {
            fd.append('api_key', chosenKey);
        }
        const nk = (el.nanoKey?.value.trim()) || (localStorage.getItem('nanobanana_api_key') || '').trim();
        if (nk) fd.append('nanobanana_api_key', nk);
        const p = promptPayload();
        if (p.text) {
            fd.append('custom_prompt', p.text);
            fd.append('prompt_mode', p.mode);
        }
        const r = await fetch('/submit-task', { method: 'POST', body: fd });
        if (!r.ok) {
            let msg = `任务提交失败 (${r.status})`;
            try {
                const d = await r.json();
                msg = d.error || d.detail || msg;
            } catch (_) { }
            throw new Error(msg);
        }
        const d = await r.json();
        if (!d.task_id) throw new Error('缺少 task_id');
        return d.task_id;
    }

    async function pollTask(taskId, index, total) {
        let logged = 0;
        let transientErrors = 0;
        for (let t = 0; t < 240; t++) {
            if (state.abort) throw new Error('用户已中止生成');
            try {
                const r = await fetch(`/task/${encodeURIComponent(taskId)}`, { cache: 'no-store' });
                if (!r.ok) throw new Error(`任务轮询失败 (${r.status})`);
                const d = await r.json();
                transientErrors = 0;
                const tp = clamp(Number(d.progress || 0), 0, 100);
                const op = ((index + tp / 100) / total) * 100;
                progress(op, d.message || '处理中...', index + 1, total);
                if (Array.isArray(d.logs) && d.logs.length > logged) {
                    for (let i = logged; i < d.logs.length; i++) writeLog(d.logs[i]);
                    logged = d.logs.length;
                }
                if (d.status === 'completed') return d;
                if (d.status === 'failed') throw new Error(d.error || d.message || '任务失败');
            } catch (err) {
                transientErrors += 1;
                writeLog(`轮询临时错误 (${transientErrors}/3): ${err.message || err}`);
                if (transientErrors >= 3) throw err;
                await sleep(1500);
                continue;
            }
            await sleep(1500);
        }
        throw new Error('任务轮询超时');
    }

    async function generate() {
        if (state.running) return;
        if (!state.model) {
            notify('请先上传 1 张模特照片。', 'warning');
            return;
        }
        if (state.garments.length === 0) {
            notify('请先上传至少 1 张服装照片。', 'warning');
            return;
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
        const keyPool = getApiKeyPool();
        const parallel = getParallelSettings(list.length);
        const effectiveMode = effectiveProviderMode();
        const modeLabelMap = {
            direct: 'Vertex AI API',
            aistudio: 'Google AI Studio 接口',
            proxy: '本地反代接口',
            nanobanana: 'Nano Banana',
        };

        writeLog(`开始生成，共 ${list.length} 个任务。`);
        writeLog(`当前风格: ${(STYLE_PRESETS[state.stylePreset] || STYLE_PRESETS.default).name}`);
        writeLog(`当前通道: ${modeLabelMap[effectiveMode] || effectiveMode}`);
        if (effectiveMode === 'proxy') {
            writeLog('本地反代试衣现已禁用会忽略参考图的文生图回退；只有真正支持两张输入图的编辑接口才会放行。');
        }
        if (keyPool.length > 0) {
            const keyKind = effectiveMode === 'proxy' ? '反代 Token' : (effectiveMode === 'aistudio' ? 'AI Studio API 密钥' : 'API 密钥');
            writeLog(`已载入 ${keyPool.length} 个${keyKind}：${keyPool.map(maskApiKey).join(' | ')}`);
        } else {
            if (effectiveMode === 'proxy') {
                writeLog(`主面板未填写反代 Token，将回退到左侧默认反代 Token${state.proxyConfig?.api_key ? `（${maskApiKey(state.proxyConfig.api_key)}）` : '（如已配置）'}。`);
            } else if (effectiveMode === 'aistudio') {
                writeLog(`主面板未填写 AI Studio 密钥，将回退到左侧默认 AI Studio 密钥${state.aiStudioConfig?.api_key ? `（${maskApiKey(state.aiStudioConfig.api_key)}）` : '（如已配置）'}。`);
            } else {
                writeLog('当前将使用服务端 Vertex AI 凭据。');
            }
        }
        if (parallel.enabled) {
            writeLog(`并行生成已开启，并发=${parallel.concurrency}`);
        }
        setResultFeedback('info', 'AI 正在生成试穿结果', '你可以留在当前页面等待，也可以展开高级区查看系统日志与通道状态。');

        const runOneTask = async (i) => {
            if (state.abort) return;
            const g = list[i];
            const f = getFreedom();
            const selectedApiKey = keyPool.length > 0 ? keyPool[i % keyPool.length] : '';
            const keyLabel = selectedApiKey
                ? `, ${effectiveMode === 'proxy' ? 'Token' : 'Key'}=${maskApiKey(selectedApiKey)} (${(i % keyPool.length) + 1}/${keyPool.length})`
                : '';
            const garmentType = getGarmentType();
            const garmentTypeLabel = garmentType ? `, 衣物类型=${garmentType}` : '';
            writeLog(`任务 ${i + 1}/${list.length}: 服装=${g}, 自由度=${f}${garmentTypeLabel}${keyLabel}`);
            try {
                const id = await submitTask(g, f, selectedApiKey);
                const t = await pollTask(id, i, list.length);
                const stableUrl = String(t.result_display_url || t.result_cloud_url || t.result_url || '').trim();
                const previewUrl = String(t.result_data_url || stableUrl || '').trim();
                if (!previewUrl) throw new Error('任务成功但结果图片为空');
                state.results.push(stableUrl || previewUrl);
                state.resultPreviews.push(previewUrl);
                ok += 1;
                if (state.results.length === 1) showResult(previewUrl);
                renderGallery();
                refreshRateStatus(true);
            } catch (e) {
                fail += 1;
                writeLog(`任务 ${i + 1} 失败: ${e.message || e}`);
                notify(`任务 ${i + 1} 失败: ${e.message || e}`, 'error');
                reportError(e.message || '任务失败', '生成任务');
                refreshRateStatus(true);
            }
            if (parallel.enabled) {
                const done = ok + fail;
                progress((done / list.length) * 100, '并行生成处理中...', done, list.length);
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
            notify(`已中止生成，成功 ${ok} 张，失败 ${fail} 张。`, 'warning');
            setResultFeedback('warning', '生成已中止', `当前已完成 ${ok} 张，失败 ${fail} 张。你可以调整参数后重新生成。`);
        } else if (ok > 0) {
            progress(100, '试穿完成', list.length, list.length);
            notify(`试穿完成：成功 ${ok} 张，失败 ${fail} 张。`, fail > 0 ? 'warning' : 'success');
            playCompletionSound(fail > 0 ? 'warning' : 'success');
            writeLog(`生成结束：成功 ${ok} 张，失败 ${fail} 张。`);
            setResultFeedback(
                fail > 0 ? 'warning' : 'success',
                fail > 0 ? '生成完成，但部分任务失败' : '试穿结果已生成',
                fail > 0
                    ? `已成功生成 ${ok} 张，另有 ${fail} 张失败。可直接下载结果或调整通道后重试。`
                    : `共生成 ${ok} 张试穿结果。可直接下载、切换风格重试，或保存到历史记录。`
            );
            storeCurrentToHistory();
        } else {
            notify('生成失败，未获得任何试穿结果。', 'error');
            playCompletionSound('warning');
            writeLog('生成结束：所有任务均失败，未返回可用图片。');
            setResultFeedback('error', '未获得可用试穿结果', '请优先检查用户图/商品图是否清晰、生成通道与 API Key 是否可用，必要时重新上传图片后再试。');
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
                notify('正在上传示例模特照片...', 'info');
                const result = await upload(file, '/upload/model');
                state.model = result.filename;
                state.modelCloudUrl = result.cloud_url;
                updateModel();
                setUploadIntakeStatus('model', `已选用示例模特「${model.name}」。`, 'success');
                notify(`已选用示例模特「${model.name}」。`, 'success');
            } catch (e) {
                card.classList.remove('selected');
                notify(e.message || '示例模特照片加载失败。', 'error');
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
            notify('已清空模特照片。', 'info');
        });
        el.refClear?.addEventListener('click', e => {
            e.stopPropagation();
            state.garments = [];
            state.garmentCloudUrls = [];
            updateGarments();
            setUploadIntakeStatus('garment', defaultIntakeStatus('garment'), 'neutral');
            notify('已清空服装照片。', 'info');
        });

        el.modelPreview?.addEventListener('click', e => {
            e.stopPropagation();
            if (!state.model) return notify('暂无模特照片。', 'warning');
            window.open(_modelDisplayUrl(), '_blank');
        });
        el.refPreview?.addEventListener('click', e => {
            e.stopPropagation();
            if (state.garments.length === 0) return notify('暂无服装照片。', 'warning');
            window.open(_garmentDisplayUrl(0), '_blank');
            notify(`已打开第一张服装图（共 ${state.garments.length} 张）。`, 'info');
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
            notify('已请求中止，等待当前任务结束...', 'warning');
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
            try { await downloadImage(el.resultImg.src, '试衣结果'); }
            catch (e) { notify(e.message || '下载失败。', 'error'); }
        });
        el.resultRetryBtn?.addEventListener('click', generate);
        el.cycleStyleBtn?.addEventListener('click', cycleStylePreset);
        el.saveHistoryBtn?.addEventListener('click', () => {
            if (state.results.length === 0) return notify('暂无可保存的试穿结果。', 'warning');
            const before = state.history.length;
            storeCurrentToHistory();
            if (state.authUser && state.history.length > before) {
                notify('当前结果已保存到历史记录。', 'success');
            }
        });
        el.returnToRecommendBtn?.addEventListener('click', () => navigateToRecommendation('return'));
        el.switchProductBtn?.addEventListener('click', () => navigateToRecommendation('switch'));

        el.nanoSave?.addEventListener('click', () => {
            localStorage.setItem('nanobanana_api_key', (el.nanoKey?.value || '').trim());
            notify('Nano Banana API Key 已保存。', 'success');
            refreshRateStatus(true);
            renderProviderCards();
        });
        el.nanoKey?.addEventListener('input', renderProviderCards);
        el.proxySave?.addEventListener('click', saveProxyConfig);
        el.proxyTest?.addEventListener('click', testProxyConfig);
        el.authLoginBtn?.addEventListener('click', loginUser);
        el.authRegisterBtn?.addEventListener('click', registerUser);
        el.authLogoutBtn?.addEventListener('click', logoutUser);
        [el.authUsername, el.authPassword].forEach(input => {
            input?.addEventListener('keydown', ev => {
                if (ev.key !== 'Enter') return;
                ev.preventDefault();
                loginUser();
            });
        });

        el.manageKeysBtn?.addEventListener('click', openKeysModal);
        el.fillSavedKeysBtn?.addEventListener('click', () => fillSavedKeysToInputs(true));
        el.keysModalClose?.addEventListener('click', closeKeysModal);
        el.keysModalOverlay?.addEventListener('click', ev => {
            if (ev.target === el.keysModalOverlay) closeKeysModal();
        });
        el.addKeyBtn?.addEventListener('click', addSavedKey);
        el.newKeyValue?.addEventListener('keydown', ev => {
            if (ev.key !== 'Enter') return;
            ev.preventDefault();
            addSavedKey();
        });
        el.keysFillSelected?.addEventListener('click', () => fillSavedKeysToInputs(false));
        el.keysFillAll?.addEventListener('click', () => fillSavedKeysToInputs(true));

        el.toggleExtraKeys?.addEventListener('click', () => {
            setExtraKeysExpanded(!state.extraKeysExpanded);
        });
        el.apiKey?.addEventListener('change', () => {
            onAnyApiKeyChanged();
        });
        el.apiKey?.addEventListener('input', updateExtraKeysToggleLabel);
        getExtraInputs().forEach(input => {
            input.addEventListener('change', onAnyApiKeyChanged);
            input.addEventListener('input', updateExtraKeysToggleLabel);
        });
        el.vertexSave?.addEventListener('click', uploadVertexCredentials);
        el.aistudioSave?.addEventListener('click', saveAiStudioConfig);

        el.promptOpen?.addEventListener('click', () => el.promptModal?.classList.remove('hidden'));
        el.promptClose?.addEventListener('click', () => el.promptModal?.classList.add('hidden'));
        el.promptModal?.addEventListener('click', e => { if (e.target === el.promptModal) el.promptModal.classList.add('hidden'); });

        const syncPromptMode = () => {
            const over = Boolean(el.promptToggle?.checked);
            el.promptAppendWrap?.classList.toggle('hidden-mode', over);
            el.promptOverrideWrap?.classList.toggle('hidden-mode', !over);
        };
        el.promptToggle?.addEventListener('change', syncPromptMode);
        syncPromptMode();

        const styleCards = [...document.querySelectorAll('#style-presets .style-card')];
        styleCards.forEach(card => {
            card.addEventListener('click', () => setStylePreset(card.dataset.style || 'default'));
        });

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

        const cards = [...document.querySelectorAll('#model-selector .model-card')];
        cards.forEach(c => c.addEventListener('click', () => {
            cards.forEach(x => x.classList.remove('active'));
            c.classList.add('active');
            setModel(c.dataset.model || 'flash');
        }));
        const providerCards = [...document.querySelectorAll('#provider-selector .provider-card')];
        providerCards.forEach(card => {
            card.addEventListener('click', () => setProviderMode(card.dataset.provider || 'auto'));
        });
        const active = cards.find(c => c.classList.contains('active'));
        setModel(active ? (active.dataset.model || 'flash') : 'flash');

        // Sidebar open/close
        const bindSidebar = (toggleBtn, openBtn, closeBtn, overlay, name) => {
            toggleBtn?.addEventListener('click', () => openSidebar(name));
            openBtn?.addEventListener('click', () => openSidebar(name));
            closeBtn?.addEventListener('click', closeAllSidebars);
            overlay?.addEventListener('click', closeAllSidebars);
        };
        bindSidebar(el.historyToggle, el.openHistory, el.historyClose, el.historyOverlay, 'history');
        bindSidebar(el.usageToggle, null, el.usageClose, el.usageOverlay, 'usage');
        bindSidebar(el.errorToggle, null, el.errorClose, el.errorOverlay, 'error');
        bindSidebar(el.nanobananaToggle, null, el.nanobananaClose, el.nanobananaOverlay, 'nanobanana');
        bindSidebar(el.vertexToggle, null, el.vertexClose, el.vertexOverlay, 'vertex');
        bindSidebar(el.aistudioToggle, null, el.aistudioClose, el.aistudioOverlay, 'aistudio');
        bindSidebar(el.proxyToggle, null, el.proxyClose, el.proxyOverlay, 'proxy');
        document.querySelectorAll('[data-open-sidebar]').forEach(btn => {
            btn.addEventListener('click', () => openSidebar(btn.dataset.openSidebar || 'history'));
        });

        // Usage query
        el.usageBtnA?.addEventListener('click', () => queryUsage(el.usageKeyA, el.usageResA));
        el.usageBtnB?.addEventListener('click', () => queryUsage(el.usageKeyB, el.usageResB));

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

        // History actions
        el.historyBack?.addEventListener('click', () => {
            state.activeHistoryId = '';
            state.historySelected.clear();
            setHistoryView(false);
            updateHistorySelectionUi();
        });
        el.historyClearAll?.addEventListener('click', () => {
            if (state.history.length === 0) return notify('暂无历史可清空。', 'info');
            if (!confirm('确认清空所有历史记录吗？')) return;
            state.history = [];
            saveHistory();
            renderHistoryList();
            setHistoryView(false);
            notify('历史记录已清空。', 'success');
        });
        el.historyDelete?.addEventListener('click', () => {
            const item = state.history.find(x => x.id === state.activeHistoryId);
            if (!item) return;
            if (!confirm('确认删除该历史会话吗？')) return;
            state.history = state.history.filter(x => x.id !== item.id);
            saveHistory();
            renderHistoryList();
            setHistoryView(false);
            notify('该历史会话已删除。', 'success');
        });
        el.historyDownloadAll?.addEventListener('click', async () => {
            const item = state.history.find(x => x.id === state.activeHistoryId);
            const urls = Array.isArray(item?.resultDisplayUrls) && item.resultDisplayUrls.length ? item.resultDisplayUrls : (item?.results || []);
            if (!item || !urls.length) return notify('当前会话无可下载图片。', 'warning');
            try { await downloadZip(urls, `历史结果_${urls.length}张`); }
            catch (e) { notify(e.message || '历史下载失败。', 'error'); }
        });
        el.historyDownloadSelected?.addEventListener('click', async () => {
            const item = state.history.find(x => x.id === state.activeHistoryId);
            if (!item) return;
            const historyResults = Array.isArray(item.resultDisplayUrls) && item.resultDisplayUrls.length ? item.resultDisplayUrls : (item.results || []);
            const urls = [...state.historySelected].sort((a, b) => a - b).map(i => historyResults[i]).filter(Boolean);
            if (urls.length === 0) return notify('请先选择历史结果图片。', 'warning');
            try { await downloadZip(urls, `历史选中_${urls.length}张`); }
            catch (e) { notify(e.message || '历史选中下载失败。', 'error'); }
        });

        // ESC closes sidebars and dialogs
        document.addEventListener('keydown', ev => {
            if (ev.key !== 'Escape') return;
            closeAllSidebars();
            el.promptModal?.classList.add('hidden');
        });
        window.addEventListener('message', event => { void handleBridgeMessage(event); });
    }

    // ===== Garment Browser Module =====
    const garmentBrowser = (() => {
        let _filters = null;
        let _currentPage = 0;
        const PAGE_SIZE = 24;
        let _currentFilters = { query: '', platform: '', gender: '', style_type: '', color: '', price_min: null, price_max: null };
        let _totalItems = 0;
        let _debounceTimer = null;

        function $(id) { return document.getElementById(id); }

        async function fetchFilters() {
            try {
                const resp = await fetch('/api/products/filters');
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
            try {
                const resp = await fetch(`/api/products?${params.toString()}`);
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
                        <span class="garment-card-price">¥${item.price || 0}</span>
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
                notify('该商品没有可用图片', 'warning');
                return;
            }
            try {
                notify(`正在导入「${(item.title || '').slice(0, 20)}…」`, 'info');
                const result = await importBridgeImage('garment', imageUrl, '');
                state.garments = [result.filename];
                state.garmentCloudUrls = [result.cloud_url || ''];
                updateGarments();
                setUploadIntakeStatus('garment', `已从商品库导入「${(item.title || '').slice(0, 30)}…」`, 'success');
                // Also update recommendation info
                state.recommendation = state.recommendation || {};
                state.recommendation.productTitle = item.title || '';
                state.recommendation.productId = String(item.id || '');
                state.recommendation.productPrice = item.price;
                state.recommendation.styleType = item.style_type || '';
                state.recommendation.colorFamily = item.color_family || '';
                state.recommendation.garmentImageUrl = imageUrl;
                updateRecommendationUi();
                updateCompareStage();
                notify(`已选择「${(item.title || '').slice(0, 25)}…」作为试穿商品`, 'success');
                // Highlight selected card
                document.querySelectorAll('.garment-card').forEach(c => c.classList.remove('selected'));
                const selectedCard = document.querySelector(`.garment-card[data-id="${item.id}"]`);
                if (selectedCard) selectedCard.classList.add('selected');
            } catch (e) {
                notify(`导入商品图失败: ${e.message || e}`, 'error');
            }
        }

        async function loadPage() {
            const grid = $('garment-grid');
            const countEl = $('garment-grid-count');
            const pageInfo = $('garment-grid-page-info');
            const prevBtn = $('garment-grid-prev');
            const nextBtn = $('garment-grid-next');
            if (!grid) return;

            grid.innerHTML = '<div class="garment-grid-loading"><i class="fas fa-spinner fa-spin"></i> 加载中...</div>';

            const offset = _currentPage * PAGE_SIZE;
            const data = await fetchProducts(offset);
            _totalItems = data.total || 0;

            if (countEl) countEl.textContent = `共 ${_totalItems} 件`;
            const totalPages = Math.max(1, Math.ceil(_totalItems / PAGE_SIZE));
            if (pageInfo) pageInfo.textContent = `第 ${_currentPage + 1} / ${totalPages} 页`;
            if (prevBtn) prevBtn.disabled = _currentPage === 0;
            if (nextBtn) nextBtn.disabled = _currentPage >= totalPages - 1;

            grid.innerHTML = '';
            if (!data.items || data.items.length === 0) {
                grid.innerHTML = '<div class="garment-grid-loading">没有找到匹配的商品</div>';
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
            _filters = await fetchFilters();
            if (!_filters) return;

            // Populate style type chips
            const styleContainer = $('filter-style');
            if (styleContainer && _filters.style_types) {
                _filters.style_types.forEach(st => {
                    const btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'filter-chip';
                    btn.dataset.value = st;
                    btn.textContent = st;
                    styleContainer.appendChild(btn);
                });
            }

            // Populate color chips
            const colorContainer = $('filter-color');
            if (colorContainer && _filters.color_families) {
                // Only show top colors (limit to avoid overflow)
                const topColors = _filters.color_families.slice(0, 15);
                topColors.forEach(c => {
                    const btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'filter-chip';
                    btn.dataset.value = c;
                    btn.textContent = c;
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
            loadPage,
        };
    })();

    async function init() {
        applyCopy();
        state.frontendConfig = normalizeFrontendConfig(FRONTEND_CONFIG_DEFAULT);
        if (el.apiKey) el.apiKey.value = localStorage.getItem('tryon_api_key') || '';
        loadExtraApiKeys();
        state.providerMode = localStorage.getItem(PROVIDER_MODE_STORAGE) || 'direct';
        state.aiStudioConfig = null;
        initAuthState();
        initErrorPanelState();
        if (el.nanoKey) el.nanoKey.value = localStorage.getItem('nanobanana_api_key') || '';
        if (el.parallelToggle) {
            el.parallelToggle.checked = localStorage.getItem(PARALLEL_ENABLED_STORAGE) === '1';
        }
        syncParallelConcurrencyControls(localStorage.getItem(PARALLEL_CONCURRENCY_STORAGE) || PARALLEL_CONCURRENCY_DEFAULT, false);
        setStylePreset(localStorage.getItem(STYLE_STORAGE) || 'default', true);
        loadHistory();
        renderHistoryList();
        setHistoryView(false);
        if (el.promptSystem) {
            fetch('/prompt').then(r => r.json()).then(d => { el.promptSystem.value = d.prompt || ''; }).catch(() => {
                el.promptSystem.value = '系统提示词读取失败';
            });
        }
        bind();
        initSampleModelPicker();
        await garmentBrowser.init();
        await fetchFrontendConfig();
        updateRecommendationUi();
        syncFreedom();
        syncInterval();
        updateModel();
        updateGarments();
        resetResult();
        renderGallery();
        refreshModelRateUi();
        renderProviderCards();
        refreshCountdowns();
        setInterval(refreshCountdowns, 1000);
        refreshRateStatus(true);
        setInterval(() => refreshRateStatus(true), 8000);
        refreshErrors();
        fetchProxyConfig();
        fetchAiStudioConfig();
        const urlPayload = parseBridgePayloadFromUrl();
        if (urlPayload) {
            await applyRecommendationPayload(urlPayload, { channel: 'query' });
        } else {
            setUploadIntakeStatus('model', defaultIntakeStatus('model'), 'neutral');
            setUploadIntakeStatus('garment', defaultIntakeStatus('garment'), 'neutral');
            setResultFeedback('info', '等待开始试穿', '可先上传用户全身照和羽绒服商品图，或从推荐系统一键带入素材。');
        }
        ready();
    }

    init().catch(err => {
        notify(err.message || '页面初始化失败', 'error');
        reportError(err.message || '页面初始化失败', '初始化');
    });
})();

