import { useSyncExternalStore } from 'react';
import { FOCAL_CHAT_ID } from './focalAgent';

// The chat last opened from Regent's board, so its header can offer the way
// back. Module state because the board and the header sit in separate trees.
let openedFromRegent: string | null = null;
const listeners = new Set<() => void>();

function set(chatId: string | null): void {
  if (openedFromRegent === chatId) return;
  openedFromRegent = chatId;
  listeners.forEach((listener) => listener());
}

export function markOpenedFromRegent(chatId: string): void {
  set(chatId);
}

/** Take back a mark whose chat failed to open. */
export function unmarkOpenedFromRegent(chatId: string): void {
  if (openedFromRegent === chatId) set(null);
}

/** Forget the way back once the user has moved on to some other chat. */
export function forgetRegentReturnUnless(chatId: string | null): void {
  if (openedFromRegent && openedFromRegent !== chatId) set(null);
}

// While Regent is on screen, it opens chats in its side panel. Module state so
// the chat list, which sits outside the chat window, can reach it too.
let besideRegent: ((chatId: string) => void) | null = null;

export function setRegentSidePanelOpener(open: ((chatId: string) => void) | null): void {
  besideRegent = open;
}

/** Opens the chat beside Regent when Regent is on screen; false when it is not. */
export function openBesideRegent(chatId: string): boolean {
  if (!besideRegent || chatId === FOCAL_CHAT_ID) return false;
  besideRegent(chatId);
  return true;
}

export function getOpenedFromRegent(): string | null {
  return openedFromRegent;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The chat opened from Regent's board, or null. */
export function useOpenedFromRegent(): string | null {
  return useSyncExternalStore(subscribe, getOpenedFromRegent, () => null);
}
