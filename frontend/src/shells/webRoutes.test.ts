import { describe, expect, it } from 'vitest';

import { tForLocale, type Locale } from '../i18n';
import { WEB_DESTINATIONS } from './webRoutes';

const LOCALES: Locale[] = ['en', 'zh-CN'];

describe('WEB_DESTINATIONS', () => {
  it('has chat at the root, since that is also the fallback route', () => {
    expect(WEB_DESTINATIONS[0]?.path).toBe('/');
  });

  it('gives every destination a distinct path', () => {
    const paths = WEB_DESTINATIONS.map((d) => d.path);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it('labels every destination in every locale', () => {
    // A missing key falls back to the key itself, which would ship a rail of
    // dotted identifiers rather than words.
    for (const locale of LOCALES) {
      for (const { labelKey } of WEB_DESTINATIONS) {
        expect(tForLocale(locale, labelKey), `${locale}:${labelKey}`).not.toBe(labelKey);
      }
    }
  });
});
