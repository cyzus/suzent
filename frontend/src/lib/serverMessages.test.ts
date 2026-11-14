import { describe, expect, it } from 'vitest';
import { mapServerMessages } from './serverMessages';

describe('mapServerMessages', () => {
  it('folds a tool round-trip and its follow-up into one assistant bubble', () => {
    const messages = mapServerMessages([
      { role: 'user', content: 'Fix the login redirect' },
      {
        role: 'assistant',
        content: '',
        tool_calls: [{ id: 'c1', function: { name: 'read_file', arguments: '{"path":"a.ts"}' } }],
      },
      { role: 'tool', tool_call_id: 'c1', name: 'read_file', content: 'export {}' },
      { role: 'assistant', content: 'Done.' },
    ]);

    expect(messages.map((message) => message.role)).toEqual(['user', 'assistant']);
    expect(messages[1].content).toContain('data-tool-call-id="c1"');
    expect(messages[1].content).toContain('Done.');
    expect(messages[1].raw_message_end_index).toBe(4);
  });

  it('drops empty user rows that only resume a tool turn', () => {
    const messages = mapServerMessages([
      { role: 'assistant', content: 'Working' },
      { role: 'user', content: '  ' },
    ]);

    expect(messages).toHaveLength(1);
  });
});
