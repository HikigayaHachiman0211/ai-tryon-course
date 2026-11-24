import { describe, expect, it } from 'vitest';
import { applyAssistantFormPatch, extractValidPatchEntries } from '../miniprogram/utils/formPatch';

describe('assistant form patch whitelist', () => {
  it('applies valid fields and rejects unknown or out-of-whitelist values', () => {
    const next = applyAssistantFormPatch(
      { color_preference: '白色', gender: 'female' },
      {
        color_preference: '黑色',
        gender: 'male',
        brand_preference: '波司登，雪中飞',
        price_min: 500,
        price_max: 1200,
        mbti: 'intj',
        size: 'xl',
        style_preference: '短款',
      },
    );

    expect(next).toEqual({
      color_preference: '黑色',
      gender: 'male',
      brand_preference: '波司登，雪中飞',
      price_min: 500,
      price_max: 1200,
      mbti: 'INTJ',
      size: 'XL',
      style_preference: '短款',
    });

    const invalid = applyAssistantFormPatch(
      { color_preference: '黑色' },
      {
        color_preference: '荧光彩虹色',
        gender: 'alien',
        brand_preference: 'UnknownBrand',
        price_min: -10,
        mbti: 'XXXX',
        size: '99XL',
      },
    );
    expect(invalid).toEqual({ color_preference: '黑色' });
  });

  it('extracts ordered valid entries for RecommendActionCard display', () => {
    const entries = extractValidPatchEntries({
      gender: 'female',
      color_preference: '米白',
      price_max: 900,
      mbti: 'ENFP',
    });
    expect(entries).toEqual([
      { key: 'gender', value: 'female' },
      { key: 'color_preference', value: '米白' },
      { key: 'mbti', value: 'ENFP' },
      { key: 'price_max', value: '900' },
    ]);
  });
});
