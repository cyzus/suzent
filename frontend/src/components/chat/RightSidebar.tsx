import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useI18n } from '../../i18n';
import { PlanProgress } from '../PlanProgress';
import { SandboxFiles } from '../sidebar/SandboxFiles';
import { WebActivitiesView } from '../sidebar/WebActivitiesView';
import { CanvasView } from '../sidebar/CanvasView';
import { SubAgentView } from '../sidebar/SubAgentView';
import { SubAgentList } from '../sidebar/SubAgentList';
import type { Message, Plan } from '../../types/api';
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
} from '@heroicons/react/24/outline';

// Icon strip width in px — keep in sync with w-11 (2.75rem = 44px)
const ICON_STRIP_WIDTH = 44;

type TabId = 'files' | 'browser' | 'canvas' | 'agents' | 'plan';

interface RightSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onOpen: () => void;
  onWidthChange?: (width: number | null) => void;
  maxWidthPx?: number;
  viewportWidthPx?: number;
  forceFullView?: boolean;
  plan: Plan | null;
  isPlanExpanded: boolean;
  onTogglePlanExpand: () => void;
  fileToPreview?: { path: string; name: string } | null;
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
  viewportWidthPx,
  forceFullView = false,
  plan,
  isPlanExpanded,
  onTogglePlanExpand,
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
}) => {
  useI18n();
  const [activeTab, setActiveTab] = useState<TabId>('browser');
  const [isFileExpanded, setIsFileExpanded] = useState(false);
  const [isBrowserStreamActive, setIsBrowserStreamActive] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState<number | null>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);
  const dragState = useRef<{ startX: number; startWidth: number } | null>(null);

  const effectiveMaxWidth = Math.max(
    MIN_RIGHT_SIDEBAR_WIDTH_PX,
    Math.min(MAX_RIGHT_SIDEBAR_WIDTH_PX, maxWidthPx ?? MAX_RIGHT_SIDEBAR_WIDTH_PX),
  );
  const effectiveViewportWidth = viewportWidthPx ?? window.innerWidth;
  const isDesktop = effectiveViewportWidth >= DESKTOP_BREAKPOINT_PX;
  const isOverlayMode = forceFullView || !isDesktop;
  
  const webHistory = useWebHistory(messages);
  const hasValidPlan = Boolean(plan && plan.phases && plan.phases.length > 0);

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
      hasContent: isBrowserStreamActive || webHistory.length > 0,
      hasActivity: isBrowserStreamActive || webHistory.length > 0,
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
      fallbackLabel: 'Plan',
      hasContent: hasValidPlan,
      hasActivity: hasValidPlan,
      activityClass: 'bg-brutal-yellow',
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
    if (hasValidPlan) setActiveTab('plan');
  }, [hasValidPlan]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Open sidebar automatically when content arrives ─────────────────
  useEffect(() => {
    if (fileToPreview && !isOpen) onOpen();
  }, [fileToPreview]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (canvas?.hasSurfaces && !isOpen) onOpen();
  }, [canvas?.hasSurfaces]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (viewingSubAgentTaskId && !isOpen) onOpen();
  }, [viewingSubAgentTaskId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (hasValidPlan && !isOpen) onOpen();
  }, [hasValidPlan]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Icon strip click: toggle panel or switch tab ───────────────────
  const handleTabClick = useCallback((tabId: TabId) => {
    const targetTab = tabs.find(tab => tab.id === tabId);
    if (!targetTab) return;
    if (targetTab.id !== 'files' && !targetTab.hasContent) {
      return;
    }

    if (isOpen && activeTab === tabId) {
      onClose();
    } else {
      setActiveTab(tabId);
      if (!isOpen) onOpen();
    }
  }, [tabs, isOpen, activeTab, onClose, onOpen]);

  // ── Resize ─────────────────────────────────────────────────────────
  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    if (forceFullView) return;
    e.preventDefault();
    const width = sidebarRef.current?.getBoundingClientRect().width ?? 384;
    dragState.current = { startX: e.clientX, startWidth: width };

    const onMouseMove = (ev: MouseEvent) => {
      if (!dragState.current) return;
      const delta = dragState.current.startX - ev.clientX;
      const next = Math.max(
        MIN_RIGHT_SIDEBAR_WIDTH_PX,
        Math.min(effectiveMaxWidth, dragState.current.startWidth + delta),
      );
      setSidebarWidth(next);
    };

    const onMouseUp = () => {
      dragState.current = null;
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
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
  const isCanvasActive = activeTab === 'canvas' && !!canvas?.hasSurfaces;
  const hasCustomWidth = sidebarWidth !== null;
  const shouldUseCustomWidth = hasCustomWidth && !isOverlayMode;

  const getDesktopDefaultWidth = () => {
    if (isAutoExpanded) return Math.round(effectiveViewportWidth * 0.5);
    if (isCanvasActive) return 576;
    return 384;
  };

  const desktopOpenWidth = Math.max(
    MIN_RIGHT_SIDEBAR_WIDTH_PX,
    Math.min(effectiveMaxWidth, shouldUseCustomWidth ? sidebarWidth! : getDesktopDefaultWidth()),
  );

  // Desktop: icon strip always visible (44px), content panel expands on open
  // Overlay: full hide/show (icon strip is part of the slide)
  const desktopWidth = isOpen ? desktopOpenWidth : ICON_STRIP_WIDTH;

  // ── Report width via ResizeObserver ────────────────────────────────
  useEffect(() => {
    if (!onWidthChange) return;
    const element = sidebarRef.current;
    if (!element) return;

    const reportWidth = () => {
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
      style={isOverlayMode
        ? { width: '100%', maxWidth: '100%' }
        : { width: desktopWidth, maxWidth: effectiveMaxWidth }}
      className={`
        z-20 flex flex-row shrink-0 min-h-0 h-full overflow-hidden bg-white dark:bg-zinc-900
        border-l-3 border-brutal-black
        ${isOverlayMode
          ? `absolute inset-y-0 right-0 transition-transform duration-300 ease-in-out ${isOpen ? 'translate-x-0' : 'translate-x-full pointer-events-none'}`
          : 'relative transition-[width] duration-300 ease-in-out'
        }
      `}
    >
      {/* Drag-to-resize handle — on the left edge of the content panel */}
      {!forceFullView && isOpen && (
        <div
          onMouseDown={handleResizeStart}
          className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize z-50 hover:bg-brutal-black/20 active:bg-brutal-black/30 transition-colors hidden lg:block"
          title="Drag to resize"
        />
      )}

      {/* ── Content Panel ─────────────────────────────────────────── */}
      <div className={`flex flex-col min-h-0 flex-1 overflow-hidden transition-opacity duration-200 ${isOpen ? 'opacity-100 border-r-3 border-brutal-black' : 'opacity-0 pointer-events-none w-0'}`}>
        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto bg-neutral-50/50 dark:bg-zinc-900 scrollbar-thin scrollbar-track-neutral-200 dark:scrollbar-track-zinc-700 scrollbar-thumb-brutal-black flex flex-col min-h-0">
          <div className={`flex-1 h-full ${activeTab === 'files' ? 'block' : 'hidden'}`}>
            <SandboxFiles
              onViewModeChange={setIsFileExpanded}
              externalFilePath={fileToPreview?.path ?? null}
              externalFileName={fileToPreview?.name ?? null}
              onMaximize={onMaximizeFile}
            />
          </div>
          {/* Web Activities View (replaces old BrowserView) */}
          <div className={`flex-1 h-full flex flex-col ${activeTab === 'browser' ? 'flex' : 'hidden'}`}>
            <WebActivitiesView 
              messages={messages}
              isBrowserStreamActive={isBrowserStreamActive}
              onBrowserStreamActive={setIsBrowserStreamActive}
              forcedContextId={forcedWebContextId}
              onClearForcedContext={onClearForcedWebContext}
            />
          </div>
          <div className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'canvas' ? 'flex' : 'hidden'}`}>
            {canvas && (
              <CanvasView
                canvas={canvas}
                onDispatch={onCanvasDispatch ?? (() => {})}
              />
            )}
          </div>
          <div className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'agents' ? 'flex' : 'hidden'}`}>
            {viewingSubAgentTaskId ? (
              <SubAgentView
                taskId={viewingSubAgentTaskId}
                onClose={onCloseSubAgent}
              />
            ) : currentChatId ? (
              <SubAgentList
                chatId={currentChatId}
                onSelect={(taskId) => onSelectSubAgent?.(taskId)}
              />
            ) : (
              <div className="flex items-center justify-center h-full text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-400">
                No sub-agent selected
              </div>
            )}
          </div>
          <div className={`flex-1 h-full flex flex-col min-h-0 ${activeTab === 'plan' ? 'flex' : 'hidden'}`}>
            <PlanProgress
              plan={plan}
              isDocked={true}
              onToggleDock={onClose}
              isExpanded={isPlanExpanded}
              onToggleExpand={onTogglePlanExpand}
              isSidebarOpen={true}
            />
          </div>
        </div>
      </div>

      {/* ── Icon Strip ────────────────────────────────────────────── */}
      <div className="flex flex-col items-center bg-white dark:bg-zinc-800 shrink-0 w-11 py-1 gap-0.5">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = isOpen && activeTab === tab.id;
          const isIdle = !tab.hasContent;
          const isDisabled = tab.id !== 'files' && !tab.hasContent;

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
