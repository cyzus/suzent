import { invoke } from '@tauri-apps/api/core';
import { getApiBase } from './api';
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

/** The release already downloaded in the background and ready to install, if any. */
export async function getStagedUpdate(): Promise<string | null> {
  if (isWeb()) return null;
  return (await invoke<string | null>('get_staged_update')) ?? null;
}

/** Restarts Suzent into the staged release; takes seconds, not a full update. */
export async function applyStagedUpdateNow(): Promise<void> {
  if (isWeb()) throw new Error('Self-update is only available in the desktop app.');
  await invoke('apply_staged_update_now');
}

/** Whether no chat, stream or subagent has run on the backend for a while. */
export async function fetchAgentsIdle(): Promise<boolean> {
  const response = await fetch(`${getApiBase()}/system/idle`);
  if (!response.ok) return false;
  const payload = (await response.json()) as { idle?: unknown };
  return payload.idle === true;
}

export async function getAutoUpdateEnabled(): Promise<boolean> {
  if (isWeb()) return false;
  return invoke<boolean>('get_auto_update_enabled');
}

export async function setAutoUpdateEnabled(enabled: boolean): Promise<void> {
  if (isWeb()) throw new Error('Automatic updates are only available in the desktop app.');
  await invoke('set_auto_update_enabled', { enabled });
}

const LAST_SEEN_VERSION_KEY = 'suzent:last-seen-version';

function versionKey(value: string): number[] {
  return (value.match(/\d+/g) ?? []).map(Number);
}

export function isNewerVersion(candidate: string, baseline: string): boolean {
  const a = versionKey(candidate);
  const b = versionKey(baseline);
  if (!a.length || !b.length) return false;
  for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
    const diff = (a[i] ?? 0) - (b[i] ?? 0);
    if (diff !== 0) return diff > 0;
  }
  return false;
}

/**
 * Returns the version Suzent was silently updated to since this window last
 * ran, once, and remembers the current one. Null on first run or no change.
 */
export function takeUpdatedVersion(current: string | undefined): string | null {
  if (!current) return null;
  let previous: string | null = null;
  try {
    previous = localStorage.getItem(LAST_SEEN_VERSION_KEY);
    localStorage.setItem(LAST_SEEN_VERSION_KEY, current);
  } catch {
    return null;
  }
  return previous && isNewerVersion(current, previous) ? current : null;
}
