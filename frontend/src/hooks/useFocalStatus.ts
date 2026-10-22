import { useSyncExternalStore } from 'react';
import { subscribeToBusPayloads } from './useEventBus';
import { fetchFocalAgentStatus, type FocalAgentStatus } from '../lib/focalAgent';

const STATUS_POLL_MS = 10_000;

// One poll serves every component showing Regent: each /focal request scans
// every project and task, so the sidebar card, the header title and its logo
// slot must not each run their own.
let current: FocalAgentStatus | null = null;
let request = 0;
let stop: (() => void) | null = null;
const listeners = new Set<() => void>();

async function refresh(): Promise<void> {
  const sequence = ++request;
  try {
    const next = await fetchFocalAgentStatus();
    if (sequence !== request) return;
    current = next;
    listeners.forEach((listener) => listener());
  } catch {
    // Status is decorative; everything still opens without it.
  }
}

/** Exported for tests; components use `useFocalStatus`. */
export function subscribeToFocalStatus(listener: () => void): () => void {
  listeners.add(listener);
  if (listeners.size === 1) {
    void refresh();
    const timer = setInterval(() => void refresh(), STATUS_POLL_MS);
    const unsubscribe = subscribeToBusPayloads((payload) => {
      if (payload?.event === 'goal_tasks_changed') void refresh();
    });
    stop = () => {
      clearInterval(timer);
      unsubscribe();
    };
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      stop?.();
      stop = null;
    }
  };
}

/**
 * Regent's status, shared by its card, its header and the project list's
 * "waiting on you" markers. Polled once for all of them while any is mounted,
 * and refreshed at once whenever tasks change.
 */
export function useFocalStatus(): FocalAgentStatus | null {
  return useSyncExternalStore(
    subscribeToFocalStatus,
    () => current,
    () => null
  );
}
