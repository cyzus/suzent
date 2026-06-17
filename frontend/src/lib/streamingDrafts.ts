import type { Message } from '../types/api';

export function isStreamingDraftMessage(message: Message): boolean {
  return message.role === 'assistant' && message._streaming_draft === true;
}

export function hideStreamingDrafts(
  messages: Message[],
  shouldHide: boolean,
): Message[] {
  if (!shouldHide) return messages;
  return messages.filter(message => !isStreamingDraftMessage(message));
}
