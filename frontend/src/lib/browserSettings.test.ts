import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./api', () => ({ getApiBase: () => 'http://localhost:8000' }));
import {
  browserChannelOptions,
  fetchBrowserSettings,
  saveBrowserSettings,
} from './browserSettings';

afterEach(() => vi.unstubAllGlobals());

describe('browser settings API', () => {
  it('posts only the changed preference without copying effective overrides', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal('fetch', fetch);
    await saveBrowserSettings({ persistent: true });
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ persistent: true });
  });
  it('disables missing browsers with a hint and keeps Chromium selectable', () => {
    const options = browserChannelOptions(
      { chromium: true, chrome: false, msedge: false },
      (key) => key
    );
    expect(options.map(({ value, disabled }) => ({ value, disabled }))).toEqual([
      { value: 'chromium', disabled: false },
      { value: 'chrome', disabled: true },
      { value: 'msedge', disabled: true },
    ]);
    expect(options[1].hint).toBe('settings.browser.notInstalled');
    const refreshed = browserChannelOptions(
      { chromium: true, chrome: true, msedge: false },
      (key) => key
    );
    expect(refreshed[1].disabled).toBe(false);
    expect(refreshed[1].hint).toBeUndefined();
  });
  it('persists visible-window and profile preferences on the backend', async () => {
    const settings = { persistent: true, headless: false, channel: 'msedge' as const };
    const response = { settings, environment_overrides: [] };
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => response });
    vi.stubGlobal('fetch', fetch);
    expect(await saveBrowserSettings(settings)).toEqual(response);
    expect(fetch).toHaveBeenCalledWith('http://localhost:8000/browser/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    });
  });

  it('loads effective preferences and environment overrides', async () => {
    const response = {
      settings: { persistent: false, headless: true, channel: 'chrome' },
      environment_overrides: ['channel'],
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => response }));
    expect(await fetchBrowserSettings()).toEqual(response);
  });

  it('rejects failed saves so the UI cannot report success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    await expect(
      saveBrowserSettings({ persistent: false, headless: true, channel: 'chrome' })
    ).rejects.toThrow();
  });
});
