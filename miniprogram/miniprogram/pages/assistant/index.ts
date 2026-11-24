import { getBundle, getLocale, subscribeLocale, t } from '../../i18n';
import {
  getAssistantConfig,
  postAssistantChat,
  searchAssistantKnowledge,
} from '../../services/assistantApi';
import {
  asrRecognize,
  getVoiceCatalog,
  getVoiceConfig,
  resolveTtsAudioUrl,
  ttsSynthesize,
} from '../../services/voiceApi';
import { applyFormPatchToStore, getState } from '../../store/appStore';
import type {
  AssistantChatMessage,
  AssistantPublicConfig,
  CallState,
  KnowledgeSearchItem,
  RecommendFormPatch,
  VoiceCallTurn,
  VoicePublicConfig,
  VoiceSettings,
} from '../../types/api';
import { TONE_PRESETS } from '../../utils/formOptions';
import { extractValidPatchEntries } from '../../utils/formPatch';
import {
  generateClientUuid,
  getOrCreateSessionId,
  getStoredVoiceSettings,
  setStoredVoiceSettings,
} from '../../utils/storage';

interface TabBarInstance {
  syncTabState(index: number): void;
}

interface VoiceOptionEntry {
  id: string;
  label: string;
  source: 'preset' | 'clone';
}

const ASR_LANGUAGES: Array<{ value: VoiceSettings['asrLanguage']; label: string }> = [
  { value: 'zh', label: '中文' },
  { value: 'en', label: 'English' },
  { value: 'ja', label: '日本語' },
  { value: 'auto', label: 'Auto' },
];

function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
}

function buildPatchLabels(patch?: RecommendFormPatch): Array<{ key: string; value: string }> {
  return extractValidPatchEntries(patch).map((entry) => ({
    key: t(`fields.${entry.key}`),
    value: entry.value,
  }));
}

function buildTexts() {
  return {
    title: t('assistant.title'),
    statusOnline: t('assistant.statusOnline'),
    statusDisabled: t('assistant.statusDisabled'),
    voiceCallBtn: t('assistant.voiceCallBtn'),
    voiceSettingsBtn: t('assistant.voiceSettingsBtn'),
    faqToggleBtn: t('assistant.faqToggleBtn'),
    faqPlaceholder: t('assistant.faqPlaceholder'),
    faqEmpty: t('assistant.faqEmpty'),
    search: t('common.search'),
    close: t('common.close'),
    quickPromptsTitle: t('assistant.quickPromptsTitle'),
    inputPlaceholder: t('assistant.inputPlaceholder'),
    sendBtn: t('assistant.sendBtn'),
    holdOrTapVoice: t('assistant.holdOrTapVoice'),
    recordingTapStop: t('assistant.recordingTapStop'),
    recognizing: t('assistant.recognizing'),
    playTts: t('assistant.playTts'),
    stopTts: t('assistant.stopTts'),
    patchTitle: t('assistant.patchTitle'),
    patchApplyOnly: t('assistant.patchApplyOnly'),
    patchApplyAndRun: t('assistant.patchApplyAndRun'),
    callTitle: t('assistant.callTitle'),
    callEndBtn: t('assistant.callEndBtn'),
    callMuteBtn: t('assistant.callMuteBtn'),
    callUnmuteBtn: t('assistant.callUnmuteBtn'),
    callSpeakBtn: t('assistant.callSpeakBtn'),
    callStopSpeakBtn: t('assistant.callStopSpeakBtn'),
    callInterruptBtn: t('assistant.callInterruptBtn'),
    settingsTitle: t('voice.settingsTitle'),
    autoPlayTts: t('voice.autoPlayTts'),
    autoSendAsr: t('voice.autoSendAsr'),
    voiceSelect: t('voice.voiceSelect'),
    tonePreset: t('voice.tonePreset'),
    asrLang: t('voice.asrLang'),
    volume: t('voice.volume'),
  };
}

function resolveCallStateLabel(cs: CallState): string {
  switch (cs) {
    case 'recording':
      return t('assistant.callStateRecording');
    case 'recognizing':
      return t('assistant.callStateRecognizing');
    case 'thinking':
      return t('assistant.callStateThinking');
    case 'speaking':
      return t('assistant.callStateSpeaking');
    case 'muted':
      return t('assistant.callStateMuted');
    case 'error':
      return t('assistant.callStateError');
    default:
      return t('assistant.callStateReady');
  }
}

function ensureRecordPermission(): Promise<boolean> {
  return new Promise((resolve) => {
    wx.getSetting({
      success(res) {
        const status = res.authSetting['scope.record'];
        if (status === true) {
          resolve(true);
          return;
        }
        if (status === false) {
          wx.showModal({
            title: t('voice.recordDenied'),
            confirmText: t('common.confirm'),
            success(modalRes) {
              if (modalRes.confirm) {
                wx.openSetting({
                  success(settingRes) {
                    resolve(Boolean(settingRes.authSetting['scope.record']));
                  },
                  fail() {
                    resolve(false);
                  },
                });
              } else {
                resolve(false);
              }
            },
          });
          return;
        }
        wx.authorize({
          scope: 'scope.record',
          success() {
            resolve(true);
          },
          fail() {
            wx.showToast({ title: t('voice.recordDenied'), icon: 'none' });
            resolve(false);
          },
        });
      },
      fail() {
        resolve(false);
      },
    });
  });
}

Page({
  data: {
    locale: getLocale(),
    sessionId: getOrCreateSessionId(),
    texts: buildTexts(),
    quickPrompts: getBundle().assistant.quickPrompts,
    assistantConfig: null as AssistantPublicConfig | null,
    voiceConfig: null as VoicePublicConfig | null,
    voiceSettings: getStoredVoiceSettings(),
    voiceOptions: [] as VoiceOptionEntry[],
    voiceOptionLabels: [] as string[],
    voiceOptionIndex: 0,
    toneOptions: TONE_PRESETS.map((tp) => ({ id: tp.id, label: t(tp.labelKey) })),
    asrLanguages: ASR_LANGUAGES,

    messages: [] as AssistantChatMessage[],
    scrollIntoId: '',
    inputText: '',
    sending: false,
    recordingMode: 'none' as 'none' | 'composer' | 'call',
    recognizing: false,
    playingMessageId: '',

    // FAQ drawer
    faqOpen: false,
    faqQuery: '',
    faqItems: [] as KnowledgeSearchItem[],
    faqLoading: false,

    // Voice settings sheet
    voiceSettingsOpen: false,

    // Call mode
    callOpen: false,
    callState: 'idle' as CallState,
    callStateLabel: resolveCallStateLabel('ready'),
    callDurationText: '00:00',
    callMuted: false,
    callTurns: [] as VoiceCallTurn[],
    callTranscript: '',
    callReplyText: '',
    callError: '',
  },

  _unsubLocale: undefined as undefined | (() => void),
  _recorder: null as WechatMiniprogram.RecorderManager | null,
  _audio: null as WechatMiniprogram.InnerAudioContext | null,
  _callTimer: 0 as number,
  _callSeconds: 0,
  _recordPurpose: 'composer' as 'composer' | 'call',

  onLoad() {
    this._unsubLocale = subscribeLocale((nextLocale) => {
      this.setData({
        locale: nextLocale,
        texts: buildTexts(),
        quickPrompts: getBundle().assistant.quickPrompts,
        toneOptions: TONE_PRESETS.map((tp) => ({ id: tp.id, label: t(tp.labelKey) })),
        callStateLabel: resolveCallStateLabel(this.data.callState),
      });
      void this.initConfigs();
    });
    this.initRecorder();
  },

  onHide() {
    this.cleanupActiveMedia();
  },

  onUnload() {
    this.cleanupActiveMedia();
    if (this._audio) {
      this._audio.destroy();
      this._audio = null;
    }
    if (this._unsubLocale) this._unsubLocale();
  },

  onShow() {
    const tabBar = typeof this.getTabBar === 'function' ? (this.getTabBar() as unknown as TabBarInstance | null) : null;
    if (tabBar && typeof tabBar.syncTabState === 'function') {
      tabBar.syncTabState(3);
    }
    wx.setNavigationBarTitle({ title: t('tabs.assistant') });
    this.setData({
      locale: getLocale(),
      texts: buildTexts(),
      quickPrompts: getBundle().assistant.quickPrompts,
      toneOptions: TONE_PRESETS.map((tp) => ({ id: tp.id, label: t(tp.labelKey) })),
    });
    void this.initConfigs();
  },

  cleanupActiveMedia() {
    if (this.data.recordingMode !== 'none' && this._recorder) {
      try {
        this._recorder.stop();
      } catch {
        // Ignore if already stopped
      }
      this.setData({ recordingMode: 'none' });
    }
    this.stopAudioPlayback();
    if (this._callTimer) {
      clearInterval(this._callTimer);
      this._callTimer = 0;
    }
  },

  initRecorder() {
    const recorder = wx.getRecorderManager();
    this._recorder = recorder;

    recorder.onStop((res) => {
      const purpose = this._recordPurpose;
      this.setData({ recordingMode: 'none' });
      if (!res.tempFilePath || (res.duration && res.duration < 450)) {
        wx.showToast({ title: t('voice.recordTooShort'), icon: 'none' });
        if (purpose === 'call' && this.data.callOpen) {
          this.updateCallState(this.data.callMuted ? 'muted' : 'ready');
        }
        return;
      }
      if (purpose === 'call') {
        void this.processCallRecording(res.tempFilePath);
      } else {
        void this.processComposerRecording(res.tempFilePath);
      }
    });

    recorder.onError((err) => {
      const purpose = this._recordPurpose;
      this.setData({ recordingMode: 'none' });
      wx.showToast({ title: (err.errMsg || t('common.unknownError')).slice(0, 28), icon: 'none' });
      if (purpose === 'call' && this.data.callOpen) {
        this.updateCallState('error', err.errMsg || '');
      }
    });
  },

  async initConfigs() {
    try {
      const [assistantCfg, voiceCfg, catalog] = await Promise.all([
        getAssistantConfig(),
        getVoiceConfig().catch(() => null),
        getVoiceCatalog().catch(() => []),
      ]);

      const options: VoiceOptionEntry[] = [];
      if (Array.isArray(catalog) && catalog.length > 0) {
        catalog.forEach((item) => {
          options.push({
            id: item.id,
            label: item.display_name || item.name || item.id,
            source: item.source === 'clone' ? 'clone' : 'preset',
          });
        });
      } else if (voiceCfg?.available_voices?.length) {
        voiceCfg.available_voices.forEach((v) => {
          options.push({ id: v, label: v, source: 'preset' });
        });
      }

      const settings = getStoredVoiceSettings();
      let selectedIdx = options.findIndex((o) => (
        settings.voiceSource === 'clone' && settings.cloneVoiceId
          ? o.id === settings.cloneVoiceId
          : o.id === settings.voice
      ));
      if (selectedIdx < 0) selectedIdx = 0;

      const messages = this.data.messages.length === 0 && assistantCfg.welcome_message
        ? [
            {
              id: 'welcome',
              role: 'assistant' as const,
              content: assistantCfg.welcome_message,
              timestamp: Date.now(),
            },
          ]
        : this.data.messages;

      this.setData({
        assistantConfig: assistantCfg,
        voiceConfig: voiceCfg,
        voiceOptions: options,
        voiceOptionLabels: options.map((o) => o.label),
        voiceOptionIndex: selectedIdx,
        messages,
      });
    } catch {
      // Keep page usable even if initial config fails
    }
  },

  onLocaleChange() {
    this.setData({
      locale: getLocale(),
      texts: buildTexts(),
      quickPrompts: getBundle().assistant.quickPrompts,
      toneOptions: TONE_PRESETS.map((tp) => ({ id: tp.id, label: t(tp.labelKey) })),
    });
    void this.initConfigs();
  },

  onInputChange(e: WechatMiniprogram.Input) {
    this.setData({ inputText: String(e.detail.value || '') });
  },

  onTapQuickPrompt(e: WechatMiniprogram.TouchEvent) {
    const text = String(e.currentTarget.dataset.text || '').trim();
    if (!text) return;
    void this.sendChatMessage(text);
  },

  onSendInput() {
    const text = this.data.inputText.trim();
    if (!text || this.data.sending) return;
    this.setData({ inputText: '' });
    void this.sendChatMessage(text);
  },

  async sendChatMessage(text: string, autoPlayOverride?: boolean) {
    const userMsg: AssistantChatMessage = {
      id: generateClientUuid('msg'),
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };
    const nextMessages = [...this.data.messages, userMsg];
    this.setData({
      messages: nextMessages,
      sending: true,
      scrollIntoId: `msg-${userMsg.id}`,
    });

    try {
      const snap = getState();
      const res = await postAssistantChat({
        session_id: this.data.sessionId,
        message: text,
        page_context: {
          view: 'assistant',
          current_form: snap.profileForm as unknown as Record<string, unknown>,
        },
        locale: getLocale(),
      });
      const patchLabels = buildPatchLabels(res.action?.form_patch);
      const assistantMsg: AssistantChatMessage = {
        id: generateClientUuid('msg'),
        role: 'assistant',
        content: res.reply,
        action: res.action,
        intent: res.intent,
        debug: res.debug,
        patchLabels,
        timestamp: Date.now(),
      };
      this.setData({
        messages: [...this.data.messages, assistantMsg],
        scrollIntoId: `msg-${assistantMsg.id}`,
      });

      const shouldSpeak = autoPlayOverride !== undefined
        ? autoPlayOverride
        : this.data.voiceSettings.autoPlayTts;
      if (shouldSpeak && this.data.voiceConfig?.tts_enabled !== false) {
        void this.playMessageTts(assistantMsg.id, assistantMsg.content);
      }
      return res;
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : t('common.networkError');
      const fallbackMsg: AssistantChatMessage = {
        id: generateClientUuid('err'),
        role: 'assistant',
        content: errMsg,
        timestamp: Date.now(),
      };
      this.setData({
        messages: [...this.data.messages, fallbackMsg],
        scrollIntoId: `msg-${fallbackMsg.id}`,
      });
      return null;
    } finally {
      this.setData({ sending: false });
    }
  },

  onApplyPatch(e: WechatMiniprogram.TouchEvent) {
    const msgId = String(e.currentTarget.dataset.id || '');
    const autoRun = String(e.currentTarget.dataset.autorun || '') === 'true';
    const msg = this.data.messages.find((m) => m.id === msgId);
    const patch = msg?.action?.form_patch;
    if (!patch) return;
    applyFormPatchToStore(patch, autoRun);
    wx.showToast({ title: t('assistant.patchAppliedToast'), icon: 'success' });
    wx.switchTab({ url: '/pages/recommend/index' });
  },

  // ---------------- Normal Voice Input & TTS ----------------

  async onToggleComposerVoice() {
    if (this.data.voiceConfig && !this.data.voiceConfig.asr_enabled) {
      wx.showToast({ title: t('voice.asrDisabled'), icon: 'none' });
      return;
    }
    if (this.data.recordingMode === 'composer' && this._recorder) {
      this._recorder.stop();
      return;
    }
    const granted = await ensureRecordPermission();
    if (!granted || !this._recorder) return;
    this.stopAudioPlayback();
    this._recordPurpose = 'composer';
    this.setData({ recordingMode: 'composer' });
    this._recorder.start({
      format: 'mp3',
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000,
      duration: 60000,
    });
  },

  async processComposerRecording(filePath: string) {
    this.setData({ recognizing: true });
    try {
      const asr = await asrRecognize(
        filePath,
        this.data.sessionId,
        this.data.voiceSettings.asrLanguage,
        'mp3',
      );
      if (!asr.success) {
        wx.showToast({
          title: (asr.error?.message || t('common.unknownError')).slice(0, 28),
          icon: 'none',
        });
        return;
      }
      const text = (asr.normalized_text || asr.text || '').trim();
      if (!text) return;
      if (this.data.voiceSettings.autoSendAsr) {
        await this.sendChatMessage(text);
      } else {
        this.setData({
          inputText: this.data.inputText ? `${this.data.inputText} ${text}` : text,
        });
      }
    } catch (err) {
      wx.showToast({
        title: (err instanceof Error ? err.message : t('common.networkError')).slice(0, 28),
        icon: 'none',
      });
    } finally {
      this.setData({ recognizing: false });
    }
  },

  onToggleMessageTts(e: WechatMiniprogram.TouchEvent) {
    const id = String(e.currentTarget.dataset.id || '');
    const msg = this.data.messages.find((m) => m.id === id);
    if (!msg) return;
    if (this.data.playingMessageId === id) {
      this.stopAudioPlayback();
      return;
    }
    if (this.data.voiceConfig && !this.data.voiceConfig.tts_enabled) {
      wx.showToast({ title: t('voice.ttsDisabled'), icon: 'none' });
      return;
    }
    void this.playMessageTts(id, msg.content);
  },

  stopAudioPlayback() {
    if (this._audio) {
      try {
        this._audio.stop();
      } catch {
        // Ignore stop errors
      }
    }
    this.setData({ playingMessageId: '' });
  },

  async playMessageTts(messageId: string, text: string): Promise<void> {
    this.stopAudioPlayback();
    this.setData({ playingMessageId: messageId });
    const vs = this.data.voiceSettings;
    try {
      const res = await ttsSynthesize({
        sessionId: this.data.sessionId,
        text,
        voice: vs.voice,
        voiceSource: vs.voiceSource,
        cloneVoiceId: vs.cloneVoiceId,
        tonePreset: vs.tonePreset,
        volume: vs.volume,
      });
      if (!res.success || !res.audio_url) {
        this.setData({ playingMessageId: '' });
        wx.showToast({ title: (res.error?.message || t('voice.ttsDisabled')).slice(0, 28), icon: 'none' });
        return;
      }
      const fullAudioUrl = resolveTtsAudioUrl(res.audio_url);
      await this.playAudioUrl(fullAudioUrl, vs.volume);
    } catch {
      this.setData({ playingMessageId: '' });
    }
  },

  playAudioUrl(url: string, volume: number): Promise<void> {
    return new Promise((resolve) => {
      if (!this._audio) {
        this._audio = wx.createInnerAudioContext();
      }
      const audio = this._audio;
      audio.offEnded();
      audio.offError();
      audio.offStop();
      audio.volume = volume;
      const done = () => {
        this.setData({ playingMessageId: '' });
        resolve();
      };
      audio.onEnded(done);
      audio.onError(done);
      audio.onStop(done);
      audio.src = url;
      audio.play();
    });
  },

  // ---------------- FAQ Search ----------------

  onToggleFaq() {
    const next = !this.data.faqOpen;
    this.setData({ faqOpen: next });
    if (next && this.data.faqItems.length === 0) {
      void this.runFaqSearch('');
    }
  },

  onFaqInput(e: WechatMiniprogram.Input) {
    this.setData({ faqQuery: String(e.detail.value || '') });
  },

  onSearchFaq() {
    void this.runFaqSearch(this.data.faqQuery.trim());
  },

  async runFaqSearch(q: string) {
    this.setData({ faqLoading: true });
    try {
      const res = await searchAssistantKnowledge(q, 8);
      this.setData({ faqItems: res.items || [] });
    } catch {
      this.setData({ faqItems: [] });
    } finally {
      this.setData({ faqLoading: false });
    }
  },

  // ---------------- Voice Settings Sheet ----------------

  onOpenVoiceSettings() {
    this.setData({ voiceSettingsOpen: true });
  },

  onCloseVoiceSettings() {
    this.setData({ voiceSettingsOpen: false });
  },

  onSwitchVoiceSetting(e: WechatMiniprogram.SwitchChange) {
    const field = String(e.currentTarget.dataset.field || '') as 'autoPlayTts' | 'autoSendAsr';
    const next: VoiceSettings = {
      ...this.data.voiceSettings,
      [field]: Boolean(e.detail.value),
    };
    setStoredVoiceSettings(next);
    this.setData({ voiceSettings: next });
  },

  onPickVoiceOption(e: WechatMiniprogram.PickerChange) {
    const idx = Number(e.detail.value) || 0;
    const item = this.data.voiceOptions[idx];
    if (!item) return;
    const next: VoiceSettings = {
      ...this.data.voiceSettings,
      voiceSource: item.source,
      voice: item.source === 'preset' ? item.id : this.data.voiceSettings.voice,
      cloneVoiceId: item.source === 'clone' ? item.id : '',
    };
    setStoredVoiceSettings(next);
    this.setData({ voiceSettings: next, voiceOptionIndex: idx });
  },

  onSelectTonePreset(e: WechatMiniprogram.TouchEvent) {
    const tone = e.currentTarget.dataset.tone as VoiceSettings['tonePreset'];
    if (!tone) return;
    const next: VoiceSettings = { ...this.data.voiceSettings, tonePreset: tone };
    setStoredVoiceSettings(next);
    this.setData({ voiceSettings: next });
  },

  onSelectAsrLang(e: WechatMiniprogram.TouchEvent) {
    const lang = e.currentTarget.dataset.lang as VoiceSettings['asrLanguage'];
    if (!lang) return;
    const next: VoiceSettings = { ...this.data.voiceSettings, asrLanguage: lang };
    setStoredVoiceSettings(next);
    this.setData({ voiceSettings: next });
  },

  onChangeVolume(e: WechatMiniprogram.SliderChange) {
    const vol = Math.max(0.2, Math.min(1.0, Number(e.detail.value) / 100));
    const next: VoiceSettings = { ...this.data.voiceSettings, volume: vol };
    setStoredVoiceSettings(next);
    this.setData({ voiceSettings: next });
  },

  // ---------------- Full-Screen Voice Call ----------------

  updateCallState(callState: CallState, errorMsg = '') {
    this.setData({
      callState,
      callStateLabel: resolveCallStateLabel(callState),
      callError: errorMsg,
    });
  },

  async onStartVoiceCall() {
    if (this.data.voiceConfig && (!this.data.voiceConfig.asr_enabled && !this.data.voiceConfig.tts_enabled)) {
      wx.showToast({ title: t('voice.asrDisabled'), icon: 'none' });
      return;
    }
    const granted = await ensureRecordPermission();
    if (!granted) return;

    this.stopAudioPlayback();
    this._callSeconds = 0;
    if (this._callTimer) clearInterval(this._callTimer);
    this._callTimer = setInterval(() => {
      this._callSeconds += 1;
      this.setData({ callDurationText: formatDuration(this._callSeconds) });
    }, 1000) as unknown as number;

    this.setData({
      callOpen: true,
      callMuted: false,
      callDurationText: '00:00',
      callTurns: [],
      callTranscript: '',
      callReplyText: '',
      callError: '',
    });
    this.updateCallState('ready');
  },

  onHangUpCall() {
    this.cleanupActiveMedia();
    this.setData({
      callOpen: false,
      callState: 'ended',
    });
  },

  onToggleCallMute() {
    const nextMuted = !this.data.callMuted;
    if (nextMuted && this.data.recordingMode === 'call' && this._recorder) {
      this._recorder.stop();
    }
    this.setData({ callMuted: nextMuted });
    this.updateCallState(nextMuted ? 'muted' : 'ready');
  },

  onInterruptCallTts() {
    this.stopAudioPlayback();
    if (this.data.callOpen) {
      this.updateCallState(this.data.callMuted ? 'muted' : 'ready');
    }
  },

  onToggleCallSpeak() {
    if (!this.data.callOpen || !this._recorder) return;
    if (this.data.callMuted) {
      this.setData({ callMuted: false });
    }
    if (this.data.callState === 'recording') {
      this._recorder.stop();
      return;
    }
    if (['recognizing', 'thinking'].includes(this.data.callState)) return;
    if (this.data.callState === 'speaking') {
      this.stopAudioPlayback();
    }
    this._recordPurpose = 'call';
    this.setData({ recordingMode: 'call', callError: '' });
    this.updateCallState('recording');
    this._recorder.start({
      format: 'mp3',
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000,
      duration: 60000,
    });
  },

  async processCallRecording(filePath: string) {
    if (!this.data.callOpen) return;
    this.updateCallState('recognizing');
    try {
      const asr = await asrRecognize(
        filePath,
        this.data.sessionId,
        this.data.voiceSettings.asrLanguage,
        'mp3',
      );
      if (!this.data.callOpen) return;
      const userText = (asr.normalized_text || asr.text || '').trim();
      if (!asr.success || !userText) {
        this.updateCallState('error', asr.error?.message || t('voice.recordTooShort'));
        return;
      }
      this.setData({ callTranscript: userText });
      this.updateCallState('thinking');

      const chatRes = await this.sendChatMessage(userText, false);
      if (!this.data.callOpen) return;
      if (!chatRes) {
        this.updateCallState('error', t('common.networkError'));
        return;
      }

      const turn: VoiceCallTurn = {
        id: generateClientUuid('turn'),
        userText,
        assistantText: chatRes.reply,
        startedAt: Date.now(),
        endedAt: Date.now(),
      };
      this.setData({
        callReplyText: chatRes.reply,
        callTurns: [...this.data.callTurns, turn],
      });

      if (this.data.voiceConfig?.tts_enabled !== false) {
        this.updateCallState('speaking');
        await this.playMessageTts(turn.id, chatRes.reply);
      }
      if (this.data.callOpen) {
        this.updateCallState(this.data.callMuted ? 'muted' : 'ready');
      }
    } catch (err) {
      if (this.data.callOpen) {
        this.updateCallState('error', err instanceof Error ? err.message : t('common.unknownError'));
      }
    }
  },
});
