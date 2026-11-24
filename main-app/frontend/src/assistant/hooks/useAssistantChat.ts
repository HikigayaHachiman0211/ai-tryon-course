import { useCallback, useState } from 'react';
import { postAssistantChat } from '../../api';
import type { AssistantChatMessage } from '../assistantTypes';
import { getSessionId } from '../utils/session';
import i18n from '../../i18n';
import { DEFAULT_LOCALE, normalizeLocale } from '../../i18n/locale';
import { useTranslation } from 'react-i18next';

function createId(): string {
  return `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export function useAssistantChat(currentView: string, currentForm: Record<string, unknown>) {
  const { t } = useTranslation('assistant');
  const [messages, setMessages] = useState<AssistantChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || loading) return;

    const userMessage: AssistantChatMessage = {
      id: createId(),
      role: 'user',
      content: text.trim(),
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);
    setError(null);

    try {
      const response = await postAssistantChat({
        session_id: getSessionId(),
        message: text.trim(),
        page_context: {
          view: currentView,
          current_form: currentForm,
        },
        locale: normalizeLocale(i18n.resolvedLanguage) ?? DEFAULT_LOCALE,
      });

      const assistantMessage: AssistantChatMessage = {
        id: createId(),
        role: 'assistant',
        content: response.reply,
        action: response.action,
        intent: response.intent,
        debug: response.debug,
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch {
      setError(t('sendFailed'));
      const errorMessage: AssistantChatMessage = {
        id: createId(),
        role: 'assistant',
        content: t('messageFailed'),
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  }, [currentView, currentForm, loading, t]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  return { messages, loading, error, sendMessage, clearMessages };
}
