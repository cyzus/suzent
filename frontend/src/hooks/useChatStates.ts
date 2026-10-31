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
// Resolves not yet confirmed by a refresh read after their save, by chat.
// Every refresh shows them, so a poll landing mid-save can't undo the click.
const pending = new Map<string, { resolved: boolean; token: number }>();
let nextToken = 0;

function publish(): void {
  listeners.forEach((listener) => listener());
}

function withPending(states: ChatStates): ChatStates {
  if (pending.size === 0) return states;
  const now = new Date();
  const chats = states.chats.map((row) => {
    const change = pending.get(row.chatId);
    return change ? withResolved(row, change.resolved, now) : row;
  });
  return { chats, counts: countStates(chats) };
}

export async function refreshChatStates(): Promise<void> {
  const sequence = ++request;
  try {
    const next = await fetchChatStates();
    if (sequence !== request) return;
    current = withPending(next);
    failed = false;
  } catch {
    if (sequence !== request) return;
    failed = true;
  }
  publish();
}

/**
 * Resolve or reopen a chat on every board at once, then save it. A failed
 * save puts that chat's row back, leaving other chats' changes alone, and
 * rejects.
 */
export async function resolveChat(chatId: string, resolved: boolean): Promise<void> {
  const token = ++nextToken;
  const previous = current?.chats.find((row) => row.chatId === chatId) ?? null;
  pending.set(chatId, { resolved, token });
  if (current) current = withPending(current);
  publish();
  // A later click on the same chat owns its row from then on.
  const owned = (): boolean => pending.get(chatId)?.token === token;
  try {
    await setChatResolved(chatId, resolved);
  } catch (error) {
    if (owned()) {
      pending.delete(chatId);
      if (current && previous) {
        const chats = current.chats.map((row) => (row.chatId === chatId ? previous : row));
        current = { chats, counts: countStates(chats) };
      }
      publish();
    }
    void refreshChatStates();
    throw error;
  }
  await refreshChatStates();
  if (owned()) pending.delete(chatId);
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
