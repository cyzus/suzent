import React, { useEffect, useRef } from 'react';
import { useI18n } from '../i18n';
import { startPanelResize, type PanelResizeAction } from '../lib/panelResize';

interface PanelResizeHandleProps {
  panelRef: React.RefObject<HTMLElement>;
  side: 'left' | 'right';
  width: number;
  minWidth: number;
  maxWidth: number;
  defaultWidth: number;
  onWidthChange: (width: number) => void;
  onCollapse?: () => void;
  onCover?: () => void;
  onDock?: (width: number) => void;
  onReset?: () => void;
  dockThreshold?: number;
  hint?: string;
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
  onCollapse,
  onCover,
  onDock,
  onReset,
  dockThreshold,
  hint,
}: PanelResizeHandleProps): React.ReactElement {
  const { t } = useI18n();
  const cleanup = useRef<(() => void) | null>(null);
  useEffect(() => () => cleanup.current?.(), [minWidth, maxWidth]);
  const direction = side === 'left' ? 1 : -1;
  const reset = (): void => {
    if (onReset) onReset();
    else commit(defaultWidth);
  };
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
      title={hint ?? t('sidebar.resizeHint')}
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
          collapseThreshold: onCollapse ? minWidth - 64 : undefined,
          coverThreshold: onCover ? maxWidth + 64 : undefined,
          dockThreshold: onDock ? dockThreshold : undefined,
          onFinish: (nextWidth, action?: PanelResizeAction) => {
            cleanup.current = null;
            onDraggingChange?.(false);
            if (action === 'collapse') onCollapse?.();
            else if (action === 'cover') onCover?.();
            else if (action === 'dock' && nextWidth !== null) onDock?.(nextWidth);
            else if (nextWidth !== null) onWidthChange(nextWidth);
          },
        });
      }}
      onDoubleClick={reset}
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
            event.preventDefault();
            reset();
            return;
          default:
            return;
        }
        event.preventDefault();
        commit(next);
      }}
    />
  );
}
