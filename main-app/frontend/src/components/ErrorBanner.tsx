import { TriangleAlert } from 'lucide-react';
import { motion } from 'framer-motion';
import type { ErrorResponse } from '../types';

interface ErrorBannerProps {
  error: ErrorResponse['error'];
}

export function ErrorBanner({ error }: ErrorBannerProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)', padding: 20, borderRadius: 12 }}
    >
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        <TriangleAlert color="#EF4444" size={24} />
        <div>
          <h4 style={{ color: '#F8FAFC', margin: 0, fontSize: 16 }}>{error.message}</h4>
          <p style={{ color: '#FCA5A5', fontSize: 13, margin: '4px 0 0 0' }}>错误码：{error.code}</p>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 11, margin: '8px 0 0 0', fontFamily: 'monospace' }}>请求 ID：{error.request_id}</p>
        </div>
      </div>
    </motion.div>
  );
}
