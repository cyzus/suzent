import React, { useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { ArrowPathIcon, CheckCircleIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';

import { ChatList } from './components/ChatList';
import { ChatWindow } from './components/ChatWindow';
import { BackendLoadingScreen } from './components/BackendLoadingScreen';
import { ErrorBoundary } from './components/ErrorBoundary';
import { RobotAvatar } from './components/chat/RobotAvatar';
import { SuzentLogo } from './components/SuzentLogo';
import { RobotShowcase } from './components/chat/RobotShowcase';
import { MemoryView } from './components/memory/MemoryView';
import { SettingsModal } from './components/settings/SettingsModal';
import { ConfigView } from './components/sidebar/ConfigView';
import { BrutalSegmentedTabs } from './components/BrutalSegmentedTabs';
import { Sidebar } from './components/sidebar/Sidebar';
import { SkillsView } from './components/skills/SkillsView';
import { StatusBar } from './components/StatusBar';
import { ChatProvider, useChatCoreStore } from './hooks/useChatStore';
import { GoalTasksProvider, useGoalTasks } from './hooks/useGoalTasks';
import { ProjectProvider } from './hooks/useProjects';
import { useStatusStore } from './hooks/useStatusStore';
import { useTheme } from './hooks/useTheme';
import { drainCronNotifications, fetchHeartbeatStatus } from './lib/api';
import { isBusStreaming } from './hooks/useEventBus';
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
import { detectDesktopPlatform } from './lib/titleBarPlatform';
import { useI18n, getInitialLocale, tForLocale } from './i18n';

interface HeaderTitleProps {
  text?: string;
  onUnlock?: () => void;
}

interface BootstrapStatus {
  required: boolean;
  workspace_dir: string;
  installer_available: boolean;
  installer_path?: string | null;
}

interface BootstrapStage {
  name: string;
  title: string;
  category: string;
  needs_user_input: boolean;
}

interface BootstrapManifest {
  protocol_version: number;
  stages: BootstrapStage[];
}

interface BootstrapStageResult {
  stage: string;
  ok: boolean;
  skipped: boolean;
  reason?: string | null;
  duration_ms: number;
}

type BootstrapStageState = 'pending' | 'running' | 'succeeded' | 'skipped' | 'failed';

function BootstrapWindowBar(): React.ReactElement {
  const locale = getInitialLocale();
  const t = (key: string, params?: Record<string, string>) => tForLocale(locale, key, params);
  const appWindow = window.__TAURI__?.window.getCurrentWindow();
  const [isMaximized, setIsMaximized] = React.useState(false);

  async function handleDrag(event: React.MouseEvent<HTMLDivElement>): Promise<void> {
    const target = event.target as HTMLElement;
    if (target.closest('button')) return;
    await appWindow?.startDragging();
  }

  async function handleMaximize(): Promise<void> {
    await appWindow?.toggleMaximize();
    setIsMaximized(prev => !prev);
  }

  return (
    <div
      className="h-12 bg-white border-b border-neutral-200 flex items-center justify-between px-4 select-none"
      onMouseDown={handleDrag}
      data-tauri-drag-region
    >
      <div className="flex items-center gap-2 pointer-events-none">
        <div className="w-2.5 h-2.5 bg-brutal-black" />
        <span className="font-brutal text-sm uppercase text-brutal-black">
          {t('bootstrap.windowTitle')}
        </span>
      </div>
      <div className="flex h-full items-center text-brutal-black">
        <button
          type="button"
          onMouseDown={(event) => event.stopPropagation()}
          onClick={() => appWindow?.minimize()}
          className="h-full w-10 flex items-center justify-center hover:bg-neutral-100"
          title={t('titlebar.minimize')}
        >
          <span className="h-0.5 w-3 bg-current" />
        </button>
        <button
          type="button"
          onMouseDown={(event) => event.stopPropagation()}
          onClick={handleMaximize}
          className="h-full w-10 flex items-center justify-center hover:bg-neutral-100"
          title={isMaximized ? t('titlebar.restore') : t('titlebar.maximize')}
        >
          <span className="h-3 w-3 border-2 border-current" />
        </button>
        <button
          type="button"
          onMouseDown={(event) => event.stopPropagation()}
          onClick={() => appWindow?.close()}
          className="h-full w-10 flex items-center justify-center hover:bg-brutal-red hover:text-white"
          title={t('titlebar.close')}
        >
          <span className="text-lg leading-none">×</span>
        </button>
      </div>
    </div>
  );
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

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>): void {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      handleClick();
    }
  }

  return (
    <div
      className="flex items-center gap-3 cursor-pointer select-none"
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
      aria-label={text || backendConfig?.title || 'SUZENT'}
    >
      <div className="w-3 h-3 bg-brutal-black dark:bg-brutal-yellow"></div>
      <h1 className="font-brutal text-3xl text-brutal-black dark:text-white tracking-tighter uppercase leading-none">
        {text || backendConfig?.title || 'SUZENT'}
      </h1>
      <div className="w-3 h-3 bg-brutal-black dark:bg-brutal-yellow"></div>
    </div>
  );
}

interface MacTrafficLightsProps {
  isMaximized: boolean;
  onMaximize: () => void;
}

function MacTrafficLights({ isMaximized, onMaximize }: MacTrafficLightsProps): React.ReactElement {
  const { t } = useI18n();
  const appWindow = window.__TAURI__?.window.getCurrentWindow();

  return (
    <div className="mr-3 flex h-10 shrink-0 items-center gap-2" aria-label={t('app.title')}>
      <button
        onClick={() => appWindow?.close()}
        className="h-3 w-3 rounded-full border border-[#e0443e] bg-[#ff5f57] transition-opacity hover:opacity-90"
        title={t('titlebar.close')}
      />
      <button
        onClick={() => appWindow?.minimize()}
        className="h-3 w-3 rounded-full border border-[#dfa123] bg-[#febc2e] transition-opacity hover:opacity-90"
        title={t('titlebar.minimize')}
      />
      <button
        onClick={onMaximize}
        className="h-3 w-3 rounded-full border border-[#1ea833] bg-[#28c840] transition-opacity hover:opacity-90"
        title={isMaximized ? t('titlebar.restore') : t('titlebar.maximize')}
      />
    </div>
  );
}

type MainView = 'chat' | 'memory' | 'skills' | 'emotes';

interface UpdateStatus {
  current_version?: string;
  latest_version?: string;
  update_available?: boolean;
  error?: string;
}

function NavTabs({ mainView, setMainView }: { mainView: MainView; setMainView: (v: MainView) => void }): React.ReactElement {
  const { t } = useI18n();
  return (
    <BrutalSegmentedTabs
      value={mainView}
      onChange={setMainView}
      tabs={[
        { id: 'chat', label: t('nav.chat') },
        { id: 'memory', label: t('nav.memory') },
        { id: 'skills', label: t('nav.skills') },
      ]}
    />
  );
}

function UpdateButton(): React.ReactElement | null {
  const { t } = useI18n();
  const setStatusMsg = useStatusStore(s => s.setStatus);
  const [updateStatus, setUpdateStatus] = React.useState<UpdateStatus | null>(null);
  const [isStartingUpdate, setIsStartingUpdate] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;

    invoke<string>('check_for_update')
      .then((raw) => {
        if (cancelled) return;
        setUpdateStatus(JSON.parse(raw) as UpdateStatus);
      })
      .catch(() => {
        if (!cancelled) setUpdateStatus(null);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (!updateStatus?.update_available) {
    return null;
  }

  async function handleUpdate(): Promise<void> {
    const latest = updateStatus?.latest_version || t('updates.latestVersion');
    const ok = window.confirm(t('updates.confirmRestart', { version: latest }));
    if (!ok) return;

    setIsStartingUpdate(true);
    try {
      await invoke('start_update_and_restart');
    } catch (error) {
      setIsStartingUpdate(false);
      const message = error instanceof Error ? error.message : String(error);
      setStatusMsg(t('updates.startFailed', { error: message }), 'error', 6000);
    }
  }

  return (
    <button
      onClick={handleUpdate}
      disabled={isStartingUpdate}
      className="h-10 w-10 flex items-center justify-center rounded-md hover:bg-neutral-200 dark:hover:bg-zinc-700 transition-colors text-brutal-black dark:text-white disabled:opacity-50 disabled:cursor-wait"
      aria-label={t('updates.available')}
      title={t('updates.availableTitle', { version: updateStatus.latest_version || t('updates.latestVersion') })}
    >
      <ArrowPathIcon className={`h-5 w-5 ${isStartingUpdate ? 'animate-spin' : ''}`} />
    </button>
  );
}

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

  const { refresh: refreshGoalTasks, refreshKanban } = useGoalTasks();
  const { currentChatId, setViewSwitcher, refreshChatList, refreshChatListSilently, chats, loadChat } = useChatCoreStore();
  const setStatusMsg = useStatusStore(s => s.setStatus);
  const setHeartbeatStatus = useHeartbeatRunning(s => s.setStatus);
  const setChatHeartbeatStatus = useHeartbeatRunning(s => s.setChatStatus);
  const { theme, toggleTheme } = useTheme();
  const { t } = useI18n();
  const [isWindowMaximized, setIsWindowMaximized] = useState(false);

  const desktopPlatform = React.useMemo(
    () => detectDesktopPlatform(navigator.userAgent, navigator.platform),
    [],
  );
  const showStandaloneTitleBar = desktopPlatform !== 'windows' && desktopPlatform !== 'macos';
  const showWindowsWindowControls = desktopPlatform === 'windows';
  const showMacWindowControls = !!window.__TAURI__ && desktopPlatform === 'macos';
  const appWindow = window.__TAURI__?.window.getCurrentWindow();

  // Use refs so the interval callback always sees the latest values without re-creating the interval.
  const refreshChatListRef = React.useRef(refreshChatList);
  const refreshChatListSilentRef = React.useRef(refreshChatListSilently);
  const loadChatRef = React.useRef(loadChat);
  const currentChatIdRef = React.useRef(currentChatId);
  const chatsRef = React.useRef(chats);
  const setChatHeartbeatStatusRef = React.useRef(setChatHeartbeatStatus);
  React.useEffect(() => { refreshChatListRef.current = refreshChatList; }, [refreshChatList]);
  React.useEffect(() => { refreshChatListSilentRef.current = refreshChatListSilently; }, [refreshChatListSilently]);
  React.useEffect(() => { loadChatRef.current = loadChat; }, [loadChat]);
  React.useEffect(() => { currentChatIdRef.current = currentChatId; }, [currentChatId]);
  React.useEffect(() => { chatsRef.current = chats; }, [chats]);
  React.useEffect(() => { setChatHeartbeatStatusRef.current = setChatHeartbeatStatus; }, [setChatHeartbeatStatus]);

  // Poll every 8 s: drain cron notifications + heartbeat status + refresh sidebar + reload open chat.
  React.useEffect(() => {
    const interval = setInterval(async () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        return;
      }
      // Heartbeat status runs in parallel with notification drain.
      const chatId = currentChatIdRef.current;
      const [notifications] = await Promise.all([
        drainCronNotifications(),
        fetchHeartbeatStatus().then(setHeartbeatStatus).catch(() => {}),
        chatId
          ? fetchHeartbeatStatus(chatId).then(s => setChatHeartbeatStatusRef.current(chatId, s)).catch(() => {})
          : Promise.resolve(),
      ]);
      if (notifications.length === 1) {
        setStatusMsg(`[${notifications[0].job_name}] finished — view in Social`, 'info', 4000);
      } else if (notifications.length > 1) {
        setStatusMsg(`${notifications.length} tasks finished — view in Social`, 'info', 4000);
      }

      // If a platform chat (cron/social) is open, reload its messages from DB.
      // Skip if a live background stream is active — the SSE connection already delivers events.
      const openChat = chatsRef.current.find(c => c.id === chatId);
      const isLiveStreamRunning = chatId ? isBusStreaming(chatId) : false;

      // Avoid redundant sidebar refreshes while SSE is already updating the active chat.
      if (!isLiveStreamRunning) {
        refreshChatListSilentRef.current();
      }

      if (chatId && (openChat?.platform || openChat?.heartbeatEnabled) && !openChat?.isRunning) {
        loadChatRef.current(chatId, { force: true });
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

  async function toggleWindowMaximize(): Promise<void> {
    await appWindow?.toggleMaximize();
    setIsWindowMaximized(prev => !prev);
  }

  function handleHeaderMouseDown(event: React.MouseEvent<HTMLElement>): void {
    if (!showWindowsWindowControls && !showMacWindowControls) {
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

  React.useEffect(() => {
    setViewSwitcher?.(setMainView as (view: 'chat' | 'memory') => void);
  }, [setViewSwitcher, setMainView]);

  React.useEffect(() => {
    // Use chatsRef (not chats) so this effect only re-runs on chat selection change,
    // not on every chat list update (which would cause spurious re-renders mid-stream).
    const chat = currentChatId ? chatsRef.current.find(c => c.id === currentChatId) : null;
    const projectId = chat?.projectId ?? null;
    refreshGoalTasks(projectId, currentChatId ?? null);
    refreshKanban(projectId);

    // Auto-collapse right sidebar on new chat
    if (!currentChatId) {
      setIsRightSidebarOpen(false);
    }

    if (window.innerWidth < DESKTOP_BREAKPOINT_PX) {
      setIsLeftSidebarOpen(false);
    }
  }, [currentChatId, refreshGoalTasks, refreshKanban]); // eslint-disable-line react-hooks/exhaustive-deps

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
      <div className={`flex h-full relative ${showStandaloneTitleBar ? 'pt-8' : ''}`}>
        <Sidebar
          activeTab={sidebarTab}
          onTabChange={setSidebarTab}
          chatsContent={<ChatList />}
          configContent={<ConfigView isActive={sidebarTab === 'config' && isLeftSidebarOpen} />}
          isOpen={isLeftSidebarOpen}
          onOpenSettings={() => setIsSettingsOpen(true)}
          onClose={() => setIsLeftSidebarOpen(false)}
          titlebarControls={
            showMacWindowControls && isLeftSidebarOpen ? (
              <MacTrafficLights isMaximized={isWindowMaximized} onMaximize={toggleWindowMaximize} />
            ) : null
          }
        />
        <div className="flex-1 flex flex-col overflow-hidden w-full">
          <header
            className="relative border-b-3 border-brutal-black px-4 md:px-6 flex items-center justify-between bg-brutal-white dark:bg-zinc-800 flex-shrink-0 h-12"
            onMouseDown={handleHeaderMouseDown}
          >
            <div className="flex items-center gap-2 md:gap-0">
              {showMacWindowControls && !isLeftSidebarOpen ? (
                <MacTrafficLights isMaximized={isWindowMaximized} onMaximize={toggleWindowMaximize} />
              ) : null}
              {isLeftSidebarOpen ? (
                <div className="h-10 w-10 mr-3" aria-hidden="true" />
              ) : (
                <div
                  className="mr-3 group h-10 w-10 cursor-pointer rounded-md transition-colors hover:bg-neutral-200 dark:hover:bg-zinc-700"
                  onClick={toggleLeftSidebar}
                  role="button"
                  aria-label={t('sidebar.open')}
                  title={t('sidebar.open')}
                >
                  <div className="flex h-full w-full items-center justify-center group-hover:hidden">
                    <SuzentLogo className="h-7 w-7" interactive />
                  </div>
                  <div className="hidden h-full w-full items-center justify-center group-hover:flex">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-brutal-black dark:text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <rect x="4" y="4" width="16" height="16" rx="2" />
                      <line x1="9" y1="4" x2="9" y2="20" />
                    </svg>
                  </div>
                </div>
              )}
              <HeaderTitle text={getTitle()} onUnlock={() => setMainView('emotes')} />
            </div>

            <div className={`flex items-center gap-3 ${showWindowsWindowControls ? 'pr-[108px]' : ''}`}>
              <NavTabs mainView={mainView} setMainView={setMainView} />
              <UpdateButton />

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

              {showWindowsWindowControls ? (
                <div className="absolute right-0 top-0 bottom-0 flex text-brutal-black dark:text-white overflow-hidden">
                  <button
                    onClick={() => appWindow?.minimize()}
                    className="h-full w-9 flex items-center justify-center hover:bg-brutal-black dark:hover:bg-zinc-600 hover:text-brutal-white transition-colors"
                    title={t('titlebar.minimize')}
                  >
                    <svg width="10" height="2" viewBox="0 0 10 2" fill="currentColor">
                      <rect width="10" height="2" />
                    </svg>
                  </button>
                  <button
                    onClick={toggleWindowMaximize}
                    className="h-full w-9 flex items-center justify-center hover:bg-brutal-black dark:hover:bg-zinc-600 hover:text-brutal-white transition-colors"
                    title={isWindowMaximized ? t('titlebar.restore') : t('titlebar.maximize')}
                  >
                    {isWindowMaximized ? (
                      <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2">
                        <rect x="2" y="0" width="8" height="8" rx="0" />
                        <rect x="0" y="2" width="8" height="8" rx="0" />
                      </svg>
                    ) : (
                      <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2">
                        <rect x="0" y="0" width="10" height="10" rx="0" />
                      </svg>
                    )}
                  </button>
                  <button
                    onClick={() => appWindow?.close()}
                    className="h-full w-9 flex items-center justify-center hover:bg-brutal-red hover:text-white transition-colors"
                    title={t('titlebar.close')}
                  >
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="0" y1="0" x2="10" y2="10" />
                      <line x1="10" y1="0" x2="0" y2="10" />
                    </svg>
                  </button>
                </div>
              ) : null}
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


function BootstrapInstallScreen({
  status,
  onComplete,
}: {
  status: BootstrapStatus;
  onComplete: () => void;
}) {
  const locale = getInitialLocale();
  const t = (key: string, params?: Record<string, string>) => tForLocale(locale, key, params);
  const [stages, setStages] = React.useState<BootstrapStage[]>([]);
  const [stageStates, setStageStates] = React.useState<Record<string, BootstrapStageState>>({});
  const [activeStage, setActiveStage] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [running, setRunning] = React.useState(false);
  const [details, setDetails] = React.useState<string[]>([]);
  const [installDir, setInstallDir] = React.useState(status.workspace_dir);

  const completedCount = stages.filter(stage => {
    const state = stageStates[stage.name];
    return state === 'succeeded' || state === 'skipped';
  }).length;
  const progress = stages.length > 0 ? Math.round((completedCount / stages.length) * 100) : 0;
  const stageTitle = React.useCallback((stage: BootstrapStage): string => {
    const translated = t(`bootstrap.stages.${stage.name}`);
    return translated === `bootstrap.stages.${stage.name}` ? stage.title : translated;
  }, [t]);

  const loadManifest = React.useCallback(async () => {
    const raw = await invoke<string>('bootstrap_manifest');
    const manifest = JSON.parse(raw) as BootstrapManifest;
    setStages(manifest.stages);
    setStageStates(Object.fromEntries(manifest.stages.map(stage => [stage.name, 'pending'])));
  }, []);

  React.useEffect(() => {
    loadManifest().catch((err) => {
      setError(err instanceof Error ? err.message : String(err));
    });
  }, [loadManifest]);

  React.useEffect(() => {
    setInstallDir(status.workspace_dir);
  }, [status.workspace_dir]);

  const chooseInstallDir = React.useCallback(async () => {
    if (running) return;
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({
        directory: true,
        multiple: false,
        title: t('bootstrap.chooseInstallDir'),
        defaultPath: installDir,
      });
      if (typeof selected === 'string' && selected.trim()) {
        setInstallDir(selected);
        setError(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [installDir, running, t]);

  const runInstall = React.useCallback(async () => {
    if (running || stages.length === 0) return;
    setRunning(true);
    setError(null);
    setDetails([]);

    try {
      await invoke('set_install_workspace', { request: { dir: installDir } });
      for (const stage of stages) {
        setActiveStage(stage.name);
        setStageStates(prev => ({ ...prev, [stage.name]: 'running' }));
        const raw = await invoke<string>('run_bootstrap_stage', { request: { stage: stage.name, dir: installDir } });
        const result = JSON.parse(raw) as BootstrapStageResult;

        if (!result.ok) {
          const reason = result.reason || t('bootstrap.stageFailed', { stage: stageTitle(stage) });
          setStageStates(prev => ({ ...prev, [stage.name]: 'failed' }));
          setError(reason);
          setDetails(prev => [...prev, `${stageTitle(stage)}: ${reason}`]);
          return;
        }

        setStageStates(prev => ({
          ...prev,
          [stage.name]: result.skipped ? 'skipped' : 'succeeded',
        }));
        if (result.reason) {
          setDetails(prev => [...prev, `${stageTitle(stage)}: ${result.reason}`]);
        }
      }

      setActiveStage(null);
      await invoke('retry_backend_start');
      onComplete();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }, [installDir, onComplete, running, stageTitle, stages, t]);

  return (
    <div className="h-screen overflow-hidden bg-neutral-100 font-sans text-brutal-black flex flex-col">
      <BootstrapWindowBar />
      <div className="flex-1 min-h-0 flex items-center justify-center p-6">
      <div className="w-full max-w-3xl max-h-full min-h-0 bg-white border border-neutral-300 shadow-[0_18px_48px_rgba(0,0,0,0.12)] p-6 flex flex-col">
        <div className="flex items-start gap-5">
          <div className="w-24 h-24 shrink-0">
            <RobotAvatar variant={error ? 'ghost' : running ? 'scanner' : 'idle'} className="w-full h-full" />
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="text-3xl font-brutal font-black uppercase text-brutal-black">
              {t('bootstrap.title')}
            </h1>
            <div className="mt-2 flex items-center gap-2">
              <p className="font-mono text-xs text-neutral-500 truncate" title={installDir}>
                {installDir}
              </p>
              <button
                type="button"
                disabled={running}
                onClick={chooseInstallDir}
                className="shrink-0 px-2 py-1 text-xs font-bold uppercase border border-neutral-300 hover:bg-neutral-100 disabled:opacity-50"
              >
                {t('bootstrap.changeDir')}
              </button>
            </div>
            {!status.installer_available && (
              <p className="mt-3 text-sm font-bold text-brutal-red">
                {t('bootstrap.installerMissing')}
              </p>
            )}
          </div>
        </div>

        <div className="mt-6 h-3 bg-neutral-200 border border-neutral-300 overflow-hidden">
          <div
            className="h-full bg-blue-500 transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="text-right text-xs font-mono mt-1 text-neutral-500">{progress}%</p>

        <div className="mt-5 min-h-0 flex-1 overflow-y-auto pr-2 grid gap-2 content-start">
          {stages.map(stage => {
            const state = stageStates[stage.name] || 'pending';
            const isActive = activeStage === stage.name;
            return (
              <div
                key={stage.name}
                className={`flex items-center justify-between border px-3 py-2 ${
                  isActive ? 'border-blue-400 bg-blue-50' : 'border-neutral-200 bg-neutral-50'
                }`}
              >
                <div className="min-w-0">
                  <p className="font-bold uppercase text-sm truncate">{stageTitle(stage)}</p>
                </div>
                <div className="ml-3 flex items-center gap-2 font-mono text-xs uppercase">
                  {state === 'running' && <ArrowPathIcon className="w-4 h-4 animate-spin" />}
                  {state === 'succeeded' && <CheckCircleIcon className="w-4 h-4" />}
                  {state === 'failed' && <ExclamationTriangleIcon className="w-4 h-4 text-brutal-red" />}
                  <span>{t(`bootstrap.state.${state}`)}</span>
                </div>
              </div>
            );
          })}
        </div>

        {details.length > 0 && (
          <div className="mt-4 shrink-0 bg-neutral-100 border border-neutral-300 p-3 max-h-28 overflow-auto text-left">
            {details.map((line, idx) => (
              <p key={`${line}-${idx}`} className="font-mono text-xs text-neutral-700">{line}</p>
            ))}
          </div>
        )}

        {error && (
          <p className="mt-4 text-sm font-bold text-brutal-red border-2 border-brutal-red p-3">
            {error}
          </p>
        )}

        <div className="mt-6 shrink-0 flex justify-end gap-3">
          <button
            type="button"
            disabled={running || !status.installer_available || stages.length === 0}
            onClick={runInstall}
            className="px-5 py-3 bg-blue-500 text-white font-bold uppercase border border-blue-600 hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {running ? t('bootstrap.running') : error ? t('common.retry') : t('bootstrap.start')}
          </button>
        </div>
      </div>
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

function rememberBackendPort(port: number): void {
  (window as any).__SUZENT_BACKEND_PORT__ = port;
  try {
    sessionStorage.setItem('SUZENT_PORT', String(port));
  } catch {
    // ignore
  }
  try {
    localStorage.setItem('SUZENT_PORT', String(port));
  } catch {
    // ignore
  }
}

function getRememberedBackendPort(): number | null {
  try {
    const injected = (window as any).__SUZENT_BACKEND_PORT__;
    if (typeof injected === 'number' && Number.isFinite(injected)) return injected;
    const stored = sessionStorage.getItem('SUZENT_PORT') || localStorage.getItem('SUZENT_PORT');
    if (!stored) return null;
    const parsed = Number.parseInt(stored, 10);
    return Number.isFinite(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

async function isBackendPortReachable(port: number): Promise<boolean> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 1500);
  try {
    const res = await fetch(`http://127.0.0.1:${port}/config`, { signal: controller.signal });
    return res.ok;
  } catch {
    return false;
  } finally {
    window.clearTimeout(timeout);
  }
}

async function waitForBackendPort(options?: { attempts?: number }): Promise<number | null> {
  const attempts = options?.attempts ?? 12;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const candidates: number[] = [];
    const remembered = getRememberedBackendPort();
    if (remembered) candidates.push(remembered);

    try {
      const tauriPort = await invoke<number>('get_backend_port');
      candidates.unshift(tauriPort);
    } catch {
      // A dev backend may only be discoverable from storage after a WebView refresh.
    }

    for (const port of Array.from(new Set(candidates))) {
      if (await isBackendPortReachable(port)) {
        rememberBackendPort(port);
        return port;
      }
    }

    await new Promise(resolve => window.setTimeout(resolve, Math.min(500 * Math.pow(1.35, attempt), 2500)));
  }
  return null;
}

function StartupDecisionScreen(): React.ReactElement {
  return <div className="h-screen w-screen bg-neutral-100" />;
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

  React.useEffect(() => {
    invoke('frontend_ready').catch(() => {
      // Older/dev shells may not expose this command yet.
    });
  }, []);

  // `backendReady` is driven by the Tauri `backend-ready` event emitted after the backend
  // is confirmed healthy. We never trust stale localStorage here — localStorage may hold
  // a port from a previous session while the backend is still starting up.
  // Gate rendering until bootstrap_status answers, so the chat UI cannot flash
  // before the installer/onboarding decision is known.
  const [backendReady, setBackendReady] = React.useState<boolean>(false);
  const [backendError, setBackendError] = React.useState<string | null>(null);
  const [bootstrapStatusState, setBootstrapStatusState] = React.useState<BootstrapStatus | null>(null);
  const [bootstrapChecked, setBootstrapChecked] = React.useState(false);
  const [backendStartingAtStartup, setBackendStartingAtStartup] = React.useState(false);
  const [backendStartingAfterInstall, setBackendStartingAfterInstall] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    invoke<BootstrapStatus>('bootstrap_status')
      .then((status) => {
        if (cancelled) return;
        if (status.required) {
          setBackendReady(false);
          setBackendError(null);
          setBackendStartingAtStartup(false);
          setBootstrapStatusState(status);
        } else if ((window as any).__SUZENT_BACKEND_PORT__) {
          setBackendReady(true);
          setBackendStartingAtStartup(false);
        } else {
          setBackendStartingAtStartup(true);
          waitForBackendPort()
            .then((port) => {
              if (cancelled || port === null) return;
              setBackendReady(true);
              setBackendError(null);
              setBackendStartingAtStartup(false);
            })
            .catch(() => {});
        }
        setBootstrapChecked(true);
      })
      .catch(() => {
        // The backend-error event handles startup failures.
        if (!cancelled) setBootstrapChecked(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    if (backendReady) return;
    let unlisten: (() => void) | undefined;
    let unlistenErr: (() => void) | undefined;
    let unlistenBootstrap: (() => void) | undefined;
    let cancelled = false;

    // Handle WebView refresh race: backend-ready may have been emitted before listeners attach.
    // If we have a persisted port, probe backend health and continue without waiting forever.
    if (hasPersistedBackendPort()) {
      waitForBackendPort({ attempts: 8 }).then((port) => {
        if (!cancelled && port !== null) {
          setBackendReady(true);
          setBackendError(null);
          setBackendStartingAtStartup(false);
          setBackendStartingAfterInstall(false);
        }
      });
    }

    import('@tauri-apps/api/event').then(({ listen }) => {
      listen<number>('backend-ready', (event) => {
        rememberBackendPort(event.payload);
        setBackendReady(true);
        setBackendError(null);
        setBackendStartingAtStartup(false);
        setBackendStartingAfterInstall(false);
        setBootstrapStatusState(null);
      }).then((fn) => { unlisten = fn; });
      listen<string>('backend-error', (event) => {
        setBackendStartingAtStartup(false);
        setBackendStartingAfterInstall(false);
        setBackendError(event.payload);
      }).then((fn) => { unlistenErr = fn; });
      listen<BootstrapStatus>('bootstrap-required', (event) => {
        setBootstrapChecked(true);
        setBackendError(null);
        setBackendReady(false);
        setBackendStartingAtStartup(false);
        setBackendStartingAfterInstall(false);
        setBootstrapStatusState(event.payload);
      }).then((fn) => { unlistenBootstrap = fn; });
    });
    return () => {
      cancelled = true;
      unlisten?.();
      unlistenErr?.();
      unlistenBootstrap?.();
    };
  }, [backendReady]);

  return (
    <ErrorBoundary>
      {!bootstrapChecked ? (
        <StartupDecisionScreen />
      ) : bootstrapStatusState ? (
        <BootstrapInstallScreen
          status={bootstrapStatusState}
          onComplete={() => {
            setBootstrapStatusState(null);
            setBackendError(null);
            setBackendStartingAfterInstall(true);
          }}
        />
      ) : backendError ? (
        <BackendLoadingScreen error={backendError} />
      ) : backendStartingAfterInstall || backendStartingAtStartup ? (
        <BackendLoadingScreen />
      ) : !backendReady ? (
        <StartupDecisionScreen />
      ) : (
        <ProjectProvider>
          <ChatProvider>
            <GoalTasksProvider>
              <AppInner />
            </GoalTasksProvider>
          </ChatProvider>
        </ProjectProvider>
      )}
    </ErrorBoundary>
  );
}








