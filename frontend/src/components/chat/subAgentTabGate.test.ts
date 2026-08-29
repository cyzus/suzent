import { describe, expect, it } from 'vitest';
import type { Message } from '../../types/api';

/**
 * Mirrors the transcript check in ChatWindow that decides whether the Agents
 * tab can be opened. The tab used to be gated purely on live SSE state, so a
 * reopened chat with a long sub-agent history had it greyed out and disabled
 * even though the panel behind it fetches that history itself.
 */
function transcriptHasSubAgentCall(messages: Message[]): boolean {
  return messages.some((message) =>
    (message.parts || []).some((part) => part.type === 'tool' && part.toolName === 'agent')
  );
}

const msg = (parts: unknown[]): Message =>
  ({ role: 'assistant', content: '', parts }) as unknown as Message;

describe('transcriptHasSubAgentCall', () => {
  it('finds a sub-agent call in a reloaded transcript', () => {
    expect(
      transcriptHasSubAgentCall([
        msg([{ type: 'text', text: 'hi' }]),
        msg([{ type: 'tool', toolName: 'agent', toolCallId: 'call-1' }]),
      ])
    ).toBe(true);
  });

  it('does not fire on other tools', () => {
    expect(transcriptHasSubAgentCall([msg([{ type: 'tool', toolName: 'run_command' }])])).toBe(
      false
    );
  });

  it('handles messages with no parts', () => {
    expect(transcriptHasSubAgentCall([{ role: 'user', content: 'hi' } as Message])).toBe(false);
  });

  it('is false for an empty transcript', () => {
    expect(transcriptHasSubAgentCall([])).toBe(false);
  });
});
