import { describe, expect, it } from 'vitest';
import { applyActivityEvent, parseChunk, type SubAgentActivity } from './useSubAgentActivity';

const EMPTY: SubAgentActivity = { entries: [], phase: null };

/** Fold a script of events the way the bus subscription does. */
function run(events: Record<string, unknown>[], from: SubAgentActivity = EMPTY) {
  return events.reduce(applyActivityEvent, from);
}

const start = (id: string, name = 'run_command') => ({
  type: 'TOOL_CALL_START',
  toolCallId: id,
  toolCallName: name,
});
const args = (id: string, delta: string) => ({ type: 'TOOL_CALL_ARGS', toolCallId: id, delta });
const result = (id: string) => ({ type: 'TOOL_CALL_RESULT', toolCallId: id, content: 'ok' });

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

  it('reads the enqueue id off the absorbed-message event', () => {
    const raw =
      'data: {"type":"CUSTOM","name":"agent_absorbed_message","value":{"enqueue_id":"enq-3"}}\n\n';
    const [event] = parseChunk(raw);
    expect((event.value as { enqueue_id: string }).enqueue_id).toBe('enq-3');
  });
});

describe('tool calls', () => {
  it('records a call and marks it running', () => {
    expect(run([start('c1')]).entries).toEqual([
      { toolCallId: 'c1', toolName: 'run_command', args: '', done: false },
    ]);
  });

  it('accumulates streamed argument fragments', () => {
    const state = run([start('c1'), args('c1', '{"content":'), args('c1', '"npm test"}')]);
    expect(state.entries[0].args).toBe('{"content":"npm test"}');
  });

  it('finishes a call only on its result', () => {
    // TOOL_CALL_END fires when the args are written, before the tool has run.
    const afterEnd = run([start('c1'), { type: 'TOOL_CALL_END', toolCallId: 'c1' }]);
    expect(afterEnd.entries[0].done).toBe(false);

    expect(run([start('c1'), result('c1')]).entries[0].done).toBe(true);
  });

  it('keeps parallel calls apart', () => {
    const state = run([
      start('c1', 'grep'),
      start('c2', 'read_file'),
      args('c2', '{"path":"a"}'),
      result('c1'),
    ]);
    expect(state.entries.map((e) => [e.toolName, e.done])).toEqual([
      ['grep', true],
      ['read_file', false],
    ]);
    expect(state.entries[1].args).toBe('{"path":"a"}');
  });

  it('ignores a duplicate start for a call already tracked', () => {
    expect(run([start('c1'), start('c1')]).entries).toHaveLength(1);
  });

  it('keeps only the newest few calls', () => {
    const state = run(Array.from({ length: 9 }, (_, i) => start(`c${i}`)));
    expect(state.entries).toHaveLength(5);
    expect(state.entries[4].toolCallId).toBe('c8');
  });

  it('ignores tool events with no call id to attach to', () => {
    expect(run([{ type: 'TOOL_CALL_ARGS', delta: 'x' }])).toEqual(EMPTY);
  });
});

describe('phase between tool calls', () => {
  it('shows thinking while the child reasons', () => {
    expect(run([{ type: 'THINKING_START' }]).phase).toBe('thinking');
    expect(run([{ type: 'REASONING_MESSAGE_START' }]).phase).toBe('thinking');
  });

  it('clears when the reasoning ends', () => {
    expect(run([{ type: 'THINKING_START' }, { type: 'THINKING_END' }]).phase).toBeNull();
  });

  it('shows responding while the child writes', () => {
    expect(run([{ type: 'TEXT_MESSAGE_START' }]).phase).toBe('responding');
    expect(run([{ type: 'TEXT_MESSAGE_START' }, { type: 'TEXT_MESSAGE_END' }]).phase).toBeNull();
  });

  it('clears when a tool call takes over', () => {
    expect(run([{ type: 'THINKING_START' }, start('c1')]).phase).toBeNull();
  });

  it('clears when the run ends', () => {
    expect(run([{ type: 'THINKING_START' }, { type: 'AGENT_FINISHED' }]).phase).toBeNull();
    expect(run([{ type: 'THINKING_START' }, { type: 'RUN_ERROR' }]).phase).toBeNull();
  });
});
