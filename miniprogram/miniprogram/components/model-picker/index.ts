import { getEndpointConfig } from '../../config/env';
import { getLocale, t } from '../../i18n';
import { SAMPLE_MODELS, type SampleModelItem } from '../../utils/formOptions';
import { downloadTempFile } from '../../utils/request';
import { buildSampleModelUrl } from '../../utils/url';

interface SampleModelView extends SampleModelItem {
  thumbUrl: string;
}

function buildModelsForGender(gender: 'male' | 'female'): SampleModelView[] {
  const base = getEndpointConfig().mainApiBaseUrl;
  return SAMPLE_MODELS.filter((m) => m.gender === gender).map((m) => ({
    ...m,
    thumbUrl: buildSampleModelUrl(m.gender, m.filename, base),
  }));
}

Component({
  properties: {
    previewUrl: {
      type: String,
      value: '',
    },
    sampleModelId: {
      type: String,
      value: '',
    },
    locale: {
      type: String,
      value: getLocale(),
    },
  },
  data: {
    sampleGender: 'male' as 'male' | 'female',
    models: buildModelsForGender('male'),
    loadingModelId: '',
    texts: {} as Record<string, string>,
  },
  observers: {
    locale() {
      this.syncTexts();
    },
  },
  lifetimes: {
    attached() {
      this.syncTexts();
    },
  },
  pageLifetimes: {
    show() {
      this.setData({
        models: buildModelsForGender(this.data.sampleGender),
      });
      this.syncTexts();
    },
  },
  methods: {
    syncTexts() {
      this.setData({
        texts: {
          photoTitle: t('profile.photoTitle'),
          photoHint: t('profile.photoHint'),
          uploadPhoto: t('profile.uploadPhoto'),
          changePhoto: t('profile.changePhoto'),
          removePhoto: t('profile.removePhoto'),
          sampleChoose: t('profile.sampleChoose'),
          sampleMale: t('profile.sampleMale'),
          sampleFemale: t('profile.sampleFemale'),
        },
      });
    },
    onChoosePhoto() {
      wx.chooseMedia({
        count: 1,
        mediaType: ['image'],
        sourceType: ['album', 'camera'],
        sizeType: ['compressed', 'original'],
        success: (res) => {
          const file = res.tempFiles && res.tempFiles[0];
          if (!file || !file.tempFilePath) return;
          this.triggerEvent('change', {
            localPath: file.tempFilePath,
            previewUrl: file.tempFilePath,
            sampleModelId: '',
            gender: '',
          });
        },
      });
    },
    onClearPhoto() {
      this.triggerEvent('clear');
    },
    onSwitchGender(e: WechatMiniprogram.TouchEvent) {
      const gender = e.currentTarget.dataset.gender as 'male' | 'female';
      if (!gender || gender === this.data.sampleGender) return;
      this.setData({
        sampleGender: gender,
        models: buildModelsForGender(gender),
      });
    },
    async onPickSample(e: WechatMiniprogram.TouchEvent) {
      const id = String(e.currentTarget.dataset.id || '');
      const target = this.data.models.find((m) => m.id === id);
      if (!target || this.data.loadingModelId) return;
      this.setData({ loadingModelId: id });
      wx.showLoading({ title: t('profile.sampleDownloading'), mask: true });
      try {
        const localPath = await downloadTempFile(target.thumbUrl);
        this.triggerEvent('change', {
          localPath,
          previewUrl: localPath,
          sampleModelId: target.id,
          gender: target.gender,
        });
        wx.showToast({ title: t('profile.sampleReady'), icon: 'success' });
      } catch (err) {
        const msg = err instanceof Error ? err.message : t('common.networkError');
        wx.showToast({ title: msg.slice(0, 28), icon: 'none' });
      } finally {
        wx.hideLoading();
        this.setData({ loadingModelId: '' });
      }
    },
  },
});
