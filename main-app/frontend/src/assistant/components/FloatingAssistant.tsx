import React, { useCallback, useEffect, useRef, useState } from 'react';
import { MessageCircle } from 'lucide-react';
import type { RecommendFormPatch } from '../assistantTypes';
import { ChatPanel } from './ChatPanel';
import { useResizablePanel } from '../hooks/useResizablePanel';

/* z-index layer constants — must match CSS variables in index.css */
const Z_BUTTON = 'var(--z-assistant-button)'; // 850
const Z_PANEL = 'var(--z-assistant-panel)';    // 900

/* Selectors for elements that must never be covered by the assistant */
const AVOID_SELECTORS = [
  '.ant-notification',
  '.ant-message',
  '.global-error',
  '.error-toast',
  '.debug-error-panel',
  '.app-notification',
  '[data-error-panel]',
].join(', ');

interface Props {
  currentView: string;
  currentForm: Record<string, unknown>;
  onFormPatch: (patch: RecommendFormPatch) => void;
  onSubmitRecommend: () => void;
  onFillAndSubmit: (patch: RecommendFormPatch) => void;
}

export const FloatingAssistant: React.FC<Props> = ({
  currentView,
  currentForm,
  onFormPatch,
  onSubmitRecommend,
  onFillAndSubmit,
}) => {
  const [open, setOpen] = useState(false);
  const [avoiding, setAvoiding] = useState(false);
  const observerRef = useRef<MutationObserver | null>(null);
  const panel = useResizablePanel();

  /* MutationObserver: detect error/toast panels and shift assistant away */
  useEffect(() => {
    const check = () => {
      const found = !!document.querySelector(AVOID_SELECTORS);
      setAvoiding(found);
    };

    check();
    observerRef.current = new MutationObserver(() => check());
    observerRef.current.observe(document.body, { childList: true, subtree: true });

    return () => {
      observerRef.current?.disconnect();
      observerRef.current = null;
    };
  }, []);

  const handleClose = useCallback(() => {
    setOpen(false);
  }, []);

  const avoidClass = avoiding ? 'assistant--avoid-error' : '';

  return (
    <>
      {/* Floating button */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className={`floating-assistant-btn ${avoidClass}`}
          style={{
            position: 'fixed',
            bottom: avoiding ? 80 : 24,
            right: 24,
            width: 56,
            height: 56,
            borderRadius: '50%',
            background: 'linear-gradient(135deg, #0071e3, #005bb5)',
            border: 'none',
            boxShadow: '0 4px 20px rgba(0, 113, 227, 0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            zIndex: Z_BUTTON,
            transition: 'transform 0.2s, box-shadow 0.2s, bottom 0.3s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = 'scale(1.1)';
            e.currentTarget.style.boxShadow = '0 6px 28px rgba(0, 113, 227, 0.6)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = 'scale(1)';
            e.currentTarget.style.boxShadow = '0 4px 20px rgba(0, 113, 227, 0.4)';
          }}
        >
          <MessageCircle size={24} color="#fff" />
        </button>
      )}

      {/* Chat panel overlay */}
      {open && (
        <div
          className={`floating-assistant-panel ${avoidClass}`}
          style={{
            position: 'fixed',
            bottom: avoiding ? 80 : 24,
            right: 24,
            width: panel.width,
            maxWidth: 'calc(100vw - 48px)',
            height: panel.height,
            maxHeight: 'calc(100vh - 120px)',
            zIndex: Z_PANEL,
            boxShadow: '0 20px 60px rgba(0, 0, 0, 0.5)',
            borderRadius: 20,
            overflow: 'hidden',
            transition: 'bottom 0.3s',
          }}
        >
          <ChatPanel
            currentView={currentView}
            currentForm={currentForm}
            onFormPatch={onFormPatch}
            onSubmitRecommend={onSubmitRecommend}
            onFillAndSubmit={onFillAndSubmit}
            onClose={handleClose}
          />
        </div>
      )}

      {/* Responsive + avoidance styles */}
      <style>{`
        .assistant-resizing {
          user-select: none !important;
          -webkit-user-select: none !important;
          cursor: nwse-resize !important;
        }
        .assistant-resizing * {
          pointer-events: none !important;
        }
        @supports (padding-bottom: env(safe-area-inset-bottom)) {
          .floating-assistant-panel {
            padding-bottom: env(safe-area-inset-bottom);
          }
        }
        @media (max-width: 768px) {
          .floating-assistant-panel {
            bottom: 0 !important;
            right: 0 !important;
            left: 0 !important;
            width: 100vw !important;
            max-width: 100vw !important;
            height: calc(100vh - 60px) !important;
            max-height: calc(100vh - 60px) !important;
            border-radius: 20px 20px 0 0 !important;
          }
          .floating-assistant-btn {
            bottom: calc(16px + env(safe-area-inset-bottom, 0px)) !important;
            right: 16px !important;
          }
          .floating-assistant-btn.assistant--avoid-error {
            bottom: calc(80px + env(safe-area-inset-bottom, 0px)) !important;
          }
        }
      `}</style>
    </>
  );
};
