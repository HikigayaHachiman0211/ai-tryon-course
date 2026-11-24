import { subscribeLocale, t } from '../i18n';

interface TabItem {
  pagePath: string;
  key: 'recommend' | 'catalog' | 'tryon' | 'assistant';
  glyph: string;
  label: string;
}

const unsubMap = new WeakMap<object, () => void>();

function buildTabList(): TabItem[] {
  return [
    { pagePath: '/pages/recommend/index', key: 'recommend', glyph: '✦', label: t('tabs.recommend') },
    { pagePath: '/pages/catalog/index', key: 'catalog', glyph: '▤', label: t('tabs.catalog') },
    { pagePath: '/pages/tryon/index', key: 'tryon', glyph: '◈', label: t('tabs.tryon') },
    { pagePath: '/pages/assistant/index', key: 'assistant', glyph: '◎', label: t('tabs.assistant') },
  ];
}

Component({
  data: {
    selected: 0,
    list: buildTabList(),
  },
  lifetimes: {
    attached() {
      const unsub = subscribeLocale(() => {
        this.setData({ list: buildTabList() });
      });
      unsubMap.set(this, unsub);
    },
    detached() {
      const unsub = unsubMap.get(this);
      if (unsub) {
        unsub();
        unsubMap.delete(this);
      }
    },
  },
  methods: {
    syncTabState(selectedIndex: number) {
      this.setData({
        selected: selectedIndex,
        list: buildTabList(),
      });
    },
    onSwitchTab(e: WechatMiniprogram.TouchEvent) {
      const idx = Number(e.currentTarget.dataset.index);
      const item = this.data.list[idx];
      if (!item) return;
      wx.switchTab({ url: item.pagePath });
    },
  },
});
