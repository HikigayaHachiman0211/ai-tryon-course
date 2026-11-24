import { getEndpointConfig } from '../config/env';
import { getLocale } from '../i18n';
import type {
  AssistantChatRequest,
  AssistantChatResponse,
  AssistantPublicConfig,
  KnowledgeSearchResponse,
} from '../types/api';
import { requestJson } from '../utils/request';
import { joinUrl } from '../utils/url';

function mainUrl(path: string): string {
  return joinUrl(getEndpointConfig().mainApiBaseUrl, path);
}

export function getAssistantConfig(): Promise<AssistantPublicConfig> {
  return requestJson<AssistantPublicConfig>({
    url: mainUrl('/api/assistant/config/public'),
    method: 'GET',
    query: { locale: getLocale() },
    timeout: 10000,
  });
}

export function postAssistantChat(data: AssistantChatRequest): Promise<AssistantChatResponse> {
  return requestJson<AssistantChatResponse>({
    url: mainUrl('/api/assistant/chat'),
    method: 'POST',
    data: {
      ...data,
      locale: data.locale ?? getLocale(),
    },
    timeout: 60000,
  });
}

export function searchAssistantKnowledge(q: string, limit = 6): Promise<KnowledgeSearchResponse> {
  return requestJson<KnowledgeSearchResponse>({
    url: mainUrl('/api/assistant/knowledge/search'),
    method: 'GET',
    query: {
      q,
      limit,
      locale: getLocale(),
    },
    timeout: 15000,
  });
}
