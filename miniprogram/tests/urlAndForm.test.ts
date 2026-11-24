import { describe, expect, it } from 'vitest';
import {
  appendQueryParams,
  buildMainMediaUrl,
  buildSampleModelUrl,
  buildTryOnMediaUrl,
  cleanFormFields,
  joinUrl,
  serializeFormUrlEncoded,
} from '../miniprogram/utils/url';

describe('URL and form encoding helpers', () => {
  it('joins base and path cleanly regardless of slashes', () => {
    expect(joinUrl('http://127.0.0.1:8000/', '/api/recommend')).toBe('http://127.0.0.1:8000/api/recommend');
    expect(joinUrl('https://demo.example.com/mp-tryon', 'submit-task')).toBe(
      'https://demo.example.com/mp-tryon/submit-task',
    );
    expect(joinUrl('http://127.0.0.1:8000', 'https://cdn.example.com/a.jpg')).toBe(
      'https://cdn.example.com/a.jpg',
    );
  });

  it('strips undefined, null, and empty string fields for FastAPI Form compatibility', () => {
    const cleaned = cleanFormFields({
      color_preference: '黑色',
      gender: 'male',
      price_min: undefined,
      price_max: null,
      mbti: '',
      freedom: 0,
    });
    expect(cleaned).toEqual({
      color_preference: '黑色',
      gender: 'male',
      freedom: '0',
    });

    const encoded = serializeFormUrlEncoded({
      color_preference: '黑色',
      price_min: '',
      gender: 'female',
    });
    expect(encoded).toContain('color_preference=%E9%BB%91%E8%89%B2');
    expect(encoded).toContain('gender=female');
    expect(encoded).not.toContain('price_min');
  });

  it('builds media, sample model, and query URLs without browser URL global', () => {
    expect(appendQueryParams('http://127.0.0.1:8000/api/history', { limit: 20, query: '' })).toBe(
      'http://127.0.0.1:8000/api/history?limit=20',
    );
    expect(buildMainMediaUrl('/static/products/1.jpg', 'http://127.0.0.1:8000/')).toBe(
      'http://127.0.0.1:8000/static/products/1.jpg',
    );
    expect(buildTryOnMediaUrl('/uploads/a.png?mt=abc', 'https://demo.example.com/mp-tryon/')).toBe(
      'https://demo.example.com/mp-tryon/uploads/a.png?mt=abc',
    );
    expect(buildSampleModelUrl('male', 'mannequin-male-1.png', 'http://127.0.0.1:8000')).toBe(
      'http://127.0.0.1:8000/sample-models/male/mannequin-male-1.png',
    );
  });
});
