import React, { useEffect, useState } from 'react';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import { RegentCube } from './regent/RegentCube';
import { RegentMark } from './regent/RegentMark';
import { regentState, useRegentNod } from './regent/regentState';
import { useI18n } from '../i18n';
import { useFocalStatus } from '../hooks/useFocalStatus';
import { FOCAL_CHAT_ID, type FocalAgentStatus } from '../lib/focalAgent';
import { hoverText } from '../lib/hoverText';

interface FocalAgentCardProps {
  active: boolean;
  onOpen: (chatId: string) => void;
  /** Leaves Regent; shown as a quiet back button on the open card. */
  onExit?: () => void;
  /** Set while another page fills the main area: the open card leads back to Regent's chat. */
  onReturn?: () => void;
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
  onExit,
  onReturn,
  nod = 0,
}: FocalAgentCardViewProps): React.ReactElement {
  const { t, locale } = useI18n();
  // Background check-ins, wake-ups and events land here as new messages, so the
  // card shows them instead of the sidebar listing Regent's schedule as tasks.
  const unread = Math.max(0, status?.unread ?? 0);
  const waiting = Math.max(0, status?.waiting ?? 0);
  const running = Math.max(0, status?.states?.running ?? 0);
  const working = Boolean(status?.running);
  const hasNews = unread > 0 && !active && Boolean(status?.lastMessage);
  const time = lastMessageTime(status?.lastMessageAt, locale, t('chatMessage.yesterday'));
  // Leaving Regent, however it happens, folds the profile back into its row.
  const [wasActive, setWasActive] = useState(active);
  const [retreating, setRetreating] = useState(false);
  if (wasActive !== active) {
    setWasActive(active);
    setRetreating(!active);
  }
  useEffect(() => {
    if (!retreating) return;
    const timer = setTimeout(() => setRetreating(false), 500);
    return () => clearTimeout(timer);
  }, [retreating]);

  const counts = [
    waiting > 0 ? t('chatList.focal.waitingCount', { count: waiting }) : null,
    running > 0 ? t('chatList.focal.runningCount', { count: running }) : null,
  ].filter(Boolean);
  const statusLine = hasNews
    ? status?.lastMessage
    : working
      ? [t('chatList.focal.working'), ...counts].join(' · ')
      : counts.length > 0
        ? counts.join(' · ')
        : t('chatList.focal.allClear');

  // Opening Regent turns its row into a profile: the flat mark grows into the
  // cube, and the sidebar turns into Regent's queue (see ChatList).
  if (active) {
    return (
      <section
        aria-current={onReturn ? undefined : 'page'}
        aria-label={t('chatList.focal.name')}
        className={`group/regent regent-card-hero relative w-full flex flex-col items-center gap-1 border-2 border-brutal-black bg-white px-3 pt-2 pb-3 text-center text-brutal-black dark:bg-zinc-800 dark:text-white ${onReturn ? 'hover:bg-neutral-50 dark:hover:bg-zinc-700/60' : ''}`}
      >
        {/* Above the animated cube and text, under the back button. */}
        {onReturn && (
          <button
            type="button"
            onClick={onReturn}
            aria-label={t('chatList.focal.open')}
            title={t('chatList.focal.open')}
            className="absolute inset-0 z-10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue"
          />
        )}
        {/* Always there so the way out is findable, but quiet until the card is hovered. */}
        {onExit && (
          <button
            type="button"
            onClick={onExit}
            aria-label={t('chatList.focal.exit')}
            title={`${t('chatList.focal.exit')} (Esc)`}
            className="absolute left-1 top-1 z-20 flex h-6 items-center gap-1 px-1 text-neutral-400 transition-colors hover:bg-neutral-100 hover:text-brutal-black group-hover/regent:text-neutral-600 focus-visible:text-brutal-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue dark:text-zinc-500 dark:hover:bg-zinc-700 dark:hover:text-white dark:group-hover/regent:text-neutral-300"
          >
            <ArrowLeftIcon className="h-3.5 w-3.5 shrink-0 stroke-2" aria-hidden="true" />
            <span className="max-w-0 overflow-hidden whitespace-nowrap text-[11px] font-bold opacity-0 transition-all duration-200 group-hover/regent:max-w-16 group-hover/regent:opacity-100 group-focus-within/regent:max-w-16 group-focus-within/regent:opacity-100">
              {t('chatList.focal.exitShort')}
            </span>
          </button>
        )}
        <span key={nod} className={`regent-hero-avatar mb-2 flex ${nod > 0 ? 'regent-nod' : ''}`}>
          <RegentCube size={56} state={regentState(status)} />
        </span>
        <span className="regent-hero-text flex items-baseline gap-1.5">
          <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
            {t('chatList.focal.brand')}
          </span>
          <span className="font-brutal text-xl font-black leading-none tracking-[-0.04em] [-webkit-text-stroke:0.75px_currentColor]">
            {t('chatList.focal.name')}
          </span>
        </span>
        <span className="regent-hero-text text-[11px] text-neutral-500 dark:text-neutral-400">
          {working ? t('chatList.focal.working') : t('chatList.focal.role')}
        </span>
        <span
          className={`regent-hero-text max-w-full truncate text-[11px] font-bold ${waiting > 0 ? 'text-brutal-black dark:text-white' : 'text-neutral-500 dark:text-neutral-400'}`}
          title={hoverText(statusLine)}
        >
          {counts.length > 0 ? counts.join(' · ') : t('chatList.focal.allClear')}
        </span>
      </section>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onOpen(status?.chatId ?? FOCAL_CHAT_ID)}
      aria-current={active ? 'page' : undefined}
      aria-label={t('chatList.focal.open')}
      className={`regent-crown-on-hover w-full px-2 py-2 min-h-9 flex items-center gap-2 text-left transition-colors text-brutal-black dark:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue ${active ? 'bg-neutral-200/70 dark:bg-zinc-700' : 'hover:bg-neutral-100 dark:hover:bg-zinc-700'}`}
    >
      {/* The mark itself shows Regent's state: scanning, a lit gem, or a nod. */}
      <span
        key={nod}
        className={`flex w-7 h-7 shrink-0 items-end justify-center ${retreating ? 'regent-row-mark-retreat' : nod > 0 ? 'regent-nod' : ''}`}
        aria-hidden="true"
      >
        <RegentMark size={26} state={regentState(status)} />
      </span>
      <span className={`min-w-0 flex-1 ${retreating ? 'regent-row-text-retreat' : ''}`}>
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
            title={hoverText(statusLine)}
          >
            {statusLine}
          </span>
          {hasNews && (
            <span className="inline-flex h-4 min-w-4 shrink-0 items-center justify-center rounded-[3px] bg-neutral-900 px-1 text-[9px] font-extrabold tabular-nums text-white dark:bg-neutral-100 dark:text-neutral-900">
              {unread > 99 ? '99+' : unread}
            </span>
          )}
        </span>
      </span>
    </button>
  );
}
