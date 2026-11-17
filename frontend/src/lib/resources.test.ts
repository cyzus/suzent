import { afterEach, describe, expect, it, vi } from 'vitest';
import { createResourceClient } from './resources';
import { resourcePaths, resourceRequests } from './resourceAPI.generated';

afterEach(() => vi.unstubAllGlobals());

describe('shared resource transport', () => {
  it('uses the selected backend at request time and preserves JSON boolean intent', async () => {
    const fetcher = vi
      .fn()
      .mockImplementation(
        async () => new Response(JSON.stringify({ models: [], starredModels: [], canManage: true }))
      );
    vi.stubGlobal('fetch', fetcher);
    let backend = 'https://first.example';
    const api = createResourceClient(() => backend);
    await api.models();
    backend = 'https://second.example';
    await api.starModel({ model: 'openrouter/org/model', starred: false });
    expect(fetcher.mock.calls[0][0]).toBe('https://first.example/api/v1/models');
    expect(fetcher.mock.calls[1][0]).toBe('https://second.example/api/v1/models/star');
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({
      model: 'openrouter/org/model',
      starred: false,
    });
  });

  it('serializes generated query parameters without adding a request body', async () => {
    const fetcher = vi
      .fn()
      .mockImplementation(async () => new Response(JSON.stringify({ id: 'chat', title: 'Chat' })));
    vi.stubGlobal('fetch', fetcher);
    await createResourceClient(() => '').chat('chat', { include_models: false });
    expect(fetcher.mock.calls[0][0]).toBe('/api/v1/chats/chat?include_models=false');
    expect(fetcher.mock.calls[0][1].body).toBeUndefined();
  });

  it('does not retry an ambiguous mutation', async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError('connection lost'));
    vi.stubGlobal('fetch', fetcher);
    await expect(createResourceClient(() => '').refreshModels({})).rejects.toThrow(
      'connection lost'
    );
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('keeps opaque IDs in one path segment and rejects traversal', () => {
    expect(resourcePaths.chat('chat + 中文%2F')).toBe(
      '/api/v1/chats/chat%20%2B%20%E4%B8%AD%E6%96%87%252F'
    );
    for (const id of ['', '.', '..', 'one/two']) expect(() => resourcePaths.chat(id)).toThrow();
    expect(resourceRequests.chatPage({ kind: 'search', offset: 30, limit: 50 }).body).toEqual({
      kind: 'search',
      offset: 30,
      limit: 50,
    });
  });
});
