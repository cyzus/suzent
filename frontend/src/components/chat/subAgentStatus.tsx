/**
 * One source of truth for how a sub-agent's state looks and reads.
 *
 * The transcript block, the sidebar list and the sidebar detail panel all show
 * the same four-or-five states. They used to each invent their own emoji and
 * their own pastel badge, so the same task looked like three different things
 * depending on where you saw it — and a failed run drew an ✕ right next to the
 * panel's ✕ close button, which read as two ways to dismiss the same thing.
 *
 * Everything here matches the tool-call pills: mono, uppercase, 2px border.
 */
import React from 'react';
import {
  CheckIcon,
  ClockIcon,
  CpuChipIcon,
  ExclamationTriangleIcon,
  NoSymbolIcon,
} from '@heroicons/react/24/outline';

export type SubAgentStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

type TranslateFn = (key: string, params?: Record<string, unknown>) => string;

/** Stopped on purpose — by you, by orphan cleanup, or by a server shutdown. */
export function isSubAgentTerminal(status: string | undefined): boolean {
  return status === 'completed' || status === 'failed' || status === 'cancelled';
}

export function isSubAgentActive(status: string | undefined): boolean {
  return status === 'running' || status === 'queued';
}

interface StatusStyle {
  /** Chip colours, shared by every surface. */
  badge: string;
  icon: React.ComponentType<{ className?: string }>;
  iconTone: string;
}

const STYLES: Record<SubAgentStatus, StatusStyle> = {
  queued: {
    badge: 'bg-white dark:bg-zinc-900 text-neutral-500 dark:text-neutral-400 border-neutral-400 dark:border-zinc-500',
    icon: ClockIcon,
    iconTone: 'text-neutral-400',
  },
  running: {
    badge: 'bg-brutal-yellow text-brutal-black border-brutal-black',
    icon: CpuChipIcon,
    iconTone: 'text-brutal-black dark:text-white',
  },
  completed: {
    badge: 'bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300 border-green-600',
    icon: CheckIcon,
    iconTone: 'text-green-600 dark:text-green-400',
  },
  failed: {
    badge: 'bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-300 border-red-600',
    // A warning triangle, never a cross: the cross in these panels closes them.
    icon: ExclamationTriangleIcon,
    iconTone: 'text-red-600 dark:text-red-400',
  },
  cancelled: {
    badge: 'bg-neutral-100 dark:bg-zinc-800 text-neutral-600 dark:text-neutral-300 border-neutral-500 dark:border-zinc-500',
    icon: NoSymbolIcon,
    iconTone: 'text-neutral-500 dark:text-neutral-400',
  },
};

function styleFor(status: string | undefined): StatusStyle {
  return STYLES[(status ?? 'queued') as SubAgentStatus] ?? STYLES.queued;
}

/**
 * Whether a streamed status should give way to one from a fetch or poll.
 *
 * The EventSource can drop while a run is still going. It leaves behind the
 * last state it saw — "running" — and the fetch that follows is the only thing
 * that knows the run has since ended. Overlaying the stream on top of that
 * would pin the card to "running" for good, so a finished answer from anywhere
 * beats an unfinished one from the stream.
 */
export function isStreamStateStale(
  streamStatus: string | undefined,
  fetchedStatus: string | undefined,
): boolean {
  return !isSubAgentTerminal(streamStatus) && isSubAgentTerminal(fetchedStatus);
}

export function subAgentStatusLabel(status: string | undefined, t: TranslateFn): string {
  const known = STYLES[(status ?? '') as SubAgentStatus] ? (status as SubAgentStatus) : null;
  return known ? t(`subAgents.status.${known}`) : (status ?? '');
}

/**
 * The heading used for whatever a terminal run left behind — a result, an
 * explanation of the stop, or an error.
 */
export function subAgentOutcomeLabel(status: string | undefined, t: TranslateFn): string {
  if (status === 'cancelled') return t('subAgents.stoppedBecause');
  if (status === 'failed') return t('subAgents.error');
  return t('subAgents.result');
}

export const SubAgentStatusIcon: React.FC<{ status: string | undefined; className?: string }> = ({
  status,
  className = 'w-3.5 h-3.5',
}) => {
  const style = styleFor(status);
  const Icon = style.icon;
  return <Icon className={`${className} ${style.iconTone} stroke-[2.25] shrink-0`} aria-hidden="true" />;
};

/** The uppercase state chip: `⏱ RUNNING`, `DONE`, `STOPPED`. */
export const SubAgentStatusBadge: React.FC<{
  status: string | undefined;
  t: TranslateFn;
  className?: string;
}> = ({ status, t, className = '' }) => (
  <span
    className={`inline-flex items-center gap-1 border-2 px-1.5 py-px text-[9px] font-mono font-bold uppercase tracking-wide rounded-sm shrink-0 ${styleFor(status).badge} ${className}`}
  >
    {subAgentStatusLabel(status, t)}
    {isSubAgentActive(status) && (
      <span className="inline-block w-1 h-1 rounded-full bg-current animate-pulse" />
    )}
  </span>
);
