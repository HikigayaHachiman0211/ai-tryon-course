import { describe, expect, it } from 'vitest';
import en from '../miniprogram/i18n/en';
import { BUNDLES, getLocale, setLocale, t } from '../miniprogram/i18n';
import ja from '../miniprogram/i18n/ja';
import zhCN from '../miniprogram/i18n/zh-CN';

function collectKeys(obj: unknown, prefix = ''): string[] {
  if (Array.isArray(obj)) {
    return [`${prefix}[len=${obj.length}]`];
  }
  if (!obj || typeof obj !== 'object') {
    return [prefix];
  }
  const keys: string[] = [];
  Object.keys(obj as Record<string, unknown>).forEach((k) => {
    const nextPrefix = prefix ? `${prefix}.${k}` : k;
    keys.push(...collectKeys((obj as Record<string, unknown>)[k], nextPrefix));
  });
  return keys.sort();
}

describe('tri-lingual i18n parity and interpolation', () => {
  it('zh-CN, en, and ja have identical nested key schemas and array lengths', () => {
    const zhKeys = collectKeys(zhCN);
    const enKeys = collectKeys(en);
    const jaKeys = collectKeys(ja);
    expect(enKeys).toEqual(zhKeys);
    expect(jaKeys).toEqual(zhKeys);
    expect(Object.keys(BUNDLES)).toEqual(['zh-CN', 'en', 'ja']);
  });

  it('interpolates variables and switches active locale cleanly', () => {
    setLocale('zh-CN');
    expect(getLocale()).toBe('zh-CN');
    expect(t('recommend.rankPrefix', { rank: 2 })).toBe('TOP 2');
    expect(t('catalog.totalCount', { total: 42 })).toContain('42');

    setLocale('en');
    expect(getLocale()).toBe('en');
    expect(t('tabs.tryon')).toBe('Try-On');

    setLocale('ja');
    expect(getLocale()).toBe('ja');
    expect(t('tabs.assistant')).toBe('AI 接客');

    setLocale('zh-CN');
  });
});
