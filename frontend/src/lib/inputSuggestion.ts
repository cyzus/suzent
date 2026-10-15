/**
 * Next-message prediction shown as ghost text in the chat composer.
 */
import { getApiBase } from './api';
import type { Message } from '../types/api';

const STORAGE_KEY = 'suzent.inputSuggestions.enabled';
const CHANGE_EVENT = 'suzent:input-suggestions-changed';
const CONTEXT_MESSAGES = 6;

export function isInputSuggestionEnabled(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== 'false';
  } catch {
    return true;
  }
}

export function setInputSuggestionEnabled(enabled: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, String(enabled));
  } catch {
    // Storage blocked: the toggle still applies for this page via the event.
  }
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: enabled }));
}

export function onInputSuggestionEnabledChange(listener: (enabled: boolean) => void): () => void {
  const handler = (e: Event) => listener((e as CustomEvent<boolean>).detail);
  window.addEventListener(CHANGE_EVENT, handler);
  return () => window.removeEventListener(CHANGE_EVENT, handler);
}

/**
 * The part of the suggestion still to be typed, or null when the input has
 * drifted away from it. Matching ignores case so typing "make" still offers
 * the rest of "Make it shorter"; accepting keeps what the user typed.
 */
export function ghostRemainder(input: string, suggestion: string | null): string | null {
  if (!suggestion) return null;
  // Mention chips render wider than their raw text, which would misplace the
  // overlay; a multi-line draft is never heading toward a one-line prediction.
  if (input.includes('@[') || input.includes('\n')) return null;
  if (input.length >= suggestion.length) return null;
  // contenteditable types a trailing space as a non-breaking one.
  const typed = input.replace(/\u00a0/g, ' ').toLowerCase();
  if (!suggestion.toLowerCase().startsWith(typed)) return null;
  return suggestion.slice(input.length);
}

/** The recent user/assistant turns the prediction is based on. */
export function suggestionContext(messages: Message[]): { role: string; content: string }[] {
  return messages
    .filter((m) => (m.role === 'user' || m.role === 'assistant') && !m._streaming_draft)
    .filter((m) => typeof m.content === 'string' && m.content.trim() !== '')
    .slice(-CONTEXT_MESSAGES)
    .map((m) => ({ role: m.role, content: m.content }));
}

/**
 * Identifies the reply a suggestion was predicted from, or null when the last
 * message is not a reply. Messages carry no stable id, so the reply's text
 * stands in for one.
 */
export function replyKey(messages: Message[]): string | null {
  const context = suggestionContext(messages);
  const last = context[context.length - 1];
  if (!last || last.role !== 'assistant') return null;
  let hash = 5381;
  for (let i = 0; i < last.content.length; i++) {
    hash = ((hash << 5) + hash + last.content.charCodeAt(i)) | 0;
  }
  return `${last.content.length}:${(hash >>> 0).toString(36)}`;
}

export interface SavedSuggestion {
  replyKey: string;
  suggestion: string;
}

/** The suggestion last saved for a chat, from whichever device made it. */
export async function fetchSavedSuggestion(
  chatId: string,
  signal: AbortSignal
): Promise<SavedSuggestion | null> {
  const res = await fetch(
    `${getApiBase()}/chat/input-suggestion?chat_id=${encodeURIComponent(chatId)}`,
    { signal }
  );
  if (!res.ok) return null;
  const data = await res.json();
  return typeof data.reply_key === 'string' && typeof data.suggestion === 'string'
    ? { replyKey: data.reply_key, suggestion: data.suggestion }
    : null;
}

/** Predicts the next message; with a chat and reply key, the server also saves it. */
export async function fetchInputSuggestion(
  messages: { role: string; content: string }[],
  signal: AbortSignal,
  save?: { chatId: string; replyKey: string }
): Promise<string | null> {
  const res = await fetch(`${getApiBase()}/chat/input-suggestion`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, chat_id: save?.chatId, reply_key: save?.replyKey }),
    signal,
  });
  if (!res.ok) return null;
  const data = await res.json();
  return typeof data.suggestion === 'string' && data.suggestion ? data.suggestion : null;
}
