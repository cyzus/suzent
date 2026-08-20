import { describe, it, expect } from 'vitest';
import { tForLocale } from './index';

const KEYS = [
  'chatInput.engineGroups.models',
  'chatInput.engineGroups.acp',
  'chatInput.acpNotInstalled',
  'chatInput.acpInstallHint',
  'acp.permission.header',
  'acp.permission.approved',
  'acp.permission.denied',
  'acp.permission.expired',
  'acp.permission.untitled',
  'acp.sessionReset.header',
  'chatWindow.acpAgentLocked',
];

// Guards against adding a string under the wrong namespace: tForLocale falls
// back to returning the key itself, so a misplaced entry renders as raw text.
describe('acp i18n keys resolve', () => {
  for (const locale of ['en', 'zh-CN'] as const) {
    for (const key of KEYS) {
      it(`${locale}: ${key}`, () => {
        expect(tForLocale(locale, key)).not.toBe(key);
      });
    }
  }
  it('interpolates the runtime signature lines', () => {
    for (const locale of ['en', 'zh-CN'] as const) {
      const external = tForLocale(locale, 'chatMessage.runtime.external', { agent: 'claude-code' });
      expect(external).toContain('claude-code');
      expect(external).not.toContain('{agent}');
      const native = tForLocale(locale, 'chatMessage.runtime.suzent', { model: 'gpt-5' });
      expect(native).toContain('gpt-5');
      expect(native).not.toContain('{model}');
    }
  });

  it('interpolates the session reset body', () => {
    const out = tForLocale('en', 'acp.sessionReset.body', { agent: 'claude-code' });
    expect(out).toContain('claude-code');
    expect(out).not.toContain('{agent}');
  });
});
