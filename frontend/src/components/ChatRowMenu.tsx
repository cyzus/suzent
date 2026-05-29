import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { Project } from '../types/api';
import { useI18n } from '../i18n';

interface ChatRowMenuProps {
  /** Screen-space anchor: usually the right-click point or the dots-button rect. */
  anchor: { x: number; y: number } | { rect: DOMRect };
  projects: Project[];
  currentProjectId?: string | null;
  onRename: () => void;
  onDelete: () => void;
  onMoveToProject: (projectId: string) => void;
  onClose: () => void;
}

type View = 'root' | 'move';

/**
 * Floating context menu portalled into document.body. Brutalist styling.
 *
 * "Move to project" replaces the menu contents with a project list rather
 * than opening a submenu — avoids stacked nested popovers.
 */
export const ChatRowMenu: React.FC<ChatRowMenuProps> = ({
  anchor,
  projects,
  currentProjectId,
  onRename,
  onDelete,
  onMoveToProject,
  onClose,
}) => {
  const { t } = useI18n();
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [view, setView] = useState<View>('root');
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);

  const anchorPoint = useMemo(() => {
    if ('rect' in anchor) return { x: anchor.rect.right, y: anchor.rect.bottom };
    return { x: anchor.x, y: anchor.y };
  }, [anchor]);

  // Position the menu after first render and after every view switch
  // (so a taller move-view re-clamps inside the viewport).
  useEffect(() => {
    if (!menuRef.current) return;
    const menuW = menuRef.current.offsetWidth || 220;
    const menuH = menuRef.current.offsetHeight || 220;
    const margin = 8;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let left = anchorPoint.x;
    let top = anchorPoint.y;

    if (left + menuW + margin > vw) left = Math.max(margin, anchorPoint.x - menuW);
    if (top + menuH + margin > vh) top = Math.max(margin, anchorPoint.y - menuH);

    setPosition({ left, top });
  }, [anchorPoint, view]);

  useEffect(() => {
    const onMouseDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (view === 'move') setView('root');
        else onClose();
      }
    };
    const onScroll = () => onClose();
    document.addEventListener('mousedown', onMouseDown);
    document.addEventListener('keydown', onKey);
    document.addEventListener('scroll', onScroll, true);
    document.addEventListener('contextmenu', onMouseDown);
    return () => {
      document.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('scroll', onScroll, true);
      document.removeEventListener('contextmenu', onMouseDown);
    };
  }, [onClose, view]);

  // Brutalist styles
  const surface = 'bg-white dark:bg-zinc-800 border-2 border-brutal-black shadow-[3px_3px_0_0_#000]';
  const itemBase =
    'w-full text-left px-3 py-2 text-xs font-extrabold uppercase tracking-wider flex items-center gap-2.5 transition-colors';
  const itemDefault =
    'text-brutal-black dark:text-white hover:bg-brutal-yellow dark:hover:bg-brutal-yellow dark:hover:text-brutal-black';
  const itemDanger =
    'text-brutal-red hover:bg-brutal-red hover:text-white';

  const rootView = (
    <>
      <button
        type="button"
        role="menuitem"
        className={`${itemBase} ${itemDefault}`}
        onClick={() => { onRename(); onClose(); }}
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
        </svg>
        {t('chatList.menu.rename')}
      </button>

      <button
        type="button"
        role="menuitem"
        className={`${itemBase} ${itemDefault}`}
        onClick={() => setView('move')}
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 7l9-4 9 4M3 7v10l9 4 9-4V7M3 7l9 4 9-4" />
        </svg>
        <span className="flex-1">{t('chatList.menu.moveToProject')}</span>
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
      </button>

      <div className="h-0.5 bg-brutal-black my-0.5" />

      <button
        type="button"
        role="menuitem"
        className={`${itemBase} ${itemDanger}`}
        onClick={() => { onDelete(); onClose(); }}
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M1 7h22M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3" />
        </svg>
        {t('chatList.menu.delete')}
      </button>
    </>
  );

  const moveView = (
    <>
      {/* Back header */}
      <button
        type="button"
        onClick={() => setView('root')}
        className="w-full text-left px-3 py-2 text-[10px] font-extrabold uppercase tracking-widest flex items-center gap-2 border-b-2 border-brutal-black bg-brutal-yellow text-brutal-black hover:bg-yellow-300 transition-colors"
      >
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        {t('chatList.menu.moveToProject')}
      </button>
      <div className="max-h-60 overflow-y-auto">
        {projects.map((p) => {
          const isCurrent = p.id === currentProjectId;
          return (
            <button
              key={p.id}
              type="button"
              role="menuitem"
              onClick={(e) => {
                e.stopPropagation();
                if (!isCurrent) onMoveToProject(p.id);
                onClose();
              }}
              disabled={isCurrent}
              className={`w-full text-left px-3 py-2 text-xs font-extrabold uppercase tracking-wider flex items-center justify-between gap-2 transition-colors ${
                isCurrent
                  ? 'text-neutral-400 dark:text-neutral-500 cursor-default'
                  : 'text-brutal-black dark:text-white hover:bg-brutal-yellow dark:hover:bg-brutal-yellow dark:hover:text-brutal-black'
              }`}
            >
              <span className="truncate">{p.name}</span>
              {isCurrent && (
                <span className="text-[9px] font-extrabold tracking-widest">
                  {t('chatList.currentLabel')}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </>
  );

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
      className={`min-w-[220px] ${surface} py-0.5`}
      onClick={(e) => e.stopPropagation()}
    >
      {view === 'root' ? rootView : moveView}
    </div>
  );

  return createPortal(menu, document.body);
};
