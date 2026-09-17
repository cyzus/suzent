import { afterEach, describe, expect, it, vi } from 'vitest';
import { isDesktop, isWeb } from './runtime';

describe('runtime host detection', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('treats a window without Tauri internals as web', () => {
    vi.stubGlobal('window', {});
    expect(isWeb()).toBe(true);
    expect(isDesktop()).toBe(false);
  });

  it('treats an injected __TAURI__ as desktop', () => {
    vi.stubGlobal('window', { __TAURI__: { window: {} } });
    expect(isDesktop()).toBe(true);
    expect(isWeb()).toBe(false);
  });
});
