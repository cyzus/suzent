import React, { useState } from 'react';

import { ChatList } from './components/ChatList';
import { ChatWindow } from './components/ChatWindow';
import { ErrorBoundary } from './components/ErrorBoundary';
import { RobotAvatar } from './components/chat/RobotAvatar';
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
import { useI18n } from './i18n';

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
  const { t } = useI18n();
  const [sidebarTab, setSidebarTab] = useState<'chats' | 'config'>('chats');
  const [mainView, setMainView] = useState<MainView>('chat');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isLeftSidebarOpen, setIsLeftSidebarOpen] = useState(window.innerWidth >= 1024);
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

    if (window.innerWidth < 1024) {
      setIsLeftSidebarOpen(false);
    }
  }, [currentChatId, refresh]);

  // Track previous width to only auto-close when crossing the threshold
  const prevWidthRef = React.useRef(window.innerWidth);

  React.useEffect(() => {
    const handleResize = () => {
      const currentWidth = window.innerWidth;
      // Close sidebar only when crossing the threshold from desktop to mobile
      if (prevWidthRef.current >= 1024 && currentWidth < 1024) {
        setIsLeftSidebarOpen(false);
      }
      prevWidthRef.current = currentWidth;
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  function getTitle(): string | undefined {
    switch (mainView) {
      case 'memory':
        return t('views.memorySystem');
      case 'skills':
        return t('views.skillsLibrary');
      case 'emotes':
        return t('views.robotGallery');
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
                  aria-label={t('sidebar.open')}
                  title={t('sidebar.open')}
                >
                  <div className="group-hover:hidden">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" role="img" aria-label={t('app.logoAriaLabel')} className="h-10 w-10">
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
                  { id: 'chat' as MainView, label: t('nav.chat') },
                  { id: 'memory' as MainView, label: t('nav.memory') },
                  { id: 'skills' as MainView, label: t('nav.skills') }
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
                  aria-label={isRightSidebarOpen ? t('sidebar.close') : t('sidebar.open')}
                  title={isRightSidebarOpen ? t('sidebar.close') : t('sidebar.open')}
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


function BackendLoadingScreen() {
  const { t } = useI18n();
  return (
    <div className="flex flex-col items-center justify-center h-screen bg-neutral-50 font-sans p-8 text-center border-8 border-brutal-black">
      <div className="bg-white p-8 border-4 border-brutal-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] max-w-md flex flex-col items-center animate-pulse">
        <div className="w-32 h-32 mb-6">
          <RobotAvatar variant="idle" className="w-full h-full" />
        </div>
        <h1 className="text-4xl font-brutal font-black uppercase mb-4 text-brutal-black">{t('app.initializing')}</h1>
        <p className="font-bold text-lg mb-6 leading-tight">
          {t('app.connectingToCore')}
        </p>
        <div className="w-full h-4 bg-neutral-200 border-2 border-brutal-black overflow-hidden relative">
          <div className="absolute top-0 left-0 h-full w-1/2 bg-brutal-black animate-[slide_1s_ease-in-out_infinite]"></div>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const { t } = useI18n();
  // Enforce desktop environment
  if (!window.__TAURI__) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-brutal-yellow font-sans p-8 text-center border-8 border-brutal-black">
        <div className="bg-white p-8 border-4 border-brutal-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] max-w-md flex flex-col items-center">
          <div className="w-32 h-32 mb-6">
            <RobotAvatar variant="ghost" className="w-full h-full" />
          </div>
          <h1 className="text-4xl font-brutal font-black uppercase mb-4 text-brutal-black">{t('app.desktopRequiredTitle')}</h1>
          <p className="font-bold text-lg mb-6 leading-tight">
            {t('app.desktopRequiredDesc')}
          </p>
          <div className="font-mono text-xs bg-neutral-100 p-4 border-2 border-brutal-black text-left w-full">
            $ npm run tauri dev
          </div>
        </div>
      </div>
    );
  }

  // Check for backend connection (Tauri specific)
  // In browser dev mode, we skip this check as api.ts falls back to 8000
  // But inside Tauri, api.ts returns empty string if port is missing.
  const isBackendReady = !!sessionStorage.getItem('SUZENT_PORT');

  if (!isBackendReady) {
    return <BackendLoadingScreen />;
  }


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
