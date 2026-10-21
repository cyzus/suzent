import { afterEach, describe, expect, it, vi } from 'vitest';
import { cancelAcpLogin, fetchAcpLogins, isLoginActive, startAcpLogin } from './acpLogin';
import type { AcpLoginState } from './acpLogin';

vi.mock('./api', () => ({ getApiBase: () => 'http://localhost:25314' }));
afterEach(() => vi.unstubAllGlobals());

describe('ACP login jobs', () => {
  it('starts the selected method and cancels the same encoded agent', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ status: 'starting' }) });
    vi.stubGlobal('fetch', fetch);
    await startAcpLogin('agent/1', 'oauth');
    expect(fetch).toHaveBeenCalledWith('http://localhost:25314/acp/agents/agent%2F1/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{"method_id":"oauth"}',
    });
    await cancelAcpLogin('agent/1');
    expect(fetch.mock.calls[1][0]).toBe('http://localhost:25314/acp/agents/agent%2F1/login');
    expect(fetch.mock.calls[1][1].method).toBe('DELETE');
  });

  it('does not surface credential-bearing server errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, json: async () => ({ error: 'secret' }) })
    );
    await expect(fetchAcpLogins()).rejects.toThrow('ACP login request failed');
  });

  it.each([
    'starting',
    'authenticating',
    'terminal',
    'verifying',
    'ready',
    'failed',
    'cancelled',
    'idle',
  ] as const)('keeps controls busy only while %s is active', (status) => {
    const state: AcpLoginState = { attempt: 1, status, error: null, result: null };
    expect(isLoginActive(state)).toBe(
      ['starting', 'authenticating', 'terminal', 'verifying'].includes(status)
    );
  });
});
