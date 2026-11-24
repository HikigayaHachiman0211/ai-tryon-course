import { TriangleAlert } from 'lucide-react';
import { motion } from 'framer-motion';
import type { ErrorResponse } from '../types';
import { useTranslation } from 'react-i18next';

interface ErrorBannerProps {
  error: ErrorResponse['error'];
}

export function ErrorBanner({ error }: ErrorBannerProps) {
  const { t, i18n } = useTranslation(['errors', 'common']);
  const translatedMessage = i18n.exists(`errors:${error.code}`)
    ? t(`errors:${error.code}`)
    : t('errors:default');
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)', padding: 20, borderRadius: 12 }}
    >
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        <TriangleAlert color="#EF4444" size={24} style={{ flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <h4 style={{ color: '#F8FAFC', margin: 0, fontSize: 16 }}>{translatedMessage}</h4>
          <p style={{ color: '#FCA5A5', fontSize: 13, margin: '4px 0 0 0' }}>{t('errors:codeLabel', { code: error.code })}</p>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 11, margin: '8px 0 0 0', fontFamily: 'monospace' }}>{t('errors:requestId', { requestId: error.request_id || 'unknown' })}</p>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 12, margin: '8px 0 0 0' }}>{t('errors:troubleshooting')}</p>
        </div>
      </div>
    </motion.div>
  );
}
