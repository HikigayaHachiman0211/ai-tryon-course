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
        errors: [],
        rateStatus: null,
        minuteResetSec: null,
        dailyResetSec: null,
        errorAnalyzing: new Set(),
        recommendation: null,
        frontendConfig: null,
        trustedMessageOrigin: '',
        runtimeAvailable: false,
    };

    const MODEL_LIMITS = {
        flash: { name: 'Gemini Flash Image', rpm: 100, tpm: 200000, rpd: 1000 },
        pro: { name: 'Gemini Pro Image', rpm: 20, tpm: 100000, rpd: 250 },
    };

    const SAMPLE_MODELS = [
        { id: 'male-mannequin-1', name: '通用男模 1', gender: 'male', filename: 'mannequin-male-1.png' },
        { id: 'male-mannequin-2', name: '通用男模 2', gender: 'male', filename: 'mannequin-male-2.png' },
        { id: 'female-mannequin-1', name: '通用女模 1', gender: 'female', filename: 'mannequin-female-1.png' },
        { id: 'female-mannequin-2', name: '通用女模 2', gender: 'female', filename: 'mannequin-female-2.png' },
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
        return /^data:image\/(png|jpe?g|webp);base64,/.test(value);
    }

    function capStr(value) {
        const s = asTrimmedString(value);
        return s.length <= BRIDGE_STR_MAX ? s : s.slice(0, BRIDGE_STR_MAX);
    }

    function isTrustedBridgeOrigin(origin) {
        const current = asTrimmedString(origin);
        // Accept empty origin (same-window edge cases)
        if (!current) return true;
        // Same-origin is always allowed
        if (current === window.location.origin) return true;
        // Check against the configured recommend app origin only
        const trusted = asTrimmedString(recommendOriginFromConfig());
        if (trusted) return trusted === current;
        // Fallback: trust the origin derived from the URL-channel payload's returnUrl.
        // This allows photo delivery via postMessage when recommend_app_url is not configured in admin.
        const fallback = asTrimmedString(state.trustedMessageOrigin);
        if (fallback) return fallback === current;
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
        // Record the opener's origin from returnUrl so postMessage photo delivery works
        // even when recommend_app_url is not configured in the workbench admin settings.
        if (meta.channel === 'query' && !state.trustedMessageOrigin && isHttpUrl(payload.returnUrl)) {
            try {
                const retOrigin = new URL(payload.returnUrl).origin;
                if (retOrigin && retOrigin !== window.location.origin) state.trustedMessageOrigin = retOrigin;
            } catch (_) {}
        }
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
        notify('未配置推荐列表地址。', 'warning');
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
                const ackOrigin = asTrimmedString(event.origin) || '*';
                try {
                    event.source.postMessage({
                        type: BRIDGE_ACK_TYPE,
                        version: 1,
                        productId: asTrimmedString(payload.productId),
                    }, ackOrigin);
                } catch (_) { /* ignore ACK delivery failure */ }
            }
        } catch (e) {
            notify(e.message || '推荐系统联动失败', 'error');
            reportError(e.message || '推荐系统联动失败', '推荐联动-postMessage');
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
        document.title = 'AI 羽绒服试穿工作台';
        if (el.genText) el.genText.textContent = '一键生成试穿结果';
        if (el.resultImg) el.resultImg.alt = '羽绒服试穿结果';
        if (el.downOne) el.downOne.innerHTML = '<i class="fas fa-download"></i> 下载主结果';
        if (el.errorToggle) el.errorToggle.title = '系统错误日志';
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

    function closeAllSidebars() {
        el.errorSidebar?.classList.remove('open');
        el.errorOverlay?.classList.add('hidden');
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
        if (which === 'error') refreshErrors();
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

    async function submitTask(garment, freedom) {
        const fd = new FormData();
        fd.append('target_image', state.model);
        fd.append('reference_image', garment);
        fd.append('model', state.modelType);
        fd.append('freedom', String(freedom));
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
        const parallel = getParallelSettings(list.length);

        writeLog(`开始生成，共 ${list.length} 个任务。`);
        if (parallel.enabled) {
            writeLog(`并行生成已开启，并发=${parallel.concurrency}`);
        }
        setResultFeedback('info', 'AI 正在生成试穿结果', '你可以留在当前页面等待，也可以展开高级区查看系统日志与通道状态。');

        const runOneTask = async (i) => {
            if (state.abort) return;
            const g = list[i];
            const f = getFreedom();
            const garmentType = getGarmentType();
            const garmentTypeLabel = garmentType ? `, 衣物类型=${garmentType}` : '';
            writeLog(`任务 ${i + 1}/${list.length}: 服装=${g}, 自由度=${f}${garmentTypeLabel}`);
            try {
                const id = await submitTask(g, f);
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
                    : `共生成 ${ok} 张试穿结果。可直接下载，或切换风格后重新生成。`
            );
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
        el.returnToRecommendBtn?.addEventListener('click', () => navigateToRecommendation('return'));
        el.switchProductBtn?.addEventListener('click', () => navigateToRecommendation('switch'));

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
        const active = cards.find(c => c.classList.contains('active'));
        setModel(active ? (active.dataset.model || 'flash') : 'flash');

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

    async function fetchRuntimeStatus() {
        try {
            const r = await fetch('/api/runtime-status', { cache: 'no-store' });
            const d = await r.json();
            state.runtimeAvailable = Boolean(
                r.ok && d.tryon_enabled === true && d.configured === true
            );
            if (d.tryon_enabled === false) {
                notify('试衣服务暂时停用', 'warning');
            } else if (d.configured === false) {
                notify('试衣服务配置未完成，请联系管理员', 'warning');
            }
        } catch (_) {
            state.runtimeAvailable = false;
            notify('暂时无法确认试衣服务状态，请稍后刷新重试', 'warning');
        }
        ready();
    }

    async function init() {
        applyCopy();
        state.frontendConfig = normalizeFrontendConfig(FRONTEND_CONFIG_DEFAULT);
        initErrorPanelState();
        if (el.parallelToggle) {
            el.parallelToggle.checked = localStorage.getItem(PARALLEL_ENABLED_STORAGE) === '1';
        }
        syncParallelConcurrencyControls(localStorage.getItem(PARALLEL_CONCURRENCY_STORAGE) || PARALLEL_CONCURRENCY_DEFAULT, false);
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
        refreshCountdowns();
        setInterval(refreshCountdowns, 1000);
        refreshRateStatus(true);
        setInterval(() => refreshRateStatus(true), 8000);
        refreshErrors();
        await fetchRuntimeStatus();
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

