import { useCallback, useEffect, useState } from 'react';
import { getAssistantConfig } from '../../api';
import type { AssistantPublicConfig } from '../../api';

export function useAssistantConfig() {
  const [config, setConfig] = useState<AssistantPublicConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadConfig = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getAssistantConfig();
      setConfig(data);
    } catch {
      setError('Failed to load assistant config');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadConfig();
  }, [loadConfig]);

  return { config, loading, error, reload: loadConfig };
}
