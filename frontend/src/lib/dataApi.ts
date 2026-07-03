import { getApiBase } from './api';

export interface SyncProfile {
  id: string;
  repo_path: string;
  branch: string;
  remote: string;
  device_id: string;
  auto_sync_enabled: boolean;
  interval_hours: number;
  auto_resolve_enabled: boolean;
  encrypted_secret_sync_enabled: boolean;
  secret_sync_available: boolean;
  synced_keys?: string[] | null;
  last_revision?: string | null;
  last_sync_at?: string | null;
}

export interface SyncStatus {
  configured: boolean;
  profile?: SyncProfile;
  payload_dir?: string;
  forbidden_paths?: string[];
  git?: Record<string, unknown>;
  payload_hashes?: Record<string, string>;
  requires_shibboleth?: boolean;
  shibboleth_unlocked?: boolean;
  has_secret_bundles?: boolean;
  rotation_detected?: {
    rotation_detected: boolean;
    mnemonic_version: number;
    rotated_by_device: string;
    rotated_at: string | null;
  } | null;
  vault?: SecretVaultInfo;
}

export interface SecretVaultInfo {
  exists: boolean;
  vault_keys: string[];
  local_keys: string[];
  local_only_keys: string[];
  vault_only_keys: string[];
  synced_keys: string[];
  devices: { device_id: string; device_name: string; mnemonic_version: number }[];
  this_device_enrolled: boolean;
  rotated_by_device: string | null;
  rotated_at: string | null;
  mnemonic_version: number | null;
  mnemonic_fingerprint: string | null;
}

async function postJson<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${getApiBase()}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const payload = await res.json();
      detail = payload.detail || payload.error || detail;
    } catch {
      // Keep the HTTP status text when the backend did not return JSON.
    }
    throw new Error(`Request failed: ${detail}`);
  }
  return res.json();
}

export interface SyncQuickstartInfo {
  default_repo_path: string;
  default_repo_name: string;
  github_authenticated?: boolean;
}

export interface SyncQuickstartResult {
  success: boolean;
  profile: SyncProfile;
  repo_path: string;
  branch: string;
  repo_name: string;
  github_username?: string | null;
  github_repo?: string | null;
  actions: string[];
  warnings: string[];
  install_required?: boolean;
  install_url?: string | null;
  github_authenticated?: boolean;
  git?: Record<string, unknown> | null;
}

export interface DeviceFlowStartResult {
  session_id: string;
  user_code: string;
  verification_uri: string;
  expires_in: number;
  interval: number;
}

export interface DeviceFlowPollResult {
  status: 'pending' | 'complete' | 'expired' | 'denied';
  username?: string | null;
  interval?: number;
}

export interface GitHubAuthStatus {
  authenticated: boolean;
  username: string | null;
  token_expired?: boolean;
}

export async function fetchSyncQuickstartInfo(): Promise<SyncQuickstartInfo> {
  const res = await fetch(`${getApiBase()}/sync/quickstart/info`);
  if (!res.ok) throw new Error(`Failed to fetch sync quickstart info: ${res.statusText}`);
  return res.json();
}

export function startGitHubAuth(): Promise<DeviceFlowStartResult> {
  return postJson<DeviceFlowStartResult>('/sync/auth/start', {});
}

export function pollGitHubAuth(sessionId: string): Promise<DeviceFlowPollResult> {
  return postJson<DeviceFlowPollResult>('/sync/auth/poll', { session_id: sessionId });
}

export async function fetchGitHubAuthStatus(): Promise<GitHubAuthStatus> {
  const res = await fetch(`${getApiBase()}/sync/auth/status`);
  if (!res.ok) throw new Error(`Failed to fetch GitHub auth status: ${res.statusText}`);
  return res.json();
}

export function logoutGitHub(): Promise<{ success: boolean }> {
  return postJson<{ success: boolean }>('/sync/auth/logout', {});
}

export function runSyncQuickstart(options?: {
  repo_name?: string;
  repo_path?: string;
  branch?: string;
  remote?: string;
  auto_sync_enabled?: boolean;
  auto_resolve_enabled?: boolean;
  interval_hours?: number;
}): Promise<SyncQuickstartResult> {
  return postJson<SyncQuickstartResult>('/sync/quickstart', {
    repo_name: options?.repo_name?.trim() || undefined,
    repo_path: options?.repo_path?.trim() || undefined,
    branch: options?.branch?.trim() || undefined,
    remote: options?.remote?.trim() || undefined,
    auto_sync_enabled: options?.auto_sync_enabled ?? true,
    auto_resolve_enabled: options?.auto_resolve_enabled ?? true,
    interval_hours: options?.interval_hours ?? 4,
  });
}

export async function fetchSyncStatus(): Promise<SyncStatus> {
  const res = await fetch(`${getApiBase()}/sync/status`);
  if (!res.ok) throw new Error(`Failed to fetch sync status: ${res.statusText}`);
  return res.json();
}

export function saveSyncProfile(profile: Partial<SyncProfile> & { repo_path: string }): Promise<SyncProfile> {
  return postJson<SyncProfile>('/sync/profiles', profile);
}

export async function fetchSyncAheadBehind(profileId?: string): Promise<{ ahead: number; behind: number }> {
  const url = `${getApiBase()}/sync/ahead-behind${profileId ? `?profile_id=${encodeURIComponent(profileId)}` : ''}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`ahead-behind check failed: ${res.statusText}`);
  return res.json();
}

export function githubSyncPull(
  profileId?: string,
  shibboleth?: string,
): Promise<Record<string, unknown>> {
  const body: Record<string, unknown> = profileId ? { profile_id: profileId } : {};
  if (shibboleth) body.shibboleth = shibboleth;
  return postJson<Record<string, unknown>>('/sync/pull', body);
}

export function githubSyncPush(
  profileId?: string,
  shibboleth?: string,
): Promise<Record<string, unknown>> {
  const body: Record<string, unknown> = profileId ? { profile_id: profileId } : {};
  if (shibboleth) body.shibboleth = shibboleth;
  return postJson<Record<string, unknown>>('/sync/push', body);
}

export function runSync(profileId?: string): Promise<Record<string, unknown>> {
  return postJson<Record<string, unknown>>('/sync/auto/run', profileId ? { profile_id: profileId } : {});
}

export function saveSyncAutoConfig(profileId: string, autoSyncEnabled: boolean, intervalHours: number, autoResolveEnabled: boolean): Promise<SyncProfile> {
  return postJson<SyncProfile>('/sync/auto', {
    profile_id: profileId,
    auto_sync_enabled: autoSyncEnabled,
    interval_hours: intervalHours,
    auto_resolve_enabled: autoResolveEnabled,
  });
}

export function enableEncryptedSecretSync(profileId: string, mnemonic: string): Promise<SyncProfile & { mnemonic_version?: number; mnemonic_fingerprint?: string }> {
  return postJson('/sync/secrets/enable', { profile_id: profileId, mnemonic });
}

export function disableEncryptedSecretSync(profileId: string): Promise<SyncProfile> {
  return postJson<SyncProfile>('/sync/secrets/disable', { profile_id: profileId });
}

export function unlockMnemonic(profileId: string, mnemonic: string): Promise<{ success: boolean }> {
  return postJson('/sync/secrets/unlock', { profile_id: profileId, mnemonic });
}

export function rotateMnemonic(profileId: string, mnemonic: string): Promise<{ success: boolean; mnemonic_version: number; mnemonic_fingerprint: string }> {
  return postJson('/sync/secrets/rotate', { profile_id: profileId, mnemonic });
}

export function registerDeviceMnemonic(profileId: string, mnemonic: string): Promise<{ success: boolean }> {
  return postJson('/sync/secrets/register-device', { profile_id: profileId, mnemonic });
}

export function setSyncedKeys(profileId: string, syncedKeys: string[] | null): Promise<SyncProfile> {
  return postJson<SyncProfile>('/sync/secrets/synced-keys', {
    profile_id: profileId,
    synced_keys: syncedKeys,
  });
}

export function checkMnemonic(profileId: string, mnemonic: string): Promise<{ valid: boolean; matches: boolean | null }> {
  return postJson('/sync/secrets/check-mnemonic', { profile_id: profileId, mnemonic });
}
