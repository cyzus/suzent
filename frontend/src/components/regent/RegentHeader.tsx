import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useI18n } from '../../i18n';
import { useFocalStatus } from '../../hooks/useFocalStatus';
import { useChatStreamingStore } from '../../hooks/useChatStore';
import type { KanbanData } from '../../hooks/useGoalTasks';
import {
  FOCAL_CHAT_ID,
  fetchFocalPanel,
  type FocalAgentStatus,
  type FocalWakeup,
} from '../../lib/focalAgent';
import { buildSessions, sessionGroupKey, type SessionCard } from '../../lib/sessionGroups';
import { RegentCube } from './RegentCube';
import type { RegentState } from './RegentMark';
import { regentState, useRegentNod } from './regentState';

const CUBE_SIZE = 50;
// Room the cube takes beside the name; it hangs below the icon row into the
// details row, so the header row keeps its height and its icons stay put.
const CUBE_SLOT = 64;
const MAX_ITEMS = 3;
const WAKEUP_POLL_MS = 30_000;

/** Regent's status, also treating a reply streaming in this chat as working. */
function useLiveRegent(): { status: FocalAgentStatus | null; state: RegentState } {
  const status = useFocalStatus();
  const { isStreaming, activeStreamingChatId } = useChatStreamingStore();
  const working = isStreaming && activeStreamingChatId === FOCAL_CHAT_ID;
  return { status, state: working ? 'working' : regentState(status) };
}

interface RegentIdentityProps {
  state: RegentState;
  /** Bumped when Regent has something new to say; replays the cube's nod. */
  nod?: number;
}

/**
 * The title of Regent's header: the crowned cube beside "SUZENT Regent". The
 * cube is larger than the icon row and hangs into `RegentHeaderDetails`
 * below it, so the row itself keeps the app header's height.
 */
export function RegentIdentity({ state, nod = 0 }: RegentIdentityProps): React.ReactElement {
  const { t } = useI18n();
  return (
    <div className="regent-identity relative flex min-w-0 items-baseline gap-2">
      <span
        key={nod}
        className={`absolute left-0 ${nod > 0 ? 'regent-nod' : ''}`}
        style={{ top: -12 }}
        aria-hidden="true"
      >
        <RegentCube size={CUBE_SIZE} state={state} />
      </span>
      <span style={{ width: CUBE_SLOT }} className="shrink-0" aria-hidden="true" />
      <span className="regent-identity-name shrink-0 font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
        {t('chatList.focal.brand')}
      </span>
      <span className="shrink-0 font-brutal text-2xl font-black leading-none tracking-[-0.04em] [-webkit-text-stroke:0.75px_currentColor] text-brutal-black dark:text-white">
        {t('chatList.focal.name')}
      </span>
    </div>
  );
}

/** `RegentIdentity` fed by Regent's live status, for the app header. */
export function LiveRegentIdentity(): React.ReactElement {
  const { status, state } = useLiveRegent();
  return <RegentIdentity state={state} nod={useRegentNod(status)} />;
}

interface RegentHeaderDetailsViewProps {
  state: RegentState;
  kanban: KanbanData | null;
  wakeups: FocalWakeup[] | null;
  onOpenChat: (chatId: string) => void;
  /** Opens the full board; omitted while it is already showing. */
  onOpenBoard?: () => void;
  /** Px from this row's left edge to where Regent's name starts above it. */
  inset?: number;
}

/**
 * The lower half of Regent's header, under the untouched icon row: what Regent
 * is doing, what waits on the user and what has stalled (each opening its
 * session), how many wake-ups it has set, and the board one click away.
 */
export function RegentHeaderDetailsView({
  state,
  kanban,
  wakeups,
  onOpenChat,
  onOpenBoard,
  inset,
}: RegentHeaderDetailsViewProps): React.ReactElement {
  const { t } = useI18n();
  const sessions = kanban ? buildSessions(kanban.tasks, {}) : [];
  const items = [
    ...sessions
      .filter((session) => sessionGroupKey(session) === 'attention')
      .map((session) => ({ session, kind: 'waiting' as const })),
    ...sessions
      .filter((session) => sessionGroupKey(session) === 'stalled')
      .map((session) => ({ session, kind: 'stalled' as const })),
  ];
  const wakeupCount = wakeups?.length ?? 0;

  return (
    <div
      className="regent-header-details relative flex min-h-10 shrink-0 items-center gap-3 overflow-hidden border-b-3 border-brutal-black bg-brutal-white px-4 md:px-6 pb-2 text-xs text-brutal-black dark:bg-zinc-800 dark:text-white"
      style={inset === undefined ? undefined : { paddingLeft: inset }}
    >
      <span className="shrink-0 text-neutral-500 dark:text-neutral-400">
        {state === 'working' ? t('chatList.focal.working') : t('chatList.focal.role')}
      </span>
      <span className="flex min-w-0 flex-1 items-center gap-2 overflow-hidden">
        {items.length === 0 ? (
          <span className="shrink-0 font-bold">{t('chatList.focal.allClear')}</span>
        ) : (
          items
            .slice(0, MAX_ITEMS)
            .map(({ session, kind }) => (
              <HeaderItem key={session.key} session={session} kind={kind} onOpenChat={onOpenChat} />
            ))
        )}
        {items.length > MAX_ITEMS && (
          <span className="shrink-0 font-mono text-[10px] font-bold text-neutral-500 dark:text-neutral-400">
            +{items.length - MAX_ITEMS}
          </span>
        )}
      </span>
      {wakeupCount > 0 && (
        <span className="shrink-0 font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
          {t('regentHeader.wakeups', { count: wakeupCount })}
        </span>
      )}
      {onOpenBoard && (
        <button
          type="button"
          onClick={onOpenBoard}
          className="shrink-0 font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500 hover:text-brutal-black dark:text-neutral-400 dark:hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue"
        >
          {t('regentHeader.board')}
        </button>
      )}
    </div>
  );
}

function HeaderItem({
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
  const body = (
    <>
      <span
        className={`shrink-0 px-1 font-mono text-[9px] font-bold uppercase tracking-wider ${kind === 'waiting' ? 'border border-brutal-black bg-brutal-yellow text-brutal-black' : 'bg-brutal-black text-white dark:bg-white dark:text-brutal-black'}`}
      >
        {kind === 'waiting' ? t('regentHeader.needsYou') : t('regentHeader.stalled')}
      </span>
      <span className="min-w-0 truncate">{reason || label}</span>
    </>
  );
  const className = 'flex min-w-0 max-w-[18rem] items-center gap-1.5';
  return session.chatId ? (
    <button
      type="button"
      className={`${className} hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue`}
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

interface RegentHeaderDetailsProps {
  kanban: KanbanData | null;
  onOpenChat: (chatId: string) => void;
  onOpenBoard?: () => void;
}

/** `RegentHeaderDetailsView` fed live and lined up under Regent's name. */
export function RegentHeaderDetails(props: RegentHeaderDetailsProps): React.ReactElement {
  const { state } = useLiveRegent();
  const [wakeups, setWakeups] = useState<FocalWakeup[] | null>(null);
  const [inset, setInset] = useState<number | undefined>(undefined);
  const row = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async (): Promise<void> => {
    try {
      setWakeups((await fetchFocalPanel()).wakeups);
    } catch {
      // The rest of the header works without the schedule.
    }
  }, []);
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), WAKEUP_POLL_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  // The name's position depends on what sits before it in the icon row (the
  // sidebar trigger, window controls), so measure it rather than guess.
  const measure = useCallback((): void => {
    const name = document.querySelector('.app-header .regent-identity-name');
    const self = row.current;
    if (!name || !self) return;
    const next = Math.round(name.getBoundingClientRect().left - self.getBoundingClientRect().left);
    setInset((current) => (current === next ? current : next));
  }, []);
  useLayoutEffect(measure);
  useEffect(() => {
    // The main column resizes whenever the side panels open or close.
    const main = row.current?.closest('.app-main');
    if (!main) return;
    const observer = new ResizeObserver(measure);
    observer.observe(main);
    return () => observer.disconnect();
  }, [measure]);

  return (
    <div ref={row}>
      <RegentHeaderDetailsView {...props} state={state} wakeups={wakeups} inset={inset} />
    </div>
  );
}
