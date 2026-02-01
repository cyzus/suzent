import { ConfigOptions } from '../types/api';

// -----------------------------------------------------------------------------
// Tauri Integration
// -----------------------------------------------------------------------------

// Get backend port injected by Tauri (available in both dev and prod modes)
// Falls back to empty string for browser mode (uses relative URLs via Vite proxy)
function getApiBase(): string {
  // We strictly target Tauri desktop environment
  // The backend port is injected by the main process
  const port = window.__SUZENT_BACKEND_PORT__;

  if (port) {
    return `http://localhost:${port}`;
  }

  // Fallback for standard dev port if injection missing (e.g. during early init or HMR)
  return 'http://localhost:8000';
}

export const API_BASE = getApiBase();

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
  const res = await fetch(`${API_BASE}/mcp_servers`);
  if (!res.ok) throw new Error('Failed to fetch MCP servers');
  return res.json();
}

export async function addMcpServer(
  name: string,
  url?: string,
  stdio?: StdioConfig
): Promise<void> {
  const body: { name: string; url?: string; stdio?: StdioConfig } = { name };
  if (url) body.url = url;
  if (stdio) body.stdio = stdio;

  const res = await fetch(`${API_BASE}/mcp_servers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error('Failed to add MCP server');
}

export async function removeMcpServer(name: string): Promise<void> {
  const res = await fetch(`${API_BASE}/mcp_servers/remove`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name })
  });
  if (!res.ok) throw new Error('Failed to remove MCP server');
}

export async function setMcpServerEnabled(name: string, enabled: boolean): Promise<void> {
  const res = await fetch(`${API_BASE}/mcp_servers/enabled`, {
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
    const res = await fetch(`${API_BASE}/config`);
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
}): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/preferences`, {
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
    const res = await fetch(`${API_BASE}/config/embedding-models`);
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
    const res = await fetch(`${API_BASE}/config/api-keys`);
    if (!res.ok) throw new Error('Failed to fetch API keys');
    return await res.json();
  } catch (e) {
    console.error(e);
    return null;
  }
}

export async function saveApiKeys(keys: Record<string, string>): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/config/api-keys`, {
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
    const res = await fetch(`${API_BASE}/config/providers/${providerId}/verify`, {
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
