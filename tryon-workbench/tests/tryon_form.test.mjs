import test from 'node:test';
import assert from 'node:assert/strict';

import '../static/js/tryon-form.js';

const TryonForm = globalThis.TryonForm;

test('tryon-form infers capabilities accurately for Gemini and GPT models', () => {
    const proCaps = TryonForm.inferCapabilities('gemini', 'gemini-3-pro-image-preview');
    assert.equal(proCaps.protocol, 'gemini_generate_content');
    assert.equal(proCaps.supports_image_size, true);
    assert.deepEqual(proCaps.image_size_options, ['auto', '1K', '2K', '4K']);
    assert.equal(proCaps.supports_quality, false);
    assert.equal(proCaps.supports_temperature, true);
    assert.equal(proCaps.supports_seed, true);

    const flash25Caps = TryonForm.inferCapabilities('gemini', 'gemini-2.5-flash-image');
    assert.equal(flash25Caps.supports_image_size, false);
    assert.deepEqual(flash25Caps.image_size_options, ['auto', '1K']);

    const gptCaps = TryonForm.inferCapabilities('totokens', 'gpt-image-2');
    assert.equal(gptCaps.protocol, 'openai_images_edit');
    assert.equal(gptCaps.supports_aspect_ratio, true);
    assert.equal(gptCaps.supports_image_size, true);
    assert.deepEqual(gptCaps.image_size_options, ['auto', '1K', '2K', '4K']);
    assert.equal(gptCaps.supports_quality, true);
    assert.deepEqual(gptCaps.quality_options, ['auto', 'low', 'medium', 'high']);
    assert.equal(gptCaps.supports_temperature, false);
    assert.equal(gptCaps.supports_seed, false);

    const gpt1Caps = TryonForm.inferCapabilities('totokens', 'gpt-image-1');
    assert.equal(gpt1Caps.protocol, 'openai_images_edit');
    assert.equal(gpt1Caps.supports_image_size, false);

    const relayGeminiCaps = TryonForm.inferCapabilities('totokens', 'gemini-3.1-flash-image');
    assert.equal(relayGeminiCaps.protocol, 'gemini_generate_content');
    assert.equal(relayGeminiCaps.supports_image_size, true);
    assert.equal(relayGeminiCaps.supports_quality, false);
    assert.equal(relayGeminiCaps.supports_seed, true);
});

test('validateCustomModelId rejects empty and injection-like strings', () => {
    assert.equal(TryonForm.validateCustomModelId('').reason, 'empty');
    assert.equal(TryonForm.validateCustomModelId('  ').reason, 'empty');
    assert.equal(TryonForm.validateCustomModelId('../etc/passwd').reason, 'unsafe_chars');
    assert.equal(TryonForm.validateCustomModelId('https://evil.example/model').reason, 'unsafe_chars');
    assert.equal(TryonForm.validateCustomModelId('gpt-image-2?key=1').reason, 'unsafe_chars');
    assert.equal(TryonForm.validateCustomModelId('user@host').reason, 'unsafe_chars');
    assert.equal(TryonForm.validateCustomModelId('bad model with spaces').reason, 'invalid_format');

    const ok1 = TryonForm.validateCustomModelId('  gemini-3.1-flash-image-preview  ');
    assert.equal(ok1.valid, true);
    assert.equal(ok1.cleaned, 'gemini-3.1-flash-image-preview');

    const ok2 = TryonForm.validateCustomModelId('publishers/google/models/gemini-2.5-flash-image');
    assert.equal(ok2.valid, true);
});

test('sanitizeOptionsForCapabilities strips incompatible options on model switch', () => {
    const geminiInput = {
        aspect_ratio: '3:4',
        image_size: '2K',
        quality: 'high',
        temperature: '0.8',
        seed: '42',
    };
    const gptCaps = TryonForm.inferCapabilities('totokens', 'gpt-image-2');
    const cleanForGpt = TryonForm.sanitizeOptionsForCapabilities(geminiInput, gptCaps);
    assert.deepEqual(cleanForGpt, {
        aspect_ratio: '3:4',
        image_size: '2K',
        quality: 'high',
        temperature: '',
        seed: '',
    });

    const gpt1Caps = TryonForm.inferCapabilities('totokens', 'gpt-image-1');
    const cleanForGpt1 = TryonForm.sanitizeOptionsForCapabilities(geminiInput, gpt1Caps);
    assert.deepEqual(cleanForGpt1, {
        aspect_ratio: '3:4',
        image_size: 'auto',
        quality: 'high',
        temperature: '',
        seed: '',
    });

    const proCaps = TryonForm.inferCapabilities('gemini', 'gemini-3-pro-image-preview');
    const cleanForPro = TryonForm.sanitizeOptionsForCapabilities(geminiInput, proCaps);
    assert.deepEqual(cleanForPro, {
        aspect_ratio: '3:4',
        image_size: '2K',
        quality: 'auto',
        temperature: '0.8',
        seed: '42',
    });
});

test('collectSubmissionOptions omits auto defaults and enforces numeric ranges', () => {
    const proCaps = TryonForm.inferCapabilities('gemini', 'gemini-3-pro-image-preview');
    assert.deepEqual(
        TryonForm.collectSubmissionOptions(TryonForm.defaultDetailOptions(), proCaps),
        {}
    );

    const submitted = TryonForm.collectSubmissionOptions({
        aspect_ratio: '4:5',
        image_size: '4K',
        quality: 'high',
        temperature: '0.75',
        seed: '123456',
    }, proCaps);
    assert.deepEqual(submitted, {
        aspect_ratio: '4:5',
        image_size: '4K',
        temperature: '0.75',
        seed: '123456',
    });

    assert.throws(
        () => TryonForm.collectSubmissionOptions({ temperature: '2.5' }, proCaps),
        /0 到 2/
    );
    assert.throws(
        () => TryonForm.collectSubmissionOptions({ seed: '12.5' }, proCaps),
        /0 到 2147483647/
    );
    assert.throws(
        () => TryonForm.collectSubmissionOptions({ seed: '2147483648' }, proCaps),
        /0 到 2147483647/
    );
});

test('resolveSelectionState switches providers, models, and keeps explicit provider selection', () => {
    const runtime = {
        providers: [
            {
                key: 'gemini',
                label: 'Google Gemini 官方直连',
                enabled: true,
                configured: true,
                is_default: true,
                default_model_id: 'gemini-3.1-flash-image-preview',
                models: [
                    { id: 'gemini-3.1-flash-image-preview', preset_key: 'flash', max_concurrency: 5 },
                    { id: 'gemini-3-pro-image-preview', preset_key: 'pro', max_concurrency: 3 },
                ],
            },
            {
                key: 'totokens',
                label: 'ToTokens 中转站',
                enabled: false,
                configured: false,
                is_default: false,
                default_model_id: 'gpt-image-2',
                models: [
                    { id: 'gpt-image-2', preset_key: 'chatgpt', max_concurrency: 3 },
                ],
            },
        ],
    };

    const initial = TryonForm.resolveSelectionState(runtime, {});
    assert.equal(initial.provider, 'gemini');
    assert.equal(initial.effectiveModelId, 'gemini-3.1-flash-image-preview');
    assert.equal(initial.presetKey, 'flash');

    const pickedUnconfigured = TryonForm.resolveSelectionState(runtime, {
        provider: 'totokens',
        modelId: 'gpt-image-2',
    });
    assert.equal(pickedUnconfigured.provider, 'totokens');
    assert.equal(pickedUnconfigured.effectiveModelId, 'gpt-image-2');
    assert.equal(pickedUnconfigured.capabilities.supports_quality, true);

    const customActive = TryonForm.resolveSelectionState(runtime, {
        provider: 'gemini',
        modelId: 'gemini-3.1-flash-image-preview',
        useCustomModel: true,
        customModelId: 'gemini-custom-pro-exp',
    });
    assert.equal(customActive.effectiveModelId, 'gemini-custom-pro-exp');
    assert.equal(customActive.presetKey, 'pro');
    assert.equal(customActive.capabilities.supports_temperature, true);
});

test('resolveTotokensRouteMatch routes Gemini, GPT 1K, and GPT 2K/4K keys strictly', () => {
    const totokensProvider = {
        key: 'totokens',
        enabled: true,
        configured: true,
        api_profiles: [
            { id: 'totokens_gemini', scope: 'gemini', label: 'Gemini Key', enabled: true, configured: true, models: ['gemini-3.1-flash-image'] },
            { id: 'totokens_gpt_1k', scope: 'gpt_1k', label: 'GPT 1K Key', enabled: true, configured: true, models: ['gpt-image-2'] },
            { id: 'totokens_gpt_2k4k', scope: 'gpt_2k4k', label: 'GPT 2K/4K Key', enabled: true, configured: false, models: ['gpt-image-2'] },
        ],
    };

    const gemMatch = TryonForm.resolveTotokensRouteMatch(totokensProvider, 'gemini-3.1-flash-image', { image_size: '2K' }, 'auto');
    assert.equal(gemMatch.matchedProfile.id, 'totokens_gemini');
    assert.equal(gemMatch.configured, true);
    assert.equal(gemMatch.issue, '');

    const gpt1kMatch = TryonForm.resolveTotokensRouteMatch(totokensProvider, 'gpt-image-2', { image_size: '1K' }, 'auto');
    assert.equal(gpt1kMatch.matchedProfile.id, 'totokens_gpt_1k');
    assert.equal(gpt1kMatch.configured, true);

    const gpt2kMissing = TryonForm.resolveTotokensRouteMatch(totokensProvider, 'gpt-image-2', { image_size: '2K' }, 'auto');
    assert.equal(gpt2kMissing.configured, false);
    assert.equal(gpt2kMissing.issue, 'missing');
    assert.equal(gpt2kMissing.matchedProfile.id, 'totokens_gpt_2k4k');

    const explicitMismatch = TryonForm.resolveTotokensRouteMatch(totokensProvider, 'gpt-image-2', { image_size: '4K' }, 'totokens_gpt_1k');
    assert.equal(explicitMismatch.compatible, false);
    assert.equal(explicitMismatch.issue, 'mismatch');
});
