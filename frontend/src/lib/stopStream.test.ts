import { describe, expect, it, vi } from 'vitest';
import { requestStopTurn } from './stopStream';

function response(status: number, body?: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: '',
    json: async () => {
      if (body === undefined) throw new Error('no body');
      return body;
    },
  } as Response;
}

describe('requestStopTurn', () => {
  it('accepts a stop the backend took, so the caller waits for STREAM_END', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response(200));
    await expect(requestStopTurn('/api', 'c1', 'User requested stop', fetchImpl)).resolves.toEqual({
      accepted: true,
    });
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe('/api/chat/stop');
    expect(JSON.parse(init.body)).toEqual({ chat_id: 'c1', reason: 'User requested stop' });
  });

  it('does not wait on a stop that only reached background sub-agents', async () => {
    // A chat paused on tool approval has no parent control handle left, so the
    // 200 is about the sub-agents and no STREAM_END is coming for the turn.
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(response(200, { status: 'stopping', stream_stopped: false }));
    await expect(requestStopTurn('/api', 'c1', 'stop', fetchImpl)).resolves.toEqual({
      accepted: false,
      reason: 'no_active_stream',
      status: 200,
    });
  });

  it('still waits when the backend says it stopped the turn itself', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(response(200, { status: 'stopping', stream_stopped: true }));
    await expect(requestStopTurn('/api', 'c1', 'stop', fetchImpl)).resolves.toEqual({
      accepted: true,
    });
  });

  it('reports a 404 as no active stream rather than an error', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response(404));
    await expect(requestStopTurn('/api', 'c1', 'stop', fetchImpl)).resolves.toEqual({
      accepted: false,
      reason: 'no_active_stream',
      status: 404,
    });
  });

  it('does not wait on a stream ending after a failed request', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response(500));
    await expect(requestStopTurn('/api', 'c1', 'stop', fetchImpl)).resolves.toEqual({
      accepted: false,
      reason: 'error',
      status: 500,
    });
  });

  it('treats a dropped request the same way', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new Error('offline'));
    await expect(requestStopTurn('/api', 'c1', 'stop', fetchImpl)).resolves.toEqual({
      accepted: false,
      reason: 'network',
    });
  });
});
