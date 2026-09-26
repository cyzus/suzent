import { getApiBase, type PairingAddress } from './api';

export interface MobilePermissions {
  chat_ids: string[];
  all_chats: boolean;
  create_chats: boolean;
  send: boolean;
  stop: boolean;
  approve_tools?: boolean;
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
  tls?: { version: number; ca_certificate: string; fingerprint: string };
  origins?: string[];
  approval?: 'phone';
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

function pairingOrigin(origin: string): string {
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
  return url.origin;
}

export function mobilePairingOrigins(origin: string, addresses: PairingAddress[] = []): string[] {
  return [
    ...new Set([
      pairingOrigin(origin),
      ...addresses.map((address) => {
        const url = new URL(address.gateway_url);
        if (
          !['ws:', 'wss:'].includes(url.protocol) ||
          url.username ||
          url.password ||
          url.search ||
          url.hash
        )
          throw new Error('Invalid discovery address');
        return `${url.protocol === 'wss:' ? 'https:' : 'http:'}//${url.host}`;
      }),
    ]),
  ].slice(0, 6);
}

export function mobilePairingPayload(
  origin: string,
  invitation: MobileInvitation,
  origins: string[] = []
): string {
  if (invitation.tls && !invitation.origins?.length)
    throw new Error('Missing secure backend addresses');
  const primary = pairingOrigin(invitation.tls ? invitation.origins![0] : origin);
  const candidates = [
    ...new Set([primary, ...(invitation.tls ? invitation.origins! : origins).map(pairingOrigin)]),
  ];
  if (candidates.length > 6) throw new Error('Too many backend addresses');
  if (invitation.tls && candidates.some((candidate) => new URL(candidate).protocol !== 'https:'))
    throw new Error('Device trust requires HTTPS');
  const value = JSON.stringify({
    type: 'suzent.mobile',
    pairing_protocol: invitation.tls ? 2 : 1,
    origin: primary,
    ...(candidates.length > 1 ? { origins: candidates } : {}),
    ...invitation,
  });
  if (new TextEncoder().encode(value).length > 4096)
    throw new Error('Pairing invitation too large');
  return value;
}

export async function cancelMobileInvitation(pairingId: string): Promise<void> {
  const response = await fetch(
    `${getApiBase()}/mobile/pairing/${encodeURIComponent(pairingId)}/cancel`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
      keepalive: true,
    }
  );
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
}
