import { describe, expect, it } from 'vitest';
import { parseChunk } from './useSubAgentActivity';

describe('parseChunk', () => {
  it('reads one encoded event out of a bus chunk', () => {
    const raw = 'data: {"type":"TOOL_CALL_START","toolCallId":"c1","toolCallName":"grep"}\n\n';
    expect(parseChunk(raw)).toEqual([
      { type: 'TOOL_CALL_START', toolCallId: 'c1', toolCallName: 'grep' },
    ]);
  });

  it('reads every event when a chunk carries more than one', () => {
    const raw =
      'data: {"type":"TOOL_CALL_START","toolCallId":"c1"}\n' +
      'data: {"type":"TOOL_CALL_RESULT","toolCallId":"c1"}\n\n';
    expect(parseChunk(raw).map((e) => e.type)).toEqual(['TOOL_CALL_START', 'TOOL_CALL_RESULT']);
  });

  it('accepts the tuple shape push_custom_event puts on the same queue', () => {
    const raw = ['chunk', 'data: {"type":"TOOL_CALL_START","toolCallId":"c1"}\n\n'];
    expect(parseChunk(raw)).toHaveLength(1);
  });

  it('skips a frame that is not valid JSON rather than throwing', () => {
    expect(parseChunk('data: {broken\n\n')).toEqual([]);
  });

  it('ignores non-data lines and empty input', () => {
    expect(parseChunk('event: ping\n\n')).toEqual([]);
    expect(parseChunk('')).toEqual([]);
    expect(parseChunk(undefined)).toEqual([]);
  });
});

describe('absorbed-message events', () => {
  it('reads the enqueue id off the custom event a run emits', () => {
    const raw =
      'data: {"type":"CUSTOM","name":"agent_absorbed_message","value":{"enqueue_id":"enq-3"}}\n\n';
    const [event] = parseChunk(raw);
    expect(event.name).toBe('agent_absorbed_message');
    expect((event.value as { enqueue_id: string }).enqueue_id).toBe('enq-3');
  });
});
