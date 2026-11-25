import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  desktopShell,
  invoke,
  isDesktop,
  listen,
  openUrl,
  registerGlobalShortcut,
} from './desktop';

function electronBridge() {
  const handlers = new Map<string, (payload: unknown) => void>();
  return {
    handlers,
    bridge: {
      platform: 'win32',
      invoke: vi.fn(async (command: string) => (command === 'get_backend_port' ? 4242 : undefined)),
      on: vi.fn((name: string, handler: (payload: unknown) => void) => {
        handlers.set(name, handler);
        return () => handlers.delete(name);
      }),
      openExternal: vi.fn(async () => undefined),
      registerShortcut: vi.fn(async () => true),
      unregisterShortcut: vi.fn(async () => undefined),
      onShortcut: vi.fn((handler: (accelerator: string) => void) => {
        handlers.set('shortcut-pressed', (payload) => handler(String(payload)));
        return () => handlers.delete('shortcut-pressed');
      }),
    },
  };
}

describe('desktop bridge', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('tells the shells and the browser apart', () => {
    vi.stubGlobal('window', {});
    expect(desktopShell()).toBeNull();
    expect(isDesktop()).toBe(false);
    vi.stubGlobal('window', { __TAURI__: {} });
    expect(desktopShell()).toBe('tauri');
    vi.stubGlobal('window', { suzentDesktop: electronBridge().bridge, __TAURI__: {} });
    expect(desktopShell()).toBe('electron');
  });

  it('routes commands and events through the Electron preload', async () => {
    const { bridge, handlers } = electronBridge();
    vi.stubGlobal('window', { suzentDesktop: bridge });
    await expect(invoke<number>('get_backend_port')).resolves.toBe(4242);
    const seen: number[] = [];
    const stop = await listen<number>('backend-ready', (port) => seen.push(port));
    handlers.get('backend-ready')?.(7);
    stop();
    expect(seen).toEqual([7]);
    expect(handlers.has('backend-ready')).toBe(false);
  });

  it('opens links in the system browser on desktop and a tab otherwise', async () => {
    const { bridge } = electronBridge();
    const open = vi.fn();
    vi.stubGlobal('window', { suzentDesktop: bridge, open });
    await openUrl('https://suzent.com');
    expect(bridge.openExternal).toHaveBeenCalledWith('https://suzent.com');
    expect(open).not.toHaveBeenCalled();

    vi.stubGlobal('window', { open });
    await openUrl('https://suzent.com');
    expect(open).toHaveBeenCalledWith('https://suzent.com', '_blank', 'noopener,noreferrer');
  });

  it('fires a global shortcut only for its own accelerator', async () => {
    const { bridge, handlers } = electronBridge();
    vi.stubGlobal('window', { suzentDesktop: bridge });
    const pressed = vi.fn();
    const stop = await registerGlobalShortcut('Alt+Space', pressed);
    handlers.get('shortcut-pressed')?.('Ctrl+K');
    handlers.get('shortcut-pressed')?.('Alt+Space');
    expect(pressed).toHaveBeenCalledTimes(1);
    stop();
    expect(bridge.unregisterShortcut).toHaveBeenCalledWith('Alt+Space');
  });

  it('reports a taken shortcut', async () => {
    const { bridge } = electronBridge();
    bridge.registerShortcut.mockResolvedValueOnce(false);
    vi.stubGlobal('window', { suzentDesktop: bridge });
    await expect(registerGlobalShortcut('Alt+Space', () => undefined)).rejects.toThrow(/taken/);
  });
});
