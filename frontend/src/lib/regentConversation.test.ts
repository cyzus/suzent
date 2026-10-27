import { describe, expect, it } from 'vitest';
import { processEvent } from '../hooks/useAGUI';
import type { AGUIPart } from '../types/agui';
import type { Message } from '../types/api';
import { readRegentDelivery, regentDisplayParts, regentReactions } from './regentConversation';
import { buildAguiActivityChunks } from '../components/chat/ActivityRail';

const delivery = (
  id: string,
  metadata: Record<string, unknown>,
  toolName = 'send_message'
): AGUIPart => ({
  type: 'tool',
  toolName,
  toolCallId: id,
  state: 'completed',
  output: JSON.stringify({ success: true, message: 'Delivered', metadata }),
});
const reaction = (emoji: string): AGUIPart =>
  delivery('reaction', { regent_reaction: emoji }, 'react_to_message');

describe('Regent conversation delivery', () => {
  it('shows complete deliveries immediately from real tool-result events, with separate bubbles', () => {
    const part = delivery('send', { regent_messages: ['Looking now.', 'Two tests failed.'] });
    const { parts } = processEvent(
      {
        type: 'TOOL_CALL_RESULT',
        data: {
          toolCallId: 'send',
          content: JSON.parse(part.output!),
        },
      },
      [{ type: 'tool', toolName: 'send_message', toolCallId: 'send', state: 'running' }]
    );
    const display = regentDisplayParts(parts);
    expect(display.map((p) => p.text)).toEqual(['Looking now.', 'Two tests failed.']);
    expect(buildAguiActivityChunks(display)).toHaveLength(2);
    expect(regentDisplayParts(JSON.parse(JSON.stringify(parts)))).toEqual(display);
  });
  it('deduplicates replayed tool calls and keeps failures visible', () => {
    const part = delivery('send', { regent_messages: ['Hello'] });
    expect(
      regentDisplayParts([{ ...part, state: 'running', output: undefined }, part, part])
    ).toHaveLength(1);
    const failed: AGUIPart = { ...part, outcome: 'failed' };
    expect(regentDisplayParts([failed])).toEqual([failed]);
    expect(readRegentDelivery({ ...part, toolName: 'other_tool' })).toBeUndefined();
  });
  it('attaches live and persisted reactions to their own user turn, replacing and removing them', () => {
    const messages: Message[] = [
      { role: 'user', content: 'hello' },
      { role: 'assistant', content: '', parts: [reaction('👀')] },
    ];
    expect(regentReactions(messages).get(0)).toBe('👀');
    expect(regentReactions(messages, [reaction('✅')]).get(0)).toBe('✅');
    expect(regentReactions(messages, [reaction('')]).size).toBe(0);
    expect(regentDisplayParts([reaction('👍')])).toEqual([]);
    messages.push({ role: 'system_triggered', content: 'wake up' });
    expect(regentReactions(messages, [reaction('❤️')]).get(0)).toBe('👀');
    messages.push({ role: 'user', content: 'next' });
    expect([...regentReactions(messages, [reaction('❤️')])]).toEqual([
      [0, '👀'],
      [3, '❤️'],
    ]);
  });
  it('does not render arguments or malformed results as delivered messages', () => {
    expect(
      regentDisplayParts([
        {
          type: 'tool',
          toolName: 'send_message',
          state: 'running',
          args: '{"messages":["unsent"]}',
        },
      ])
    ).toEqual([]);
    expect(readRegentDelivery(delivery('bad', { regent_messages: [42] }))).toBeUndefined();
  });
});
