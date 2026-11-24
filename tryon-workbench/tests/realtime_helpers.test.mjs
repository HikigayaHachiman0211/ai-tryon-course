import test from 'node:test';
import assert from 'node:assert/strict';

import {
  FLOATING_SIZE_PRESETS,
  KNOWN_ERROR_CODES,
  PROMPT_PRESETS,
  REACTOR_DEFAULT_MODEL,
  REACTOR_MODELS,
  STAGE_DISPLAY_MODES,
  STAGE_FIT_MODES,
  STAGE_LAYOUTS,
  XMAX_CAMERA_PRESETS,
  XMAX_PRESET_AUTO,
  calculateMaxCents,
  calculateMaxCredits,
  cameraPresetForModel,
  clampFloatingRect,
  computeCenterCropRect,
  computeStageAspectRatio,
  durationCandidates,
  formatRealtimeErrorDetail,
  mapReactorErrorCode,
  mapXmaxErrorCode,
  needsAspectCenterCrop,
  nextFloatingSizePreset,
  normalizeClientStopReason,
  parsePresetDimensions,
  pickBestXmaxPreset,
  presetAspectLabel,
  reactorModelLabelKey,
  resolveProvidersStatus,
  sanitizeRealtimeDetail,
} from '../static/js/realtime-helpers.js';

test('resolveProvidersStatus handles unified /providers and legacy /status payloads', () => {
  const dual = resolveProvidersStatus({
    any_available: true,
    default_provider: 'xmax',
    providers: {
      decart: { available: false, reason: 'disabled' },
      xmax: { available: true, model: 'x2.1', max_seconds: 60 },
      reactor: { available: true, model: 'reactor/xmax-x2-1', max_seconds: 60, credits_per_second: 17, cents_per_minute: 11 },
    },
  });
  assert.deepEqual(dual.availableProviders, ['reactor', 'xmax']);
  assert.equal(dual.defaultProvider, 'xmax');
  assert.equal(dual.xmax.max_seconds, 60);
  assert.equal(dual.reactor.model, 'reactor/xmax-x2-1');

  const legacy = resolveProvidersStatus({
    available: true,
    model: 'lucy-vton-3.6',
    cents_per_second: 2,
  });
  assert.deepEqual(legacy.availableProviders, ['decart']);
  assert.equal(legacy.defaultProvider, 'decart');
  assert.equal(legacy.xmax.available, false);
  assert.equal(legacy.reactor.available, false);
});

test('calculateMaxCents and calculateMaxCredits match conservative billing formulas', () => {
  assert.equal(calculateMaxCents('decart', { cents_per_second: 2 }, 15), 30);
  assert.equal(calculateMaxCents('xmax', { cents_per_minute: 10 }, 30), 5);
  assert.equal(calculateMaxCents('xmax', { cents_per_minute: 10 }, 10), 2);
  assert.equal(calculateMaxCents('reactor', { cents_per_minute: 11 }, 30), 6);
  assert.equal(calculateMaxCents('reactor', { cents_per_minute: 11 }, 10), 2);
  assert.equal(calculateMaxCredits({ credits_per_second: 1 }, 45), 45);
  assert.equal(calculateMaxCredits({ credits_per_second: 17 }, 30, 17), 510);
});

test('durationCandidates and cameraPresetForModel stay within bounds', () => {
  assert.deepEqual(durationCandidates(10, 60), [10, 15, 20, 30, 45, 60]);
  assert.deepEqual(durationCandidates(12, 25), [12, 15, 20, 25]);
  assert.equal(cameraPresetForModel('x2.1', '1920x1080'), '1920x1080');
  assert.equal(cameraPresetForModel('x2.1-flash', '1080x1920'), XMAX_CAMERA_PRESETS['x2.1-flash'][0]);
  assert.ok(PROMPT_PRESETS.xmax.length >= 4);
  assert.ok(PROMPT_PRESETS.reactor.length >= 4);
  assert.equal(REACTOR_DEFAULT_MODEL, 'reactor/xmax-x2-1');
  assert.deepEqual(REACTOR_MODELS, ['reactor/xmax-x2-1', 'xmax/x2']);
  assert.equal(reactorModelLabelKey('reactor/xmax-x2-1'), 'reactorModelX21');
  assert.equal(reactorModelLabelKey('xmax/x2'), 'reactorModelX20');
});

test('mapXmaxErrorCode and mapReactorErrorCode map SDK error categories cleanly', () => {
  assert.equal(mapXmaxErrorCode({ apiCode: 46019, message: 'limit' }), 'insufficient_credits');
  assert.equal(mapXmaxErrorCode({ apiCode: 46032, message: 'too many' }), 'session_limit');
  assert.equal(mapXmaxErrorCode({ code: 'UNSAFE_IMAGE' }), 'unsafe_image');
  assert.equal(mapXmaxErrorCode({ code: 'CAMERA_PERMISSION_DENIED' }), 'camera_denied');
  assert.equal(mapXmaxErrorCode({ code: 'RTC_ERROR' }), 'connection_lost');

  assert.equal(mapReactorErrorCode({ code: 'UNAUTHORIZED' }), 'session_unavailable');
  assert.equal(mapReactorErrorCode({ code: 'RATE_LIMITED' }), 'session_limit');
  assert.equal(mapReactorErrorCode({ code: 'CONFLICT' }), 'connection_lost');
  assert.equal(mapReactorErrorCode({ code: 'NETWORK_ERROR' }), 'connection_lost');
});

test('parsePresetDimensions, presetAspectLabel, and empty resolveProvidersStatus behave cleanly', () => {
  assert.deepEqual(parsePresetDimensions('1080x1920'), { width: 1080, height: 1920 });
  assert.deepEqual(parsePresetDimensions('768x1024'), { width: 768, height: 1024 });
  assert.deepEqual(parsePresetDimensions('invalid'), { width: 1080, height: 1920 });

  assert.equal(presetAspectLabel('1080x1920'), '1080×1920 (9:16)');
  assert.equal(presetAspectLabel('1920x1080'), '1920×1080 (16:9)');
  assert.equal(presetAspectLabel('1152x1536'), '1152×1536 (3:4)');
  assert.equal(presetAspectLabel('1408x1408'), '1408×1408 (1:1)');
  assert.equal(presetAspectLabel(''), '1080×1920 (9:16)');

  const allOff = resolveProvidersStatus({
    any_available: false,
    default_provider: 'xmax',
    providers: {
      decart: { available: false, reason: 'disabled' },
      xmax: { available: false, reason: 'disabled' },
      reactor: { available: false, reason: 'disabled' },
    },
  });
  assert.deepEqual(allOff.availableProviders, []);
  assert.equal(allOff.defaultProvider, 'xmax');
});

test('floating window clamping, size cycling, and stage mode constants work safely', () => {
  assert.deepEqual(STAGE_DISPLAY_MODES, ['inline', 'maximized', 'floating', 'popout']);
  assert.deepEqual(STAGE_LAYOUTS, ['dual', 'remote', 'pip-overlay', 'local']);
  assert.deepEqual(STAGE_FIT_MODES, ['cover', 'contain']);

  assert.equal(nextFloatingSizePreset('sm'), 'md');
  assert.equal(nextFloatingSizePreset('md'), 'lg');
  assert.equal(nextFloatingSizePreset('lg'), 'sm');
  assert.equal(nextFloatingSizePreset('unknown'), 'md');

  const centeredDefault = clampFloatingRect(FLOATING_SIZE_PRESETS.md, { width: 1280, height: 800 }, 12);
  assert.deepEqual(centeredDefault, { left: 748, top: 358, width: 520, height: 430 });

  const clampedOverflow = clampFloatingRect(
    { left: -50, top: 900, width: 900, height: 700 },
    { width: 600, height: 500 },
    12,
  );
  assert.deepEqual(clampedOverflow, { left: 12, top: 12, width: 576, height: 476 });
});

test('error sanitization, diagnostic formatting, and stop reason normalization work safely', () => {
  assert.ok(KNOWN_ERROR_CODES.has('camera_not_readable'));
  assert.ok(KNOWN_ERROR_CODES.has('session_error'));

  assert.equal(mapXmaxErrorCode({ code: 'RTC_ERROR', message: 'Agora operation failed (NOT_READABLE)' }), 'camera_not_readable');
  assert.equal(mapXmaxErrorCode({ name: 'NotReadableError', message: 'Could not start video source' }), 'camera_not_readable');
  assert.equal(mapXmaxErrorCode({ name: 'NotAllowedError', message: 'Permission denied' }), 'camera_denied');
  assert.equal(mapXmaxErrorCode({ code: 'API_ERROR', apiCode: 46018, message: 'expired' }), 'session_unavailable');
  assert.equal(mapXmaxErrorCode({ code: 'API_ERROR', apiCode: 46005, message: '模型类型不存在' }), 'invalid_model');
  assert.equal(mapXmaxErrorCode({ code: 'SESSION_ERROR', message: 'Session does not contain complete RTC join information' }), 'session_error');

  const dirty = 'failed with uk-secret123 tk-temp456 rk-secret789 Bearer abc.def.ghi eyJhbGciOi.eyJzdWIi.sig?token=topsecret ' + 'x'.repeat(250);
  const cleaned = sanitizeRealtimeDetail(dirty);
  assert.equal(cleaned.includes('uk-secret123'), false);
  assert.equal(cleaned.includes('tk-temp456'), false);
  assert.equal(cleaned.includes('rk-secret789'), false);
  assert.equal(cleaned.includes('eyJhbGciOi'), false);
  assert.equal(cleaned.includes('topsecret'), false);
  assert.ok(cleaned.length <= 180);

  const formatted = formatRealtimeErrorDetail({
    code: 'RTC_ERROR',
    apiCode: 500,
    httpStatus: 502,
    message: 'Agora operation failed (NOT_READABLE) for tk-secret',
  }, 'camera');
  assert.equal(formatted, '[camera · RTC_ERROR · api=500 · http=502] Agora operation failed (NOT_READABLE) for [redacted]');

  assert.equal(normalizeClientStopReason('limitReached'), 'limit_reached');
  assert.equal(normalizeClientStopReason('camera_not_readable', 'camera'), 'camera_not_readable');
  assert.equal(normalizeClientStopReason('unknown_error', 'upload'), 'upload_failed');
  assert.ok(/^[a-z0-9_]{1,32}$/.test(normalizeClientStopReason('Weird Error Name!!! ' + 'z'.repeat(50))));
});

test('pickBestXmaxPreset, computeStageAspectRatio, and center-crop helpers choose distortion-free framing', () => {
  assert.equal(XMAX_PRESET_AUTO, 'auto');
  assert.equal(pickBestXmaxPreset('x2.1', { width: 1280, height: 720 }), '1920x1080');
  assert.equal(pickBestXmaxPreset('x2.1', { width: 640, height: 480 }), '1536x1152');
  assert.equal(pickBestXmaxPreset('x2.1', { width: 720, height: 1280 }), '1080x1920');
  assert.equal(pickBestXmaxPreset('x2.1', { width: 1000, height: 1000 }), '1408x1408');
  assert.equal(pickBestXmaxPreset('x2.1-flash', { width: 1280, height: 720 }), '1280x704');
  assert.equal(pickBestXmaxPreset('x2.1', null, { width: 1440, height: 900 }), '1920x1080');
  assert.equal(pickBestXmaxPreset('x2.1', null, { width: 390, height: 844 }), '1080x1920');

  assert.deepEqual(computeStageAspectRatio({ width: 1920, height: 1080 }), { ratio: 1.7778, orientation: 'landscape' });
  assert.deepEqual(computeStageAspectRatio({ width: 1080, height: 1920 }), { ratio: 0.5625, orientation: 'portrait' });
  assert.deepEqual(computeStageAspectRatio({ width: 1408, height: 1408 }), { ratio: 1, orientation: 'square' });
  assert.deepEqual(computeStageAspectRatio({ width: 3000, height: 1000 }), { ratio: 1.7778, orientation: 'landscape' });

  assert.equal(needsAspectCenterCrop({ width: 1280, height: 720 }, { width: 1080, height: 1920 }), true);
  assert.equal(needsAspectCenterCrop({ width: 1280, height: 720 }, { width: 1920, height: 1080 }), false);
  assert.equal(needsAspectCenterCrop(null, { width: 1920, height: 1080 }), false);

  const crop = computeCenterCropRect(1280, 720, 1080, 1920);
  assert.equal(crop.sy, 0);
  assert.ok(crop.sx > 0);
  assert.equal(crop.outWidth % 2, 0);
  assert.equal(crop.outHeight % 2, 0);
  assert.ok(Math.abs((crop.outWidth / crop.outHeight) - (1080 / 1920)) < 0.01);
});
