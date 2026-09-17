import { describe, expect, it } from 'vitest';

import { tForLocale, type Locale } from '../i18n';
import { CONSOLE_HOSTED_CATEGORIES, WEB_DESTINATIONS } from './webRoutes';
import { SETTINGS_CATEGORY_IDS } from '../components/settings/SettingsNavigation';

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

describe('CONSOLE_HOSTED_CATEGORIES', () => {
  it('names only settings categories that actually exist', () => {
    // A typo here would silently fail to hide anything, and the duplicate tab
    // it was meant to remove would come back with nothing pointing at why.
    for (const category of CONSOLE_HOSTED_CATEGORIES) {
      expect(SETTINGS_CATEGORY_IDS, category).toContain(category);
    }
  });

  it('covers every destination that supersedes a settings tab', () => {
    const declared = WEB_DESTINATIONS.flatMap((d) =>
      d.settingsCategory === undefined ? [] : [d.settingsCategory]
    );
    expect([...CONSOLE_HOSTED_CATEGORIES].sort()).toEqual(declared.sort());
  });
});
