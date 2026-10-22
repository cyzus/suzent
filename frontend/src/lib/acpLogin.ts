import { getApiBase } from './api';
import type { AcpProbeResult } from './api';

export interface AcpLoginState {
  attempt: number;
  status:
    | 'idle'
    | 'starting'
    | 'authenticating'
    | 'terminal'
    | 'verifying'
    | 'ready'
    | 'failed'
    | 'cancelled';
  error: 'unavailable' | 'failed' | 'timeout' | 'verification_failed' | null;
  result: AcpProbeResult | null;
}

export function isLoginActive(state?: AcpLoginState): boolean {
  return !!state && ['starting', 'authenticating', 'terminal', 'verifying'].includes(state.status);
}

async function request<T>(path: string, method: string, body?: object): Promise<T> {
  const response = await fetch(`${getApiBase()}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) throw new Error('ACP login request failed');
  return response.json() as Promise<T>;
}

export const fetchAcpLogins = (): Promise<Record<string, AcpLoginState>> =>
  request('/acp/logins', 'GET');
export const startAcpLogin = (id: string, methodId?: string): Promise<AcpLoginState> =>
  request(
    `/acp/agents/${encodeURIComponent(id)}/login`,
    'POST',
    methodId ? { method_id: methodId } : {}
  );
export const cancelAcpLogin = (id: string): Promise<AcpLoginState> =>
  request(`/acp/agents/${encodeURIComponent(id)}/login`, 'DELETE');
