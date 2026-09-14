import { describe, expect, it } from 'vitest';
import { mobilePairingPayload } from './mobileApi';

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
