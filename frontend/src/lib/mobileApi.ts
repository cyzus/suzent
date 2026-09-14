import { getApiBase } from './api';

export interface MobilePermissions {
  chat_ids: string[];
  all_chats: boolean;
  create_chats: boolean;
  send: boolean;
  stop: boolean;
}
export interface MobileDevice {
  device_id: string;
  display_name: string;
  platform: 'ios' | 'android';
  permissions: MobilePermissions;
}
export interface MobilePending {
  pairing_id: string;
  display_name: string;
  platform: 'ios' | 'android';
  expires_at: number;
}
export interface MobileInvitation {
  pairing_id: string;
  invitation: string;
  expires_at: number;
}
export async function mobileRequest<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${getApiBase()}/mobile/${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: 'no-store',
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

export function mobilePairingPayload(origin: string, invitation: MobileInvitation): string {
  const url = new URL(origin);
  if (
    !['http:', 'https:'].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== '/'
  )
    throw new Error('Invalid backend origin');
  return JSON.stringify({
    type: 'suzent.mobile',
    pairing_protocol: 1,
    origin: url.origin,
    ...invitation,
  });
}
