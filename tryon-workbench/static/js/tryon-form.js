(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    }
    if (root && typeof root === 'object') {
        root.TryonForm = api;
    }
})(typeof globalThis !== 'undefined' ? globalThis : window, function () {
    'use strict';

    const ASPECT_RATIOS = Object.freeze([
        'auto', '3:4', '4:5', '9:16', '1:1', '4:3', '3:2', '2:3', '5:4', '16:9', '21:9',
    ]);
    const GEMINI_IMAGE_SIZES = Object.freeze(['auto', '1K', '2K', '4K']);
    const GPT_QUALITIES = Object.freeze(['auto', 'low', 'medium', 'high']);
    const MODEL_ID_REGEX = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/;

    const BUILTIN_PROVIDERS = Object.freeze([
        {
            key: 'gemini',
            label: 'Google Gemini 官方直连',
            protocol_summary: 'Gemini Native SDK',
            enabled: true,
            configured: true,
            is_default: true,
            default_model_id: 'gemini-3.1-flash-image-preview',
            models: [
                { id: 'gemini-3.1-flash-image-preview', preset_key: 'flash', speed_tier: 'fast', badge: '新版极速', max_concurrency: 5 },
                { id: 'gemini-3-pro-image-preview', preset_key: 'pro', speed_tier: 'quality', badge: '精修', max_concurrency: 3 },
                { id: 'gemini-2.5-flash-image', preset_key: 'flash', speed_tier: 'fast', badge: '快速', max_concurrency: 5 },
            ],
        },
        {
            key: 'totokens',
            label: 'ToTokens 中转站',
            protocol_summary: 'Gemini / OpenAI 统一中转',
            enabled: true,
            configured: false,
            is_default: false,
            default_model_id: 'gpt-image-2',
            models: [
                { id: 'gemini-3.1-flash-image', preset_key: 'flash', speed_tier: 'fast', badge: '新版极速', max_concurrency: 5 },
                { id: 'gpt-image-2', preset_key: 'chatgpt', speed_tier: 'relay', badge: 'GPT 图像', max_concurrency: 3 },
                { id: 'chatgpt-image-latest', preset_key: 'chatgpt', speed_tier: 'relay', badge: 'GPT 图像', max_concurrency: 3 },
                { id: 'gpt-image-1.5', preset_key: 'chatgpt', speed_tier: 'relay', badge: 'GPT 图像', max_concurrency: 3 },
                { id: 'gpt-image-1', preset_key: 'chatgpt', speed_tier: 'relay', badge: 'GPT 图像', max_concurrency: 3 },
            ],
            api_profiles: [
                { id: 'totokens_gemini', scope: 'gemini', label: 'ToTokens Gemini', builtin: true, enabled: true, configured: false, default_model: 'gemini-3.1-flash-image', models: ['gemini-3.1-flash-image', 'gemini-3-pro-image-preview'], supported_resolutions: ['1K', '2K', '4K'], protocol: 'gemini_generate_content' },
                { id: 'totokens_gpt_1k', scope: 'gpt_1k', label: 'ToTokens GPT Image 1K', builtin: true, enabled: true, configured: false, default_model: 'gpt-image-2', models: ['gpt-image-2', 'chatgpt-image-latest', 'gpt-image-1.5', 'gpt-image-1'], supported_resolutions: ['1K'], protocol: 'openai_images_edit' },
                { id: 'totokens_gpt_2k4k', scope: 'gpt_2k4k', label: 'ToTokens GPT Image 2K/4K', builtin: true, enabled: true, configured: false, default_model: 'gpt-image-2', models: ['gpt-image-2'], supported_resolutions: ['2K', '4K'], protocol: 'openai_images_edit' },
            ],
        },
    ]);

    function inferPresetKey(modelId) {
        const low = String(modelId || '').trim().toLowerCase();
        if (!low) return 'flash';
        if (low.includes('gpt') || low.includes('chatgpt')) return 'chatgpt';
        if (low.includes('pro')) return 'pro';
        return 'flash';
    }

    function supportsGptMultiResolution(modelId) {
        const low = String(modelId || '').trim().toLowerCase();
        return low.startsWith('gpt-image-2') || low.startsWith('gpt-image-3');
    }

    function inferCapabilities(providerKey, modelId, entryCapabilities) {
        if (entryCapabilities && typeof entryCapabilities === 'object' && entryCapabilities.protocol) {
            return {
                protocol: String(entryCapabilities.protocol),
                supports_aspect_ratio: Boolean(entryCapabilities.supports_aspect_ratio ?? true),
                aspect_ratio_options: Array.isArray(entryCapabilities.aspect_ratio_options) ? [...entryCapabilities.aspect_ratio_options] : [...ASPECT_RATIOS],
                supports_image_size: Boolean(entryCapabilities.supports_image_size),
                image_size_options: Array.isArray(entryCapabilities.image_size_options) ? [...entryCapabilities.image_size_options] : [...GEMINI_IMAGE_SIZES],
                supports_quality: Boolean(entryCapabilities.supports_quality),
                quality_options: Array.isArray(entryCapabilities.quality_options) ? [...entryCapabilities.quality_options] : [...GPT_QUALITIES],
                supports_temperature: Boolean(entryCapabilities.supports_temperature),
                supports_seed: Boolean(entryCapabilities.supports_seed),
            };
        }
        const pkey = String(providerKey || 'gemini').trim().toLowerCase();
        const low = String(modelId || '').trim().toLowerCase();
        if (pkey === 'totokens' && (low.includes('gpt') || low.includes('chatgpt'))) {
            const multiRes = supportsGptMultiResolution(low);
            return {
                protocol: 'openai_images_edit',
                supports_aspect_ratio: true,
                aspect_ratio_options: [...ASPECT_RATIOS],
                supports_image_size: multiRes,
                image_size_options: multiRes ? [...GEMINI_IMAGE_SIZES] : ['auto', '1K'],
                supports_quality: true,
                quality_options: [...GPT_QUALITIES],
                supports_temperature: false,
                supports_seed: false,
            };
        }
        const supportsImageSize = !low.includes('2.5-flash');
        return {
            protocol: 'gemini_generate_content',
            supports_aspect_ratio: true,
            aspect_ratio_options: [...ASPECT_RATIOS],
            supports_image_size: supportsImageSize,
            image_size_options: supportsImageSize ? [...GEMINI_IMAGE_SIZES] : ['auto', '1K'],
            supports_quality: false,
            quality_options: ['auto'],
            supports_temperature: true,
            supports_seed: true,
        };
    }

    function validateCustomModelId(rawValue) {
        const cleaned = String(rawValue || '').trim();
        if (!cleaned) {
            return { valid: false, cleaned: '', reason: 'empty' };
        }
        if (cleaned.includes('..') || cleaned.includes('://') || cleaned.includes('?') || cleaned.includes('#') || cleaned.includes('@')) {
            return { valid: false, cleaned, reason: 'unsafe_chars' };
        }
        if (!MODEL_ID_REGEX.test(cleaned)) {
            return { valid: false, cleaned, reason: 'invalid_format' };
        }
        return { valid: true, cleaned, reason: '' };
    }

    function normalizeProvidersCatalog(runtimeStatus) {
        const rawProviders = Array.isArray(runtimeStatus?.providers) && runtimeStatus.providers.length
            ? runtimeStatus.providers
            : BUILTIN_PROVIDERS;
        return rawProviders.map(provider => {
            const pkey = String(provider?.key || 'gemini').trim().toLowerCase();
            const rawModels = Array.isArray(provider?.models) ? provider.models : [];
            const models = rawModels.map(m => {
                const id = String(m?.id || '').trim();
                if (!id) return null;
                return {
                    id,
                    label: String(m?.label || id),
                    preset_key: String(m?.preset_key || inferPresetKey(id)),
                    speed_tier: String(m?.speed_tier || 'custom'),
                    badge: String(m?.badge || ''),
                    max_concurrency: Number(m?.max_concurrency || 5),
                    is_default: Boolean(m?.is_default),
                    capabilities: inferCapabilities(pkey, id, m?.capabilities),
                };
            }).filter(Boolean);
            const rawProfiles = Array.isArray(provider?.api_profiles) ? provider.api_profiles : [];
            const api_profiles = rawProfiles.map(prof => ({
                id: String(prof?.id || '').trim(),
                scope: String(prof?.scope || 'custom').trim().toLowerCase(),
                label: String(prof?.label || prof?.id || ''),
                builtin: Boolean(prof?.builtin),
                enabled: Boolean(prof?.enabled),
                configured: Boolean(prof?.configured),
                default_model: String(prof?.default_model || ''),
                models: Array.isArray(prof?.models) ? prof.models.map(item => String(item || '').trim()).filter(Boolean) : [],
                supported_resolutions: Array.isArray(prof?.supported_resolutions) ? [...prof.supported_resolutions] : ['1K', '2K', '4K'],
                protocol: String(prof?.protocol || 'mixed'),
            })).filter(p => p.id);
            return {
                key: pkey,
                label: String(provider?.label || pkey),
                protocol_summary: String(provider?.protocol_summary || ''),
                enabled: Boolean(provider?.enabled),
                configured: Boolean(provider?.configured),
                is_default: Boolean(provider?.is_default),
                default_model_id: String(provider?.default_model_id || models[0]?.id || ''),
                models,
                api_profiles,
                legacy_configured: Boolean(provider?.legacy_configured),
            };
        });
    }

    function defaultDetailOptions() {
        return {
            aspect_ratio: 'auto',
            image_size: 'auto',
            quality: 'auto',
            temperature: '',
            seed: '',
        };
    }

    function sanitizeOptionsForCapabilities(detailOptions, capabilities) {
        const src = { ...defaultDetailOptions(), ...(detailOptions || {}) };
        const caps = inferCapabilities('gemini', '', capabilities);

        const arOptions = caps.aspect_ratio_options || ASPECT_RATIOS;
        const aspect_ratio = arOptions.includes(src.aspect_ratio) ? src.aspect_ratio : 'auto';

        let image_size = 'auto';
        if (caps.supports_image_size) {
            const validSizes = caps.image_size_options || GEMINI_IMAGE_SIZES;
            const upper = String(src.image_size || 'auto').trim().toUpperCase();
            image_size = validSizes.includes(upper) ? upper : 'auto';
        }

        let quality = 'auto';
        if (caps.supports_quality) {
            const validQuals = caps.quality_options || GPT_QUALITIES;
            const low = String(src.quality || 'auto').trim().toLowerCase();
            quality = validQuals.includes(low) ? low : 'auto';
        }

        const temperature = caps.supports_temperature ? String(src.temperature ?? '').trim() : '';
        const seed = caps.supports_seed ? String(src.seed ?? '').trim() : '';

        return { aspect_ratio, image_size, quality, temperature, seed };
    }

    function collectSubmissionOptions(detailOptions, capabilities) {
        const clean = sanitizeOptionsForCapabilities(detailOptions, capabilities);
        const caps = inferCapabilities('gemini', '', capabilities);
        const out = {};

        if (clean.aspect_ratio && clean.aspect_ratio !== 'auto') {
            out.aspect_ratio = clean.aspect_ratio;
        }
        if (caps.supports_image_size && clean.image_size && clean.image_size !== 'auto') {
            out.image_size = clean.image_size;
        }
        if (caps.supports_quality && clean.quality && clean.quality !== 'auto') {
            out.quality = clean.quality;
        }
        if (caps.supports_temperature && clean.temperature !== '') {
            const num = Number(clean.temperature);
            if (!Number.isFinite(num) || num < 0 || num > 2) {
                throw new Error('采样温度必须在 0 到 2 之间');
            }
            out.temperature = String(Math.round(num * 1000) / 1000);
        }
        if (caps.supports_seed && clean.seed !== '') {
            const num = Number(clean.seed);
            if (!Number.isInteger(num) || num < 0 || num > 2147483647) {
                throw new Error('随机种子必须是 0 到 2147483647 之间的整数');
            }
            out.seed = String(num);
        }
        return out;
    }

    function resolveTotokensRouteMatch(providerObj, modelId, detailOptions, desiredProfileId) {
        const profiles = Array.isArray(providerObj?.api_profiles) ? providerObj.api_profiles : [];
        const rawReq = String(desiredProfileId || 'auto').trim() || 'auto';
        const selectedProfileId = (rawReq !== 'auto' && profiles.some(p => p.id === rawReq)) ? rawReq : 'auto';
        const caps = inferCapabilities('totokens', modelId);
        const isGemini = caps.protocol === 'gemini_generate_content';
        const sizeUpper = String(detailOptions?.image_size || 'auto').trim().toUpperCase();
        const reqSize = sizeUpper === '1K' || sizeUpper === '2K' || sizeUpper === '4K' ? sizeUpper : 'AUTO';
        const multiResGpt = supportsGptMultiResolution(modelId);
        const usable = profiles.filter(p => p.enabled && p.configured);
        const legacyReady = Boolean(providerObj?.legacy_configured);

        if (selectedProfileId !== 'auto') {
            const target = profiles.find(p => p.id === selectedProfileId) || null;
            if (!target) {
                return { profiles, selectedProfileId: 'auto', matchedProfile: null, compatible: true, configured: Boolean(providerObj?.configured), issue: '' };
            }
            let mismatch = false;
            if (target.scope === 'gemini' && !isGemini) mismatch = true;
            if (['gpt_1k', 'gpt_2k4k', 'gpt_all'].includes(target.scope) && isGemini) mismatch = true;
            if (target.scope === 'gpt_1k' && !isGemini && (reqSize === '2K' || reqSize === '4K')) mismatch = true;
            if (target.scope === 'gpt_2k4k' && !isGemini && (!multiResGpt || reqSize === '1K')) mismatch = true;
            return {
                profiles,
                selectedProfileId,
                matchedProfile: target,
                compatible: !mismatch,
                configured: target.enabled && target.configured,
                issue: mismatch ? 'mismatch' : (!target.configured ? 'missing' : ''),
            };
        }

        const findByScope = (scope) => usable.find(p => p.scope === scope && p.models.includes(modelId)) || usable.find(p => p.scope === scope) || null;
        const findAnyByScope = (scope) => profiles.find(p => p.scope === scope) || null;
        let matched = null;
        let expectedScope = 'gemini';

        if (isGemini) {
            expectedScope = 'gemini';
            matched = findByScope('gemini') || usable.find(p => p.scope === 'custom' && p.models.includes(modelId)) || null;
        } else if (reqSize === '2K' || reqSize === '4K') {
            expectedScope = 'gpt_2k4k';
            matched = findByScope('gpt_2k4k') || findByScope('gpt_all') || usable.find(p => p.scope === 'custom' && p.models.includes(modelId)) || null;
        } else if (reqSize === '1K' || !multiResGpt) {
            expectedScope = 'gpt_1k';
            matched = findByScope('gpt_1k') || findByScope('gpt_all') || usable.find(p => p.scope === 'custom' && p.models.includes(modelId)) || null;
        } else {
            expectedScope = 'gpt_1k';
            matched = findByScope('gpt_1k') || findByScope('gpt_all') || findByScope('gpt_2k4k') || usable.find(p => p.scope === 'custom' && p.models.includes(modelId)) || null;
        }

        const hasMatchOrLegacy = Boolean(matched || legacyReady || (profiles.length === 0 && providerObj?.configured));
        return {
            profiles,
            selectedProfileId: 'auto',
            matchedProfile: matched || (hasMatchOrLegacy ? null : findAnyByScope(expectedScope)),
            compatible: true,
            configured: hasMatchOrLegacy,
            issue: hasMatchOrLegacy ? '' : 'missing',
        };
    }

    function resolveSelectionState(runtimeStatus, desiredState) {
        const providers = normalizeProvidersCatalog(runtimeStatus);
        const desiredProvider = String(desiredState?.provider || '').trim().toLowerCase();
        const desiredModelId = String(desiredState?.modelId || '').trim();
        const useCustom = Boolean(desiredState?.useCustomModel);
        const customInput = String(desiredState?.customModelId || '').trim();

        let providerObj = providers.find(p => p.key === desiredProvider);
        if (!providerObj) {
            providerObj = providers.find(p => p.is_default && p.configured)
                || providers.find(p => p.configured)
                || providers.find(p => p.is_default)
                || providers[0];
        }

        const providerKey = providerObj.key;
        const models = providerObj.models || [];
        let selectedListModel = models.find(m => m.id === desiredModelId)
            || models.find(m => m.id === providerObj.default_model_id)
            || models[0]
            || null;

        const customCheck = useCustom ? validateCustomModelId(customInput) : { valid: false, cleaned: '', reason: '' };
        const effectiveModelId = useCustom && customCheck.valid
            ? customCheck.cleaned
            : (selectedListModel?.id || providerObj.default_model_id || '');
        const entryCaps = useCustom && customCheck.valid ? null : selectedListModel?.capabilities;
        const capabilities = inferCapabilities(providerKey, effectiveModelId, entryCaps);
        const presetKey = (!useCustom && selectedListModel?.preset_key) || inferPresetKey(effectiveModelId);
        const totokensMatch = providerKey === 'totokens'
            ? resolveTotokensRouteMatch(providerObj, effectiveModelId, desiredState?.detailOptions, desiredState?.totokensProfile)
            : null;

        return {
            providers,
            providerObj,
            provider: providerKey,
            models,
            selectedListModelId: selectedListModel?.id || '',
            useCustomModel: useCustom,
            customModelValidation: useCustom ? validateCustomModelId(customInput) : { valid: true, cleaned: '', reason: '' },
            effectiveModelId,
            presetKey,
            capabilities,
            totokensMatch,
        };
    }

    return {
        ASPECT_RATIOS,
        GEMINI_IMAGE_SIZES,
        GPT_QUALITIES,
        BUILTIN_PROVIDERS,
        supportsGptMultiResolution,
        inferPresetKey,
        inferCapabilities,
        validateCustomModelId,
        normalizeProvidersCatalog,
        resolveTotokensRouteMatch,
        defaultDetailOptions,
        sanitizeOptionsForCapabilities,
        collectSubmissionOptions,
        resolveSelectionState,
    };
});
