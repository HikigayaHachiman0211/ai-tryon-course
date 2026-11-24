import test from 'node:test';
import assert from 'node:assert/strict';

const load = () => import('../static/js/video-form.js');
const params = [
  { name: 'prompt', type: 'text', required: true, maxLength: 100 },
  { name: 'image_url', type: 'image' },
  { name: 'duration', type: 'integer', default: 5, min: 3, max: 15 },
  { name: 'audio', type: 'boolean', default: false },
  { name: 'quality', type: 'enum', options: [1, 2, 3], default: 2 },
  { name: 'images', type: 'images', maxItems: 2 },
];

test('model and provider switch uses current schema and clears incompatible fields', async () => {
  const { parametersFor, defaultsFor, collectInput } = await load();
  const model = { params, providers: [{ provider: 'fast', params: params.slice(0, 3) }] };
  const selected = parametersFor(model, 'fast');
  assert.equal(selected.length, 3);
  const values = defaultsFor(selected);
  assert.equal(values.duration, 5);
  assert.equal(values.audio, undefined);
  const input = collectInput(selected, { ...values, prompt: 'walk slowly', audio: false });
  assert.deepEqual(input, { prompt: 'walk slowly', duration: 5 });
});

test('parameter input preserves boolean false and numeric enum values', async () => {
  const { collectInput, defaultsFor } = await load();
  assert.deepEqual(collectInput(params, { ...defaultsFor(params), prompt: 'turn', duration: '8' }), {
    prompt: 'turn', duration: 8, audio: false, quality: 2,
  });
});

test('parameter validation covers ranges, required values, array limits and decimals', async () => {
  const { collectInput } = await load();
  for (const values of [{}, { prompt: 'a', duration: '2' }, { prompt: 'a', duration: '5.5' },
    { prompt: 'a', images: 'https://a.test/1\nhttps://a.test/2\nhttps://a.test/3' }]) {
    assert.throws(() => collectInput(params, values));
  }
  assert.deepEqual(collectInput(params, { prompt: 'a', images: 'https://a.test/1\n\nhttps://a.test/2' }).images,
    ['https://a.test/1', 'https://a.test/2']);
});

test('try-on source binds to a supported image slot only', async () => {
  const { bindSourceImage } = await load();
  assert.deepEqual(bindSourceImage(params, { prompt: 'a' }, '/uploads/tryon.png'), { prompt: 'a', image_url: '/uploads/tryon.png' });
  assert.deepEqual(bindSourceImage([{ name: 'images', type: 'images' }], {}, '/uploads/tryon.png'), { images: ['/uploads/tryon.png'] });
  assert.throws(() => bindSourceImage([{ name: 'prompt', type: 'text' }], {}, 'https://a.test/1'));
});

test('pickDefaultVideoModel prioritizes gemini-omni-flash-1.2 when available', async () => {
  const { pickDefaultVideoModel } = await load();
  const catalog = [
    { slug: 'seedance-2.5-flash', params: [{ name: 'image_url', type: 'image' }] },
    { slug: 'gemini-omni-flash-1.2', params: [{ name: 'image_url', type: 'image' }] },
  ];
  assert.equal(pickDefaultVideoModel(catalog).slug, 'gemini-omni-flash-1.2');
  assert.equal(pickDefaultVideoModel(catalog, 'seedance-2.5-flash').slug, 'seedance-2.5-flash');
  assert.equal(pickDefaultVideoModel([{ slug: 'text-only', params: [] }, { slug: 'other-i2v', params: [{ name: 'image_url', type: 'image' }] }]).slug, 'other-i2v');
});

test('adaptiveAspectRatio matches try-on image dimensions to nearest supported ratio', async () => {
  const { adaptiveAspectRatio } = await load();
  const omniParams = [{ name: 'aspect_ratio', type: 'enum', options: ['16:9', '9:16'], default: '16:9' }];
  const seedanceParams = [{ name: 'aspect_ratio', type: 'enum', options: ['16:9', '9:16', '1:1', '4:3', '3:4', '21:9'], default: '16:9' }];

  // Portrait 3:4 try-on output adapts to 9:16 on Omni Flash 1.2 and exact 3:4 on Seedance
  assert.equal(adaptiveAspectRatio(omniParams, 896, 1152), '9:16');
  assert.equal(adaptiveAspectRatio(seedanceParams, 896, 1152), '3:4');

  // Vertical 9:16 -> 9:16; landscape 16:9 -> 16:9; square 1:1 on 16:9/9:16 prefers vertical 9:16
  assert.equal(adaptiveAspectRatio(omniParams, 1080, 1920), '9:16');
  assert.equal(adaptiveAspectRatio(omniParams, 1920, 1080), '16:9');
  assert.equal(adaptiveAspectRatio(omniParams, 1024, 1024), '9:16');
  assert.equal(adaptiveAspectRatio(seedanceParams, 1024, 1024), '1:1');
});
