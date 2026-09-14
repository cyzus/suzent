import { processEvent } from '../hooks/useAGUI';
import type { AGUIPart } from '../types/agui';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { recoverableStream, type StreamBatch } from './recoverableStream';

const snapshot = (seq = 1, run_id = 'run', text = 'hello') => ({
  type: 'STREAM_SNAPSHOT',
  run_id,
  seq,
  events: [{ type: 'TEXT_MESSAGE_CONTENT', delta: text }],
});
const event = (seq: number, delta: string) => ({
  type: 'STREAM_EVENT',
  run_id: 'run',
  seq,
  event: { type: 'TEXT_MESSAGE_CONTENT', delta },
});
const end = (seq: number, run_id = 'run', persisted = true) => ({
  type: 'STREAM_END',
  run_id,
  seq,
  persisted,
});
function response(...frames: unknown[]): Response {
  const bytes = new TextEncoder().encode(
    frames.map((f) => `data: ${JSON.stringify(f)}\n\n`).join('')
  );
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
        controller.close();
      },
    })
  );
}
async function collect(
  signal = new AbortController().signal,
  onStart = vi.fn()
): Promise<StreamBatch[]> {
  const batches: StreamBatch[] = [];
  for await (const batch of recoverableStream('/chat/live', { chat_id: 'chat' }, signal, onStart)) {
    batches.push(batch);
  }
  return batches;
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('recoverable streaming transport', () => {
  it('replaces local content from snapshot then applies live events', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(response(snapshot(1, 'run', '你好'), event(2, '!'), end(2)))
    );
    const batches = await collect();
    expect(batches.map((b) => [b.reset, b.events[0].delta])).toEqual([
      [true, '你好'],
      [false, '!'],
    ]);
  });
  it('reconnects an unexpected EOF from the last applied cursor and ignores duplicates', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response(snapshot(), event(2, ' world')))
      .mockResolvedValueOnce(response(event(2, ' world'), event(3, '!'), end(3)));
    vi.stubGlobal('fetch', fetch);
    const batches = await collect();
    expect(batches.flatMap((b) => b.events.map((e) => e.delta))).toEqual(['hello', ' world', '!']);
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({ run_id: 'run', after_seq: 2 });
  });
  it('asks for a snapshot on a sequence gap instead of appending missing content', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response(snapshot(), event(3, 'bad suffix')))
      .mockResolvedValueOnce(response(snapshot(3, 'run', 'complete'), end(3)));
    vi.stubGlobal('fetch', fetch);
    const batches = await collect();
    expect(batches.map((b) => b.reset)).toEqual([true, true]);
    expect(JSON.parse(fetch.mock.calls[1][1].body)).not.toHaveProperty('run_id');
    expect(batches[1].events[0].delta).toBe('complete');
  });
  it('accepts a reset when a new run replaces the old run', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(response(snapshot()))
        .mockResolvedValueOnce(response(snapshot(1, 'new-run', 'new'), end(1, 'new-run')))
    );
    expect((await collect())[1]).toMatchObject({ reset: true, events: [{ delta: 'new' }] });
  });
  it('does not report a failed save as completion', async () => {
    const fetch = vi.fn().mockResolvedValue(response(snapshot(), end(1, 'run', false)));
    vi.stubGlobal('fetch', fetch);
    await expect(collect()).rejects.toThrow('persistence failed');
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('does not restart a send or report success when the retained run disappears', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response(snapshot()))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetch);
    await expect(collect()).rejects.toThrow('no longer available');
    expect(fetch.mock.calls.every(([url]) => url === '/chat/live')).toBe(true);
  });
  it('returns without starting on an idle probe', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    const onStart = vi.fn();
    expect(await collect(undefined, onStart)).toEqual([]);
    expect(onStart).not.toHaveBeenCalled();
  });
  it('stops reconnecting when the user changes chats', async () => {
    const controller = new AbortController();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => {
        controller.abort();
        throw new DOMException('Aborted', 'AbortError');
      })
    );
    await expect(collect(controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

it('starts a turn only once when the acknowledgement is lost', async () => {
  const fetch = vi
    .fn()
    .mockRejectedValueOnce(new TypeError('Failed to fetch'))
    .mockResolvedValueOnce(response(snapshot(), end(1)));
  vi.stubGlobal('fetch', fetch);
  for await (const _batch of recoverableStream(
    '/chat/live',
    { chat_id: 'chat' },
    new AbortController().signal,
    vi.fn(),
    {
      url: '/chat',
      body: { chat_id: 'chat', message: 'send once' },
    }
  )) {
    /* drain */
  }
  expect(fetch.mock.calls.map(([url]) => url)).toEqual(['/chat', '/chat/live']);
  expect(JSON.parse(fetch.mock.calls[1][1].body)).not.toHaveProperty('message');
});

it('follows an explicit supersession without finalizing the replaced run', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValueOnce(response(snapshot(), { ...end(1, 'run', false), superseded: true }))
      .mockResolvedValueOnce(response(snapshot(1, 'next', 'replacement'), end(1, 'next')))
  );
  const onStart = vi.fn();
  const batches = await collect(undefined, onStart);
  expect(batches[1].events[0].delta).toBe('replacement');
  expect(onStart).toHaveBeenCalledTimes(2);
});

it('reconstructs text, reasoning and tools from a snapshot without using a stale local seed', async () => {
  const events = [
    { type: 'REASONING_MESSAGE_CHUNK', delta: 'thinking' },
    { type: 'TEXT_MESSAGE_START', messageId: 'm' },
    { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'before' },
    { type: 'TOOL_CALL_START', toolCallId: 't', toolCallName: 'read_file' },
    { type: 'TOOL_CALL_ARGS', toolCallId: 't', delta: '{"path":"file"}' },
    {
      type: 'CUSTOM',
      name: 'tool_approval_request',
      value: { toolCallId: 't', approvalId: 't', toolName: 'read_file' },
    },
  ];
  const result = {
    type: 'CUSTOM',
    name: 'tool_approval_result',
    value: { toolCallId: 't', toolName: 'read_file', status: 'executed', output: 'contents' },
  };
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        response({ ...snapshot(6), events }, { ...event(7, ''), event: result }, end(7))
      )
  );
  let parts: AGUIPart[] = [{ type: 'text', text: 'stale local text', messageId: 'old' }];
  for (const batch of await collect()) {
    if (batch.reset) parts = [];
    for (const data of batch.events) parts = processEvent({ type: data.type, data }, parts).parts;
  }
  expect(parts.filter((p) => p.type === 'text').map((p) => p.text)).toEqual(['before']);
  expect(parts.find((p) => p.type === 'reasoning')?.text).toBe('thinking');
  const tool = parts.find((p) => p.type === 'tool');
  expect(tool).toMatchObject({ toolCallId: 't', state: 'completed', output: 'contents' });
  expect(tool?.approvalId).toBeUndefined();
});
