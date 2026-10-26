import type { AGUIPart } from '../types/agui';
import type { Message } from '../types/api';

export function splitLeadingTriggers(parts: AGUIPart[]): {
  triggers: AGUIPart[];
  response: AGUIPart[];
} {
  const responseStart = parts.findIndex(
    (part) => part.type !== 'incoming-message' || !part.persisted
  );
  const boundary = responseStart === -1 ? parts.length : responseStart;
  return { triggers: parts.slice(0, boundary), response: parts.slice(boundary) };
}

export function isStreamingDraftMessage(message: Message): boolean {
  return message.role === 'assistant' && message._streaming_draft === true;
}

export function hideStreamingDrafts(messages: Message[], shouldHide: boolean): Message[] {
  const settledContents = new Set<string>();
  const hidden = new Set<Message>();
  for (let index = messages.length - 1; index >= 0; index--) {
    const message = messages[index];
    if (message.role === 'user' || message.role === 'system_triggered') {
      settledContents.clear();
    } else if (isStreamingDraftMessage(message)) {
      if (shouldHide || (message.content && settledContents.has(message.content))) {
        hidden.add(message);
      }
    } else if (message.role === 'assistant' && message.content) {
      settledContents.add(message.content);
    }
  }
  return hidden.size ? messages.filter((message) => !hidden.has(message)) : messages;
}

/**
 * Hide the stored trigger row a live run is already showing.
 *
 * A turn started by a hidden message writes its trigger row before the run
 * starts and announces it on the stream, because the reload that opens the
 * stream usually lands first. When the reload wins instead, both would show.
 * Only the latest matching row is hidden: an earlier turn with the same
 * trigger text (a recurring task) keeps its own.
 */
export function hideLiveTriggerRows(messages: Message[], liveParts: AGUIPart[]): Message[] {
  const pending = liveParts
    .filter((part) => part.type === 'incoming-message' && part.persisted && part.text)
    .map((part) => part.text as string);
  if (pending.length === 0) return messages;
  const hidden = new Set<number>();
  for (let i = messages.length - 1; i >= 0 && pending.length > 0; i--) {
    const message = messages[i];
    if (message.role !== 'system_triggered') continue;
    const match = pending.indexOf(message.content);
    if (match < 0) continue;
    pending.splice(match, 1);
    hidden.add(i);
  }
  return hidden.size ? messages.filter((_, i) => !hidden.has(i)) : messages;
}
