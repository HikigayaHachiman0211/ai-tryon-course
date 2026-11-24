import { getLocale, LOCALE_OPTIONS, setLocale, subscribeLocale, t } from '../../i18n';
import type { AppLocale } from '../../types/api';

const unsubMap = new WeakMap<object, () => void>();

Component({
  properties: {
    showShortcuts: {
      type: Boolean,
      value: true,
    },
  },
  data: {
    locale: getLocale(),
    options: LOCALE_OPTIONS,
    brandName: t('common.appName'),
    historyLabel: t('common.history'),
    settingsLabel: t('common.settings'),
  },
  lifetimes: {
    attached() {
      this.syncTexts();
      const unsub = subscribeLocale(() => this.syncTexts());
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
  pageLifetimes: {
    show() {
      this.syncTexts();
    },
  },
  methods: {
    syncTexts() {
      this.setData({
        locale: getLocale(),
        brandName: t('common.appName'),
        historyLabel: t('common.history'),
        settingsLabel: t('common.settings'),
      });
    },
    onSelectLocale(e: WechatMiniprogram.TouchEvent) {
      const next = e.currentTarget.dataset.locale as AppLocale;
      if (!next || next === this.data.locale) return;
      const resolved = setLocale(next);
      this.syncTexts();
      this.triggerEvent('localechange', { locale: resolved });
    },
    onOpenHistory() {
      wx.navigateTo({ url: '/pages/history/index' });
    },
    onOpenSettings() {
      wx.navigateTo({ url: '/pages/settings/index' });
    },
  },
});
