import { getEndpointConfig } from '../../config/env';
import { getLocale, t } from '../../i18n';
import type { ProductCatalogItem, RecommendedItem } from '../../types/api';
import { buildMainMediaUrl } from '../../utils/url';

type CardItem = Partial<RecommendedItem> & Partial<ProductCatalogItem> & {
  id: number;
  title: string;
  price: number;
  image_url: string;
};

Component({
  properties: {
    item: {
      type: Object,
      value: {} as CardItem,
    },
    rank: {
      type: Number,
      value: 0,
    },
    locale: {
      type: String,
      value: getLocale(),
    },
  },
  data: {
    expanded: false,
    imageUrl: '',
    displayTitle: '',
    displayStyle: '',
    displayColor: '',
    displayFit: '',
    sizePreview: [] as string[],
    scoreText: '',
    rankText: '',
    texts: {} as Record<string, string>,
  },
  observers: {
    'item, rank, locale'() {
      this.syncCard();
    },
  },
  lifetimes: {
    attached() {
      this.syncCard();
    },
  },
  methods: {
    syncCard() {
      const item = this.properties.item as CardItem;
      const rank = this.properties.rank || 0;
      const mainBase = getEndpointConfig().mainApiBaseUrl;
      const rawImg = item.canonical?.image_url || item.image_url || '';
      const displayTitle = item.display?.title || item.title || '';
      const displayStyle = item.display?.styleType || item.style_type || '';
      const displayColor = item.display?.colorFamily || item.color_family || '';
      const displayFit = item.display?.bodyFit || item.body_fit || '';
      const sizePreview = Array.isArray(item.size_tags) ? item.size_tags.slice(0, 5) : [];
      const totalScore = typeof item.total_score === 'number' ? Math.round(item.total_score) : null;

      this.setData({
        imageUrl: buildMainMediaUrl(rawImg, mainBase),
        displayTitle,
        displayStyle,
        displayColor,
        displayFit,
        sizePreview,
        scoreText: totalScore !== null ? `${totalScore}${t('common.scoreUnit')}` : '',
        rankText: rank > 0 ? t('recommend.rankPrefix', { rank }) : '',
        texts: {
          tryOnBtn: t('recommend.tryOnBtn'),
          styleLabBtn: t('recommend.styleLabBtn'),
          expandAnalysis: t('recommend.expandAnalysis'),
          collapseAnalysis: t('recommend.collapseAnalysis'),
          matchScore: t('score.matchScore'),
        },
      });
    },
    onToggleExpand() {
      this.setData({ expanded: !this.data.expanded });
    },
    onPreviewImage() {
      if (!this.data.imageUrl) return;
      wx.previewImage({
        current: this.data.imageUrl,
        urls: [this.data.imageUrl],
      });
    },
    onTryOn() {
      this.triggerEvent('tryon', { item: this.properties.item });
    },
    onStyleLab() {
      this.triggerEvent('stylelab', { item: this.properties.item });
    },
  },
});
