import { useCallback, useEffect, useState } from 'react';
import { Clock, Loader2, Sparkles, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { getHistory } from '../api';
import type { HistoryEntry } from '../types';
import { useTranslation } from 'react-i18next';
import i18n from '../i18n';
import { formatDateTime, formatRelative } from '../i18n/formatters';
import { DEFAULT_LOCALE, normalizeLocale } from '../i18n/locale';

interface HistoryDrawerProps {
  open: boolean;
  onClose: () => void;
  onSelect: (entry: HistoryEntry) => void;
}

export function HistoryDrawer({ open, onClose, onSelect }: HistoryDrawerProps) {
  const { t } = useTranslation(['history', 'common']);
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isMobileSheet, setIsMobileSheet] = useState(() => (
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(max-width: 768px)').matches
      : false
  ));

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(max-width: 768px)');
    const sync = () => setIsMobileSheet(mq.matches);
    sync();
    mq.addEventListener?.('change', sync);
    return () => mq.removeEventListener?.('change', sync);
  }, []);

  useEffect(() => {
    if (!open || typeof document === 'undefined') return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await getHistory(50);
      setEntries(response.items);
    } catch {
      setError(t('history:loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (open) {
      void loadHistory();
    }
  }, [open, loadHistory]);

  useEffect(() => {
    const handleLocaleChange = () => {
      if (open) void loadHistory();
    };
    window.addEventListener('localechange', handleLocaleChange);
    return () => window.removeEventListener('localechange', handleLocaleChange);
  }, [open, loadHistory]);

  const formatTime = (iso: string) => {
    try {
      const date = new Date(iso);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMin = Math.floor(diffMs / 60_000);
      const locale = normalizeLocale(i18n.resolvedLanguage) ?? DEFAULT_LOCALE;

      if (diffMin < 1) return t('history:relative.now');
      if (diffMin < 60) return formatRelative(-diffMin, 'minute', locale);

      const diffHour = Math.floor(diffMin / 60);
      if (diffHour < 24) return formatRelative(-diffHour, 'hour', locale);

      const diffDay = Math.floor(diffHour / 24);
      if (diffDay < 7) return formatRelative(-diffDay, 'day', locale);

      return formatDateTime(date, locale, { month: 'short', day: 'numeric' });
    } catch {
      return iso;
    }
  };

  const typeLabel = (type: string) =>
    type === 'recommend' ? t('history:type.recommend') : t('history:type.styleLab');

  const typeBadgeClass = (type: string) =>
    type === 'recommend' ? 'history-badge-recommend' : 'history-badge-lab';

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            className="history-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />

          {/* Drawer */}
          <motion.aside
            className="history-drawer"
            initial={isMobileSheet ? { y: '100%' } : { x: '100%' }}
            animate={isMobileSheet ? { y: 0 } : { x: 0 }}
            exit={isMobileSheet ? { y: '100%' } : { x: '100%' }}
            transition={{ type: 'spring', damping: 28, stiffness: 300 }}
          >
            <div className="history-drawer-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Clock size={18} color="var(--accent-blue-text)" />
                <h2 style={{ fontSize: 18, fontWeight: 600 }}>{t('history:title')}</h2>
              </div>
              <button className="history-close-btn" onClick={onClose} type="button" aria-label={t('history:close')} title={t('history:close')}>
                <X size={18} />
              </button>
            </div>

            <div className="history-drawer-body">
              {loading && (
                <div className="history-empty-state">
                  <Loader2 className="animate-spin" size={24} color="var(--text-tertiary)" />
                  <div style={{ marginTop: 12 }}>{t('history:loading')}</div>
                </div>
              )}

              {!loading && error && (
                <div className="history-empty-state" style={{ color: '#FCA5A5' }}>
                  {error}
                </div>
              )}

              {!loading && !error && entries.length === 0 && (
                <div className="history-empty-state">
                  <Sparkles size={28} style={{ opacity: 0.4, marginBottom: 12 }} />
                  <div>{t('history:empty')}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 6 }}>
                    {t('history:emptyHint')}
                  </div>
                </div>
              )}

              {!loading && entries.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {entries.map((entry) => (
                    <button
                      key={entry.id}
                      className="history-card"
                      type="button"
                      onClick={() => onSelect(entry)}
                    >
                      {/* Thumbnail */}
                      <div className="history-thumb-wrapper">
                        {entry.thumbnail_url ? (
                          <img
                            src={entry.thumbnail_url}
                            alt={t('history:thumbnailAlt')}
                            className="history-thumb-img"
                            onError={(e) => {
                              e.currentTarget.style.display = 'none';
                            }}
                          />
                        ) : (
                          <div className="history-thumb-placeholder">
                            <Sparkles size={16} />
                          </div>
                        )}
                      </div>

                      {/* Info */}
                      <div style={{ flex: 1, minWidth: 0, textAlign: 'left' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                          <span className={`history-badge ${typeBadgeClass(entry.type)}`}>
                            {typeLabel(entry.type)}
                          </span>
                          <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                            {formatTime(entry.timestamp)}
                          </span>
                        </div>

                        <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {entry.summary}
                        </div>

                        <div style={{ display: 'flex', gap: 12, marginTop: 6, fontSize: 11, color: 'var(--text-tertiary)' }}>
                          {entry.item_count > 0 && (
                            <span>{t('history:count', { count: entry.item_count })}</span>
                          )}
                          {entry.total_score !== null && (
                            <span>{t('history:score', { score: entry.total_score.toFixed(1) })}</span>
                          )}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
