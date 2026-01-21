import { ConfigOptions } from '../types/api';

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
  const res = await fetch('/api/mcp_servers');
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

  const res = await fetch('/api/mcp_servers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error('Failed to add MCP server');
}

export async function removeMcpServer(name: string): Promise<void> {
  const res = await fetch('/api/mcp_servers/remove', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name })
  });
  if (!res.ok) throw new Error('Failed to remove MCP server');
}

export async function setMcpServerEnabled(name: string, enabled: boolean): Promise<void> {
  const res = await fetch('/api/mcp_servers/enabled', {
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
    const res = await fetch('/api/config');
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
    const res = await fetch('/api/preferences', {
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
    const res = await fetch('/api/config/embedding-models');
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
    const res = await fetch('/api/config/api-keys');
    if (!res.ok) throw new Error('Failed to fetch API keys');
    return await res.json();
  } catch (e) {
    console.error(e);
    return null;
  }
}

export async function saveApiKeys(keys: Record<string, string>): Promise<boolean> {
  try {
    const res = await fetch('/api/config/api-keys', {
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
    const res = await fetch(`/api/config/providers/${providerId}/verify`, {
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
