/**
 * Bearer token for a browser that is not on the backend's machine.
 *
 * Loopback callers are trusted by AuthBoundaryMiddleware, so the desktop app
 * and a browser on the same machine need none of this. A browser reaching the
 * backend across the network is a remote caller like any other device: it has
 * to present a host-scope token, which the operator mints (POST /nodes/host-token)
 * and hands over once, as `?token=` on the URL.
 *
 * The token is stripped from the address bar immediately and kept in
 * localStorage, so it is not left in history, bookmarks, or a Referer header.
 */

import { getApiBase } from './api';

const STORAGE_KEY = 'suzent.auth_token';

let cached: string | null = null;

function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    // Private mode or blocked storage: fall back to memory for this tab only.
    return null;
  }
}

/** Consume `?token=` from the URL, if present, and persist it. */
export function captureAuthTokenFromUrl(): void {
  const url = new URL(window.location.href);
  const token = url.searchParams.get('token');
  if (!token) {
    cached = readStored();
    return;
  }
  cached = token;
  try {
    window.localStorage.setItem(STORAGE_KEY, token);
  } catch {
    // Keeping it in memory still gets this tab through the session.
  }
  url.searchParams.delete('token');
  window.history.replaceState({}, '', url.toString());
}

export function getAuthToken(): string | null {
  if (cached === null) cached = readStored();
  return cached;
}

export function clearAuthToken(): void {
  cached = null;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to clear.
  }
}

/**
 * Append the token to a URL that cannot carry a header.
 *
 * `EventSource` has no way to set `Authorization`, so the two SSE endpoints
 * accept the token as a query parameter. Everything else uses the header.
 */
export function withAuthQuery(url: string): string {
  const token = getAuthToken();
  if (!token) return url;
  return `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`;
}

/**
 * Attach the token to every same-backend `fetch`.
 *
 * There are ~200 raw `fetch` call sites and no central client, so the header is
 * installed once here rather than threaded through each one. Requests that
 * already set an Authorization header (there are none today, but a future
 * caller might) are left alone.
 */
export function installAuthenticatedFetch(): void {
  const original = window.fetch.bind(window);
  const backendOrigin = new URL(getApiBase() || window.location.origin, window.location.href)
    .origin;

  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    const token = getAuthToken();
    if (!token) return original(input, init);

    // Never send our credential anywhere but the backend it belongs to.
    const target = input instanceof Request ? input.url : String(input);
    let targetOrigin: string;
    try {
      targetOrigin = new URL(target, window.location.href).origin;
    } catch {
      return original(input, init);
    }
    if (targetOrigin !== backendOrigin) return original(input, init);

    const headers = new Headers(
      init?.headers ?? (input instanceof Request ? input.headers : undefined)
    );
    if (!headers.has('Authorization') && !headers.has('X-Suzent-Token')) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    return original(input, { ...init, headers });
  };
}
