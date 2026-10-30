import { SidebarExpansionContext } from '../sidebar/SidebarExpansionContext';
import React, { useMemo, useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n';
import { FOCAL_CHAT_ID, readFocalBoardOpen } from '../../lib/focalAgent';
import { markOpenedFromRegent, unmarkOpenedFromRegent } from '../../lib/regentReturn';
import { TaskPanel } from '../sidebar/TaskPanel';
import { SandboxFiles } from '../sidebar/SandboxFiles';
import { WebActivitiesView } from '../sidebar/WebActivitiesView';
import { CanvasView } from '../sidebar/CanvasView';
import { useSurfaceEntry } from '../a2ui/InlineSurfaceContext';
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
  Squares2X2Icon,
  ServerStackIcon,
  EllipsisHorizontalIcon,
} from '@heroicons/react/24/outline';
import { PanelResizeHandle } from '../PanelResizeHandle';
import { ToolsPanel } from './ToolsPanel';
import { FocalToolsPanel } from './FocalToolsPanel';
import {
  HeaderMoreMenu,
  OverviewBackBar,
  OverviewList,
  PlanProgress,
  SidebarOverview,
  type OverviewSection,
} from './SidebarOverview';
import { ContextUsageSummary } from '../sidebar/ContextUsageSummary';
import {
  ContextHeaderButton,
  ContextUsageHeadline,
  ContextWindowStats,
} from '../sidebar/ContextWindowStats';
import {
  EnvironmentPreview,
  EnvironmentProjectName,
  EnvironmentSummary,
} from '../sidebar/EnvironmentSummary';
import { useContextUsageStats } from '../../hooks/useContextUsageStats';
import {
  RegentBoardCounts,
  RegentBoardList,
  RegentWaitingCount,
} from '../sidebar/RegentBoardSummary';
import { formatPercent } from '../../lib/contextFormat';
import { isSubAgentActive } from './subAgentStatus';

export type TabId =
  | 'overview'
  | 'files'
  | 'context'
  | 'browser'
  | 'canvas'
  | 'agents'
  | 'plan'
  | 'project'
  | 'environment'
  | 'tools';

export interface AutoOpenFlags {
  chatId: string | null | undefined;
  file: boolean;
  fileToPreview: { path: string; name: string; nonce?: number } | null | undefined;
  canvas: boolean;
  canvasResolved: boolean;
  activeTab?: TabId;
  canvasSurfaceId?: string;
  canvasLocation?: 'inline' | 'canvas';
  subAgent: boolean;
  viewingSubAgentTaskId: string | null | undefined;
  webContext: boolean;
  forcedWebContextId: string | null | undefined;
  /** Bumped when the user pops a chat surface out to the side panel. */
  canvasRequestNonce?: number;
  goal: boolean;
  goalResolved: boolean;
  /** On the Focal Agent chat with room for its board: how the user last left it. */
  focalBoard?: 'open' | 'closed';
}

export function evaluateSidebarAutoOpen(
  prev: AutoOpenFlags,
  flags: AutoOpenFlags
): { nextTab: TabId | null; shouldOpen: boolean; shouldClose?: boolean } {
  if (prev.chatId !== flags.chatId) {
    if (flags.focalBoard === 'open') return { nextTab: 'plan', shouldOpen: true };
    if (flags.focalBoard === 'closed')
      return { nextTab: null, shouldOpen: false, shouldClose: true };
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
  const canvasRequested =
    !!flags.canvasRequestNonce && prev.canvasRequestNonce !== flags.canvasRequestNonce;
  const goalRose = prev.goalResolved && flags.goalResolved && !prev.goal && flags.goal;

  let nextTab: TabId | null = null;
  if (fileTriggered) {
    nextTab = 'files';
  } else if (subAgentTriggered) {
    nextTab = 'agents';
  } else if (webContextTriggered) {
    nextTab = 'browser';
  } else if (canvasRequested) {
    nextTab = 'canvas';
  } else if (canvasRose && !flags.file) {
    nextTab = 'canvas';
  } else if (goalRose && !flags.file) {
    // Async task refreshes must not hide an explicitly requested output file.
    nextTab = 'plan';
  }

  const returnedToChat =
    flags.activeTab === 'canvas' &&
    flags.canvasResolved &&
    !!flags.canvasSurfaceId &&
    prev.canvasSurfaceId === flags.canvasSurfaceId &&
    prev.canvasLocation === 'canvas' &&
    flags.canvasLocation === 'inline';

  return {
    nextTab,
    ...(returnedToChat && !nextTab ? { shouldClose: true } : {}),
    shouldOpen:
      fileTriggered ||
      subAgentTriggered ||
      webContextTriggered ||
      canvasRequested ||
      canvasRose ||
      goalRose,
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
  onMaximizeFile?: (filePath: string, fileName: string, anchor?: DOMRect) => void;
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
  canvasRequestNonce?: number;
  canvasExpandNonce?: number;
  onClearForcedWebContext?: () => void;
  isNewChat?: boolean;
  /** App header node the tab buttons are portalled into. */
  headerSlot?: HTMLElement | null;
}

interface TabConfig {
  id: TabId;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  labelKey: string;
  fallbackLabel: string;
  hasContent: boolean;
  hasActivity: boolean;
  activityClass?: string;
  /** Gets its own header button; the rest are reached from the overview. */
  pinned: boolean;
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
  canvasRequestNonce,
  canvasExpandNonce,
  onClearForcedWebContext,
  isNewChat = false,
  headerSlot,
}) => {
  const { t } = useI18n();
  const { taskStates } = useBackgroundTasks();
  const backgroundTasks = Object.values(taskStates).filter(
    (task) => task.parent_chat_id === currentChatId
  );
  const hasBackgroundActivity = backgroundTasks.some(
    (task) => task.status === 'running' || task.status === 'queued'
  );
  const [activeTab, setActiveTab] = useState<TabId>(currentChatId ? 'overview' : 'tools');
  const selectedTabByChat = useRef<Map<string, TabId>>(new Map());
  const previousChatId = useRef(currentChatId);
  useEffect(() => {
    if (previousChatId.current !== currentChatId) {
      if (previousChatId.current) {
        selectedTabByChat.current.set(previousChatId.current, activeTab);
      }
      previousChatId.current = currentChatId;
      setActiveTab(
        currentChatId ? (selectedTabByChat.current.get(currentChatId) ?? 'overview') : 'tools'
      );
    } else if (currentChatId) {
      selectedTabByChat.current.set(currentChatId, activeTab);
    }
  }, [activeTab, currentChatId]);
  const [expandedSections, setExpandedSections] = useState<ReadonlySet<TabId>>(
    () => new Set<TabId>(['plan', 'agents'])
  );
  const [isFileExpanded, setIsFileExpanded] = useState(false);
  const [isBrowserStreamActive, setIsBrowserStreamActive] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState<number | null>(null);
  const [coveringChat, setCoveringChat] = useState(false);
  const previousCanvasExpand = useRef(canvasExpandNonce);
  useEffect(() => {
    if (canvasExpandNonce !== previousCanvasExpand.current) {
      previousCanvasExpand.current = canvasExpandNonce;
      setCoverWidth(null);
      setCoveringChat(true);
    }
  }, [canvasExpandNonce]);

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
  const canvasSurfaceId = canvasMatchesChat
    ? (
        canvas?.surfaces.find((surface) => surface.id === canvas.activeSurfaceId) ??
        canvas?.surfaces[0]
      )?.id
    : undefined;
  const canvasLocation = useSurfaceEntry(canvasSurfaceId ?? '')?.location;

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
  // Agents open on history too: the panel fetches its own list from /subagents,
  // so a reopened chat can show every past run. The dot stays tied to live
  // state -- a finished history is not activity.
  const hasAgentContent =
    backgroundTasks.length > 0 || hasSubAgents || hasSubAgentHistory || !!viewingSubAgentTaskId;
  const isFocal = currentChatId === FOCAL_CHAT_ID;
  const tabs: TabConfig[] = [
    {
      id: 'overview',
      icon: Squares2X2Icon,
      labelKey: 'sidebar.tabs.overview',
      fallbackLabel: 'Overview',
      hasContent: Boolean(currentChatId),
      hasActivity: hasBackgroundActivity,
      activityClass: 'bg-brutal-blue animate-pulse',
      pinned: true,
    },
    {
      id: 'files',
      icon: FolderIcon,
      labelKey: 'sidebar.tabs.files',
      fallbackLabel: 'Files',
      hasContent: true,
      hasActivity: !!fileToPreview,
      activityClass: 'bg-brutal-yellow',
      pinned: true,
    },
    {
      id: 'browser',
      icon: GlobeAltIcon,
      labelKey: 'sidebar.tabs.browser',
      fallbackLabel: 'Web',
      hasContent: Boolean(currentChatId),
      hasActivity: isBrowserStreamActive || hasWebActivity,
      activityClass: 'bg-brutal-green',
      pinned: true,
    },
    {
      id: 'plan',
      icon: ClipboardDocumentListIcon,
      labelKey: 'sidebar.tabs.plan',
      fallbackLabel: 'Tasks',
      hasContent: true,
      hasActivity: hasGoalContent,
      activityClass: 'bg-brutal-yellow',
      // Regent's board spans every project, so it gets its own header button.
      pinned: isFocal,
    },
    {
      id: 'canvas',
      icon: PencilSquareIcon,
      labelKey: 'sidebar.tabs.canvas',
      fallbackLabel: 'Canvas',
      hasContent: hasCanvasContent,
      hasActivity: hasCanvasContent,
      activityClass: 'bg-brutal-yellow',
      pinned: hasCanvasContent,
    },
    {
      id: 'agents',
      icon: CpuChipIcon,
      labelKey: 'sidebar.tabs.agents',
      fallbackLabel: 'Background tasks',
      hasContent: hasAgentContent,
      hasActivity: hasBackgroundActivity,
      activityClass: 'bg-brutal-blue animate-pulse',
      pinned: false,
    },
    {
      id: 'context',
      icon: DocumentTextIcon,
      labelKey: 'sidebar.tabs.context',
      fallbackLabel: 'Context',
      hasContent: Boolean(currentChatId),
      hasActivity: false,
      pinned: false,
    },
    {
      id: 'environment',
      icon: ServerStackIcon,
      labelKey: 'sidebar.tabs.environment',
      fallbackLabel: 'Environment',
      hasContent: Boolean(currentChatId),
      hasActivity: false,
      pinned: false,
    },
    {
      id: 'tools',
      icon: WrenchScrewdriverIcon,
      labelKey: 'sidebar.tabs.tools',
      fallbackLabel: 'Tools',
      hasContent: true,
      hasActivity: false,
      pinned: true,
    },
  ];

  // ── Auto-switch tab & open sidebar when content arrives ────────────
  // Only auto-switch or auto-open when content transitions absent → present
  // *within the same chat*. On a chat switch we re-baseline without popping
  // the sidebar; the selected tab is restored separately for that chat.
  //
  // Canvas and goal load asynchronously, so right after a switch their flags
  // read false simply because the fetch hasn't landed — baselining on that and
  // then seeing the data arrive would look like a rise. Each carries a
  // "resolved" signal (surfacesChatId / goalChatId stamped for the chat we're
  // viewing); a rise only counts if the flag was already resolved for this
  // chat while false.
  const autoOpenRef = useRef<AutoOpenFlags>({
    chatId: currentChatId,
    file: !!fileToPreview,
    fileToPreview,
    canvas: hasCanvasContent,
    canvasResolved: canvasMatchesChat,
    activeTab,
    canvasSurfaceId,
    canvasLocation,
    subAgent: !!viewingSubAgentTaskId,
    viewingSubAgentTaskId,
    webContext: !!forcedWebContextId,
    forcedWebContextId,
    canvasRequestNonce,
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
      activeTab,
      canvasSurfaceId,
      canvasLocation,
      subAgent: !!viewingSubAgentTaskId,
      viewingSubAgentTaskId,
      webContext: !!forcedWebContextId,
      forcedWebContextId,
      canvasRequestNonce,
      goal: hasGoalContent,
      goalResolved: goalMatchesChat,
      focalBoard:
        currentChatId === FOCAL_CHAT_ID &&
        (viewportWidthPx ?? window.innerWidth) >= DESKTOP_BREAKPOINT_PX
          ? readFocalBoardOpen()
            ? 'open'
            : 'closed'
          : undefined,
    };

    const { nextTab, shouldOpen, shouldClose } = evaluateSidebarAutoOpen(prev, flags);
    // Regent's board needs the full panel; any other plan is status, so it unfolds in place.
    if (nextTab === 'plan' && currentChatId !== FOCAL_CHAT_ID) {
      setActiveTab('overview');
      setExpandedSections((current) => new Set(current).add('plan'));
    } else if (nextTab) {
      setActiveTab(nextTab);
    }
    if (!isOpen && shouldOpen) {
      onOpen();
    }
    if (isOpen && shouldClose) {
      onClose();
    }

    autoOpenRef.current = flags;
  }, [
    currentChatId,
    fileToPreview,
    hasCanvasContent,
    canvasMatchesChat,
    activeTab,
    canvasSurfaceId,
    canvasLocation,
    viewingSubAgentTaskId,
    forcedWebContextId,
    canvasRequestNonce,
    hasGoalContent,
    goalMatchesChat,
    viewportWidthPx,
    isOpen,
    onOpen,
    onClose,
  ]);

  // In a new chat only the Tools tab is usable — the rest have no chat context
  // yet, so they can't be selected (avoids opening an empty/collapsed panel).
  const isTabLocked = useCallback((tabId: TabId) => isNewChat && tabId !== 'tools', [isNewChat]);

  // ── Header tab click: toggle panel or switch tab ───────────────────
  const handleTabClick = useCallback(
    (tabId: TabId) => {
      const targetTab = tabs.find((tab) => tab.id === tabId);
      if (!targetTab || !targetTab.hasContent || isTabLocked(tabId)) return;

      if (isOpen && activeTab === tabId) {
        onClose();
      } else {
        setActiveTab(tabId);
        if (!isOpen) onOpen();
      }
    },
    [tabs, isOpen, activeTab, onClose, onOpen, isTabLocked]
  );

  const chatTasks = goalMatchesChat ? tasks : [];
  const doneTaskCount = chatTasks.filter((task) => task.status === 'completed').length;
  const currentTask = chatTasks.find((task) => task.status === 'in_progress');
  const runningAgentCount = backgroundTasks.filter(
    (task) => task.status === 'running' || task.status === 'queued'
  ).length;
  const activeAgents = backgroundTasks.filter((task) => isSubAgentActive(task.status));
  const previewAgents = (activeAgents.length > 0 ? activeAgents : backgroundTasks.slice(-1)).slice(
    0,
    2
  );
  const contextStats = useContextUsageStats(currentChatId);
  const emptySections: Partial<Record<TabId, boolean>> = {
    plan: !isFocal && chatTasks.length === 0,
    agents: backgroundTasks.length === 0,
    context: !contextStats.known && contextStats.measuredPercent == null,
  };
  const overviewContent: Partial<
    Record<TabId, Pick<OverviewSection, 'summary' | 'detail' | 'preview' | 'body' | 'fullView'>>
  > = {
    plan: isFocal
      ? {
          summary: <RegentWaitingCount />,
          detail: <RegentBoardCounts />,
          body: <RegentBoardList onOpenChat={(chatId) => void openChatFromBoard(chatId)} />,
        }
      : {
          summary: chatTasks.length > 0 ? `${doneTaskCount}/${chatTasks.length}` : undefined,
          detail:
            chatTasks.length > 0 ? (
              <PlanProgress
                statuses={chatTasks.map((task) => task.status)}
                caption={currentTask?.title ?? goal?.objective}
              />
            ) : undefined,
          body: (
            <OverviewList
              items={chatTasks}
              empty={t('sidebar.overview.noPlan')}
              getKey={(task) => task.id}
              muted={(task) => task.status === 'completed' || task.status === 'cancelled'}
              renderMarker={(task) => (
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    task.status === 'completed'
                      ? 'bg-brutal-green'
                      : task.status === 'in_progress'
                        ? 'bg-brutal-yellow'
                        : 'bg-neutral-300 dark:bg-zinc-600'
                  }`}
                />
              )}
              renderLabel={(task) => task.title}
            />
          ),
        },
    agents: {
      summary: runningAgentCount
        ? t('sidebar.overview.running', { count: runningAgentCount })
        : undefined,
      preview: (
        <ul className="mt-1.5 space-y-0.5">
          {previewAgents.map((task) => (
            <li
              key={task.task_id}
              className="flex items-center gap-2 text-xs text-neutral-500 dark:text-neutral-400"
            >
              <span
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                  isSubAgentActive(task.status)
                    ? 'bg-brutal-blue animate-pulse'
                    : task.status === 'failed'
                      ? 'bg-brutal-red'
                      : 'bg-neutral-300 dark:bg-zinc-600'
                }`}
              />
              <span className="truncate">{task.description}</span>
            </li>
          ))}
        </ul>
      ),
      body: (
        <OverviewList
          items={backgroundTasks}
          empty={t('backgroundTasks.empty')}
          getKey={(task) => task.task_id}
          muted={(task) => !isSubAgentActive(task.status)}
          renderMarker={(task) => (
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                isSubAgentActive(task.status)
                  ? 'bg-brutal-blue animate-pulse'
                  : task.status === 'failed'
                    ? 'bg-brutal-red'
                    : 'bg-neutral-300 dark:bg-zinc-600'
              }`}
            />
          )}
          renderLabel={(task) => task.description}
          onSelect={(task) => onSelectSubAgent?.(task.task_id)}
        />
      ),
    },
    context: {
      summary:
        contextStats.measuredPercent != null
          ? formatPercent(contextStats.measuredPercent)
          : undefined,
      preview: currentChatId ? <ContextUsageHeadline chatId={currentChatId} /> : null,
      body: currentChatId ? (
        <>
          <ContextWindowStats chatId={currentChatId} />
          <ContextUsageSummary chatId={currentChatId} plain />
        </>
      ) : null,
    },
    environment: {
      // Once expanded, the project row names the project.
      summary: expandedSections.has('environment') ? undefined : <EnvironmentProjectName />,
      preview: <EnvironmentPreview />,
      body: <EnvironmentSummary />,
      fullView: false,
    },
  };
  const overviewSections: OverviewSection[] = tabs
    .filter(
      (tab) =>
        (!tab.pinned || tab.id === 'plan') &&
        tab.hasContent &&
        !isTabLocked(tab.id) &&
        !emptySections[tab.id]
    )
    .map((tab) => ({
      id: tab.id,
      icon: tab.icon,
      label: t(tab.labelKey) || tab.fallbackLabel,
      activityClass: tab.hasActivity ? tab.activityClass : undefined,
      body: null,
      ...overviewContent[tab.id],
    }));
  const headerTabs = tabs.filter((tab) => tab.pinned && tab.hasContent && !isTabLocked(tab.id));
  // Next to the overview, so the board never lands in the overflow menu.
  if (isFocal) {
    const board = headerTabs.findIndex((tab) => tab.id === 'plan');
    if (board > 1) headerTabs.splice(1, 0, ...headerTabs.splice(board, 1));
  }
  const activeTabInHeader = headerTabs.some((tab) => tab.id === activeTab);
  const maxHeaderTabs = chatAreaWidth > 0 && chatAreaWidth < 900 ? 3 : 4;
  const overflowing = headerTabs.length > maxHeaderTabs;
  const visibleHeaderTabs = overflowing ? headerTabs.slice(0, maxHeaderTabs - 1) : headerTabs;
  // The open panel keeps its button, so the header always shows where you are.
  const activeOverflowTab = overflowing
    ? headerTabs.slice(maxHeaderTabs - 1).find((tab) => tab.id === activeTab)
    : undefined;
  if (activeOverflowTab) visibleHeaderTabs.push(activeOverflowTab);
  const overflowTabs = headerTabs.filter((tab) => !visibleHeaderTabs.includes(tab));
  const openChatFromBoard = async (chatId: string): Promise<void> => {
    if (isFocal) markOpenedFromRegent(chatId);
    const opened = await onTaskChat?.(chatId);
    if (!opened && isFocal) unmarkOpenedFromRegent(chatId);
    if (opened) {
      if (isCoveringChat) dockSidebar(sidebarWidth ?? getDesktopDefaultWidth());
      if (isOverlayMode) onClose();
    }
  };
  const toggleSection = (tabId: TabId): void => {
    setExpandedSections((current) => {
      const next = new Set(current);
      if (!next.delete(tabId)) next.add(tabId);
      return next;
    });
  };
  const backToOverview = (
    <OverviewBackBar label={t('sidebar.tabs.overview')} onBack={() => setActiveTab('overview')} />
  );
  const contextOpenInOverview =
    isOpen && !isNewChat && activeTab === 'overview' && expandedSections.has('context');
  const openContextSection = (): void => {
    if (contextOpenInOverview) {
      onClose();
      return;
    }
    setActiveTab('overview');
    setExpandedSections((current) => new Set(current).add('context'));
    if (!isOpen) onOpen();
  };
  const closeSubAgent = (): void => {
    onCloseSubAgent?.();
    setActiveTab('overview');
    setExpandedSections((current) => new Set(current).add('agents'));
  };
  const overviewPanel = (
    <div
      // A reserved gutter keeps expanding a section from narrowing every row.
      className={`flex-1 h-full flex-col min-h-0 overflow-y-auto scrollbar-stable bg-neutral-50 dark:bg-zinc-900 ${activeTab === 'overview' ? 'flex' : 'hidden'}`}
    >
      <SidebarOverview
        sections={overviewSections}
        expanded={expandedSections}
        onToggle={toggleSection}
        onOpenFull={setActiveTab}
        openFullLabel={t('sidebar.overview.viewAll')}
        emptyLabel={t('sidebar.overview.empty')}
      />
    </div>
  );

  useEffect(() => {
    const parent = sidebarRef.current?.parentElement;
    if (!parent) return;
    setChatAreaWidth(parent.clientWidth);
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setChatAreaWidth(Math.round(entry.contentRect.width));
    });
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

  // Tab buttons live in the app header, so a closed sidebar takes no width.
  // New chat: in overlay mode hide entirely; on desktop only the tools tab expands.
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
  // The overview blends into the chat; content panels keep the brutalist edge.
  const sidebarLeftBorder =
    activeTab === 'overview'
      ? ''
      : coveringChat
        ? 'border-l border-neutral-300 dark:border-zinc-700'
        : 'border-l-3 border-brutal-black';
  const desktopWidth = effectiveOpen && !isNewChatOverlayHidden ? desktopOpenWidth : 0;

  // ── Report width via ResizeObserver ────────────────────────────────
  useEffect(() => {
    if (!onWidthChange) return;
    const element = sidebarRef.current;
    if (!element) return;

    const reportWidth = (measuredWidth: number): void => {
      // While dragging we drive width via direct DOM writes; don't push those
      // intermediate sizes up to App (it would re-render the layout per frame).
      // The final width is reported when setSidebarWidth commits on mouseup.
      if (dragState.current) return;
      const width = isCoveringChat ? 0 : Math.round(measuredWidth);
      onWidthChange(Number.isFinite(width) && width >= 0 ? width : null);
    };

    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      reportWidth(entry.borderBoxSize[0]?.inlineSize ?? element.getBoundingClientRect().width);
    });
    observer.observe(element, { box: 'border-box' });
    return () => {
      observer.disconnect();
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
    <SidebarExpansionContext.Provider
      value={{
        expanded: isOverlayMode ? coveringChat : isCoveringChat,
        toggle: () => {
          if (coveringChat) {
            dockSidebar(sidebarWidth ?? getDesktopDefaultWidth());
          } else {
            setCoverWidth(null);
            setCoveringChat(true);
          }
        },
      }}
    >
      <div ref={spacerRef} className="h-full shrink-0" style={{ width: 0 }} aria-hidden="true" />
      <div
        ref={sidebarRef}
        style={
          isNewChatOverlayHidden
            ? { width: 0 }
            : isOverlayMode
              ? { width: 0, maxWidth: 0 }
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
        // Animating docked width reflows the transcript and reports intermediate sizes back to App.
        className={`
        z-20 flex flex-row shrink-0 min-h-0 h-full overflow-visible
        ${isNewChatOverlayHidden ? 'pointer-events-none' : `bg-white dark:bg-zinc-900 ${!isOverlayMode && effectiveOpen ? sidebarLeftBorder : ''}`}
        relative
      `}
      >
        {/* ── Content Panel ─────────────────────────────────────────── */}
        {/* In overlay mode: slides in from the right edge over the chat */}
        {isOverlayMode ? (
          <div
            className={`absolute inset-y-0 right-full transform-gpu will-change-transform transition-transform duration-300 ease-in-out ${sidebarLeftBorder} overflow-hidden bg-white dark:bg-zinc-900 ${isOpen ? 'translate-x-0' : 'translate-x-full pointer-events-none'}`}
            style={{
              width: isOpen
                ? isBrowserActive || coveringChat
                  ? effectiveViewportWidth
                  : desktopOpenWidth
                : 0,
            }}
          >
            <div className="flex flex-col h-full min-h-0 min-w-0 overflow-hidden">
              <div className="flex-1 overflow-y-auto bg-neutral-50/50 dark:bg-zinc-900 scrollbar-thin scrollbar-track-neutral-200 dark:scrollbar-track-zinc-700 scrollbar-thumb-brutal-black flex flex-col min-h-0">
                {overviewPanel}
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
                  {backToOverview}
                  <div className="flex-1 min-h-0">
                    {currentChatId && <RepositoryContextView chatId={currentChatId} />}
                  </div>
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
                    <BackgroundTaskView taskId={viewingSubAgentTaskId} onClose={closeSubAgent} />
                  ) : currentChatId ? (
                    <>
                      {backToOverview}
                      <div className="flex-1 min-h-0">
                        <BackgroundTaskList
                          chatId={currentChatId}
                          onSelect={(taskId) => onSelectSubAgent?.(taskId)}
                        />
                      </div>
                    </>
                  ) : (
                    <div className="flex items-center justify-center h-full text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-400">
                      {t('backgroundTasks.empty')}
                    </div>
                  )}
                </div>

                <div
                  className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'tools' ? 'flex' : 'hidden'}`}
                >
                  {currentChatId === FOCAL_CHAT_ID ? <FocalToolsPanel /> : <ToolsPanel />}
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
              className={`flex flex-col min-h-0 min-w-0 flex-1 overflow-hidden transform-gpu will-change-transform transition-[opacity,transform] duration-200 ease-out ${effectiveOpen ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-3 pointer-events-none'}`}
            >
              <div className="flex-1 overflow-y-auto bg-neutral-50/50 dark:bg-zinc-900 scrollbar-thin scrollbar-track-neutral-200 dark:scrollbar-track-zinc-700 scrollbar-thumb-brutal-black flex flex-col min-h-0">
                {overviewPanel}
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
                  {backToOverview}
                  <div className="flex-1 min-h-0">
                    {currentChatId && <RepositoryContextView chatId={currentChatId} />}
                  </div>
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
                    <BackgroundTaskView taskId={viewingSubAgentTaskId} onClose={closeSubAgent} />
                  ) : currentChatId ? (
                    <>
                      {backToOverview}
                      <div className="flex-1 min-h-0">
                        <BackgroundTaskList
                          chatId={currentChatId}
                          onSelect={(taskId) => onSelectSubAgent?.(taskId)}
                        />
                      </div>
                    </>
                  ) : (
                    <div className="flex items-center justify-center h-full text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-400">
                      {t('backgroundTasks.empty')}
                    </div>
                  )}
                </div>

                <div
                  className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'tools' ? 'flex' : 'hidden'}`}
                >
                  {currentChatId === FOCAL_CHAT_ID ? <FocalToolsPanel /> : <ToolsPanel />}
                </div>
              </div>
            </div>
          </>
        )}

        <div
          className={`absolute inset-y-0 z-10 overflow-hidden bg-white dark:bg-zinc-900 ${effectiveOpen && activeTab === 'plan' ? 'flex flex-col' : 'hidden'}`}
          style={
            isOverlayMode ? { right: '100%', width: effectiveViewportWidth } : { left: 0, right: 0 }
          }
        >
          {currentChatId !== FOCAL_CHAT_ID && backToOverview}
          <div className="flex-1 min-h-0">
            <TaskPanel
              navigationError={taskNavigationError}
              onDismissError={onDismissTaskError}
              goal={goalMatchesChat ? goal : null}
              tasks={goalMatchesChat ? tasks : []}
              kanban={kanban}
              projectName={currentProjectName}
              chatTitles={chatTitles}
              focal={currentChatId === FOCAL_CHAT_ID}
              onOpenTask={async (task) => {
                // Marked before the switch, so the header sees the mark the moment
                // the chat becomes current, and taken back if it never does.
                const marked = currentChatId === FOCAL_CHAT_ID ? task.chatId : null;
                if (marked) markOpenedFromRegent(marked);
                const opened = (await onOpenTask?.(task)) ?? false;
                if (!opened && marked) unmarkOpenedFromRegent(marked);
                if (opened) {
                  if (isCoveringChat) dockSidebar(sidebarWidth ?? getDesktopDefaultWidth());
                  if (isOverlayMode) onClose();
                }
                return opened;
              }}
              onOpenChat={openChatFromBoard}
            />
          </div>
        </div>
      </div>
      {headerSlot &&
        createPortal(
          <div className="flex items-center gap-0.5">
            {isCoveringChat && activeTab !== 'plan' && (
              <button
                type="button"
                onClick={() => dockSidebar()}
                title={t('sidebar.dock')}
                aria-label={t('sidebar.dock')}
                className="flex h-7 w-7 items-center justify-center text-brutal-black hover:bg-neutral-100 dark:text-white dark:hover:bg-zinc-700"
              >
                <ChevronDoubleRightIcon className="h-4 w-4" />
              </button>
            )}
            {currentChatId && !isTabLocked('context') && (
              <ContextHeaderButton
                chatId={currentChatId}
                active={contextOpenInOverview}
                onOpen={openContextSection}
              />
            )}
            {visibleHeaderTabs.map((tab) => {
              const Icon = tab.icon;
              const isActive =
                effectiveOpen &&
                (activeTab === tab.id || (tab.id === 'overview' && !activeTabInHeader));
              const label = t(tab.labelKey) || tab.fallbackLabel;
              return (
                <React.Fragment key={tab.id}>
                  <button
                    type="button"
                    onClick={() => handleTabClick(tab.id)}
                    title={label}
                    aria-label={label}
                    aria-pressed={isActive}
                    className={`relative flex h-7 w-7 items-center justify-center rounded transition-colors ${
                      isActive
                        ? 'bg-neutral-200 text-brutal-black dark:bg-zinc-700 dark:text-white'
                        : 'text-neutral-500 hover:bg-neutral-100 hover:text-brutal-black dark:text-neutral-400 dark:hover:bg-zinc-700 dark:hover:text-white'
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    {tab.hasActivity && !isActive && (
                      <span
                        className={`absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full border border-brutal-black ${tab.activityClass ?? 'bg-brutal-yellow'}`}
                      />
                    )}
                  </button>
                  {tab.id === 'overview' && visibleHeaderTabs.length > 1 && (
                    <span
                      className="mx-1 h-4 w-px bg-neutral-300 dark:bg-zinc-600"
                      aria-hidden="true"
                    />
                  )}
                </React.Fragment>
              );
            })}
            {overflowTabs.length > 0 && (
              <HeaderMoreMenu
                items={overflowTabs.map((tab) => ({
                  id: tab.id,
                  icon: tab.icon,
                  label: t(tab.labelKey) || tab.fallbackLabel,
                  activityClass: tab.hasActivity
                    ? (tab.activityClass ?? 'bg-brutal-yellow')
                    : undefined,
                }))}
                label={t('sidebar.morePanels')}
                icon={EllipsisHorizontalIcon}
                onSelect={handleTabClick}
              />
            )}
          </div>,
          headerSlot
        )}
    </SidebarExpansionContext.Provider>
  );
};
