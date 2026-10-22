import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { isImeComposing } from '../../lib/ime';

export interface BoardRowMenuItem {
  key: string;
  label: string;
  danger?: boolean;
  onSelect: () => void;
}

interface BoardRowMenuProps {
  anchor: { x: number; y: number };
  title: string;
  items: BoardRowMenuItem[];
  onClose: () => void;
}

/**
 * Right-click menu for a session or task row on the board. Portalled into
 * document.body so the panel's scroll container never clips it.
 */
export function BoardRowMenu({
  anchor,
  title,
  items,
  onClose,
}: BoardRowMenuProps): React.ReactElement {
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);

  useEffect(() => {
    if (!menuRef.current) return;
    const margin = 8;
    const maxLeft = window.innerWidth - menuRef.current.offsetWidth - margin;
    const maxTop = window.innerHeight - menuRef.current.offsetHeight - margin;
    setPosition({
      left: Math.max(margin, Math.min(anchor.x, maxLeft)),
      top: Math.max(margin, Math.min(anchor.y, maxTop)),
    });
    menuRef.current.querySelector<HTMLButtonElement>('button')?.focus();
  }, [anchor]);

  useEffect(() => {
    const onMouseDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) onClose();
    };
    const onContextMenu = (e: MouseEvent) => {
      if (menuRef.current?.contains(e.target as Node)) e.preventDefault();
    };
    const onKey = (e: KeyboardEvent) => {
      if (isImeComposing(e)) return;
      if (e.key === 'Escape') onClose();
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
      const buttons = [...(menuRef.current?.querySelectorAll('button') ?? [])];
      if (buttons.length === 0) return;
      e.preventDefault();
      const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
      const step = e.key === 'ArrowDown' ? 1 : -1;
      buttons[(current + step + buttons.length) % buttons.length].focus();
    };
    const onScroll = () => onClose();
    document.addEventListener('mousedown', onMouseDown);
    document.addEventListener('keydown', onKey);
    document.addEventListener('contextmenu', onContextMenu);
    window.addEventListener('blur', onClose);
    document.addEventListener('scroll', onScroll, true);
    return () => {
      document.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('contextmenu', onContextMenu);
      window.removeEventListener('blur', onClose);
      document.removeEventListener('scroll', onScroll, true);
    };
  }, [onClose]);

  return createPortal(
    <div
      ref={menuRef}
      role="menu"
      aria-label={title}
      style={{
        position: 'fixed',
        left: position?.left ?? -9999,
        top: position?.top ?? -9999,
        visibility: position ? 'visible' : 'hidden',
        zIndex: 9999,
      }}
      className="min-w-[180px] max-w-[260px] border-2 border-brutal-black bg-white py-0.5 shadow-[3px_3px_0_0_#000] dark:bg-zinc-800"
    >
      <p className="truncate border-b-2 border-brutal-black px-3 py-1.5 font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-zinc-400">
        {title}
      </p>
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          role="menuitem"
          onClick={() => {
            item.onSelect();
            onClose();
          }}
          className={`block w-full px-3 py-2 text-left text-xs font-extrabold uppercase tracking-wider transition-colors focus-visible:outline-none ${
            item.danger
              ? 'text-brutal-red hover:bg-brutal-red hover:text-white focus-visible:bg-brutal-red focus-visible:text-white'
              : 'text-brutal-black hover:bg-brutal-yellow focus-visible:bg-brutal-yellow dark:text-white dark:hover:text-brutal-black dark:focus-visible:text-brutal-black'
          }`}
        >
          {item.label}
        </button>
      ))}
    </div>,
    document.body
  );
}
