import { describe, expect, it } from 'vitest';
import type { VideoModelItem, VideoParamSpec } from '../miniprogram/types/api';
import {
  adaptiveAspectRatio,
  bindSourceImage,
  collectInput,
  parametersFor,
  pickDefaultVideoModel,
} from '../miniprogram/utils/videoForm';

const SAMPLE_PARAMS: VideoParamSpec[] = [
  { name: 'prompt', type: 'text', required: true, maxLength: 500 },
  { name: 'image_url', type: 'image' },
  { name: 'aspect_ratio', type: 'enum', options: ['16:9', '9:16', '3:4'], default: '3:4' },
  { name: 'duration', type: 'integer', default: 5, min: 3, max: 10 },
];

describe('video form helpers', () => {
  it('picks preferred default video model and adapts vertical aspect ratio', () => {
    const models: VideoModelItem[] = [
      { slug: 'other-model', params: SAMPLE_PARAMS },
      { slug: 'gemini-omni-flash-1.2', params: SAMPLE_PARAMS },
    ];
    expect(pickDefaultVideoModel(models)?.slug).toBe('gemini-omni-flash-1.2');
    expect(adaptiveAspectRatio(SAMPLE_PARAMS, 900, 1200)).toBe('3:4');
    expect(adaptiveAspectRatio(SAMPLE_PARAMS, 1080, 1920)).toBe('9:16');
  });

  it('binds image source and validates dynamic inputs', () => {
    const bound = bindSourceImage(SAMPLE_PARAMS, { prompt: 'turn slowly' }, '/api/media/results/demo.png?st=abc');
    expect(bound.image_url).toBe('/api/media/results/demo.png?st=abc');

    const collected = collectInput(SAMPLE_PARAMS, bound);
    expect(collected).toEqual({
      prompt: 'turn slowly',
      image_url: '/api/media/results/demo.png?st=abc',
      aspect_ratio: '3:4',
      duration: 5,
    });

    expect(() => collectInput(SAMPLE_PARAMS, { prompt: 'ok', duration: 99 })).toThrow();
    expect(parametersFor({ slug: 'x', params: SAMPLE_PARAMS })).toHaveLength(4);
  });
});
