import { ChatGPTLoginResponse, ChatGPTStatusResponse, ConfigOptions, PermissionMode } from '../types/api';
import type { PermissionPrompt } from '../types/agui';

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
      return `http://127.0.0.1:${injectedPort}`;
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
    if (port) return `http://127.0.0.1:${port}`;
    // If port is missing in Tauri, we return empty string.
    // App.tsx should handle this by showing a loading screen.
    return '';
  }

  // Fallback for standard dev port if injection missing (e.g. during early init or HMR)
  // or running in browser mode
  return 'http://127.0.0.1:8000';
}

export interface PermissionModeState {
  mode: PermissionMode;
  prePlanMode?: PermissionMode | null;
  availableModes: PermissionMode[];
  autoModeAvailable: boolean;
  unavailableReasons: Record<string, string>;
}

export async function setChatPermissionMode(
  chatId: string,
  mode: PermissionMode,
): Promise<PermissionModeState> {
  const response = await fetch(`${getApiBase()}/chats/${chatId}/permission-mode`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  });
  if (!response.ok) {
    throw new Error(`Failed to set permission mode: ${response.status}`);
  }
  return response.json();
}

export async function restoreChatPermissionMode(
  chatId: string,
): Promise<PermissionModeState> {
  const response = await fetch(`${getApiBase()}/chats/${chatId}/permission-mode`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ restorePrevious: true }),
  });
  if (!response.ok) {
    throw new Error(`Failed to restore permission mode: ${response.status}`);
  }
  return response.json();
}

export interface PendingPermissionApproval {
  approvalId: string;
  toolCallId: string;
  toolName: string;
  args: Record<string, unknown>;
  decision: PermissionPrompt;
  savedAt?: string;
}

export interface ChatPermissionState {
  chatId: string;
  mode: PermissionMode;
  prePlanMode?: PermissionMode | null;
  pendingApprovals: PendingPermissionApproval[];
}

export async function getChatPermissionState(
  chatId: string,
): Promise<ChatPermissionState> {
  const response = await fetch(`${getApiBase()}/chats/${chatId}/permission-state`);
  if (!response.ok) {
    throw new Error(`Failed to load permission state: ${response.status}`);
  }
  return response.json();
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
  source?: 'env' | 'db' | null;
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
  logo_url?: string;
  user_defined?: boolean;
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
  message?: string;
  error?: string;
}

// -----------------------------------------------------------------------------
// Tool Approval (Human-in-the-Loop)
// -----------------------------------------------------------------------------

async function postOk(path: string, body: Record<string, unknown>): Promise<boolean> {
  try {
    const res = await fetch(`${getApiBase()}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function approveTool(
  chatId: string,
  requestId: string,
  approved: boolean,
  remember?: 'session' | 'global' | null,
): Promise<boolean> {
  return postOk('/chat/approve-tool', {
    chat_id: chatId,
    request_id: requestId,
    approved,
    remember: remember || null,
  });
}

export async function deactivateTool(chatId: string, toolName: string): Promise<boolean> {
  return postOk('/chat/deactivate-tool', { chat_id: chatId, tool_name: toolName });
}

// -----------------------------------------------------------------------------
// MCP Server Management
// -----------------------------------------------------------------------------

export async function fetchMcpServers(): Promise<McpServersResponse> {
  const res = await fetch(`${getApiBase()}/mcp_servers`);
  if (!res.ok) throw new Error('Failed to fetch MCP servers');
  return res.json();
}

export interface McpToolInfo {
  name: string;
  description?: string;
}

export interface McpProbeResult {
  ok: boolean;
  count?: number;
  tools?: McpToolInfo[];
  error?: string;
}

export async function addMcpServer(
  name: string,
  url?: string,
  stdio?: StdioConfig,
  headers?: Record<string, string>
): Promise<McpProbeResult | undefined> {
  const body: { name: string; url?: string; stdio?: StdioConfig; headers?: Record<string, string> } = { name };
  if (url) body.url = url;
  if (stdio) body.stdio = stdio;
  if (headers && Object.keys(headers).length > 0) body.headers = headers;

  const res = await fetch(`${getApiBase()}/mcp_servers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error('Failed to add MCP server');
  const data = await res.json();
  return data.probe as McpProbeResult | undefined;
}

export async function updateMcpServer(
  name: string,
  url?: string,
  stdio?: StdioConfig,
  headers?: Record<string, string>
): Promise<McpProbeResult | undefined> {
  const body: { name: string; url?: string; stdio?: StdioConfig; headers?: Record<string, string> } = { name };
  if (url) body.url = url;
  if (stdio) body.stdio = stdio;
  if (headers && Object.keys(headers).length > 0) body.headers = headers;

  const res = await fetch(`${getApiBase()}/mcp_servers/update`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error('Failed to update MCP server');
  const data = await res.json();
  return data.probe as McpProbeResult | undefined;
}

export async function testMcpServer(name: string): Promise<McpProbeResult> {
  const res = await fetch(`${getApiBase()}/mcp_servers/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name })
  });
  if (!res.ok) throw new Error('Failed to test MCP server');
  return res.json();
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

// ─── Nodes / Devices ─────────────────────────────────────────────────

export interface NodeCapabilityInfo {
  name: string;
  description?: string;
  params_schema?: Record<string, string>;
}

export interface ConnectedNode {
  node_id: string;
  display_name: string;
  platform: string;
  status: string;
  connected_at?: string;
  capabilities: NodeCapabilityInfo[];
}

export interface PendingNode {
  pairing_code: string;
  display_name: string;
  platform: string;
  capabilities: NodeCapabilityInfo[];
  requested_at: string;
}

export interface ApprovedDevice {
  device_id: string;
  display_name: string;
  platform: string;
  scope?: 'node' | 'agent' | 'full';
  status?: 'active' | 'paused';
  token_hint?: string;
  approved_at: string;
  connected: boolean;
}

export interface PairingAddress {
  label: string;
  host: string;
  gateway_url: string;
}

export interface NodeAuthConfig {
  nodes_enabled: boolean;
  node_lan_bind?: boolean;
  lan_host?: string;
  port?: number;
  gateway_url?: string;
  addresses?: PairingAddress[];
}

export async function fetchNodes(): Promise<ConnectedNode[]> {
  const res = await fetch(`${getApiBase()}/nodes`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.nodes || [];
}

export async function fetchPendingNodes(): Promise<PendingNode[]> {
  const res = await fetch(`${getApiBase()}/nodes/pending`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.pending || [];
}

export async function fetchApprovedDevices(): Promise<ApprovedDevice[]> {
  const res = await fetch(`${getApiBase()}/nodes/devices`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.devices || [];
}

export async function approvePendingNode(pairingCode: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/nodes/pending/${pairingCode}/approve`, { method: 'POST' });
  if (!res.ok) throw new Error((await res.text()) || 'Failed to approve');
}

export async function denyPendingNode(pairingCode: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/nodes/pending/${pairingCode}/deny`, { method: 'POST' });
  if (!res.ok) throw new Error((await res.text()) || 'Failed to deny');
}

export async function revokeDevice(deviceId: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/nodes/devices/${deviceId}/revoke`, { method: 'POST' });
  if (!res.ok) throw new Error((await res.text()) || 'Failed to revoke');
}

/** Pause or resume an inbound grant (a device that can drive us). */
export async function setDeviceStatus(deviceId: string, status: 'active' | 'paused'): Promise<void> {
  const res = await fetch(`${getApiBase()}/nodes/devices/${deviceId}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error((await res.text()) || 'Failed to update device status');
}

/** Mint a full-access ("host") token to use this server remotely. Shown once. */
export async function createHostToken(name = ''): Promise<{ token: string; device_id: string }> {
  const res = await fetch(`${getApiBase()}/nodes/host-token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error((await res.text()) || 'Failed to create host token');
  return await res.json();
}

export interface DiscoveredPeer {
  name: string;
  host: string;
  port: number;
  gateway_url: string;
  source: 'lan' | 'tailscale';
  auth_mode?: string;
  reachable?: boolean;
}

export interface OutboundConnection {
  gateway_url: string;
  display_name: string;
  status: string;
  pairing_code: string | null;
  node_id: string | null;
  error: string | null;
}

export async function discoverNodes(timeout = 2.0): Promise<{ lan: DiscoveredPeer[]; tailscale: DiscoveredPeer[] }> {
  const res = await fetch(`${getApiBase()}/nodes/discover?timeout=${timeout}`);
  if (!res.ok) return { lan: [], tailscale: [] };
  return await res.json();
}

export async function connectNode(gateway_url: string, name = ''): Promise<void> {
  const res = await fetch(`${getApiBase()}/nodes/connect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gateway_url, name }),
  });
  if (!res.ok) throw new Error((await res.text()) || 'Failed to connect');
}

export async function fetchConnections(): Promise<OutboundConnection[]> {
  const res = await fetch(`${getApiBase()}/nodes/connections`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.connections || [];
}

export async function disconnectNode(gateway_url: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/nodes/connect/stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gateway_url }),
  });
  if (!res.ok) throw new Error((await res.text()) || 'Failed to disconnect');
}

// ─── Control-grant (peer agent control) ──────────────────────────────

export interface ControlRequest {
  request_id: string;
  controller_name: string;
  controller_host: string;
  requested_at: string;
}

export interface ControlledPeer {
  peer_id: string;
  name: string;
  base_url: string;
  mode: 'off' | 'trigger' | 'paused';
  reverse_enabled?: boolean;
  added_at: string;
  online?: boolean;
}

export async function fetchGrants(): Promise<ControlRequest[]> {
  const res = await fetch(`${getApiBase()}/nodes/grants`);
  if (!res.ok) return [];
  return (await res.json()).grants || [];
}

export async function approveGrant(requestId: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/nodes/grants/${requestId}/approve`, { method: 'POST' });
  if (!res.ok) throw new Error((await res.text()) || 'Failed to approve');
}

export async function denyGrant(requestId: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/nodes/grants/${requestId}/deny`, { method: 'POST' });
  if (!res.ok) throw new Error((await res.text()) || 'Failed to deny');
}

export async function fetchPeers(): Promise<ControlledPeer[]> {
  const res = await fetch(`${getApiBase()}/nodes/peers`);
  if (!res.ok) return [];
  return (await res.json()).peers || [];
}

export async function setPeerMode(peerId: string, mode: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/nodes/peers/${peerId}/mode`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  });
  if (!res.ok) throw new Error((await res.text()) || 'Failed to set mode');
}

/** Enable/disable the inbound direction: let this peer trigger our agent. */
export async function setPeerReverse(peerId: string, enabled: boolean): Promise<void> {
  const res = await fetch(`${getApiBase()}/nodes/peers/${peerId}/reverse`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
  if (!res.ok) throw new Error((await res.text()) || 'Failed to update inbound access');
}

export async function removePeer(peerId: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/nodes/peers/${peerId}/remove`, { method: 'POST' });
  if (!res.ok) throw new Error((await res.text()) || 'Failed to remove peer');
}

/** Start controlling a peer: request a grant, then poll until approved. */
export async function requestControl(baseUrl: string): Promise<{ request_id: string; base_url: string }> {
  const res = await fetch(`${getApiBase()}/nodes/control`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ base_url: baseUrl }),
  });
  if (!res.ok) throw new Error((await res.text()) || 'Failed to request control');
  return await res.json();
}

export async function controlStatus(baseUrl: string, requestId: string, name = ''): Promise<{ status: string; peer_id?: string }> {
  const url = `${getApiBase()}/nodes/control-status?base_url=${encodeURIComponent(baseUrl)}&request_id=${encodeURIComponent(requestId)}&name=${encodeURIComponent(name)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error((await res.text()) || 'Failed to poll control status');
  return await res.json();
}

export async function fetchNodeConfig(): Promise<NodeAuthConfig> {
  const res = await fetch(`${getApiBase()}/nodes/config`);
  if (!res.ok) throw new Error('Failed to load node config');
  return await res.json();
}

export async function saveNodeConfig(
  updates: { node_lan_bind?: boolean }
): Promise<NodeAuthConfig & { restart_required?: boolean }> {
  const res = await fetch(`${getApiBase()}/nodes/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error((await res.text()) || 'Failed to save node config');
  return await res.json();
}

export async function saveGlobalSandboxConfig(sandbox_volumes: string[]): Promise<string[]> {
  const res = await fetch(`${getApiBase()}/config/sandbox-global`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sandbox_volumes })
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || 'Failed to save global sandbox configuration');
  }

  const data = await res.json();
  return data.globalSandboxVolumes || sandbox_volumes;
}

export async function saveUserPreferences(preferences: {
  model?: string;
  agent?: string;
  tools?: string[];
  memory_enabled?: boolean;
  sandbox_enabled?: boolean;
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
    return await res.json();
  } catch (e) {
    console.error(e);
    return { success: false, models: [], error: String(e) };
  }
}

export interface CustomProviderPayload {
  id: string;
  label: string;
  api_type: string;
  base_url?: string;
  env_keys?: string[];
  fields?: Array<{ key: string; label: string; placeholder: string; type: 'secret' | 'text' }>;
  default_models?: Model[];
  logo_url?: string;
}

export async function saveCustomProvider(payload: CustomProviderPayload): Promise<{ success: boolean; error?: string }> {
  try {
    const res = await fetch(`${getApiBase()}/config/providers/custom`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

export async function deleteCustomProvider(providerId: string): Promise<{ success: boolean; error?: string }> {
  try {
    const res = await fetch(`${getApiBase()}/config/providers/custom/${providerId}`, {
      method: 'DELETE',
    });
    return await res.json();
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

export async function syncCapabilities(): Promise<{ success: boolean; providers?: number; models?: number; error?: string }> {
  try {
    const res = await fetch(`${getApiBase()}/config/capabilities/sync`, { method: 'POST' });
    return await res.json();
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

// -----------------------------------------------------------------------------
// ChatGPT Subscription
// -----------------------------------------------------------------------------

export async function fetchChatGPTStatus(): Promise<ChatGPTStatusResponse | null> {
  try {
    const res = await fetch(`${getApiBase()}/chatgpt/status`);
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    console.error('Error fetching ChatGPT status:', e);
    return null;
  }
}

export async function startChatGPTLogin(): Promise<ChatGPTLoginResponse> {
  try {
    const res = await fetch(`${getApiBase()}/chatgpt/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    return await res.json();
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

export async function logoutChatGPT(): Promise<{ success: boolean; error?: string }> {
  try {
    const res = await fetch(`${getApiBase()}/chatgpt/logout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    return await res.json();
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

// -----------------------------------------------------------------------------
// Role Models
// -----------------------------------------------------------------------------

export async function fetchRoleSuggestions(): Promise<Record<string, string[]>> {
  try {
    const res = await fetch(`${getApiBase()}/config/role-suggestions`);
    if (!res.ok) return {};
    return await res.json();
  } catch (e) {
    console.error('Error fetching role suggestions:', e);
    return {};
  }
}

export async function fetchRoleModels(): Promise<Record<string, string[]>> {
  try {
    const res = await fetch(`${getApiBase()}/config/role-models`);
    if (!res.ok) return {};
    const data = await res.json();
    return data.roles || {};
  } catch (e) {
    console.error('Error fetching role models:', e);
    return {};
  }
}

export async function saveRoleModels(roles: Record<string, string[]>): Promise<boolean> {
  try {
    const res = await fetch(`${getApiBase()}/config/role-models`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roles }),
    });
    return res.ok;
  } catch (e) {
    console.error('Error saving role models:', e);
    return false;
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

export interface PairingRequest {
  token: string;
  sender_id: string;
  sender_name: string;
  platform: string;
  intro: string;
  state: string;
  requested_at: number;
  expires_at: number;
}

export async function fetchPairings(): Promise<PairingRequest[]> {
  try {
    const res = await fetch(`${getApiBase()}/social/pairing`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.pairings || [];
  } catch {
    return [];
  }
}

export async function approvePairing(token: string): Promise<boolean> {
  try {
    const res = await fetch(`${getApiBase()}/social/pairing/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function denyPairing(token: string): Promise<boolean> {
  try {
    const res = await fetch(`${getApiBase()}/social/pairing/deny`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });
    return res.ok;
  } catch {
    return false;
  }
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

export async function markChatRead(chatId: string): Promise<void> {
  try {
    await fetch(`${getApiBase()}/chats/${chatId}/mark-read`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
  } catch { }
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
  heartbeat_instructions?: string;
  last_run_at: string | null;
  last_result: string | null;
  last_error: string | null;
  heartbeat_due?: boolean;
}

export async function fetchHeartbeatStatus(chatId?: string): Promise<HeartbeatStatus> {
  const url = chatId ? `${getApiBase()}/heartbeat/status?chat_id=${encodeURIComponent(chatId)}` : `${getApiBase()}/heartbeat/status`;
  const res = await fetch(url);
  if (!res.ok) throw new Error('Failed to fetch heartbeat status');
  return res.json();
}

export async function enableHeartbeat(chatId?: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/heartbeat/enable`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(chatId ? { chat_id: chatId } : {})
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || 'Failed to enable heartbeat');
  }
}

export async function disableHeartbeat(chatId?: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/heartbeat/disable`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(chatId ? { chat_id: chatId } : {})
  });
  if (!res.ok) throw new Error('Failed to disable heartbeat');
}

export async function triggerHeartbeat(chatId?: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/heartbeat/trigger`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(chatId ? { chat_id: chatId } : {})
  });
  if (!res.ok) throw new Error('Failed to trigger heartbeat');
}

export async function setHeartbeatInterval(minutes: number, chatId?: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/heartbeat/interval`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ interval_minutes: minutes, chat_id: chatId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || 'Failed to set heartbeat interval');
  }
}

export async function fetchHeartbeatMd(chatId?: string): Promise<{ content: string; exists: boolean }> {
  if (!chatId) return { content: '', exists: false };
  const res = await fetch(`${getApiBase()}/heartbeat/md?chat_id=${encodeURIComponent(chatId)}`);
  if (!res.ok) return { content: '', exists: false };
  return res.json();
}

export async function saveHeartbeatMd(content: string, chatId?: string): Promise<boolean> {
  if (!chatId) return false;
  const res = await fetch(`${getApiBase()}/heartbeat/md`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, chat_id: chatId }),
  });
  return res.ok;
}

export interface HeartbeatGlobalConfig {
  allowed_tools?: string[];
}

export async function fetchHeartbeatGlobalConfig(): Promise<HeartbeatGlobalConfig> {
  try {
    const res = await fetch(`${getApiBase()}/heartbeat/config`);
    if (!res.ok) return {};
    return res.json();
  } catch {
    return {};
  }
}

export async function saveHeartbeatGlobalConfig(cfg: HeartbeatGlobalConfig): Promise<void> {
  await fetch(`${getApiBase()}/heartbeat/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  });
}

// -----------------------------------------------------------------------------
// Cost Tracking
// -----------------------------------------------------------------------------

export interface CostGlobal {
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_calls: number;
  days: number;
}

export interface CostDaily {
  date: string;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  calls: number;
}

export async function fetchGlobalCost(days = 30): Promise<CostGlobal> {
  const res = await fetch(`${getApiBase()}/config/cost/global?days=${days}`);
  if (!res.ok) throw new Error('Failed to fetch global cost');
  return res.json();
}

export async function fetchDailyCost(days = 30): Promise<CostDaily[]> {
  const res = await fetch(`${getApiBase()}/config/cost/daily?days=${days}`);
  if (!res.ok) throw new Error('Failed to fetch daily cost');
  return res.json();
}

export async function fetchHourlyCost(days = 30): Promise<CostDaily[]> {
  const res = await fetch(`${getApiBase()}/config/cost/hourly?days=${days}`);
  if (!res.ok) throw new Error('Failed to fetch hourly cost');
  return res.json();
}

export async function fetchActivityGrid(range: string): Promise<CostDaily[]> {
  const res = await fetch(`${getApiBase()}/config/cost/activity-grid?range=${range}`);
  if (!res.ok) throw new Error('Failed to fetch activity grid');
  return res.json();
}

export interface CostModel {
  model: string;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  calls: number;
}

export async function fetchModelsCost(days = 30): Promise<CostModel[]> {
  const res = await fetch(`${getApiBase()}/config/cost/models?days=${days}`);
  if (!res.ok) throw new Error('Failed to fetch models cost');
  return res.json();
}

export interface ActivityStats {
  cumulative_tokens: number;
  peak_tokens: number;
  current_streak: number;
  longest_streak: number;
}

export async function fetchActivityStats(): Promise<ActivityStats> {
  const res = await fetch(`${getApiBase()}/config/cost/activity`);
  if (!res.ok) throw new Error('Failed to fetch activity stats');
  return res.json();
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
