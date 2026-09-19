import { describe, expect, it } from 'vitest';
import { mobilePairingPayload, mobilePairingOrigins } from './mobileApi';

const invitation = { pairing_id: 'a'.repeat(32), invitation: 'b'.repeat(43), expires_at: 12345 };

describe('mobile QR payload', () => {
  it('includes the exact invitation and explicit protocol without a durable token', () => {
    expect(JSON.parse(mobilePairingPayload('https://desktop.example:25314/', invitation))).toEqual({
      type: 'suzent.mobile',
      pairing_protocol: 1,
      origin: 'https://desktop.example:25314',
      ...invitation,
    });
  });
  it.each([
    'file:///etc/passwd',
    'https://user:secret@desktop.example',
    'https://desktop.example/path',
    'https://desktop.example/?token=secret',
    'https://desktop.example/#fragment',
  ])('rejects ambiguous or credential-bearing origin %s', (origin) => {
    expect(() => mobilePairingPayload(origin, invitation)).toThrow();
  });
});

it('includes deduplicated LAN and Tailscale candidates while retaining the legacy origin', () => {
  const payload = JSON.parse(
    mobilePairingPayload('http://192.168.1.2:25314', invitation, [
      'http://192.168.1.2:25314/',
      'http://100.64.1.2:25314',
      'https://desktop.example',
    ])
  );
  expect(payload.origin).toBe('http://192.168.1.2:25314');
  expect(payload.origins).toEqual([
    'http://192.168.1.2:25314',
    'http://100.64.1.2:25314',
    'https://desktop.example',
  ]);
  expect(() =>
    mobilePairingPayload('https://desktop.example', invitation, [
      'https://user:secret@other.example',
    ])
  ).toThrow();
  expect(() =>
    mobilePairingPayload(
      'https://desktop.example',
      invitation,
      Array.from({ length: 6 }, (_, i) => `https://host${i}.example`)
    )
  ).toThrow();
});

it('collects detected LAN and Tailscale endpoints with the preferred address first', () => {
  expect(
    mobilePairingOrigins('http://192.168.1.2:25314', [
      { label: 'LAN', host: '192.168.1.2', gateway_url: 'ws://192.168.1.2:25314/ws/node' },
      { label: 'Tailscale', host: '100.64.1.2', gateway_url: 'ws://100.64.1.2:25314/ws/node' },
      { label: 'MagicDNS', host: 'desktop.example', gateway_url: 'wss://desktop.example/ws/node' },
    ])
  ).toEqual(['http://192.168.1.2:25314', 'http://100.64.1.2:25314', 'https://desktop.example']);
});

it('marks phone-confirmed invitations without embedding permissions in the QR', () => {
  const payload = JSON.parse(
    mobilePairingPayload('https://desktop.example', { ...invitation, approval: 'phone' })
  );
  expect(payload.approval).toBe('phone');
  expect(payload).not.toHaveProperty('permissions');
});

it('uses only device-verified HTTPS candidates for local TLS invitations', () => {
  const tls = { version: 1, ca_certificate: 'fixture', fingerprint: 'fixture' };
  const payload = JSON.parse(
    mobilePairingPayload(
      'http://192.168.1.2:25314',
      {
        ...invitation,
        tls,
        origins: ['https://192.168.1.2:25443', 'https://desktop.local:25443'],
      },
      ['http://192.168.1.3:25314']
    )
  );
  expect(payload.pairing_protocol).toBe(2);
  expect(payload.origin).toBe('https://192.168.1.2:25443');
  expect(payload.origins).toEqual(['https://192.168.1.2:25443', 'https://desktop.local:25443']);
  expect(payload.tls).toEqual(tls);
});
