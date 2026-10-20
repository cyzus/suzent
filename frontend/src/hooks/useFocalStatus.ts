import { useCallback, useEffect, useRef, useState } from 'react';
import { subscribeToBusPayloads } from './useEventBus';
import { fetchFocalAgentStatus, type FocalAgentStatus } from '../lib/focalAgent';

const STATUS_POLL_MS = 10_000;

/**
 * SUZENT's status, shared by its card and the project list's "waiting on you"
 * markers. Polled, and refreshed at once whenever tasks change.
 */
export function useFocalStatus(): FocalAgentStatus | null {
  const [status, setStatus] = useState<FocalAgentStatus | null>(null);
  const request = useRef(0);

  const refresh = useCallback(async (): Promise<void> => {
    const sequence = ++request.current;
    try {
      const next = await fetchFocalAgentStatus();
      if (sequence === request.current) setStatus(next);
    } catch {
      // Status is decorative; everything still opens without it.
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), STATUS_POLL_MS);
    const unsubscribe = subscribeToBusPayloads((payload) => {
      if (payload?.event === 'goal_tasks_changed') void refresh();
    });
    return () => {
      window.clearInterval(timer);
      unsubscribe();
    };
  }, [refresh]);

  return status;
}
