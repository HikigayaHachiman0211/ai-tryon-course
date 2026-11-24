import {
    DECART_DEFAULT_PROMPT,
    FLOATING_SIZE_PRESETS,
    KNOWN_ERROR_CODES,
    PROMPT_PRESETS,
    REACTOR_DEFAULT_MODEL,
    REACTOR_DEFAULT_PROMPT,
    REACTOR_MODELS,
    XMAX_CAMERA_PRESETS,
    XMAX_DEFAULT_PROMPT,
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
} from './realtime-helpers.js?v=20261124-v8';

let docPipWindow = null;
const $ = id => document.getElementById(`realtime-${id}`)
    || docPipWindow?.document?.getElementById(`realtime-${id}`)
    || null;
const root = '/api/realtime-tryon';
const t = (key, values) => window.WorkbenchI18n.t(`realtime.${key}`, values);
const storageKey = 'tryon-lucy.last-session';
const codeStorageKey = 'tryon-lucy.access-code';
const providerStorageKey = 'tryon-realtime.provider';
const imageTypes = ['image/jpeg', 'image/png', 'image/webp'];
const videoTypes = ['video/mp4', 'video/webm', 'video/quicktime'];
const rtcSupported = window.isSecureContext && typeof RTCPeerConnection === 'function';
const supported = rtcSupported && Boolean(navigator.mediaDevices?.getUserMedia);

let providersState = resolveProvidersStatus({ available: false, reason: 'disabled' });
let activeProvider = 'xmax';
let config = providersState.xmax;
let sdk;
let xmaxSdk;
let reactorSdk;
let model;
let camera;
let pendingCamera;
let run;
let phase = 'loading';
let failure = '';
let failureDetail = '';
let statusParams = {};
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let selected = document.getElementById('ref-cover-img')?.getAttribute('src') || '';
let previewUrl;
let snapshotUrl;
let lastReceipt;
let facingMode = 'user';
let mirrored = true;
let switchingCamera = false;
let xmaxSourceMode = 'camera';
let xmaxSourceFile = null;
let xmaxSourceUrl = '';
let xmaxPresetSelection = XMAX_PRESET_AUTO;
let detectedSourceDims = null;
let liveRemoteDims = null;
let stageDisplayMode = 'inline';
let stageLayout = 'dual';
let stageFit = 'cover';
let stageSwapped = false;
let stageFloatSize = 'md';
let stageFloatRect = null;
let stageDrag = null;

const currentViewport = () => ({
    width: Math.round(window.visualViewport?.width || window.innerWidth || 1280),
    height: Math.round(window.visualViewport?.height || window.innerHeight || 720),
});

function sameDims(a, b) {
    if (!a && !b) return true;
    if (!a || !b) return false;
    return a.width === b.width && a.height === b.height;
}

function setDetectedSourceDims(width, height) {
    const w = Math.round(Number(width));
    const h = Math.round(Number(height));
    if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return;
    const next = { width: w, height: h };
    if (sameDims(detectedSourceDims, next)) return;
    detectedSourceDims = next;
    if (activeProvider === 'xmax') renderXmaxOptions();
    renderStageDisplay();
}

function setLiveRemoteDims(width, height) {
    const w = Math.round(Number(width));
    const h = Math.round(Number(height));
    if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return;
    const next = { width: w, height: h };
    if (sameDims(liveRemoteDims, next)) return;
    liveRemoteDims = next;
    renderStageDisplay();
}

function readStreamTrackDims(streamOrTrack) {
    const track = streamOrTrack?.getVideoTracks ? streamOrTrack.getVideoTracks()[0] : streamOrTrack;
    const settings = track?.getSettings?.();
    const w = Math.round(Number(settings?.width));
    const h = Math.round(Number(settings?.height));
    return Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0 ? { width: w, height: h } : null;
}

async function readImageFileDimensions(file) {
    if (!file) return null;
    const url = URL.createObjectURL(file);
    try {
        const img = new Image();
        img.src = url;
        await img.decode();
        return img.naturalWidth > 0 && img.naturalHeight > 0
            ? { width: img.naturalWidth, height: img.naturalHeight }
            : null;
    } catch {
        return null;
    } finally {
        URL.revokeObjectURL(url);
    }
}

const imageFile = () => $('file').files[0];
const selectedXmaxModel = () => $('xmax-model')?.value || config?.model || 'x2.1';
const selectedXmaxPreset = () => {
    const chosenModel = selectedXmaxModel();
    if (xmaxPresetSelection === XMAX_PRESET_AUTO) {
        return pickBestXmaxPreset(chosenModel, detectedSourceDims, currentViewport());
    }
    return cameraPresetForModel(chosenModel, xmaxPresetSelection);
};
const selectedReactorModel = () => $('reactor-model')?.value || config?.model || REACTOR_DEFAULT_MODEL;
const usingLocalFileSource = () => activeProvider === 'xmax' && xmaxSourceMode !== 'camera';
const currentGarmentSignature = () => {
    const file = imageFile();
    return file ? `file:${file.name}:${file.size}:${file.lastModified}` : `sel:${selected || ''}`;
};
const defaultPromptForProvider = () => (
    config?.default_prompt
    || (activeProvider === 'reactor' ? REACTOR_DEFAULT_PROMPT : activeProvider === 'xmax' ? XMAX_DEFAULT_PROMPT : DECART_DEFAULT_PROMPT)
);
const promptText = () => $('prompt').value.trim() || defaultPromptForProvider();
const seconds = () => $('duration').valueAsNumber;
const usd = cents => new Intl.NumberFormat(window.WorkbenchI18n.locale, {
    style: 'currency', currency: 'USD',
}).format(cents / 100);

async function api(path, body, options = {}) {
    const res = await fetch(root + path, {
        credentials: 'same-origin', cache: 'no-store',
        ...(body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
        ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error?.code || 'request_failed');
    return data;
}

function renderProviderTabs() {
    const tabs = $('provider-tabs');
    if (tabs) {
        tabs.hidden = false;
        const availability = {
            xmax: Boolean(providersState.xmax?.available),
            reactor: Boolean(providersState.reactor?.available),
            decart: Boolean(providersState.decart?.available),
        };
        for (const key of ['xmax', 'reactor', 'decart']) {
            const btn = $(`provider-${key}`);
            if (!btn) continue;
            const isActive = activeProvider === key;
            const isAvailable = availability[key];
            btn.hidden = false;
            btn.classList.toggle('active', isActive);
            btn.classList.toggle('is-unavailable', !isAvailable);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
            btn.disabled = Boolean(run || pendingCamera);
            const stateEl = btn.querySelector('.realtime-provider-state');
            if (stateEl) {
                stateEl.dataset.state = isAvailable ? 'on' : 'off';
                stateEl.textContent = t(isAvailable ? 'providerStateOn' : 'providerStateOff');
            }
        }
    }
    if ($('refresh-status')) {
        $('refresh-status').disabled = Boolean(run || pendingCamera);
    }
}

function renderXmaxOptions() {
    const panel = $('xmax-options');
    if (!panel) return;
    const isXmax = activeProvider === 'xmax' && Boolean(config?.available);
    panel.hidden = !isXmax;
    if (!isXmax) return;

    const select = $('xmax-model');
    if (select) {
        const allowed = Array.isArray(config.allowed_models) && config.allowed_models.length
            ? config.allowed_models
            : (config.environment === 'china' ? ['x2.1', 'x2.1-flash'] : ['x2.1']);
        const prev = select.value;
        select.replaceChildren();
        for (const m of allowed) {
            const opt = document.createElement('option');
            opt.value = m;
            opt.textContent = m === 'x2.1-flash'
                ? t('xmaxModelFlash')
                : t('xmaxModelStandard');
            select.appendChild(opt);
        }
        select.value = allowed.includes(prev) ? prev : (config.model || allowed[0]);
        select.disabled = Boolean(run);
    }

    const presetSelect = $('xmax-preset');
    if (presetSelect) {
        const chosenModel = select ? select.value : selectedXmaxModel();
        const presets = XMAX_CAMERA_PRESETS[chosenModel] || XMAX_CAMERA_PRESETS['x2.1'];
        if (xmaxPresetSelection !== XMAX_PRESET_AUTO && !presets.includes(xmaxPresetSelection)) {
            xmaxPresetSelection = XMAX_PRESET_AUTO;
        }
        const autoMatched = pickBestXmaxPreset(chosenModel, detectedSourceDims, currentViewport());
        presetSelect.replaceChildren();
        const autoOpt = document.createElement('option');
        autoOpt.value = XMAX_PRESET_AUTO;
        autoOpt.textContent = t('xmaxPresetAuto', { preset: presetAspectLabel(autoMatched) });
        presetSelect.appendChild(autoOpt);
        for (const p of presets) {
            const opt = document.createElement('option');
            opt.value = p;
            opt.textContent = presetAspectLabel(p);
            presetSelect.appendChild(opt);
        }
        presetSelect.value = xmaxPresetSelection;
        presetSelect.disabled = Boolean(run);
    }

    const sourceSelect = $('xmax-source');
    if (sourceSelect) {
        sourceSelect.value = xmaxSourceMode;
        sourceSelect.disabled = Boolean(run || pendingCamera);
    }

    const sourceUpload = $('xmax-source-upload');
    if (sourceUpload) {
        const isFileSource = xmaxSourceMode !== 'camera';
        sourceUpload.hidden = !isFileSource;
        if (isFileSource) {
            if ($('xmax-source-file')) {
                $('xmax-source-file').accept = xmaxSourceMode === 'video'
                    ? 'video/mp4,video/webm,video/quicktime'
                    : 'image/jpeg,image/png,image/webp';
                $('xmax-source-file').disabled = Boolean(run);
            }
            if ($('xmax-source-btn')) $('xmax-source-btn').disabled = Boolean(run);
            if ($('xmax-source-btn-text')) {
                $('xmax-source-btn-text').textContent = t(xmaxSourceMode === 'video' ? 'xmaxPickVideo' : 'xmaxPickImage');
            }
            if ($('xmax-source-name')) {
                $('xmax-source-name').textContent = xmaxSourceFile ? xmaxSourceFile.name : t('xmaxSourceMissing');
            }
        }
    }

    if ($('face-restoration')) {
        if ($('face-restoration').dataset.userChanged !== '1') {
            $('face-restoration').checked = config.face_restoration !== false;
        }
        $('face-restoration').disabled = !config?.available;
    }

    if ($('xmax-adaptive')) {
        $('xmax-adaptive').disabled = Boolean(run);
    }
}

function renderReactorOptions() {
    const panel = $('reactor-options');
    if (!panel) return;
    const isReactor = activeProvider === 'reactor' && Boolean(config?.available);
    panel.hidden = !isReactor;
    if (!isReactor) return;

    const select = $('reactor-model');
    if (select) {
        const allowed = Array.isArray(config.allowed_models) && config.allowed_models.length
            ? config.allowed_models
            : REACTOR_MODELS;
        const prev = select.value;
        select.replaceChildren();
        for (const m of allowed) {
            const opt = document.createElement('option');
            opt.value = m;
            opt.textContent = t(reactorModelLabelKey(m));
            select.appendChild(opt);
        }
        const preferredDefault = config.model && allowed.includes(config.model) ? config.model : allowed[0];
        select.value = allowed.includes(prev) ? prev : preferredDefault;
        select.disabled = Boolean(run);
    }
}

function renderQuotaBar() {
    const bar = $('quota-bar');
    if (!bar) return;
    const quota = config?.quota;
    if (!config?.available || !quota) {
        bar.hidden = true;
        return;
    }
    bar.hidden = false;
    bar.replaceChildren();

    const visitorPill = document.createElement('span');
    visitorPill.className = 'realtime-quota-pill';
    visitorPill.dataset.tone = quota.visitor_remaining_cents >= quota.min_session_cents ? 'ok' : 'warn';
    visitorPill.textContent = t('quotaVisitor', {
        remaining: usd(quota.visitor_remaining_cents),
        limit: usd(quota.visitor_daily_cents),
    });

    const siteEnough = quota.site_daily_remaining_cents >= quota.min_session_cents
        && quota.site_monthly_remaining_cents >= quota.min_session_cents;
    const sitePill = document.createElement('span');
    sitePill.className = 'realtime-quota-pill';
    sitePill.dataset.tone = siteEnough ? 'ok' : 'warn';
    sitePill.textContent = siteEnough
        ? t('quotaSiteOk', {
            daily: usd(quota.site_daily_remaining_cents),
            monthly: usd(quota.site_monthly_remaining_cents),
        })
        : t('quotaSiteLow');

    const slotPill = document.createElement('span');
    slotPill.className = 'realtime-quota-pill';
    slotPill.dataset.tone = quota.active_sessions < quota.max_active ? 'ok' : 'warn';
    slotPill.textContent = t('quotaSlots', {
        active: quota.active_sessions,
        max: quota.max_active,
    });

    bar.append(visitorPill, sitePill, slotPill);
}

function renderDurationChips() {
    const container = $('duration-chips');
    if (!container || !config?.available) return;
    const candidates = durationCandidates(config.min_seconds || 10, config.max_seconds || 20);
    const current = seconds();
    container.replaceChildren();
    for (const sec of candidates) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `video-preset${current === sec ? ' active' : ''}`;
        btn.disabled = Boolean(run);
        const estCents = calculateMaxCents(activeProvider, config, sec);
        btn.textContent = (activeProvider === 'xmax' || activeProvider === 'reactor')
            ? `${sec}s · ${calculateMaxCredits(config, sec, activeProvider === 'reactor' ? 17 : 1)}${t('creditsShort')} (${usd(estCents)})`
            : `${sec}s · ${usd(estCents)}`;
        btn.addEventListener('click', () => {
            $('duration').value = String(sec);
            $('duration').dataset.userChanged = '1';
            render();
        });
        container.appendChild(btn);
    }
}

function renderPresets() {
    const container = $('presets');
    if (!container) return;
    const list = PROMPT_PRESETS[activeProvider] || PROMPT_PRESETS.decart;
    const currentVal = $('prompt').value.trim();
    container.replaceChildren();
    for (const item of list) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `video-preset${currentVal === item.prompt ? ' active' : ''}`;
        btn.textContent = t(`presets.${item.key}`);
        btn.addEventListener('click', () => {
            $('prompt').value = item.prompt;
            renderPresets();
        });
        container.appendChild(btn);
    }
}

function renderStreamsUi() {
    const hasXmaxLocalHost = Boolean(run?.provider === 'xmax' && run.xmaxLocalReady);
    const hasXmaxRemoteHost = Boolean(run?.provider === 'xmax' && run.xmaxRemoteReady);
    const fileSource = usingLocalFileSource();
    const hasLocalImagePreview = Boolean(!hasXmaxLocalHost && fileSource && xmaxSourceMode === 'image' && xmaxSourceUrl);
    const hasLocalVideoPreview = Boolean(!hasXmaxLocalHost && fileSource && xmaxSourceMode === 'video' && xmaxSourceUrl);

    if ($('local-image')) {
        if (hasLocalImagePreview) {
            if ($('local-image').getAttribute('src') !== xmaxSourceUrl) {
                $('local-image').src = xmaxSourceUrl;
            }
            $('local-image').hidden = false;
        } else {
            $('local-image').hidden = true;
            $('local-image').removeAttribute('src');
        }
    }

    if ($('local')) {
        const showVideoEl = !hasXmaxLocalHost && !hasLocalImagePreview;
        $('local').hidden = !showVideoEl;
        if (hasLocalVideoPreview) {
            $('local').srcObject = null;
            if ($('local').dataset.sourceUrl !== xmaxSourceUrl) {
                $('local').src = xmaxSourceUrl;
                $('local').loop = true;
                $('local').muted = true;
                $('local').dataset.sourceUrl = xmaxSourceUrl;
                void $('local').play?.().catch(() => {});
            }
        } else if ($('local').dataset.sourceUrl) {
            $('local').pause?.();
            $('local').removeAttribute('src');
            delete $('local').dataset.sourceUrl;
            $('local').load?.();
        }
        $('local').classList.toggle('is-mirrored', mirrored && !hasLocalVideoPreview);
    }

    if ($('remote')) $('remote').hidden = hasXmaxRemoteHost;
    if ($('xmax-local')) $('xmax-local').hidden = !hasXmaxLocalHost;
    if ($('xmax-remote')) $('xmax-remote').hidden = !hasXmaxRemoteHost;

    const hasLocal = Boolean($('local')?.srcObject || hasXmaxLocalHost || hasLocalImagePreview || hasLocalVideoPreview);
    const hasRemote = Boolean($('remote')?.srcObject || hasXmaxRemoteHost);

    if ($('local-empty')) $('local-empty').hidden = hasLocal;
    if ($('local-empty-text')) {
        $('local-empty-text').textContent = t(fileSource ? 'xmaxSourceMissing' : 'localEmpty');
    }
    if ($('remote-empty')) $('remote-empty').hidden = hasRemote;
    if ($('local-badge')) {
        $('local-badge').hidden = !hasLocal;
        $('local-badge').textContent = t('previewBadge');
    }
    if ($('remote-badge')) {
        $('remote-badge').hidden = !hasRemote;
        $('remote-badge').textContent = t('liveBadge');
    }
    if (run?.xmaxLocalView) {
        run.xmaxLocalView.isMirrored = run.sourceMode === 'camera' ? mirrored : false;
    }
    if ($('mirror-toggle')) {
        $('mirror-toggle').hidden = fileSource;
        $('mirror-toggle').setAttribute('aria-pressed', mirrored ? 'true' : 'false');
        $('mirror-toggle').classList.toggle('active', mirrored);
    }
    if ($('flip-camera')) {
        const canFlip = Boolean(!fileSource && !run?.xmaxUsingExternalCamera && (camera || run?.xmaxRealtime || run?.reactorClient) && !switchingCamera);
        $('flip-camera').hidden = !canFlip;
    }
    if ($('snapshot')) {
        const hasVideoEl = Boolean(
            ($('remote')?.srcObject && $('remote').videoWidth)
            || (hasXmaxRemoteHost && run?.xmaxRemoteView?.videoElement?.videoWidth)
            || hasRemote,
        );
        $('snapshot').hidden = !hasVideoEl;
    }
    renderStageDisplay();
}

const hasActivePipWindow = () => Boolean((docPipWindow && !docPipWindow.closed) || document.pictureInPictureElement);

function activeVideoElementForPane(pane) {
    const video = pane === 'remote'
        ? (run?.provider === 'xmax' ? run.xmaxRemoteView?.videoElement : $('remote'))
        : (run?.provider === 'xmax' ? run.xmaxLocalView?.videoElement : $('local'));
    if (!video) return null;
    const hasSrc = Boolean(video.srcObject || video.currentSrc || video.getAttribute('src'));
    return hasSrc ? video : null;
}

function resumeStageVideos() {
    for (const video of [$('local'), $('remote'), run?.xmaxLocalView?.videoElement, run?.xmaxRemoteView?.videoElement]) {
        if (video && (video.srcObject || video.currentSrc || video.getAttribute('src'))) {
            void video.play?.().catch(() => {});
        }
    }
}

function syncXmaxContentMode() {
    if (!xmaxSdk || run?.provider !== 'xmax') return;
    const mode = stageFit === 'contain' ? xmaxSdk.VideoContentMode.fit : xmaxSdk.VideoContentMode.fill;
    if (run.xmaxLocalView) run.xmaxLocalView.videoContentMode = mode;
    if (run.xmaxRemoteView) run.xmaxRemoteView.videoContentMode = mode;
}

function applyFloatingGeometry() {
    const stage = $('stage');
    if (!stage) return;
    if (stageDisplayMode !== 'floating') {
        stage.style.left = '';
        stage.style.top = '';
        stage.style.width = '';
        stage.style.height = '';
        return;
    }
    const preset = FLOATING_SIZE_PRESETS[stageFloatSize] || FLOATING_SIZE_PRESETS.md;
    const rect = clampFloatingRect(
        stageFloatRect || preset,
        currentViewport(),
        12,
    );
    stageFloatRect = rect;
    stage.style.left = `${rect.left}px`;
    stage.style.top = `${rect.top}px`;
    stage.style.width = `${rect.width}px`;
    stage.style.height = `${rect.height}px`;
}

function restoreStageFromDocPip({ resetMode = true } = {}) {
    const stage = $('stage');
    const home = document.getElementById('realtime-stage-home');
    if (stage && home && stage.parentNode !== home) {
        home.appendChild(stage);
    }
    const win = docPipWindow;
    docPipWindow = null;
    if (win && !win.closed) {
        try { win.close(); } catch { /* ignore */ }
    }
    if (resetMode && stageDisplayMode === 'popout') {
        stageDisplayMode = 'inline';
    }
    resumeStageVideos();
}

function setStageDisplayMode(nextMode) {
    const activeFs = document.fullscreenElement || docPipWindow?.document?.fullscreenElement;
    if (activeFs && activeFs.ownerDocument?.exitFullscreen) {
        void activeFs.ownerDocument.exitFullscreen().catch(() => {});
    }
    if (stageDisplayMode === 'popout' && nextMode !== 'popout') {
        restoreStageFromDocPip({ resetMode: false });
    }
    stageDisplayMode = nextMode;
    document.body.classList.toggle('realtime-stage-locked', nextMode === 'maximized');
    document.getElementById('section-realtime')?.classList.toggle(
        'has-stage-overlay',
        nextMode === 'maximized' || nextMode === 'floating',
    );
    applyFloatingGeometry();
    renderStageDisplay();
}

function stageTargetDims() {
    if (liveRemoteDims) return liveRemoteDims;
    if (activeProvider === 'xmax' && xmaxPresetSelection !== XMAX_PRESET_AUTO) {
        return parsePresetDimensions(selectedXmaxPreset());
    }
    if (detectedSourceDims) return detectedSourceDims;
    if (activeProvider === 'xmax') {
        return parsePresetDimensions(selectedXmaxPreset());
    }
    return null;
}

async function openDocPip() {
    const stage = $('stage');
    if (!stage) return;
    if (stageDisplayMode === 'popout' && docPipWindow && !docPipWindow.closed) {
        setStageDisplayMode('inline');
        return;
    }
    if (document.fullscreenElement) {
        await document.exitFullscreen().catch(() => {});
    }
    if (window.documentPictureInPicture?.requestWindow) {
        try {
            const { orientation } = computeStageAspectRatio(stageTargetDims(), 4 / 5);
            const pipBounds = orientation === 'landscape'
                ? (stageLayout === 'dual' ? { width: 920, height: 420 } : { width: 640, height: 420 })
                : (stageLayout === 'dual' ? { width: 820, height: 600 } : { width: 480, height: 600 });
            const pipWin = await window.documentPictureInPicture.requestWindow(pipBounds);
            for (const link of document.querySelectorAll('link[rel="stylesheet"]')) {
                const clone = pipWin.document.createElement('link');
                clone.rel = 'stylesheet';
                clone.href = link.href;
                pipWin.document.head.appendChild(clone);
            }
            pipWin.document.documentElement.lang = document.documentElement.lang;
            pipWin.document.title = t('stagePopoutTitle');
            pipWin.document.body.className = 'realtime-pip-body';
            pipWin.document.body.appendChild(stage);
            docPipWindow = pipWin;
            stageDisplayMode = 'popout';
            document.body.classList.remove('realtime-stage-locked');
            document.getElementById('section-realtime')?.classList.remove('has-stage-overlay');
            applyFloatingGeometry();
            resumeStageVideos();
            renderStageDisplay();
            pipWin.document.addEventListener('fullscreenchange', renderStageDisplay);
            pipWin.addEventListener('pagehide', () => {
                if (docPipWindow !== pipWin) return;
                restoreStageFromDocPip({ resetMode: true });
                renderStageDisplay();
                if (document.hidden && (run || camera || pendingCamera)) {
                    finish('hiddenStop');
                }
            }, { once: true });
            return;
        } catch {
            /* fall back to Video PiP or in-page floating window */
        }
    }
    const targetVideo = activeVideoElementForPane('remote') || activeVideoElementForPane('local');
    if (document.pictureInPictureEnabled && targetVideo?.requestPictureInPicture) {
        try {
            if (document.pictureInPictureElement === targetVideo) {
                await document.exitPictureInPicture();
            } else {
                await targetVideo.requestPictureInPicture();
                targetVideo.addEventListener('leavepictureinpicture', () => {
                    renderStageDisplay();
                    if (document.hidden && (run || camera || pendingCamera)) {
                        finish('hiddenStop');
                    }
                }, { once: true });
            }
            renderStageDisplay();
            return;
        } catch {
            /* fall back to in-page floating window */
        }
    }
    setStageDisplayMode('floating');
}

async function togglePaneVideoPip(pane) {
    const video = activeVideoElementForPane(pane);
    if (!video || !document.pictureInPictureEnabled || !video.requestPictureInPicture) return;
    try {
        if (document.pictureInPictureElement === video) {
            await document.exitPictureInPicture();
        } else {
            await video.requestPictureInPicture();
            video.addEventListener('leavepictureinpicture', () => {
                renderStageDisplay();
                if (document.hidden && (run || camera || pendingCamera)) {
                    finish('hiddenStop');
                }
            }, { once: true });
        }
    } catch {
        /* ignore denied or unsupported PiP */
    }
    renderStageDisplay();
}

async function toggleStageFullscreen() {
    const stage = $('stage');
    if (!stage) return;
    const ownerDoc = stage.ownerDocument || document;
    if (ownerDoc.fullscreenElement) {
        await ownerDoc.exitFullscreen().catch(() => {});
        renderStageDisplay();
        return;
    }
    if (stageDisplayMode === 'popout') {
        restoreStageFromDocPip({ resetMode: true });
    } else if (stageDisplayMode === 'floating') {
        setStageDisplayMode('inline');
    }
    try {
        await stage.requestFullscreen();
    } catch {
        setStageDisplayMode('maximized');
    }
    renderStageDisplay();
}

function focusPane(pane) {
    stageLayout = stageLayout === pane ? 'dual' : pane;
    renderStageDisplay();
}

function renderStageDisplay() {
    const stage = $('stage');
    if (!stage) return;
    if (!config?.available && !run && !camera && stageDisplayMode !== 'inline') {
        if (stageDisplayMode === 'popout') restoreStageFromDocPip({ resetMode: false });
        stageDisplayMode = 'inline';
        document.body.classList.remove('realtime-stage-locked');
        document.getElementById('section-realtime')?.classList.remove('has-stage-overlay');
        applyFloatingGeometry();
    }
    const isPipOpen = stageDisplayMode === 'popout' && Boolean(docPipWindow && !docPipWindow.closed);
    if (stageDisplayMode === 'popout' && !isPipOpen) {
        restoreStageFromDocPip({ resetMode: true });
    }
    const effectiveMode = stageDisplayMode === 'popout' && !docPipWindow ? 'inline' : stageDisplayMode;
    const { ratio, orientation } = computeStageAspectRatio(stageTargetDims(), 4 / 5);
    stage.style.setProperty('--realtime-aspect-ratio', String(ratio));
    stage.dataset.orientation = orientation;
    stage.dataset.displayMode = effectiveMode;
    stage.dataset.layout = stageLayout;
    stage.dataset.fit = stageFit;
    stage.dataset.swapped = stageSwapped ? 'true' : 'false';
    stage.dataset.floatSize = stageFloatSize;

    const backdrop = document.getElementById('realtime-stage-backdrop');
    if (backdrop) backdrop.hidden = effectiveMode !== 'maximized';

    const placeholder = document.getElementById('realtime-stage-placeholder');
    if (placeholder) {
        const detached = effectiveMode === 'floating' || effectiveMode === 'popout';
        placeholder.hidden = !detached;
        const placeholderText = document.getElementById('realtime-stage-placeholder-text');
        if (placeholderText) {
            placeholderText.textContent = t(effectiveMode === 'popout' ? 'stagePlaceholderPopout' : 'stagePlaceholderFloating');
        }
    }

    for (const [id, layoutKey] of [
        ['layout-dual', 'dual'],
        ['layout-remote', 'remote'],
        ['layout-pip', 'pip-overlay'],
        ['layout-local', 'local'],
    ]) {
        const btn = $(id);
        if (!btn) continue;
        const active = stageLayout === layoutKey;
        btn.classList.toggle('active', active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    }

    const swapBtn = $('swap-panes');
    if (swapBtn) {
        swapBtn.hidden = stageLayout !== 'dual' && stageLayout !== 'pip-overlay';
        swapBtn.classList.toggle('active', stageSwapped);
        swapBtn.title = t('swapPanes');
        swapBtn.setAttribute('aria-label', t('swapPanes'));
    }

    const fitBtn = $('fit-toggle');
    if (fitBtn) {
        const isContain = stageFit === 'contain';
        fitBtn.classList.toggle('active', isContain);
        if ($('fit-label')) $('fit-label').textContent = t(isContain ? 'fitContain' : 'fitCover');
        const fitIcon = fitBtn.querySelector('i');
        if (fitIcon) {
            fitIcon.className = isContain
                ? 'fas fa-down-left-and-up-right-to-center'
                : 'fas fa-up-right-and-down-left-from-center';
        }
    }

    const isFloat = effectiveMode === 'floating';
    if ($('float-size')) {
        $('float-size').hidden = !isFloat;
        $('float-size').title = t('floatSizeTooltip');
        if ($('float-size-label')) $('float-size-label').textContent = stageFloatSize.toUpperCase();
    }
    if ($('float-toggle')) {
        $('float-toggle').classList.toggle('active', isFloat);
        if ($('float-label')) $('float-label').textContent = t(isFloat ? 'dockStage' : 'floatStage');
    }

    const isMax = effectiveMode === 'maximized';
    if ($('maximize-toggle')) {
        $('maximize-toggle').classList.toggle('active', isMax);
        if ($('maximize-label')) $('maximize-label').textContent = t(isMax ? 'exitMaximizeStage' : 'maximizeStage');
        const maxIcon = $('maximize-toggle').querySelector('i');
        if (maxIcon) maxIcon.className = isMax ? 'fas fa-minimize' : 'fas fa-maximize';
    }

    const isPopout = effectiveMode === 'popout';
    if ($('popout-toggle')) {
        $('popout-toggle').classList.toggle('active', isPopout);
        if ($('popout-label')) $('popout-label').textContent = t(isPopout ? 'closePopoutStage' : 'popoutStage');
    }

    const activeFs = Boolean(document.fullscreenElement || docPipWindow?.document?.fullscreenElement);
    if ($('fullscreen-toggle')) {
        $('fullscreen-toggle').classList.toggle('active', activeFs);
        $('fullscreen-toggle').title = t(activeFs ? 'exitFullscreenStage' : 'fullscreenStage');
        $('fullscreen-toggle').setAttribute('aria-label', t(activeFs ? 'exitFullscreenStage' : 'fullscreenStage'));
        const fsIcon = $('fullscreen-toggle').querySelector('i');
        if (fsIcon) fsIcon.className = activeFs ? 'fas fa-compress' : 'fas fa-expand';
    }

    for (const pane of ['local', 'remote']) {
        const focusBtn = $(`focus-${pane}`);
        if (focusBtn) {
            const focused = stageLayout === pane;
            focusBtn.classList.toggle('active', focused);
            focusBtn.title = t(focused ? 'restoreDual' : 'focusPane');
            const fIcon = focusBtn.querySelector('i');
            if (fIcon) {
                fIcon.className = focused
                    ? 'fas fa-down-left-and-up-right-to-center'
                    : 'fas fa-up-right-and-down-left-from-center';
            }
        }
        const pipBtn = $(`pip-${pane}`);
        if (pipBtn) {
            const videoEl = activeVideoElementForPane(pane);
            pipBtn.hidden = !(document.pictureInPictureEnabled && videoEl);
            pipBtn.classList.toggle('active', Boolean(videoEl && document.pictureInPictureElement === videoEl));
            pipBtn.title = t('videoPip');
        }
    }

    const isExpanded = effectiveMode !== 'inline' || activeFs;
    const canApply = Boolean(run?.client || run?.xmaxRealtime || run?.reactorClient);
    const canStop = Boolean(camera || pendingCamera || run);
    if ($('stage-apply')) {
        $('stage-apply').hidden = !(isExpanded && canApply);
        $('stage-apply').textContent = t(activeProvider === 'xmax' ? 'xmaxApplyContext' : 'apply');
        $('stage-apply').disabled = $('apply') ? $('apply').disabled : true;
    }
    if ($('stage-stop')) {
        $('stage-stop').hidden = !(isExpanded && canStop);
        $('stage-stop').textContent = t('stop');
    }

    syncXmaxContentMode();
    if (isPipOpen) {
        try { window.WorkbenchI18n?.apply?.(stage); } catch { /* ignore */ }
    }
}

function renderUsage() {
    const activeMeter = Boolean(run?.hardDeadline);
    if ($('meter')) $('meter').hidden = !activeMeter;
    if ($('progress')) $('progress').hidden = !run?.deadline;
    if (!activeMeter) return;

    const now = performance.now();
    if (run.deadline) {
        const left = Math.max(0, Math.ceil((run.deadline - now) / 1000));
        const sinceStart = run.generatedAt ? (now - run.generatedAt) / 1000 : 0;
        const usedSec = Math.min(run.limit, Math.ceil(Math.max(run.tick || 0, sinceStart)));
        const isSubcent = run.provider === 'xmax' || run.provider === 'reactor';
        const estCents = isSubcent
            ? calculateMaxCents(run.provider, run.cfgSnapshot, usedSec)
            : usedSec * run.rate;
        const pct = Math.max(
            0,
            Math.min(100, ((run.limit * 1000 - Math.max(0, run.deadline - now)) / (run.limit * 1000)) * 100),
        );
        if ($('progress-fill')) $('progress-fill').style.width = `${pct.toFixed(1)}%`;
        $('meter').textContent = isSubcent
            ? t('xmaxMeter', {
                left,
                credits: calculateMaxCredits(run.cfgSnapshot, usedSec, run.provider === 'reactor' ? 17 : 1),
                cost: usd(estCents),
            })
            : t('meter', { left, cost: usd(estCents) });
    } else {
        $('meter').textContent = t(phase, statusParams);
    }
}

function renderTelemetry() {
    const el = $('telemetry');
    if (!el) return;
    if (!run || (run.provider !== 'xmax' && run.provider !== 'reactor') || (!run.statsText && !run.netText)) {
        el.hidden = true;
        return;
    }
    el.hidden = false;
    el.textContent = [run.statsText, run.netText].filter(Boolean).join(' · ');
}

function unavailableStatusKey() {
    if (!config) return 'unavailable';
    if (config.reason === 'disabled') {
        if (activeProvider === 'xmax') return 'unavailableXmaxDisabled';
        if (activeProvider === 'reactor') return 'unavailableReactorDisabled';
        return 'unavailableDisabled';
    }
    if (config.reason === 'missing_api_key') {
        if (activeProvider === 'reactor') return 'unavailableMissingReactorKey';
        return activeProvider === 'xmax' ? 'unavailableMissingXmaxKey' : 'unavailableMissingKey';
    }
    if (config.reason === 'missing_access_code') return 'unavailableMissingCode';
    return 'unavailable';
}

function syncDynamicHeaderTexts() {
    const isXmax = activeProvider === 'xmax';
    const isReactor = activeProvider === 'reactor';
    if ($('eyebrow')) $('eyebrow').textContent = t(isReactor ? 'reactorEyebrow' : isXmax ? 'xmaxEyebrow' : 'eyebrow');
    if ($('subtitle')) $('subtitle').textContent = t(isReactor ? 'reactorSubtitle' : isXmax ? 'xmaxSubtitle' : 'subtitle');
    if ($('consent-text')) $('consent-text').textContent = t(isReactor ? 'reactorConsent' : isXmax ? 'xmaxConsent' : 'consent');
    if ($('prompt')) {
        $('prompt').placeholder = config?.default_prompt
            || t(isReactor ? 'reactorPromptPlaceholder' : isXmax ? 'xmaxPromptPlaceholder' : 'promptPlaceholder');
    }
}

function renderNoticeMessage(el, mainText, detailText = '') {
    if (!el) return;
    if (!detailText) {
        el.textContent = mainText;
        return;
    }
    el.replaceChildren();
    const msgSpan = document.createElement('span');
    msgSpan.textContent = mainText;
    const detailDiv = document.createElement('div');
    detailDiv.className = 'realtime-error-detail';
    detailDiv.textContent = `${t('diagnosticPrefix')}: ${detailText}`;
    el.append(msgSpan, detailDiv);
}

function render() {
    syncDynamicHeaderTexts();
    renderProviderTabs();
    renderXmaxOptions();
    renderReactorOptions();

    const errorKey = `errors.${failure}`;
    const errorText = t(errorKey);
    const activePhaseKey = phase === 'unavailable' ? unavailableStatusKey() : phase;
    const statusMain = failure
        ? (errorText === `realtime.${errorKey}` ? t('errors.request_failed') : errorText)
        : t(activePhaseKey, statusParams);
    renderNoticeMessage($('status'), statusMain, failure ? failureDetail : '');
    $('status').dataset.tone = failure ? 'error' : (phase === 'live' ? 'success' : 'info');
    if ($('inline-error')) {
        $('inline-error').hidden = !failure;
        if (failure) {
            renderNoticeMessage($('inline-error'), statusMain, failureDetail);
        } else {
            $('inline-error').replaceChildren();
        }
    }
    $('controls').hidden = !config?.available;

    const needCode = config?.require_access_code !== false;
    if ($('code-field')) $('code-field').hidden = !needCode;
    if ($('rate-tag')) {
        $('rate-tag').hidden = !config?.available;
        if (config?.available) {
            if (activeProvider === 'reactor') {
                const chosen = selectedReactorModel();
                $('rate-tag').textContent = t('reactorRateTag', {
                    model: chosen === 'xmax/x2' ? 'X2.0' : 'X2.1',
                    rate: usd(config.cents_per_minute || 11),
                });
            } else if (activeProvider === 'xmax') {
                const resTag = selectedXmaxModel() === 'x2.1-flash' ? '720p' : '1080p';
                $('rate-tag').textContent = t('xmaxRateTag', {
                    res: resTag,
                    credits: config.credits_per_second || 1,
                    rate: usd(config.cents_per_minute || 10),
                });
            } else {
                $('rate-tag').textContent = t('rateTag', { rate: usd(config.cents_per_second) });
            }
        }
    }

    const garment = Boolean(imageFile() || selected);
    const validDuration = $('duration').validity.valid && Number.isInteger(seconds());
    const hasCode = !needCode || Boolean($('code').value.trim());
    const fileSource = usingLocalFileSource();
    const sourceReady = fileSource ? Boolean(xmaxSourceFile) : Boolean(camera);
    const supportedForCurrent = fileSource ? rtcSupported : supported;

    $('preview').hidden = fileSource;
    $('preview').disabled = fileSource || !config?.available || !supported || Boolean(camera || pendingCamera || run);
    $('start').disabled = !config?.available || !supportedForCurrent || !sourceReady || Boolean(run) || !$('consent').checked || !hasCode || !garment || !validDuration;
    $('stop').hidden = !(camera || pendingCamera || run);
    $('apply').hidden = !(run?.client || run?.xmaxRealtime || run?.reactorClient);
    $('apply').textContent = t(activeProvider === 'xmax' ? 'xmaxApplyContext' : 'apply');
    $('apply').disabled = !garment || Boolean(run?.applying);
    $('code').disabled = $('duration').disabled = Boolean(run);

    if (config?.available && validDuration) {
        const estCents = calculateMaxCents(activeProvider, config, seconds());
        $('quote').textContent = (activeProvider === 'xmax' || activeProvider === 'reactor')
            ? t('xmaxQuote', {
                credits: calculateMaxCredits(config, seconds(), activeProvider === 'reactor' ? 17 : 1),
                rate: usd(config.cents_per_minute || (activeProvider === 'reactor' ? 11 : 10)),
                cost: usd(estCents),
            })
            : t('quote', { rate: usd(config.cents_per_second), cost: usd(estCents) });
    } else {
        $('quote').textContent = t('quoteDuration');
    }

    $('source').textContent = t(imageFile() ? 'fileSelected' : selected ? 'selected' : 'noGarment');
    $('use-selected').hidden = !imageFile();

    renderQuotaBar();
    renderDurationChips();
    renderPresets();
    renderStreamsUi();
    renderUsage();
    renderTelemetry();

    $('receipt').hidden = !lastReceipt;
    if (!lastReceipt) return;
    const rcpt = lastReceipt;
    const isXmaxReceipt = rcpt.provider_key === 'xmax';
    const isReactorReceipt = rcpt.provider_key === 'reactor';
    $('receipt').textContent = rcpt.state !== 'ended'
        ? t(rcpt.state === 'unknown' ? 'receiptUnknown' : 'receiptPending')
        : rcpt.provider_seconds != null
            ? (
                isReactorReceipt
                    ? t('reactorReceiptConfirmed', {
                        credits: rcpt.provider_credits ?? calculateMaxCredits(rcpt, Math.ceil(rcpt.provider_seconds), 17),
                        seconds: Number(rcpt.provider_seconds).toFixed(1),
                        cost: usd(rcpt.accounted_cents),
                    })
                    : isXmaxReceipt && rcpt.provider_credits != null
                        ? t('xmaxReceiptConfirmed', {
                            credits: rcpt.provider_credits,
                            seconds: rcpt.provider_seconds,
                            cost: usd(rcpt.accounted_cents),
                        })
                        : t('receiptConfirmed', { seconds: rcpt.provider_seconds, cost: usd(rcpt.accounted_cents) })
            )
            : rcpt.accounted_cents > 0
                ? t('receiptHeld', { cost: usd(rcpt.accounted_cents) })
                : t('receiptReleased');
}

function status(next, code = '', params = {}, detail = '') {
    phase = next;
    failure = code;
    statusParams = params;
    failureDetail = code ? sanitizeRealtimeDetail(detail) : '';
    render();
}

function refreshGarment() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = imageFile() ? URL.createObjectURL(imageFile()) : '';
    const url = previewUrl || selected;
    if (url) $('garment').src = url;
    else $('garment').removeAttribute('src');
    $('garment').hidden = !url;
    if ($('garment-icon')) $('garment-icon').hidden = Boolean(url);
    render();
}

async function garmentImage({ maxSide = 720, maxBytes = 256 * 1024 } = {}) {
    let blob = imageFile();
    if (!blob) {
        if (!selected) throw new Error('invalid_image');
        const source = new URL(selected, location.href);
        const validUploadPath = source.pathname.startsWith('/uploads/') || source.pathname.startsWith('/mp-tryon/uploads/');
        if (source.origin !== location.origin || !validUploadPath) throw new Error('invalid_image');
        const res = await fetch(source, { credentials: 'same-origin' });
        if (!res.ok) throw new Error('invalid_image');
        blob = await res.blob();
    }
    if (!imageTypes.includes(blob.type) || !blob.size || blob.size > 12 * 1024 * 1024) throw new Error('invalid_image');
    const url = URL.createObjectURL(blob);
    try {
        const img = new Image();
        img.src = url;
        await img.decode();
        const canvas = document.createElement('canvas');
        const scale = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight));
        canvas.width = Math.max(1, Math.round(img.naturalWidth * scale));
        canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        const jpeg = quality => new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', quality));
        let result = await jpeg(0.88);
        if (result?.size > maxBytes) result = await jpeg(0.68);
        if (result?.size > maxBytes) result = await jpeg(0.5);
        if (!result?.size || result.size > maxBytes) throw new Error('invalid_image');
        return result;
    } catch {
        throw new Error('invalid_image');
    } finally {
        URL.revokeObjectURL(url);
    }
}

async function requestCameraStream() {
    const vp = currentViewport();
    const isLandscapeViewport = vp.width >= vp.height;
    if (activeProvider === 'xmax') {
        const dims = xmaxPresetSelection === XMAX_PRESET_AUTO
            ? (isLandscapeViewport ? { width: 1920, height: 1080 } : { width: 1080, height: 1920 })
            : parsePresetDimensions(selectedXmaxPreset());
        return navigator.mediaDevices.getUserMedia({
            audio: false,
            video: {
                facingMode: { ideal: facingMode },
                width: { ideal: dims.width },
                height: { ideal: dims.height },
                frameRate: { ideal: 30 },
            },
        });
    }
    const constraints = model
        ? {
            facingMode: { ideal: facingMode },
            width: { ideal: model.width },
            height: { ideal: model.height },
            frameRate: model.fps,
        }
        : {
            facingMode: { ideal: facingMode },
            width: { ideal: isLandscapeViewport ? 1280 : 720 },
            height: { ideal: isLandscapeViewport ? 720 : 1280 },
            frameRate: 30,
        };
    return navigator.mediaDevices.getUserMedia({ audio: false, video: constraints });
}

async function openPreview() {
    const attempt = Symbol('camera');
    pendingCamera = attempt;
    status('opening');
    if (activeProvider === 'decart') {
        try {
            sdk ||= await import('../vendor/decart-sdk.js?v=0.2.14');
            model = sdk.models.realtime(config.model);
        } catch {
            if (pendingCamera === attempt) {
                pendingCamera = undefined;
                status('ready', 'sdk_unavailable');
            }
            return;
        }
    } else if (activeProvider === 'reactor') {
        model = undefined;
        try {
            reactorSdk ||= await import('../vendor/reactor-sdk.js?v=3.5.0');
        } catch {
            if (pendingCamera === attempt) {
                pendingCamera = undefined;
                status('ready', 'sdk_unavailable');
            }
            return;
        }
    } else {
        model = undefined;
        try {
            xmaxSdk ||= await import('../vendor/xmax-sdk/index.js?v=1.1.5');
        } catch {
            if (pendingCamera === attempt) {
                pendingCamera = undefined;
                status('ready', 'sdk_unavailable');
            }
            return;
        }
    }
    if (pendingCamera !== attempt || document.hidden) return;
    try {
        const stream = await requestCameraStream();
        if (pendingCamera !== attempt || document.hidden) {
            stream.getTracks().forEach(track => track.stop());
            return;
        }
        pendingCamera = undefined;
        camera = stream;
        for (const track of stream.getTracks()) track.addEventListener('ended', () => {
            if (camera === stream) finish('stopped', 'camera_ended');
        }, { once: true });
        $('local').srcObject = stream;
        const trackDims = readStreamTrackDims(stream);
        if (trackDims) setDetectedSourceDims(trackDims.width, trackDims.height);
        status('previewing');
        if (currentViewport().width <= 900) {
            $('stage')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    } catch {
        if (pendingCamera === attempt) {
            pendingCamera = undefined;
            status('ready', 'camera_denied');
        }
    }
}

async function flipCamera() {
    if (switchingCamera) return;
    if (run?.provider === 'xmax' && run.xmaxRealtime) {
        switchingCamera = true;
        renderStreamsUi();
        try {
            await run.xmaxRealtime.switchCamera();
            facingMode = facingMode === 'user' ? 'environment' : 'user';
            mirrored = facingMode === 'user';
            const switchedDims = readStreamTrackDims(run.xmaxLocalView?.videoElement?.srcObject);
            if (switchedDims) setDetectedSourceDims(switchedDims.width, switchedDims.height);
        } catch {
            /* ignore unsupported flip */
        } finally {
            switchingCamera = false;
            renderStreamsUi();
        }
        return;
    }

    if (run?.provider === 'reactor' && run.reactorClient) {
        const prevFacing = facingMode;
        facingMode = prevFacing === 'user' ? 'environment' : 'user';
        switchingCamera = true;
        renderStreamsUi();
        try {
            const nextStream = await requestCameraStream();
            const nextTrack = nextStream.getVideoTracks()[0];
            if (!nextTrack || !run?.reactorClient) {
                nextStream.getTracks().forEach(track => track.stop());
                return;
            }
            const pc = run.reactorClient.getPeerConnection?.();
            const sender = pc?.getSenders?.().find(s => s.track?.kind === 'video');
            if (sender) {
                await sender.replaceTrack(nextTrack);
            } else {
                await run.reactorClient.unpublishTrack('source');
                await run.reactorClient.publishTrack('source', nextTrack);
            }
            const prevStream = camera;
            camera = nextStream;
            nextTrack.addEventListener('ended', () => {
                if (camera === nextStream) finish('stopped', 'camera_ended');
            }, { once: true });
            if ($('local')) $('local').srcObject = nextStream;
            prevStream?.getTracks().forEach(track => track.stop());
            mirrored = facingMode === 'user';
            const nextDims = readStreamTrackDims(nextStream);
            if (nextDims) setDetectedSourceDims(nextDims.width, nextDims.height);
        } catch {
            facingMode = prevFacing;
        } finally {
            switchingCamera = false;
            renderStreamsUi();
        }
        return;
    }

    if (!camera || (activeProvider === 'decart' && !model)) return;
    const prevFacing = facingMode;
    facingMode = prevFacing === 'user' ? 'environment' : 'user';
    switchingCamera = true;
    renderStreamsUi();
    try {
        const nextStream = await requestCameraStream();
        const nextTrack = nextStream.getVideoTracks()[0];
        if (!nextTrack || !camera) {
            nextStream.getTracks().forEach(track => track.stop());
            return;
        }
        if (run?.client?.replaceVideoTrack) {
            await run.client.replaceVideoTrack(nextTrack);
        }
        const prevStream = camera;
        camera = nextStream;
        nextTrack.addEventListener('ended', () => {
            if (camera === nextStream) finish('stopped', 'camera_ended');
        }, { once: true });
        $('local').srcObject = nextStream;
        prevStream.getTracks().forEach(track => track.stop());
        const nextDims = readStreamTrackDims(nextStream);
        if (nextDims) setDetectedSourceDims(nextDims.width, nextDims.height);
        if (facingMode === 'environment') mirrored = false;
        else if (facingMode === 'user') mirrored = true;
    } catch {
        facingMode = prevFacing;
    } finally {
        switchingCamera = false;
        renderStreamsUi();
    }
}

function captureSnapshot() {
    const video = run?.xmaxRemoteView?.videoElement || $('remote');
    if (!video || !video.videoWidth || !video.videoHeight) return;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(blob => {
        if (!blob) return;
        if (snapshotUrl) URL.revokeObjectURL(snapshotUrl);
        snapshotUrl = URL.createObjectURL(blob);
        if ($('snapshot-img')) $('snapshot-img').src = snapshotUrl;
        if ($('snapshot-download')) $('snapshot-download').href = snapshotUrl;
        if ($('snapshot-result')) $('snapshot-result').hidden = false;
    }, 'image/png');
}

async function refreshReceipt(id) {
    for (let index = 0; index < 8 && lastReceipt?.id === id; index++) {
        const data = await api(`/sessions/${id}`).catch(() => null);
        if (lastReceipt?.id !== id) return;
        if (data?.state === 'ended') {
            lastReceipt = data;
            render();
            await loadConfig({ preserveStatus: true });
            return;
        }
        await new Promise(resolve => setTimeout(resolve, 900));
    }
    if (lastReceipt?.id === id) {
        lastReceipt = { id, state: 'unknown' };
        render();
        await loadConfig({ preserveStatus: true });
    }
}

function stopTicket(id, meta = {}) {
    const payload = {};
    if (meta.reason) payload.reason = normalizeClientStopReason(meta.reason, meta.stage);
    if (meta.stage) payload.stage = String(meta.stage).slice(0, 24);
    if (meta.detail) payload.detail = sanitizeRealtimeDetail(meta.detail);
    return api(`/sessions/${id}/stop`, payload, { keepalive: true }).catch(() => {});
}

function cleanupXmaxAttempt(attempt) {
    try { attempt.xmaxLocalView?.detach(); } catch { /* ignore */ }
    try { attempt.xmaxRemoteView?.detach(); } catch { /* ignore */ }
    if ($('xmax-local')) $('xmax-local').replaceChildren();
    if ($('xmax-remote')) $('xmax-remote').replaceChildren();
    attempt.xmaxLocalReady = false;
    attempt.xmaxRemoteReady = false;
    attempt.xmaxUsingExternalCamera = false;
    if (attempt.xmaxCropCleanup) {
        try { attempt.xmaxCropCleanup(); } catch { /* ignore */ }
        attempt.xmaxCropCleanup = undefined;
    }
    if (attempt.xmaxExternalMediaStream) {
        attempt.xmaxExternalMediaStream.getTracks().forEach(track => track.stop());
        attempt.xmaxExternalMediaStream = undefined;
    }
    if (attempt.xmaxRealtime) {
        void attempt.xmaxRealtime.close().catch(() => {});
        attempt.xmaxRealtime = undefined;
    }
}

function finish(next = 'stopped', error = '', detail = '', stage = '') {
    const attempt = run;
    run = undefined;
    pendingCamera = undefined;
    const effectiveStage = stage || attempt?.stage || '';
    const normalizedReason = normalizeClientStopReason(
        error || (next === 'limitReached' ? 'limit_reached' : next === 'hiddenStop' ? 'hidden_stop' : 'stopped'),
        effectiveStage,
    );
    if (attempt) {
        clearInterval(attempt.timer);
        clearTimeout(attempt.firstFrame);
        if (attempt.id) {
            lastReceipt = { id: attempt.id, state: 'waiting', provider_key: attempt.provider };
            void stopTicket(attempt.id, {
                reason: normalizedReason,
                stage: effectiveStage,
                detail,
            }).finally(() => {
                if (lastReceipt?.id === attempt.id) {
                    void refreshReceipt(attempt.id);
                }
            });
        }
        if (attempt.provider === 'xmax') {
            cleanupXmaxAttempt(attempt);
        }
        if (attempt.provider === 'reactor' && attempt.reactorClient) {
            const rc = attempt.reactorClient;
            attempt.reactorClient = undefined;
            void rc.disconnect(false).catch(() => {});
        }
    }
    camera?.getTracks().forEach(track => track.stop());
    camera = undefined;
    if ($('local')) $('local').srcObject = null;
    if ($('remote')) $('remote').srcObject = null;
    liveRemoteDims = null;
    if (!usingLocalFileSource()) detectedSourceDims = null;
    status(next, error, {}, detail);
    if (usingLocalFileSource() && xmaxSourceMode === 'video' && xmaxSourceUrl) {
        void $('local')?.play?.().catch(() => {});
    }
    attempt?.client?.disconnect();
}

function armFirstFrameTimeout(attempt, timeoutMs = 15000) {
    clearTimeout(attempt.firstFrame);
    attempt.firstFrame = setTimeout(() => {
        if (run === attempt && !attempt.firstFrameReceived) {
            finish('stopped', 'no_output', `first frame timeout after ${Math.round(timeoutMs / 1000)}s`, attempt.stage || 'session');
        }
    }, timeoutMs);
}

function startActiveCountdown(attempt) {
    if (!attempt.generatedAt) attempt.generatedAt = performance.now();
    if (!attempt.deadline) {
        attempt.deadline = Math.min(attempt.hardDeadline, attempt.generatedAt + attempt.limit * 1000);
    }
}

async function startDecart() {
    const needCode = config?.require_access_code !== false;
    const code = needCode ? $('code').value.trim() : '';
    if (needCode && code) {
        try { sessionStorage.setItem(codeStorageKey, code); } catch { /* ignore */ }
    }
    const limit = seconds();
    const rate = config.cents_per_second;
    const attempt = { provider: 'decart', limit, rate, stage: 'garment' };
    run = attempt;
    lastReceipt = undefined;
    status('preparing');
    try {
        const image = await garmentImage({ maxSide: 720, maxBytes: 256 * 1024 });
        if (run !== attempt || document.hidden) return;
        attempt.stage = 'ticket';
        const ticket = await api('/sessions', { access_code: code, seconds: limit, max_cents: limit * rate });
        if (run !== attempt || document.hidden) {
            void stopTicket(ticket.id);
            return;
        }
        attempt.id = ticket.id;
        try { sessionStorage.setItem(storageKey, ticket.id); } catch { /* ignore */ }
        attempt.hardDeadline = performance.now() + (limit + 18) * 1000;
        attempt.timer = setInterval(() => {
            if (run !== attempt) return;
            const now = performance.now();
            if ((attempt.deadline && now >= attempt.deadline) || now >= attempt.hardDeadline) {
                finish('limitReached');
            } else {
                renderUsage();
            }
        }, 250);
        attempt.stage = 'connect';
        armFirstFrameTimeout(attempt, 15000);
        status('connecting');
        const signal = new URL(root, location.href);
        signal.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        let dialed = false;
        const client = sdk.createDecartClient({
            proxy: location.origin,
            realtimeBaseUrl: signal.href,
            telemetry: false,
            apiKeyProvider: () => {
                if (dialed || run !== attempt) throw new Error('A new session requires user confirmation');
                dialed = true;
                return 'workbench';
            },
        });
        const realtime = await client.realtime.connect(camera, {
            model, retries: 0, resolution: '720p', mirror: 'auto',
            queryParams: { ticket: ticket.id },
            initialState: { image, prompt: { text: promptText(), enhance: false } },
            onQueuePosition: pos => {
                if (run !== attempt) return;
                armFirstFrameTimeout(attempt, 15000);
                status('queued', '', {
                    position: pos?.position ?? 1,
                    total: pos?.queueSize ?? pos?.position ?? 1,
                });
            },
            onConnectionChange: state => {
                if (run !== attempt) return;
                if (state === 'generating') {
                    attempt.stage = 'live';
                    attempt.firstFrameReceived = true;
                    clearTimeout(attempt.firstFrame);
                    startActiveCountdown(attempt);
                    status('live');
                }
                if (state === 'reconnecting' || (state === 'disconnected' && attempt.client)) finish('stopped', 'connection_lost');
            },
            onRemoteStream: stream => {
                if (run === attempt) {
                    $('remote').srcObject = stream;
                    renderStreamsUi();
                }
            },
        });
        if (run !== attempt) {
            realtime.disconnect();
            return;
        }
        attempt.client = realtime;
        realtime.on('generationTick', data => {
            attempt.tick = data.seconds;
            attempt.firstFrameReceived = true;
            startActiveCountdown(attempt);
        });
        realtime.on('generationEnded', ({ reason }) => {
            if (run !== attempt) return;
            if (reason === 'timeout') finish('limitReached');
            else if (['moderation_violation', 'insufficient_credits'].includes(reason)) finish('stopped', reason);
            else finish('stopped');
        });
        realtime.on('error', err => {
            if (run === attempt) {
                console.error('[realtime][decart] stream error:', err);
                finish('stopped', 'provider_error', formatRealtimeErrorDetail(err, attempt.stage), attempt.stage);
            }
        });
        if (phase !== 'live') status('connected');
    } catch (err) {
        if (run !== attempt) return;
        console.error(`[realtime][decart] failed at stage=${attempt.stage || 'unknown'}`, err);
        const rawMsg = typeof err?.message === 'string' ? err.message.trim() : '';
        const mapped = KNOWN_ERROR_CODES.has(rawMsg) ? rawMsg : (attempt.id ? 'connection_failed' : 'request_failed');
        const detail = formatRealtimeErrorDetail(err, attempt.stage);
        if (attempt.id) finish('stopped', mapped, detail, attempt.stage);
        else {
            run = undefined;
            if (mapped === 'quote_changed') await loadConfig();
            status('previewing', mapped, {}, detail);
        }
    }
}

async function requestRelaxedCameraStream() {
    const attempts = [
        { audio: false, video: { facingMode: { ideal: facingMode } } },
        { audio: false, video: true },
    ];
    let lastErr;
    for (const constraints of attempts) {
        try {
            return await navigator.mediaDevices.getUserMedia(constraints);
        } catch (err) {
            lastErr = err;
        }
    }
    throw lastErr || new Error('camera_not_readable');
}

async function readVideoElementDims(video, timeoutMs = 5000) {
    if (video.videoWidth > 0 && video.videoHeight > 0) {
        return { width: video.videoWidth, height: video.videoHeight };
    }
    await new Promise(resolve => {
        let done = false;
        const finishWait = () => {
            if (done) return;
            done = true;
            clearTimeout(timer);
            video.removeEventListener('loadedmetadata', onReady);
            video.removeEventListener('resize', onReady);
            resolve();
        };
        const onReady = () => {
            if (video.videoWidth > 0 && video.videoHeight > 0) finishWait();
        };
        const timer = setTimeout(finishWait, timeoutMs);
        video.addEventListener('loadedmetadata', onReady);
        video.addEventListener('resize', onReady);
    });
    return (video.videoWidth > 0 && video.videoHeight > 0)
        ? { width: video.videoWidth, height: video.videoHeight }
        : null;
}

async function createCroppedCameraExternalStream(attempt, realtime, { width, height, fps, existingStream = null }) {
    const rawStream = existingStream || await requestRelaxedCameraStream();
    if (run !== attempt || document.hidden) {
        rawStream.getTracks().forEach(track => track.stop());
        throw new Error('stopped');
    }
    const video = document.createElement('video');
    video.muted = true;
    video.playsInline = true;
    video.srcObject = rawStream;
    try { await video.play(); } catch { /* loadedmetadata may still populate dimensions */ }
    const actualDims = (await readVideoElementDims(video, 5000)) || readStreamTrackDims(rawStream);
    if (run !== attempt || document.hidden) {
        video.pause?.();
        video.srcObject = null;
        rawStream.getTracks().forEach(track => track.stop());
        throw new Error('stopped');
    }
    if (actualDims) setDetectedSourceDims(actualDims.width, actualDims.height);

    if (!actualDims || !needsAspectCenterCrop(actualDims, { width, height })) {
        video.pause?.();
        video.srcObject = null;
        const rawTrack = rawStream.getVideoTracks()[0];
        if (!rawTrack) {
            rawStream.getTracks().forEach(track => track.stop());
            throw new Error('camera_not_readable');
        }
        attempt.xmaxExternalMediaStream = rawStream;
        attempt.xmaxUsingExternalCamera = true;
        return await realtime.createExternalVideoStream({
            videoTrack: rawTrack,
            videoFormat: new xmaxSdk.RealtimeVideoFormat({ width, height, fps }),
        });
    }

    const crop = computeCenterCropRect(actualDims.width, actualDims.height, width, height);
    const canvas = document.createElement('canvas');
    canvas.width = crop.outWidth;
    canvas.height = crop.outHeight;
    const ctx = canvas.getContext('2d', { alpha: false });
    ctx.drawImage(video, crop.sx, crop.sy, crop.sw, crop.sh, 0, 0, crop.outWidth, crop.outHeight);
    const targetFps = Math.max(15, Math.min(30, Number(fps) || 30));
    const cropStream = canvas.captureStream(targetFps);
    const croppedTrack = cropStream.getVideoTracks()[0];
    if (!croppedTrack) {
        video.pause?.();
        video.srcObject = null;
        cropStream.getTracks().forEach(track => track.stop());
        rawStream.getTracks().forEach(track => track.stop());
        throw new Error('camera_not_readable');
    }

    let stopped = false;
    let rvfcId = null;
    let intervalId = null;
    const drawFrame = () => {
        if (stopped || video.readyState < 2) return;
        const vw = video.videoWidth;
        const vh = video.videoHeight;
        if (!vw || !vh) return;
        const c = (vw === actualDims.width && vh === actualDims.height)
            ? crop
            : computeCenterCropRect(vw, vh, width, height);
        ctx.drawImage(video, c.sx, c.sy, c.sw, c.sh, 0, 0, canvas.width, canvas.height);
    };

    if (typeof video.requestVideoFrameCallback === 'function') {
        const onVideoFrame = () => {
            if (stopped) return;
            drawFrame();
            rvfcId = video.requestVideoFrameCallback(onVideoFrame);
        };
        rvfcId = video.requestVideoFrameCallback(onVideoFrame);
    } else {
        intervalId = setInterval(drawFrame, Math.max(16, Math.round(1000 / targetFps)));
    }

    const cleanupCrop = () => {
        stopped = true;
        if (rvfcId !== null && typeof video.cancelVideoFrameCallback === 'function') {
            try { video.cancelVideoFrameCallback(rvfcId); } catch { /* ignore */ }
            rvfcId = null;
        }
        if (intervalId !== null) {
            clearInterval(intervalId);
            intervalId = null;
        }
        try { video.pause?.(); } catch { /* ignore */ }
        video.srcObject = null;
        cropStream.getTracks().forEach(track => track.stop());
        rawStream.getTracks().forEach(track => track.stop());
    };

    attempt.xmaxCropCleanup = cleanupCrop;
    attempt.xmaxUsingExternalCamera = true;
    try {
        return await realtime.createExternalVideoStream({
            videoTrack: croppedTrack,
            videoFormat: new xmaxSdk.RealtimeVideoFormat({ width, height, fps }),
        });
    } catch (err) {
        if (attempt.xmaxCropCleanup === cleanupCrop) {
            attempt.xmaxCropCleanup = undefined;
        }
        cleanupCrop();
        throw err;
    }
}

async function acquireXmaxCameraStream(attempt, realtime, { activeModel, preset, presetMode, position, width, height, fps }) {
    if (presetMode !== XMAX_PRESET_AUTO && detectedSourceDims && needsAspectCenterCrop(detectedSourceDims, { width, height })) {
        return await createCroppedCameraExternalStream(attempt, realtime, { width, height, fps });
    }

    let firstErr;
    let localStream;
    try {
        localStream = await realtime.createLocalCameraStream({
            preset,
            position,
            useMicrophone: false,
        });
    } catch (err) {
        firstErr = err;
        if (err?.code === 'CAMERA_PERMISSION_DENIED' || err?.code === 'CANCELLED' || err?.name === 'NotAllowedError') {
            throw err;
        }
        console.warn('[realtime][xmax] createLocalCameraStream attempt 1 failed:', formatRealtimeErrorDetail(err, 'camera'));
    }

    let retryErr;
    if (!localStream) {
        await sleep(500);
        if (run !== attempt || document.hidden) {
            throw new Error('stopped');
        }
        try {
            localStream = await realtime.createLocalCameraStream({
                preset,
                position,
                useMicrophone: false,
            });
        } catch (err) {
            retryErr = err;
            if (err?.code === 'CAMERA_PERMISSION_DENIED' || err?.code === 'CANCELLED' || err?.name === 'NotAllowedError') {
                throw err;
            }
            console.warn('[realtime][xmax] createLocalCameraStream retry failed, falling back to external video track:', formatRealtimeErrorDetail(err, 'camera'));
        }
    }

    if (localStream) {
        const actualDims = readStreamTrackDims(localStream?.videoTrack?.mediaStreamTrack);
        if (actualDims) {
            setDetectedSourceDims(actualDims.width, actualDims.height);
            if (presetMode === XMAX_PRESET_AUTO && needsAspectCenterCrop(actualDims, { width, height })) {
                const refined = pickBestXmaxPreset(activeModel, actualDims, currentViewport());
                if (refined !== preset && typeof realtime.updateCameraFormat === 'function') {
                    try {
                        await realtime.updateCameraFormat(refined);
                    } catch (err) {
                        console.warn('[realtime][xmax] updateCameraFormat skipped:', formatRealtimeErrorDetail(err, 'camera'));
                    }
                }
            }
        }
        return localStream;
    }

    let fallbackStream;
    try {
        fallbackStream = await requestRelaxedCameraStream();
        if (run !== attempt || document.hidden) {
            fallbackStream.getTracks().forEach(track => track.stop());
            throw new Error('stopped');
        }
        const actualDims = readStreamTrackDims(fallbackStream);
        if (actualDims) setDetectedSourceDims(actualDims.width, actualDims.height);
        if (presetMode === XMAX_PRESET_AUTO) {
            const bestPreset = actualDims
                ? pickBestXmaxPreset(activeModel, actualDims, currentViewport())
                : preset;
            const bestDims = parsePresetDimensions(bestPreset);
            const videoTrack = fallbackStream.getVideoTracks()[0];
            if (!videoTrack) {
                fallbackStream.getTracks().forEach(track => track.stop());
                throw new Error('camera_not_readable');
            }
            attempt.xmaxExternalMediaStream = fallbackStream;
            attempt.xmaxUsingExternalCamera = true;
            return await realtime.createExternalVideoStream({
                videoTrack,
                videoFormat: new xmaxSdk.RealtimeVideoFormat({ width: bestDims.width, height: bestDims.height, fps }),
            });
        }
        return await createCroppedCameraExternalStream(attempt, realtime, {
            width,
            height,
            fps,
            existingStream: fallbackStream,
        });
    } catch (extErr) {
        fallbackStream?.getTracks().forEach(track => track.stop());
        if (attempt.xmaxExternalMediaStream === fallbackStream) {
            attempt.xmaxExternalMediaStream = undefined;
        }
        if (extErr?.name === 'NotReadableError' || extErr?.name === 'NotAllowedError') {
            throw extErr;
        }
        throw retryErr || firstErr || extErr;
    }
}

async function startXmax() {
    const needCode = config?.require_access_code !== false;
    const code = needCode ? $('code').value.trim() : '';
    if (needCode && code) {
        try { sessionStorage.setItem(codeStorageKey, code); } catch { /* ignore */ }
    }
    const limit = seconds();
    const chosenModel = selectedXmaxModel();
    const presetModeAtStart = xmaxPresetSelection;
    const adaptiveEnabled = $('xmax-adaptive') ? Boolean($('xmax-adaptive').checked) : true;
    const sourceModeAtStart = xmaxSourceMode;
    const sourceFileAtStart = xmaxSourceFile;
    const maxCents = calculateMaxCents('xmax', config, limit);
    const attempt = {
        provider: 'xmax',
        sourceMode: sourceModeAtStart,
        garmentSignature: currentGarmentSignature(),
        limit,
        rate: config.cents_per_minute || 10,
        cfgSnapshot: { ...config },
        stage: 'sdk',
    };
    run = attempt;
    lastReceipt = undefined;
    status('preparing');

    try {
        xmaxSdk ||= await import('../vendor/xmax-sdk/index.js?v=1.1.5');
        attempt.stage = 'garment';
        const image = await garmentImage({ maxSide: 1024, maxBytes: 900 * 1024 });
        if (run !== attempt || document.hidden) return;

        attempt.stage = 'ticket';
        const ticket = await api('/xmax/sessions', {
            access_code: code,
            seconds: limit,
            max_cents: maxCents,
            model: chosenModel,
        });
        if (run !== attempt || document.hidden) {
            void stopTicket(ticket.id);
            return;
        }
        attempt.id = ticket.id;
        try { sessionStorage.setItem(storageKey, ticket.id); } catch { /* ignore */ }

        attempt.stage = 'token';
        const tokenData = await api(`/xmax/sessions/${ticket.id}/token`, {});
        if (run !== attempt || document.hidden) {
            finish('stopped');
            return;
        }

        const env = tokenData.environment === 'china'
            ? xmaxSdk.XmaxEnvironment.china
            : xmaxSdk.XmaxEnvironment.global;
        const client = new xmaxSdk.XmaxClient(new xmaxSdk.XmaxConfiguration({
            apiKey: tokenData.temporary_api_key,
            environment: env,
            loggerOptions: xmaxSdk.XmaxLoggerOption.business,
        }));
        const storage = client.createStorageService();
        attempt.xmaxStorage = storage;

        attempt.stage = 'upload';
        status('xmaxUploadingGarment');
        const uploaded = await storage.uploadImage({
            data: image,
            fileName: 'garment.jpg',
            contentType: 'image/jpeg',
        });
        attempt.referenceUrl = uploaded.url;

        if (run !== attempt || document.hidden) {
            finish('stopped');
            return;
        }

        attempt.hardDeadline = performance.now() + (limit + 22) * 1000;
        attempt.timer = setInterval(() => {
            if (run !== attempt) return;
            const now = performance.now();
            if ((attempt.deadline && now >= attempt.deadline) || now >= attempt.hardDeadline) {
                finish('limitReached');
            } else {
                renderUsage();
            }
        }, 250);

        attempt.stage = 'camera';
        status('xmaxConnecting');
        // Snapshot actual preview track/video dims and release raw camera right before Agora capture opens.
        const previewTrackDims = readStreamTrackDims(camera)
            || ($('local')?.videoWidth && $('local')?.videoHeight
                ? { width: $('local').videoWidth, height: $('local').videoHeight }
                : null);
        if (previewTrackDims) setDetectedSourceDims(previewTrackDims.width, previewTrackDims.height);
        const hadPreviewCamera = Boolean(camera);
        camera?.getTracks().forEach(track => track.stop());
        camera = undefined;
        if ($('local')) {
            $('local').pause?.();
            $('local').srcObject = null;
        }
        if (hadPreviewCamera && sourceModeAtStart === 'camera') {
            await sleep(250);
            if (run !== attempt || document.hidden) {
                finish('stopped');
                return;
            }
        }

        const contentMode = stageFit === 'contain' ? xmaxSdk.VideoContentMode.fit : xmaxSdk.VideoContentMode.fill;
        const localView = new xmaxSdk.XmaxRealtimeVideoView({
            videoContentMode: contentMode,
            isInteractionEnabled: false,
        });
        localView.element.style.width = '100%';
        localView.element.style.height = '100%';
        const remoteView = new xmaxSdk.XmaxRealtimeVideoView({
            videoContentMode: contentMode,
            isInteractionEnabled: false,
        });
        remoteView.element.style.width = '100%';
        remoteView.element.style.height = '100%';
        for (const evt of ['loadedmetadata', 'resize']) {
            localView.videoElement?.addEventListener(evt, () => {
                if (run !== attempt) return;
                const v = localView.videoElement;
                if (v?.videoWidth && v?.videoHeight) setDetectedSourceDims(v.videoWidth, v.videoHeight);
            });
            remoteView.videoElement?.addEventListener(evt, () => {
                if (run !== attempt) return;
                const v = remoteView.videoElement;
                if (v?.videoWidth && v?.videoHeight) setLiveRemoteDims(v.videoWidth, v.videoHeight);
            });
        }
        if ($('xmax-local')) localView.attach($('xmax-local'));
        if ($('xmax-remote')) remoteView.attach($('xmax-remote'));
        localView.isMirrored = sourceModeAtStart === 'camera' ? mirrored : false;
        attempt.xmaxLocalView = localView;
        attempt.xmaxRemoteView = remoteView;

        const activeModel = tokenData.model || chosenModel;
        const realtime = client.createRealtimeManager(new xmaxSdk.RealtimeConfiguration({
            model: activeModel,
            isAdaptiveQualityEnabled: adaptiveEnabled,
        }));
        attempt.xmaxRealtime = realtime;

        await realtime.setStateListener(state => {
            if (run !== attempt) return;
            if (state.sessionID && attempt.providerSessionAttached !== state.sessionID) {
                attempt.providerSessionAttached = state.sessionID;
                void api(`/xmax/sessions/${attempt.id}/attach`, { provider_session_id: state.sessionID }).catch(() => {});
            }
            if (state.reason?.kind === 'failure') {
                const sdkErr = state.reason.error;
                console.error('[realtime][xmax] state failure:', sdkErr);
                finish(
                    'stopped',
                    mapXmaxErrorCode(sdkErr),
                    formatRealtimeErrorDetail(sdkErr, attempt.stage),
                    attempt.stage,
                );
                return;
            }
            if (state.connectionState === 'Connected' || state.connectionState === 'Starting') {
                startActiveCountdown(attempt);
                if (phase !== 'live') status('connected');
            } else if (state.connectionState === 'Generating') {
                attempt.stage = 'live';
                attempt.firstFrameReceived = true;
                clearTimeout(attempt.firstFrame);
                startActiveCountdown(attempt);
                attempt.xmaxRemoteReady = true;
                renderStreamsUi();
                void remoteView.videoElement?.play?.().catch(() => {});
                status('live');
            }
        });

        await realtime.setDownlinkVideoStatisticsListener(stats => {
            if (run !== attempt) return;
            if (!stats) {
                attempt.statsText = '';
            } else {
                const parts = [];
                if (stats.width && stats.height) {
                    parts.push(`${stats.width}×${stats.height}`);
                    setLiveRemoteDims(stats.width, stats.height);
                }
                if (Number.isFinite(stats.renderFrameRate)) parts.push(`${Math.round(stats.renderFrameRate)} fps`);
                if (Number.isFinite(stats.endToEndDelayMs)) parts.push(`${Math.round(stats.endToEndDelayMs)} ms`);
                attempt.statsText = parts.join(' · ');
            }
            renderTelemetry();
        });

        await realtime.setNetworkQualityListener(net => {
            if (run !== attempt) return;
            attempt.netText = net ? `${t('xmaxNetwork')}: ${net.downlink || net.uplink}` : '';
            renderTelemetry();
        });

        if (sourceModeAtStart === 'image' && sourceFileAtStart && !detectedSourceDims) {
            const imgDims = await readImageFileDimensions(sourceFileAtStart);
            if (run !== attempt || document.hidden) {
                finish('stopped');
                return;
            }
            if (imgDims) setDetectedSourceDims(imgDims.width, imgDims.height);
        } else if (sourceModeAtStart === 'video' && $('local')?.videoWidth && $('local')?.videoHeight) {
            setDetectedSourceDims($('local').videoWidth, $('local').videoHeight);
        }

        const chosenPreset = presetModeAtStart === XMAX_PRESET_AUTO
            ? pickBestXmaxPreset(activeModel, detectedSourceDims, currentViewport())
            : cameraPresetForModel(activeModel, presetModeAtStart);
        const preset = cameraPresetForModel(activeModel, chosenPreset || tokenData.camera_preset);
        const { width, height } = parsePresetDimensions(preset);
        const fps = xmaxSdk.defaultFrameRate ? xmaxSdk.defaultFrameRate(activeModel) : 30;
        let localStream;
        if (sourceModeAtStart === 'image' && sourceFileAtStart) {
            const videoFormat = new xmaxSdk.RealtimeVideoFormat({ width, height, fps });
            localStream = await realtime.createLocalImageStream({
                file: sourceFileAtStart,
                videoFormat,
            });
        } else if (sourceModeAtStart === 'video' && sourceFileAtStart) {
            const videoFormat = new xmaxSdk.RealtimeVideoFormat({ width, height, fps });
            localStream = await realtime.createLocalVideoStream({
                file: sourceFileAtStart,
                videoFormat,
                loop: true,
                includeAudio: false,
            });
        } else {
            const position = facingMode === 'environment'
                ? xmaxSdk.CameraPosition.back
                : xmaxSdk.CameraPosition.front;
            localStream = await acquireXmaxCameraStream(attempt, realtime, {
                activeModel,
                preset,
                presetMode: presetModeAtStart,
                position,
                width,
                height,
                fps,
            });
        }
        if (run !== attempt || document.hidden) {
            finish('stopped');
            return;
        }
        attempt.xmaxLocalStream = localStream;
        attempt.xmaxLocalReady = true;
        renderStreamsUi();
        localView.track = localStream.videoTrack;
        void localView.videoElement?.play?.().catch(() => {});

        attempt.stage = 'session';
        armFirstFrameTimeout(attempt, 30000);
        const faceRestoration = $('face-restoration')
            ? Boolean($('face-restoration').checked)
            : Boolean(tokenData.face_restoration);
        const remoteStream = await realtime.startGeneration({
            localStream,
            context: new xmaxSdk.RealtimeContext({
                prompt: promptText(),
                referencePath: attempt.referenceUrl,
            }),
            faceRestoration,
        });
        if (run !== attempt) {
            finish('stopped');
            return;
        }
        attempt.xmaxRemoteReady = true;
        renderStreamsUi();
        remoteView.track = remoteStream.videoTrack;
        void remoteView.videoElement?.play?.().catch(() => {});
        if (phase !== 'live') status('connected');
    } catch (err) {
        if (run !== attempt) return;
        console.error(`[realtime][xmax] failed at stage=${attempt.stage || 'unknown'}`, err);
        const rawMsg = typeof err?.message === 'string' ? err.message.trim() : '';
        const mapped = KNOWN_ERROR_CODES.has(rawMsg) ? rawMsg : mapXmaxErrorCode(err);
        const detail = formatRealtimeErrorDetail(err, attempt.stage);
        if (attempt.id) {
            finish('stopped', mapped || 'connection_failed', detail, attempt.stage);
        } else {
            cleanupXmaxAttempt(attempt);
            run = undefined;
            if (mapped === 'quote_changed') await loadConfig();
            const fallbackPhase = usingLocalFileSource()
                ? (xmaxSourceFile ? 'xmaxPreviewSourceReady' : 'ready')
                : (camera ? 'previewing' : 'ready');
            status(fallbackPhase, mapped || 'request_failed', {}, detail);
        }
    }
}

async function startReactor() {
    const needCode = config?.require_access_code !== false;
    const code = needCode ? $('code').value.trim() : '';
    if (needCode && code) {
        try { sessionStorage.setItem(codeStorageKey, code); } catch { /* ignore */ }
    }
    const limit = seconds();
    const chosenModel = selectedReactorModel();
    const maxCents = calculateMaxCents('reactor', config, limit);
    const attempt = {
        provider: 'reactor',
        model: chosenModel,
        limit,
        rate: config.cents_per_minute || 11,
        cfgSnapshot: { ...config },
        stage: 'garment',
    };
    run = attempt;
    lastReceipt = undefined;
    status('preparing');

    try {
        attempt.stage = 'sdk';
        reactorSdk ||= await import('../vendor/reactor-sdk.js?v=3.5.0');
        attempt.stage = 'garment';
        const image = await garmentImage({ maxSide: 1024, maxBytes: 900 * 1024 });
        if (run !== attempt || document.hidden) return;

        if (!camera) {
            attempt.stage = 'camera';
            const stream = await requestCameraStream();
            if (run !== attempt || document.hidden) {
                stream.getTracks().forEach(track => track.stop());
                return;
            }
            camera = stream;
            for (const track of stream.getTracks()) track.addEventListener('ended', () => {
                if (camera === stream) finish('stopped', 'camera_ended');
            }, { once: true });
            if ($('local')) $('local').srcObject = stream;
            renderStreamsUi();
        }

        attempt.stage = 'ticket';
        const ticket = await api('/reactor/sessions', {
            access_code: code,
            seconds: limit,
            max_cents: maxCents,
            model: chosenModel,
        });
        if (run !== attempt || document.hidden) {
            void stopTicket(ticket.id);
            return;
        }
        attempt.id = ticket.id;
        try { sessionStorage.setItem(storageKey, ticket.id); } catch { /* ignore */ }

        attempt.stage = 'token';
        const tokenData = await api(`/reactor/sessions/${ticket.id}/token`, {});
        if (run !== attempt || document.hidden) {
            finish('stopped');
            return;
        }

        const activeModel = tokenData.model || chosenModel;
        const activeApiUrl = tokenData.api_url || tokenData.base_url;
        attempt.hardDeadline = performance.now() + (limit + 25) * 1000;
        attempt.timer = setInterval(() => {
            if (run !== attempt) return;
            const now = performance.now();
            if ((attempt.deadline && now >= attempt.deadline) || now >= attempt.hardDeadline) {
                finish('limitReached');
            } else {
                renderUsage();
            }
        }, 250);
        attempt.stage = 'connect';
        armFirstFrameTimeout(attempt, 25000);

        status('reactorConnecting');
        const client = new reactorSdk.Reactor({
            modelName: activeModel,
            ...(activeApiUrl ? { apiUrl: activeApiUrl } : {}),
            maxSessionAttempts: 1,
            maxSdpAttempts: 2,
            logLevel: 'error',
        });
        attempt.reactorClient = client;

        client.on('sessionIdChanged', sessionId => {
            if (run === attempt && sessionId && attempt.providerSessionAttached !== sessionId) {
                attempt.providerSessionAttached = sessionId;
                void api(`/reactor/sessions/${attempt.id}/attach`, { provider_session_id: sessionId }).catch(() => {});
            }
        });
        client.on('trackReceived', (_name, track, stream) => {
            if (run === attempt && track?.kind === 'video') {
                if ($('remote')) $('remote').srcObject = stream;
                renderStreamsUi();
            }
        });
        client.on('statsUpdate', stats => {
            if (run !== attempt) return;
            const parts = [];
            if (Number.isFinite(stats?.framesPerSecond)) parts.push(`${Math.round(stats.framesPerSecond)} fps`);
            if (Number.isFinite(stats?.rtt)) parts.push(`${Math.round(stats.rtt)} ms`);
            attempt.statsText = parts.join(' · ');
            renderTelemetry();
        });
        client.on('runtimeMessage', msg => {
            if (run === attempt && msg?.type === 'moderation' && msg?.data?.action === 'terminate') {
                finish('stopped', 'moderation_violation', 'moderation terminate', attempt.stage);
            }
        });
        client.on('error', err => {
            if (run === attempt && !err?.recoverable) {
                console.error('[realtime][reactor] error:', err);
                finish('stopped', mapReactorErrorCode(err), formatRealtimeErrorDetail(err, attempt.stage), attempt.stage);
            }
        });
        client.on('statusChanged', nextStatus => {
            if (run !== attempt) return;
            if (nextStatus === 'ready') {
                attempt.reactorConnected = true;
                attempt.stage = 'live';
                startActiveCountdown(attempt);
                if (phase !== 'live') status('connected');
            } else if (nextStatus === 'disconnected' && attempt.reactorConnected) {
                finish('stopped', 'connection_lost', 'reactor disconnected', attempt.stage);
            }
        });

        await client.connect(tokenData.jwt, { maxAttempts: 1 });
        if (run !== attempt || document.hidden) {
            finish('stopped');
            return;
        }
        const currentSid = client.getSessionId?.();
        if (currentSid && attempt.providerSessionAttached !== currentSid) {
            attempt.providerSessionAttached = currentSid;
            void api(`/reactor/sessions/${attempt.id}/attach`, { provider_session_id: currentSid }).catch(() => {});
        }

        attempt.stage = 'publish';
        const videoTrack = camera?.getVideoTracks?.()[0];
        if (!videoTrack) throw new Error('camera_ended');
        await client.publishTrack('source', videoTrack);
        void client.setTrackBitrate('source', { maxBps: 4_000_000 }).catch(() => {});

        attempt.stage = 'upload';
        const fileRef = await client.uploadFile(image, { name: 'garment.jpg' });
        if (run !== attempt) {
            finish('stopped');
            return;
        }
        await client.sendCommand('set_reference_image', fileRef);
        await client.sendCommand('set_prompt', { prompt: promptText() });
        if (activeModel === 'xmax/x2') {
            await client.sendCommand('set_keep_backlog', { keep_backlog: false });
        }
    } catch (err) {
        if (run !== attempt) return;
        console.error(`[realtime][reactor] failed at stage=${attempt.stage || 'unknown'}`, err);
        const rawMsg = typeof err?.message === 'string' ? err.message.trim() : '';
        const mapped = err?.code ? mapReactorErrorCode(err) : (KNOWN_ERROR_CODES.has(rawMsg) ? rawMsg : (attempt.id ? 'connection_failed' : 'request_failed'));
        const detail = formatRealtimeErrorDetail(err, attempt.stage);
        if (attempt.id) {
            finish('stopped', mapped || 'connection_failed', detail, attempt.stage);
        } else {
            run = undefined;
            if (mapped === 'quote_changed') await loadConfig();
            status('previewing', mapped || 'request_failed', {}, detail);
        }
    }
}

async function applyGarment(options = {}) {
    const skipGarmentUpload = Boolean(options && options.skipGarmentUpload);
    const attempt = run;
    if (!attempt || attempt.applying) return;
    if (attempt.provider === 'xmax') {
        if (!attempt.xmaxRealtime || !attempt.xmaxStorage || !attempt.xmaxLocalStream) return;
        attempt.applying = true;
        render();
        try {
            const sig = currentGarmentSignature();
            if (!skipGarmentUpload && (!attempt.referenceUrl || sig !== attempt.garmentSignature)) {
                const image = await garmentImage({ maxSide: 1024, maxBytes: 900 * 1024 });
                if (run !== attempt) return;
                const uploaded = await attempt.xmaxStorage.uploadImage({
                    data: image,
                    fileName: 'garment-swap.jpg',
                    contentType: 'image/jpeg',
                });
                if (run !== attempt) return;
                attempt.referenceUrl = uploaded.url;
                attempt.garmentSignature = sig;
            }
            const faceRestoration = Boolean($('face-restoration')?.checked);
            await attempt.xmaxRealtime.startGeneration({
                localStream: attempt.xmaxLocalStream,
                context: new xmaxSdk.RealtimeContext({
                    prompt: promptText(),
                    referencePath: attempt.referenceUrl,
                }),
                faceRestoration,
            });
            if (run === attempt) status('live');
        } catch (err) {
            if (run === attempt) {
                const code = err?.message === 'invalid_image' ? 'invalid_image' : mapXmaxErrorCode(err);
                status('live', code === 'unsafe_image' ? 'unsafe_image' : 'garment_rejected');
            }
        } finally {
            if (run === attempt) {
                attempt.applying = false;
                render();
            }
        }
        return;
    }

    if (attempt.provider === 'reactor') {
        if (!attempt.reactorClient) return;
        attempt.applying = true;
        render();
        try {
            const image = await garmentImage({ maxSide: 1024, maxBytes: 900 * 1024 });
            if (run !== attempt) return;
            const fileRef = await attempt.reactorClient.uploadFile(image, { name: 'garment-swap.jpg' });
            if (run !== attempt) return;
            await attempt.reactorClient.sendCommand('set_reference_image', fileRef);
            await attempt.reactorClient.sendCommand('set_prompt', { prompt: promptText() });
            if (run === attempt) status('live');
        } catch (err) {
            if (run === attempt) {
                const code = err?.message === 'invalid_image' ? 'invalid_image' : 'garment_rejected';
                status('live', code);
            }
        } finally {
            if (run === attempt) {
                attempt.applying = false;
                render();
            }
        }
        return;
    }

    if (!attempt.client) return;
    attempt.applying = true;
    render();
    try {
        const image = await garmentImage({ maxSide: 720, maxBytes: 256 * 1024 });
        if (run !== attempt) return;
        await attempt.client.set({ image, prompt: promptText(), enhance: false });
        if (run === attempt) status('live');
    } catch (err) {
        if (run === attempt) status('live', err.message === 'invalid_image' ? err.message : 'garment_rejected');
    } finally {
        if (run === attempt) {
            attempt.applying = false;
            render();
        }
    }
}

function clearXmaxSourceFile() {
    if (xmaxSourceUrl) {
        URL.revokeObjectURL(xmaxSourceUrl);
        xmaxSourceUrl = '';
    }
    xmaxSourceFile = null;
    detectedSourceDims = null;
    if ($('xmax-source-file')) $('xmax-source-file').value = '';
    if ($('local-image')) {
        $('local-image').hidden = true;
        $('local-image').removeAttribute('src');
    }
    if ($('local')?.dataset.sourceUrl) {
        $('local').pause?.();
        $('local').removeAttribute('src');
        delete $('local').dataset.sourceUrl;
        $('local').load?.();
    }
}

function selectProvider(nextProvider, { preserveStatus = false } = {}) {
    if (run || pendingCamera) return;
    if (!['decart', 'reactor', 'xmax'].includes(nextProvider)) return;
    if (nextProvider !== activeProvider) {
        liveRemoteDims = null;
        detectedSourceDims = null;
        if (camera) {
            camera.getTracks().forEach(track => track.stop());
            camera = undefined;
            if ($('local')) $('local').srcObject = null;
        }
    }
    activeProvider = nextProvider;
    config = providersState[activeProvider] || { available: false, reason: 'disabled' };
    try { sessionStorage.setItem(providerStorageKey, activeProvider); } catch { /* ignore */ }

    if (config.available) {
        $('duration').min = config.min_seconds;
        $('duration').max = config.max_seconds;
        $('duration').dataset.userChanged = '0';
        $('duration').value = String(config.default_seconds || config.max_seconds);
    }
    const supportedForCurrent = usingLocalFileSource() ? rtcSupported : supported;
    if (!preserveStatus) {
        status(!config.available ? 'unavailable' : supportedForCurrent ? 'ready' : 'unsupported');
    } else {
        render();
    }
}

async function loadConfig({ preserveStatus = false } = {}) {
    try {
        let rawPayload;
        try {
            rawPayload = await api('/providers');
        } catch {
            try {
                rawPayload = await api('/status');
            } catch {
                rawPayload = await api('/config');
            }
        }
        providersState = resolveProvidersStatus(rawPayload);

        let preferred = 'xmax';
        let saved;
        try { saved = sessionStorage.getItem(providerStorageKey); } catch { /* ignore */ }
        if (providersState.availableProviders.length > 0) {
            if (saved && providersState[saved]?.available) {
                preferred = saved;
            } else if (providersState.defaultProvider && providersState[providersState.defaultProvider]?.available) {
                preferred = providersState.defaultProvider;
            } else {
                preferred = providersState.availableProviders[0];
            }
        } else if (saved && ['xmax', 'reactor', 'decart'].includes(saved)) {
            preferred = saved;
        }

        if (run) {
            activeProvider = run.provider;
            config = providersState[activeProvider] || config;
            render();
            return;
        }

        activeProvider = preferred;
        config = providersState[activeProvider] || { available: false, reason: 'disabled' };

        if (config.available) {
            $('duration').min = config.min_seconds;
            $('duration').max = config.max_seconds;
            if (!$('duration').validity.valid || $('duration').dataset.userChanged !== '1') {
                $('duration').value = String(config.default_seconds || config.max_seconds);
            }
        }
        const supportedForCurrent = usingLocalFileSource() ? rtcSupported : supported;
        if (preserveStatus && (run || camera || pendingCamera)) {
            render();
        } else {
            status(!config.available ? 'unavailable' : supportedForCurrent ? 'ready' : 'unsupported');
        }
    } catch {
        if (!preserveStatus) status('unavailable', 'request_failed');
    }
}

$('preview').addEventListener('click', openPreview);
$('form').addEventListener('submit', event => {
    event.preventDefault();
    if ($('start').disabled) return;
    if (activeProvider === 'reactor') void startReactor();
    else if (activeProvider === 'xmax') void startXmax();
    else void startDecart();
});
$('stop').addEventListener('click', () => finish());
$('apply').addEventListener('click', () => { void applyGarment(); });
$('file').addEventListener('change', refreshGarment);
$('upload-trigger')?.addEventListener('click', () => $('file').click());
$('pick-catalog')?.addEventListener('click', () => {
    const panel = document.getElementById('garment-browser-panel');
    const toggle = document.getElementById('garment-browser-toggle');
    if (panel?.classList.contains('hidden')) toggle?.click();
    (panel || toggle)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
});
$('use-selected').addEventListener('click', () => { $('file').value = ''; refreshGarment(); });
$('code-toggle')?.addEventListener('click', () => {
    const input = $('code');
    const isHidden = input.type === 'password';
    input.type = isHidden ? 'text' : 'password';
    const icon = $('code-toggle').querySelector('i');
    if (icon) icon.className = isHidden ? 'fas fa-eye-slash' : 'fas fa-eye';
});
$('flip-camera')?.addEventListener('click', () => { void flipCamera(); });
$('mirror-toggle')?.addEventListener('click', () => {
    mirrored = !mirrored;
    renderStreamsUi();
});
$('snapshot')?.addEventListener('click', captureSnapshot);
$('duration')?.addEventListener('input', () => {
    $('duration').dataset.userChanged = '1';
    render();
});
$('prompt')?.addEventListener('input', renderPresets);
$('xmax-model')?.addEventListener('change', render);
$('xmax-preset')?.addEventListener('change', () => {
    xmaxPresetSelection = $('xmax-preset')?.value || XMAX_PRESET_AUTO;
    render();
});
$('xmax-source')?.addEventListener('change', () => {
    if (run || pendingCamera) return;
    xmaxSourceMode = $('xmax-source').value || 'camera';
    clearXmaxSourceFile();
    if (xmaxSourceMode !== 'camera' && camera) {
        camera.getTracks().forEach(track => track.stop());
        camera = undefined;
        if ($('local')) $('local').srcObject = null;
    }
    if (!config?.available) {
        render();
        return;
    }
    const supportedForCurrent = usingLocalFileSource() ? rtcSupported : supported;
    status(supportedForCurrent ? 'ready' : 'unsupported');
});
$('xmax-source-btn')?.addEventListener('click', () => $('xmax-source-file')?.click());
$('xmax-source-file')?.addEventListener('change', () => {
    const file = $('xmax-source-file').files?.[0];
    if (!file) {
        clearXmaxSourceFile();
        if (config?.available) status('ready');
        else render();
        return;
    }
    const isVideo = xmaxSourceMode === 'video';
    const validType = isVideo
        ? (videoTypes.includes(file.type) || /\.(mp4|webm|mov)$/i.test(file.name))
        : (imageTypes.includes(file.type) || /\.(jpe?g|png|webp)$/i.test(file.name));
    const maxBytes = isVideo ? 50 * 1024 * 1024 : 12 * 1024 * 1024;
    if (!validType || !file.size || file.size > maxBytes) {
        clearXmaxSourceFile();
        status('ready', 'invalid_source_media');
        return;
    }
    if (xmaxSourceUrl) URL.revokeObjectURL(xmaxSourceUrl);
    detectedSourceDims = null;
    xmaxSourceFile = file;
    xmaxSourceUrl = URL.createObjectURL(file);
    status('xmaxPreviewSourceReady');
});
$('reactor-model')?.addEventListener('change', render);
$('face-restoration')?.addEventListener('change', () => {
    if ($('face-restoration')) $('face-restoration').dataset.userChanged = '1';
    if (run?.provider === 'xmax' && run.xmaxRealtime && run.xmaxLocalStream && !run.applying) {
        void applyGarment({ skipGarmentUpload: true });
    }
});
$('refresh-status')?.addEventListener('click', () => { void loadConfig(); });
$('provider-decart')?.addEventListener('click', () => selectProvider('decart'));
$('provider-reactor')?.addEventListener('click', () => selectProvider('reactor'));
$('provider-xmax')?.addEventListener('click', () => selectProvider('xmax'));
for (const id of ['code', 'consent']) $(id).addEventListener('input', render);

for (const [id, layoutKey] of [
    ['layout-dual', 'dual'],
    ['layout-remote', 'remote'],
    ['layout-pip', 'pip-overlay'],
    ['layout-local', 'local'],
]) {
    $(id)?.addEventListener('click', () => {
        stageLayout = layoutKey;
        renderStageDisplay();
    });
}
$('swap-panes')?.addEventListener('click', () => {
    stageSwapped = !stageSwapped;
    renderStageDisplay();
});
$('fit-toggle')?.addEventListener('click', () => {
    stageFit = stageFit === 'cover' ? 'contain' : 'cover';
    renderStageDisplay();
});
$('float-toggle')?.addEventListener('click', () => {
    setStageDisplayMode(stageDisplayMode === 'floating' ? 'inline' : 'floating');
});
$('float-size')?.addEventListener('click', () => {
    stageFloatSize = nextFloatingSizePreset(stageFloatSize);
    const preset = FLOATING_SIZE_PRESETS[stageFloatSize] || FLOATING_SIZE_PRESETS.md;
    if (stageFloatRect) {
        stageFloatRect = { ...stageFloatRect, width: preset.width, height: preset.height };
    }
    applyFloatingGeometry();
    renderStageDisplay();
});
$('maximize-toggle')?.addEventListener('click', () => {
    setStageDisplayMode(stageDisplayMode === 'maximized' ? 'inline' : 'maximized');
});
$('popout-toggle')?.addEventListener('click', () => { void openDocPip(); });
$('fullscreen-toggle')?.addEventListener('click', () => { void toggleStageFullscreen(); });
document.getElementById('realtime-stage-return')?.addEventListener('click', () => {
    setStageDisplayMode('inline');
});
document.getElementById('realtime-stage-backdrop')?.addEventListener('click', () => {
    if (stageDisplayMode === 'maximized') setStageDisplayMode('inline');
});
$('focus-local')?.addEventListener('click', () => focusPane('local'));
$('focus-remote')?.addEventListener('click', () => focusPane('remote'));
$('pip-local')?.addEventListener('click', () => { void togglePaneVideoPip('local'); });
$('pip-remote')?.addEventListener('click', () => { void togglePaneVideoPip('remote'); });
$('stage-apply')?.addEventListener('click', () => { void applyGarment(); });
$('stage-stop')?.addEventListener('click', () => finish());

for (const pane of ['local', 'remote']) {
    const paneEl = $(`pane-${pane}`);
    const boxEl = paneEl?.querySelector('.realtime-video-box');
    boxEl?.addEventListener('dblclick', event => {
        if (event.target instanceof Element && event.target.closest('button')) return;
        focusPane(pane);
    });
    paneEl?.addEventListener('click', event => {
        if (stageLayout !== 'pip-overlay') return;
        if (event.target instanceof Element && event.target.closest('button')) return;
        const isCornerPip = (!stageSwapped && pane === 'local') || (stageSwapped && pane === 'remote');
        if (!isCornerPip) return;
        stageSwapped = !stageSwapped;
        renderStageDisplay();
    });
}

$('stage-bar')?.addEventListener('pointerdown', event => {
    if (stageDisplayMode !== 'floating' || event.button !== 0) return;
    if (event.target instanceof Element && event.target.closest('button, a, input, select')) return;
    const stage = $('stage');
    if (!stage) return;
    const rect = stage.getBoundingClientRect();
    stageDrag = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        originLeft: rect.left,
        originTop: rect.top,
        width: rect.width,
        height: rect.height,
    };
    stage.classList.add('is-dragging');
    try { $('stage-bar').setPointerCapture(event.pointerId); } catch { /* ignore */ }
});
window.addEventListener('pointermove', event => {
    if (!stageDrag || stageDisplayMode !== 'floating') return;
    if (event.pointerId !== stageDrag.pointerId) return;
    stageFloatRect = clampFloatingRect(
        {
            left: stageDrag.originLeft + (event.clientX - stageDrag.startX),
            top: stageDrag.originTop + (event.clientY - stageDrag.startY),
            width: stageDrag.width,
            height: stageDrag.height,
        },
        currentViewport(),
        12,
    );
    applyFloatingGeometry();
});
const endStageDrag = event => {
    if (stageDrag && event?.pointerId != null && event.pointerId !== stageDrag.pointerId) return;
    const stage = $('stage');
    if (stage) stage.classList.remove('is-dragging');
    if (!stageDrag && stageDisplayMode === 'floating' && stage) {
        const rect = stage.getBoundingClientRect();
        if (rect.width >= 200 && rect.height >= 160) {
            stageFloatRect = clampFloatingRect(
                { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
                currentViewport(),
                12,
            );
        }
    }
    stageDrag = null;
};
window.addEventListener('pointerup', endStageDrag);
window.addEventListener('pointercancel', endStageDrag);
const handleViewportChange = () => {
    if (stageDisplayMode === 'floating') applyFloatingGeometry();
    if (!detectedSourceDims && !liveRemoteDims && !run) {
        if (activeProvider === 'xmax') renderXmaxOptions();
        renderStageDisplay();
    }
};
window.addEventListener('resize', handleViewportChange);
window.addEventListener('orientationchange', handleViewportChange);
window.visualViewport?.addEventListener('resize', handleViewportChange);
document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && stageDisplayMode === 'maximized' && !document.fullscreenElement) {
        setStageDisplayMode('inline');
    }
});
document.addEventListener('fullscreenchange', renderStageDisplay);

for (const evt of ['loadedmetadata', 'resize']) {
    $('local')?.addEventListener(evt, () => {
        const video = $('local');
        if (video?.videoWidth && video?.videoHeight) {
            setDetectedSourceDims(video.videoWidth, video.videoHeight);
        }
    });
    $('remote')?.addEventListener(evt, () => {
        const video = $('remote');
        if (video?.videoWidth && video?.videoHeight) {
            setLiveRemoteDims(video.videoWidth, video.videoHeight);
        }
    });
}
$('local-image')?.addEventListener('load', () => {
    const img = $('local-image');
    if (img?.naturalWidth && img?.naturalHeight) {
        setDetectedSourceDims(img.naturalWidth, img.naturalHeight);
    }
});

$('remote').addEventListener('playing', () => {
    if (!run || !$('remote').srcObject) return;
    run.firstFrameReceived = true;
    clearTimeout(run.firstFrame);
    startActiveCountdown(run);
    status('live');
});

window.addEventListener('workbench:garmentchange', event => { selected = event.detail; refreshGarment(); });
window.addEventListener('localechange', render);
window.addEventListener('pagehide', () => {
    restoreStageFromDocPip({ resetMode: false });
    if (run || camera || pendingCamera) finish();
    if (snapshotUrl) URL.revokeObjectURL(snapshotUrl);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    if (xmaxSourceUrl) URL.revokeObjectURL(xmaxSourceUrl);
});
document.addEventListener('visibilitychange', () => {
    if (document.hidden && !hasActivePipWindow() && (run || camera || pendingCamera)) finish('hiddenStop');
});

window.WorkbenchI18n.ready.then(async () => {
    try {
        const savedCode = sessionStorage.getItem(codeStorageKey);
        if (savedCode && !$('code').value) $('code').value = savedCode;
    } catch { /* ignore */ }
    refreshGarment();
    await loadConfig();
    let id;
    try { id = sessionStorage.getItem(storageKey); } catch { /* ignore */ }
    if (config?.available && /^[0-9a-f]{32}$/.test(id || '') && !run && !lastReceipt) {
        lastReceipt = { id, state: 'waiting', provider_key: activeProvider };
        render();
        void refreshReceipt(id);
    }
});
