import { ExpandedSurfaceCard } from '../ExpandedSurfaceCard';
import { FullscreenButton } from '../FullscreenButton';
/**
 * InlineSurface — an A2UI surface as it sits in a chat message.
 *
 * Inline surfaces get a slim header for popping them out to the side panel or
 * fullscreen. A canvas-target surface leaves only a pointer here, since its
 * content lives in the side panel. Either collapses once a later render of the
 * same surface id lands further down the chat.
 */

import React, { useCallback, useLayoutEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { ViewColumnsIcon } from '@heroicons/react/24/outline';
import type { A2UISurface } from '../../types/a2ui';
import { useI18n } from '../../i18n';
import { A2UIRenderer } from './A2UIRenderer';
import { isAnsweredQuestion } from '../../lib/questionAnswer';
import { WorkspacePanel } from '../WorkspacePanel';
import { BrutalButton, BrutalIconButton } from '../BrutalButton';
import {
  useInlineSurfaceContext,
  useIsSuperseded,
  useSurfaceEntry,
  useSurfaceSlot,
} from './InlineSurfaceContext';

interface InlineSurfaceProps {
  surface: A2UISurface;
  onAction: (action: string, context?: Record<string, unknown>) => void;
  /** The user has written since this surface; a question form on it is answered. */
  answered?: boolean;
}

const noAction = (): void => {};

const labelClass =
  'text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-500 dark:text-neutral-400 truncate';

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
  const entry = useSurfaceEntry(surface.id);
  const workspace = ctx?.workspace;
  const shared = Boolean(
    workspace && interactive && !superseded && !isAnsweredQuestion(surface, answered)
  );
  const [showOld, setShowOld] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  // The body is portaled into one host node that moves between the inline
  // slot and the fullscreen slot, so form input survives the switch instead
  // of living in two independent renderers.
  const [host] = useState(() => document.createElement('div'));
  const [inlineSlot, setInlineSlot] = useState<HTMLDivElement | null>(null);
  const [fullscreenSlot, setFullscreenSlot] = useState<HTMLDivElement | null>(null);
  useLayoutEffect(() => {
    if (shared) return;
    const slot = fullscreen ? fullscreenSlot : inlineSlot;
    if (slot && host.parentNode !== slot) slot.appendChild(host);
  }, [fullscreen, inlineSlot, fullscreenSlot, host, shared]);
  useLayoutEffect(() => {
    if (shared && workspace) workspace.upsert(surface);
  }, [shared, workspace, surface]);
  const sharedInline = useSurfaceSlot(surface.id, 'inline', shared);
  const sharedFullscreen = useSurfaceSlot(surface.id, 'fullscreen', shared && fullscreen);
  const attachInline = useCallback(
    (node: HTMLDivElement | null) => {
      sharedInline(node);
      setInlineSlot(node);
    },
    [sharedInline]
  );
  const attachFullscreen = useCallback(
    (node: HTMLDivElement | null) => {
      sharedFullscreen(node);
      setFullscreenSlot(node);
    },
    [sharedFullscreen]
  );
  const title = surface.title || surface.id;

  const body = <A2UIRenderer component={surface.component} onAction={onAction} />;

  if (!interactive) return <div className="my-2">{body}</div>;

  // A saved question form that the user has since replied to: Regent's forms
  // outlive their turn, so without this a reload would offer it again.
  if (isAnsweredQuestion(surface, answered)) {
    return (
      <div className="my-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={labelClass}>{title}</span>
          <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500 shrink-0">
            {t('a2uiSurface.answered')}
          </span>
          <BrutalButton
            size="xs"
            type="button"
            onClick={() => setShowOld((v) => !v)}
            className="shrink-0"
          >
            {showOld ? t('a2uiSurface.hide') : t('a2uiSurface.show')}
          </BrutalButton>
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
          <BrutalButton
            size="xs"
            type="button"
            onClick={() => setShowOld((v) => !v)}
            className="shrink-0"
          >
            {showOld ? t('a2uiSurface.hide') : t('a2uiSurface.show')}
          </BrutalButton>
        </div>
        {showOld && <div className="mt-2 opacity-70">{body}</div>}
      </div>
    );
  }

  const inCanvas = (entry?.location ?? surface.target) === 'canvas';
  const sidePanelPointer = (
    <div className="my-2 flex items-center gap-3 border-2 border-brutal-black bg-white dark:bg-zinc-800 px-3 py-2 min-w-0">
      <ViewColumnsIcon className="w-4 h-4 shrink-0 text-brutal-black dark:text-white" />
      <div className="flex-1 min-w-0 flex flex-col">
        <span className={`${labelClass} text-brutal-black dark:text-white`}>{title}</span>
        <span className="text-[10px] font-mono text-neutral-500 dark:text-neutral-400">
          {t('a2uiSurface.inSidePanel')}
        </span>
      </div>
      {ctx && (
        <>
          <BrutalButton
            size="xs"
            type="button"
            className="shrink-0"
            onClick={() => ctx.workspace.place(surface.id, 'inline')}
          >
            {t('a2uiSurface.showHere')}
          </BrutalButton>
          <BrutalButton
            variant="default"
            size="xs"
            className="shrink-0"
            onClick={() => ctx.openInCanvas(surface)}
          >
            {t('a2uiSurface.open')}
          </BrutalButton>
        </>
      )}
    </div>
  );

  return (
    <div className="my-2 min-w-0">
      {inCanvas ? (
        sidePanelPointer
      ) : (
        <div className="flex items-start gap-3 min-w-0 px-3 py-2">
          <span className={`${labelClass} flex-1 min-h-8 flex items-center`}>{title}</span>
          {ctx && (
            <BrutalIconButton
              type="button"
              className="shrink-0"
              onClick={() => ctx.openInCanvas(surface)}
              label={t('a2uiSurface.openInSidePanel')}
            >
              <ViewColumnsIcon className="w-4 h-4 stroke-2" />
            </BrutalIconButton>
          )}
          <FullscreenButton
            onClick={() => (ctx ? ctx.openInCanvas(surface, true) : setFullscreen(true))}
          />
        </div>
      )}
      <div ref={attachInline} className={inCanvas ? 'hidden' : undefined} />
      {!shared && createPortal(body, host)}

      <WorkspacePanel open={fullscreen} onClose={() => setFullscreen(false)}>
        <ExpandedSurfaceCard title={title} onShrink={() => setFullscreen(false)}>
          <div
            ref={attachFullscreen}
            className="flex-1 min-h-0 overflow-y-auto scrollbar-thin p-4"
          />
        </ExpandedSurfaceCard>
      </WorkspacePanel>
    </div>
  );
};
