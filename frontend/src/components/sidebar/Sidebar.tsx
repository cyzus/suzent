import React, { useEffect, useState } from 'react';

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

const TAB_LABELS: Record<SidebarTab, string> = {
  chats: 'Chats',
  config: 'Config'
};

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

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-brutal-black/50 z-40 md:hidden backdrop-blur-sm"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside className={`
        fixed md:relative z-50 h-full shrink-0
        w-80 border-r-3 border-brutal-black flex flex-col bg-neutral-50
        transition-all duration-300 ease-in-out
        ${isOpen ? 'translate-x-0 md:ml-0' : '-translate-x-full md:translate-x-0 md:-ml-80'}
      `}>
        <div className="h-14 flex items-center justify-start px-4 border-b-3 border-brutal-black bg-white sticky top-0 z-10 shrink-0">
          {/* Toggle Button (Close) */}
          <button
            onClick={onClose}
            className="h-10 w-10 flex items-center justify-center rounded-md hover:bg-neutral-200 transition-colors text-brutal-black"
            aria-label="Close Sidebar"
            title="Close Sidebar"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <rect x="4" y="4" width="16" height="16" rx="2" />
              <line x1="9" y1="4" x2="9" y2="20" />
            </svg>
          </button>

          {/* Vertical Separator */}
          <div className="h-6 w-[2px] bg-neutral-300 mx-2 rounded-full" />

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
                className={`flex-1 py-3 text-xs font-bold uppercase relative transition-all duration-200 ${active ? 'bg-brutal-black text-white' : 'bg-white text-brutal-black hover:bg-brutal-yellow border-r-3 border-brutal-black last:border-r-0'}`}
              >
                {TAB_LABELS[tab]}
              </button>
            );
          })}
        </nav>
        <div
          className={`flex-1 flex flex-col overflow-hidden relative ${animateContent ? 'animate-brutal-drop' : ''
            }`}
        >
          <div className={activeTab === 'chats' ? 'h-full' : 'hidden'} aria-hidden={activeTab !== 'chats'}>
            {mountedTabs.has('chats') ? chatsContent : null}
          </div>
          <div className={`${activeTab === 'config' ? '' : 'hidden'} h-full overflow-y-auto scrollbar-thin p-4 space-y-4`} aria-hidden={activeTab !== 'config'}>
            {mountedTabs.has('config') ? configContent : null}
          </div>
        </div>

        {/* User / Global Settings - Bottom Stick */}
        <div className="border-t-3 border-brutal-black bg-white p-3 md:p-4 sticky bottom-0 z-20">
          <button
            onClick={onOpenSettings}
            className="w-full flex items-center gap-3 p-3 bg-neutral-100 hover:bg-brutal-yellow border-2 border-brutal-black transition-colors group text-left"
          >
            <div className="w-8 h-8 rounded-full bg-brutal-black flex items-center justify-center text-white shrink-0">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="flex flex-col min-w-0">
              <span className="font-bold text-sm truncate uppercase tracking-tight">ADMIN USER</span>
              <span className="text-xs text-neutral-600 font-mono truncate">Manage Keys</span>
            </div>
            <div className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
          </button>
        </div>
      </aside>
    </>
  );
};
