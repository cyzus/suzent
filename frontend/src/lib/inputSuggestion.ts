/**
 * Next-message prediction shown as ghost text in the chat composer.
 */
import { getApiBase } from './api';
import type { Message } from '../types/api';

const STORAGE_KEY = 'suzent.inputSuggestions.enabled';
const CACHE_KEY = 'suzent.inputSuggestions.cache';
const CHANGE_EVENT = 'suzent:input-suggestions-changed';
const CONTEXT_MESSAGES = 6;
const CACHE_CHATS = 50;

interface CachedSuggestion {
  reply: string;
  text: string;
  at: number;
}

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
 * Identifies the reply a suggestion was predicted from. Messages carry no
 * stable id, so the reply's text stands in for one.
 */
function replyFingerprint(messages: Message[]): string | null {
  const context = suggestionContext(messages);
  const last = context[context.length - 1];
  if (!last || last.role !== 'assistant') return null;
  let hash = 5381;
  for (let i = 0; i < last.content.length; i++) {
    hash = ((hash << 5) + hash + last.content.charCodeAt(i)) | 0;
  }
  return `${last.content.length}:${(hash >>> 0).toString(36)}`;
}

function readCache(): Record<string, CachedSuggestion> {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(CACHE_KEY) || '{}');
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, CachedSuggestion>) : {};
  } catch {
    return {};
  }
}

/** The suggestion saved for this chat, while its last reply is still the one it was made for. */
export function loadCachedSuggestion(chatId: string, messages: Message[]): string | null {
  const entry = readCache()[chatId];
  const reply = replyFingerprint(messages);
  return entry && reply && entry.reply === reply && typeof entry.text === 'string'
    ? entry.text
    : null;
}

export function saveCachedSuggestion(
  chatId: string,
  messages: Message[],
  suggestion: string | null
): void {
  const cache = readCache();
  const reply = replyFingerprint(messages);
  // Re-inserting puts this chat last, so it wins a same-millisecond tie below.
  delete cache[chatId];
  if (suggestion && reply) cache[chatId] = { reply, text: suggestion, at: Date.now() };
  const kept = Object.entries(cache)
    .sort(([, a], [, b]) => a.at - b.at)
    .slice(-CACHE_CHATS);
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(Object.fromEntries(kept)));
  } catch {
    // Storage blocked or full: the suggestion still shows until the app closes.
  }
}

export async function fetchInputSuggestion(
  messages: { role: string; content: string }[],
  signal: AbortSignal
): Promise<string | null> {
  const res = await fetch(`${getApiBase()}/chat/input-suggestion`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
    signal,
  });
  if (!res.ok) return null;
  const data = await res.json();
  return typeof data.suggestion === 'string' && data.suggestion ? data.suggestion : null;
}
