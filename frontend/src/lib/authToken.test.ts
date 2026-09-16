import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  captureAuthTokenFromUrl,
  clearAuthToken,
  getAuthToken,
  installAuthenticatedFetch,
  withAuthQuery,
} from './authToken';

function stubWindow(href: string) {
  const store = new Map<string, string>();
  const replaceState = vi.fn();
  vi.stubGlobal('window', {
    location: { href, origin: new URL(href).origin },
    history: { replaceState },
    localStorage: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => store.set(k, v),
      removeItem: (k: string) => store.delete(k),
    },
    fetch: vi.fn(async () => ({ ok: true })),
  });
  return replaceState;
}

describe('auth token', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    clearAuthToken();
  });

  it('consumes ?token= and strips it from the address bar', () => {
    const replaceState = stubWindow('http://suzent.example/?token=secret&keep=1');
    captureAuthTokenFromUrl();

    expect(getAuthToken()).toBe('secret');
    const rewritten = String(replaceState.mock.calls[0][2]);
    expect(rewritten).not.toContain('secret');
    expect(rewritten).toContain('keep=1');
  });

  it('appends the token only where a header is impossible', () => {
    stubWindow('http://suzent.example/?token=secret');
    captureAuthTokenFromUrl();

    expect(withAuthQuery('/events/stream')).toBe('/events/stream?token=secret');
    expect(withAuthQuery('/events/stream?a=1')).toBe('/events/stream?a=1&token=secret');
  });

  it('never sends the token to a foreign origin', async () => {
    // getApiBase() names 127.0.0.1:8000 under Vite dev, which is what vitest
    // reports, so that is the backend origin this wrapper will trust.
    stubWindow('http://127.0.0.1:8000/?token=secret');
    captureAuthTokenFromUrl();

    const original = (window as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch;
    installAuthenticatedFetch();

    await window.fetch('http://127.0.0.1:8000/config');
    await window.fetch('https://api.openai.com/v1/models');

    const [[, ours], [, theirs]] = original.mock.calls;
    expect(new Headers(ours?.headers).get('Authorization')).toBe('Bearer secret');
    expect(theirs?.headers).toBeUndefined();
  });
});
