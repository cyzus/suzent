/**
 * CanvasView — renders active A2UI surfaces in the sidebar canvas panel.
 *
 * Shows a tab strip when multiple surfaces are active. User interactions
 * (button clicks, form submits) are dispatched via the /canvas/{chatId}/action
 * endpoint and inject a lightweight "action message" into the chat.
 */

import React, { useCallback, useLayoutEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowsPointingOutIcon, ArrowsPointingInIcon } from '@heroicons/react/24/outline';
import type { CanvasState } from '../../hooks/useCanvas';
import { A2UIRenderer } from '../a2ui/A2UIRenderer';
import { BrutalButton } from '../BrutalButton';
import { WorkspacePanel } from '../WorkspacePanel';
import { useI18n } from '../../i18n';

interface CanvasViewProps {
  canvas: CanvasState;
  onDispatch: (action: string, context: Record<string, unknown>, surfaceId: string) => void;
}

export const CanvasView: React.FC<CanvasViewProps> = ({ canvas, onDispatch }) => {
  const { t } = useI18n();
  const { surfaces, activeSurfaceId, setActiveSurface } = canvas;
  const hasMultipleSurfaces = surfaces.length > 1;
  const activeSurface = surfaces.find((s) => s.id === activeSurfaceId) ?? surfaces[0] ?? null;
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [host] = useState(() => document.createElement('div'));
  const [inlineSlot, setInlineSlot] = useState<HTMLDivElement | null>(null);
  const [expandedSlot, setExpandedSlot] = useState<HTMLDivElement | null>(null);
  useLayoutEffect(() => {
    const slot = isFullscreen ? expandedSlot : inlineSlot;
    if (slot && host.parentNode !== slot) slot.appendChild(host);
  }, [isFullscreen, inlineSlot, expandedSlot, host]);

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
    <div className="flex-1 overflow-x-auto flex min-w-0 h-11 items-stretch">
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
    <div className="min-w-0 p-4">
      <A2UIRenderer component={activeSurface.component} onAction={dispatchAction} />
    </div>
  );

  return (
    <>
      <div className="flex flex-col h-full min-h-0 min-w-0">
        <div
          className={`flex items-stretch border-b-3 border-brutal-black shrink-0 ${hasMultipleSurfaces ? 'bg-neutral-100 dark:bg-zinc-900' : 'bg-white dark:bg-zinc-800'}`}
        >
          <div className="flex-1 min-w-0">{surfaceNav}</div>
          <div className="px-2 h-11 flex items-center justify-center bg-white dark:bg-zinc-800 shrink-0">
            <BrutalButton
              variant="default"
              size="icon"
              onClick={() => setIsFullscreen(true)}
              title={t('a2uiSurface.fullscreen')}
            >
              <ArrowsPointingOutIcon className="w-4 h-4" />
            </BrutalButton>
          </div>
        </div>
        <div ref={setInlineSlot} className="flex-1 min-h-0 overflow-y-auto scrollbar-thin" />
      </div>
      {createPortal(content, host)}

      <WorkspacePanel open={isFullscreen} onClose={() => setIsFullscreen(false)}>
        <div className="flex items-center justify-between px-3 py-2 border-b-3 border-brutal-black bg-brutal-yellow dark:bg-zinc-800 shrink-0">
          <span className="text-[10px] font-bold uppercase tracking-widest font-mono text-brutal-black dark:text-white">
            {activeSurface.title ?? activeSurface.id}
          </span>
          <div className="flex items-center gap-2">
            <BrutalButton
              variant="primary"
              className="px-2 py-0.5 text-[10px] h-full"
              onClick={() => setIsFullscreen(false)}
              title={t('a2uiSurface.exitFullscreen')}
            >
              <ArrowsPointingInIcon className="w-4 h-4" />
            </BrutalButton>
          </div>
        </div>

        <div className="flex flex-col min-h-0 flex-1">
          {/* surfaceNav carries flex-1 for the horizontal header; in this vertical
              column it must not grow vertically, so pin it with shrink-0 + h-11. */}
          <div className="shrink-0 h-11 flex border-b-2 border-brutal-black">{surfaceNav}</div>
          <div ref={setExpandedSlot} className="flex-1 min-h-0 overflow-y-auto scrollbar-thin" />
        </div>
      </WorkspacePanel>
    </>
  );
};
