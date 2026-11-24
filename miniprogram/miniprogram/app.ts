import { getEndpointConfig } from './config/env';
import { getLocale } from './i18n';
import { getOrCreateSessionId, getVisitorToken } from './utils/storage';

export interface AppGlobalData {
  sessionId: string;
  visitorToken: string;
}

App<{ globalData: AppGlobalData }>({
  globalData: {
    sessionId: '',
    visitorToken: '',
  },
  onLaunch() {
    getEndpointConfig();
    getLocale();
    this.globalData.sessionId = getOrCreateSessionId();
    this.globalData.visitorToken = getVisitorToken();
  },
});
