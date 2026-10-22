import React from 'react';
import { useI18n } from '../../i18n';
import type { KanbanData } from '../../hooks/useGoalTasks';
import type { FocalAgentStatus } from '../../lib/focalAgent';
import { buildSessions, sessionGroupKey, type SessionCard } from '../../lib/sessionGroups';
import { RegentCube } from './RegentCube';
import { regentState, useRegentNod } from './regentState';
import { useFocalStatus } from '../../hooks/useFocalStatus';

const MAX_CHIPS = 4;

interface RegentIdentityProps {
  status: FocalAgentStatus | null;
  /** Bumped when Regent has something new to say; replays the cube's nod. */
  nod?: number;
}

/**
 * Who the conversation is with, read like a contact in a messaging app: the
 * crowned cube, "SUZENT Regent" and what it is doing. Lives in the app header
 * on Regent's chat, in place of a chat title.
 */
export function RegentIdentity({ status, nod = 0 }: RegentIdentityProps): React.ReactElement {
  const { t } = useI18n();
  const state = regentState(status);
  const waitingCount = Math.max(0, status?.waiting ?? 0);
  const stalledCount = Math.max(0, status?.stalled ?? 0);
  const counts = [
    waitingCount > 0 ? t('chatList.focal.waitingCount', { count: waitingCount }) : null,
    stalledCount > 0 ? t('chatList.focal.stalledCount', { count: stalledCount }) : null,
  ].filter(Boolean);
  const presence =
    state === 'working'
      ? t('chatList.focal.working')
      : counts.length > 0
        ? counts.join(' · ')
        : t('chatList.focal.role');

  return (
    <div className="regent-identity flex min-w-0 items-center gap-2.5">
      <span key={nod} className={nod > 0 ? 'regent-nod inline-flex' : 'inline-flex'}>
        <RegentCube size={38} state={state} />
      </span>
      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="shrink-0 font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
            {t('chatList.focal.brand')}
          </span>
          <span className="shrink-0 font-brutal text-2xl font-black leading-none tracking-[-0.04em] [-webkit-text-stroke:0.75px_currentColor] text-brutal-black dark:text-white">
            {t('chatList.focal.name')}
          </span>
        </div>
        <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-neutral-500 dark:text-neutral-400">
          <span
            className={`h-2 w-2 shrink-0 border border-brutal-black ${state === 'working' ? 'bg-brutal-blue animate-pulse' : state === 'waiting' ? 'bg-brutal-yellow' : 'bg-emerald-500'}`}
            aria-hidden="true"
          />
          <span className="truncate">{presence}</span>
        </p>
      </div>
    </div>
  );
}

/** `RegentIdentity` fed by Regent's live status, for the app header. */
export function LiveRegentIdentity(): React.ReactElement {
  const status = useFocalStatus();
  return <RegentIdentity status={status} nod={useRegentNod(status)} />;
}

interface RegentPinnedProps {
  kanban: KanbanData | null;
  onOpenChat: (chatId: string) => void;
}

/**
 * The board, pinned under the header like a pinned message: what waits on the
 * user, then what has stalled, each opening its session.
 */
export function RegentPinned({ kanban, onOpenChat }: RegentPinnedProps): React.ReactElement {
  const { t } = useI18n();
  const sessions = kanban ? buildSessions(kanban.tasks, {}) : [];
  const shown = [
    ...sessions
      .filter((session) => sessionGroupKey(session) === 'attention')
      .map((session) => ({ session, kind: 'waiting' as const })),
    ...sessions
      .filter((session) => sessionGroupKey(session) === 'stalled')
      .map((session) => ({ session, kind: 'stalled' as const })),
  ];

  return (
    <div className="regent-pinned flex min-h-9 shrink-0 items-center gap-2 overflow-x-auto whitespace-nowrap scrollbar-thin border-b-2 border-brutal-black bg-neutral-100 px-4 md:px-6 py-1.5 text-xs text-brutal-black dark:bg-zinc-900 dark:text-white">
      {shown.length === 0 ? (
        <span className="text-neutral-500 dark:text-neutral-400">
          {t('chatList.focal.allClear')}
        </span>
      ) : (
        <>
          {shown.slice(0, MAX_CHIPS).map(({ session, kind }) => (
            <PinnedChip key={session.key} session={session} kind={kind} onOpenChat={onOpenChat} />
          ))}
          {shown.length > MAX_CHIPS && (
            <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
              {t('chatList.focal.moreCount', { count: shown.length - MAX_CHIPS })}
            </span>
          )}
        </>
      )}
    </div>
  );
}

function PinnedChip({
  session,
  kind,
  onOpenChat,
}: {
  session: SessionCard;
  kind: 'waiting' | 'stalled';
  onOpenChat: (chatId: string) => void;
}): React.ReactElement {
  const { t } = useI18n();
  const label = session.title || t('taskFlow.unassignedSession');
  const reason = session.blocker?.waitingReason;
  const tag = (
    <span
      className={`shrink-0 px-1 font-mono text-[10px] font-bold uppercase tracking-wider ${kind === 'waiting' ? 'border border-brutal-black bg-brutal-yellow text-brutal-black' : 'bg-brutal-black text-white dark:bg-white dark:text-brutal-black'}`}
    >
      {kind === 'waiting' ? t('chatList.focal.pinnedWaiting') : t('chatList.focal.pinnedStalled')}
    </span>
  );
  const body = (
    <>
      {tag}
      {session.projectLabel && (
        <span className="shrink-0 font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
          {session.projectLabel}
        </span>
      )}
      <span className="min-w-0 truncate">{reason || label}</span>
    </>
  );
  const className =
    'inline-flex max-w-[22rem] items-center gap-1.5 border-2 border-brutal-black bg-white px-2 py-0.5 shadow-brutal-sm dark:bg-zinc-800';
  return session.chatId ? (
    <button
      type="button"
      className={`${className} hover:bg-neutral-50 dark:hover:bg-zinc-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue`}
      title={reason ? `${label}: ${reason}` : label}
      onClick={() => onOpenChat(session.chatId!)}
    >
      {body}
    </button>
  ) : (
    <span className={className} title={label}>
      {body}
    </span>
  );
}
