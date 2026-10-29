import { isQuietReply } from './quietReply';
import type { Message } from '../types/api';
import type { AGUIPart } from '../types/agui';

export type RegentDelivery = { messages: string[] } | { reaction: string };
const reactions = new Set(['👍', '❤️', '👀', '✅', '🎉', '😂', '🤔', '🙏', '']);

export function readRegentDelivery(part: AGUIPart): RegentDelivery | undefined {
  if (part.type !== 'tool' || part.state !== 'completed' || part.outcome || !part.output) return;
  try {
    const result = JSON.parse(part.output);
    if (result?.success !== true) return;
    const metadata = result.metadata;
    if (
      part.toolName === 'send_message' &&
      Array.isArray(metadata?.regent_messages) &&
      metadata.regent_messages.length > 0 &&
      metadata.regent_messages.every((text: unknown) => typeof text === 'string' && text.trim())
    )
      return { messages: metadata.regent_messages };
    if (
      part.toolName === 'react_to_message' &&
      typeof metadata?.regent_reaction === 'string' &&
      reactions.has(metadata.regent_reaction)
    )
      return { reaction: metadata.regent_reaction };
  } catch {
    // Interrupted or failed calls stay in the activity rail.
  }
}

/** Delivery IDs reuse tool call IDs, so stream recovery cannot duplicate bubbles. */
export function regentDisplayParts(parts: AGUIPart[], streaming = false): AGUIPart[] {
  const latest = new Map<string, AGUIPart>();
  for (const part of parts) {
    if (part.type === 'tool' && part.toolCallId) {
      const previous = latest.get(part.toolCallId);
      latest.set(part.toolCallId, {
        ...previous,
        ...part,
        output: part.output ?? previous?.output,
      });
    }
  }
  const seen = new Set<string>();
  return parts.flatMap((original): AGUIPart[] => {
    let part = original;
    if (part.type === 'tool' && part.toolCallId) {
      if (seen.has(part.toolCallId)) return [];
      seen.add(part.toolCallId);
      part = latest.get(part.toolCallId)!;
    }
    const delivery = readRegentDelivery(part);
    if (delivery && 'messages' in delivery) {
      return delivery.messages.flatMap((text, index) =>
        isQuietReply(text)
          ? []
          : [
              {
                type: 'text',
                text,
                messageId: `${part.toolCallId}:${index}`,
                regentBubble: true,
              },
            ]
      );
    }
    if (delivery && 'reaction' in delivery) return [];
    if (
      part.type === 'text' &&
      (isQuietReply(part.text) ||
        (streaming && !!part.text?.trim() && 'HEARTBEAT_OK'.startsWith(part.text.trim())))
    )
      return [];
    if (
      part.type === 'tool' &&
      ['send_message', 'react_to_message'].includes(part.toolName || '') &&
      part.state === 'running' &&
      !part.output
    )
      return [];
    return [part];
  });
}

/** A reaction belongs to its user turn, never across a wake-up/system boundary. */
export function regentReactions(
  messages: Message[],
  streamingParts: AGUIPart[] = []
): Map<number, string> {
  const result = new Map<number, string>();
  let target: number | undefined;
  const apply = (parts: AGUIPart[]): void => {
    for (const part of parts) {
      if (part.type === 'incoming-message') target = undefined;
      const delivery = readRegentDelivery(part);
      if (target !== undefined && delivery && 'reaction' in delivery) {
        if (delivery.reaction) result.set(target, delivery.reaction);
        else result.delete(target);
      }
    }
  };
  messages.forEach((message, index) => {
    if (message.role === 'system_triggered' || message.role === 'canvas_action') target = undefined;
    else if (message.role === 'user') target = index;
    else if (message.role === 'assistant') apply(message.parts || []);
  });
  apply(streamingParts);
  return result;
}
