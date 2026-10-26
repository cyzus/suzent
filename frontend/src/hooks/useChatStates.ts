import { useSyncExternalStore } from 'react';
import { subscribeToBusPayloads } from './useEventBus';
import { fetchChatStates, type ChatStates } from '../lib/chatStates';

const POLL_MS = 10_000;
const REFRESH_EVENTS = new Set([
  'chat_status_changed',
  'goal_tasks_changed',
  'stream_started',
  'stream_ended',
]);

// One poll for the board and the header's resolve button, as with useFocalStatus.
let current: ChatStates | null = null;
let failed = false;
let request = 0;
let stop: (() => void) | null = null;
const listeners = new Set<() => void>();

function publish(): void {
  listeners.forEach((listener) => listener());
}

export async function refreshChatStates(): Promise<void> {
  const sequence = ++request;
  try {
    const next = await fetchChatStates();
    if (sequence !== request) return;
    current = next;
    failed = false;
  } catch {
    if (sequence !== request) return;
    failed = true;
  }
  publish();
}

export function subscribeToChatStates(listener: () => void): () => void {
  listeners.add(listener);
  if (listeners.size === 1) {
    void refreshChatStates();
    const timer = setInterval(() => void refreshChatStates(), POLL_MS);
    const unsubscribe = subscribeToBusPayloads((payload) => {
      if (REFRESH_EVENTS.has(payload?.event)) void refreshChatStates();
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

/** Every project chat by where it stands for the user, or null until the first load. */
export function useChatStates(): { states: ChatStates | null; failed: boolean } {
  const states = useSyncExternalStore(
    subscribeToChatStates,
    () => current,
    () => null
  );
  const loadFailed = useSyncExternalStore(
    subscribeToChatStates,
    () => failed,
    () => false
  );
  return { states, failed: loadFailed };
}
