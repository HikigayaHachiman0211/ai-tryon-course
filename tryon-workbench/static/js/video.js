import {
    parametersFor,
    defaultsFor,
    collectInput,
    bindSourceImage,
    pickDefaultVideoModel,
    adaptiveAspectRatio,
    parseAspectRatio,
} from './video-form.js?v=20261120-v5';

const $ = id => document.getElementById(id);
const root = $('section-video');
const state = { models: [], model: null, params: [], values: {}, source: '', sourceDimensions: null, manualAspectRatio: false, config: null,
    quote: null, revision: 0, busy: false, current: null, history: [], timer: null, started: 0, failures: 0, preset: 'turn' };
const PRESET_KEYS = ['turn', 'walk', 'detail', 'studio'];
const isPrimaryImageParam = spec => {
    if (!spec || !['image', 'images'].includes(spec.type)) return false;
    const preferred = state.params.find(item => ['image_url', 'start_image_url', 'first_frame_image'].includes(item.name));
    if (preferred) return spec.name === preferred.name;
    const first = state.params.find(item => ['image', 'images'].includes(item.type));
    return Boolean(first && spec.name === first.name);
};
const t = (key, values) => window.WorkbenchI18n.t(`video.${key}`, values);
const active = task => task && ['submitting', 'queued', 'processing'].includes(task.status);
let quoteTimer;
let visitorToken = '';
let pendingSubmission = null;
try {
    visitorToken = sessionStorage.getItem('tryon-video.visitor') || JSON.parse(sessionStorage.getItem('tryon_active_task_v1') || 'null')?.taskToken || '';
} catch { /* cookie sessions remain available when storage is disabled */ }

function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
}

async function api(path, body) {
    const response = await fetch(`/api/video${path}`, {
        method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin',
        headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...(visitorToken ? { 'X-Task-Token': visitorToken } : {}) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        const code = data.error?.code;
        const local = code && t(`errors.${code}`);
        const error = new Error(local && !local.startsWith('video.') ? local : (data.error?.message || data.detail || `HTTP ${response.status}`));
        error.status = response.status;
        throw error;
    }
    return data;
}

function showError(error) {
    $('video-error').hidden = !error;
    $('video-error').textContent = error?.message || String(error || '');
}

function snapshot() {
    if (!state.model) throw new Error(t('chooseModel'));
    return { model: state.model.slug, provider: $('video-provider').value, input: collectInput(state.params, state.values) };
}

function syncButtons() {
    $('video-generate').disabled = state.busy || Boolean(pendingSubmission) || !state.quote || !state.config?.enabled || !state.config?.configured;
    $('video-quote-btn').disabled = state.busy || !state.model;
    $('video-refresh-models').disabled = state.busy;
}

function persistPending(value) {
    pendingSubmission = value;
    try {
        if (value) sessionStorage.setItem('tryon-video.pending', JSON.stringify(value));
        else sessionStorage.removeItem('tryon-video.pending');
    } catch { /* memory still protects the current page from duplicate submission */ }
}

function renderConnection() {
    const connection = $('video-connection');
    connection.hidden = Boolean(state.config?.enabled && state.config?.configured && !state.config?.sandbox);
    connection.textContent = t(!state.config ? 'loading' : state.config.sandbox ? 'sandbox' : 'notConfigured');
}

function syncStageAspectRatio() {
    const stage = $('video-empty')?.parentElement;
    if (!stage) return;
    const player = $('video-player');
    if (player && !player.hidden && player.videoWidth > 0 && player.videoHeight > 0) {
        stage.style.aspectRatio = `${player.videoWidth} / ${player.videoHeight}`;
        return;
    }
    const chosen = String(state.values?.aspect_ratio || '').trim();
    if (parseAspectRatio(chosen)) {
        stage.style.aspectRatio = chosen.replace(':', ' / ');
    } else if (state.sourceDimensions?.width > 0 && state.sourceDimensions?.height > 0) {
        stage.style.aspectRatio = `${state.sourceDimensions.width} / ${state.sourceDimensions.height}`;
    } else {
        stage.style.aspectRatio = '3 / 4';
    }
}

function applySourceAspectRatio(force = false) {
    if (!state.sourceDimensions?.width || !state.sourceDimensions?.height) return false;
    if (state.manualAspectRatio && !force) return false;
    const adapted = adaptiveAspectRatio(state.params, state.sourceDimensions.width, state.sourceDimensions.height);
    if (!adapted) return false;
    const changedRatio = state.values.aspect_ratio !== adapted;
    state.values.aspect_ratio = adapted;
    return changedRatio;
}

function changed() {
    state.revision++;
    state.quote = null;
    $('video-quote-lines').replaceChildren(node('span', t('quoteChanged'), 'video-help'));
    syncStageAspectRatio();
    syncButtons();
    clearTimeout(quoteTimer);
    try {
        $('video-request-preview').textContent = JSON.stringify(snapshot(), null, 2);
        quoteTimer = setTimeout(() => quote(false), 800);
    } catch {
        $('video-request-preview').textContent = t('completeFields');
    }
}

function fieldHelp(spec) {
    const parts = [spec.description || ''];
    if (spec.name === 'aspect_ratio' && state.sourceDimensions?.width > 0 && state.sourceDimensions?.height > 0 && !state.manualAspectRatio && state.values.aspect_ratio) {
        parts.push(t('autoAspectHint', {
            width: state.sourceDimensions.width,
            height: state.sourceDimensions.height,
            ratio: state.values.aspect_ratio,
        }));
    }
    const help = t(`fieldHelp.${spec.name}`);
    if (!help.startsWith('video.')) parts.push(help);
    if (spec.min !== undefined || spec.max !== undefined) parts.push(`${t('range')}: ${spec.min ?? '…'} – ${spec.max ?? '…'}`);
    if (spec.default !== undefined) parts.push(`${t('default')}: ${String(spec.default)}`);
    if (spec.maxItems) parts.push(`${t('maxItems')}: ${spec.maxItems}`);
    if (spec.maxLength) parts.push(`${t('maxLength')}: ${spec.maxLength}`);
    return parts.filter(Boolean).join(' · ');
}

function renderField(spec) {
    const wrap = node('div', undefined, `video-field${['text', 'images', 'videos', 'audios'].includes(spec.type) || spec.name === 'prompt' ? ' wide' : ''}`);
    const translated = t(`fields.${spec.name}`);
    const label = node('label', `${translated.startsWith('video.') ? (spec.label || spec.name) : translated}${spec.required ? ' *' : ''} `);
    label.htmlFor = `video-input-${spec.name}`;
    label.append(node('code', spec.name));
    wrap.append(label);
    let input;
    const value = state.values[spec.name];
    if (spec.options?.length || spec.type === 'boolean') {
        input = node('select');
        const options = spec.options?.length ? spec.options : [true, false];
        const blank = node('option', t('modelDefault'));
        blank.value = '';
        input.append(blank);
        options.forEach((option, i) => {
            const item = node('option', typeof option === 'boolean' ? t(option ? 'on' : 'off') : String(option));
            item.value = String(i);
            if (option === value) item.selected = true;
            input.append(item);
        });
        input.addEventListener('change', () => {
            state.values[spec.name] = input.value === '' ? undefined : options[Number(input.value)];
            if (spec.name === 'aspect_ratio') {
                state.manualAspectRatio = true;
                const helpEl = $(`video-help-${spec.name}`);
                if (helpEl) helpEl.textContent = fieldHelp(spec);
            }
            changed();
        });
    } else {
        input = node(['text', 'images', 'videos', 'audios'].includes(spec.type) ? 'textarea' : 'input');
        if (input.tagName === 'TEXTAREA') input.rows = spec.name === 'prompt' ? 4 : 3;
        else input.type = ['number', 'integer'].includes(spec.type) ? 'number' : 'text';
        if (input.type === 'number') {
            input.step = spec.type === 'integer' ? '1' : 'any';
            if (spec.min !== undefined) input.min = spec.min;
            if (spec.max !== undefined) input.max = spec.max;
        }
        input.value = Array.isArray(value) ? value.join('\n') : (value ?? '');
        if (spec.maxLength) input.maxLength = spec.maxLength;
        if (['images', 'videos', 'audios'].includes(spec.type)) input.placeholder = t('urlsPerLine');
        if (['image', 'video', 'audio'].includes(spec.type)) input.placeholder = 'https://…';
        input.addEventListener('input', () => {
            state.values[spec.name] = input.value;
            if (spec.name === 'prompt') {
                const matched = PRESET_KEYS.find(key => t(`prompts.${key}`) === input.value) || '';
                if (state.preset !== matched) {
                    state.preset = matched;
                    renderPresets();
                }
            } else if (isPrimaryImageParam(spec)) {
                const nextUrl = String(input.value || '').split('\n').map(s => s.trim()).find(Boolean) || '';
                if (nextUrl !== state.source) {
                    state.source = nextUrl;
                    state.sourceDimensions = null;
                    state.manualAspectRatio = false;
                    renderSource();
                }
            }
            changed();
        });
    }
    input.id = `video-input-${spec.name}`;
    input.name = spec.name;
    input.required = Boolean(spec.required);
    input.setAttribute('aria-describedby', `video-help-${spec.name}`);
    wrap.append(input);
    if (['image', 'images'].includes(spec.type)) {
        const uploadRow = node('div', undefined, 'video-upload-row');
        const uploadTrigger = node('button', undefined, 'glass-btn small-btn video-file-btn');
        uploadTrigger.type = 'button';
        const uploadIcon = node('i', undefined, 'fas fa-arrow-up-from-bracket');
        uploadIcon.setAttribute('aria-hidden', 'true');
        uploadTrigger.append(uploadIcon, document.createTextNode(` ${t('upload')}`));
        const fileStatus = node('span', '', 'video-file-name');
        const filled = Array.isArray(value) ? value.filter(Boolean) : (value ? [String(value)] : []);
        if (filled.length) {
            const first = String(filled[0]).split('?')[0].split('/').pop() || filled[0];
            fileStatus.textContent = filled.length > 1 ? `${first} (+${filled.length - 1})` : first;
        }
        const upload = node('input', undefined, 'video-param-upload');
        upload.type = 'file';
        upload.accept = 'image/jpeg,image/png,image/webp';
        upload.multiple = spec.type === 'images';
        upload.hidden = true;
        upload.setAttribute('aria-label', `${t('upload')} · ${spec.name}`);
        uploadTrigger.addEventListener('click', () => upload.click());
        upload.addEventListener('change', async () => {
            try {
                const files = Array.from(upload.files || []);
                if (spec.maxItems && files.length > spec.maxItems) throw new Error(`${spec.name}: ${t('maxItems')} ${spec.maxItems}`);
                if (files.length) fileStatus.textContent = files.map(file => file.name).join(', ');
                const urls = [];
                for (const file of files) urls.push(await uploadImage(file));
                if (!urls.length) return;
                if (isPrimaryImageParam(spec) || !state.source) {
                    useSource(urls[0]);
                } else {
                    state.values[spec.name] = spec.type === 'images' ? urls : urls[0];
                    renderFields(); renderSource(); changed();
                }
            } catch (error) { showError(error); }
        });
        uploadRow.append(uploadTrigger, fileStatus, upload);
        wrap.append(uploadRow);
    }
    const help = node('small', fieldHelp(spec));
    help.id = `video-help-${spec.name}`;
    wrap.append(help);
    return wrap;
}

function renderFields() {
    $('video-prompt-fields').replaceChildren();
    $('video-parameter-fields').replaceChildren();
    for (const spec of state.params) {
        (spec.name === 'prompt' ? $('video-prompt-fields') : $('video-parameter-fields')).append(renderField(spec));
    }
}

function renderPresets() {
    $('video-presets').replaceChildren();
    for (const preset of PRESET_KEYS) {
        const isActive = state.preset === preset;
        const button = node('button', t(`presets.${preset}`), `video-preset${isActive ? ' active' : ''}`);
        button.type = 'button';
        button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        button.addEventListener('click', () => {
            if (!state.params.some(spec => spec.name === 'prompt')) return;
            state.preset = preset;
            state.values.prompt = t(`prompts.${preset}`);
            renderPresets(); renderFields(); changed();
        });
        $('video-presets').append(button);
    }
}

function renderSource() {
    const preview = $('video-source-preview');
    preview.hidden = !state.source;
    $('video-source-icon').hidden = Boolean(state.source);
    if (state.source) preview.src = state.source;
    else preview.removeAttribute('src');
    const supportsImage = state.params.some(spec => ['image', 'images'].includes(spec.type));
    $('video-upload-trigger').disabled = !supportsImage;
    $('video-use-result').disabled = !supportsImage;
    $('video-source-help').textContent = t(supportsImage ? 'sourceHelp' : 'textOnly');
}

function chooseProvider() {
    const prompt = state.values.prompt;
    state.params = parametersFor(state.model, $('video-provider').value);
    state.values = defaultsFor(state.params);
    if (state.params.some(spec => spec.name === 'prompt')) {
        if (prompt) {
            state.values.prompt = prompt;
        } else {
            state.preset = state.preset || 'turn';
            state.values.prompt = t(`prompts.${state.preset}`);
        }
    }
    if (state.source) {
        try {
            state.values = bindSourceImage(state.params, state.values, state.source);
            applySourceAspectRatio(false);
        } catch {
            state.source = '';
            state.sourceDimensions = null;
        }
    }
    renderPresets(); renderFields(); renderSource(); changed(); showError(null);
}

function chooseModel() {
    state.model = state.models.find(model => model.slug === $('video-model').value) || null;
    $('video-provider').replaceChildren();
    if (!state.model) { state.params = []; syncButtons(); return; }
    const automatic = node('option', state.model.provider ? `${t('pinned')}: ${state.model.provider}` : t('autoRoute'));
    automatic.value = '';
    $('video-provider').append(automatic);
    for (const provider of state.model.providers || []) {
        const option = node('option', provider.providerName || provider.provider);
        option.value = provider.provider;
        $('video-provider').append(option);
    }
    $('video-provider').disabled = !state.model.providers?.length;
    $('video-model-info').textContent = [state.model.vendor, state.model.name, state.model.description].filter(Boolean).join(' · ');
    chooseProvider();
}

async function loadModels(refresh = false) {
    const selected = $('video-model').value;
    $('video-model').disabled = true;
    try {
        const result = await api(`/models${refresh ? '?refresh=true' : ''}`);
        state.models = result.data;
        $('video-model').replaceChildren();
        for (const model of state.models) {
            const option = node('option', `${model.vendor ? model.vendor + ' · ' : ''}${model.name || model.slug}`);
            option.value = model.slug;
            $('video-model').append(option);
        }
        const preferred = pickDefaultVideoModel(state.models, selected);
        if (preferred) $('video-model').value = preferred.slug;
        else throw new Error(t('noModels'));
        $('video-model').disabled = false;
        chooseModel();
    } catch (error) { showError(error); }
}

async function quote(explicit = true) {
    const revision = state.revision;
    try {
        const body = snapshot();
        const result = await api('/quote', body);
        if (revision !== state.revision) return;
        state.quote = result.providers?.length ? { result, body } : null;
        renderQuote();
        for (const item of result.unavailable || []) $('video-quote-lines').append(node('small', `${item.provider}: ${item.reason || item.message || t('unavailable')}`, 'video-help'));
        if (!state.quote) $('video-quote-lines').append(node('span', t('noQuote'), 'video-help'));
        if (explicit) showError(null);
    } catch (error) {
        if (revision === state.revision) {
            state.quote = null;
            $('video-quote-lines').replaceChildren(node('span', error.message, 'video-help'));
            if (explicit) showError(error);
        }
    } finally { syncButtons(); }
}

function renderQuote() {
    $('video-quote-lines').replaceChildren();
    if (!state.quote) return;
    for (const [index, provider] of state.quote.result.providers.entries()) {
        const row = node('div', undefined, 'video-quote-line');
        row.append(node('span', `${provider.provider}${!index && !state.quote.body.provider ? ' · ' + t('firstRoute') : ''}`),
            node('strong', `${money(provider.price_usd)}${provider.credits != null ? ` · ${provider.credits} ${t('credits')}` : ''}`));
        $('video-quote-lines').append(row);
    }
}

function money(value) {
    return value == null ? '—' : new Intl.NumberFormat(window.WorkbenchI18n.locale, { style: 'currency', currency: 'USD', maximumFractionDigits: 4 }).format(Number(value));
}

async function uploadImage(file) {
    if (file.size > 15 * 1024 * 1024) throw new Error(t('imageTooLarge'));
    const body = new FormData();
    body.append('file', file);
    const response = await fetch('/upload/model', { method: 'POST', body, credentials: 'same-origin', headers: visitorToken ? { 'X-Task-Token': visitorToken } : {} });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || data.detail || t('uploadFailed'));
    return data.url || data.cloud_url;
}

function useSource(url, dimensions = null) {
    try {
        state.manualAspectRatio = false;
        state.sourceDimensions = (dimensions?.width > 0 && dimensions?.height > 0)
            ? { width: dimensions.width, height: dimensions.height }
            : null;
        state.values = bindSourceImage(state.params, state.values, url);
        state.source = url;
        applySourceAspectRatio(true);
        renderFields(); renderSource(); changed(); showError(null);
    } catch { showError(new Error(t('textOnly'))); }
}

function useResult() {
    const image = $('result-img');
    if (!image?.getAttribute('src') || image.classList.contains('hidden')) { showError(new Error(t('noResult'))); return; }
    useSource(image.getAttribute('src'), { width: image.naturalWidth, height: image.naturalHeight });
    root.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderTask(task) {
    state.current = task;
    const statusEl = $('video-task-status');
    statusEl.textContent = t(`status.${task.status}`);
    statusEl.dataset.status = task.status || 'processing';
    $('video-task-cost').textContent = task.price_usd != null ? `${t('actual')}: ${money(task.price_usd)}` : '';
    $('video-task-meta').textContent = `${task.model} · ${task.provider || t('autoRoute')} · ${task.upstream_id || task.id}`;
    const outputs = task.outputs || [];
    const player = $('video-player');
    player.hidden = !outputs.length;
    $('video-empty').hidden = Boolean(outputs.length);
    if (outputs.length && player.getAttribute('src') !== outputs[0]) player.src = outputs[0];
    if (!outputs.length) { player.pause(); player.removeAttribute('src'); }
    $('video-output-links').replaceChildren();
    outputs.forEach((url, index) => {
        const link = node('a', `${t('download')} ${outputs.length > 1 ? index + 1 : ''}`, 'glass-btn small-btn');
        link.href = task.download_urls?.[index] || `/api/video/tasks/${encodeURIComponent(task.id)}/download?index=${index}`;
        link.target = '_blank'; link.rel = 'noopener noreferrer';
        $('video-output-links').append(link);
        if (outputs.length > 1) {
            const play = node('button', `${t('play')} ${index + 1}`, 'glass-btn small-btn');
            play.type = 'button'; play.addEventListener('click', () => { player.src = url; });
            $('video-output-links').append(play);
        }
    });
    $('video-cancel').hidden = !['queued', 'processing'].includes(task.status);
    $('video-resume').hidden = !active(task);
    $('video-resume').textContent = t('resume');
    const unknown = task.status === 'unknown';
    $('video-task-note').textContent = unknown ? t('unknownHelp') : (task.error ? `${t(task.error === 'Canceled by user' ? 'canceled' : 'failedHelp')}${task.error === 'Canceled by user' ? '' : ': ' + task.error}` : t('resultHelp'));
    const index = state.history.findIndex(item => item.id === task.id);
    if (index < 0) state.history.unshift(task); else state.history[index] = task;
    renderHistory();
}

function renderHistory() {
    $('video-history-list').replaceChildren();
    if (!state.history.length) $('video-history-list').append(node('p', t('noHistory'), 'video-help'));
    for (const task of state.history.slice(0, 20)) {
        const row = node('div', undefined, 'video-history-item');
        const button = node('button', task.model);
        button.type = 'button';
        button.addEventListener('click', () => { stopPoll(); renderTask(task); if (active(task)) startPoll(); });
        const statusBadge = node('span', t(`status.${task.status}`), 'video-history-status');
        statusBadge.dataset.status = task.status || 'processing';
        row.append(button, statusBadge);
        $('video-history-list').append(row);
    }
}

function stopPoll() { clearTimeout(state.timer); state.timer = null; }

function startPoll() {
    stopPoll(); state.started = Date.now(); state.failures = 0;
    state.timer = setTimeout(pollTask, 4000);
}

async function pollTask() {
    const taskId = state.current?.id;
    if (!taskId) return;
    try {
        const task = await api(`/tasks/${encodeURIComponent(taskId)}`);
        if (state.current?.id !== taskId) return;
        state.failures = 0;
        renderTask(task);
        if (!active(task)) return;
    } catch (error) {
        if (state.current?.id !== taskId) return;
        state.failures++;
        if ([401, 403, 404, 409, 503].includes(error.status) || state.failures >= 6) { showError(error); $('video-resume').hidden = false; return; }
    }
    if (Date.now() - state.started > 30 * 60 * 1000) { $('video-task-note').textContent = t('pollTimeout'); return; }
    state.timer = setTimeout(pollTask, Math.min(4000 * 2 ** state.failures, 30000));
}

async function submit(event) {
    event.preventDefault();
    if (state.busy || pendingSubmission || !state.quote) return;
    const current = snapshot();
    if (JSON.stringify(current) !== JSON.stringify(state.quote.body)) { changed(); return; }
    await sendSubmission({ ...current, idempotency_key: crypto.randomUUID() });
}

async function sendSubmission(body) {
    if (state.busy) return;
    state.busy = true;
    persistPending({ key: body.idempotency_key, body });
    syncButtons(); showError(null);
    try {
        const task = await api('/tasks', body);
        persistPending(null);
        stopPoll(); renderTask(task);
        if (window.innerWidth <= 900) {
            document.querySelector('.video-stage')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
        if (active(task)) startPoll();
    } catch (error) {
        showError(error);
        const recovered = await recoverSubmission(body.idempotency_key);
        if (!recovered && error.status && error.status < 500 && error.status !== 408) {
            persistPending(null);
            $('video-resume').hidden = !active(state.current);
            $('video-resume').textContent = t('resume');
        }
    } finally { state.busy = false; syncButtons(); }
}

async function recoverSubmission(key) {
    try {
        const task = await api(`/submissions/${encodeURIComponent(key)}`);
        persistPending(null);
        stopPoll();
        renderTask(task);
        if (active(task)) startPoll();
        return true;
    } catch {
        $('video-task-note').textContent = t('submissionLost');
        $('video-resume').hidden = false;
        $('video-resume').textContent = t(pendingSubmission?.body ? 'retrySubmission' : 'resume');
        return false;
    }
}

async function init() {
    await window.WorkbenchI18n.ready;
    renderPresets(); renderHistory();
    $('video-task-status').textContent = t('ready');
    $('video-task-status').dataset.status = 'ready';
    $('video-task-note').textContent = t('resultHelp');
    renderConnection();
    $('video-model').addEventListener('change', chooseModel);
    $('video-provider').addEventListener('change', chooseProvider);
    $('video-reset').addEventListener('click', () => { state.values = {}; state.manualAspectRatio = false; state.preset = 'turn'; chooseProvider(); });
    $('video-source-preview').addEventListener('load', () => {
        const img = $('video-source-preview');
        if (!state.source || !img?.naturalWidth || !img?.naturalHeight) return;
        state.sourceDimensions = { width: img.naturalWidth, height: img.naturalHeight };
        if (applySourceAspectRatio(false)) {
            renderFields();
            changed();
        } else {
            const spec = state.params.find(item => item.name === 'aspect_ratio');
            const helpEl = $('video-help-aspect_ratio');
            if (spec && helpEl) helpEl.textContent = fieldHelp(spec);
            syncStageAspectRatio();
        }
    });
    $('video-player').addEventListener('loadedmetadata', syncStageAspectRatio);
    $('video-refresh-models').addEventListener('click', () => loadModels(true));
    $('video-quote-btn').addEventListener('click', () => quote());
    $('video-use-result').addEventListener('click', useResult);
    $('video-from-result').addEventListener('click', useResult);
    $('video-upload-trigger').addEventListener('click', () => $('video-upload').click());
    $('video-upload').addEventListener('change', async event => {
        try { if (event.target.files[0]) useSource(await uploadImage(event.target.files[0])); }
        catch (error) { showError(error); }
        event.target.value = '';
    });
    $('video-form').addEventListener('submit', submit);
    $('video-resume').addEventListener('click', () => {
        if (pendingSubmission?.body) { void sendSubmission(pendingSubmission.body); }
        else if (pendingSubmission?.key) { void recoverSubmission(pendingSubmission.key); }
        else startPoll();
    });
    $('video-cancel').addEventListener('click', async () => {
        const taskId = state.current?.id;
        $('video-cancel').disabled = true;
        try {
            const task = await api(`/tasks/${encodeURIComponent(taskId)}/cancel`, {});
            if (state.current?.id === taskId) { stopPoll(); renderTask(task); if (active(task)) startPoll(); }
        } catch (error) { showError(error); }
        finally { $('video-cancel').disabled = false; }
    });
    window.addEventListener('pagehide', stopPoll);
    window.addEventListener('pageshow', () => { if (active(state.current)) startPoll(); });
    window.addEventListener('localechange', () => {
        const hadValidQuote = Boolean(state.quote && state.model && JSON.stringify(state.quote.body) === JSON.stringify(snapshot()));
        if (state.preset && state.params.some(spec => spec.name === 'prompt')) {
            state.values.prompt = t(`prompts.${state.preset}`);
        }
        renderFields(); renderPresets(); renderSource(); renderHistory();
        renderConnection(); renderQuote();
        if (state.model) {
            try {
                const updated = snapshot();
                $('video-request-preview').textContent = JSON.stringify(updated, null, 2);
                if (hadValidQuote && state.quote) state.quote.body = updated;
            } catch {
                $('video-request-preview').textContent = t('completeFields');
            }
        }
        const route = $('video-provider').options[0];
        if (route) route.textContent = state.model?.provider ? `${t('pinned')}: ${state.model.provider}` : t('autoRoute');
        if (state.current) renderTask(state.current);
        else {
            $('video-task-status').textContent = t('ready');
            $('video-task-status').dataset.status = 'ready';
            $('video-task-note').textContent = t('resultHelp');
        }
    });
    try {
        state.config = await api('/config');
        visitorToken = state.config.task_token || visitorToken;
        try { if (visitorToken) sessionStorage.setItem('tryon-video.visitor', visitorToken); } catch { /* private browsing */ }
        renderConnection();
        await loadModels();
        const history = await api('/tasks');
        state.history = history.data;
        renderHistory();
        try {
            const saved = sessionStorage.getItem('tryon-video.pending');
            if (saved) pendingSubmission = JSON.parse(saved);
        } catch { /* storage may be disabled */ }
        if (pendingSubmission?.key) await recoverSubmission(pendingSubmission.key);
        else if (state.history.length) { renderTask(state.history[0]); if (active(state.current)) startPoll(); }
        syncButtons();
    } catch (error) { showError(error); $('video-connection').textContent = t('loadFailed'); }
}

if (root) init();
