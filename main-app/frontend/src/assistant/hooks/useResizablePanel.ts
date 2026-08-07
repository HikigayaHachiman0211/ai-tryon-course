import { useCallback, useLayoutEffect, useRef, useState } from 'react';

export type PanelSizePreset = 'compact' | 'default' | 'large' | 'wide' | 'custom';

export interface PanelSize {
  width: number;
  height: number;
  preset?: PanelSizePreset;
}

const STORAGE_KEY_SIZE = 'assistant_panel_size';
const STORAGE_KEY_PRESET = 'assistant_panel_size_preset';

const PRESETS: Record<Exclude<PanelSizePreset, 'custom'>, PanelSize> = {
  compact: { width: 340, height: 480, preset: 'compact' },
  default: { width: 420, height: 620, preset: 'default' },
  large: { width: 520, height: 720, preset: 'large' },
  wide: { width: 680, height: 720, preset: 'wide' },
};

const MIN_WIDTH = 320;
const MIN_HEIGHT = 420;

function getMaxWidth(): number {
  return Math.min(720, window.innerWidth - 32);
}

function getMaxHeight(): number {
  return window.innerHeight - 96;
}

function clampSize(w: number, h: number): { width: number; height: number } {
  return {
    width: Math.max(MIN_WIDTH, Math.min(w, getMaxWidth())),
    height: Math.max(MIN_HEIGHT, Math.min(h, getMaxHeight())),
  };
}

function loadSavedSize(): PanelSize {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_SIZE);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (typeof parsed.width === 'number' && typeof parsed.height === 'number') {
        const clamped = clampSize(parsed.width, parsed.height);
        const preset = (localStorage.getItem(STORAGE_KEY_PRESET) as PanelSizePreset) || 'custom';
        return { ...clamped, preset };
      }
    }
  } catch {
    // ignore
  }
  return { ...PRESETS.default };
}

function saveSize(size: PanelSize): void {
  try {
    localStorage.setItem(STORAGE_KEY_SIZE, JSON.stringify({ width: size.width, height: size.height }));
    if (size.preset) {
      localStorage.setItem(STORAGE_KEY_PRESET, size.preset);
    }
  } catch {
    // ignore
  }
}

type ResizeDirection = 'right' | 'bottom' | 'bottom-right';

export interface UseResizablePanelReturn {
  width: number;
  height: number;
  preset: PanelSizePreset;
  setPreset: (preset: PanelSizePreset) => void;
  resetToDefault: () => void;
  /** Returns pointer event handlers for a given resize direction */
  getResizeHandleProps: (dir: ResizeDirection) => React.HTMLAttributes<HTMLElement>;
}

export function useResizablePanel(): UseResizablePanelReturn {
  const [size, setSize] = useState<PanelSize>(loadSavedSize);
  const sizeRef = useRef(size);
  useLayoutEffect(() => {
    sizeRef.current = size;
  });

  const setPreset = useCallback((preset: PanelSizePreset) => {
    if (preset === 'custom') return;
    const next = { ...PRESETS[preset], preset };
    const clamped = clampSize(next.width, next.height);
    const result = { ...clamped, preset };
    setSize(result);
    saveSize(result);
  }, []);

  const resetToDefault = useCallback(() => {
    setPreset('default');
  }, [setPreset]);

  const getResizeHandleProps = useCallback((dir: ResizeDirection): React.HTMLAttributes<HTMLElement> => {
    const onPointerDown = (e: React.PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const target = e.currentTarget as HTMLElement;
      target.setPointerCapture(e.pointerId);

      const startX = e.clientX;
      const startY = e.clientY;
      const startW = sizeRef.current.width;
      const startH = sizeRef.current.height;

      document.body.classList.add('assistant-resizing');
      document.body.style.userSelect = 'none';

      const onPointerMove = (ev: PointerEvent) => {
        const dx = ev.clientX - startX;
        const dy = ev.clientY - startY;
        let newW = startW;
        let newH = startH;

        if (dir === 'right' || dir === 'bottom-right') {
          newW = startW + dx;
        }
        if (dir === 'bottom' || dir === 'bottom-right') {
          newH = startH + dy;
        }

        const clamped = clampSize(newW, newH);
        setSize({ ...clamped, preset: 'custom' });
      };

      const onPointerUp = () => {
        document.removeEventListener('pointermove', onPointerMove);
        document.removeEventListener('pointerup', onPointerUp);
        document.body.classList.remove('assistant-resizing');
        document.body.style.userSelect = '';
        saveSize(sizeRef.current);
      };

      document.addEventListener('pointermove', onPointerMove);
      document.addEventListener('pointerup', onPointerUp);
    };

    const cursorMap: Record<ResizeDirection, string> = {
      right: 'ew-resize',
      bottom: 'ns-resize',
      'bottom-right': 'nwse-resize',
    };

    return {
      onPointerDown,
      style: {
        position: 'absolute' as const,
        cursor: cursorMap[dir],
        zIndex: 10,
        ...(dir === 'right' ? { top: 0, right: -3, width: 6, height: '100%' } : {}),
        ...(dir === 'bottom' ? { bottom: -3, left: 0, width: '100%', height: 6 } : {}),
        ...(dir === 'bottom-right' ? { bottom: -4, right: -4, width: 16, height: 16 } : {}),
      },
    };
  }, []);

  return { width: size.width, height: size.height, preset: size.preset || 'custom', setPreset, resetToDefault, getResizeHandleProps };
}
