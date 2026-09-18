import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchOpsStatus, OpsError, restartOpsService, setOpsServiceEnabled } from './opsApi';

function mockFetch(status: number, body: unknown): void {
  // `getApiBase` reads window to find the Tauri-injected backend port.
  vi.stubGlobal('window', {});
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      json: async () => body,
    })
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('fetchOpsStatus', () => {
  it('maps the backend snake_case contract', async () => {
    mockFetch(200, {
      installed: true,
      autostart: true,
      running: true,
      ready: true,
      pid: 4321,
      port: 25314,
      version: '1.2.3',
      uptime_seconds: 61,
      rss_bytes: 1024,
      error: null,
      self_managed: true,
      log_path: '/var/suzent/server.log',
      log_available: true,
    });

    const status = await fetchOpsStatus();
    expect(status.uptimeSeconds).toBe(61);
    expect(status.rssBytes).toBe(1024);
    expect(status.selfManaged).toBe(true);
    expect(status.logPath).toBe('/var/suzent/server.log');
  });

  it('treats missing numeric fields as null rather than 0', async () => {
    // A stopped service reports no pid or uptime; 0 would render as a real
    // reading ("0m uptime") instead of "no data".
    mockFetch(200, { installed: true, running: false, ready: false });
    const status = await fetchOpsStatus();
    expect(status.pid).toBeNull();
    expect(status.uptimeSeconds).toBeNull();
    expect(status.selfManaged).toBe(false);
  });
});

describe('restartOpsService', () => {
  it('returns null for a deferred self-restart', async () => {
    // 202 means the host is about to go away, so there is no status to report
    // and the caller must poll instead of trusting a stale one.
    mockFetch(202, { status: 'restarting', self_managed: true });
    expect(await restartOpsService()).toBeNull();
  });

  it('returns the fresh status when the service is another process', async () => {
    mockFetch(200, { installed: true, running: true, ready: true, pid: 99 });
    const status = await restartOpsService();
    expect(status?.pid).toBe(99);
  });

  it('raises the backend error code for a service that is not installed', async () => {
    mockFetch(409, { error: 'service_not_installed' });
    await expect(restartOpsService()).rejects.toMatchObject({
      code: 'service_not_installed',
      status: 409,
    });
  });
});

describe('setOpsServiceEnabled', () => {
  it('surfaces the self-disable refusal as a typed error', async () => {
    mockFetch(409, { error: 'would_disable_self', detail: 'This service is serving the console.' });
    const failure = await setOpsServiceEnabled(false).catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(OpsError);
    expect((failure as OpsError).code).toBe('would_disable_self');
  });

  it('survives a non-JSON error body', async () => {
    // A proxy in front of a dying host answers with HTML, not JSON.
    vi.stubGlobal('window', {});
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => {
          throw new SyntaxError('Unexpected token <');
        },
      })
    );
    const failure = await setOpsServiceEnabled(true).catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(OpsError);
    expect((failure as OpsError).message).toBe('HTTP 502');
    expect((failure as OpsError).code).toBeNull();
  });
});
