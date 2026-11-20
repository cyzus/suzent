import { describe, expect, it } from 'vitest';
import { processEvent, type AGUIPart } from './useAGUI';

const recovery = {
  type: 'CUSTOM',
  data: {
    name: 'model_recovery',
    value: { attempt: 1, maxAttempts: 3, reason: 'connection', detail: 'Connection error.' },
  },
};

describe('processEvent model_recovery', () => {
  it('drops the reply that broke off and notes the retry', () => {
    const parts: AGUIPart[] = [
      { type: 'text', text: 'Looking it up' },
      { type: 'tool', toolCallId: 'a', toolName: 'read', state: 'completed', output: 'ok' },
      { type: 'reasoning', text: 'Now I write' },
      { type: 'text', text: 'Here is the first half' },
      { type: 'tool', toolCallId: 'b', toolName: 'write', args: '{"pa', state: 'running' },
    ];

    const { parts: next } = processEvent(recovery, parts);

    expect(next.map((part) => part.type)).toEqual(['text', 'tool', 'model-notice']);
    expect(next[2].modelNotice).toMatchObject({ attempt: 1, maxAttempts: 3, reason: 'connection' });
    expect(parts).toHaveLength(5);
  });

  it('keeps messages that arrived during the reply', () => {
    const parts: AGUIPart[] = [
      { type: 'incoming-message', text: 'also check the tests' },
      { type: 'text', text: 'Sure' },
    ];

    const { parts: next } = processEvent(recovery, parts);

    expect(next.map((part) => part.type)).toEqual(['incoming-message', 'model-notice']);
  });
});

describe('processEvent RUN_ERROR code', () => {
  it('keeps the failure code so the chat can explain it', () => {
    const result = processEvent(
      { type: 'RUN_ERROR', data: { message: 'Request timed out.', code: 'model_stalled' } },
      []
    );
    expect(result.errorCode).toBe('model_stalled');
  });
});
