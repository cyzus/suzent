import type { Message } from '../types/api';

export function hasToolContinuation(message: Partial<Message>): boolean {
  const parts = message.parts?.filter(
    (part) =>
      part.type === 'tool' ||
      part.type === 'reasoning' ||
      (part.type === 'text' && part.text?.trim()) ||
      part.type === 'a2ui'
  );
  return parts?.at(-1)?.type === 'tool';
}
