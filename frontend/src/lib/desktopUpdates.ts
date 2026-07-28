import { invoke } from '@tauri-apps/api/core';

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
  if (pendingUpdateCheck) return pendingUpdateCheck;
  if (
    !force
    && cachedUpdateStatus
    && Date.now() - cachedUpdateStatus.checkedAt < UPDATE_STATUS_CACHE_MS
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
  await invoke('start_update_and_restart');
}
