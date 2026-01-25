import React, { useState } from 'react';

import { ChatList } from './components/ChatList';
import { ChatWindow } from './components/ChatWindow';
import { ErrorBoundary } from './components/ErrorBoundary';
import { RobotShowcase } from './components/chat/RobotShowcase';
import { MemoryView } from './components/memory/MemoryView';
import { SettingsModal } from './components/settings/SettingsModal';
import { ConfigView } from './components/sidebar/ConfigView';
import { Sidebar } from './components/sidebar/Sidebar';
import { SkillsView } from './components/skills/SkillsView';
import { StatusBar } from './components/StatusBar';
import { ChatProvider, useChatStore } from './hooks/useChatStore.js';
import { PlanProvider, usePlan } from './hooks/usePlan';
import { TitleBar } from './components/TitleBar';

interface HeaderTitleProps {
  text?: string;
  onUnlock?: () => void;
}

function HeaderTitle({ text, onUnlock }: HeaderTitleProps): React.ReactElement {
  const { backendConfig } = useChatStore();
  const [clicks, setClicks] = React.useState(0);
  const timerRef = React.useRef<NodeJS.Timeout | null>(null);

  function handleClick(): void {
    setClicks(c => c + 1);

    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }

    timerRef.current = setTimeout(() => {
      setClicks(0);
    }, 500);
  }

  React.useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, []);

  React.useEffect(() => {
    if (clicks >= 5 && onUnlock) {
      onUnlock();
      setClicks(0);
    }
  }, [clicks, onUnlock]);

  return (
    <div className="flex items-center gap-3 cursor-pointer select-none" onClick={handleClick}>
      <div className="w-3 h-3 bg-brutal-black"></div>
      <h1 className="font-brutal text-3xl text-brutal-black tracking-tighter uppercase leading-none">
        {text || backendConfig?.title || 'SUZENT'}
      </h1>
      <div className="w-3 h-3 bg-brutal-black"></div>
    </div>
  );
}

type MainView = 'chat' | 'memory' | 'skills' | 'emotes';

function AppInner(): React.ReactElement {
  const [sidebarTab, setSidebarTab] = useState<'chats' | 'config'>('chats');
  const [mainView, setMainView] = useState<MainView>('chat');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isLeftSidebarOpen, setIsLeftSidebarOpen] = useState(window.innerWidth >= 768);
  const [isRightSidebarOpen, setIsRightSidebarOpen] = useState(false);

  const { refresh } = usePlan();
  const { currentChatId, setViewSwitcher } = useChatStore();

  function handleRightSidebarToggle(isOpen: boolean): void {
    setIsRightSidebarOpen(isOpen);
    if (isOpen && window.innerWidth >= 768) {
      setIsLeftSidebarOpen(false);
    }
  }

  function toggleLeftSidebar(): void {
    setIsLeftSidebarOpen(prev => !prev);
  }

  React.useEffect(() => {
    setViewSwitcher?.(setMainView as (view: 'chat' | 'memory') => void);
  }, [setViewSwitcher, setMainView]);

  React.useEffect(() => {
    console.log('Loading plan for chat:', currentChatId);
    refresh(currentChatId);

    // Auto-collapse right sidebar on new chat
    if (!currentChatId) {
      setIsRightSidebarOpen(false);
    }

    if (window.innerWidth < 768) {
      setIsLeftSidebarOpen(false);
    }
  }, [currentChatId, refresh]);

  function getTitle(): string | undefined {
    switch (mainView) {
      case 'memory':
        return 'MEMORY SYSTEM';
      case 'skills':
        return 'SKILLS LIBRARY';
      case 'emotes':
        return 'ROBOT GALLERY';
      default:
        return undefined;
    }
  }

  return (
    <div className="h-full w-full bg-neutral-50 text-brutal-black font-sans">
      <TitleBar />
      <div className={`flex h-full relative ${window.__TAURI__ ? 'pt-8' : ''}`}>
        <Sidebar
          activeTab={sidebarTab}
          onTabChange={setSidebarTab}
          chatsContent={<ChatList />}
          configContent={<ConfigView />}
          isOpen={isLeftSidebarOpen}
          onOpenSettings={() => setIsSettingsOpen(true)}
          onClose={() => setIsLeftSidebarOpen(false)}
        />
        <div className="flex-1 flex flex-col overflow-hidden w-full">
          <header className="border-b-3 border-brutal-black px-4 md:px-6 flex items-center justify-between bg-brutal-white flex-shrink-0 h-14">
            <div className="flex items-center gap-2 md:gap-0">
              {isLeftSidebarOpen ? (
                <div className="h-10 w-10 mr-3" aria-hidden="true" />
              ) : (
                <div
                  className="mr-3 group cursor-pointer"
                  onClick={toggleLeftSidebar}
                  role="button"
                  aria-label="Open Sidebar"
                  title="Open Sidebar"
                >
                  <div className="group-hover:hidden">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" role="img" aria-label="Suzent Logo" className="h-10 w-10">
                      <rect x="1.5" y="1.5" width="21" height="21" rx="3" fill="#FFFFFF" />
                      <rect x="3.5" y="3.5" width="17" height="17" rx="3" fill="#000000" />
                      <rect x="5.5" y="7" width="5" height="5" rx="1.5" fill="#FFFFFF" />
                      <rect x="13.5" y="7" width="5" height="5" rx="1.5" fill="#FFFFFF" />
                    </svg>
                  </div>
                  <div className="hidden group-hover:block">
                    <div className="h-10 w-10 flex items-center justify-center rounded-md hover:bg-neutral-200 transition-colors">
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-brutal-black" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <rect x="4" y="4" width="16" height="16" rx="2" />
                        <line x1="9" y1="4" x2="9" y2="20" />
                      </svg>
                    </div>
                  </div>
                </div>
              )}
              <HeaderTitle text={getTitle()} onUnlock={() => setMainView('emotes')} />
            </div>

            <div className="flex items-center gap-3">
              <div className="flex border-3 border-brutal-black bg-white shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
                {[
                  { id: 'chat' as MainView, label: 'Chat' },
                  { id: 'memory' as MainView, label: 'Memory' },
                  { id: 'skills' as MainView, label: 'Skills' }
                ].map((view) => (
                  <button
                    key={view.id}
                    onClick={() => setMainView(view.id)}
                    className={`
                      px-4 py-2 font-bold uppercase text-xs md:text-sm transition-colors border-r-3 border-brutal-black last:border-r-0
                      ${mainView === view.id ? 'bg-brutal-black text-white' : 'bg-white text-brutal-black hover:bg-neutral-100'}
                    `}
                  >
                    {view.label}
                  </button>
                ))}
              </div>

              {mainView === 'chat' ? (
                <button
                  onClick={() => handleRightSidebarToggle(!isRightSidebarOpen)}
                  className={`
                    h-10 w-10 flex items-center justify-center rounded-md transition-colors
                    ${isRightSidebarOpen ? 'bg-neutral-200 text-brutal-black' : 'hover:bg-neutral-200 text-brutal-black'}
                  `}
                  aria-label={isRightSidebarOpen ? "Close Sidebar" : "Open Sidebar"}
                  title={isRightSidebarOpen ? "Close Sidebar" : "Open Sidebar"}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <rect x="4" y="4" width="16" height="16" rx="2" />
                    <line x1="15" y1="4" x2="15" y2="20" />
                  </svg>
                </button>
              ) : (
                <div className="h-10 w-10" aria-hidden="true" />
              )}
            </div>
          </header>

          <StatusBar />

          {mainView === 'chat' && (
            <div key="chat" className="flex-1 flex flex-col min-h-0 animate-view-fade">
              <ChatWindow
                isRightSidebarOpen={isRightSidebarOpen}
                onRightSidebarToggle={handleRightSidebarToggle}
              />
            </div>
          )}
          {mainView === 'memory' && (
            <div key="memory" className="flex-1 flex flex-col min-h-0 animate-view-fade">
              <MemoryView />
            </div>
          )}
          {mainView === 'skills' && (
            <div key="skills" className="flex-1 flex flex-col min-h-0 animate-view-fade">
              <SkillsView />
            </div>
          )}
          {mainView === 'emotes' && (
            <div key="emotes" className="flex-1 flex flex-col min-h-0 animate-view-fade">
              <RobotShowcase />
            </div>
          )}
        </div>
      </div>
      <SettingsModal isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </div>
  );
};

export default function App() {
  return (
    <ErrorBoundary>
      <ChatProvider>
        <PlanProvider>
          <AppInner />
        </PlanProvider>
      </ChatProvider>
    </ErrorBoundary>
  );
}
