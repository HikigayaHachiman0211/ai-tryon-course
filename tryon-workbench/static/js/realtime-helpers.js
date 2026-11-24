export const XMAX_MODELS = ['x2.1', 'x2.1-flash'];

export const XMAX_PRESET_AUTO = 'auto';

export const REACTOR_MODELS = ['reactor/xmax-x2-1', 'xmax/x2'];
export const REACTOR_DEFAULT_MODEL = 'reactor/xmax-x2-1';

export const XMAX_CAMERA_PRESETS = {
    'x2.1': ['1080x1920', '1920x1080', '1152x1536', '1536x1152', '1408x1408'],
    'x2.1-flash': ['704x1280', '1280x704', '768x1024', '1024x768', '960x960'],
};

export const DECART_DEFAULT_PROMPT =
    'Substitute the current top with the jacket in the reference image. Preserve the jacket color, stitching and length.';

export const XMAX_DEFAULT_PROMPT =
    '将参考图的服装穿戴到视频角色身上，跟随角色原有动作。';

export const REACTOR_DEFAULT_PROMPT =
    '视频中人物衣服替换成参考图中衣服，保持人物面部与动作自然连贯。';

export const PROMPT_PRESETS = {
    decart: [
        { key: 'default', prompt: DECART_DEFAULT_PROMPT },
        {
            key: 'quilted',
            prompt:
                'Substitute the current outerwear with the down jacket in the reference image. Preserve quilting seams, collar structure, zipper details, and natural loft while keeping natural body motion.',
        },
        {
            key: 'street',
            prompt:
                'Replace the outerwear with the parka or down jacket in the reference image in an oversized relaxed silhouette, keeping true fabric texture, hood/collar proportions, and authentic folds.',
        },
        {
            key: 'tailored',
            prompt:
                'Replace the current coat with the reference down coat in a clean tailored fit, matching exact color tone, matte/gloss finish, and seam alignment.',
        },
    ],
    xmax: [
        { key: 'xmaxOutfit', prompt: '将参考图的服装穿戴到视频角色身上，跟随角色原有动作。' },
        { key: 'xmaxOuterwear', prompt: '将参考图的外套穿到视频人物身上，保持人物面部与背景不变。' },
        { key: 'xmaxTop', prompt: '将参考图的上衣穿到视频角色身上，其他都保持不变。' },
        { key: 'xmaxInner', prompt: '外套保持不变，将上衣内搭换成参考图当中的。' },
        { key: 'xmaxFull', prompt: '将参考图的衣服应用到视频角色身上，包括帽子，保持自然贴合。' },
    ],
    reactor: [
        { key: 'xmaxOutfit', prompt: '视频中人物衣服替换成参考图中衣服，保持人物面部与动作自然连贯。' },
        { key: 'xmaxOuterwear', prompt: '视频中人物衣服替换成参考图中衣服，仅替换外套并保留人物面部与背景。' },
        { key: 'xmaxTop', prompt: '视频中人物衣服替换成参考图中衣服，仅更换上衣，其余保持不变。' },
        { key: 'xmaxInner', prompt: '视频中人物衣服替换成参考图中衣服，外套不变并将内搭替换成参考图款式。' },
        { key: 'xmaxFull', prompt: '视频中人物衣服替换成参考图中衣服，整套服装与配饰自然贴合。' },
    ],
};

export function resolveProvidersStatus(payload) {
    if (payload && typeof payload === 'object' && payload.providers && typeof payload.providers === 'object') {
        const decart = payload.providers.decart || { available: false, reason: 'disabled' };
        const xmax = payload.providers.xmax || { available: false, reason: 'disabled' };
        const reactor = payload.providers.reactor || { available: false, reason: 'disabled' };
        const availableProviders = [];
        if (decart.available) availableProviders.push('decart');
        if (reactor.available) availableProviders.push('reactor');
        if (xmax.available) availableProviders.push('xmax');
        const defaultProvider =
            payload.default_provider && payload.providers[payload.default_provider]?.available
                ? payload.default_provider
                : availableProviders[0] || payload.default_provider || 'decart';
        return { decart, xmax, reactor, availableProviders, defaultProvider };
    }

    const legacy = payload && typeof payload === 'object' ? payload : { available: false, reason: 'disabled' };
    const decart = { provider: 'decart', ...legacy };
    const xmax = { available: false, reason: 'disabled' };
    const reactor = { available: false, reason: 'disabled' };
    return {
        decart,
        xmax,
        reactor,
        availableProviders: decart.available ? ['decart'] : [],
        defaultProvider: 'decart',
    };
}

export function calculateMaxCents(provider, cfg, seconds) {
    const cleanSeconds = Number(seconds);
    if (!Number.isInteger(cleanSeconds) || cleanSeconds <= 0) return 0;
    if (provider === 'xmax' || provider === 'reactor') {
        const fallbackCpm = provider === 'reactor' ? 11 : 10;
        const cpm = Math.max(1, Number(cfg?.cents_per_minute ?? fallbackCpm));
        return Math.max(1, Math.ceil((cleanSeconds * cpm) / 60));
    }
    const cps = Math.max(1, Number(cfg?.cents_per_second ?? 2));
    return cleanSeconds * cps;
}

export function calculateMaxCredits(cfg, seconds, fallbackCps = 1) {
    const cleanSeconds = Number(seconds);
    if (!Number.isInteger(cleanSeconds) || cleanSeconds <= 0) return 0;
    const cps = Math.max(1, Number(cfg?.credits_per_second ?? fallbackCps));
    return Math.ceil(cleanSeconds * cps);
}

export function durationCandidates(minSeconds, maxSeconds) {
    const minS = Math.max(10, Number(minSeconds || 10));
    const maxS = Math.max(minS, Number(maxSeconds || minS));
    const base = [10, 15, 20, 30, 45, 60, 90, 120].filter(v => v >= minS && v <= maxS);
    if (!base.includes(minS)) base.unshift(minS);
    if (!base.includes(maxS)) base.push(maxS);
    return base;
}

export function cameraPresetForModel(model, preferredPreset) {
    const cleanModel = XMAX_MODELS.includes(model) ? model : 'x2.1';
    const allowed = XMAX_CAMERA_PRESETS[cleanModel];
    if (preferredPreset && allowed.includes(preferredPreset)) return preferredPreset;
    return allowed[0];
}

export function parsePresetDimensions(preset) {
    const match = /^(\d{3,4})x(\d{3,4})$/i.exec(String(preset || '').trim());
    if (!match) return { width: 1080, height: 1920 };
    return { width: Number(match[1]), height: Number(match[2]) };
}

export function pickBestXmaxPreset(model, sourceDims = null, viewport = null) {
    const cleanModel = XMAX_MODELS.includes(model) ? model : 'x2.1';
    const allowed = XMAX_CAMERA_PRESETS[cleanModel];
    const sw = Number(sourceDims?.width);
    const sh = Number(sourceDims?.height);
    if (Number.isFinite(sw) && Number.isFinite(sh) && sw > 0 && sh > 0) {
        const srcRatio = sw / sh;
        let bestPreset = allowed[0];
        let bestDiff = Infinity;
        for (const preset of allowed) {
            const { width: cw, height: ch } = parsePresetDimensions(preset);
            const diff = Math.abs(Math.log(srcRatio / (cw / ch)));
            if (diff < bestDiff) {
                bestDiff = diff;
                bestPreset = preset;
            }
        }
        return bestPreset;
    }

    const vw = Number(viewport?.width);
    const vh = Number(viewport?.height);
    if (Number.isFinite(vw) && Number.isFinite(vh) && vw > 0 && vh > 0) {
        return vw >= vh ? (allowed[1] || allowed[0]) : allowed[0];
    }

    return allowed[1] || allowed[0];
}

export function computeStageAspectRatio(dims = null, fallback = 4 / 5) {
    const w = Number(dims?.width);
    const h = Number(dims?.height);
    const raw = (Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0)
        ? (w / h)
        : Number(fallback || (4 / 5));
    const clamped = Math.min(16 / 9, Math.max(9 / 16, raw));
    const ratio = Number(clamped.toFixed(4));
    const orientation = ratio > 1.15 ? 'landscape' : ratio < 0.85 ? 'portrait' : 'square';
    return { ratio, orientation };
}

export function needsAspectCenterCrop(sourceDims, targetDims, threshold = 0.22) {
    const sw = Number(sourceDims?.width);
    const sh = Number(sourceDims?.height);
    const tw = Number(targetDims?.width);
    const th = Number(targetDims?.height);
    if (!Number.isFinite(sw) || !Number.isFinite(sh) || sw <= 0 || sh <= 0) return false;
    if (!Number.isFinite(tw) || !Number.isFinite(th) || tw <= 0 || th <= 0) return false;
    return Math.abs(Math.log((sw / sh) / (tw / th))) > threshold;
}

export function computeCenterCropRect(srcWidth, srcHeight, targetWidth, targetHeight) {
    const srcW = Math.max(2, Math.round(Number(srcWidth) || 0));
    const srcH = Math.max(2, Math.round(Number(srcHeight) || 0));
    const targetW = Math.max(2, Math.round(Number(targetWidth) || 0));
    const targetH = Math.max(2, Math.round(Number(targetHeight) || 0));
    const srcRatio = srcW / srcH;
    const targetRatio = targetW / targetH;
    let sx = 0;
    let sy = 0;
    let sw = srcW;
    let sh = srcH;
    if (srcRatio > targetRatio) {
        sh = srcH;
        sw = Math.max(2, Math.min(srcW, Math.round(srcH * targetRatio)));
        sx = Math.max(0, Math.floor((srcW - sw) / 2));
    } else {
        sw = srcW;
        sh = Math.max(2, Math.min(srcH, Math.round(srcW / targetRatio)));
        sy = Math.max(0, Math.floor((srcH - sh) / 2));
    }
    const outWidth = Math.max(2, sw - (sw % 2));
    const outHeight = Math.max(2, sh - (sh % 2));
    return { sx, sy, sw, sh, outWidth, outHeight };
}

function gcd(a, b) {
    let x = Math.abs(a);
    let y = Math.abs(b);
    while (y) {
        const tmp = y;
        y = x % y;
        x = tmp;
    }
    return x || 1;
}

export function presetAspectLabel(preset) {
    const clean = String(preset || '').trim();
    const { width, height } = parsePresetDimensions(clean);
    if (!/^\d{3,4}x\d{3,4}$/i.test(clean)) return '1080×1920 (9:16)';
    const divisor = gcd(width, height);
    return `${width}×${height} (${Math.round(width / divisor)}:${Math.round(height / divisor)})`;
}

export function reactorModelLabelKey(model) {
    return String(model || '').toLowerCase() === 'xmax/x2' ? 'reactorModelX20' : 'reactorModelX21';
}

export const KNOWN_ERROR_CODES = new Set([
    'access_denied',
    'invalid_access_code',
    'invalid_duration',
    'invalid_model',
    'quote_changed',
    'unavailable',
    'daily_budget',
    'monthly_budget',
    'visitor_budget',
    'budget_reset',
    'rate_limit',
    'busy',
    'visitor_busy',
    'session_unavailable',
    'session_limit',
    'ledger_unavailable',
    'request_failed',
    'sdk_unavailable',
    'invalid_image',
    'invalid_source_media',
    'unsafe_image',
    'camera_denied',
    'camera_not_readable',
    'camera_ended',
    'connection_failed',
    'connection_lost',
    'no_output',
    'provider_error',
    'session_error',
    'garment_rejected',
    'moderation_violation',
    'insufficient_credits',
]);

export function sanitizeRealtimeDetail(raw) {
    if (raw == null) return '';
    let text = String(raw)
        .replace(/\b(?:uk|tk|rk)-[A-Za-z0-9_-]+/gi, '[redacted]')
        .replace(/\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]*)?/g, '[redacted]')
        .replace(/\bBearer\s+[A-Za-z0-9._~+/-]+=*/gi, 'Bearer [redacted]')
        .replace(/([?&](?:api_key|apikey|token|secret|access_token)=)[^&\s]+/gi, '$1[redacted]')
        .replace(/\s+/g, ' ')
        .trim();
    if (text.length > 180) text = text.slice(0, 177) + '...';
    return text;
}

export function formatRealtimeErrorDetail(err, stage = '') {
    if (!err && !stage) return '';
    const cleanStage = typeof stage === 'string' ? stage.replace(/[^a-z0-9_-]/gi, '').slice(0, 24) : '';
    if (!err) return cleanStage ? `[${cleanStage}]` : '';
    if (typeof err === 'string') {
        const cleanMsg = sanitizeRealtimeDetail(err);
        if (!cleanMsg) return cleanStage ? `[${cleanStage}]` : '';
        return cleanStage ? `[${cleanStage}] ${cleanMsg}` : cleanMsg;
    }

    const tags = [];
    if (cleanStage) tags.push(cleanStage);
    const code = typeof err.code === 'string' && err.code.trim() ? err.code.trim() : '';
    const name = typeof err.name === 'string' && err.name.trim() && err.name !== 'Error' ? err.name.trim() : '';
    if (code) tags.push(code);
    else if (name) tags.push(name);
    if (err.apiCode !== undefined && err.apiCode !== null && err.apiCode !== '') {
        tags.push(`api=${err.apiCode}`);
    }
    if (err.httpStatus !== undefined && err.httpStatus !== null && err.httpStatus !== '') {
        tags.push(`http=${err.httpStatus}`);
    }
    const prefix = tags.length ? `[${tags.join(' · ')}]` : '';
    const rawMsg = typeof err.message === 'string' ? err.message : '';
    const cleanMsg = sanitizeRealtimeDetail(rawMsg);
    if (prefix && cleanMsg) return sanitizeRealtimeDetail(`${prefix} ${cleanMsg}`);
    return sanitizeRealtimeDetail(prefix || cleanMsg || String(err));
}

export function normalizeClientStopReason(errorCode, stage = '') {
    const raw = String(errorCode || '').trim().toLowerCase();
    const mapped = {
        limitreached: 'limit_reached',
        limit_reached: 'limit_reached',
        hiddenstop: 'hidden_stop',
        hidden_stop: 'hidden_stop',
        camera_not_readable: 'camera_not_readable',
        camera_denied: 'camera_denied',
        camera_ended: 'camera_ended',
        session_error: 'session_error',
        session_unavailable: 'session_unavailable',
        session_limit: 'session_limit',
        insufficient_credits: 'insufficient_credits',
        unsafe_image: 'unsafe_image',
        garment_rejected: 'garment_rejected',
        moderation_violation: 'moderation_violation',
        no_output: 'no_output',
        connection_lost: 'connection_lost',
        connection_failed: 'connection_failed',
        provider_error: 'provider_error',
        sdk_unavailable: 'sdk_unavailable',
        invalid_image: 'invalid_image',
        invalid_source_media: 'invalid_source_media',
        request_failed: 'request_failed',
        stopped: 'stopped',
    }[raw];
    if (mapped) return mapped;
    if (stage === 'upload' && raw) return 'upload_failed';
    if (stage === 'camera' && raw) return 'camera_not_readable';
    const clean = raw.replace(/[^a-z0-9_]/g, '_').replace(/_+/g, '_').replace(/^_+|_+$/g, '').slice(0, 32);
    return /^[a-z0-9_]{1,32}$/.test(clean) ? clean : 'stopped';
}

export function mapXmaxErrorCode(err) {
    if (!err) return 'provider_error';
    const code = String(err.code || '').toUpperCase();
    const name = String(err.name || '').toUpperCase();
    const apiCode = Number(err.apiCode);
    const msg = String(err.message || '').toLowerCase();

    if (apiCode === 46019 || msg.includes('insufficient')) return 'insufficient_credits';
    if (apiCode === 46032 || msg.includes('session limit')) return 'session_limit';
    if (apiCode === 46018) return 'session_unavailable';
    if (
        apiCode === 46005
        || msg.includes('模型类型不存在')
        || msg.includes('model not found')
        || msg.includes('unsupported model')
    ) {
        return 'invalid_model';
    }
    if (code === 'UNSAFE_IMAGE') return 'unsafe_image';
    if (code === 'CAMERA_PERMISSION_DENIED' || name === 'NOTALLOWEDERROR') return 'camera_denied';
    if (
        name === 'NOTREADABLEERROR'
        || msg.includes('not_readable')
        || msg.includes('notreadableerror')
        || msg.includes('could not start video source')
    ) {
        return 'camera_not_readable';
    }
    if (code === 'UPLOAD_ERROR') return 'garment_rejected';
    if (code === 'TIMEOUT') return 'no_output';
    if (code === 'SESSION_ERROR' && msg.includes('rtc join information')) return 'session_error';
    if (code === 'NETWORK_ERROR' || code === 'RTC_ERROR' || code === 'SESSION_ERROR') return 'connection_lost';
    return 'provider_error';
}

export function mapReactorErrorCode(err) {
    if (!err) return 'provider_error';
    const code = String(err.code || '').toUpperCase();
    const cmdCode = String(err.command_code || '').toLowerCase();
    const status = Number(err.status);
    const msg = String(err.message || '').toLowerCase();

    if (code === 'UNAUTHORIZED' || status === 401 || status === 403) return 'session_unavailable';
    if (code === 'RATE_LIMITED' || status === 429) return 'session_limit';
    if (cmdCode === 'invalid_image' || msg.includes('invalid_image')) return 'garment_rejected';
    if (msg.includes('moderation') || code === 'MODERATION') return 'moderation_violation';
    if (msg.includes('insufficient') || msg.includes('credit')) return 'insufficient_credits';
    if (code === 'REQUEST_TIMEOUT') return 'no_output';
    if (code === 'NOT_FOUND' || code === 'CONFLICT' || code === 'SESSION_TERMINAL' || code === 'NETWORK_ERROR' || code === 'TRANSPORT_ERROR' || code === 'DISCONNECTED') {
        return 'connection_lost';
    }
    return 'provider_error';
}

export const STAGE_DISPLAY_MODES = ['inline', 'maximized', 'floating', 'popout'];
export const STAGE_LAYOUTS = ['dual', 'remote', 'pip-overlay', 'local'];
export const STAGE_FIT_MODES = ['cover', 'contain'];
export const FLOATING_SIZE_PRESETS = {
    sm: { width: 380, height: 340 },
    md: { width: 520, height: 430 },
    lg: { width: 680, height: 540 },
};

export function clampFloatingRect(rect, viewport, margin = 12) {
    const vw = Math.max(320, Number(viewport?.width || 1280));
    const vh = Math.max(240, Number(viewport?.height || 720));
    const m = Math.max(0, Number(margin || 0));
    const width = Math.min(Math.max(280, Number(rect?.width || 520)), Math.max(280, vw - m * 2));
    const height = Math.min(Math.max(220, Number(rect?.height || 430)), Math.max(220, vh - m * 2));
    const maxLeft = Math.max(m, vw - width - m);
    const maxTop = Math.max(m, vh - height - m);
    const rawLeft = Number(rect?.left);
    const rawTop = Number(rect?.top);
    const left = Number.isFinite(rawLeft) ? Math.min(Math.max(m, rawLeft), maxLeft) : maxLeft;
    const top = Number.isFinite(rawTop) ? Math.min(Math.max(m, rawTop), maxTop) : maxTop;
    return {
        left: Math.round(left),
        top: Math.round(top),
        width: Math.round(width),
        height: Math.round(height),
    };
}

export function nextFloatingSizePreset(current) {
    if (current === 'sm') return 'md';
    if (current === 'md') return 'lg';
    if (current === 'lg') return 'sm';
    return 'md';
}
