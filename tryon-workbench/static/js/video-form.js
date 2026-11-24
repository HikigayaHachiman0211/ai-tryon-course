/** Catalog-driven video form rules, independent of the DOM. */
export const DEFAULT_VIDEO_MODELS = ['gemini-omni-flash-1.2', 'gemini-omni-flash-1.1'];

export function pickDefaultVideoModel(models, selectedSlug = '', preferredSlugs = DEFAULT_VIDEO_MODELS) {
    const list = Array.isArray(models) ? models : [];
    if (selectedSlug) {
        const selected = list.find(model => model.slug === selectedSlug);
        if (selected) return selected;
    }
    for (const slug of preferredSlugs || []) {
        const match = list.find(model => model.slug === slug);
        if (match) return match;
    }
    return list.find(model => model.params?.some(spec => ['image', 'images'].includes(spec.type))) || list[0] || null;
}

export function parseAspectRatio(label) {
    const match = String(label || '').trim().match(/^(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)$/);
    if (!match) return null;
    const w = Number(match[1]);
    const h = Number(match[2]);
    if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return null;
    return w / h;
}

export function adaptiveAspectRatio(params, width, height) {
    const spec = (params || []).find(item => item.name === 'aspect_ratio');
    const options = Array.isArray(spec?.options) ? spec.options : [];
    if (!options.length || !Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
        return spec?.default;
    }
    const imgRatio = width / height;
    const numeric = options
        .map(opt => ({ opt, ratio: parseAspectRatio(opt) }))
        .filter(entry => entry.ratio !== null);
    if (!numeric.length) {
        return options.find(opt => ['adaptive', 'auto'].includes(String(opt).toLowerCase())) ?? spec?.default;
    }
    let best = numeric[0];
    let bestDist = Infinity;
    for (const cand of numeric) {
        const dist = Math.abs(Math.log(imgRatio / cand.ratio));
        const eps = 1e-6;
        // On exact distance ties (e.g. 1:1 image vs 16:9 / 9:16), prefer vertical framing to avoid cropping heads.
        if (dist + eps < bestDist || (Math.abs(dist - bestDist) <= eps && cand.ratio <= 1 && best.ratio > 1)) {
            best = cand;
            bestDist = dist;
        }
    }
    return best.opt;
}

export function parametersFor(model, provider = '') {
    if (provider && model.providers?.length) {
        const channel = model.providers.find(item => item.provider === provider);
        if (!channel) throw new Error('invalid_provider');
        return channel.params ?? model.params ?? [];
    }
    return model.params ?? [];
}

export function defaultsFor(params) {
    return Object.fromEntries(params.filter(spec => spec.default !== undefined && spec.default !== null).map(spec => [spec.name, spec.default]));
}

export function collectInput(params, raw) {
    const result = {};
    for (const spec of params) {
        let value = raw[spec.name];
        if (value === '' || value === undefined || value === null) value = spec.default;
        if (value === '' || value === undefined || value === null || (Array.isArray(value) && !value.length)) {
            if (spec.required) throw new Error(`${spec.name}: required`);
            continue;
        }
        if (spec.type === 'number' || spec.type === 'integer') {
            value = Number(value);
            if (!Number.isFinite(value) || (spec.type === 'integer' && !Number.isInteger(value)) ||
                (spec.min !== undefined && value < spec.min) || (spec.max !== undefined && value > spec.max)) {
                throw new Error(`${spec.name}: ${spec.min ?? '…'} – ${spec.max ?? '…'}`);
            }
        }
        if (['images', 'videos', 'audios'].includes(spec.type)) {
            value = Array.isArray(value) ? value : String(value).split('\n').map(item => item.trim()).filter(Boolean);
            if (spec.maxItems && value.length > spec.maxItems) throw new Error(`${spec.name}: max ${spec.maxItems}`);
        }
        if (spec.options?.length && !spec.options.some(option => option === value)) throw new Error(`${spec.name}: invalid option`);
        if (typeof value === 'string' && value.length > (spec.maxLength ?? 10000)) throw new Error(`${spec.name}: max ${spec.maxLength ?? 10000}`);
        result[spec.name] = value;
    }
    return result;
}

export function bindSourceImage(params, values, url, field = '') {
    const images = params.filter(spec => ['image', 'images'].includes(spec.type));
    const spec = images.find(item => item.name === field) ?? images.find(item => ['image_url', 'start_image_url', 'first_frame_image'].includes(item.name)) ?? images[0];
    if (!spec) throw new Error('no_image_input');
    return { ...values, [spec.name]: spec.type === 'images' ? [url] : url };
}
