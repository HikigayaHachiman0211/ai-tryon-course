(function (global) {
  'use strict';

  var SUPPORTED = ['zh-CN', 'en', 'ja'];
  var DEFAULT = 'zh-CN';
  var STORAGE_KEY = 'ai-tryon.workbench.locale';
  var locale = DEFAULT;
  var bundles = {};
  var sourceToKey = {};
  var applying = false;
  var textSources = new WeakMap();
  var attributeSources = new WeakMap();
  var ignoredSelectors = ['#notification-container', '#garment-grid', '#errorlog-sidebar-list', '#error-log-list', 'pre', 'textarea', 'input'];

  function normalize(input) {
    if (!input) return null;
    var value = String(input).trim().toLowerCase().replace('_', '-');
    if (value === 'zh' || value === 'zh-cn' || value === 'zh-hans' || value.indexOf('zh-hans-') === 0) return 'zh-CN';
    if (value === 'en' || value.indexOf('en-') === 0) return 'en';
    if (value === 'ja' || value.indexOf('ja-') === 0) return 'ja';
    return null;
  }

  function readStorage() {
    try { return global.localStorage.getItem(STORAGE_KEY); } catch (_) { return null; }
  }

  function writeStorage(value) {
    try { global.localStorage.setItem(STORAGE_KEY, value); } catch (_) { /* privacy mode */ }
  }

  function detect(explicit) {
    return normalize(explicit) || normalize(new URLSearchParams(global.location.search).get('lang')) || normalize(readStorage()) || normalize(global.navigator.language) || DEFAULT;
  }

  function getPath(bundle, key) {
    return String(key || '').split('.').reduce(function (value, part) {
      return value && typeof value === 'object' ? value[part] : undefined;
    }, bundle);
  }

  function interpolate(value, params) {
    return String(value == null ? '' : value).replace(/\{\{\s*([\w.-]+)\s*\}\}/g, function (_, name) {
      return params && params[name] != null ? String(params[name]) : _;
    });
  }

  function t(key, params) {
    var value = getPath(bundles[locale], key);
    if (value == null) value = getPath(bundles[DEFAULT], key);
    if (value == null) value = key;
    return interpolate(value, params || {});
  }

  function inIgnored(node, attributes) {
    var element = node && (node.nodeType === 1 ? node : node.parentElement);
    if (!element || !element.closest) return false;
    return ignoredSelectors.some(function (selector) {
      return !(attributes && (selector === 'input' || selector === 'textarea')) && element.closest(selector);
    });
  }

  function translateSource(source) {
    var key = sourceToKey[source];
    if (key) return getPath(bundles[locale], 'legacy.' + key) || source;
    return source;
  }

  function applyTextNode(node) {
    if (!node || !node.nodeValue || inIgnored(node) || node.parentElement?.closest('[data-i18n]')) return;
    var original = textSources.get(node) || node.nodeValue;
    var leading = (original.match(/^\s*/) || [''])[0];
    var trailing = (original.match(/\s*$/) || [''])[0];
    var core = original.trim();
    if (!core) return;
    textSources.set(node, original);
    var translated = leading + translateSource(core) + trailing;
    if (node.nodeValue !== translated) node.nodeValue = translated;
  }

  function applyAttributes(root) {
    var nodes = root.querySelectorAll ? root.querySelectorAll('[data-i18n], [data-i18n-placeholder], [data-i18n-title], [data-i18n-aria-label], [data-i18n-alt], [title], [placeholder], [aria-label], [alt]') : [];
    Array.prototype.forEach.call(nodes, function (element) {
      if (inIgnored(element, true)) return;
      ['data-i18n', 'data-i18n-placeholder', 'data-i18n-title', 'data-i18n-aria-label', 'data-i18n-alt'].forEach(function (attribute) {
        var key = element.getAttribute(attribute);
        if (!key) return;
        var target = attribute === 'data-i18n-placeholder' ? 'placeholder' : attribute === 'data-i18n-title' ? 'title' : attribute === 'data-i18n-aria-label' ? 'aria-label' : attribute === 'data-i18n-alt' ? 'alt' : null;
        var translated = t(key);
        if (target && element.getAttribute(target) !== translated) element.setAttribute(target, translated);
        else if (!target && element.textContent !== translated) element.textContent = translated;
      });
      ['title', 'placeholder', 'aria-label', 'alt'].forEach(function (attribute) {
        var value = element.getAttribute(attribute);
        if (!value || element.hasAttribute('data-i18n-' + attribute)) return;
        var originals = attributeSources.get(element) || {};
        if (!Object.prototype.hasOwnProperty.call(originals, attribute)) originals[attribute] = value;
        attributeSources.set(element, originals);
        if (sourceToKey[originals[attribute]]) {
          var translated = translateSource(originals[attribute]);
          if (value !== translated) element.setAttribute(attribute, translated);
        }
      });
    });
  }

  function apply(root) {
    if (!root || applying) return;
    applying = true;
    try {
      applyAttributes(root);
      var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      var node;
      while ((node = walker.nextNode())) applyTextNode(node);
    } finally {
      applying = false;
    }
  }

  function updateMetadata() {
    document.documentElement.lang = locale;
    var title = document.querySelector('title[data-i18n]');
    document.title = t(title ? title.getAttribute('data-i18n') : 'meta.title');
    var description = document.querySelector('meta[name="description"]');
    if (description) description.setAttribute('content', t('meta.description'));
  }

  function load(next) {
    var target = normalize(next) || DEFAULT;
    if (bundles[target]) return Promise.resolve(bundles[target]);
    return fetch('/static/i18n/' + target + '.json', { cache: 'no-store' })
      .then(function (response) { if (!response.ok) throw new Error('locale resource ' + response.status); return response.json(); })
      .then(function (data) { bundles[target] = data; return data; })
      .catch(function (error) {
        console.warn('[workbench-i18n] locale resource unavailable', target, error && error.name);
        if (!bundles[target]) bundles[target] = bundles[DEFAULT] || { meta: { title: 'AI Down Jacket Try-On Workbench', description: '' }, fallback: { untranslated: '' }, legacy: {} };
        return bundles[target];
      });
  }

  function setLocale(next) {
    var target = normalize(next) || DEFAULT;
    return load(target).then(function () {
      locale = target;
      writeStorage(locale);
      var url = new URL(global.location.href);
      url.searchParams.set('lang', locale);
      global.history.replaceState({}, '', url.pathname + url.search + url.hash);
      updateMetadata();
      apply(document.body);
      var switcher = document.getElementById('workbench-locale-switcher');
      if (switcher) switcher.value = locale;
      global.dispatchEvent(new CustomEvent('localechange', { detail: { locale: locale } }));
      return locale;
    });
  }

  function formatCurrency(value) {
    if (value == null || Number.isNaN(Number(value))) return '—';
    return new Intl.NumberFormat(locale, { style: 'currency', currency: 'CNY', minimumFractionDigits: 2 }).format(Number(value));
  }
  function formatNumber(value) { return new Intl.NumberFormat(locale).format(Number(value || 0)); }
  function formatDate(value) {
    var date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value || '—') : new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai' }).format(date);
  }
  function formatRelative(value, unit) { return new Intl.RelativeTimeFormat(locale, { numeric: 'auto' }).format(value, unit); }

  var ready = Promise.resolve().then(function () {
    return load(DEFAULT).then(function () {
      sourceToKey = Object.keys(bundles[DEFAULT].legacy || {}).reduce(function (result, key) {
        result[bundles[DEFAULT].legacy[key]] = key;
        return result;
      }, {});
      return load(detect()).then(function () { return setLocale(detect()); });
    });
  });

  global.addEventListener('DOMContentLoaded', function () { ready.then(function () { apply(document.body); }); });
  global.addEventListener('localechange', function () { if (!applying) apply(document.body); });
  if (global.MutationObserver) new MutationObserver(function () { if (!applying) apply(document.body); }).observe(document.documentElement, { childList: true, subtree: true });
  global.addEventListener('DOMContentLoaded', function () {
    var switcher = document.getElementById('workbench-locale-switcher');
    if (switcher) {
      ready.then(function () { switcher.value = locale; });
      switcher.addEventListener('change', function () { setLocale(switcher.value); });
    }
  });

  global.WorkbenchI18n = {
    SUPPORTED_LOCALES: SUPPORTED,
    DEFAULT_LOCALE: DEFAULT,
    get locale() { return locale; },
    normalize: normalize,
    detect: detect,
    load: load,
    ready: ready,
    t: t,
    setLocale: setLocale,
    apply: apply,
    formatCurrency: formatCurrency,
    formatNumber: formatNumber,
    formatDate: formatDate,
    formatRelative: formatRelative,
  };
})(window);
