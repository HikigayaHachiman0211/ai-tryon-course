import React, { useState } from 'react';
import { isAxiosError } from 'axios';
import { getDebugErrorCodes, getDebugRecentErrors } from '../api';

export const DebugDrawer: React.FC = () => {
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
        setData({ error: '调试接口请求失败', response: e.response?.data ?? null, details: e.message });
      } else if (e instanceof Error) {
        setData({ error: '调试接口请求失败', details: e.message });
      } else {
        setData({ error: '调试请求失败，原因未知' });
      }
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) {
    return (
      <button 
        onClick={handleOpen}
        style={{
          position: 'fixed', bottom: 16, right: 16, 
          zIndex: 1000, 
          background: 'rgba(255,255,255,0.1)',
          border: '1px solid rgba(255,255,255,0.2)',
          color: '#94A3B8',
          padding: '8px 12px',
          borderRadius: '16px',
          fontSize: '12px',
          cursor: 'pointer',
          backdropFilter: 'blur(10px)'
        }}
      >
        🐛 调试工具
      </button>
    );
  }

  return (
    <div style={{
      position: 'fixed', top: 0, right: 0, bottom: 0, width: '400px',
      background: 'rgba(11, 11, 14, 0.95)',
      backdropFilter: 'blur(20px)',
      borderLeft: '1px solid rgba(255,255,255,0.1)',
      zIndex: 1001,
      padding: '24px',
      boxShadow: '-10px 0 30px rgba(0,0,0,0.5)',
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h3 style={{ fontSize: '18px', fontWeight: 600 }}>开发调试工具</h3>
        <button className="btn-secondary" onClick={() => setIsOpen(false)}>关闭</button>
      </div>

      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
        <button 
          className={activeTab === 'codes' ? 'btn-secondary' : 'modern-input'} 
          style={{ width: 'auto', padding: '6px 12px' }}
          onClick={() => fetchData('codes')}
        >错误码</button>
        <button 
          className={activeTab === 'recent' ? 'btn-secondary' : 'modern-input'} 
          style={{ width: 'auto', padding: '6px 12px' }}
          onClick={() => fetchData('recent')}
        >最近错误</button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', background: 'rgba(0,0,0,0.3)', borderRadius: '8px', padding: '16px', border: '1px solid rgba(255,255,255,0.05)' }}>
        {loading ? (
          <div style={{ color: '#94A3B8' }}>加载中...</div>
        ) : (
          <pre style={{ fontSize: '11px', color: '#38BDF8', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
            {JSON.stringify(data, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
};
