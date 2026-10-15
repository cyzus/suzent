import React, { useMemo, useState, useEffect, useRef, useCallback } from 'react';
import { useI18n } from '../../i18n';
import { TaskPanel } from '../sidebar/TaskPanel';
import { SandboxFiles } from '../sidebar/SandboxFiles';
import { WebActivitiesView } from '../sidebar/WebActivitiesView';
import { CanvasView } from '../sidebar/CanvasView';
import { BackgroundTaskView } from '../sidebar/BackgroundTaskView';
import { useBackgroundTasks } from '../../hooks/useBackgroundTasks';
import { BackgroundTaskList } from '../sidebar/BackgroundTaskList';
import { RepositoryContextView } from '../sidebar/RepositoryContextView';
import type { Message, Goal, Task } from '../../types/api';
import type { KanbanData } from '../../hooks/useGoalTasks';
import type { CanvasState } from '../../hooks/useCanvas';
import { useWebHistory } from '../../hooks/useWebHistory';
import {
  DESKTOP_BREAKPOINT_PX,
  MIN_RIGHT_SIDEBAR_WIDTH_PX,
  getRightSidebarMaxWidth,
  getCanvasSidebarWidth,
} from '../../lib/layout';
import {
  ChevronDoubleRightIcon,
  FolderIcon,
  GlobeAltIcon,
  PencilSquareIcon,
  CpuChipIcon,
  ClipboardDocumentListIcon,
  WrenchScrewdriverIcon,
  DocumentTextIcon,
} from '@heroicons/react/24/outline';
import { PanelResizeHandle } from '../PanelResizeHandle';
import { ToolsPanel } from './ToolsPanel';

// Icon strip width in px — keep in sync with w-11 (2.75rem = 44px)
const ICON_STRIP_WIDTH = 44;

export type TabId =
  'files' | 'context' | 'browser' | 'canvas' | 'agents' | 'plan' | 'project' | 'tools';

export interface AutoOpenFlags {
  chatId: string | null | undefined;
  file: boolean;
  fileToPreview: { path: string; name: string; nonce?: number } | null | undefined;
  canvas: boolean;
  canvasResolved: boolean;
  subAgent: boolean;
  viewingSubAgentTaskId: string | null | undefined;
  webContext: boolean;
  forcedWebContextId: string | null | undefined;
  goal: boolean;
  goalResolved: boolean;
}

export function evaluateSidebarAutoOpen(
  prev: AutoOpenFlags,
  flags: AutoOpenFlags
): { nextTab: TabId | null; shouldOpen: boolean } {
  if (prev.chatId !== flags.chatId) {
    return { nextTab: null, shouldOpen: false };
  }

  const fileTriggered = flags.file && prev.fileToPreview !== flags.fileToPreview;
  const subAgentTriggered =
    flags.subAgent && prev.viewingSubAgentTaskId !== flags.viewingSubAgentTaskId;
  const webContextTriggered =
    flags.webContext && prev.forcedWebContextId !== flags.forcedWebContextId;
  // Only treat canvas/goal as rising when it was already resolved for THIS
  // chat in the previous render (not transitioning from unresolved → resolved
  // after the initial fetch for the switched chat lands).
  const canvasRose = prev.canvasResolved && flags.canvasResolved && !prev.canvas && flags.canvas;
  const goalRose = prev.goalResolved && flags.goalResolved && !prev.goal && flags.goal;

  let nextTab: TabId | null = null;
  if (fileTriggered) {
    nextTab = 'files';
  } else if (subAgentTriggered) {
    nextTab = 'agents';
  } else if (webContextTriggered) {
    nextTab = 'browser';
  } else if (canvasRose && !flags.file) {
    nextTab = 'canvas';
  } else if (goalRose && !flags.file) {
    // Async task refreshes must not hide an explicitly requested output file.
    nextTab = 'plan';
  }

  return {
    nextTab,
    shouldOpen: fileTriggered || subAgentTriggered || webContextTriggered || canvasRose || goalRose,
  };
}

interface RightSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onOpen: () => void;
  onWidthChange?: (width: number | null) => void;
  maxWidthPx?: number;
  wideContentDefaultWidthPx?: number;
  viewportWidthPx?: number;
  forceFullView?: boolean;
  goal: Goal | null;
  tasks: Task[];
  goalChatId?: string | null;
  kanban: KanbanData | null;
  currentProjectName?: string | null;
  currentProjectId?: string | null;
  chatTitles?: Record<string, string>;
  onOpenTask?: (task: Task) => Promise<boolean>;
  taskNavigationError?: string | null;
  onDismissTaskError?: () => void;
  onTaskChat?: (chatId: string) => Promise<boolean>;
  fileToPreview?: { path: string; name: string; nonce?: number } | null;
  onMaximizeFile?: (filePath: string, fileName: string) => void;
  canvas?: CanvasState;
  onCanvasDispatch?: (action: string, context: Record<string, unknown>, surfaceId: string) => void;
  viewingSubAgentTaskId?: string | null;
  onCloseSubAgent?: () => void;
  onSelectSubAgent?: (taskId: string) => void;
  currentChatId?: string | null;
  hasSubAgents?: boolean;
  /** This chat has spawned sub-agents at some point, live stream or not. */
  hasSubAgentHistory?: boolean;
  messages?: Message[];
  forcedWebContextId?: string | null;
  onClearForcedWebContext?: () => void;
  isNewChat?: boolean;
}

interface TabConfig {
  id: TabId;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  labelKey: string;
  fallbackLabel: string;
  hasContent: boolean;
  hasActivity: boolean;
  activityClass?: string;
}

export const RightSidebar: React.FC<RightSidebarProps> = ({
  isOpen,
  onClose,
  onOpen,
  onWidthChange,
  maxWidthPx,
  wideContentDefaultWidthPx,
  viewportWidthPx,
  forceFullView = false,
  goal,
  tasks,
  goalChatId,
  kanban,
  currentProjectName,
  chatTitles = {},
  onTaskChat,
  taskNavigationError,
  onDismissTaskError,
  onOpenTask,
  fileToPreview,
  onMaximizeFile,
  canvas,
  onCanvasDispatch,
  viewingSubAgentTaskId,
  onCloseSubAgent,
  onSelectSubAgent,
  currentChatId,
  hasSubAgents = false,
  hasSubAgentHistory = false,
  messages = [],
  forcedWebContextId,
  onClearForcedWebContext,
  isNewChat = false,
}) => {
  const { t } = useI18n();
  const { taskStates } = useBackgroundTasks();
  const backgroundTasks = Object.values(taskStates).filter(
    (task) => task.parent_chat_id === currentChatId
  );
  const hasBackgroundActivity = backgroundTasks.some(
    (task) => task.status === 'running' || task.status === 'queued'
  );
  const [activeTab, setActiveTab] = useState<TabId>('browser');
  const [isFileExpanded, setIsFileExpanded] = useState(false);
  const [isBrowserStreamActive, setIsBrowserStreamActive] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState<number | null>(null);
  const [coveringChat, setCoveringChat] = useState(false);
  const [coverWidth, setCoverWidth] = useState<number | null>(null);
  const [chatAreaWidth, setChatAreaWidth] = useState(0);
  const spacerRef = useRef<HTMLDivElement>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);
  const dragState = useRef(false);

  const effectiveViewportWidth = viewportWidthPx ?? window.innerWidth;
  const isDesktop = effectiveViewportWidth >= DESKTOP_BREAKPOINT_PX;
  const isOverlayMode = forceFullView || !isDesktop;

  // Canvas surfaces load async on chat switch; only treat them as content once
  // the surfaces are stamped for the chat we're viewing (avoids the previous
  // chat's canvas being read as current mid-switch).
  const canvasMatchesChat = !canvas || canvas.surfacesChatId === currentChatId;
  const hasCanvasContent = canvasMatchesChat && !!canvas?.hasSurfaces;

  const isCanvasActive = activeTab === 'canvas' && hasCanvasContent;
  const isBrowserActive = activeTab === 'browser';
  const effectiveMaxWidth = Math.max(
    MIN_RIGHT_SIDEBAR_WIDTH_PX,
    maxWidthPx ?? getRightSidebarMaxWidth(effectiveViewportWidth)
  );

  const shouldBuildWebHistory = isOpen || isBrowserStreamActive || Boolean(forcedWebContextId);
  const webHistoryMessages = useMemo(
    () => (shouldBuildWebHistory ? messages : []),
    [messages, shouldBuildWebHistory]
  );
  const webHistory = useWebHistory(webHistoryMessages);
  const hasWebActivity =
    webHistory.length > 0 ||
    (!shouldBuildWebHistory &&
      messages.some(
        (message) =>
          message.role === 'assistant' &&
          typeof message.content === 'string' &&
          (message.content.includes('web_search') || message.content.includes('webpage_fetch'))
      ));
  // Goal/tasks load async on chat switch; only treat them as content once the
  // fetched data is stamped for the chat we're viewing (see canvas scoping above).
  const goalMatchesChat = goalChatId === undefined || goalChatId === currentChatId;
  const hasGoalContent = goalMatchesChat && Boolean(goal !== null || tasks.length > 0);

  // ── Tab definitions ─────────────────────────────────────────────────
  const tabs: TabConfig[] = [
    {
      id: 'files',
      icon: FolderIcon,
      labelKey: 'sidebar.tabs.files',
      fallbackLabel: 'Files',
      hasContent: !!fileToPreview,
      hasActivity: !!fileToPreview,
    },
    {
      id: 'context',
      icon: DocumentTextIcon,
      labelKey: 'sidebar.tabs.context',
      fallbackLabel: 'Context',
      hasContent: Boolean(currentChatId),
      hasActivity: false,
    },
    {
      id: 'browser',
      icon: GlobeAltIcon,
      labelKey: 'sidebar.tabs.browser',
      fallbackLabel: 'Web',
      hasContent: isBrowserStreamActive || hasWebActivity,
      hasActivity: isBrowserStreamActive || hasWebActivity,
      activityClass: 'bg-brutal-green',
    },
    {
      id: 'canvas',
      icon: PencilSquareIcon,
      labelKey: 'sidebar.tabs.canvas',
      fallbackLabel: 'Canvas',
      hasContent: hasCanvasContent,
      hasActivity: hasCanvasContent,
      activityClass: 'bg-brutal-yellow',
    },
    {
      id: 'agents',
      icon: CpuChipIcon,
      labelKey: 'sidebar.tabs.agents',
      fallbackLabel: 'Background tasks',
      // Openable on history: the panel fetches its own list from /subagents,
      // so a reopened chat can show every past run. The dot stays tied to live
      // state -- a finished history is not activity.
      hasContent:
        backgroundTasks.length > 0 || hasSubAgents || hasSubAgentHistory || !!viewingSubAgentTaskId,
      hasActivity: hasBackgroundActivity,
      activityClass: 'bg-brutal-blue animate-pulse',
    },
    {
      id: 'plan',
      icon: ClipboardDocumentListIcon,
      labelKey: 'sidebar.tabs.plan',
      fallbackLabel: 'Tasks',
      hasContent: true,
      hasActivity: hasGoalContent,
      activityClass: 'bg-brutal-yellow',
    },
    {
      id: 'tools',
      icon: WrenchScrewdriverIcon,
      labelKey: 'sidebar.tabs.tools',
      fallbackLabel: 'Tools',
      hasContent: true, // always accessible
      hasActivity: false,
    },
  ];

  // ── Auto-switch tab & open sidebar when content arrives ────────────
  // Only auto-switch or auto-open when content transitions absent → present
  // *within the same chat*. On a chat switch we re-baseline without changing
  // the active tab or popping the sidebar, so switching chats preserves the
  // user's current sidebar state.
  //
  // Canvas and goal load asynchronously, so right after a switch their flags
  // read false simply because the fetch hasn't landed — baselining on that and
  // then seeing the data arrive would look like a rise. Each carries a
  // "resolved" signal (surfacesChatId / goalChatId stamped for the chat we're
  // viewing); a rise only counts if the flag was already resolved for this
  // chat while false.
  const autoOpenRef = useRef({
    chatId: currentChatId,
    file: !!fileToPreview,
    fileToPreview,
    canvas: hasCanvasContent,
    canvasResolved: canvasMatchesChat,
    subAgent: !!viewingSubAgentTaskId,
    viewingSubAgentTaskId,
    webContext: !!forcedWebContextId,
    forcedWebContextId,
    goal: hasGoalContent,
    goalResolved: goalMatchesChat,
  });

  useEffect(() => {
    const prev = autoOpenRef.current;
    const flags: AutoOpenFlags = {
      chatId: currentChatId,
      file: !!fileToPreview,
      fileToPreview,
      canvas: hasCanvasContent,
      canvasResolved: canvasMatchesChat,
      subAgent: !!viewingSubAgentTaskId,
      viewingSubAgentTaskId,
      webContext: !!forcedWebContextId,
      forcedWebContextId,
      goal: hasGoalContent,
      goalResolved: goalMatchesChat,
    };

    const { nextTab, shouldOpen } = evaluateSidebarAutoOpen(prev, flags);
    if (nextTab) {
      setActiveTab(nextTab);
    }
    if (!isOpen && shouldOpen) {
      onOpen();
    }

    autoOpenRef.current = flags;
  }, [
    currentChatId,
    fileToPreview,
    hasCanvasContent,
    canvasMatchesChat,
    viewingSubAgentTaskId,
    forcedWebContextId,
    hasGoalContent,
    goalMatchesChat,
    isOpen,
    onOpen,
  ]);

  // In a new chat only the Tools tab is usable — the rest have no chat context
  // yet, so they can't be selected (avoids opening an empty/collapsed panel).
  const isTabLocked = useCallback((tabId: TabId) => isNewChat && tabId !== 'tools', [isNewChat]);

  // ── Icon strip click: toggle panel or switch tab ───────────────────
  const handleTabClick = useCallback(
    (tabId: TabId) => {
      const targetTab = tabs.find((tab) => tab.id === tabId);
      if (!targetTab) return;
      if (isTabLocked(tabId)) return;
      if (
        targetTab.id !== 'files' &&
        targetTab.id !== 'plan' &&
        targetTab.id !== 'tools' &&
        !targetTab.hasContent
      ) {
        return;
      }

      if (isOpen && activeTab === tabId) {
        onClose();
      } else {
        setActiveTab(tabId);
        if (!isOpen) onOpen();
      }
    },
    [tabs, isOpen, activeTab, onClose, onOpen, isTabLocked]
  );

  useEffect(() => {
    const parent = sidebarRef.current?.parentElement;
    if (!parent) return;
    const measure = (): void => setChatAreaWidth(parent.clientWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(parent);
    return () => observer.disconnect();
  }, []);

  // ── Width calculation ───────────────────────────────────────────────
  const isAutoExpanded =
    (activeTab === 'files' && isFileExpanded) || (activeTab === 'browser' && isBrowserStreamActive);
  const hasCustomWidth = sidebarWidth !== null;
  const shouldUseCustomWidth = hasCustomWidth && !isOverlayMode;

  const getDesktopDefaultWidth = () => {
    if (isBrowserActive || isCanvasActive) {
      return wideContentDefaultWidthPx ?? getCanvasSidebarWidth(effectiveViewportWidth);
    }
    if (isAutoExpanded) return Math.round(effectiveViewportWidth * 0.5);
    return 384;
  };

  const desktopOpenWidth = Math.max(
    MIN_RIGHT_SIDEBAR_WIDTH_PX,
    Math.min(effectiveMaxWidth, shouldUseCustomWidth ? sidebarWidth! : getDesktopDefaultWidth())
  );

  // Desktop: icon strip always visible (44px), content panel expands on open
  // Overlay: full hide/show (icon strip is part of the slide)
  // New chat: in overlay mode hide entirely; in desktop mode show icon strip but only expand for tools tab
  const isNewChatOverlayHidden = isNewChat && isOverlayMode;
  const effectiveOpen = isOpen && (!isNewChat || activeTab === 'tools');
  const isCoveringChat = coveringChat && effectiveOpen && !isOverlayMode;
  const availableCoverWidth = Math.max(
    MIN_RIGHT_SIDEBAR_WIDTH_PX,
    chatAreaWidth || effectiveViewportWidth
  );
  const displayedCoverWidth = Math.min(coverWidth ?? availableCoverWidth, availableCoverWidth);
  const dockSidebar = (width: number = getDesktopDefaultWidth()): void => {
    setCoveringChat(false);
    setCoverWidth(null);
    setSidebarWidth(Math.min(effectiveMaxWidth, width));
  };
  const collapseSidebar = (): void => {
    setCoveringChat(false);
    setCoverWidth(null);
    onClose();
  };
  const desktopWidth = isNewChatOverlayHidden
    ? 0
    : effectiveOpen
      ? desktopOpenWidth
      : ICON_STRIP_WIDTH;

  // ── Report width via ResizeObserver ────────────────────────────────
  useEffect(() => {
    if (!onWidthChange) return;
    const element = sidebarRef.current;
    if (!element) return;

    const reportWidth = () => {
      // While dragging we drive width via direct DOM writes; don't push those
      // intermediate sizes up to App (it would re-render the layout per frame).
      // The final width is reported when setSidebarWidth commits on mouseup.
      if (dragState.current) return;
      const width = isCoveringChat
        ? ICON_STRIP_WIDTH
        : Math.round(element.getBoundingClientRect().width);
      onWidthChange(Number.isFinite(width) && width > 0 ? width : null);
    };

    reportWidth();
    const observer = new ResizeObserver(reportWidth);
    observer.observe(element);
    window.addEventListener('resize', reportWidth);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', reportWidth);
    };
  }, [
    onWidthChange,
    isOpen,
    activeTab,
    isAutoExpanded,
    isCanvasActive,
    sidebarWidth,
    forceFullView,
    isCoveringChat,
  ]);

  return (
    <>
      <div
        ref={spacerRef}
        className="h-full shrink-0"
        style={{ width: isCoveringChat ? ICON_STRIP_WIDTH : 0 }}
        aria-hidden="true"
      />
      <div
        ref={sidebarRef}
        style={
          isNewChatOverlayHidden
            ? { width: 0 }
            : isOverlayMode
              ? { width: ICON_STRIP_WIDTH, maxWidth: ICON_STRIP_WIDTH }
              : isCoveringChat
                ? {
                    width: displayedCoverWidth,
                    maxWidth: availableCoverWidth,
                    position: 'absolute',
                    right: 0,
                    top: 0,
                  }
                : { width: desktopWidth, maxWidth: availableCoverWidth }
        }
        className={`
        z-20 flex flex-row shrink-0 min-h-0 h-full overflow-visible transition-[width] duration-[160ms] ease-out motion-reduce:transition-none
        ${isNewChatOverlayHidden ? 'pointer-events-none' : `bg-white dark:bg-zinc-900 ${!isOverlayMode || isOpen ? 'border-l-3 border-brutal-black' : ''}`}
        relative
      `}
      >
        {/* ── Content Panel ─────────────────────────────────────────── */}
        {/* In overlay mode: slides out absolutely to the right of the icon strip */}
        {/* In desktop mode: sits inline to the left of the icon strip */}
        {isOverlayMode ? (
          <div
            className={`absolute inset-y-0 right-full transform-gpu will-change-transform transition-transform duration-300 ease-in-out border-l-3 border-brutal-black overflow-hidden bg-white dark:bg-zinc-900 ${isOpen ? 'translate-x-0' : 'translate-x-full pointer-events-none'}`}
            style={{
              width: isOpen
                ? isBrowserActive
                  ? Math.max(0, effectiveViewportWidth - ICON_STRIP_WIDTH)
                  : desktopOpenWidth
                : 0,
            }}
          >
            <div className="flex flex-col h-full min-h-0 min-w-0 overflow-hidden">
              <div className="flex-1 overflow-y-auto bg-neutral-50/50 dark:bg-zinc-900 scrollbar-thin scrollbar-track-neutral-200 dark:scrollbar-track-zinc-700 scrollbar-thumb-brutal-black flex flex-col min-h-0">
                <div className={`flex-1 h-full ${activeTab === 'files' ? 'block' : 'hidden'}`}>
                  <SandboxFiles
                    onViewModeChange={setIsFileExpanded}
                    externalFilePath={fileToPreview?.path ?? null}
                    externalFileName={fileToPreview?.name ?? null}
                    externalFileNonce={fileToPreview?.nonce ?? null}
                    onMaximize={onMaximizeFile}
                  />
                </div>
                <div
                  className={`flex-1 h-full flex-col min-h-0 ${activeTab === 'context' ? 'flex' : 'hidden'}`}
                >
                  {currentChatId && <RepositoryContextView chatId={currentChatId} />}
                </div>
                <div
                  className={`flex-1 h-full flex flex-col ${activeTab === 'browser' ? 'flex' : 'hidden'}`}
                >
                  <WebActivitiesView
                    visible={effectiveOpen && activeTab === 'browser'}
                    history={webHistory}
                    isBrowserStreamActive={isBrowserStreamActive}
                    onBrowserStreamActive={setIsBrowserStreamActive}
                    forcedContextId={forcedWebContextId}
                    onClearForcedContext={onClearForcedWebContext}
                  />
                </div>
                <div
                  className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'canvas' ? 'flex' : 'hidden'}`}
                >
                  {canvas && (
                    <CanvasView canvas={canvas} onDispatch={onCanvasDispatch ?? (() => {})} />
                  )}
                </div>
                <div
                  className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'agents' ? 'flex' : 'hidden'}`}
                >
                  {viewingSubAgentTaskId ? (
                    <BackgroundTaskView taskId={viewingSubAgentTaskId} onClose={onCloseSubAgent} />
                  ) : currentChatId ? (
                    <BackgroundTaskList
                      chatId={currentChatId}
                      onSelect={(taskId) => onSelectSubAgent?.(taskId)}
                    />
                  ) : (
                    <div className="flex items-center justify-center h-full text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-400">
                      {t('backgroundTasks.empty')}
                    </div>
                  )}
                </div>

                <div
                  className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'tools' ? 'flex' : 'hidden'}`}
                >
                  <ToolsPanel />
                </div>
              </div>
            </div>
          </div>
        ) : (
          <>
            {!forceFullView && effectiveOpen && (
              <PanelResizeHandle
                panelRef={sidebarRef}
                side="right"
                width={isCoveringChat ? displayedCoverWidth : desktopOpenWidth}
                minWidth={MIN_RIGHT_SIDEBAR_WIDTH_PX}
                maxWidth={isCoveringChat ? availableCoverWidth : effectiveMaxWidth}
                defaultWidth={getDesktopDefaultWidth()}
                onWidthChange={isCoveringChat ? setCoverWidth : setSidebarWidth}
                onCollapse={collapseSidebar}
                onCover={() => {
                  setCoverWidth(null);
                  setCoveringChat(true);
                }}
                onDock={dockSidebar}
                dockMaxWidth={effectiveMaxWidth}
                coverWidth={availableCoverWidth}
                initiallyCovering={isCoveringChat}
                spacerRef={spacerRef}
                dockThreshold={Math.max(MIN_RIGHT_SIDEBAR_WIDTH_PX, effectiveMaxWidth - 48)}
                onReset={() => dockSidebar()}
                hint={t(isCoveringChat ? 'sidebar.resizeCoverHint' : 'sidebar.resizeRightHint')}
                onDraggingChange={(dragging) => {
                  dragState.current = dragging;
                }}
              />
            )}
            <div
              className={`flex flex-col min-h-0 min-w-0 flex-1 overflow-hidden transform-gpu will-change-transform transition-[opacity,transform] duration-200 ease-out ${effectiveOpen ? 'opacity-100 translate-x-0 border-r-3 border-brutal-black' : 'opacity-0 translate-x-3 pointer-events-none'}`}
            >
              <div className="flex-1 overflow-y-auto bg-neutral-50/50 dark:bg-zinc-900 scrollbar-thin scrollbar-track-neutral-200 dark:scrollbar-track-zinc-700 scrollbar-thumb-brutal-black flex flex-col min-h-0">
                <div className={`flex-1 h-full ${activeTab === 'files' ? 'block' : 'hidden'}`}>
                  <SandboxFiles
                    onViewModeChange={setIsFileExpanded}
                    externalFilePath={fileToPreview?.path ?? null}
                    externalFileName={fileToPreview?.name ?? null}
                    externalFileNonce={fileToPreview?.nonce ?? null}
                    onMaximize={onMaximizeFile}
                  />
                </div>
                <div
                  className={`flex-1 h-full flex-col min-h-0 ${activeTab === 'context' ? 'flex' : 'hidden'}`}
                >
                  {currentChatId && <RepositoryContextView chatId={currentChatId} />}
                </div>
                <div
                  className={`flex-1 h-full flex flex-col ${activeTab === 'browser' ? 'flex' : 'hidden'}`}
                >
                  <WebActivitiesView
                    visible={effectiveOpen && activeTab === 'browser'}
                    history={webHistory}
                    isBrowserStreamActive={isBrowserStreamActive}
                    onBrowserStreamActive={setIsBrowserStreamActive}
                    forcedContextId={forcedWebContextId}
                    onClearForcedContext={onClearForcedWebContext}
                  />
                </div>
                <div
                  className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'canvas' ? 'flex' : 'hidden'}`}
                >
                  {canvas && (
                    <CanvasView canvas={canvas} onDispatch={onCanvasDispatch ?? (() => {})} />
                  )}
                </div>
                <div
                  className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'agents' ? 'flex' : 'hidden'}`}
                >
                  {viewingSubAgentTaskId ? (
                    <BackgroundTaskView taskId={viewingSubAgentTaskId} onClose={onCloseSubAgent} />
                  ) : currentChatId ? (
                    <BackgroundTaskList
                      chatId={currentChatId}
                      onSelect={(taskId) => onSelectSubAgent?.(taskId)}
                    />
                  ) : (
                    <div className="flex items-center justify-center h-full text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-400">
                      {t('backgroundTasks.empty')}
                    </div>
                  )}
                </div>

                <div
                  className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'tools' ? 'flex' : 'hidden'}`}
                >
                  <ToolsPanel />
                </div>
              </div>
            </div>
          </>
        )}

        <div
          className={`absolute inset-y-0 z-10 overflow-hidden border-r-3 border-brutal-black bg-white dark:bg-zinc-900 ${effectiveOpen && activeTab === 'plan' ? '' : 'hidden'}`}
          style={
            isOverlayMode
              ? { right: '100%', width: Math.max(0, effectiveViewportWidth - ICON_STRIP_WIDTH) }
              : { left: 0, right: ICON_STRIP_WIDTH }
          }
        >
          <TaskPanel
            navigationError={taskNavigationError}
            onDismissError={onDismissTaskError}
            goal={goalMatchesChat ? goal : null}
            tasks={goalMatchesChat ? tasks : []}
            kanban={kanban}
            projectName={currentProjectName}
            chatTitles={chatTitles}

            onOpenTask={async (task) => {
              const opened = (await onOpenTask?.(task)) ?? false;
              if (opened) {
                if (isCoveringChat) dockSidebar(sidebarWidth ?? getDesktopDefaultWidth());
                if (isOverlayMode) onClose();
              }
              return opened;
            }}
            onOpenChat={async (chatId) => {
              const opened = await onTaskChat?.(chatId);
              if (opened) {
                if (isCoveringChat) dockSidebar(sidebarWidth ?? getDesktopDefaultWidth());
                if (isOverlayMode) onClose();
              }
            }}
          />
        </div>

        {/* ── Icon Strip — always visible (except new chat) ─────────── */}
        <div className="flex flex-col items-center bg-white dark:bg-zinc-800 shrink-0 w-11 py-1 gap-0.5">
          {isCoveringChat && activeTab !== 'plan' && (
            <button
              type="button"
              onClick={() => dockSidebar()}
              title={t('sidebar.dock')}
              aria-label={t('sidebar.dock')}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded text-brutal-black hover:bg-neutral-100 dark:text-white dark:hover:bg-zinc-700"
            >
              <ChevronDoubleRightIcon className="h-5 w-5" />
            </button>
          )}
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const locked = isTabLocked(tab.id);
            const isActive = isOpen && activeTab === tab.id && !locked;
            const isIdle = !tab.hasContent;
            const isDisabled = locked || (tab.id !== 'files' && !tab.hasContent);

            return (
              <button
                key={tab.id}
                disabled={isDisabled}
                onClick={() => handleTabClick(tab.id)}
                title={t(tab.labelKey) || tab.fallbackLabel}
                aria-disabled={isDisabled}
                className={`
                relative flex items-center justify-center w-9 h-9 rounded transition-colors
                ${
                  isActive
                    ? 'bg-brutal-black text-white'
                    : isDisabled
                      ? 'text-neutral-300 dark:text-zinc-600 cursor-default'
                      : isIdle
                        ? 'text-neutral-300 dark:text-zinc-600 hover:text-neutral-500 dark:hover:text-zinc-400 hover:bg-neutral-100 dark:hover:bg-zinc-700'
                        : 'text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-700'
                }
              `}
              >
                <Icon className="w-5 h-5" />
                {/* Activity dot — shown when content exists and panel not active */}
                {tab.hasActivity && !isActive && (
                  <span
                    className={`absolute top-1 right-1 w-2 h-2 border border-brutal-black rounded-full ${tab.activityClass ?? 'bg-brutal-yellow'}`}
                  />
                )}
              </button>
            );
          })}
        </div>
      </div>
    </>
  );
};
