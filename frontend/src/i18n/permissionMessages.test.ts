import { describe, expect, it } from 'vitest';
import { tForLocale } from './index';

describe('permission card translations', () => {
  for (const locale of ['en', 'zh-CN'] as const) {
    it(`resolves inline review metadata in ${locale}`, () => {
      const paths = [
        ...['policy', 'rule', 'auto_classifier', 'full_access'].map(
          (source) => `toolCallBlock.permissionSources.${source}`
        ),
        ...['once', 'session', 'global'].map((scope) => `toolCallBlock.permissionScopes.${scope}`),
        ...['safe', 'low', 'medium', 'high', 'critical'].map(
          (risk) => `permissionDock.riskLevels.${risk}`
        ),
      ];
      for (const path of paths) expect(tForLocale(locale, path)).not.toBe(path);
    });
    it(`resolves permission labels in ${locale}`, () => {
      for (const key of [
        'allowOptions',
        'riskLabel',
        'scope',
        'once',
        'commandSession',
        'commandAlways',
        'feedback',
        'allow',
        'decline',
      ]) {
        const path = `permissionDock.${key}`;
        expect(tForLocale(locale, path, { risk: 'test' })).not.toBe(path);
      }
    });
  }
});
