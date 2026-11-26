/**
 * The one way the UI talks to the desktop shell.
 *
 * Two shells host this bundle while Suzent moves from Tauri to Electron. The
 * Electron preload exposes `window.suzentDesktop`; Tauri exposes
 * `window.__TAURI__` and its `@tauri-apps/*` packages. Both answer the same
 * command names, so callers never branch on the shell. In a plain browser
 * every function here is unavailable: gate calls on `isDesktop()`.
 */

export type Unlisten = () => void;

export interface OpenDialogOptions {
  directory?: boolean;
  multiple?: boolean;
  title?: string;
  defaultPath?: string;
}

export interface ElectronDesktopBridge {
  platform: string;
  invoke(command: string, args?: Record<string, unknown>): Promise<unknown>;
  on(event: string, callback: (payload: unknown) => void): Unlisten;
  window: {
    minimize(): Promise<void>;
    toggleMaximize(): Promise<boolean>;
    close(): Promise<void>;
    show(): Promise<void>;
  };
  openExternal(url: string): Promise<void>;
  openDialog(options: OpenDialogOptions): Promise<string | string[] | null>;
  registerShortcut(accelerator: string): Promise<boolean>;
  unregisterShortcut(accelerator: string): Promise<void>;
  onShortcut(callback: (accelerator: string) => void): Unlisten;
  pathForFile(file: File): string;
}

export type DesktopShell = 'electron' | 'tauri';

export function desktopShell(): DesktopShell | null {
  if (typeof window === 'undefined') return null;
  if (window.suzentDesktop) return 'electron';
  if (window.__TAURI__) return 'tauri';
  return null;
}

export function isDesktop(): boolean {
  return desktopShell() !== null;
}

function electron(): ElectronDesktopBridge | undefined {
  return typeof window === 'undefined' ? undefined : window.suzentDesktop;
}

export async function invoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  const bridge = electron();
  if (bridge) return (await bridge.invoke(command, args)) as T;
  const core = await import('@tauri-apps/api/core');
  return core.invoke<T>(command, args);
}

export async function listen<T>(event: string, callback: (payload: T) => void): Promise<Unlisten> {
  const bridge = electron();
  if (bridge) return bridge.on(event, (payload) => callback(payload as T));
  const { listen: tauriListen } = await import('@tauri-apps/api/event');
  return tauriListen<T>(event, (message) => callback(message.payload));
}

export const desktopWindow = {
  async minimize(): Promise<void> {
    const bridge = electron();
    if (bridge) return bridge.window.minimize();
    await window.__TAURI__?.window.getCurrentWindow().minimize();
  },
  async toggleMaximize(): Promise<void> {
    const bridge = electron();
    if (bridge) {
      await bridge.window.toggleMaximize();
      return;
    }
    await window.__TAURI__?.window.getCurrentWindow().toggleMaximize();
  },
  async close(): Promise<void> {
    const bridge = electron();
    if (bridge) return bridge.window.close();
    await window.__TAURI__?.window.getCurrentWindow().close();
  },
  /** Electron drags through CSS (`app-region: drag`), so only Tauri needs this. */
  async startDragging(): Promise<void> {
    if (electron()) return;
    await window.__TAURI__?.window.getCurrentWindow().startDragging();
  },
  async reveal(): Promise<void> {
    const bridge = electron();
    if (bridge) return bridge.window.show();
    const { getCurrentWindow } = await import('@tauri-apps/api/window');
    const appWindow = getCurrentWindow();
    await appWindow.show();
    await appWindow.unminimize();
    await appWindow.setFocus();
  },
};

export async function openExternal(url: string): Promise<void> {
  const bridge = electron();
  if (bridge) return bridge.openExternal(url);
  const { open } = await import('@tauri-apps/plugin-shell');
  await open(url);
}

/** Opens a URL in the system browser on desktop, and in a new tab otherwise. */
export async function openUrl(url: string): Promise<void> {
  if (isDesktop()) {
    try {
      await openExternal(url);
      return;
    } catch (err) {
      console.warn('Desktop shell could not open the URL; falling back to window.open', err);
    }
  }
  window.open(url, '_blank', 'noopener,noreferrer');
}

export async function openDialog(options: OpenDialogOptions): Promise<string | string[] | null> {
  const bridge = electron();
  if (bridge) return bridge.openDialog(options);
  const { open } = await import('@tauri-apps/plugin-dialog');
  return open(options);
}

/**
 * Registers a system-wide shortcut. `onPress` runs on each press. Returns an
 * unregister function, or throws when the accelerator is taken or invalid.
 */
export async function registerGlobalShortcut(
  accelerator: string,
  onPress: () => void
): Promise<Unlisten> {
  const bridge = electron();
  if (bridge) {
    const stopListening = bridge.onShortcut((pressed) => {
      if (pressed === accelerator) onPress();
    });
    if (!(await bridge.registerShortcut(accelerator))) {
      stopListening();
      throw new Error(`Shortcut ${accelerator} is taken or invalid`);
    }
    return () => {
      stopListening();
      void bridge.unregisterShortcut(accelerator);
    };
  }
  const shortcuts = await import('@tauri-apps/plugin-global-shortcut');
  await shortcuts.register(accelerator, (event) => {
    if (event.state === 'Pressed') onPress();
  });
  return () => {
    void shortcuts.unregister(accelerator).catch(() => undefined);
  };
}

/** Whether the shell may show notifications, asking the OS where it must. */
export async function ensureNotificationPermission(): Promise<boolean> {
  // Electron's main process shows notifications without a page permission.
  if (electron()) return true;
  const { isPermissionGranted, requestPermission } =
    await import('@tauri-apps/plugin-notification');
  if (await isPermissionGranted()) return true;
  return (await requestPermission()) === 'granted';
}
