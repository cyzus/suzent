import { describe, expect, it } from 'vitest';
import { processEvent } from './useAGUI';
import { hasStreamedOutput } from '../lib/chatUtils';
import type { AGUIPart } from '../types/agui';

/**
 * ag-ui-protocol 0.1.13 renamed the thinking family to REASONING_*, and
 * pydantic-ai emits whichever family the negotiated version calls for. When
 * only the legacy names were handled, every reasoning event was dropped: no
 * reasoning part meant `hasStreamedOutput` stayed false, so the message sat in
 * its collapsed "thinking" state — the assembly animation with the stream
 * hidden behind it — until the first answer token arrived.
 */
const replay = (events: Array<{ type: string; delta?: string }>): AGUIPart[] =>
  events.reduce<AGUIPart[]>(
    (parts, event) =>
      processEvent({ type: event.type, data: { ...event, messageId: 'm1' } }, parts).parts,
    []
  );

describe('reasoning stream events', () => {
  it('accumulates the REASONING_* family into one reasoning part', () => {
    const parts = replay([
      { type: 'REASONING_START' },
      { type: 'REASONING_MESSAGE_START' },
      { type: 'REASONING_MESSAGE_CONTENT', delta: 'Let me ' },
      { type: 'REASONING_MESSAGE_CONTENT', delta: 'think.' },
      { type: 'REASONING_MESSAGE_END' },
      { type: 'REASONING_END' },
    ]);

    expect(parts).toEqual([{ type: 'reasoning', text: 'Let me think.' }]);
  });

  it('still accumulates the legacy THINKING_* family', () => {
    const parts = replay([
      { type: 'THINKING_START' },
      { type: 'THINKING_TEXT_MESSAGE_START' },
      { type: 'THINKING_TEXT_MESSAGE_CONTENT', delta: 'Let me ' },
      { type: 'THINKING_TEXT_MESSAGE_CONTENT', delta: 'think.' },
      { type: 'THINKING_TEXT_MESSAGE_END' },
      { type: 'THINKING_END' },
    ]);

    expect(parts).toEqual([{ type: 'reasoning', text: 'Let me think.' }]);
  });

  it('opens a part for REASONING_MESSAGE_CHUNK, which carries no start event', () => {
    const parts = replay([{ type: 'REASONING_MESSAGE_CHUNK', delta: 'Thinking.' }]);

    expect(parts).toEqual([{ type: 'reasoning', text: 'Thinking.' }]);
  });

  it('counts a streamed thought as visible output, so the turn leaves its thinking state', () => {
    // The whole point: this is what un-collapses the message and reveals the
    // stream while the model is still reasoning.
    const beforeAnyDelta = replay([{ type: 'REASONING_START' }]);
    expect(hasStreamedOutput(beforeAnyDelta)).toBe(false);

    const afterFirstDelta = replay([
      { type: 'REASONING_START' },
      { type: 'REASONING_MESSAGE_CONTENT', delta: 'Let me think.' },
    ]);
    expect(hasStreamedOutput(afterFirstDelta)).toBe(true);
  });

  it('ignores the encrypted reasoning blob, which carries nothing displayable', () => {
    const parts = replay([
      { type: 'REASONING_START' },
      { type: 'REASONING_MESSAGE_CONTENT', delta: 'Let me think.' },
      { type: 'REASONING_ENCRYPTED_VALUE' },
    ]);

    expect(parts).toEqual([{ type: 'reasoning', text: 'Let me think.' }]);
  });
});
