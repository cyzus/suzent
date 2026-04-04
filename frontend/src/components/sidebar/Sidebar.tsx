import React, { useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import { detectDesktopPlatform } from '../../lib/titleBarPlatform';

type SidebarTab = 'chats' | 'config';

interface SidebarProps {
  activeTab: SidebarTab;
  onTabChange: (tab: SidebarTab) => void;
  chatsContent: React.ReactNode;
  configContent: React.ReactNode;
  isOpen?: boolean;
  onOpenSettings: () => void;
  onClose?: () => void;
}

export function Sidebar({
  activeTab,
  onTabChange,
  chatsContent,
  configContent,
  isOpen = false,
  onOpenSettings,
  onClose
}: SidebarProps): React.ReactElement {
  const [animateContent, setAnimateContent] = useState(false);
  const [mountedTabs, setMountedTabs] = useState<Set<SidebarTab>>(() => new Set(['chats']));
  const { t } = useI18n();
  const desktopPlatform = React.useMemo(
    () => detectDesktopPlatform(navigator.userAgent, navigator.platform),
    [],
  );
  const canDragWindowFromSidebar = !!window.__TAURI__ && desktopPlatform === 'windows';
  const appWindow = window.__TAURI__?.window.getCurrentWindow();

  const TAB_LABELS: Record<SidebarTab, string> = {
    chats: t('sidebar.tabs.chats'),
    config: t('sidebar.tabs.config')
  };

  useEffect(() => {
    setAnimateContent(true);
    const timeout = window.setTimeout(() => setAnimateContent(false), 200);
    return () => window.clearTimeout(timeout);
  }, [activeTab]);

  useEffect(() => {
    setMountedTabs(prev => {
      if (prev.has(activeTab)) return prev;
      const next = new Set(prev);
      next.add(activeTab);
      return next;
    });
  }, [activeTab]);

  function handleSidebarHeaderMouseDown(event: React.MouseEvent<HTMLElement>): void {
    if (!canDragWindowFromSidebar) {
      return;
    }

    const target = event.target as HTMLElement;
    const interactiveSelector = 'button, a, input, textarea, select, [role="button"]';
    if (target.closest(interactiveSelector)) {
      return;
    }

    appWindow?.startDragging().catch(() => {
      // No-op: dragging is best-effort for custom titlebars.
    });
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
        transition-all duration-300 ease-in-out
        ${isOpen ? 'translate-x-0 lg:ml-0' : '-translate-x-full lg:translate-x-0 lg:-ml-80'}
      `}>
        <div
          className="h-12 flex items-center justify-start px-4 border-b-3 border-brutal-black bg-white dark:bg-zinc-800 sticky top-0 z-10 shrink-0"
          onMouseDown={handleSidebarHeaderMouseDown}
        >
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
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" role="img" aria-label="Suzent Logo" className="h-10 w-10">
            <rect x="1.5" y="1.5" width="21" height="21" rx="3" fill="#FFFFFF" />
            <rect x="3.5" y="3.5" width="17" height="17" rx="3" fill="#000000" />
            <rect x="5.5" y="7" width="5" height="5" rx="1.5" fill="#FFFFFF" />
            <rect x="13.5" y="7" width="5" height="5" rx="1.5" fill="#FFFFFF" />
          </svg>
        </div>
        <nav className="flex border-b-3 border-brutal-black">
          {(['chats', 'config'] as const).map(tab => {
            const active = activeTab === tab;
            return (
              <button
                key={tab}
                onClick={() => onTabChange(tab)}
                className={`flex-1 py-2 text-xs font-bold uppercase relative transition-all duration-200 ${active
                  ? 'bg-brutal-black text-white dark:bg-brutal-yellow dark:text-brutal-black'
                  : 'bg-white dark:bg-zinc-800 text-brutal-black dark:text-white hover:bg-brutal-yellow dark:hover:bg-zinc-700 border-r-3 border-brutal-black last:border-r-0'}`}
              >
                {TAB_LABELS[tab]}
              </button>
            );
          })}
        </nav>
        <div
          className={`flex-1 flex flex-col overflow-hidden relative min-h-0 ${animateContent ? 'animate-brutal-drop' : ''
            }`}
        >
          <div className={activeTab === 'chats' ? 'h-full min-h-0 flex flex-col' : 'hidden'} aria-hidden={activeTab !== 'chats'}>
            {mountedTabs.has('chats') ? chatsContent : null}
          </div>
          <div className={`${activeTab === 'config' ? '' : 'hidden'} h-full overflow-y-auto scrollbar-thin p-4 space-y-4 min-h-0`} aria-hidden={activeTab !== 'config'}>
            {mountedTabs.has('config') ? configContent : null}
          </div>
        </div>

        {/* User / Global Settings - Bottom Stick */}
        <button
          onClick={onOpenSettings}
          className="w-full flex items-center h-[52px] px-4 bg-white dark:bg-zinc-800 border-t-3 border-brutal-black hover:bg-brutal-yellow dark:hover:bg-brutal-yellow transition-colors group shrink-0 relative z-20"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-[18px] w-[18px] shrink-0 text-brutal-black dark:text-white dark:group-hover:text-brutal-black transition-colors" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clipRule="evenodd" />
          </svg>
          <span className="font-bold text-xs truncate uppercase tracking-tight text-brutal-black dark:text-white dark:group-hover:text-brutal-black transition-colors ml-2.5">
            {t('sidebar.settings')}
          </span>
          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 ml-auto opacity-0 group-hover:opacity-100 text-brutal-black transition-opacity shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </aside>
    </>
  );
};
