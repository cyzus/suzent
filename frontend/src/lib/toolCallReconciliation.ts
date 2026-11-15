import type { AGUIPart } from '../types/agui';
import type { Message } from '../types/api';

export function mergeLiveToolContinuation(
  messages: Message[],
  liveParts: AGUIPart[]
): { messages: Message[]; parts: AGUIPart[] } {
  const unchanged = { messages, parts: liveParts };
  const liveTools = new Map<string, number>();
  liveParts.forEach((part, i) => {
    if (part.type === 'tool' && part.toolCallId) liveTools.set(part.toolCallId, i);
  });
  if (liveTools.size === 0) return unchanged;

  let index = messages.length - 1;
  for (; index >= 0; index--) {
    const message = messages[index];
    if (
      message.role === 'user' ||
      message.role === 'system_triggered' ||
      (message.role === 'assistant' && !message._streaming_draft)
    )
      break;
  }
  const stored = messages[index]?.parts;
  if (
    messages[index]?.role !== 'assistant' ||
    !stored?.some(
      (part) => part.type === 'tool' && part.toolCallId && liveTools.has(part.toolCallId)
    )
  ) {
    return unchanged;
  }

  // A reload can leave only the approval or the resumed events in the live
  // buffer. Recover earlier steps from history at the first shared part.
  let storedStart = -1;
  let liveStart = liveParts.findIndex((part) => {
    storedStart = stored.findIndex(
      (previous) =>
        previous.type === part.type &&
        ((part.type === 'tool' && !!part.toolCallId && previous.toolCallId === part.toolCallId) ||
          (!!part.messageId && previous.messageId === part.messageId))
    );
    return storedStart >= 0;
  });
  while (
    storedStart > 0 &&
    liveStart > 0 &&
    stored[storedStart - 1].type === 'reasoning' &&
    liveParts[liveStart - 1].type === 'reasoning' &&
    stored[storedStart - 1].text === liveParts[liveStart - 1].text
  ) {
    storedStart--;
    liveStart--;
  }

  const parts = stored.slice(0, storedStart);
  const previousTools = new Map<string, AGUIPart>();
  const toolsBefore = new Map<number, AGUIPart[]>();
  let insertAt = 0;
  for (const part of stored) {
    if (part.type !== 'tool' || !part.toolCallId) continue;
    const liveIndex = liveTools.get(part.toolCallId);
    if (liveIndex !== undefined) insertAt = Math.max(insertAt, liveIndex + 1);
  }
  // Parallel tools may have finished around a deferred call. Preserve their
  // positions even when the resumed stream only replays the deferred calls.
  for (let i = stored.length - 1; i >= storedStart; i--) {
    const part = stored[i];
    if (part.type !== 'tool' || !part.toolCallId) continue;
    const liveIndex = liveTools.get(part.toolCallId);
    if (liveIndex === undefined) {
      const group = toolsBefore.get(insertAt) ?? [];
      group.push(part);
      toolsBefore.set(insertAt, group);
    } else {
      previousTools.set(part.toolCallId, part);
      insertAt = liveIndex;
    }
  }
  for (const [i, part] of liveParts.entries()) {
    parts.push(...(toolsBefore.get(i)?.reverse() ?? []));
    const previous = part.toolCallId ? previousTools.get(part.toolCallId) : undefined;
    parts.push(
      previous
        ? {
            ...part,
            args: part.args || previous.args,
            permissionDecision: part.permissionDecision ?? previous.permissionDecision,
          }
        : part
    );
  }
  parts.push(...(toolsBefore.get(liveParts.length)?.reverse() ?? []));
  return {
    messages: messages.filter((_, i) => i !== index),
    parts,
  };
}

function toolStateScore(part: AGUIPart): number {
  if (part.output != null || part.state === 'completed') return 4;
  if (part.state === 'error') return 3;
  if (part.state === 'running') return 2;
  if (part.state === 'approval-requested') return 1;
  return 0;
}

function hasVisibleNonToolPart(parts: AGUIPart[]): boolean {
  return parts.some((part) => {
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
  transientParts: AGUIPart[] = []
): Message[] {
  const transientToolIds = new Set(
    transientParts
      .filter((part) => part.type === 'tool' && Boolean(part.toolCallId))
      .map((part) => part.toolCallId as string)
  );

  const ownerByToolId = new Map<string, { messageIndex: number; score: number }>();
  messages.forEach((message, messageIndex) => {
    if (message.role !== 'assistant' || !Array.isArray(message.parts)) return;
    message.parts.forEach((part) => {
      if (part.type !== 'tool' || !part.toolCallId) return;
      if (transientToolIds.has(part.toolCallId)) return;
      const score = toolStateScore(part);
      const current = ownerByToolId.get(part.toolCallId);
      if (
        !current ||
        score > current.score ||
        (score === current.score && messageIndex > current.messageIndex)
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
    const parts = message.parts.filter((part) => {
      if (part.type !== 'tool' || !part.toolCallId) return true;
      const owner = ownerByToolId.get(part.toolCallId);
      const keep = !transientToolIds.has(part.toolCallId) && owner?.messageIndex === messageIndex;
      if (!keep) removedTool = true;
      return keep;
    });

    if (!removedTool) return [message];

    const hasRemainingTool = parts.some((part) => part.type === 'tool');
    if (!hasRemainingTool && !hasVisibleNonToolPart(parts)) {
      return [];
    }

    return [{ ...message, parts }];
  });
}
