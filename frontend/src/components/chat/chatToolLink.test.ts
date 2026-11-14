import { describe, expect, it } from 'vitest';
import { linkedChatFor, linkedChatsFromTools } from './chatToolLink';

const result = (metadata: Record<string, unknown>): string =>
  JSON.stringify({ success: true, message: 'ok', metadata });

describe('linkedChatFor', () => {
  it('links a dispatch to the local session it reached', () => {
    expect(linkedChatFor('agent_dispatch', { agent_id: 'c1', agent_title: ' Fix login ' })).toEqual(
      { id: 'c1', title: 'Fix login' }
    );
  });

  it('leaves remote agents and other tools unlinked', () => {
    expect(linkedChatFor('agent_dispatch', { agent_id: 'peer:laptop' })).toBeNull();
    expect(linkedChatFor('read_file', { agent_id: 'c1', agent_title: 'x' })).toBeNull();
  });
});

describe('linkedChatsFromTools', () => {
  it('collects each finished session once, in order', () => {
    expect(
      linkedChatsFromTools([
        { toolName: 'agent_dispatch', output: result({ agent_id: 'a', agent_title: 'A' }) },
        { toolName: 'mailbox', output: result({ agent_id: 'b', agent_title: 'B' }) },
        { toolName: 'agent_dispatch', output: result({ agent_id: 'a', agent_title: 'A' }) },
        {
          toolName: 'agent_dispatch',
          failed: true,
          output: result({ agent_id: 'c', agent_title: 'C' }),
        },
        { toolName: 'agent_dispatch', running: true },
      ])
    ).toEqual([
      { id: 'a', title: 'A' },
      { id: 'b', title: 'B' },
    ]);
  });
});
