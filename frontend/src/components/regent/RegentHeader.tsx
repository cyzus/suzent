import React from 'react';
import { useI18n } from '../../i18n';
import type { KanbanData } from '../../hooks/useGoalTasks';
import { useFocalStatus } from '../../hooks/useFocalStatus';
import { useChatStreamingStore } from '../../hooks/useChatStore';
import { FOCAL_CHAT_ID, type FocalAgentStatus } from '../../lib/focalAgent';
import { buildSessions, sessionGroupKey, type SessionCard } from '../../lib/sessionGroups';
import { RegentCube } from './RegentCube';
import { regentState, useRegentNod } from './regentState';

interface RegentIdentityProps {
  status: FocalAgentStatus | null;
  /** Regent is answering in this chat right now, ahead of the next status poll. */
  working?: boolean;
  /** Bumped when Regent has something new to say; replays the cube's nod. */
  nod?: number;
}

/**
 * Who the conversation is with, read like a contact in a messaging app: the
 * crowned cube, "SUZENT Regent" and what it is doing. Lives in the app header
 * on Regent's chat, in place of a chat title. Counts are left to the pinned bar.
 */
export function RegentIdentity({
  status,
  working = false,
  nod = 0,
}: RegentIdentityProps): React.ReactElement {
  const { t } = useI18n();
  const state = working ? 'working' : regentState(status);

  return (
    <div className="regent-identity flex min-w-0 items-center gap-2.5">
      <span key={nod} className={nod > 0 ? 'regent-nod inline-flex' : 'inline-flex'}>
        <RegentCube size={34} state={state} />
      </span>
      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="shrink-0 font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
            {t('chatList.focal.brand')}
          </span>
          <span className="shrink-0 font-brutal text-xl font-black leading-none tracking-[-0.04em] [-webkit-text-stroke:0.75px_currentColor] text-brutal-black dark:text-white">
            {t('chatList.focal.name')}
          </span>
        </div>
        <p className="mt-0.5 truncate text-[11px] leading-tight text-neutral-500 dark:text-neutral-400">
          {state === 'working' ? t('chatList.focal.working') : t('chatList.focal.role')}
        </p>
      </div>
    </div>
  );
}

/** `RegentIdentity` fed by Regent's live status, for the app header. */
export function LiveRegentIdentity(): React.ReactElement {
  const status = useFocalStatus();
  const { isStreaming, activeStreamingChatId } = useChatStreamingStore();
  return (
    <RegentIdentity
      status={status}
      working={isStreaming && activeStreamingChatId === FOCAL_CHAT_ID}
      nod={useRegentNod(status)}
    />
  );
}

interface RegentPinnedProps {
  kanban: KanbanData | null;
  onOpenChat: (chatId: string) => void;
  /** Opens the full board; omitted while it is already showing. */
  onOpenBoard?: () => void;
}

/**
 * One slim line under the header, like a pinned message: how much waits on the
 * user and the most pressing item, with the full board a click away. Nothing
 * waiting means no bar at all.
 */
export function RegentPinned({
  kanban,
  onOpenChat,
  onOpenBoard,
}: RegentPinnedProps): React.ReactElement | null {
  const { t } = useI18n();
  const sessions = kanban ? buildSessions(kanban.tasks, {}) : [];
  const waiting = sessions.filter((session) => sessionGroupKey(session) === 'attention');
  const stalled = sessions.filter((session) => sessionGroupKey(session) === 'stalled');
  const top = waiting[0] ?? stalled[0];
  if (!top) return null;

  const counts = [
    waiting.length > 0 ? t('chatList.focal.waitingCount', { count: waiting.length }) : null,
    stalled.length > 0 ? t('chatList.focal.stalledCount', { count: stalled.length }) : null,
  ].filter(Boolean);

  return (
    <div className="regent-pinned flex h-8 shrink-0 items-center gap-3 border-b-2 border-brutal-black bg-white px-4 md:px-6 text-xs text-brutal-black dark:bg-zinc-800 dark:text-white">
      <span
        className={`h-2 w-2 shrink-0 border border-brutal-black ${waiting.length > 0 ? 'bg-brutal-yellow' : 'bg-neutral-400'}`}
        aria-hidden="true"
      />
      <span className="shrink-0 font-mono text-[10px] font-bold uppercase tracking-wider">
        {counts.join(' · ')}
      </span>
      <PinnedItem session={top} onOpenChat={onOpenChat} />
      {onOpenBoard && (
        <button
          type="button"
          onClick={onOpenBoard}
          className="ml-auto shrink-0 font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500 hover:text-brutal-black dark:text-neutral-400 dark:hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue"
        >
          {t('chatList.focal.openBoard')}
        </button>
      )}
    </div>
  );
}

function PinnedItem({
  session,
  onOpenChat,
}: {
  session: SessionCard;
  onOpenChat: (chatId: string) => void;
}): React.ReactElement {
  const { t } = useI18n();
  const label = session.title || t('taskFlow.unassignedSession');
  const text = session.blocker?.waitingReason || label;
  const body = (
    <>
      {session.projectLabel && (
        <span className="shrink-0 text-neutral-500 dark:text-neutral-400">
          {session.projectLabel}
        </span>
      )}
      <span className="min-w-0 truncate">{text}</span>
    </>
  );
  return session.chatId ? (
    <button
      type="button"
      className="flex min-w-0 items-center gap-1.5 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue"
      title={text === label ? label : `${label}: ${text}`}
      onClick={() => onOpenChat(session.chatId!)}
    >
      {body}
      <span aria-hidden="true">›</span>
    </button>
  ) : (
    <span className="flex min-w-0 items-center gap-1.5" title={label}>
      {body}
    </span>
  );
}
