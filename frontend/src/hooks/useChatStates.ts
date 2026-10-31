import { useSyncExternalStore } from 'react';
import { subscribeToBusPayloads } from './useEventBus';
import {
  countStates,
  fetchChatStates,
  setChatResolved,
  withResolved,
  type ChatStates,
} from '../lib/chatStates';

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

/**
 * Resolve or reopen a chat on every board at once, then save it. A failed
 * save puts the row back and rejects.
 */
export async function resolveChat(chatId: string, resolved: boolean): Promise<void> {
  const before = current;
  if (current) {
    const now = new Date();
    const chats = current.chats.map((row) =>
      row.chatId === chatId ? withResolved(row, resolved, now) : row
    );
    current = { chats, counts: countStates(chats) };
  }
  // A refresh already in flight was read before this change and would undo it.
  request += 1;
  publish();
  try {
    await setChatResolved(chatId, resolved);
  } catch (error) {
    current = before;
    request += 1;
    publish();
    throw error;
  } finally {
    void refreshChatStates();
  }
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

export function getChatStates(): ChatStates | null {
  return current;
}

/** Every project chat by where it stands for the user, or null until the first load. */
export function useChatStates(): { states: ChatStates | null; failed: boolean } {
  const states = useSyncExternalStore(subscribeToChatStates, getChatStates, () => null);
  const loadFailed = useSyncExternalStore(
    subscribeToChatStates,
    () => failed,
    () => false
  );
  return { states, failed: loadFailed };
}
