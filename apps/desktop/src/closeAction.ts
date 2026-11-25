/**
 * What closing the main window does when a tray icon is available: ask, hide
 * to the tray, or quit. The choice is a one-word file in the data dir so the
 * main process can read it before the page answers.
 */

import fs from 'node:fs';
import path from 'node:path';

export type CloseAction = 'ask' | 'tray' | 'quit';
export type TrayHost = 'windows' | 'macos' | 'unsupported';

export function trayHostFor(platform: NodeJS.Platform): TrayHost {
  if (platform === 'win32') return 'windows';
  if (platform === 'darwin') return 'macos';
  return 'unsupported';
}

export function supportsTray(host: TrayHost): boolean {
  return host !== 'unsupported';
}

export function parseCloseAction(value: string): CloseAction | null {
  const trimmed = value.trim();
  return trimmed === 'ask' || trimmed === 'tray' || trimmed === 'quit' ? trimmed : null;
}

/** macOS apps conventionally stay alive when their window closes. */
export function defaultCloseAction(host: TrayHost): CloseAction {
  return host === 'macos' ? 'tray' : 'ask';
}

export function closeActionPath(dataDir: string): string {
  return path.join(dataDir, 'desktop', 'close-action');
}

export function loadCloseAction(dataDir: string, host: TrayHost): CloseAction {
  try {
    return (
      parseCloseAction(fs.readFileSync(closeActionPath(dataDir), 'utf8')) ??
      defaultCloseAction(host)
    );
  } catch {
    return defaultCloseAction(host);
  }
}

export function saveCloseAction(dataDir: string, action: CloseAction): void {
  const file = closeActionPath(dataDir);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, action);
}

export type CloseDecision = 'allow' | 'hide' | 'quit' | 'ask';

/**
 * Quit, restart and the updater mark the app as exiting before the window
 * close they cause, and a failed tray must not trap the app with no window.
 */
export function decideClose(
  host: TrayHost,
  trayReady: boolean,
  exiting: boolean,
  action: CloseAction
): CloseDecision {
  if (exiting || !trayReady || !supportsTray(host)) return 'allow';
  if (action === 'quit') return 'quit';
  if (action === 'ask') return 'ask';
  return 'hide';
}
