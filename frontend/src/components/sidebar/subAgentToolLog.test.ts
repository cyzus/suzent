import { describe, expect, it } from 'vitest';
import { extractToolLog } from './subAgentToolLog';

describe('extractToolLog', () => {
  it('reads tool activity from captured run parts', () => {
    expect(
      extractToolLog([
        {
          role: 'assistant',
          parts: [
            { type: 'text' },
            {
              type: 'tool',
              toolCallId: 't1',
              toolName: 'read_file',
              args: { path: 'a' },
              output: 'contents',
            },
            { type: 'tool', toolCallId: 't2', toolName: 'shell', args: 'pwd' },
          ],
        },
      ])
    ).toEqual([
      { toolName: 'read_file', args: '{"path":"a"}', output: 'contents' },
      { toolName: 'shell', args: 'pwd', output: undefined },
    ]);
  });

  it('keeps legacy calls and results', () => {
    expect(
      extractToolLog([
        {
          role: 'assistant',
          tool_calls: [{ id: 't1', function: { name: 'shell', arguments: '{}' } }],
        },
        { role: 'tool', tool_call_id: 't1', content: 'ok' },
      ])
    ).toEqual([{ toolName: 'shell', args: '{}', output: 'ok' }]);
  });

  it('deduplicates mixed records and prefers captured output', () => {
    expect(
      extractToolLog([
        {
          role: 'assistant',
          tool_calls: [{ id: 't1', function: { name: 'shell', arguments: '{}' } }],
          parts: [{ type: 'tool', toolCallId: 't1', toolName: 'shell', args: '{}', output: 'new' }],
        },
        { role: 'tool', tool_call_id: 't1', content: 'old' },
      ])
    ).toEqual([{ toolName: 'shell', args: '{}', output: 'new' }]);
  });
});
