/**
 * InlineSurface — an A2UI surface as it sits in a chat message.
 *
 * Inline surfaces get a slim header for popping them out to the side panel or
 * fullscreen. A canvas-target surface leaves only a pointer here, since its
 * content lives in the side panel. Either collapses once a later render of the
 * same surface id lands further down the chat.
 */

import React, { useLayoutEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  ArrowsPointingInIcon,
  ArrowsPointingOutIcon,
  ViewColumnsIcon,
} from '@heroicons/react/24/outline';
import type { A2UISurface } from '../../types/a2ui';
import { useI18n } from '../../i18n';
import { A2UIRenderer } from './A2UIRenderer';
import { isAnsweredQuestion } from '../../lib/questionAnswer';
import { FullscreenOverlay } from '../FullscreenOverlay';
import { BrutalButton } from '../BrutalButton';
import { useInlineSurfaceContext, useIsSuperseded } from './InlineSurfaceContext';

interface InlineSurfaceProps {
  surface: A2UISurface;
  onAction: (action: string, context?: Record<string, unknown>) => void;
  /** The user has written since this surface; a question form on it is answered. */
  answered?: boolean;
}

const noAction = (): void => {};

const labelClass =
  'text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-500 dark:text-neutral-400 truncate';

const iconButtonClass =
  'p-1 text-neutral-500 hover:text-brutal-black dark:text-neutral-400 dark:hover:text-white transition-colors';

export const InlineSurface: React.FC<InlineSurfaceProps> = ({
  surface,
  onAction,
  answered = false,
}) => {
  const { t } = useI18n();
  const ctx = useInlineSurfaceContext();
  // ask_question forms are answered once and removed; nothing to pop out.
  const interactive = !surface.deferred;
  const superseded = useIsSuperseded(surface, interactive);
  const [showOld, setShowOld] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  // The body is portaled into one host node that moves between the inline
  // slot and the fullscreen slot, so form input survives the switch instead
  // of living in two independent renderers.
  const [host] = useState(() => document.createElement('div'));
  const [inlineSlot, setInlineSlot] = useState<HTMLDivElement | null>(null);
  const [fullscreenSlot, setFullscreenSlot] = useState<HTMLDivElement | null>(null);
  useLayoutEffect(() => {
    const slot = fullscreen ? fullscreenSlot : inlineSlot;
    if (slot && host.parentNode !== slot) slot.appendChild(host);
  }, [fullscreen, inlineSlot, fullscreenSlot, host]);
  const title = surface.title || surface.id;

  const body = <A2UIRenderer component={surface.component} onAction={onAction} />;

  if (!interactive) return <div className="my-2">{body}</div>;

  // A saved question form that the user has since replied to: SUZENT's forms
  // outlive their turn, so without this a reload would offer it again.
  if (isAnsweredQuestion(surface, answered)) {
    return (
      <div className="my-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={labelClass}>{title}</span>
          <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500 shrink-0">
            {t('a2uiSurface.answered')}
          </span>
          <button
            type="button"
            onClick={() => setShowOld((v) => !v)}
            className="text-[10px] font-bold uppercase tracking-widest font-mono underline text-neutral-500 hover:text-brutal-black dark:text-neutral-400 dark:hover:text-white shrink-0"
          >
            {showOld ? t('a2uiSurface.hide') : t('a2uiSurface.show')}
          </button>
        </div>
        {showOld && (
          <div className="mt-2 opacity-70 pointer-events-none" aria-disabled="true">
            <A2UIRenderer component={surface.component} onAction={noAction} />
          </div>
        )}
      </div>
    );
  }

  if (superseded) {
    return (
      <div className="my-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={labelClass}>{title}</span>
          <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500 shrink-0">
            {t('a2uiSurface.updatedLater')}
          </span>
          <button
            type="button"
            onClick={() => setShowOld((v) => !v)}
            className="text-[10px] font-bold uppercase tracking-widest font-mono underline text-neutral-500 hover:text-brutal-black dark:text-neutral-400 dark:hover:text-white shrink-0"
          >
            {showOld ? t('a2uiSurface.hide') : t('a2uiSurface.show')}
          </button>
        </div>
        {showOld && <div className="mt-2 opacity-70">{body}</div>}
      </div>
    );
  }

  if (surface.target === 'canvas') {
    return (
      <div className="my-2 flex items-center gap-3 border-2 border-brutal-black bg-white dark:bg-zinc-800 px-3 py-2 min-w-0">
        <ViewColumnsIcon className="w-4 h-4 shrink-0 text-brutal-black dark:text-white" />
        <div className="flex-1 min-w-0 flex flex-col">
          <span className={`${labelClass} text-brutal-black dark:text-white`}>{title}</span>
          <span className="text-[10px] font-mono text-neutral-500 dark:text-neutral-400">
            {t('a2uiSurface.inSidePanel')}
          </span>
        </div>
        {ctx && (
          <BrutalButton
            variant="default"
            className="px-2 py-0.5 text-[10px] shrink-0"
            onClick={() => ctx.openInCanvas(surface)}
          >
            {t('a2uiSurface.open')}
          </BrutalButton>
        )}
      </div>
    );
  }

  return (
    <div className="my-2 min-w-0">
      <div className="flex items-center gap-1 min-w-0 mb-1">
        <span className={`${labelClass} flex-1`}>{title}</span>
        {ctx && (
          <button
            type="button"
            className={iconButtonClass}
            onClick={() => ctx.openInCanvas(surface)}
            title={t('a2uiSurface.openInSidePanel')}
            aria-label={t('a2uiSurface.openInSidePanel')}
          >
            <ViewColumnsIcon className="w-3.5 h-3.5" />
          </button>
        )}
        <button
          type="button"
          className={iconButtonClass}
          onClick={() => setFullscreen(true)}
          title={t('a2uiSurface.fullscreen')}
          aria-label={t('a2uiSurface.fullscreen')}
        >
          <ArrowsPointingOutIcon className="w-3.5 h-3.5" />
        </button>
      </div>
      <div ref={setInlineSlot} />
      {createPortal(body, host)}

      <FullscreenOverlay
        open={fullscreen}
        onClose={() => setFullscreen(false)}
        containerClassName="relative w-full max-w-[96vw] h-[94vh] bg-white dark:bg-zinc-900 border-4 border-brutal-black shadow-brutal-xl flex flex-col"
      >
        <div className="flex items-center justify-between gap-2 px-3 py-2 border-b-3 border-brutal-black bg-brutal-yellow dark:bg-zinc-800 shrink-0">
          <span className={`${labelClass} text-brutal-black dark:text-white`}>{title}</span>
          <BrutalButton
            variant="primary"
            className="px-2 py-0.5 text-[10px]"
            onClick={() => setFullscreen(false)}
            title={t('a2uiSurface.exitFullscreen')}
          >
            <ArrowsPointingInIcon className="w-4 h-4" />
          </BrutalButton>
        </div>
        <div ref={setFullscreenSlot} className="flex-1 min-h-0 overflow-y-auto p-4" />
      </FullscreenOverlay>
    </div>
  );
};
