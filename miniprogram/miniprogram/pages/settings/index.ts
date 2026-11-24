import {
  applyEndpointPreset,
  type EndpointPresetId,
  getEndpointConfig,
  resetEndpointConfig,
  saveEndpointConfig,
} from '../../config/env';
import { getLocale, LOCALE_OPTIONS, setLocale, subscribeLocale, t } from '../../i18n';
import { getAssistantConfig } from '../../services/assistantApi';
import { getHealth } from '../../services/mainApi';
import { getRuntimeStatus } from '../../services/tryonApi';
import { getVideoConfig } from '../../services/videoApi';
import { getVoiceConfig } from '../../services/voiceApi';
import type { AppLocale } from '../../types/api';

interface ProbeRow {
  id: string;
  label: string;
  status: 'idle' | 'ok' | 'warn' | 'fail';
  detail: string;
}

function buildTexts() {
  return {
    title: t('settings.title'),
    languageSection: t('settings.languageSection'),
    endpointSection: t('settings.endpointSection'),
    presetLocalBatch: t('settings.presetLocalBatch'),
    presetLocalManual: t('settings.presetLocalManual'),
    presetCloud443: t('settings.presetCloud443'),
    mainApiLabel: t('settings.mainApiLabel'),
    tryonApiLabel: t('settings.tryonApiLabel'),
    saveEndpoints: t('settings.saveEndpoints'),
    resetEndpoints: t('settings.resetEndpoints'),
    probeSection: t('settings.probeSection'),
    runProbe: t('settings.runProbe'),
    probing: t('settings.probing'),
    defenseTipTitle: t('settings.defenseTipTitle'),
    defenseTipBody: t('settings.defenseTipBody'),
  };
}

function initialProbes(): ProbeRow[] {
  return [
    { id: 'main', label: t('settings.probeMainHealth'), status: 'idle', detail: '-' },
    { id: 'assistant', label: t('settings.probeAssistant'), status: 'idle', detail: '-' },
    { id: 'voice', label: t('settings.probeVoice'), status: 'idle', detail: '-' },
    { id: 'tryon', label: t('settings.probeTryon'), status: 'idle', detail: '-' },
    { id: 'video', label: t('settings.probeVideo'), status: 'idle', detail: '-' },
  ];
}

async function runSingleProbe(
  id: string,
  label: string,
  fn: () => Promise<{ ok: boolean; warnDetail?: string }>,
): Promise<ProbeRow> {
  const start = Date.now();
  try {
    const res = await fn();
    const ms = Date.now() - start;
    if (res.ok) {
      return { id, label, status: 'ok', detail: t('settings.probeOk', { ms }) };
    }
    return { id, label, status: 'warn', detail: `${t('settings.probeWarn', { ms })}${res.warnDetail ? ` · ${res.warnDetail}` : ''}` };
  } catch (err) {
    const msg = err instanceof Error ? err.message : t('settings.probeFail');
    return { id, label, status: 'fail', detail: `${t('settings.probeFail')} · ${msg.slice(0, 60)}` };
  }
}

Page({
  data: {
    locale: getLocale(),
    localeOptions: LOCALE_OPTIONS,
    presetId: getEndpointConfig().presetId as EndpointPresetId,
    mainApiBaseUrl: getEndpointConfig().mainApiBaseUrl,
    tryonApiBaseUrl: getEndpointConfig().tryonApiBaseUrl,
    probing: false,
    probes: initialProbes(),
    texts: buildTexts(),
  },
  _unsubLocale: undefined as undefined | (() => void),

  onLoad() {
    this._unsubLocale = subscribeLocale((nextLocale) => {
      this.syncTexts(nextLocale);
    });
  },

  onUnload() {
    if (this._unsubLocale) this._unsubLocale();
  },

  onShow() {
    this.syncTexts(getLocale());
  },

  syncTexts(locale: AppLocale) {
    wx.setNavigationBarTitle({ title: t('settings.title') });
    const cfg = getEndpointConfig();
    this.setData({
      locale,
      presetId: cfg.presetId,
      mainApiBaseUrl: cfg.mainApiBaseUrl,
      tryonApiBaseUrl: cfg.tryonApiBaseUrl,
      texts: buildTexts(),
      probes: this.data.probes.map((p) => {
        const keyMap: Record<string, string> = {
          main: 'settings.probeMainHealth',
          assistant: 'settings.probeAssistant',
          voice: 'settings.probeVoice',
          tryon: 'settings.probeTryon',
          video: 'settings.probeVideo',
        };
        return { ...p, label: t(keyMap[p.id] || p.label) };
      }),
    });
  },

  onSelectLocale(e: WechatMiniprogram.TouchEvent) {
    const next = e.currentTarget.dataset.locale as AppLocale;
    if (!next) return;
    setLocale(next);
    wx.showToast({ title: t('common.localeSwitched'), icon: 'success' });
  },

  onSelectPreset(e: WechatMiniprogram.TouchEvent) {
    const presetId = e.currentTarget.dataset.preset as Exclude<EndpointPresetId, 'custom'>;
    if (!presetId) return;
    const saved = applyEndpointPreset(presetId);
    this.setData({
      presetId: saved.presetId,
      mainApiBaseUrl: saved.mainApiBaseUrl,
      tryonApiBaseUrl: saved.tryonApiBaseUrl,
    });
  },

  onInputEndpoint(e: WechatMiniprogram.Input) {
    const field = String(e.currentTarget.dataset.field || '');
    const value = String(e.detail.value || '');
    this.setData({
      [field]: value,
      presetId: 'custom',
    } as Record<string, unknown>);
  },

  onSaveEndpoints() {
    const saved = saveEndpointConfig({
      presetId: this.data.presetId,
      mainApiBaseUrl: this.data.mainApiBaseUrl,
      tryonApiBaseUrl: this.data.tryonApiBaseUrl,
    });
    this.setData({
      presetId: saved.presetId,
      mainApiBaseUrl: saved.mainApiBaseUrl,
      tryonApiBaseUrl: saved.tryonApiBaseUrl,
    });
    wx.showToast({ title: t('settings.endpointsSaved'), icon: 'success' });
  },

  onResetEndpoints() {
    const saved = resetEndpointConfig();
    this.setData({
      presetId: saved.presetId,
      mainApiBaseUrl: saved.mainApiBaseUrl,
      tryonApiBaseUrl: saved.tryonApiBaseUrl,
    });
    wx.showToast({ title: t('settings.endpointsSaved'), icon: 'success' });
  },

  async onRunProbe() {
    saveEndpointConfig({
      presetId: this.data.presetId,
      mainApiBaseUrl: this.data.mainApiBaseUrl,
      tryonApiBaseUrl: this.data.tryonApiBaseUrl,
    });
    this.setData({ probing: true });
    try {
      const results = await Promise.all([
        runSingleProbe('main', t('settings.probeMainHealth'), async () => {
          await getHealth();
          return { ok: true };
        }),
        runSingleProbe('assistant', t('settings.probeAssistant'), async () => {
          const cfg = await getAssistantConfig();
          return { ok: Boolean(cfg.enabled) };
        }),
        runSingleProbe('voice', t('settings.probeVoice'), async () => {
          const cfg = await getVoiceConfig();
          return {
            ok: Boolean(cfg.asr_enabled || cfg.tts_enabled),
            warnDetail: `ASR:${cfg.asr_enabled ? 'ON' : 'OFF'} TTS:${cfg.tts_enabled ? 'ON' : 'OFF'}`,
          };
        }),
        runSingleProbe('tryon', t('settings.probeTryon'), async () => {
          const st = await getRuntimeStatus();
          return {
            ok: Boolean(st.tryon_enabled && st.configured),
            warnDetail: st.config_source || '',
          };
        }),
        runSingleProbe('video', t('settings.probeVideo'), async () => {
          const vc = await getVideoConfig();
          return {
            ok: Boolean(vc.enabled && vc.configured),
            warnDetail: vc.sandbox ? 'sandbox' : '',
          };
        }),
      ]);
      this.setData({ probes: results });
    } finally {
      this.setData({ probing: false });
    }
  },
});
