import { invoke } from '@tauri-apps/api/core';
import { isWeb } from './runtime';

export interface UpdateStatus {
  current_version?: string;
  latest_version?: string;
  update_available?: boolean;
  error?: string;
}

const UPDATE_STATUS_CACHE_MS = 60_000;

let cachedUpdateStatus: { value: UpdateStatus; checkedAt: number } | null = null;
let pendingUpdateCheck: Promise<UpdateStatus> | null = null;

export function checkDesktopUpdate(force = false): Promise<UpdateStatus> {
  // The web UI is updated by updating the backend that serves it; there is no
  // app binary to replace, so callers get "nothing available" rather than an error.
  if (isWeb()) return Promise.resolve({});
  if (pendingUpdateCheck) return pendingUpdateCheck;
  if (
    !force &&
    cachedUpdateStatus &&
    Date.now() - cachedUpdateStatus.checkedAt < UPDATE_STATUS_CACHE_MS
  ) {
    return Promise.resolve(cachedUpdateStatus.value);
  }

  pendingUpdateCheck = invoke<string>('check_for_update')
    .then((raw) => {
      const value = JSON.parse(raw) as UpdateStatus;
      cachedUpdateStatus = { value, checkedAt: Date.now() };
      return value;
    })
    .finally(() => {
      pendingUpdateCheck = null;
    });
  return pendingUpdateCheck;
}

export async function startDesktopUpdateAndRestart(): Promise<void> {
  if (isWeb()) throw new Error('Self-update is only available in the desktop app.');
  await invoke('start_update_and_restart');
}
