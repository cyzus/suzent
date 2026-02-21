import { ConfigOptions } from '../types/api';

// -----------------------------------------------------------------------------
// Tauri Integration
// -----------------------------------------------------------------------------

// Get backend port injected by Tauri (available in both dev and prod modes)
// Falls back to empty string for browser mode (uses relative URLs via Vite proxy)
// IMPORTANT: This is a function, not a constant, because the port may not be
// set in sessionStorage when the module first loads.
export function getApiBase(): string {
  // We strictly target Tauri desktop environment
  // The backend port is injected by the main process into sessionStorage
  if (window.__TAURI__) {
    const injectedPort = (window as any).__SUZENT_BACKEND_PORT__;
    if (typeof injectedPort === 'number' && Number.isFinite(injectedPort)) {
      return `http://localhost:${injectedPort}`;
    }

    let port: string | null = null;
    try {
      port = sessionStorage.getItem('SUZENT_PORT');
    } catch {
      port = null;
    }
    if (!port) {
      try {
        port = localStorage.getItem('SUZENT_PORT');
      } catch {
        port = null;
      }
    }
    if (port) return `http://localhost:${port}`;
    // If port is missing in Tauri, we return empty string.
    // App.tsx should handle this by showing a loading screen.
    return '';
  }

  // Fallback for standard dev port if injection missing (e.g. during early init or HMR)
  // or running in browser mode
  return 'http://localhost:8000';
}

// Legacy constant for backward compatibility - but callers should prefer getApiBase()
// Legacy constant removed - callers must use getApiBase() to ensure dynamic port resolution
// export const API_BASE = getApiBase();

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export interface ApiField {
  key: string;
  label: string;
  placeholder: string;
  type: 'secret' | 'text';
  value: string;
  isSet: boolean;
}

export interface Model {
  id: string;
  name: string;
}

export interface UserConfig {
  enabled_models: string[];
  custom_models: string[];
}

export interface ApiProvider {
  id: string;
  label: string;
  default_models: Model[];
  fields: ApiField[];
  models: Model[];
  user_config: UserConfig;
}

interface StdioConfig {
  command: string;
  args?: string[];
  env?: Record<string, string>;
}

interface McpServersResponse {
  urls: Record<string, string>;
  stdio: Record<string, StdioConfig>;
  headers: Record<string, Record<string, string>>;
  enabled: Record<string, boolean>;
}

interface VerifyProviderResponse {
  success: boolean;
  models: Model[];
}

// -----------------------------------------------------------------------------
// MCP Server Management
// -----------------------------------------------------------------------------

export async function fetchMcpServers(): Promise<McpServersResponse> {
  const res = await fetch(`${getApiBase()}/mcp_servers`);
  if (!res.ok) throw new Error('Failed to fetch MCP servers');
  return res.json();
}

export async function addMcpServer(
  name: string,
  url?: string,
  stdio?: StdioConfig,
  headers?: Record<string, string>
): Promise<void> {
  const body: { name: string; url?: string; stdio?: StdioConfig; headers?: Record<string, string> } = { name };
  if (url) body.url = url;
  if (stdio) body.stdio = stdio;
  if (headers && Object.keys(headers).length > 0) body.headers = headers;

  /* eslint-disable-next-line @typescript-eslint/no-unused-vars */
  const res = await fetch(`${getApiBase()}/mcp_servers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error('Failed to add MCP server');
}

export async function removeMcpServer(name: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/mcp_servers/remove`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name })
  });
  if (!res.ok) throw new Error('Failed to remove MCP server');
}

export async function setMcpServerEnabled(name: string, enabled: boolean): Promise<void> {
  const res = await fetch(`${getApiBase()}/mcp_servers/enabled`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, enabled })
  });
  if (!res.ok) throw new Error('Failed to update MCP server');
}

// -----------------------------------------------------------------------------
// Configuration
// -----------------------------------------------------------------------------

export async function fetchBackendConfig(): Promise<ConfigOptions | null> {
  try {
    const res = await fetch(`${getApiBase()}/config`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function saveUserPreferences(preferences: {
  model?: string;
  agent?: string;
  tools?: string[];
  memory_enabled?: boolean;
  embedding_model?: string;
  extraction_model?: string;
  EXTRACTION_MODEL?: string;
}): Promise<boolean> {
  try {
    const res = await fetch(`${getApiBase()}/preferences`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(preferences)
    });
    if (!res.ok) {
      console.error('Failed to save preferences:', res.status, res.statusText);
      return false;
    }
    return true;
  } catch (error) {
    console.error('Error saving preferences:', error);
    return false;
  }
}

export async function fetchEmbeddingModels(): Promise<string[]> {
  try {
    const res = await fetch(`${getApiBase()}/config/embedding-models`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.models || [];
  } catch (e) {
    console.error('Error fetching embedding models:', e);
    return [];
  }
}

// -----------------------------------------------------------------------------
// API Keys
// -----------------------------------------------------------------------------

export async function fetchApiKeys(): Promise<{ providers: ApiProvider[] } | null> {
  try {
    const res = await fetch(`${getApiBase()}/config/api-keys`);
    if (!res.ok) throw new Error('Failed to fetch API keys');
    return await res.json();
  } catch (e) {
    console.error(e);
    return null;
  }
}

export async function saveApiKeys(keys: Record<string, string>): Promise<boolean> {
  try {
    const res = await fetch(`${getApiBase()}/config/api-keys`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keys })
    });
    if (!res.ok) throw new Error('Failed to save API keys');
    return true;
  } catch (e) {
    console.error(e);
    return false;
  }
}

export async function verifyProvider(
  providerId: string,
  config: Record<string, string>
): Promise<VerifyProviderResponse> {
  try {
    const res = await fetch(`${getApiBase()}/config/providers/${providerId}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config })
    });
    if (!res.ok) throw new Error('Failed to verify provider');
    return await res.json();
  } catch (e) {
    console.error(e);
    return { success: false, models: [] };
  }
}

// -----------------------------------------------------------------------------
// Sandbox
// -----------------------------------------------------------------------------

/**
 * Helper to generate sandbox query parameters, including volumes from config.
 * @param chatId The current chat ID
 * @param path The path to access
 * @param volumes Optional list of volume strings from config
 */
export function getSandboxParams(chatId: string, path: string, volumes?: string[]): string {
  const params = new URLSearchParams();
  if (chatId) params.append('chat_id', chatId);
  if (path) params.append('path', path);
  if (volumes && volumes.length > 0) {
    params.append('volumes', JSON.stringify(volumes));
  }
  return params.toString();
}

// -----------------------------------------------------------------------------
// Social Configuration
// -----------------------------------------------------------------------------

export interface SocialConfig {
  allowed_users: string[];
  model?: string;
  memory_enabled?: boolean;
  tools?: string[] | null;
  mcp_enabled?: Record<string, boolean> | null;
  [key: string]: any;
}

export async function fetchSocialConfig(): Promise<SocialConfig> {
  try {
    const res = await fetch(`${getApiBase()}/config/social`);
    if (!res.ok) return { allowed_users: [] };
    const data = await res.json();
    return data.config || { allowed_users: [] };
  } catch (e) {
    console.error('Error fetching social config:', e);
    return { allowed_users: [] };
  }
}

// -----------------------------------------------------------------------------
// Cron Jobs / Automation
// -----------------------------------------------------------------------------

export interface CronJob {
  id: number;
  name: string;
  cron_expr: string;
  prompt: string;
  active: boolean;
  delivery_mode: 'announce' | 'none';
  model_override: string | null;
  retry_count: number;
  last_run_at: string | null;
  next_run_at: string | null;
  last_result: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface CronNotification {
  job_id: number;
  job_name: string;
  result: string;
  timestamp: string;
}

export async function fetchCronJobs(): Promise<CronJob[]> {
  const res = await fetch(`${getApiBase()}/cron/jobs`);
  if (!res.ok) throw new Error('Failed to fetch cron jobs');
  const data = await res.json();
  return data.jobs || [];
}

export async function createCronJob(job: {
  name: string;
  cron_expr: string;
  prompt: string;
  active?: boolean;
  delivery_mode?: string;
  model_override?: string | null;
}): Promise<CronJob> {
  const res = await fetch(`${getApiBase()}/cron/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(job),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || 'Failed to create cron job');
  }
  const data = await res.json();
  return data.job;
}

export async function updateCronJob(jobId: number, updates: Partial<CronJob>): Promise<CronJob> {
  const res = await fetch(`${getApiBase()}/cron/jobs/${jobId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || 'Failed to update cron job');
  }
  const data = await res.json();
  return data.job;
}

export async function deleteCronJob(jobId: number): Promise<void> {
  const res = await fetch(`${getApiBase()}/cron/jobs/${jobId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete cron job');
}

export async function triggerCronJob(jobId: number): Promise<void> {
  const res = await fetch(`${getApiBase()}/cron/jobs/${jobId}/trigger`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to trigger cron job');
}

export async function fetchCronStatus(): Promise<{
  scheduler_running: boolean;
  total_jobs: number;
  active_jobs: number;
}> {
  const res = await fetch(`${getApiBase()}/cron/status`);
  if (!res.ok) throw new Error('Failed to fetch cron status');
  return res.json();
}

export async function drainCronNotifications(): Promise<CronNotification[]> {
  try {
    const res = await fetch(`${getApiBase()}/cron/notifications`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.notifications || [];
  } catch {
    return [];
  }
}

export interface CronRun {
  id: number;
  job_id: number;
  started_at: string;
  finished_at: string | null;
  status: 'running' | 'success' | 'error';
  result: string | null;
  error: string | null;
}

export async function fetchCronJobRuns(jobId: number, limit = 20): Promise<CronRun[]> {
  const res = await fetch(`${getApiBase()}/cron/jobs/${jobId}/runs?limit=${limit}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.runs || [];
}

// -----------------------------------------------------------------------------
// Heartbeat
// -----------------------------------------------------------------------------

export interface HeartbeatStatus {
  enabled: boolean;
  running: boolean;
  interval_minutes: number;
  heartbeat_md_exists: boolean;
  last_run_at: string | null;
  last_result: string | null;
  last_error: string | null;
}

export async function fetchHeartbeatStatus(): Promise<HeartbeatStatus> {
  const res = await fetch(`${getApiBase()}/heartbeat/status`);
  if (!res.ok) throw new Error('Failed to fetch heartbeat status');
  return res.json();
}

export async function enableHeartbeat(): Promise<void> {
  const res = await fetch(`${getApiBase()}/heartbeat/enable`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || 'Failed to enable heartbeat');
  }
}

export async function disableHeartbeat(): Promise<void> {
  const res = await fetch(`${getApiBase()}/heartbeat/disable`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to disable heartbeat');
}

export async function triggerHeartbeat(): Promise<void> {
  const res = await fetch(`${getApiBase()}/heartbeat/trigger`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to trigger heartbeat');
}

export async function setHeartbeatInterval(minutes: number): Promise<void> {
  const res = await fetch(`${getApiBase()}/heartbeat/interval`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ interval_minutes: minutes }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || 'Failed to set heartbeat interval');
  }
}

export async function fetchHeartbeatMd(): Promise<{ content: string; exists: boolean }> {
  const res = await fetch(`${getApiBase()}/heartbeat/md`);
  if (!res.ok) return { content: '', exists: false };
  return res.json();
}

export async function saveHeartbeatMd(content: string): Promise<boolean> {
  const res = await fetch(`${getApiBase()}/heartbeat/md`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  return res.ok;
}

export async function saveSocialConfig(config: SocialConfig): Promise<boolean> {
  try {
    const res = await fetch(`${getApiBase()}/config/social`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config })
    });
    if (!res.ok) throw new Error('Failed to save social config');
    return true;
  } catch (e) {
    console.error(e);
    return false;
  }
}
