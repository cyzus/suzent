import { describe, expect, it } from 'vitest';
import type { AGUIPart } from '../types/agui';
import type { Message } from '../types/api';
import { reconcileToolCallMessages } from './toolCallReconciliation';

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
        toolName: 'bash_execute',
        state: 'approval-requested',
      }),
    ];
    const transient: AGUIPart[] = [{
      type: 'tool',
      toolCallId: 'call-1',
      toolName: 'bash_execute',
      state: 'running',
    }];

    expect(reconcileToolCallMessages(messages, transient)).toEqual([]);
  });

  it('keeps only the strongest persisted result for a duplicated tool call', () => {
    const pending = toolMessage({
      type: 'tool',
      toolCallId: 'call-1',
      toolName: 'bash_execute',
      state: 'approval-requested',
    });
    const completed = toolMessage({
      type: 'tool',
      toolCallId: 'call-1',
      toolName: 'bash_execute',
      state: 'completed',
      output: 'ok',
    });

    const result = reconcileToolCallMessages([pending, completed]);

    expect(result).toHaveLength(1);
    expect(result[0].parts?.[1].output).toBe('ok');
  });

  it('preserves real text when removing a shadowed tool part', () => {
    const messages: Message[] = [{
      role: 'assistant',
      content: 'Useful explanation',
      parts: [
        { type: 'text', text: 'Useful explanation' },
        {
          type: 'tool',
          toolCallId: 'call-1',
          toolName: 'bash_execute',
          state: 'approval-requested',
        },
      ],
    }];

    const result = reconcileToolCallMessages(messages, [{
      type: 'tool',
      toolCallId: 'call-1',
      state: 'completed',
      output: 'ok',
    }]);

    expect(result).toHaveLength(1);
    expect(result[0].parts).toEqual([
      { type: 'text', text: 'Useful explanation' },
    ]);
  });
});
