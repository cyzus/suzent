import { describe, expect, it } from 'vitest';
import type { AGUIPart } from '../types/agui';
import type { Message } from '../types/api';
import { mergeLiveToolContinuation, reconcileToolCallMessages } from './toolCallReconciliation';

function toolMessage(part: AGUIPart): Message {
  return {
    role: 'assistant',
    content: 'stored tool snapshot',
    parts: [{ type: 'reasoning', text: 'Thinking' }, part],
  };
}

describe('reconcileToolCallMessages', () => {
  it('suppresses a stale persisted approval owned by the resumed stream', () => {
    const messages = [
      toolMessage({
        type: 'tool',
        toolCallId: 'call-1',
        toolName: 'run_command',
        state: 'approval-requested',
      }),
    ];
    const transient: AGUIPart[] = [
      {
        type: 'tool',
        toolCallId: 'call-1',
        toolName: 'run_command',
        state: 'running',
      },
    ];

    expect(reconcileToolCallMessages(messages, transient)).toEqual([]);
  });

  it('keeps only the strongest persisted result for a duplicated tool call', () => {
    const pending = toolMessage({
      type: 'tool',
      toolCallId: 'call-1',
      toolName: 'run_command',
      state: 'approval-requested',
    });
    const completed = toolMessage({
      type: 'tool',
      toolCallId: 'call-1',
      toolName: 'run_command',
      state: 'completed',
      output: 'ok',
    });

    const result = reconcileToolCallMessages([pending, completed]);

    expect(result).toHaveLength(1);
    expect(result[0].parts?.[1].output).toBe('ok');
  });

  it('preserves real text when removing a shadowed tool part', () => {
    const messages: Message[] = [
      {
        role: 'assistant',
        content: 'Useful explanation',
        parts: [
          { type: 'text', text: 'Useful explanation' },
          {
            type: 'tool',
            toolCallId: 'call-1',
            toolName: 'run_command',
            state: 'approval-requested',
          },
        ],
      },
    ];

    const result = reconcileToolCallMessages(messages, [
      {
        type: 'tool',
        toolCallId: 'call-1',
        state: 'completed',
        output: 'ok',
      },
    ]);

    expect(result).toHaveLength(1);
    expect(result[0].parts).toEqual([{ type: 'text', text: 'Useful explanation' }]);
  });
});

describe('mergeLiveToolContinuation', () => {
  const thought: AGUIPart = { type: 'reasoning', text: 'Check the results' };
  const priorTool: AGUIPart = { type: 'tool', toolCallId: 'read', state: 'completed' };
  const pending: AGUIPart = {
    type: 'tool',
    toolCallId: 'run',
    state: 'approval-requested',
    approvalId: 'run',
  };
  const user: Message = { role: 'user', content: 'Check the project' };
  const suspended: Message = {
    role: 'assistant',
    content: '',
    parts: [thought, priorTool, pending],
  };

  it('uses one rail when the resumed stream already includes the suspended steps', () => {
    const parts: AGUIPart[] = [
      thought,
      priorTool,
      { ...pending, state: 'completed', approvalId: undefined, output: 'ok' },
      { type: 'tool', toolCallId: 'test', state: 'running' },
    ];
    expect(mergeLiveToolContinuation([user, suspended], parts)).toEqual({
      messages: [user],
      parts,
    });
  });

  it('restores the earlier steps when a reload only has the pending or resumed call', () => {
    for (const tool of [
      pending,
      { ...pending, state: 'running', approvalId: undefined },
    ] as const) {
      expect(mergeLiveToolContinuation([user, suspended], [tool])).toEqual({
        messages: [user],
        parts: [thought, priorTool, tool],
      });
    }
  });

  it('keeps a separate rail across a new user message', () => {
    const messages = [suspended, user];
    expect(mergeLiveToolContinuation(messages, [pending])).toEqual({
      messages,
      parts: [pending],
    });
  });

  it('keeps finished parallel calls in place when the replay begins with an approval', () => {
    const parallel: AGUIPart = { type: 'tool', toolCallId: 'parallel', state: 'completed' };
    const resumed: AGUIPart = { ...pending, state: 'completed', approvalId: undefined };
    const next: AGUIPart = { type: 'tool', toolCallId: 'next', state: 'running' };
    const history = { ...suspended, parts: [thought, pending, parallel] };

    expect(mergeLiveToolContinuation([user, history], [resumed, next])).toEqual({
      messages: [user],
      parts: [thought, resumed, parallel, next],
    });
  });
});
