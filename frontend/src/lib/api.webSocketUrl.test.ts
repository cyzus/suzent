import { afterEach, describe, expect, it, vi } from 'vitest';

import { getWebSocketUrl } from './api';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('getWebSocketUrl', () => {
  it('drops the hash route of a served web console', () => {
    vi.stubEnv('DEV', false);
    const page = new URL('https://suzent.example:8443/#/settings?tab=voice');
    vi.stubGlobal('window', { location: page });

    const url = getWebSocketUrl('/ws/voice');

    expect(url.hash).toBe('');
    expect(url.search).toBe('');
    expect(url.pathname).toBe('/ws/voice');
    expect(url.protocol).toBe('wss:');
    expect(url.host).toBe('suzent.example:8443');
    expect(() => new URL(url.toString())).not.toThrow();
    expect(url.toString()).not.toContain('#');
  });

  it('uses the named backend in dev', () => {
    vi.stubEnv('DEV', true);
    vi.stubEnv('VITE_SUZENT_BACKEND', 'https://suzent.example');

    expect(getWebSocketUrl('/ws/browser').toString()).toBe('wss://suzent.example/ws/browser');
  });
});
