import React, { useCallback, useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import type { KanbanData } from '../../hooks/useGoalTasks';
import { useFocalStatus } from '../../hooks/useFocalStatus';
import { fetchFocalPanel, type FocalAgentStatus, type FocalWakeup } from '../../lib/focalAgent';
import { buildSessions, sessionGroupKey, type SessionCard } from '../../lib/sessionGroups';
import { RegentCube } from './RegentCube';
import { regentState } from './regentState';

const WAKEUP_POLL_MS = 30_000;

interface RegentPanelViewProps {
  status: FocalAgentStatus | null;
  kanban: KanbanData | null;
  wakeups: FocalWakeup[] | null;
  onOpenChat: (chatId: string) => void;
  /** The full all-projects board, shown in place of the cards on request. */
  board: React.ReactNode;
}

/**
 * Regent's side panel: a stack of cards for what it watches, read top to
 * bottom like a status page. The full board stays one click away.
 */
export function RegentPanel(
  props: Omit<RegentPanelViewProps, 'status' | 'wakeups'>
): React.ReactElement {
  const status = useFocalStatus();
  const [wakeups, setWakeups] = useState<FocalWakeup[] | null>(null);
  const refresh = useCallback(async (): Promise<void> => {
    try {
      setWakeups((await fetchFocalPanel()).wakeups);
    } catch {
      // The other cards still work without the schedule.
    }
  }, []);
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), WAKEUP_POLL_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);
  return <RegentPanelView {...props} status={status} wakeups={wakeups} />;
}

export function RegentPanelView({
  status,
  kanban,
  wakeups,
  onOpenChat,
  board,
}: RegentPanelViewProps): React.ReactElement {
  const { t } = useI18n();
  const [showBoard, setShowBoard] = useState(false);

  if (showBoard) {
    return (
      <div className="flex h-full min-h-0 flex-col">
        <button
          type="button"
          onClick={() => setShowBoard(false)}
          className="shrink-0 border-b-2 border-brutal-black px-3 py-2 text-left font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500 hover:text-brutal-black dark:text-neutral-400 dark:hover:text-white"
        >
          {t('regentPanel.overview')}
        </button>
        <div className="min-h-0 flex-1">{board}</div>
      </div>
    );
  }

  const state = regentState(status);
  const sessions = kanban ? buildSessions(kanban.tasks, {}) : [];
  const group = (key: ReturnType<typeof sessionGroupKey>): SessionCard[] =>
    sessions.filter((session) => sessionGroupKey(session) === key);
  const needsYou = group('attention');
  const running = group('active');
  const stalled = group('stalled');
  const allClear = needsYou.length === 0 && stalled.length === 0;

  return (
    <div className="regent-panel flex h-full min-h-0 flex-col gap-3 overflow-y-auto scrollbar-thin bg-neutral-50 p-3 text-brutal-black dark:bg-zinc-900 dark:text-white">
      <section className="flex items-center gap-3 border-2 border-brutal-black bg-white px-3 py-3 shadow-brutal-sm dark:bg-zinc-800">
        <RegentCube size={52} state={state} />
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
              {t('chatList.focal.brand')}
            </span>
            <span className="font-brutal text-xl font-black leading-none tracking-[-0.04em] [-webkit-text-stroke:0.75px_currentColor]">
              {t('chatList.focal.name')}
            </span>
          </div>
          <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {state === 'working' ? t('chatList.focal.working') : t('chatList.focal.role')}
          </p>
          <p className="mt-0.5 text-xs font-bold">
            {allClear
              ? t('chatList.focal.allClear')
              : [
                  needsYou.length > 0
                    ? t('chatList.focal.waitingCount', { count: needsYou.length })
                    : null,
                  stalled.length > 0
                    ? t('chatList.focal.stalledCount', { count: stalled.length })
                    : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
          </p>
        </div>
      </section>

      <SessionCardGroup
        title={t('regentPanel.needsYou')}
        tone="attention"
        sessions={needsYou}
        onOpenChat={onOpenChat}
      />
      <SessionCardGroup
        title={t('regentPanel.running')}
        tone="running"
        sessions={running}
        onOpenChat={onOpenChat}
      />
      <SessionCardGroup
        title={t('regentPanel.stalled')}
        tone="stalled"
        sessions={stalled}
        onOpenChat={onOpenChat}
      />

      <PanelCard title={t('regentPanel.wakeups')} count={wakeups?.length ?? 0}>
        {wakeups && wakeups.length > 0 ? (
          <ul className="divide-y divide-neutral-200 dark:divide-zinc-700">
            {wakeups.map((wakeup) => (
              <li key={wakeup.id} className="flex items-center gap-2 px-3 py-2 text-xs">
                <span
                  className={`shrink-0 border border-brutal-black px-1 font-mono text-[9px] font-bold uppercase ${wakeup.kind === 'reminder' ? 'bg-brutal-yellow text-brutal-black' : 'bg-white text-brutal-black dark:bg-zinc-700 dark:text-white'}`}
                >
                  {t(`focalTools.${wakeup.kind}`)}
                </span>
                <span className="min-w-0 flex-1 truncate font-bold" title={wakeup.name}>
                  {wakeup.name}
                </span>
                <span className="shrink-0 font-mono text-[10px] text-neutral-500 dark:text-neutral-400">
                  {wakeup.nextRunAt ? formatTime(wakeup.nextRunAt) : wakeup.schedule}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-3 py-2 text-xs text-neutral-500 dark:text-neutral-400">
            {t('focalTools.noWakeups')}
          </p>
        )}
      </PanelCard>

      <button
        type="button"
        onClick={() => setShowBoard(true)}
        className="self-start font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500 hover:text-brutal-black dark:text-neutral-400 dark:hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue"
      >
        {t('regentPanel.fullBoard')}
      </button>
    </div>
  );
}

function formatTime(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  const sameDay = at.toDateString() === new Date().toDateString();
  return sameDay
    ? at.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : at.toLocaleDateString([], { month: 'numeric', day: 'numeric' });
}

function PanelCard({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <details
      open
      className="group border-2 border-brutal-black bg-white shadow-brutal-sm dark:bg-zinc-800"
    >
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue [&::-webkit-details-marker]:hidden">
        <span className="text-xs font-extrabold">{title}</span>
        <span
          aria-hidden="true"
          className="text-neutral-400 transition-transform group-open:rotate-90"
        >
          ›
        </span>
        <span className="ml-auto font-mono text-[10px] font-bold text-neutral-500 dark:text-neutral-400">
          {count}
        </span>
      </summary>
      <div className="border-t-2 border-brutal-black">{children}</div>
    </details>
  );
}

function SessionCardGroup({
  title,
  tone,
  sessions,
  onOpenChat,
}: {
  title: string;
  tone: 'attention' | 'running' | 'stalled';
  sessions: SessionCard[];
  onOpenChat: (chatId: string) => void;
}): React.ReactElement | null {
  const { t } = useI18n();
  if (sessions.length === 0) return null;
  const dot =
    tone === 'attention'
      ? 'bg-brutal-yellow'
      : tone === 'running'
        ? 'bg-brutal-blue animate-pulse'
        : 'bg-neutral-400';
  return (
    <PanelCard title={title} count={sessions.length}>
      <ul className="divide-y divide-neutral-200 dark:divide-zinc-700">
        {sessions.map((session) => {
          const label = session.title || t('taskFlow.unassignedSession');
          const detail = session.blocker?.waitingReason;
          const body = (
            <>
              <span
                className={`mt-1 h-2 w-2 shrink-0 border border-brutal-black ${dot}`}
                aria-hidden="true"
              />
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline gap-1.5">
                  <span className="truncate text-xs font-bold">{label}</span>
                  {session.projectLabel && (
                    <span className="shrink-0 font-mono text-[10px] text-neutral-500 dark:text-neutral-400">
                      {session.projectLabel}
                    </span>
                  )}
                </span>
                {detail && (
                  <span className="mt-0.5 block text-[11px] leading-snug text-neutral-600 dark:text-neutral-300">
                    {detail}
                  </span>
                )}
              </span>
            </>
          );
          return (
            <li key={session.key}>
              {session.chatId ? (
                <button
                  type="button"
                  onClick={() => onOpenChat(session.chatId!)}
                  className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-neutral-50 dark:hover:bg-zinc-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue"
                >
                  {body}
                  <span aria-hidden="true" className="text-neutral-400">
                    ›
                  </span>
                </button>
              ) : (
                <div className="flex items-start gap-2 px-3 py-2">{body}</div>
              )}
            </li>
          );
        })}
      </ul>
    </PanelCard>
  );
}
