import React, { useState } from 'react';
import { Sidebar } from './components/sidebar/Sidebar';
import { ChatWindow } from './components/ChatWindow';

import { ConfigView } from './components/sidebar/ConfigView';
import { ChatList } from './components/ChatList';
import { MemoryView } from './components/memory/MemoryView';
import { ErrorBoundary } from './components/ErrorBoundary';
import { StatusBar } from './components/StatusBar';
import { PlanProvider, usePlan } from './hooks/usePlan';
import { ChatProvider, useChatStore } from './hooks/useChatStore.js';

const HeaderTitle: React.FC<{ text?: string; onUnlock?: () => void }> = ({ text, onUnlock }) => {
  const { backendConfig } = useChatStore();
  const [clicks, setClicks] = React.useState(0);

  const timerRef = React.useRef<NodeJS.Timeout | null>(null);

  const handleClick = () => {
    setClicks(c => c + 1);

    // Clear existing timer
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }

    // Reset clicks if user stops clicking for 500ms
    timerRef.current = setTimeout(() => {
      setClicks(0);
    }, 500);
  };

  // Cleanup on unmount
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
};

import { SkillsView } from './components/skills/SkillsView';
import { RobotShowcase } from './components/chat/RobotShowcase';

const AppInner: React.FC = () => {
  const [sidebarTab, setSidebarTab] = useState<'chats' | 'config'>('chats');
  const [mainView, setMainView] = useState<'chat' | 'memory' | 'skills' | 'emotes'>('chat');

  // Sidebar State Management
  // Default to open on larger screens, closed on mobile
  const [isLeftSidebarOpen, setIsLeftSidebarOpen] = useState(window.innerWidth >= 768);
  const [isRightSidebarOpen, setIsRightSidebarOpen] = useState(false);

  // ... (rest of imports/hooks same as before) ...
  const { refresh } = usePlan();
  const { currentChatId, setViewSwitcher } = useChatStore();
  const chatIdRef = React.useRef<string | null>(null);

  const handlePlanRefresh = React.useCallback(() => {
    refresh(currentChatId);
  }, [refresh, currentChatId]);

  // Logic: When Right Sidebar Opens, Auto-Collapse Left Sidebar
  const handleRightSidebarToggle = (isOpen: boolean) => {
    setIsRightSidebarOpen(isOpen);
    if (isOpen && window.innerWidth >= 768) {
      setIsLeftSidebarOpen(false);
    }
  };

  const toggleLeftSidebar = () => setIsLeftSidebarOpen(!isLeftSidebarOpen);

  // Set view switcher in context so child components can switch views
  React.useEffect(() => {
    setViewSwitcher?.(setMainView as any);
  }, [setViewSwitcher, setMainView]);

  // Load plan when chat changes
  React.useEffect(() => {
    console.log('Loading plan for chat:', currentChatId);
    refresh(currentChatId);
    // Track chat change
    chatIdRef.current = currentChatId;
    // Close sidebar on mobile when chat changes (user selected a chat)
    if (window.innerWidth < 768) {
      setIsLeftSidebarOpen(false);
    }
  }, [currentChatId, refresh]);

  const getTitle = () => {
    switch (mainView) {
      case 'memory': return 'MEMORY SYSTEM';
      case 'skills': return 'SKILLS LIBRARY';
      case 'emotes': return 'ROBOT GALLERY';
      default: return undefined;
    }
  };

  return (
    <div className="h-full w-full bg-neutral-50 text-brutal-black font-sans">
      <div className="flex h-full relative">
        <Sidebar
          activeTab={sidebarTab}
          onTabChange={setSidebarTab}
          chatsContent={<ChatList />}
          configContent={<ConfigView />}
          isOpen={isLeftSidebarOpen}
          onClose={() => setIsLeftSidebarOpen(false)}
        />
        <div className="flex-1 flex flex-col overflow-hidden w-full">
          <header className="border-b-3 border-brutal-black px-4 md:px-6 flex items-center justify-between bg-brutal-white flex-shrink-0 h-14">
            <div className="flex items-center gap-2 md:gap-0">
              {!isLeftSidebarOpen ? (
                <div
                  className="mr-3 group cursor-pointer"
                  onClick={toggleLeftSidebar}
                  role="button"
                  aria-label="Open Sidebar"
                  title="Open Sidebar"
                >
                  {/* Default: Logo */}
                  <div className="group-hover:hidden">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" role="img" aria-label="Suzent Logo" className="h-10 w-10">
                      <rect x="1.5" y="1.5" width="21" height="21" rx="3" fill="#FFFFFF" />
                      <rect x="3.5" y="3.5" width="17" height="17" rx="3" fill="#000000" />
                      <rect x="5.5" y="7" width="5" height="5" rx="1.5" fill="#FFFFFF" />
                      <rect x="13.5" y="7" width="5" height="5" rx="1.5" fill="#FFFFFF" />
                    </svg>
                  </div>
                  {/* Hover: Toggle Button */}
                  <div className="hidden group-hover:block">
                    <div className="h-10 w-10 flex items-center justify-center rounded-md hover:bg-neutral-200 transition-colors">
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-brutal-black" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <rect x="4" y="4" width="16" height="16" rx="2" />
                        <line x1="9" y1="4" x2="9" y2="20" />
                      </svg>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="h-10 w-10 mr-3" aria-hidden="true" />
              )}
              <HeaderTitle text={getTitle()} onUnlock={() => setMainView('emotes')} />
            </div>

            <div className="flex items-center gap-3">
              {/* View Switcher - Segmented Control */}
              <div className="flex border-3 border-brutal-black bg-white shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
                {[
                  { id: 'chat', label: 'Chat' },
                  { id: 'memory', label: 'Memory' },
                  { id: 'skills', label: 'Skills' }
                ].map((view) => (
                  <button
                    key={view.id}
                    onClick={() => setMainView(view.id as any)}
                    className={`
                            px-4 py-2 font-bold uppercase text-xs md:text-sm transition-colors
                            ${mainView === view.id
                        ? 'bg-brutal-black text-white'
                        : 'bg-white text-brutal-black hover:bg-neutral-100'}
                            ${view.id !== 'emotes' ? 'border-r-3 border-brutal-black' : ''}
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

          {/* System Status Line */}
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
