import { getApiBase } from './api';

export interface AcpPairingStatus {
  pending: { request_id: string; client_name: string; code: string; expires_at: number }[];
  grants: { grant_id: string; client_name: string; approved_at: number }[];
}

async function request<T>(path: string, method: string, body?: object): Promise<T> {
  const response = await fetch(`${getApiBase()}/acp/auth/${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || data.detail || `ACP: ${response.status}`);
  return data as T;
}

export function fetchAcpPairing(): Promise<AcpPairingStatus> {
  return request('status', 'GET');
}

export function decideAcpPairing(id: string, approved: boolean): Promise<{ ok: boolean }> {
  return request(`requests/${encodeURIComponent(id)}/decide`, 'POST', { approved });
}

export function revokeAcpGrant(id: string): Promise<{ ok: boolean }> {
  return request(`grants/${encodeURIComponent(id)}`, 'DELETE');
}
