export const MBTI_OPTIONS: string[] = [
  'INTJ', 'INTP', 'ENTJ', 'ENTP',
  'INFJ', 'INFP', 'ENFJ', 'ENFP',
  'ISTJ', 'ISFJ', 'ESTJ', 'ESFJ',
  'ISTP', 'ISFP', 'ESTP', 'ESFP',
];

export const SIZE_OPTIONS: string[] = [
  'XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL',
];

export const GENDER_OPTIONS = [
  { value: 'female', labelKey: 'profile.genderFemale' },
  { value: 'male', labelKey: 'profile.genderMale' },
] as const;

export const COLOR_SUGGESTIONS = [
  { value: '黑色', labelKey: 'profile.colorBlack', swatch: '#1c1c1e' },
  { value: '白色', labelKey: 'profile.colorWhite', swatch: '#f5f5f7' },
  { value: '藏青', labelKey: 'profile.colorNavy', swatch: '#1d3557' },
  { value: '米白', labelKey: 'profile.colorCream', swatch: '#eae4d7' },
  { value: '灰色', labelKey: 'profile.colorGray', swatch: '#8e8e93' },
  { value: '雾蓝', labelKey: 'profile.colorMistBlue', swatch: '#6b9ac4' },
  { value: '卡其色', labelKey: 'profile.colorKhaki', swatch: '#b59e7a' },
  { value: '粉色', labelKey: 'profile.colorPink', swatch: '#e5a9b8' },
] as const;

export const BRAND_SUGGESTIONS = [
  { value: '波司登', labelKey: 'profile.brandBosideng' },
  { value: '阿迪达斯', labelKey: 'profile.brandAdidas' },
  { value: '李宁', labelKey: 'profile.brandLiNing' },
  { value: '骆驼', labelKey: 'profile.brandCamel' },
  { value: '北面', labelKey: 'profile.brandNorthFace' },
  { value: '雪中飞', labelKey: 'profile.brandXuezhongfei' },
] as const;

export const STYLE_SUGGESTIONS = [
  { value: '短款', labelKey: 'profile.styleShort' },
  { value: '面包服', labelKey: 'profile.stylePuffer' },
  { value: '中长款大衣', labelKey: 'profile.styleMidLong' },
  { value: '轻薄款', labelKey: 'profile.styleLight' },
  { value: '巴恩风/工装风', labelKey: 'profile.styleWorkwear' },
  { value: '派克大衣', labelKey: 'profile.styleParka' },
] as const;

export interface SampleModelItem {
  id: string;
  name: string;
  gender: 'male' | 'female';
  filename: string;
}

export const SAMPLE_MODELS: SampleModelItem[] = [
  { id: 'male-mannequin-1', name: '通用男模 1', gender: 'male', filename: 'mannequin-male-1.png' },
  { id: 'male-mannequin-2', name: '通用男模 2', gender: 'male', filename: 'mannequin-male-2.png' },
  { id: 'female-mannequin-1', name: '通用女模 1', gender: 'female', filename: 'mannequin-female-1.png' },
  { id: 'female-mannequin-2', name: '通用女模 2', gender: 'female', filename: 'mannequin-female-2.png' },
];

export const TONE_PRESETS = [
  { id: 'natural', labelKey: 'voice.toneNatural' },
  { id: 'gentle', labelKey: 'voice.toneGentle' },
  { id: 'professional', labelKey: 'voice.toneProfessional' },
  { id: 'anime', labelKey: 'voice.toneAnime' },
] as const;

export const TRYON_GARMENT_TYPES = [
  { value: '', labelKey: 'tryon.garmentAuto' },
  { value: 'tops', labelKey: 'tryon.garmentTops' },
  { value: 'outerwear', labelKey: 'tryon.garmentOuterwear' },
  { value: 'one-pieces', labelKey: 'tryon.garmentOnePiece' },
] as const;

export const VIDEO_PRESET_PROMPTS: Record<'turn' | 'walk' | 'detail' | 'studio', Record<'zh-CN' | 'en' | 'ja', string>> = {
  turn: {
    'zh-CN': '保留人物外貌与羽绒服质感，模特自然微笑并缓慢原地转身 180 度展示外套版型与充绒蓬松度，柔和影棚光。',
    en: 'Preserve identity and down jacket fabric details; the model smiles naturally and slowly turns 180 degrees to showcase coat silhouette and loft under soft studio lighting.',
    ja: '人物の顔立ちとダウンジャケットの質感を保ち、モデルが自然に微笑みながらゆっくり180度ターンしてシルエットとふくらみを見せる柔らかなスタジオ光映像。',
  },
  walk: {
    'zh-CN': '模特身穿这件羽绒服在冬日都市街头自信漫步，衣摆自然摆动，电影感浅景深跟拍镜头。',
    en: 'The model walks confidently along a crisp winter city street wearing this down jacket, natural fabric motion, cinematic shallow depth-of-field tracking shot.',
    ja: 'このダウンジャケットを着たモデルが冬の街並みを自信を持って歩く、生地の自然な揺れとシネマティックな浅い被写界深度のトラッキングショット。',
  },
  detail: {
    'zh-CN': '镜头从半身平滑推进到羽绒服领口、拉链与哑光防风面料纹理细节，光影细腻真实。',
    en: 'Smooth camera push-in from mid-shot to collar, zipper, and matte windproof down fabric texture details with crisp realistic lighting.',
    ja: 'ミドルショットから襟元・ファスナー・マットな防風ダウン生地の質感ディテールへ滑らかに寄るリアルなライティング映像。',
  },
  studio: {
    'zh-CN': '极简高级灰影棚背景，模特微微侧身整理衣领并展示正面及侧面立体剪裁，质感大片效果。',
    en: 'Minimalist studio backdrop, the model slightly adjusts the collar and presents front and side tailored silhouette in an editorial fashion look.',
    ja: 'ミニマルなスタジオ背景で、モデルが襟元を軽く整えながら正面とサイドの立体裁断を見せるエディトリアル映像。',
  },
};
