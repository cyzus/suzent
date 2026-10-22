import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { isImeComposing } from '../lib/ime';

interface ContextMenuProps {
  anchor: { x: number; y: number } | { rect: DOMRect };
  boundary?: DOMRect | null;
  children: React.ReactNode;
  onClose: () => void;
  onEscape?: () => void;
  viewKey?: string;
  label?: string;
  rootDataAttrs?: Record<string, string>;
  returnFocus?: HTMLElement;
}

export function ContextMenu({
  anchor,
  boundary,
  children,
  onClose,
  onEscape,
  viewKey,
  label,
  rootDataAttrs,
  returnFocus,
}: ContextMenuProps): React.ReactElement {
  const ref = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const [position, setPosition] = useState({ left: -9999, top: -9999 });
  const x = 'rect' in anchor ? anchor.rect.right : anchor.x;
  const y = 'rect' in anchor ? anchor.rect.bottom : anchor.y;

  useLayoutEffect(() => {
    const menu = ref.current;
    previousFocus.current = returnFocus ?? (document.activeElement as HTMLElement | null);
    return () => {
      // Do not steal focus from a dialog opened by a menu action or an outside click.
      if (document.activeElement === document.body || menu?.contains(document.activeElement)) {
        previousFocus.current?.focus({ preventScroll: true });
      }
    };
  }, [returnFocus]);

  useLayoutEffect(() => {
    const menu = ref.current;
    if (!menu) return;
    const left = Math.max(8, boundary?.left ?? 0);
    const top = Math.max(8, boundary?.top ?? 0);
    const right = Math.min(window.innerWidth, boundary?.right ?? window.innerWidth) - 8;
    const bottom = Math.min(window.innerHeight, boundary?.bottom ?? window.innerHeight) - 8;
    menu.style.maxWidth = `${Math.max(0, right - left)}px`;
    menu.style.maxHeight = `${Math.max(0, bottom - top)}px`;
    setPosition({
      left: Math.max(left, Math.min(x, right - menu.offsetWidth)),
      top: Math.max(top, Math.min(y, bottom - menu.offsetHeight)),
    });
    menu.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus({ preventScroll: true });
  }, [x, y, boundary, viewKey]);

  useEffect(() => {
    const dismiss = (event: Event): void => {
      if (!ref.current?.contains(event.target as Node)) onClose();
    };
    const close = (): void => onClose();
    document.addEventListener('pointerdown', dismiss);
    document.addEventListener('contextmenu', dismiss);
    document.addEventListener('scroll', dismiss, true);
    window.addEventListener('resize', close);
    window.addEventListener('blur', close);
    return () => {
      document.removeEventListener('pointerdown', dismiss);
      document.removeEventListener('contextmenu', dismiss);
      document.removeEventListener('scroll', dismiss, true);
      window.removeEventListener('resize', close);
      window.removeEventListener('blur', close);
    };
  }, [onClose]);

  return createPortal(
    <div
      {...rootDataAttrs}
      ref={ref}
      role="menu"
      aria-label={label}
      style={position}
      className="fixed z-[9999] w-56 overflow-y-auto border-2 border-brutal-black bg-white py-0.5 shadow-[3px_3px_0_0_#000] dark:bg-zinc-800"
      onClick={(event) => event.stopPropagation()}
      onContextMenu={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
      onKeyDown={(event) => {
        if (isImeComposing(event)) return;
        event.stopPropagation();
        if (event.key === 'Escape') {
          event.preventDefault();
          (onEscape ?? onClose)();
        } else if (event.key === 'Tab') {
          onClose();
        } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
          event.preventDefault();
          const buttons = Array.from(
            ref.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? []
          );
          const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
          const next =
            event.key === 'Home'
              ? 0
              : event.key === 'End'
                ? buttons.length - 1
                : (index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length;
          buttons[next]?.focus();
        }
      }}
    >
      {children}
    </div>,
    document.fullscreenElement ?? document.body
  );
}
