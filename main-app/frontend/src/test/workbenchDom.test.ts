/// <reference types="node" />
import { test } from 'vitest';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const { JSDOM } = createRequire(import.meta.url)('jsdom');
const workbench = path.resolve(process.cwd(), '../../tryon-workbench');
const appSource = fs.readFileSync(path.join(workbench, 'static/js/script.js'), 'utf8');
const escape = appSource.slice(appSource.indexOf('function escapeHtml('), appSource.indexOf('\n    }', appSource.indexOf('function escapeHtml(')) + 6);
const render = appSource.slice(appSource.indexOf('function renderErrors()'), appSource.indexOf('    async function refreshErrors()'));

test('workbench error text and identifiers cannot inject markup', () => {
  const dom = new JSDOM('<div id="sidebar"></div><div id="panel"></div>', { runScripts: 'outside-only' });
  const { window } = dom;
  window.state = { errors: [{ id: 'id" onmouseover="bad', time: '<img src=x>', context: '<b>context</b>', message: '<img data-injected src=x onerror=bad>', analysis: '<svg onload=bad>' }], errorAnalyzing: new Set() };
  window.el = { errorSidebarList: window.document.querySelector('#sidebar'), errorPanelList: window.document.querySelector('#panel') };
  window.uiText = (key: string) => key;
  window.analyzeErrorItem = () => {};
  window.eval(`${escape}\n${render}\nrenderErrors();`);
  assert.equal(window.document.querySelectorAll('img, b, svg, [onmouseover]').length, 0);
  assert.equal(window.document.querySelectorAll('[data-analyze-error]').length, 2);
  assert.match(window.el.errorSidebarList.textContent, /<img data-injected/);
  assert.equal(window.el.errorSidebarList.querySelector('button').getAttribute('data-analyze-error'), 'id" onmouseover="bad');
  dom.window.close();
});

test('standalone workbench error log renders external text as text', async () => {
  const html = fs.readFileSync(path.join(workbench, 'static/error-log.html'), 'utf8');
  const script = html.slice(html.indexOf('const listEl ='), html.indexOf("        document.getElementById('refresh')"));
  const dom = new JSDOM('<div id="list"></div><span id="total"></span>', { runScripts: 'outside-only' });
  dom.window.WorkbenchI18n = { locale: 'en', t: (key: string) => key };
  dom.window.fetch = async () => ({ json: async () => ({ errors: [{ time: '<b>time</b>', context: '<b>context</b>', message: '<img src=x onerror=bad>', detail: '<svg>', analysis: '<b>analysis</b>' }] }) });
  await dom.window.eval(`${script}\nload();`);
  assert.equal(dom.window.document.querySelectorAll('b, img, svg').length, 0);
  assert.match(dom.window.document.querySelector('#list').textContent, /<img src=x/);
  dom.window.close();
});

test('workbench translations settle and attributes switch without changing input', async () => {
  const source = fs.readFileSync(path.join(workbench, 'static/js/i18n.js'), 'utf8');
  const bundles: Record<string, { legacy: { generate: string } }> = Object.fromEntries(['zh-CN', 'en', 'ja'].map(locale => [locale, JSON.parse(fs.readFileSync(path.join(workbench, `static/i18n/${locale}.json`), 'utf8'))]));
  const dom = new JSDOM('<html><body><span id="explicit" data-i18n="legacy.generate"></span><button id="button"></button><input id="input" value="untouched"><input id="explicit-input" value="kept" data-i18n-placeholder="legacy.generate" data-i18n-aria-label="legacy.generate"></body></html>', { url: 'https://test.invalid/?lang=zh-CN', runScripts: 'outside-only' });
  const { window } = dom;
  window.fetch = async (url: string) => ({ ok: true, json: async () => bundles[String(url).split('/').at(-1)!.replace('.json', '')] });
  const sourceText = bundles['zh-CN'].legacy.generate;
  window.document.querySelector('#button').title = sourceText;
  window.document.querySelector('#button').setAttribute('aria-label', sourceText);
  window.document.querySelector('#input').placeholder = sourceText;
  const RealObserver = window.MutationObserver;
  let callbacks = 0;
  const observation: { current: { disconnect: () => void } | null } = { current: null };
  window.MutationObserver = class extends RealObserver {
    constructor(callback: (changes: unknown, observer: { disconnect: () => void }) => void) {
      super((changes: unknown, observer: { disconnect: () => void }) => {
        observation.current = observer;
        callbacks += 1;
        if (callbacks > 20) return observer.disconnect();
        callback(changes, observer);
      });
    }
  };
  window.eval(source);
  await window.WorkbenchI18n.ready;
  for (const locale of ['en', 'ja', 'zh-CN']) {
    await window.WorkbenchI18n.setLocale(locale);
    assert.equal(window.document.querySelector('#button').title, bundles[locale].legacy.generate);
    assert.equal(window.document.querySelector('#button').getAttribute('aria-label'), bundles[locale].legacy.generate);
    assert.equal(window.document.querySelector('#input').placeholder, bundles[locale].legacy.generate);
    assert.equal(window.document.querySelector('#input').value, 'untouched');
    assert.equal(window.document.querySelector('#explicit-input').placeholder, bundles[locale].legacy.generate);
    assert.equal(window.document.querySelector('#explicit-input').getAttribute('aria-label'), bundles[locale].legacy.generate);
    assert.equal(window.document.querySelector('#explicit-input').value, 'kept');
    assert.equal(window.document.querySelector('#explicit').textContent, bundles[locale].legacy.generate);
  }
  const dynamic = window.document.createElement('span');
  dynamic.setAttribute('data-i18n', 'legacy.generate');
  window.document.body.appendChild(dynamic);
  await new Promise(resolve => setTimeout(resolve, 20));
  assert.equal(dynamic.textContent, sourceText);
  assert.ok(callbacks <= 20, `observer did not settle: ${callbacks}`);
  observation.current?.disconnect();
  dom.window.close();
});
