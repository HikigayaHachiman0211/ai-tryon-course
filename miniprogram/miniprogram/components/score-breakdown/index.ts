import { getLocale, t } from '../../i18n';

interface BreakdownRow {
  label: string;
  score: number;
  widthPct: number;
  toneClass: string;
}

function normalizeRows(raw: Record<string, number> | null | undefined): BreakdownRow[] {
  if (!raw || typeof raw !== 'object') return [];
  const labelMap: Record<string, string> = {
    color: t('score.color'),
    size: t('score.size'),
    style: t('score.style'),
    brand: t('score.brand'),
    personality: t('score.personality'),
    gender: t('score.gender'),
    price: t('score.price'),
  };
  return Object.keys(raw).map((key) => {
    const num = Math.max(0, Math.min(100, Math.round(Number(raw[key]) || 0)));
    return {
      label: labelMap[key] || key,
      score: num,
      widthPct: num,
      toneClass: num >= 85 ? 'bar-gold' : 'bar-blue',
    };
  });
}

Component({
  properties: {
    breakdown: {
      type: Object,
      value: {} as Record<string, number>,
    },
    locale: {
      type: String,
      value: getLocale(),
    },
  },
  data: {
    title: t('score.breakdownTitle'),
    rows: [] as BreakdownRow[],
  },
  observers: {
    'breakdown, locale'(breakdown: Record<string, number>) {
      this.setData({
        title: t('score.breakdownTitle'),
        rows: normalizeRows(breakdown),
      });
    },
  },
  lifetimes: {
    attached() {
      this.setData({
        title: t('score.breakdownTitle'),
        rows: normalizeRows(this.properties.breakdown as Record<string, number>),
      });
    },
  },
});
