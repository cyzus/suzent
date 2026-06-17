import React, { useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import { detectDesktopPlatform } from '../../lib/titleBarPlatform';
import { SuzentLogo } from '../SuzentLogo';

interface SidebarProps {
  chatsContent: React.ReactNode;
  isOpen?: boolean;
  onOpenSettings: () => void;
  onClose?: () => void;
  titlebarControls?: React.ReactNode;
}

export function Sidebar({
  chatsContent,
  isOpen = false,
  onOpenSettings,
  onClose,
  titlebarControls
}: SidebarProps): React.ReactElement {
  const { t } = useI18n();
  const desktopPlatform = React.useMemo(
    () => detectDesktopPlatform(navigator.userAgent, navigator.platform),
    [],
  );
  const canDragWindowFromSidebar = !!window.__TAURI__ && (desktopPlatform === 'windows' || desktopPlatform === 'macos');
  const appWindow = window.__TAURI__?.window.getCurrentWindow();

  function handleSidebarHeaderMouseDown(event: React.MouseEvent<HTMLElement>): void {
    if (!canDragWindowFromSidebar) return;
    const target = event.target as HTMLElement;
    const interactiveSelector = 'button, a, input, textarea, select, [role="button"]';
    if (target.closest(interactiveSelector)) return;
    appWindow?.startDragging().catch(() => {});
  }

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-brutal-black/50 z-40 lg:hidden backdrop-blur-sm"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside className={`
        fixed lg:relative z-50 h-full shrink-0
        w-80 border-r-3 border-brutal-black flex flex-col bg-neutral-50 dark:bg-zinc-900
        transform-gpu will-change-transform transition-transform duration-300 ease-in-out
        ${isOpen ? 'translate-x-0 lg:ml-0' : '-translate-x-full lg:translate-x-0 lg:-ml-80'}
      `}>
        <div
          className="h-12 flex items-center justify-start px-4 border-b-3 border-brutal-black bg-white dark:bg-zinc-800 sticky top-0 z-10 shrink-0"
          onMouseDown={handleSidebarHeaderMouseDown}
        >
          {titlebarControls}

          {/* Toggle Button (Close) */}
          <button
            onClick={onClose}
            className="h-10 w-10 flex items-center justify-center rounded-md hover:bg-neutral-200 dark:hover:bg-zinc-700 transition-colors text-brutal-black dark:text-white"
            aria-label={t('sidebar.close')}
            title={t('sidebar.close')}
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <rect x="4" y="4" width="16" height="16" rx="2" />
              <line x1="9" y1="4" x2="9" y2="20" />
            </svg>
          </button>

          {/* Vertical Separator */}
          <div className="h-6 w-[2px] bg-neutral-300 dark:bg-zinc-600 mx-2 rounded-full" />

          {/* Logo (Static) */}
          <SuzentLogo className="h-7 w-7" interactive />
        </div>

        <div className="flex-1 flex flex-col overflow-hidden min-h-0">
          <div className="h-full min-h-0 flex flex-col">
            {chatsContent}
          </div>
        </div>

        {/* User / Global Settings - Bottom Stick */}
        <button
          onClick={onOpenSettings}
          className="w-full flex items-center h-[52px] px-4 bg-white dark:bg-zinc-800 border-t border-neutral-200 dark:border-zinc-700 hover:bg-neutral-50 dark:hover:bg-zinc-700/80 transition-colors group shrink-0 relative z-20"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-[18px] w-[18px] shrink-0 text-neutral-500 dark:text-neutral-400 group-hover:text-brutal-black dark:group-hover:text-white transition-colors" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clipRule="evenodd" />
          </svg>
          <span className="font-bold text-xs truncate uppercase tracking-tight text-neutral-500 dark:text-neutral-400 group-hover:text-brutal-black dark:group-hover:text-white transition-colors ml-2.5">
            {t('sidebar.settings')}
          </span>
          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 ml-auto opacity-0 group-hover:opacity-100 text-neutral-400 group-hover:text-brutal-black dark:group-hover:text-white transition-all shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </aside>
    </>
  );
};
