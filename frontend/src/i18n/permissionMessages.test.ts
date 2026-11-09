import { describe, expect, it } from 'vitest';
import { tForLocale } from './index';

describe('permission card translations', () => {
  for (const locale of ['en', 'zh-CN'] as const) {
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
