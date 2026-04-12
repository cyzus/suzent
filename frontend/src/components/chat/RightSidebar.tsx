import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useI18n } from '../../i18n';
import { PlanProgress } from '../PlanProgress';
import { SandboxFiles } from '../sidebar/SandboxFiles';
import { BrowserView } from '../sidebar/BrowserView';
import { CanvasView } from '../sidebar/CanvasView';
import { SubAgentView } from '../sidebar/SubAgentView';
import type { Plan } from '../../types/api';
import type { CanvasState } from '../../hooks/useCanvas';
import {
  DESKTOP_BREAKPOINT_PX,
  MIN_RIGHT_SIDEBAR_WIDTH_PX,
  MAX_RIGHT_SIDEBAR_WIDTH_PX,
} from '../../lib/layout';

interface RightSidebarProps {
  isOpen: boolean;
  onClose: () => void;
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
}

export const RightSidebar: React.FC<RightSidebarProps> = ({
  isOpen,
  onClose,
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
}) => {
  const { t } = useI18n();
  const [activeTab, setActiveTab] = useState<'files' | 'browser' | 'canvas' | 'agents'>('browser');
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
    if (clamped !== sidebarWidth) {
      setSidebarWidth(clamped);
    }
  }, [sidebarWidth, effectiveMaxWidth, forceFullView]);

  useEffect(() => {
    if (forceFullView && sidebarWidth !== null) {
      setSidebarWidth(null);
    }
  }, [forceFullView, sidebarWidth]);

  // Auto-switch to files tab when a file is provided
  useEffect(() => {
    if (fileToPreview) {
      setActiveTab('files');
    }
  }, [fileToPreview]);

  // Auto-switch to canvas tab when the first surface arrives
  useEffect(() => {
    if (canvas?.hasSurfaces) {
      setActiveTab('canvas');
    }
  }, [canvas?.hasSurfaces]);

  // Auto-switch to agents tab when a sub-agent is opened
  useEffect(() => {
    if (viewingSubAgentTaskId) {
      setActiveTab('agents');
    }
  }, [viewingSubAgentTaskId]);

  const isAutoExpanded = (activeTab === 'files' && isFileExpanded) || (activeTab === 'browser' && isBrowserStreamActive);
  const isCanvasActive = activeTab === 'canvas' && !!canvas?.hasSurfaces;
  const hasCustomWidth = sidebarWidth !== null;
  const shouldUseCustomWidth = hasCustomWidth && !isOverlayMode;

  const getDesktopDefaultWidth = () => {
    if (isAutoExpanded) {
      return Math.round(effectiveViewportWidth * 0.5);
    }
    if (isCanvasActive) {
      return 576; // 36rem
    }
    return 384; // 24rem
  };

  const desktopOpenWidth = Math.max(
    MIN_RIGHT_SIDEBAR_WIDTH_PX,
    Math.min(effectiveMaxWidth, shouldUseCustomWidth ? sidebarWidth! : getDesktopDefaultWidth()),
  );

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
        : {
          width: isOpen ? desktopOpenWidth : 0,
          maxWidth: effectiveMaxWidth,
        }}
      className={`
        z-20 flex flex-col shrink-0 min-h-0 h-full overflow-hidden bg-white dark:bg-zinc-900
        ${isOpen ? 'border-l-3 border-brutal-black' : 'border-l-0'}
        ${isOverlayMode
          ? `absolute inset-y-0 right-0 transition-transform duration-300 ease-in-out ${isOpen ? 'translate-x-0' : 'translate-x-full pointer-events-none'}`
          : 'relative transition-[width] duration-300 ease-in-out'
        }
      `}
    >
      {/* Drag-to-resize handle */}
      {!forceFullView && (
        <div
          onMouseDown={handleResizeStart}
          className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize z-50 hover:bg-brutal-black/20 active:bg-brutal-black/30 transition-colors hidden lg:block"
          title="Drag to resize"
        />
      )}

      {/* Tab Header */}
      <div className="h-14 bg-white dark:bg-zinc-800 border-b-3 border-brutal-black flex items-center justify-between px-0 shrink-0">
        <div className="flex h-full w-full">
          <button
            onClick={() => setActiveTab('files')}
            className={`flex-1 px-2 font-brutal font-bold text-sm tracking-wider uppercase h-full border-r-3 border-brutal-black transition-colors ${activeTab === 'files'
              ? 'bg-brutal-black text-white'
              : 'bg-white dark:bg-zinc-800 hover:bg-neutral-100 dark:hover:bg-zinc-700 text-brutal-black dark:text-white'
              }`}
          >
            {t('sidebar.tabs.files')}
          </button>
          <button
            onClick={() => setActiveTab('browser')}
            className={`flex-1 px-2 font-brutal font-bold text-sm tracking-wider uppercase h-full border-r-3 border-brutal-black transition-colors ${activeTab === 'browser'
              ? 'bg-brutal-black text-white'
              : 'bg-white dark:bg-zinc-800 hover:bg-neutral-100 dark:hover:bg-zinc-700 text-brutal-black dark:text-white'
              }`}
          >
            {t('sidebar.tabs.browser')}
          </button>
          <button
            onClick={() => setActiveTab('canvas')}
            className={`flex-1 px-2 font-brutal font-bold text-sm tracking-wider uppercase h-full transition-colors relative ${activeTab === 'canvas'
              ? 'bg-brutal-black text-white'
              : 'bg-white dark:bg-zinc-800 hover:bg-neutral-100 dark:hover:bg-zinc-700 text-brutal-black dark:text-white'
              }`}
          >
            Canvas
            {canvas?.hasSurfaces && activeTab !== 'canvas' && (
              <span className="absolute top-2 right-2 w-2 h-2 bg-brutal-yellow border border-brutal-black rounded-full" />
            )}
          </button>
          <button
            onClick={() => setActiveTab('agents')}
            className={`flex-1 px-2 font-brutal font-bold text-sm tracking-wider uppercase h-full transition-colors relative ${activeTab === 'agents'
              ? 'bg-brutal-black text-white'
              : 'bg-white dark:bg-zinc-800 hover:bg-neutral-100 dark:hover:bg-zinc-700 text-brutal-black dark:text-white'
              }`}
          >
            Agents
            {viewingSubAgentTaskId && activeTab !== 'agents' && (
              <span className="absolute top-2 right-2 w-2 h-2 bg-brutal-blue border border-brutal-black rounded-full animate-pulse" />
            )}
          </button>
        </div>
      </div>

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
        {/* Always render BrowserView to keep WS connection alive, just hide it */}
        <div className={`flex-1 h-full flex flex-col ${activeTab === 'browser' ? 'flex' : 'hidden'}`}>
          <BrowserView onStreamActive={setIsBrowserStreamActive} />
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
          ) : (
            <div className="flex items-center justify-center h-full text-[11px] text-neutral-400 font-mono">
              No sub-agent selected
            </div>
          )}
        </div>
      </div>

      {/* Permanent Plan View */}
      <div className="border-t-3 border-brutal-black bg-white dark:bg-zinc-800 p-4 shrink-0 max-h-[30%] overflow-y-auto scrollbar-thin">
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
  );
};
