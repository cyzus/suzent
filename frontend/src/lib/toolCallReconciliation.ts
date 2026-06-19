import type { AGUIPart } from '../types/agui';
import type { Message } from '../types/api';

function toolStateScore(part: AGUIPart): number {
  if (part.output != null || part.state === 'completed') return 4;
  if (part.state === 'error') return 3;
  if (part.state === 'running') return 2;
  if (part.state === 'approval-requested') return 1;
  return 0;
}

function hasVisibleNonToolPart(parts: AGUIPart[]): boolean {
  return parts.some(part => {
    if (part.type === 'text') {
      return Boolean(part.text?.trim());
    }
    return part.type === 'a2ui';
  });
}

/**
 * Keep one canonical rendered occurrence of each tool call.
 *
 * A suspended turn is persisted as an assistant message, while its resumed
 * stream is rendered from transient AG-UI parts. Without cross-boundary
 * reconciliation, both surfaces render the same toolCallId and the stale
 * persisted approval can appear as a separate "denied" execution.
 */
export function reconcileToolCallMessages(
  messages: Message[],
  transientParts: AGUIPart[] = [],
): Message[] {
  const transientToolIds = new Set(
    transientParts
      .filter(part => part.type === 'tool' && Boolean(part.toolCallId))
      .map(part => part.toolCallId as string),
  );

  const ownerByToolId = new Map<string, { messageIndex: number; score: number }>();
  messages.forEach((message, messageIndex) => {
    if (message.role !== 'assistant' || !Array.isArray(message.parts)) return;
    message.parts.forEach(part => {
      if (part.type !== 'tool' || !part.toolCallId) return;
      if (transientToolIds.has(part.toolCallId)) return;
      const score = toolStateScore(part);
      const current = ownerByToolId.get(part.toolCallId);
      if (
        !current
        || score > current.score
        || (score === current.score && messageIndex > current.messageIndex)
      ) {
        ownerByToolId.set(part.toolCallId, { messageIndex, score });
      }
    });
  });

  return messages.flatMap((message, messageIndex) => {
    if (message.role !== 'assistant' || !Array.isArray(message.parts)) {
      return [message];
    }

    let removedTool = false;
    const parts = message.parts.filter(part => {
      if (part.type !== 'tool' || !part.toolCallId) return true;
      const owner = ownerByToolId.get(part.toolCallId);
      const keep = !transientToolIds.has(part.toolCallId)
        && owner?.messageIndex === messageIndex;
      if (!keep) removedTool = true;
      return keep;
    });

    if (!removedTool) return [message];

    const hasRemainingTool = parts.some(part => part.type === 'tool');
    if (!hasRemainingTool && !hasVisibleNonToolPart(parts)) {
      return [];
    }

    return [{ ...message, parts }];
  });
}
