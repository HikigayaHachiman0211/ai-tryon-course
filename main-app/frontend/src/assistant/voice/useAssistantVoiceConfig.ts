/* Hook to load and manage public voice configuration from the backend */

import { useCallback, useEffect, useState } from 'react';
import { getVoiceConfig } from './voiceApi';
import type { VoicePublicConfig } from './voiceTypes';

const FALLBACK_CONFIG: VoicePublicConfig = {
  asr_enabled: false,
  tts_enabled: false,
  voice_clone_enabled: false,
  default_asr_provider: 'mimo_asr',
  default_asr_model: 'mimo-v2.5-asr',
  default_tts_provider: 'mimo_tts',
  default_tts_model: 'mimo-v2.5-tts',
  default_voice: '茉莉',
  available_voices: ['冰糖', '茉莉', '苏打', '白桦', 'Mia', 'Chloe', 'Milo', 'Dean'],
  published_clone_voices: [],
  asr_languages: ['zh', 'en', 'auto'],
  max_record_seconds: 15,
  hard_max_record_seconds: 55,
  max_audio_base64_mb: 10,
  supported_audio_formats: ['wav', 'mp3'],
  default_language: 'zh',
  max_tts_text_length: 300,
};

export function useAssistantVoiceConfig() {
  const [config, setConfig] = useState<VoicePublicConfig>(FALLBACK_CONFIG);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getVoiceConfig();
      setConfig(data);
    } catch {
      setError('Failed to load voice config');
      setConfig(FALLBACK_CONFIG);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return { config, loading, error, reload: load };
}
