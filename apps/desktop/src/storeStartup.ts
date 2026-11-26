/**
 * Settings > Background service in the Microsoft Store package. A packaged
 * app has no Python service: it starts at login through the manifest's
 * StartupTask, which only a process inside the package can switch. The
 * package's `resources\bin\suzent.exe` (apps/desktop/store-cli) does that and
 * prints the task state as JSON.
 */

import { execFile } from 'node:child_process';
import path from 'node:path';

export interface StartupTaskState {
  state: string;
  enabled: boolean;
  error: string | null;
}

export type StartupTaskAction = 'status' | 'enable' | 'disable';

export function storeHelperPath(resourcesPath: string): string {
  return path.join(resourcesPath, 'bin', 'suzent.exe');
}

export function runStartupTask(helper: string, action: StartupTaskAction): Promise<StartupTaskState> {
  return new Promise((resolve, reject) => {
    execFile(helper, ['--startup-task', action], { windowsHide: true, timeout: 30_000 }, (error, stdout, stderr) => {
      if (error) {
        reject(new Error(stderr.toString().trim() || error.message));
        return;
      }
      try {
        resolve(JSON.parse(stdout.toString()) as StartupTaskState);
      } catch {
        reject(new Error(`Unexpected start-at-login state: ${stdout.toString().trim()}`));
      }
    });
  });
}

/** The task as `suzent service status --json` would report a service. */
export function storeServiceStatus(
  task: StartupTaskState,
  backend: { port: number; ready: boolean } | null,
  version: string
): string {
  const ready = backend?.ready ?? false;
  return JSON.stringify({
    installed: task.enabled,
    autostart: task.enabled,
    running: ready,
    ready,
    pid: null,
    port: backend?.port ?? null,
    version: ready ? version : null,
    uptime_seconds: null,
    rss_bytes: null,
    error: task.error,
  });
}
