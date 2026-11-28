import React from 'react';

import { useBackendHealth } from '../../hooks/useBackendHealth';
import { useI18n } from '../../i18n';

const HEALTH_DOT: Record<string, string> = {
  checking: 'bg-neutral-400',
  online: 'bg-brutal-green',
  offline: 'bg-brutal-red',
};

/**
 * Which host this browser is talking to, and whether it answers.
 *
 * A browser pointed at a remote Suzent cannot tell a stopped server from a
 * dropped tunnel from a revoked token until it sends a request, so the answer
 * -- and the host it is about -- stays on screen. The desktop owns its backend
 * and has no use for it.
 */
export function HostStatus(): React.ReactElement {
  const { t } = useI18n();
  const health = useBackendHealth();
  const label = t(`console.health.${health}`);

  return (
    <div
      className="flex shrink-0 items-center gap-2 border-t border-neutral-200 bg-white px-4 py-2 dark:border-zinc-700 dark:bg-zinc-800"
      title={`${window.location.host} - ${label}`}
    >
      <span className={`h-2 w-2 shrink-0 rounded-full ${HEALTH_DOT[health]}`} aria-hidden="true" />
      <span className="min-w-0 truncate font-mono text-[11px] text-neutral-500 dark:text-neutral-400">
        {window.location.host}
      </span>
      <span className="sr-only">{label}</span>
    </div>
  );
}
