import React, { useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import { useFocalStatus } from '../../hooks/useFocalStatus';
import { useChatStreamingStore } from '../../hooks/useChatStore';
import { FOCAL_CHAT_ID, type FocalAgentStatus } from '../../lib/focalAgent';
import { RegentCube } from './RegentCube';
import type { RegentState } from './RegentMark';
import { regentState, useRegentNod } from './regentState';

/** Regent's status, also treating a reply streaming in this chat as working. */
export function useLiveRegent(): { status: FocalAgentStatus | null; state: RegentState } {
  const status = useFocalStatus();
  const { isStreaming, activeStreamingChatId } = useChatStreamingStore();
  const working = isStreaming && activeStreamingChatId === FOCAL_CHAT_ID;
  return { status, state: working ? 'working' : regentState(status) };
}

interface RegentIdentityProps {
  status: FocalAgentStatus | null;
  state: RegentState;
}

/**
 * The title of Regent's chat in the one-row app header: "SUZENT Regent" and a
 * small pill for what waits on the user. Its picture lives in the sidebar, or
 * in the header's logo slot while the sidebar is collapsed.
 */
export function RegentIdentity({ status, state }: RegentIdentityProps): React.ReactElement {
  const { t } = useI18n();
  const waiting = Math.max(0, status?.waiting ?? 0);
  const pill =
    state === 'working'
      ? { label: t('chatList.focal.working'), dot: 'bg-brutal-blue animate-pulse' }
      : waiting > 0
        ? { label: t('chatList.focal.waitingCount', { count: waiting }), dot: 'bg-brutal-yellow' }
        : null;

  return (
    <div className="regent-identity flex min-w-0 items-baseline gap-2">
      <span className="shrink-0 font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
        {t('chatList.focal.brand')}
      </span>
      <span className="shrink-0 font-brutal text-2xl font-black leading-none tracking-[-0.04em] [-webkit-text-stroke:0.75px_currentColor] text-brutal-black dark:text-white">
        {t('chatList.focal.name')}
      </span>
      {pill && (
        <span className="ml-1 inline-flex min-w-0 items-center gap-1.5 self-center border-2 border-brutal-black bg-white px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider text-brutal-black dark:bg-zinc-700 dark:text-white">
          <span
            className={`h-2 w-2 shrink-0 border border-brutal-black ${pill.dot}`}
            aria-hidden="true"
          />
          <span className="truncate">{pill.label}</span>
        </span>
      )}
    </div>
  );
}

/** `RegentIdentity` fed by Regent's live status, for the app header. */
export function LiveRegentIdentity(): React.ReactElement {
  const { status, state } = useLiveRegent();
  return <RegentIdentity status={status} state={state} />;
}

/**
 * The crowned cube for the header's logo slot, shown on Regent's chat while
 * the sidebar, which otherwise carries it, is collapsed.
 */
export function LiveRegentLogo(): React.ReactElement {
  const { status, state } = useLiveRegent();
  const nod = useRegentNod(status);
  return (
    <span key={nod} className={`inline-flex ${nod > 0 ? 'regent-nod' : ''}`}>
      <RegentCube size={24} state={state} />
    </span>
  );
}

interface RegentLogoSlotProps {
  regent: boolean;
  /** The app's own logo, shown everywhere but Regent's chat. */
  children: React.ReactNode;
}

/**
 * The header's logo slot while the sidebar is collapsed: Regent's cube grows
 * in on its chat, and the app's logo springs back once you leave it.
 */
export function RegentLogoSlot({ regent, children }: RegentLogoSlotProps): React.ReactElement {
  const [wasRegent, setWasRegent] = useState(regent);
  const [returning, setReturning] = useState(false);
  if (wasRegent !== regent) {
    setWasRegent(regent);
    setReturning(!regent);
  }
  useEffect(() => {
    if (!returning) return;
    const timer = setTimeout(() => setReturning(false), 500);
    return () => clearTimeout(timer);
  }, [returning]);
  if (regent) {
    return (
      <span className="regent-logo-enter inline-flex">
        <LiveRegentLogo />
      </span>
    );
  }
  return <span className={`inline-flex ${returning ? 'regent-logo-return' : ''}`}>{children}</span>;
}
