/**
 * CanvasView — renders active A2UI surfaces in the sidebar canvas panel.
 *
 * Shows a tab strip when multiple surfaces are active. User interactions
 * (button clicks, form submits) are dispatched via the /canvas/{chatId}/action
 * endpoint and inject a lightweight "action message" into the chat.
 */

import React, { useCallback, useState } from 'react';
import { ArrowsPointingOutIcon, ArrowsPointingInIcon, XMarkIcon } from '@heroicons/react/24/outline';
import type { CanvasState } from '../../hooks/useCanvas';
import { A2UIRenderer } from '../a2ui/A2UIRenderer';
import { BrutalButton } from '../BrutalButton';
import { FullscreenOverlay } from '../FullscreenOverlay';

interface CanvasViewProps {
  canvas: CanvasState;
  onDispatch: (action: string, context: Record<string, unknown>, surfaceId: string) => void;
}

export const CanvasView: React.FC<CanvasViewProps> = ({
  canvas,
  onDispatch,
}) => {
  const { surfaces, activeSurfaceId, setActiveSurface } = canvas;
  const activeSurface = surfaces.find(s => s.id === activeSurfaceId) ?? surfaces[0] ?? null;
  const [isFullscreen, setIsFullscreen] = useState(false);

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
          No canvas surfaces
        </p>
        <p className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">
          The agent will render interactive surfaces here.
        </p>
      </div>
    );
  }

  const surfaceNav = (
    <div className="flex border-b-3 border-brutal-black shrink-0 bg-white dark:bg-zinc-800">
      <div className="flex-1 overflow-x-auto flex">
        {surfaces.length > 1 ? surfaces.map(s => (
          <button
            key={s.id}
            onClick={() => setActiveSurface(s.id)}
            className={`px-3 py-2 text-[10px] font-bold uppercase tracking-widest font-mono whitespace-nowrap border-r-2 border-brutal-black transition-colors
              ${s.id === activeSurfaceId
                ? 'bg-brutal-black text-white'
                : 'bg-white dark:bg-zinc-800 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-700'
              }`}
          >
            {s.title ?? s.id}
          </button>
        )) : (
          <div className="px-3 py-2 bg-neutral-50 dark:bg-zinc-800">
            <span className="text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-500 dark:text-neutral-400">
              {activeSurface.title ?? activeSurface.id}
            </span>
          </div>
        )}
      </div>
    </div>
  );

  const content = (
    <div className="flex-1 overflow-y-auto p-4 scrollbar-thin scrollbar-track-neutral-200 dark:scrollbar-track-zinc-700 scrollbar-thumb-brutal-black">
      <A2UIRenderer component={activeSurface.component} onAction={dispatchAction} />
    </div>
  );

  return (
    <>
      <div className="flex flex-col h-full min-h-0">
        <div className="flex items-center border-b-3 border-brutal-black shrink-0 bg-white dark:bg-zinc-800">
          <div className="flex-1 min-w-0">{surfaceNav}</div>
          <div className="px-2 py-1 border-l-2 border-brutal-black">
            <BrutalButton
              variant="default"
              size="icon"
              onClick={() => setIsFullscreen(true)}
              title="Fullscreen"
            >
              <ArrowsPointingOutIcon className="w-4 h-4" />
            </BrutalButton>
          </div>
        </div>
        {content}
      </div>

      <FullscreenOverlay
        open={isFullscreen}
        onClose={() => setIsFullscreen(false)}
        containerClassName="relative w-full max-w-[96vw] h-[94vh] bg-white dark:bg-zinc-900 border-4 border-brutal-black shadow-brutal-xl flex flex-col"
      >
        <div className="flex items-center justify-between px-4 py-2 border-b-3 border-brutal-black bg-brutal-yellow dark:bg-zinc-800 shrink-0">
          <span className="text-xs font-bold uppercase tracking-widest text-brutal-black dark:text-white">
            Canvas Fullscreen
          </span>
          <div className="flex items-center gap-2">
            <BrutalButton
              variant="primary"
              size="icon"
              onClick={() => setIsFullscreen(false)}
              title="Exit fullscreen"
            >
              <ArrowsPointingInIcon className="w-5 h-5" />
            </BrutalButton>
            <BrutalButton
              variant="danger"
              size="icon"
              onClick={() => setIsFullscreen(false)}
              title="Close"
            >
              <XMarkIcon className="w-5 h-5" />
            </BrutalButton>
          </div>
        </div>

        <div className="flex flex-col min-h-0 flex-1">
          {surfaceNav}
          {content}
        </div>
      </FullscreenOverlay>
    </>
  );
};
