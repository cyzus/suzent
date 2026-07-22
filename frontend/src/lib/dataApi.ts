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
}

export type SyncOperation = 'push' | 'pull' | 'auto';
export type SyncChangeType = 'added' | 'modified' | 'deleted';
export type SyncRisk = 'low' | 'medium' | 'high';
export type SyncDirection = 'outgoing' | 'incoming';

export interface SyncFileChange {
  path: string;
  category: 'config' | 'skills' | 'memory' | 'sync' | 'other';
  change_type: SyncChangeType;
  risk: SyncRisk;
  direction?: SyncDirection;
  diff_preview?: string | null;
}

export interface SyncPlan {
  operation: SyncOperation;
  files: SyncFileChange[];
  summary: Record<string, number>;
  destructive: boolean;
  requires_confirmation: boolean;
  warnings: string[];
}

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

async function postJson<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${getApiBase()}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    let payload: unknown = null;
    try {
      payload = await res.json();
      if (payload && typeof payload === 'object') {
        const data = payload as { detail?: unknown; error?: unknown };
        detail = String(data.detail || data.error || detail);
      }
    } catch {
      // Keep the HTTP status text when the backend did not return JSON.
    }
    throw new ApiError(`Request failed: ${detail}`, res.status, payload);
  }
  return res.json();
}

export function syncReviewPlanFromError(error: unknown): SyncPlan | null {
  if (!(error instanceof ApiError)) return null;
  if (!error.payload || typeof error.payload !== 'object') return null;
  const plan = (error.payload as { plan?: unknown }).plan;
  if (!plan || typeof plan !== 'object') return null;
  return plan as SyncPlan;
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

export function githubSyncPlan(operation: SyncOperation, profileId?: string): Promise<SyncPlan> {
  const body: Record<string, unknown> = { operation };
  if (profileId) body.profile_id = profileId;
  return postJson<SyncPlan>('/sync/plan', body);
}

export function githubSyncPull(
  profileId?: string,
  confirmDestructive = false,
  preferCloud = false,
): Promise<Record<string, unknown>> {
  const body: Record<string, unknown> = profileId ? { profile_id: profileId } : {};
  if (confirmDestructive) body.confirm_destructive = true;
  if (preferCloud) body.prefer_cloud = true;
  return postJson<Record<string, unknown>>('/sync/pull', body);
}

export function githubSyncDiscardOutgoing(profileId?: string): Promise<Record<string, unknown>> {
  const body: Record<string, unknown> = profileId ? { profile_id: profileId } : {};
  return postJson<Record<string, unknown>>('/sync/discard-outgoing', body);
}

export function githubSyncPush(
  profileId?: string,
  confirmDestructive = false,
): Promise<Record<string, unknown>> {
  const body: Record<string, unknown> = profileId ? { profile_id: profileId } : {};
  if (confirmDestructive) body.confirm_destructive = true;
  return postJson<Record<string, unknown>>('/sync/push', body);
}

export function runSync(profileId?: string, confirmDestructive = false): Promise<Record<string, unknown>> {
  const body: Record<string, unknown> = profileId ? { profile_id: profileId } : {};
  if (confirmDestructive) body.confirm_destructive = true;
  return postJson<Record<string, unknown>>('/sync/auto/run', body);
}

export function saveSyncAutoConfig(profileId: string, autoSyncEnabled: boolean, intervalHours: number, autoResolveEnabled: boolean): Promise<SyncProfile> {
  return postJson<SyncProfile>('/sync/auto', {
    profile_id: profileId,
    auto_sync_enabled: autoSyncEnabled,
    interval_hours: intervalHours,
    auto_resolve_enabled: autoResolveEnabled,
  });
}
