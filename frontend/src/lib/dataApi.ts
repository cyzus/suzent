import { getApiBase } from './api';

export interface DataStatus {
  data_dir: string;
  runtime_dir: string;
  cache_dir: string;
  exists: boolean;
  portable_entries: string[];
}

export interface DataExportResult {
  output_path: string;
  included: string[];
  skipped?: string[];
}

export interface DataImportPreview {
  archive_path: string;
  valid: boolean;
  entries: string[];
}

export interface DataImportResult {
  archive_path: string;
  data_dir: string;
  backup_path: string;
  restored_entries: string[];
}

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
  last_revision?: string | null;
  last_sync_at?: string | null;
}

export interface SyncStatus {
  configured: boolean;
  profile?: SyncProfile;
  payload_dir?: string;
  forbidden_paths?: string[];
  git?: Record<string, unknown>;
  requires_shibboleth?: boolean;
  shibboleth_unlocked?: boolean;
  has_secret_bundles?: boolean;
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

export async function fetchDataStatus(): Promise<DataStatus> {
  const res = await fetch(`${getApiBase()}/data/status`);
  if (!res.ok) throw new Error(`Failed to fetch data status: ${res.statusText}`);
  return res.json();
}

export function exportData(output?: string): Promise<DataExportResult> {
  return postJson<DataExportResult>('/data/export', output ? { output } : {});
}

export function previewImportData(archive: string): Promise<DataImportPreview> {
  return postJson<DataImportPreview>('/data/import/dry-run', { archive });
}

export function importData(archive: string): Promise<DataImportResult> {
  return postJson<DataImportResult>('/data/import', { archive });
}

export function syncPush(target: string): Promise<DataExportResult> {
  return postJson<DataExportResult>('/data/sync/push', { target });
}

export function previewSyncPull(target: string): Promise<DataImportPreview> {
  return postJson<DataImportPreview>('/data/sync/pull', { target, dry_run: true });
}

export function syncPull(target: string): Promise<DataImportResult> {
  return postJson<DataImportResult>('/data/sync/pull', { target });
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
    auto_sync_enabled: options?.auto_sync_enabled ?? false,
    auto_resolve_enabled: options?.auto_resolve_enabled ?? true,
    interval_hours: options?.interval_hours ?? 4,
  });
}

export async function fetchSyncStatus(): Promise<SyncStatus> {
  const res = await fetch(`${getApiBase()}/sync/status`);
  if (!res.ok) throw new Error(`Failed to fetch sync status: ${res.statusText}`);
  return res.json();
}

export async function fetchSyncProfiles(): Promise<SyncProfile[]> {
  const res = await fetch(`${getApiBase()}/sync/profiles`);
  if (!res.ok) throw new Error(`Failed to fetch sync profiles: ${res.statusText}`);
  const payload = await res.json();
  return payload.profiles || [];
}

export function saveSyncProfile(profile: Partial<SyncProfile> & { repo_path: string }): Promise<SyncProfile> {
  return postJson<SyncProfile>('/sync/profiles', profile);
}

export function validateGitHubSync(profile: Partial<SyncProfile> & { repo_path: string }): Promise<Record<string, unknown>> {
  return postJson<Record<string, unknown>>('/sync/validate', profile);
}

export function githubSyncPreviewPull(profileId?: string): Promise<Record<string, unknown>> {
  return postJson<Record<string, unknown>>('/sync/preview-pull', profileId ? { profile_id: profileId } : {});
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

export function unlockShibboleth(profileId: string, shibboleth: string): Promise<{ success: boolean }> {
  return postJson<{ success: boolean }>('/sync/shibboleth/unlock', {
    profile_id: profileId,
    shibboleth,
  });
}

export function lockShibboleth(profileId: string): Promise<{ success: boolean }> {
  return postJson<{ success: boolean }>('/sync/shibboleth/lock', { profile_id: profileId });
}

export function saveSyncAutoConfig(profileId: string, autoSyncEnabled: boolean, intervalHours: number, autoResolveEnabled: boolean): Promise<SyncProfile> {
  return postJson<SyncProfile>('/sync/auto', {
    profile_id: profileId,
    auto_sync_enabled: autoSyncEnabled,
    interval_hours: intervalHours,
    auto_resolve_enabled: autoResolveEnabled,
  });
}

export function enableEncryptedSecretSync(profileId: string, shibboleth: string): Promise<SyncProfile> {
  return postJson<SyncProfile>('/sync/secrets/enable', { profile_id: profileId, shibboleth });
}

export function disableEncryptedSecretSync(profileId: string): Promise<SyncProfile> {
  return postJson<SyncProfile>('/sync/secrets/disable', { profile_id: profileId });
}
