import React, { useEffect, useRef } from 'react';
import { useI18n } from '../i18n';
import { startPanelResize } from '../lib/panelResize';

interface PanelResizeHandleProps {
  panelRef: React.RefObject<HTMLElement>;
  side: 'left' | 'right';
  width: number;
  minWidth: number;
  maxWidth: number;
  defaultWidth: number;
  onWidthChange: (width: number) => void;
  onDraggingChange?: (dragging: boolean) => void;
}

export function PanelResizeHandle({
  panelRef,
  side,
  width,
  minWidth,
  maxWidth,
  defaultWidth,
  onWidthChange,
  onDraggingChange,
}: PanelResizeHandleProps): React.ReactElement {
  const { t } = useI18n();
  const cleanup = useRef<(() => void) | null>(null);
  useEffect(() => () => cleanup.current?.(), [minWidth, maxWidth]);
  const direction = side === 'left' ? 1 : -1;
  const commit = (value: number): void =>
    onWidthChange(Math.max(minWidth, Math.min(maxWidth, value)));
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={t(side === 'left' ? 'sidebar.resizeLeft' : 'sidebar.resizeRight')}
      aria-valuemin={minWidth}
      aria-valuemax={Math.round(maxWidth)}
      aria-valuenow={Math.round(width)}
      tabIndex={0}
      title={t('sidebar.resizeHint')}
      className={`absolute inset-y-0 ${side === 'left' ? '-right-1' : '-left-1'} z-50 w-2 cursor-col-resize touch-none hover:bg-brutal-blue/30 focus-visible:bg-brutal-blue/30 focus-visible:outline-none active:bg-brutal-blue/50`}
      onPointerDown={(event) => {
        if (event.button !== 0 || !event.isPrimary || !panelRef.current) return;
        event.preventDefault();
        event.stopPropagation();
        cleanup.current?.();
        onDraggingChange?.(true);
        cleanup.current = startPanelResize({
          panel: panelRef.current,
          handle: event.currentTarget,
          pointerId: event.pointerId,
          startX: event.clientX,
          direction,
          minWidth,
          maxWidth,
          onFinish: (nextWidth) => {
            cleanup.current = null;
            onDraggingChange?.(false);
            if (nextWidth !== null) onWidthChange(nextWidth);
          },
        });
      }}
      onDoubleClick={() => commit(defaultWidth)}
      onKeyDown={(event) => {
        const step = event.shiftKey ? 40 : 10;
        let next: number;
        switch (event.key) {
          case 'ArrowLeft':
            next = width - direction * step;
            break;
          case 'ArrowRight':
            next = width + direction * step;
            break;
          case 'Home':
            next = minWidth;
            break;
          case 'End':
            next = maxWidth;
            break;
          case 'Enter':
            next = defaultWidth;
            break;
          default:
            return;
        }
        event.preventDefault();
        commit(next);
      }}
    />
  );
}
