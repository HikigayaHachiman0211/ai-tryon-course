export const MBTI_OPTIONS = [
  'INTJ', 'INTP', 'ENTJ', 'ENTP',
  'INFJ', 'INFP', 'ENFJ', 'ENFP',
  'ISTJ', 'ISFJ', 'ESTJ', 'ESFJ',
  'ISTP', 'ISFP', 'ESTP', 'ESFP',
];

export const GENDER_OPTIONS = [
  { value: 'female', labelKey: 'profile.gender.female' },
  { value: 'male', labelKey: 'profile.gender.male' },
];

export const BRAND_SUGGESTIONS = [
  { value: '阿迪达斯', labelKey: 'profile.brand.adidas' },
  { value: '骆驼', labelKey: 'profile.brand.camel' },
  { value: '波司登', labelKey: 'profile.brand.bosideng' },
  { value: '李宁', labelKey: 'profile.brand.liNing' },
];

export const SAMPLE_MODELS = [
  { id: 'male-mannequin-1', name: '通用男模 1', gender: 'male' as const, filename: 'mannequin-male-1.png' },
  { id: 'male-mannequin-2', name: '通用男模 2', gender: 'male' as const, filename: 'mannequin-male-2.png' },
  { id: 'female-mannequin-1', name: '通用女模 1', gender: 'female' as const, filename: 'mannequin-female-1.png' },
  { id: 'female-mannequin-2', name: '通用女模 2', gender: 'female' as const, filename: 'mannequin-female-2.png' },
];

export type SampleModel = typeof SAMPLE_MODELS[number];

export const GENDER_LABELS: Record<string, string> = {
  female: 'profile.gender.femaleLong',
  male: 'profile.gender.maleLong',
};

export type ViewMode = 'recommend' | 'style-lab';
export type CatalogMode = 'gender' | 'all';
export type CatalogPlatform = 'all' | 'jd' | 'taobao';

export const getInitialView = (): ViewMode => {
  if (typeof window === 'undefined') {
    return 'recommend';
  }

  return window.location.hash === '#style-lab' ? 'style-lab' : 'recommend';
};
