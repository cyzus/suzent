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
import { ChatProvider, useChatCoreStore } from './hooks/useChatStore.js';
import { PlanProvider, usePlan } from './hooks/usePlan';
import { useStatusStore } from './hooks/useStatusStore';
import { useTheme } from './hooks/useTheme';
import { drainCronNotifications, fetchHeartbeatStatus } from './lib/api';
import { useHeartbeatRunning } from './hooks/useHeartbeatRunning';
import {
  DESKTOP_BREAKPOINT_PX,
  LEFT_SIDEBAR_WIDTH_PX,
  MAX_RIGHT_SIDEBAR_WIDTH_PX,
  clampRightSidebarWidth,
  shouldCollapseLeftSidebarOnRightOpen,
  shouldUseFullWidthRightSidebar,
} from './lib/layout';
import { TitleBar } from './components/TitleBar';
import { useI18n, getInitialLocale, tForLocale } from './i18n';

interface HeaderTitleProps {
  text?: string;
  onUnlock?: () => void;
}

function HeaderTitle({ text, onUnlock }: HeaderTitleProps): React.ReactElement {
  const { backendConfig } = useChatCoreStore();
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
      <div className="w-3 h-3 bg-brutal-black dark:bg-brutal-yellow"></div>
      <h1 className="font-brutal text-3xl text-brutal-black dark:text-white tracking-tighter uppercase leading-none">
        {text || backendConfig?.title || 'SUZENT'}
      </h1>
      <div className="w-3 h-3 bg-brutal-black dark:bg-brutal-yellow"></div>
    </div>
  );
}

type MainView = 'chat' | 'memory' | 'skills' | 'emotes';

function AppInner(): React.ReactElement {
  const [sidebarTab, setSidebarTab] = useState<'chats' | 'config'>('chats');
  const [mainView, setMainView] = useState<MainView>('chat');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isLeftSidebarOpen, setIsLeftSidebarOpen] = useState(window.innerWidth >= DESKTOP_BREAKPOINT_PX);
  const [isRightSidebarOpen, setIsRightSidebarOpen] = useState(false);
  const [rightSidebarWidth, setRightSidebarWidth] = useState<number | null>(null);
  const [viewportWidth, setViewportWidth] = useState(window.innerWidth);

  const rightSidebarMaxWidthPx = clampRightSidebarWidth(
    MAX_RIGHT_SIDEBAR_WIDTH_PX,
    viewportWidth,
    isLeftSidebarOpen ? LEFT_SIDEBAR_WIDTH_PX : 0,
  );
  const rightSidebarForceFullView = shouldUseFullWidthRightSidebar(
    viewportWidth,
    isLeftSidebarOpen ? LEFT_SIDEBAR_WIDTH_PX : 0,
  );

  const { refresh } = usePlan();
  const { currentChatId, setViewSwitcher, refreshChatList, refreshChatListSilently, chats, loadChat } = useChatCoreStore();
  const setStatusMsg = useStatusStore(s => s.setStatus);
  const setHeartbeatStatus = useHeartbeatRunning(s => s.setStatus);
  const { theme, toggleTheme } = useTheme();
  const { t } = useI18n();

  // Use refs so the interval callback always sees the latest values without re-creating the interval.
  const refreshChatListRef = React.useRef(refreshChatList);
  const refreshChatListSilentRef = React.useRef(refreshChatListSilently);
  const loadChatRef = React.useRef(loadChat);
  const currentChatIdRef = React.useRef(currentChatId);
  const chatsRef = React.useRef(chats);
  React.useEffect(() => { refreshChatListRef.current = refreshChatList; }, [refreshChatList]);
  React.useEffect(() => { refreshChatListSilentRef.current = refreshChatListSilently; }, [refreshChatListSilently]);
  React.useEffect(() => { loadChatRef.current = loadChat; }, [loadChat]);
  React.useEffect(() => { currentChatIdRef.current = currentChatId; }, [currentChatId]);
  React.useEffect(() => { chatsRef.current = chats; }, [chats]);

  // Poll every 8 s: drain cron notifications + heartbeat status + refresh sidebar + reload open chat.
  React.useEffect(() => {
    const interval = setInterval(async () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        return;
      }
      // Heartbeat status runs in parallel with notification drain.
      const [notifications] = await Promise.all([
        drainCronNotifications(),
        fetchHeartbeatStatus().then(setHeartbeatStatus).catch(() => {}),
      ]);
      if (notifications.length === 1) {
        setStatusMsg(`[${notifications[0].job_name}] finished — view in Social`, 'info', 4000);
      } else if (notifications.length > 1) {
        setStatusMsg(`${notifications.length} tasks finished — view in Social`, 'info', 4000);
      }

      // If a platform chat (cron/social) is open, reload its messages from DB.
      // Skip if a live background stream is active — the SSE connection already delivers events.
      const chatId = currentChatIdRef.current;
      const openChat = chatsRef.current.find(c => c.id === chatId);
      const isLiveStreamRunning = !!openChat?.isRunning;

      // Avoid redundant sidebar refreshes while SSE is already updating the active chat.
      if (!isLiveStreamRunning) {
        refreshChatListSilentRef.current();
      }

      if (chatId && (openChat?.platform || openChat?.heartbeatEnabled) && !openChat?.isRunning) {
        loadChatRef.current(chatId);
      }
    }, 8000);
    return () => clearInterval(interval);
  }, [setStatusMsg, setHeartbeatStatus]); // stable Zustand actions

  function handleRightSidebarToggle(isOpen: boolean): void {
    setIsRightSidebarOpen(isOpen);
    if (!isOpen) {
      return;
    }

    const currentWidth = window.innerWidth;
    if (currentWidth < DESKTOP_BREAKPOINT_PX) {
      setIsLeftSidebarOpen(false);
      return;
    }

    if (shouldCollapseLeftSidebarOnRightOpen(currentWidth, rightSidebarWidth)) {
      setIsLeftSidebarOpen(false);
    }
  }

  function toggleLeftSidebar(): void {
    setIsLeftSidebarOpen(prev => {
      const next = !prev;
      if (next) {
        setIsRightSidebarOpen(false);
      }
      return next;
    });
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

    if (window.innerWidth < DESKTOP_BREAKPOINT_PX) {
      setIsLeftSidebarOpen(false);
    }
  }, [currentChatId, refresh]);

  React.useEffect(() => {
    if (!isLeftSidebarOpen || !isRightSidebarOpen) {
      return;
    }

    if (shouldCollapseLeftSidebarOnRightOpen(viewportWidth, rightSidebarWidth)) {
      setIsLeftSidebarOpen(false);
    }
  }, [
    isLeftSidebarOpen,
    isRightSidebarOpen,
    viewportWidth,
    rightSidebarWidth,
  ]);

  // Track previous width to only auto-close when crossing the threshold
  const prevWidthRef = React.useRef(window.innerWidth);

  React.useEffect(() => {
    const handleResize = () => {
      const currentWidth = window.innerWidth;
      // Close sidebar only when crossing the threshold from desktop to mobile
      if (prevWidthRef.current >= DESKTOP_BREAKPOINT_PX && currentWidth < DESKTOP_BREAKPOINT_PX) {
        setIsLeftSidebarOpen(false);
      }
      setViewportWidth(currentWidth);
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
    <div className="h-full w-full bg-neutral-50 dark:bg-zinc-900 text-brutal-black dark:text-white font-sans">
      <TitleBar />
      <div className={`flex h-full relative ${window.__TAURI__ ? 'pt-8' : ''}`}>
        <Sidebar
          activeTab={sidebarTab}
          onTabChange={setSidebarTab}
          chatsContent={<ChatList />}
          configContent={<ConfigView isActive={sidebarTab === 'config' && isLeftSidebarOpen} />}
          isOpen={isLeftSidebarOpen}
          onOpenSettings={() => setIsSettingsOpen(true)}
          onClose={() => setIsLeftSidebarOpen(false)}
        />
        <div className="flex-1 flex flex-col overflow-hidden w-full">
          <header className="border-b-3 border-brutal-black px-4 md:px-6 flex items-center justify-between bg-brutal-white dark:bg-zinc-800 flex-shrink-0 h-14">
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
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" role="img" aria-label="Suzent Logo" className="h-10 w-10">
                      <rect x="1.5" y="1.5" width="21" height="21" rx="3" fill="#FFFFFF" />
                      <rect x="3.5" y="3.5" width="17" height="17" rx="3" fill="#000000" />
                      <rect x="5.5" y="7" width="5" height="5" rx="1.5" fill="#FFFFFF" />
                      <rect x="13.5" y="7" width="5" height="5" rx="1.5" fill="#FFFFFF" />
                    </svg>
                  </div>
                  <div className="hidden group-hover:block">
                    <div className="h-10 w-10 flex items-center justify-center rounded-md hover:bg-neutral-200 dark:hover:bg-zinc-700 transition-colors">
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-brutal-black dark:text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
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
              <div className="flex border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
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
                      ${mainView === view.id
                        ? 'bg-brutal-black text-white dark:bg-brutal-yellow dark:text-brutal-black'
                        : 'bg-white dark:bg-zinc-700 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-600'}
                    `}
                  >
                    {view.label}
                  </button>
                ))}
              </div>

              {/* Dark mode toggle */}
              <button
                onClick={toggleTheme}
                className="h-10 w-10 flex items-center justify-center rounded-md hover:bg-neutral-200 dark:hover:bg-zinc-700 transition-colors text-brutal-black dark:text-white"
                aria-label={theme === 'dark' ? t('settings.switchToLight') : t('settings.switchToDark')}
                title={theme === 'dark' ? t('settings.switchToLight') : t('settings.switchToDark')}
              >
                {theme === 'dark' ? (
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <circle cx="12" cy="12" r="5" />
                    <line x1="12" y1="1" x2="12" y2="3" />
                    <line x1="12" y1="21" x2="12" y2="23" />
                    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                    <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                    <line x1="1" y1="12" x2="3" y2="12" />
                    <line x1="21" y1="12" x2="23" y2="12" />
                    <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                    <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
                  </svg>
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
                  </svg>
                )}
              </button>

              {mainView === 'chat' ? (
                <button
                  onClick={() => handleRightSidebarToggle(!isRightSidebarOpen)}
                  className={`
                    h-10 w-10 flex items-center justify-center rounded-md transition-colors
                    ${isRightSidebarOpen
                      ? 'bg-neutral-200 dark:bg-zinc-700 text-brutal-black dark:text-white'
                      : 'hover:bg-neutral-200 dark:hover:bg-zinc-700 text-brutal-black dark:text-white'}
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
                onRightSidebarWidthChange={setRightSidebarWidth}
                rightSidebarMaxWidthPx={rightSidebarMaxWidthPx}
                viewportWidthPx={viewportWidth}
                rightSidebarForceFullView={rightSidebarForceFullView}
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


// Map each setup step message to a progress percentage.
// Steps that aren't listed fall back to the previous progress value.
const STEP_PROGRESS: Record<string, number> = {
  'Setting up Python environment...': 5,
  'Creating Python virtual environment...': 20,
  'Installing packages...': 45,
  'Installing Playwright Chromium browser (this may take a few minutes)...': 70,
  'Finalizing setup...': 88,
  'Starting backend server...': 95,
  'Starting backend...': 95,
};

function BackendLoadingScreen({ error, onRetry }: { error?: string | null; onRetry?: () => void }) {
  const locale = getInitialLocale();
  const t = (key: string, params?: Record<string, string>) => tForLocale(locale, key, params);
  const [setupStep, setSetupStep] = React.useState<string | null>(null);
  const [progress, setProgress] = React.useState(0);

  React.useEffect(() => {
    if (error) return;
    const interval = setInterval(() => {
      const step = (window as any).__SUZENT_SETUP_STEP__;
      if (step && step !== setupStep) {
        setSetupStep(step);
        const pct = STEP_PROGRESS[step];
        if (pct !== undefined) setProgress(pct);
      }
    }, 150);
    return () => clearInterval(interval);
  }, [error, setupStep]);

  return (
    <div className="flex flex-col items-center justify-center h-screen bg-neutral-50 font-sans p-8 text-center border-8 border-brutal-black">
      <div className="bg-white p-8 border-4 border-brutal-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] max-w-md w-full flex flex-col items-center">
        <div className="w-32 h-32 mb-6">
          <RobotAvatar variant={error ? 'ghost' : 'idle'} className="w-full h-full" />
        </div>
        <h1 className="text-4xl font-brutal font-black uppercase mb-4 text-brutal-black">
          {error ? t('app.backendErrorTitle') : t('app.initializing')}
        </h1>
        <p className="font-bold text-lg mb-6 leading-tight min-h-[2rem]">
          {error || setupStep || t('app.connectingToCore')}
        </p>
        {error && onRetry ? (
          <button
            onClick={onRetry}
            className="px-6 py-3 bg-brutal-black text-white font-bold uppercase border-3 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] hover:shadow-none hover:translate-x-1 hover:translate-y-1 transition-all"
          >
            {t('common.retry')}
          </button>
        ) : (
          <div className="w-full">
            <div className="w-full h-4 bg-neutral-200 border-2 border-brutal-black overflow-hidden relative">
              {progress > 0 ? (
                <div
                  className="absolute top-0 left-0 h-full bg-brutal-black transition-all duration-500 ease-out"
                  style={{ width: `${progress}%` }}
                />
              ) : (
                <div className="absolute top-0 left-0 h-full w-1/2 bg-brutal-black animate-[slide_1s_ease-in-out_infinite]" />
              )}
            </div>
            {progress > 0 && (
              <p className="text-right text-xs font-mono mt-1 text-neutral-500">{progress}%</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function hasPersistedBackendPort(): boolean {
  try {
    return !!sessionStorage.getItem('SUZENT_PORT') || !!localStorage.getItem('SUZENT_PORT');
  } catch {
    return false;
  }
}

async function isBackendReachable(): Promise<boolean> {
  const apiBase = (() => {
    try {
      const injected = (window as any).__SUZENT_BACKEND_PORT__;
      if (typeof injected === 'number' && Number.isFinite(injected)) {
        return `http://localhost:${injected}`;
      }
      const persisted = sessionStorage.getItem('SUZENT_PORT') || localStorage.getItem('SUZENT_PORT');
      if (persisted) return `http://localhost:${persisted}`;
    } catch {
      // ignore
    }
    return '';
  })();

  if (!apiBase) return false;

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 1500);
  try {
    const res = await fetch(`${apiBase}/config`, { signal: controller.signal });
    return res.ok;
  } catch {
    return false;
  } finally {
    window.clearTimeout(timeout);
  }
}

export default function App() {
  const locale = getInitialLocale();
  const t = (key: string, params?: Record<string, string>) => tForLocale(locale, key, params);

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

  // `backendReady` is driven by the Tauri `backend-ready` event emitted after the backend
  // is confirmed healthy. We never trust stale localStorage here — localStorage may hold
  // a port from a previous session while the backend is still starting up.
  // The initial value handles the rare race where Rust injects the port before React renders.
  const [backendReady, setBackendReady] = React.useState<boolean>(
    !!(window as any).__SUZENT_BACKEND_PORT__ || hasPersistedBackendPort()
  );
  const [backendError, setBackendError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (backendReady) return;
    let unlisten: (() => void) | undefined;
    let unlistenErr: (() => void) | undefined;
    let cancelled = false;

    // Handle WebView refresh race: backend-ready may have been emitted before listeners attach.
    // If we have a persisted port, probe backend health and continue without waiting forever.
    if (hasPersistedBackendPort()) {
      isBackendReachable().then((ok) => {
        if (!cancelled && ok) {
          setBackendReady(true);
          setBackendError(null);
        }
      });
    }

    import('@tauri-apps/api/event').then(({ listen }) => {
      listen<number>('backend-ready', () => {
        setBackendReady(true);
      }).then((fn) => { unlisten = fn; });
      listen<string>('backend-error', (event) => {
        setBackendError(event.payload);
      }).then((fn) => { unlistenErr = fn; });
    });
    return () => {
      cancelled = true;
      unlisten?.();
      unlistenErr?.();
    };
  }, [backendReady]);

  if (!backendReady || backendError) {
    return <BackendLoadingScreen error={backendError} />;
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
