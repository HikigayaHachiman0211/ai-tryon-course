import { useCallback, useEffect, useState } from 'react';
import { Clock, Loader2, Sparkles, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { getHistory } from '../api';
import type { HistoryEntry } from '../types';

interface HistoryDrawerProps {
  open: boolean;
  onClose: () => void;
  onSelect: (entry: HistoryEntry) => void;
}

export function HistoryDrawer({ open, onClose, onSelect }: HistoryDrawerProps) {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await getHistory(50);
      setEntries(response.items);
    } catch {
      setError('加载历史记录失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      void loadHistory();
    }
  }, [open, loadHistory]);

  const formatTime = (iso: string) => {
    try {
      const date = new Date(iso);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMin = Math.floor(diffMs / 60_000);

      if (diffMin < 1) return '刚刚';
      if (diffMin < 60) return `${diffMin} 分钟前`;

      const diffHour = Math.floor(diffMin / 60);
      if (diffHour < 24) return `${diffHour} 小时前`;

      const diffDay = Math.floor(diffHour / 24);
      if (diffDay < 7) return `${diffDay} 天前`;

      return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
    } catch {
      return iso;
    }
  };

  const typeLabel = (type: string) =>
    type === 'recommend' ? '智能推荐' : '自定义搭配';

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
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 28, stiffness: 300 }}
          >
            <div className="history-drawer-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Clock size={18} color="var(--accent-blue-text)" />
                <h2 style={{ fontSize: 18, fontWeight: 600 }}>历史记录</h2>
              </div>
              <button className="history-close-btn" onClick={onClose} type="button">
                <X size={18} />
              </button>
            </div>

            <div className="history-drawer-body">
              {loading && (
                <div className="history-empty-state">
                  <Loader2 className="animate-spin" size={24} color="var(--text-tertiary)" />
                  <div style={{ marginTop: 12 }}>加载中…</div>
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
                  <div>还没有记录</div>
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 6 }}>
                    完成一次推荐或搭配分析后，记录会自动出现在这里。
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
                            alt="缩略图"
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
                            <span>{entry.item_count} 件</span>
                          )}
                          {entry.total_score !== null && (
                            <span>评分 {entry.total_score.toFixed(1)}</span>
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
