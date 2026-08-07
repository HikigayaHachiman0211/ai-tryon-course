import type { RecommendFormPatch } from '../assistantTypes';

const VALID_GENDERS = new Set(['male', 'female']);
const VALID_COLORS = new Set([
  '黑色', '白色', '米白', '灰色', '蓝色', '雾蓝', '藏青', '绿色',
  '豆绿', '橄榄', '红色', '棕色', '卡其色', '米色', '橘色', '粉色',
]);
const VALID_BRANDS = new Set([
  '波司登', '李宁', '安踏', '骆驼', '阿迪达斯', '耐克', '优衣库',
  '太平鸟', '雪中飞', '雅鹿', '鸭鸭', '鸿星尔克', '361°', '北面',
  '始祖鸟', '哥伦比亚', 'Under Armour', '安德玛', '罗蒙', '南极人',
  '乔丹', 'FILA', '匹克', '海澜之家',
]);
const VALID_SIZES = new Set(['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL', '6XL', '7XL']);
const VALID_STYLES = new Set([
  '常规短外套', '短款', '轻薄款', '绗缝款（排骨款）', '面包服',
  '中长款大衣', '长款', '巴恩风/工装风', '派克大衣', '马甲',
]);
const VALID_AI_PROVIDERS = new Set(['auto', 'gemini', 'deepseek', 'mimo']);
const VALID_VISION_PROVIDERS = new Set(['mimo', 'gemini', 'auto']);
const VALID_MBTI = new Set([
  'INTJ', 'INTP', 'ENTJ', 'ENTP',
  'INFJ', 'INFP', 'ENFJ', 'ENFP',
  'ISTJ', 'ISFJ', 'ESTJ', 'ESFJ',
  'ISTP', 'ISFP', 'ESTP', 'ESFP',
]);
const VALID_MIMO_MODELS = new Set(['mimo-v2.5', 'mimo-v2.5-pro', 'mimo-v2-omni']);

export function applyAssistantFormPatch(
  currentForm: Record<string, unknown>,
  patch: RecommendFormPatch,
): Record<string, unknown> {
  const next = { ...currentForm };

  if (patch.color_preference && typeof patch.color_preference === 'string') {
    const color = patch.color_preference.trim();
    if (VALID_COLORS.has(color)) {
      next.color_preference = color;
    }
  }

  if (patch.brand_preference && typeof patch.brand_preference === 'string') {
    const brands = patch.brand_preference
      .split(/[,，、|]+/)
      .map((brand) => brand.trim())
      .filter(Boolean);
    if (brands.length > 0 && brands.every((brand) => VALID_BRANDS.has(brand))) {
      next.brand_preference = brands.join('，');
    }
  }

  if (patch.gender && VALID_GENDERS.has(patch.gender)) {
    next.gender = patch.gender;
  }

  if (patch.price_min !== null && patch.price_min !== undefined && patch.price_min > 0) {
    next.price_min = patch.price_min;
  }

  if (patch.price_max !== null && patch.price_max !== undefined && patch.price_max > 0) {
    next.price_max = patch.price_max;
  }

  if (patch.mbti && typeof patch.mbti === 'string') {
    const upper = patch.mbti.toUpperCase();
    if (VALID_MBTI.has(upper)) {
      next.mbti = upper;
    }
  }

  if (patch.size && typeof patch.size === 'string') {
    const size = patch.size.trim().toUpperCase();
    if (VALID_SIZES.has(size)) {
      next.size = size;
    }
  }

  if (patch.style_preference && typeof patch.style_preference === 'string') {
    const style = patch.style_preference.trim();
    if (VALID_STYLES.has(style)) {
      next.style_preference = style;
    }
  }

  if (patch.ai_provider && VALID_AI_PROVIDERS.has(patch.ai_provider)) {
    next.ai_provider = patch.ai_provider;
  }

  if (patch.vision_provider && VALID_VISION_PROVIDERS.has(patch.vision_provider)) {
    next.vision_provider = patch.vision_provider;
  }

  if (patch.mimo_model && VALID_MIMO_MODELS.has(patch.mimo_model)) {
    next.mimo_model = patch.mimo_model;
  }

  if (patch.gemini_model && typeof patch.gemini_model === 'string' && patch.gemini_model.trim()) {
    next.gemini_model = patch.gemini_model.trim();
  }

  if (patch.deepseek_model && typeof patch.deepseek_model === 'string' && patch.deepseek_model.trim()) {
    next.deepseek_model = patch.deepseek_model.trim();
  }

  return next;
}
