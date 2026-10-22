import { useSidebarExpansion } from './SidebarExpansionContext';
import { ExpandedSurfaceCard } from '../ExpandedSurfaceCard';
import { BrutalButton } from '../BrutalButton';
import { FullscreenButton } from '../FullscreenButton';
/**
 * CanvasView — renders active A2UI surfaces in the sidebar canvas panel.
 *
 * Shows a tab strip when multiple surfaces are active. User interactions
 * (button clicks, form submits) are dispatched via the /canvas/{chatId}/action
 * endpoint and inject a lightweight "action message" into the chat.
 */

import React, { useCallback, useLayoutEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import type { CanvasState } from '../../hooks/useCanvas';
import { A2UIRenderer } from '../a2ui/A2UIRenderer';
import { A2UIHtmlComponent } from '../a2ui/components/A2UIHtmlComponent';
import { htmlContentHeight } from '../../lib/a2uiHtml';
import {
  useInlineSurfaceContext,
  useSurfaceEntry,
  useSurfaceSlot,
} from '../a2ui/InlineSurfaceContext';
import { WorkspacePanel } from '../WorkspacePanel';
import { useI18n } from '../../i18n';

interface CanvasViewProps {
  canvas: CanvasState;
  onDispatch: (action: string, context: Record<string, unknown>, surfaceId: string) => void;
}

export const CanvasView: React.FC<CanvasViewProps> = ({ canvas, onDispatch }) => {
  const { t } = useI18n();
  const sidebarExpansion = useSidebarExpansion();
  const { surfaces, activeSurfaceId, setActiveSurface } = canvas;
  const hasMultipleSurfaces = surfaces.length > 1;
  const activeSurface = surfaces.find((s) => s.id === activeSurfaceId) ?? surfaces[0] ?? null;
  const ctx = useInlineSurfaceContext();
  const entry = useSurfaceEntry(activeSurface?.id ?? '');
  const workspace = ctx?.workspace;
  const shownInChat = entry?.location === 'inline';
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [host] = useState(() => document.createElement('div'));
  const [inlineSlot, setInlineSlot] = useState<HTMLDivElement | null>(null);
  const [expandedSlot, setExpandedSlot] = useState<HTMLDivElement | null>(null);
  const fixedHtml =
    activeSurface?.component.type === 'html' &&
    htmlContentHeight(activeSurface.component.height) !== null;
  useLayoutEffect(() => {
    host.style.height = fixedHtml ? '100%' : '';
  }, [host, fixedHtml]);
  useLayoutEffect(() => {
    if (workspace) return;
    const slot = isFullscreen ? expandedSlot : inlineSlot;
    if (slot && host.parentNode !== slot) slot.appendChild(host);
  }, [isFullscreen, inlineSlot, expandedSlot, host, workspace]);
  useLayoutEffect(() => {
    if (workspace && activeSurface) workspace.upsert(activeSurface);
  }, [workspace, activeSurface]);
  const sharedCanvas = useSurfaceSlot(activeSurface?.id ?? '', 'canvas', Boolean(activeSurface));
  const sharedFullscreen = useSurfaceSlot(
    activeSurface?.id ?? '',
    'fullscreen',
    Boolean(activeSurface) && isFullscreen && !shownInChat
  );
  const attachCanvas = useCallback(
    (node: HTMLDivElement | null) => {
      sharedCanvas(node);
      setInlineSlot(node);
    },
    [sharedCanvas]
  );
  const attachFullscreen = useCallback(
    (node: HTMLDivElement | null) => {
      sharedFullscreen(node);
      setExpandedSlot(node);
    },
    [sharedFullscreen]
  );
  useLayoutEffect(() => {
    if (shownInChat) setIsFullscreen(false);
  }, [shownInChat]);

  const dispatchAction = useCallback(
    (action: string, context: Record<string, unknown>) => {
      onDispatch(action, context, activeSurface?.id ?? '');
    },
    [onDispatch, activeSurface]
  );

  if (!activeSurface) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-6 py-12 gap-2">
        <p className="text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-400 dark:text-neutral-500">
          {t('a2uiSurface.emptyCanvas')}
        </p>
        <p className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">
          {t('a2uiSurface.emptyCanvasHint')}
        </p>
      </div>
    );
  }

  const surfaceNav = (
    <div className="flex-1 overflow-x-auto flex min-w-0 h-8 items-stretch">
      {hasMultipleSurfaces ? (
        surfaces.map((s) => (
          <button
            key={s.id}
            onClick={() => setActiveSurface(s.id)}
            className={`px-3 h-full flex items-center text-[10px] font-bold uppercase tracking-widest font-mono whitespace-nowrap border-r-2 border-brutal-black transition-colors shrink-0
            ${
              s.id === activeSurfaceId
                ? 'bg-brutal-black text-white'
                : 'bg-white dark:bg-zinc-800 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-700'
            }`}
          >
            {s.title ?? s.id}
          </button>
        ))
      ) : (
        <div className="px-3 h-full flex-1 min-w-0 flex items-center bg-white dark:bg-zinc-800">
          <span className="text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-500 dark:text-neutral-400 truncate w-full block">
            {activeSurface.title ?? activeSurface.id}
          </span>
        </div>
      )}
    </div>
  );

  const content = (
    <div
      className={`min-w-0 ${fixedHtml ? 'h-full' : ''} ${activeSurface.component.type === 'html' ? '' : 'p-4'}`}
    >
      {activeSurface.component.type === 'html' ? (
        <A2UIHtmlComponent
          component={activeSurface.component}
          onAction={dispatchAction}
          framed={false}
        />
      ) : (
        <A2UIRenderer component={activeSurface.component} onAction={dispatchAction} />
      )}
    </div>
  );

  return (
    <>
      <div className="flex flex-col h-full min-h-0 min-w-0">
        <div
          className={`flex items-stretch border-b-2 border-brutal-black shrink-0 ${hasMultipleSurfaces ? 'bg-neutral-100 dark:bg-zinc-900' : 'bg-white dark:bg-zinc-800'}`}
        >
          <div className="flex-1 min-w-0">{surfaceNav}</div>
          <div className="px-3 py-2 flex items-start justify-center bg-white dark:bg-zinc-800 shrink-0">
            <FullscreenButton
              expanded={sidebarExpansion?.expanded}
              onClick={() => (sidebarExpansion ? sidebarExpansion.toggle() : setIsFullscreen(true))}
              disabled={shownInChat}
            />
          </div>
        </div>
        {shownInChat && (
          <div className="flex items-center justify-between gap-3 p-4 text-xs">
            <span>{t('a2uiSurface.inChat')}</span>
            <BrutalButton
              type="button"
              size="xs"

              onClick={() => ctx?.openInCanvas(activeSurface)}
            >
              {t('a2uiSurface.showHere')}
            </BrutalButton>
          </div>
        )}
        <div
          ref={attachCanvas}
          className={`flex-1 min-h-0 ${fixedHtml ? 'overflow-hidden' : 'overflow-y-auto scrollbar-thin'}`}
        />
      </div>
      {!workspace && createPortal(content, host)}

      <WorkspacePanel open={isFullscreen} onClose={() => setIsFullscreen(false)}>
        <ExpandedSurfaceCard
          title={activeSurface.title ?? activeSurface.id}
          navigation={hasMultipleSurfaces ? surfaceNav : undefined}
          onShrink={() => setIsFullscreen(false)}
        >
          <div
            ref={attachFullscreen}
            className={`flex-1 min-h-0 ${fixedHtml ? 'overflow-hidden' : 'overflow-y-auto scrollbar-thin'}`}
          />
        </ExpandedSurfaceCard>
      </WorkspacePanel>
    </>
  );
};
