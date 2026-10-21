import type { AGUIPart } from '../types/agui';
import type { Message } from '../types/api';

export function isStreamingDraftMessage(message: Message): boolean {
  return message.role === 'assistant' && message._streaming_draft === true;
}

export function hideStreamingDrafts(messages: Message[], shouldHide: boolean): Message[] {
  if (!shouldHide) return messages;
  return messages.filter((message) => !isStreamingDraftMessage(message));
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
