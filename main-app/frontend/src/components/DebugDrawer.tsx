import React, { useState } from 'react';
import { isAxiosError } from 'axios';
import { getDebugErrorCodes, getDebugRecentErrors } from '../api';
import { useTranslation } from 'react-i18next';

export const DebugDrawer: React.FC = () => {
  const { t } = useTranslation(['common', 'errors']);
  const [isOpen, setIsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'codes' | 'recent'>('codes');
  const [data, setData] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const handleOpen = async () => {
    setIsOpen(true);
    fetchData('codes');
  };

  const fetchData = async (tab: 'codes' | 'recent') => {
    setActiveTab(tab);
    setLoading(true);
    try {
      if (tab === 'codes') {
        const res = await getDebugErrorCodes();
        setData(res);
      } else {
        const res = await getDebugRecentErrors();
        setData(res);
      }
    } catch (e: unknown) {
      if (isAxiosError(e)) {
        setData({ error: t('errors:default'), response: e.response?.data ?? null, details: e.message });
      } else if (e instanceof Error) {
        setData({ error: t('errors:default'), details: e.message });
      } else {
        setData({ error: t('errors:default') });
      }
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) {
    return (
      <button
        type="button"
        className="debug-drawer-trigger"
        aria-label={t('common:common.debugTools')}
        onClick={handleOpen}
        style={{
          position: 'fixed',
          bottom: 'calc(16px + env(safe-area-inset-bottom, 0px))',
          left: 'calc(16px + env(safe-area-inset-left, 0px))',
          zIndex: 'var(--z-debug-button, 840)',
          background: 'rgba(255,255,255,0.1)',
          border: '1px solid rgba(255,255,255,0.2)',
          color: '#94A3B8',
          padding: '8px 12px',
          minHeight: 44,
          minWidth: 44,
          borderRadius: 999,
          fontSize: 12,
          cursor: 'pointer',
          backdropFilter: 'blur(10px)',
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        🐛 {t('common:common.debugTools')}
      </button>
    );
  }

  return (
    <>
      <div
        onClick={() => setIsOpen(false)}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.45)',
          zIndex: 'calc(var(--z-debug-drawer, 1350) - 1)',
        }}
      />
      <div style={{
        position: 'fixed',
        top: 0,
        left: 0,
        bottom: 0,
        width: 'min(400px, 100vw)',
        height: '100dvh',
        background: 'rgba(11, 11, 14, 0.96)',
        backdropFilter: 'blur(20px)',
        borderRight: '1px solid rgba(255,255,255,0.1)',
        zIndex: 'var(--z-debug-drawer, 1350)',
        padding: 'calc(16px + env(safe-area-inset-top, 0px)) 16px calc(16px + env(safe-area-inset-bottom, 0px))',
        boxShadow: '10px 0 30px rgba(0,0,0,0.5)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <h3 style={{ fontSize: 18, fontWeight: 600 }}>{t('common:common.debugTools')}</h3>
          <button type="button" className="btn-secondary" style={{ minHeight: 44, minWidth: 44 }} onClick={() => setIsOpen(false)}>
            {t('common:common.close')}
          </button>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
          <button
            type="button"
            className={activeTab === 'codes' ? 'btn-secondary' : 'modern-input'}
            style={{ width: 'auto', minHeight: 44, padding: '8px 14px' }}
            onClick={() => fetchData('codes')}
          >{t('common:common.errorCodes')}</button>
          <button
            type="button"
            className={activeTab === 'recent' ? 'btn-secondary' : 'modern-input'}
            style={{ width: 'auto', minHeight: 44, padding: '8px 14px' }}
            onClick={() => fetchData('recent')}
          >{t('common:common.recentErrors')}</button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', background: 'rgba(0,0,0,0.3)', borderRadius: 8, padding: 16, border: '1px solid rgba(255,255,255,0.05)' }}>
          {loading ? (
            <div style={{ color: '#94A3B8' }}>{t('common:common.loading')}</div>
          ) : (
            <pre style={{ fontSize: 11, color: '#38BDF8', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
              {JSON.stringify(data, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </>
  );
};
