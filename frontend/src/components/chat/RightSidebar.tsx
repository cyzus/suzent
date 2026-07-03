import React, { useMemo, useState, useEffect, useRef, useCallback } from 'react';
import { useI18n } from '../../i18n';
import { GoalTaskView } from '../sidebar/GoalTaskView';
import { SandboxFiles } from '../sidebar/SandboxFiles';
import { WebActivitiesView } from '../sidebar/WebActivitiesView';
import { CanvasView } from '../sidebar/CanvasView';
import { SubAgentView } from '../sidebar/SubAgentView';
import { SubAgentList } from '../sidebar/SubAgentList';
import type { Message, Goal, Task } from '../../types/api';
import type { KanbanData } from '../../hooks/useGoalTasks';
import type { CanvasState } from '../../hooks/useCanvas';
import { useWebHistory } from '../../hooks/useWebHistory';
import {
  DESKTOP_BREAKPOINT_PX,
  MIN_RIGHT_SIDEBAR_WIDTH_PX,
  MAX_RIGHT_SIDEBAR_WIDTH_PX,
} from '../../lib/layout';
import {
  FolderIcon,
  GlobeAltIcon,
  PencilSquareIcon,
  CpuChipIcon,
  ClipboardDocumentListIcon,
  WrenchScrewdriverIcon,
} from '@heroicons/react/24/outline';
import { ToolsPanel } from './ToolsPanel';

// Icon strip width in px — keep in sync with w-11 (2.75rem = 44px)
const ICON_STRIP_WIDTH = 44;

type TabId = 'files' | 'browser' | 'canvas' | 'agents' | 'plan' | 'project' | 'tools';

interface RightSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onOpen: () => void;
  onWidthChange?: (width: number | null) => void;
  maxWidthPx?: number;
  canvasMaxWidthPx?: number;
  viewportWidthPx?: number;
  forceFullView?: boolean;
  goal: Goal | null;
  tasks: Task[];
  kanban: KanbanData | null;
  currentProjectName?: string | null;
  currentProjectId?: string | null;
  chatTitles?: Record<string, string>;
  onProjectBoardChange?: (open: boolean) => void;
  fileToPreview?: { path: string; name: string; nonce?: number } | null;
  onMaximizeFile?: (filePath: string, fileName: string) => void;
  canvas?: CanvasState;
  onCanvasDispatch?: (action: string, context: Record<string, unknown>, surfaceId: string) => void;
  viewingSubAgentTaskId?: string | null;
  onCloseSubAgent?: () => void;
  onSelectSubAgent?: (taskId: string) => void;
  currentChatId?: string | null;
  hasSubAgents?: boolean;
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
  canvasMaxWidthPx,
  viewportWidthPx,
  forceFullView = false,
  goal,
  tasks,
  kanban,
  currentProjectName,
  currentProjectId,
  chatTitles = {},
  onProjectBoardChange,
  fileToPreview,
  onMaximizeFile,
  canvas,
  onCanvasDispatch,
  viewingSubAgentTaskId,
  onCloseSubAgent,
  onSelectSubAgent,
  currentChatId,
  hasSubAgents = false,
  messages = [],
  forcedWebContextId,
  onClearForcedWebContext,
  isNewChat = false,
}) => {
  useI18n();
  const [activeTab, setActiveTab] = useState<TabId>('browser');
  const [isFileExpanded, setIsFileExpanded] = useState(false);
  const [isBrowserStreamActive, setIsBrowserStreamActive] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState<number | null>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);
  const dragState = useRef<{ startX: number; startWidth: number } | null>(null);

  const effectiveViewportWidth = viewportWidthPx ?? window.innerWidth;
  const isDesktop = effectiveViewportWidth >= DESKTOP_BREAKPOINT_PX;
  const isOverlayMode = forceFullView || !isDesktop;

  // Canvas gets a wider, ratio-based ceiling than other tabs (it holds wide
  // content). App passes canvasMaxWidthPx (viewport-derived, chat-width-safe);
  // other tabs keep the standard maxWidthPx.
  const isCanvasActive = activeTab === 'canvas' && !!canvas?.hasSurfaces;
  const activeMax = isCanvasActive
    ? (canvasMaxWidthPx ?? maxWidthPx ?? MAX_RIGHT_SIDEBAR_WIDTH_PX)
    : (maxWidthPx ?? MAX_RIGHT_SIDEBAR_WIDTH_PX);
  const effectiveMaxWidth = Math.max(MIN_RIGHT_SIDEBAR_WIDTH_PX, activeMax);

  const shouldBuildWebHistory = isOpen || isBrowserStreamActive || Boolean(forcedWebContextId);
  const webHistoryMessages = useMemo(
    () => shouldBuildWebHistory ? messages : [],
    [messages, shouldBuildWebHistory],
  );
  const webHistory = useWebHistory(webHistoryMessages);
  const hasWebActivity = webHistory.length > 0 || (!shouldBuildWebHistory && messages.some(
    message => message.role === 'assistant' && typeof message.content === 'string' && (
      message.content.includes('web_search') || message.content.includes('webpage_fetch')
    ),
  ));
  const hasGoalContent = Boolean(goal !== null || tasks.length > 0);

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
      hasContent: !!canvas?.hasSurfaces,
      hasActivity: !!canvas?.hasSurfaces,
      activityClass: 'bg-brutal-yellow',
    },
    {
      id: 'agents',
      icon: CpuChipIcon,
      labelKey: 'sidebar.tabs.agents',
      fallbackLabel: 'Agents',
      hasContent: hasSubAgents || !!viewingSubAgentTaskId,
      hasActivity: hasSubAgents || !!viewingSubAgentTaskId,
      activityClass: 'bg-brutal-blue animate-pulse',
    },
    {
      id: 'plan',
      icon: ClipboardDocumentListIcon,
      labelKey: 'sidebar.tabs.plan',
      fallbackLabel: 'Goal',
      hasContent: true,  // always accessible — shows empty state + board button
      hasActivity: hasGoalContent,
      activityClass: 'bg-brutal-yellow',
    },
    {
      id: 'tools',
      icon: WrenchScrewdriverIcon,
      labelKey: 'sidebar.tabs.tools',
      fallbackLabel: 'Tools',
      hasContent: true,  // always accessible
      hasActivity: false,
    },
  ];

  // ── Auto-switch tab when content arrives ───────────────────────────
  useEffect(() => {
    if (fileToPreview) setActiveTab('files');
  }, [fileToPreview]);

  useEffect(() => {
    if (canvas?.hasSurfaces) setActiveTab('canvas');
  }, [canvas?.hasSurfaces]);

  useEffect(() => {
    if (viewingSubAgentTaskId) setActiveTab('agents');
  }, [viewingSubAgentTaskId]);

  useEffect(() => {
    if (hasGoalContent) setActiveTab('plan');
  }, [hasGoalContent]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Open sidebar automatically when content arrives ─────────────────
  // Auto-open only when content transitions absent → present *while staying in
  // the same chat*. Switching chats (currentChatId changes) resets the baseline
  // so an existing chat's data — which loads async after the switch — is treated
  // as pre-existing and does NOT pop the sidebar open. Content that arrives while
  // you remain in the chat still auto-opens.
  const autoOpenRef = useRef({
    chatId: currentChatId,
    file: false,
    canvas: false,
    subAgent: false,
    goal: false,
  });
  // A chat's goal/canvas data loads async *after* currentChatId changes, so we
  // stay in an "adopting" window for a short settle after each switch: any
  // content that appears during it is treated as the chat's pre-existing state
  // (baseline updated, no auto-open). New content after that opens the sidebar.
  const adoptingUntilRef = useRef(0);

  useEffect(() => {
    const prev = autoOpenRef.current;
    if (prev.chatId !== currentChatId) {
      // Chat switched: reset baseline and start the adopt window.
      autoOpenRef.current = {
        chatId: currentChatId,
        file: !!fileToPreview,
        canvas: !!canvas?.hasSurfaces,
        subAgent: !!viewingSubAgentTaskId,
        goal: hasGoalContent,
      };
      adoptingUntilRef.current = Date.now() + 800;
      return;
    }

    const flags = {
      chatId: currentChatId,
      file: !!fileToPreview,
      canvas: !!canvas?.hasSurfaces,
      subAgent: !!viewingSubAgentTaskId,
      goal: hasGoalContent,
    };
    const adopting = Date.now() < adoptingUntilRef.current;

    if (!adopting && !isOpen) {
      const rose =
        (!prev.file && flags.file) ||
        (!prev.canvas && flags.canvas) ||
        (!prev.subAgent && flags.subAgent) ||
        (!prev.goal && flags.goal);
      if (rose) onOpen();
    }

    autoOpenRef.current = flags;
  }, [currentChatId, fileToPreview, canvas?.hasSurfaces, viewingSubAgentTaskId, hasGoalContent, isOpen, onOpen]);


  // In a new chat only the Tools tab is usable — the rest have no chat context
  // yet, so they can't be selected (avoids opening an empty/collapsed panel).
  const isTabLocked = useCallback(
    (tabId: TabId) => isNewChat && tabId !== 'tools',
    [isNewChat],
  );

  // ── Icon strip click: toggle panel or switch tab ───────────────────
  const handleTabClick = useCallback((tabId: TabId) => {
    const targetTab = tabs.find(tab => tab.id === tabId);
    if (!targetTab) return;
    if (isTabLocked(tabId)) return;
    if (targetTab.id !== 'files' && targetTab.id !== 'plan' && targetTab.id !== 'tools' && !targetTab.hasContent) {
      return;
    }

    if (isOpen && activeTab === tabId) {
      onClose();
    } else {
      setActiveTab(tabId);
      if (!isOpen) onOpen();
    }
  }, [tabs, isOpen, activeTab, onClose, onOpen, isTabLocked]);

  // ── Resize ─────────────────────────────────────────────────────────
  // During the drag we write the width straight to the DOM (no React state, so
  // the heavy canvas/content subtree never re-renders per mouse move) and
  // coalesce moves into a single rAF write. React state is committed only once
  // on mouseup — that's the sole re-render the resize triggers.
  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    if (forceFullView) return;
    e.preventDefault();
    const element = sidebarRef.current;
    if (!element) return;

    const startWidth = element.getBoundingClientRect().width;
    dragState.current = { startX: e.clientX, startWidth };
    let latestWidth = startWidth;
    let rafId = 0;

    // Freeze children from reflowing mid-drag work; keeps the paint cheap.
    const prevUserSelect = document.body.style.userSelect;
    document.body.style.userSelect = 'none';

    const applyWidth = () => {
      rafId = 0;
      element.style.width = `${latestWidth}px`;
    };

    const onMouseMove = (ev: MouseEvent) => {
      if (!dragState.current) return;
      const delta = dragState.current.startX - ev.clientX;
      latestWidth = Math.max(
        MIN_RIGHT_SIDEBAR_WIDTH_PX,
        Math.min(effectiveMaxWidth, dragState.current.startWidth + delta),
      );
      if (!rafId) rafId = requestAnimationFrame(applyWidth);
    };

    const onMouseUp = () => {
      dragState.current = null;
      if (rafId) cancelAnimationFrame(rafId);
      document.body.style.userSelect = prevUserSelect;
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      // Commit the final width to React state (single re-render).
      setSidebarWidth(latestWidth);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }, [effectiveMaxWidth, forceFullView]);

  useEffect(() => {
    if (sidebarWidth === null || forceFullView) return;
    const clamped = Math.max(MIN_RIGHT_SIDEBAR_WIDTH_PX, Math.min(effectiveMaxWidth, sidebarWidth));
    if (clamped !== sidebarWidth) setSidebarWidth(clamped);
  }, [sidebarWidth, effectiveMaxWidth, forceFullView]);

  useEffect(() => {
    if (forceFullView && sidebarWidth !== null) setSidebarWidth(null);
  }, [forceFullView, sidebarWidth]);

  // ── Width calculation ───────────────────────────────────────────────
  const isAutoExpanded = (activeTab === 'files' && isFileExpanded) || (activeTab === 'browser' && isBrowserStreamActive);
  const hasCustomWidth = sidebarWidth !== null;
  const shouldUseCustomWidth = hasCustomWidth && !isOverlayMode;

  const getDesktopDefaultWidth = () => {
    if (isAutoExpanded) return Math.round(effectiveViewportWidth * 0.5);
    // Canvas often holds wide content (tables, forms) — give it as much room as
    // the layout allows (clamped to effectiveMaxWidth below). Drag to narrow.
    if (isCanvasActive) return effectiveMaxWidth;
    return 384;
  };

  const desktopOpenWidth = Math.max(
    MIN_RIGHT_SIDEBAR_WIDTH_PX,
    Math.min(effectiveMaxWidth, shouldUseCustomWidth ? sidebarWidth! : getDesktopDefaultWidth()),
  );

  // Desktop: icon strip always visible (44px), content panel expands on open
  // Overlay: full hide/show (icon strip is part of the slide)
  // New chat: in overlay mode hide entirely; in desktop mode show icon strip but only expand for tools tab
  const isNewChatOverlayHidden = isNewChat && isOverlayMode;
  const effectiveOpen = isOpen && (!isNewChat || activeTab === 'tools');
  const desktopWidth = isNewChatOverlayHidden ? 0 : effectiveOpen ? desktopOpenWidth : ICON_STRIP_WIDTH;

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
      const width = Math.round(element.getBoundingClientRect().width);
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
  }, [onWidthChange, isOpen, activeTab, isAutoExpanded, isCanvasActive, sidebarWidth, forceFullView]);

  return (
    <div
      ref={sidebarRef}
      style={isNewChatOverlayHidden
        ? { width: 0 }
        : isOverlayMode
          ? { width: ICON_STRIP_WIDTH, maxWidth: ICON_STRIP_WIDTH }
          : { width: desktopWidth, maxWidth: effectiveMaxWidth }}
      className={`
        z-20 flex flex-row shrink-0 min-h-0 h-full overflow-visible
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
          style={{ width: isOpen ? desktopOpenWidth : 0 }}
        >
          {!forceFullView && isOpen && (
            <div
              onMouseDown={handleResizeStart}
              className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize z-50 hover:bg-brutal-black/20 active:bg-brutal-black/30 transition-colors"
              title="Drag to resize"
            />
          )}
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
              <div className={`flex-1 h-full flex flex-col ${activeTab === 'browser' ? 'flex' : 'hidden'}`}>
                <WebActivitiesView
                  history={webHistory}
                  isBrowserStreamActive={isBrowserStreamActive}
                  onBrowserStreamActive={setIsBrowserStreamActive}
                  forcedContextId={forcedWebContextId}
                  onClearForcedContext={onClearForcedWebContext}
                />
              </div>
              <div className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'canvas' ? 'flex' : 'hidden'}`}>
                {canvas && <CanvasView canvas={canvas} onDispatch={onCanvasDispatch ?? (() => {})} />}
              </div>
              <div className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'agents' ? 'flex' : 'hidden'}`}>
                {viewingSubAgentTaskId ? (
                  <SubAgentView taskId={viewingSubAgentTaskId} onClose={onCloseSubAgent} />
                ) : currentChatId ? (
                  <SubAgentList chatId={currentChatId} onSelect={(taskId) => onSelectSubAgent?.(taskId)} />
                ) : (
                  <div className="flex items-center justify-center h-full text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-400">No sub-agent selected</div>
                )}
              </div>
              <div className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'plan' ? 'flex' : 'hidden'}`}>
                <GoalTaskView
                  goal={goal}
                  tasks={tasks}
                  onOpenBoard={onProjectBoardChange ? () => onProjectBoardChange(true) : undefined}
                  projectTaskCount={kanban?.tasks.length}
                />
              </div>
              <div className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'tools' ? 'flex' : 'hidden'}`}>
                <ToolsPanel />
              </div>
            </div>
          </div>
        </div>
      ) : (
        <>
          {!forceFullView && effectiveOpen && (
            <div
              onMouseDown={handleResizeStart}
              className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize z-50 hover:bg-brutal-black/20 active:bg-brutal-black/30 transition-colors hidden lg:block"
              title="Drag to resize"
            />
          )}
          <div className={`flex flex-col min-h-0 min-w-0 flex-1 overflow-hidden transform-gpu will-change-transform transition-[opacity,transform] duration-200 ease-out ${effectiveOpen ? 'opacity-100 translate-x-0 border-r-3 border-brutal-black' : 'opacity-0 translate-x-3 pointer-events-none'}`}>
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
              <div className={`flex-1 h-full flex flex-col ${activeTab === 'browser' ? 'flex' : 'hidden'}`}>
                <WebActivitiesView
                  history={webHistory}
                  isBrowserStreamActive={isBrowserStreamActive}
                  onBrowserStreamActive={setIsBrowserStreamActive}
                  forcedContextId={forcedWebContextId}
                  onClearForcedContext={onClearForcedWebContext}
                />
              </div>
              <div className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'canvas' ? 'flex' : 'hidden'}`}>
                {canvas && <CanvasView canvas={canvas} onDispatch={onCanvasDispatch ?? (() => {})} />}
              </div>
              <div className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'agents' ? 'flex' : 'hidden'}`}>
                {viewingSubAgentTaskId ? (
                  <SubAgentView taskId={viewingSubAgentTaskId} onClose={onCloseSubAgent} />
                ) : currentChatId ? (
                  <SubAgentList chatId={currentChatId} onSelect={(taskId) => onSelectSubAgent?.(taskId)} />
                ) : (
                  <div className="flex items-center justify-center h-full text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-400">No sub-agent selected</div>
                )}
              </div>
              <div className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'plan' ? 'flex' : 'hidden'}`}>
                <GoalTaskView
                  goal={goal}
                  tasks={tasks}
                  onOpenBoard={onProjectBoardChange ? () => onProjectBoardChange(true) : undefined}
                  projectTaskCount={kanban?.tasks.length}
                />
              </div>
              <div className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'tools' ? 'flex' : 'hidden'}`}>
                <ToolsPanel />
              </div>
            </div>
          </div>
        </>
      )}

      {/* ── Icon Strip — always visible (except new chat) ─────────── */}
      <div className="flex flex-col items-center bg-white dark:bg-zinc-800 shrink-0 w-11 py-1 gap-0.5">
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
              title={tab.fallbackLabel}
              aria-disabled={isDisabled}
              className={`
                relative flex items-center justify-center w-9 h-9 rounded transition-colors
                ${isActive
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
                <span className={`absolute top-1 right-1 w-2 h-2 border border-brutal-black rounded-full ${tab.activityClass ?? 'bg-brutal-yellow'}`} />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};
