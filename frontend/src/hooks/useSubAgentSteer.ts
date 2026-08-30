/**
 * useSubAgentSteer — redirects sent to sub-agents, and whether they landed.
 *
 * Module-level rather than component state for two reasons. A redirect outlives
 * the card that sent it: collapsing the block, switching chats, or reopening the
 * transcript mid-run would otherwise erase the only record that the user said
 * anything. And the same redirect needs to read the same way from the
 * transcript card and the sidebar panel, which are separate components looking
 * at one sub-agent.
 *
 * "Sent" and "picked up" stay distinct here. An injected message waits for the
 * child's next model request, so the run reports back with an
 * `agent_absorbed_message` event carrying the enqueue id it took.
 */
import { useEffect, useState } from 'react';
import { getApiBase } from '../lib/api';

export interface SentSteer {
  enqueueId: string;
  text: string;
  /** True once the run has taken the message into its history. */
  absorbed: boolean;
}

const _sent = new Map<string, SentSteer[]>();
const _listeners = new Set<() => void>();

/** Bounded so a long session cannot grow the record without limit. */
const MAX_PER_TASK = 10;

function notify() {
  for (const listener of _listeners) listener();
}

export function markSteerAbsorbed(enqueueId: string): void {
  let changed = false;
  for (const [taskId, steers] of _sent) {
    const next = steers.map((steer) =>
      steer.enqueueId === enqueueId && !steer.absorbed ? { ...steer, absorbed: true } : steer
    );
    if (next.some((steer, i) => steer !== steers[i])) {
      _sent.set(taskId, next);
      changed = true;
    }
  }
  if (changed) notify();
}

/**
 * Send a redirect to one running sub-agent.
 *
 * Returns false when the sub-agent has no live run to take it — the caller
 * should say so rather than let the text vanish as though it were delivered.
 */
export async function sendSubAgentSteer(taskId: string, message: string): Promise<boolean> {
  const res = await fetch(`${getApiBase()}/subagents/${taskId}/steer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) return false;
  const enqueueId: string = (await res.json())?.enqueue_id ?? '';
  if (!enqueueId) return false;
  const existing = _sent.get(taskId) ?? [];
  _sent.set(
    taskId,
    [...existing, { enqueueId, text: message, absorbed: false }].slice(-MAX_PER_TASK)
  );
  notify();
  return true;
}

/** Forget one task's redirects — used when its run is cleared from view. */
export function clearSentSteers(taskId: string): void {
  if (_sent.delete(taskId)) notify();
}

/** The redirects recorded for one sub-agent. The hook is a thin wrapper. */
export function getSentSteers(taskId: string | undefined): SentSteer[] {
  return taskId ? (_sent.get(taskId) ?? []) : [];
}

export function useSentSteers(taskId: string | undefined): SentSteer[] {
  const [, forceUpdate] = useState(0);

  useEffect(() => {
    const listener = () => forceUpdate((n) => n + 1);
    _listeners.add(listener);
    return () => {
      _listeners.delete(listener);
    };
  }, []);

  return taskId ? (_sent.get(taskId) ?? []) : [];
}
