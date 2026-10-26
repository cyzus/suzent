import { afterEach, describe, expect, it, vi } from 'vitest';
import { decideAcpPairing, fetchAcpPairing, revokeAcpGrant } from './acpPairing';

vi.mock('./api', () => ({ getApiBase: () => 'http://localhost:25314' }));
afterEach(() => vi.unstubAllGlobals());

describe('ACP editor approvals', () => {
  it('sends explicit approval decisions and encodes request IDs', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    vi.stubGlobal('fetch', fetch);
    await decideAcpPairing('id/1', false);
    expect(fetch).toHaveBeenCalledWith('http://localhost:25314/acp/auth/requests/id%2F1/decide', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{"approved":false}',
    });
    await revokeAcpGrant('grant');
    expect(fetch.mock.calls[1][0]).toBe('http://localhost:25314/acp/auth/grants/grant');
    expect(fetch.mock.calls[1][1].method).toBe('DELETE');
  });

  it('surfaces a refused local approval request', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, json: async () => ({ detail: 'Local only' }) })
    );
    await expect(fetchAcpPairing()).rejects.toThrow('Local only');
  });
});
