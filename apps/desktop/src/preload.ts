/**
 * The bridge the frontend sees as `window.suzentDesktop`. It runs sandboxed,
 * so it may only use `electron` itself; every capability is a named IPC call
 * the main process validates.
 */

import { contextBridge, ipcRenderer, webUtils } from 'electron';

type Listener = (payload: unknown) => void;

const listeners = new Map<string, Set<Listener>>();

ipcRenderer.on('suzent:event', (_event, name: string, payload: unknown) => {
  for (const listener of listeners.get(name) ?? []) listener(payload);
});

function on(name: string, listener: Listener): () => void {
  let set = listeners.get(name);
  if (!set) {
    set = new Set();
    listeners.set(name, set);
  }
  set.add(listener);
  return () => {
    set?.delete(listener);
  };
}

const invoke = (command: string, args?: Record<string, unknown>): Promise<unknown> =>
  ipcRenderer.invoke('suzent:invoke', command, args ?? {});

contextBridge.exposeInMainWorld('suzentDesktop', {
  platform: process.platform,
  invoke,
  on,
  window: {
    minimize: () => invoke('window_minimize'),
    toggleMaximize: () => invoke('window_toggle_maximize'),
    close: () => invoke('window_close'),
    show: () => invoke('window_show'),
  },
  openExternal: (url: string) => invoke('open_external', { url }),
  openDialog: (options: Record<string, unknown>) => invoke('open_dialog', { options }),
  registerShortcut: (accelerator: string) => invoke('register_shortcut', { accelerator }),
  unregisterShortcut: (accelerator: string) => invoke('unregister_shortcut', { accelerator }),
  onShortcut: (listener: (accelerator: string) => void) =>
    on('shortcut-pressed', (payload) => listener(String(payload))),
  pathForFile: (file: File) => webUtils.getPathForFile(file),
});

window.addEventListener('DOMContentLoaded', () => {
  document.documentElement.classList.add('electron-shell', `electron-${process.platform}`);
});
