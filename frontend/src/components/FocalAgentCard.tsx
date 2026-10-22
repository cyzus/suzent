import React from 'react';
import { RegentMark } from './regent/RegentMark';
import { regentState, useRegentNod } from './regent/regentState';
import { useI18n } from '../i18n';
import { useFocalStatus } from '../hooks/useFocalStatus';
import { FOCAL_CHAT_ID, type FocalAgentStatus } from '../lib/focalAgent';

interface FocalAgentCardProps {
  active: boolean;
  onOpen: (chatId: string) => void;
}

export function FocalAgentCard({ active, onOpen }: FocalAgentCardProps): React.ReactElement {
  const status = useFocalStatus();
  return (
    <FocalAgentCardView
      status={status}
      active={active}
      onOpen={onOpen}
      nod={useRegentNod(status)}
    />
  );
}

interface FocalAgentCardViewProps extends FocalAgentCardProps {
  status: FocalAgentStatus | null;
  /** Bumped when Regent has something new to say; replays the mark's nod. */
  nod?: number;
}

/** "14:05" today, "Yesterday" for yesterday, a short date before that. */
function lastMessageTime(
  iso: string | null | undefined,
  locale: string,
  yesterday: string,
  now = new Date()
): string | null {
  if (!iso) return null;
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return null;
  const day = (date: Date): number =>
    new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const daysAgo = Math.round((day(now) - day(at)) / 86_400_000);
  if (daysAgo <= 0) return at.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
  if (daysAgo === 1) return yesterday;
  return at.toLocaleDateString(locale, { month: 'numeric', day: 'numeric' });
}

export function FocalAgentCardView({
  status,
  active,
  onOpen,
  nod = 0,
}: FocalAgentCardViewProps): React.ReactElement {
  const { t, locale } = useI18n();
  // Background check-ins, wake-ups and events land here as new messages, so the
  // card shows them instead of the sidebar listing Regent's schedule as tasks.
  const unread = Math.max(0, status?.unread ?? 0);
  const waiting = Math.max(0, status?.waiting ?? 0);
  const stalled = Math.max(0, status?.stalled ?? 0);
  const autoRun = Math.max(0, status?.autoRun ?? 0);
  const working = Boolean(status?.running);
  const hasNews = unread > 0 && !active && Boolean(status?.lastMessage);
  const time = lastMessageTime(status?.lastMessageAt, locale, t('chatMessage.yesterday'));

  const counts = [
    waiting > 0 ? t('chatList.focal.waitingCount', { count: waiting }) : null,
    stalled > 0 ? t('chatList.focal.stalledCount', { count: stalled }) : null,
    autoRun > 0 ? t('chatList.focal.autoRunCount', { count: autoRun }) : null,
  ].filter(Boolean);
  const statusLine = hasNews
    ? status?.lastMessage
    : working
      ? [t('chatList.focal.working'), ...counts].join(' · ')
      : counts.length > 0
        ? counts.join(' · ')
        : t('chatList.focal.allClear');

  return (
    <button
      type="button"
      onClick={() => onOpen(status?.chatId ?? FOCAL_CHAT_ID)}
      aria-current={active ? 'page' : undefined}
      aria-label={t('chatList.focal.open')}
      className={`w-full px-2 py-2 min-h-9 flex items-center gap-2 text-left transition-colors text-brutal-black dark:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue ${active ? 'bg-neutral-200/70 dark:bg-zinc-700' : 'hover:bg-neutral-100 dark:hover:bg-zinc-700'}`}
    >
      {/* The mark itself shows Regent's state: scanning, a lit gem, or a nod. */}
      <span
        key={nod}
        className={`flex w-7 h-7 shrink-0 items-end justify-center ${nod > 0 ? 'regent-nod' : ''}`}
        aria-hidden="true"
      >
        <RegentMark size={24} state={regentState(status)} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline gap-1.5 min-w-0">
          <span className="font-mono text-xs font-bold tracking-wide shrink-0">
            {t('chatList.focal.name')}
          </span>
          {hasNews && time && (
            <span className="ml-auto shrink-0 text-[10px] tabular-nums text-neutral-400 dark:text-neutral-500">
              {time}
            </span>
          )}
        </span>
        <span className="mt-0.5 flex items-center gap-2 min-w-0">
          <span
            className={`min-w-0 flex-1 truncate text-[11px] ${hasNews || waiting > 0 ? 'text-brutal-black dark:text-white' : 'text-neutral-500 dark:text-neutral-400'}`}
            title={statusLine ?? undefined}
          >
            {statusLine}
          </span>
          {hasNews ? (
            <span className="inline-flex h-4 min-w-4 shrink-0 items-center justify-center rounded-[3px] bg-neutral-900 px-1 text-[9px] font-extrabold tabular-nums text-white dark:bg-neutral-100 dark:text-neutral-900">
              {unread > 99 ? '99+' : unread}
            </span>
          ) : (
            waiting > 0 && (
              <span
                className="inline-flex h-4 min-w-4 shrink-0 items-center justify-center rounded-[3px] bg-brutal-yellow px-1 text-[9px] font-extrabold tabular-nums text-brutal-black"
                title={t('chatList.focal.waitingBadge', { count: waiting })}
              >
                {waiting}
              </span>
            )
          )}
        </span>
      </span>
    </button>
  );
}
