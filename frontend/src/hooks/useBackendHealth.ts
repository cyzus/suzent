import { useEffect, useState } from 'react';
import { getApiBase } from '../lib/api';
import { pollWhileVisible } from '../lib/visiblePolling';

export type BackendHealth = 'checking' | 'online' | 'offline';

const POLL_INTERVAL_MS = 15_000;

/**
 * Whether the backend is answering.
 *
 * The desktop shell owns the backend process and can simply restart it, so it
 * has never needed this. A browser pointed at a remote host has no such
 * relationship: the server may be down, the tunnel may have dropped, or the
 * device token may have been revoked, and all three look identical until you
 * send a request. The console keeps the answer visible.
 */
export function useBackendHealth(): BackendHealth {
  const [health, setHealth] = useState<BackendHealth>('checking');

  useEffect(() => {
    let cancelled = false;

    const probe = async () => {
      try {
        const response = await fetch(`${getApiBase()}/health`);
        if (!cancelled) setHealth(response.ok ? 'online' : 'offline');
      } catch {
        if (!cancelled) setHealth('offline');
      }
    };

    void probe();
    const stopPolling = pollWhileVisible(() => void probe(), POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, []);

  return health;
}
