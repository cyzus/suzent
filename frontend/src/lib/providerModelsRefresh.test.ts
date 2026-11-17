import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const refresh = vi.fn();
let apiBase = 'http://a';

vi.mock('./api', () => ({
  getApiBase: () => apiBase,
  refreshAllProviderModels: () => refresh(),
}));

const {
  AUTO_REFRESH_TTL_MS,
  autoRefreshProviderModels,
  forceRefreshProviderModels,
  markProviderModelsSuperseded,
  resetProviderModelsRefreshForTests,
  syncCachedStarredModels,
} = await import('./providerModelsRefresh');

const ok = { success: true, models: ['m1'], starredModels: [] };

describe('providerModelsRefresh', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    refresh.mockReset();
    refresh.mockResolvedValue(ok);
    apiBase = 'http://a';
    resetProviderModelsRefreshForTests();
  });
  afterEach(() => vi.useRealTimers());

  it('runs discovery once across remounts within the TTL', async () => {
    const first = autoRefreshProviderModels();
    const second = autoRefreshProviderModels();
    expect(second).toBe(first);
    await first;
    expect(await autoRefreshProviderModels()).toEqual(ok);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('runs again once the TTL has passed', async () => {
    await autoRefreshProviderModels();
    vi.advanceTimersByTime(AUTO_REFRESH_TTL_MS + 1);
    await autoRefreshProviderModels();
    expect(refresh).toHaveBeenCalledTimes(2);
  });

  it('retries after a failed refresh', async () => {
    refresh.mockResolvedValueOnce({ success: false, error: 'x' });
    await autoRefreshProviderModels();
    await autoRefreshProviderModels();
    expect(refresh).toHaveBeenCalledTimes(2);
  });

  it('keys the record by backend', async () => {
    await autoRefreshProviderModels();
    apiBase = 'http://b';
    await autoRefreshProviderModels();
    expect(refresh).toHaveBeenCalledTimes(2);
  });

  it('returns nothing once a config listing supersedes a settled result', async () => {
    await autoRefreshProviderModels();
    markProviderModelsSuperseded();
    expect(autoRefreshProviderModels()).toBeNull();
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('does not supersede a refresh still in flight', async () => {
    const pending = autoRefreshProviderModels();
    markProviderModelsSuperseded();
    expect(autoRefreshProviderModels()).toBe(pending);
  });

  it('replays starred models changed after discovery', async () => {
    await autoRefreshProviderModels();
    syncCachedStarredModels(['m1']);
    expect((await autoRefreshProviderModels())?.starredModels).toEqual(['m1']);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('forced refresh joins an in-flight one, otherwise starts anew', async () => {
    const pending = autoRefreshProviderModels();
    expect(forceRefreshProviderModels()).toBe(pending);
    await pending;
    await forceRefreshProviderModels();
    expect(refresh).toHaveBeenCalledTimes(2);
  });
});
