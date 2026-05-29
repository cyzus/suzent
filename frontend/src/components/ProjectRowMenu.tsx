import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../i18n';

interface ProjectRowMenuProps {
  anchor: { x: number; y: number } | { rect: DOMRect };
  canDelete: boolean;
  /** When canDelete is false, optional reason shown as a tooltip on the disabled item. */
  deleteDisabledReason?: string;
  onRename: () => void;
  onDelete: () => void;
  onClose: () => void;
}

/**
 * Brutalist context menu for a project row inside the filter dropdown.
 * Portalled into document.body so it never gets clipped by the dropdown.
 */
export const ProjectRowMenu: React.FC<ProjectRowMenuProps> = ({
  anchor,
  canDelete,
  deleteDisabledReason,
  onRename,
  onDelete,
  onClose,
}) => {
  const { t } = useI18n();
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);

  const anchorPoint = useMemo(() => {
    if ('rect' in anchor) return { x: anchor.rect.right, y: anchor.rect.bottom };
    return { x: anchor.x, y: anchor.y };
  }, [anchor]);

  useEffect(() => {
    if (!menuRef.current) return;
    const menuW = menuRef.current.offsetWidth || 200;
    const menuH = menuRef.current.offsetHeight || 100;
    const margin = 8;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let left = anchorPoint.x;
    let top = anchorPoint.y;
    if (left + menuW + margin > vw) left = Math.max(margin, anchorPoint.x - menuW);
    if (top + menuH + margin > vh) top = Math.max(margin, anchorPoint.y - menuH);
    setPosition({ left, top });
  }, [anchorPoint]);

  useEffect(() => {
    const onMouseDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', onMouseDown);
    document.addEventListener('keydown', onKey);
    document.addEventListener('contextmenu', onMouseDown);
    return () => {
      document.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('contextmenu', onMouseDown);
    };
  }, [onClose]);

  const surface = 'bg-white dark:bg-zinc-800 border-2 border-brutal-black shadow-[3px_3px_0_0_#000]';
  const itemBase =
    'w-full text-left px-3 py-2 text-xs font-extrabold uppercase tracking-wider flex items-center gap-2.5 transition-colors';

  const menu = (
    <div
      ref={menuRef}
      role="menu"
      style={{
        position: 'fixed',
        left: position?.left ?? -9999,
        top: position?.top ?? -9999,
        visibility: position ? 'visible' : 'hidden',
        zIndex: 9999,
      }}
      className={`min-w-[200px] ${surface} py-0.5`}
      onClick={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        role="menuitem"
        className={`${itemBase} text-brutal-black dark:text-white hover:bg-brutal-yellow dark:hover:bg-brutal-yellow dark:hover:text-brutal-black`}
        onClick={() => { onRename(); onClose(); }}
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
        </svg>
        {t('chatList.menu.rename')}
      </button>

      <div className="h-0.5 bg-brutal-black my-0.5" />

      <button
        type="button"
        role="menuitem"
        title={!canDelete ? deleteDisabledReason : undefined}
        disabled={!canDelete}
        onClick={() => { onDelete(); onClose(); }}
        className={`${itemBase} ${
          canDelete
            ? 'text-brutal-red hover:bg-brutal-red hover:text-white'
            : 'text-neutral-300 dark:text-neutral-600 cursor-not-allowed'
        }`}
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M1 7h22M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3" />
        </svg>
        {t('chatList.menu.delete')}
      </button>
    </div>
  );

  return createPortal(menu, document.body);
};
