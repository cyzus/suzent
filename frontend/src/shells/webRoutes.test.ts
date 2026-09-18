import { describe, expect, it } from 'vitest';

import { tForLocale, type Locale } from '../i18n';
import { LEGACY_SETTINGS_TARGET, WEB_DESTINATIONS, WEB_DESTINATION_GROUPS } from './webRoutes';
import { SETTINGS_CATEGORY_IDS } from '../components/settings/SettingsNavigation';

const LOCALES: Locale[] = ['en', 'zh-CN'];

/** Categories a browser cannot show: both drive Tauri commands. */
const DESKTOP_ONLY = ['browser', 'service'];

describe('WEB_DESTINATIONS', () => {
  it('has chat at the root, since that is also the fallback route', () => {
    expect(WEB_DESTINATIONS[0]?.path).toBe('/');
  });

  it('gives every destination a distinct path', () => {
    const paths = WEB_DESTINATIONS.map((d) => d.path);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it('labels every destination in every locale', () => {
    // A missing key falls back to the key itself, which would ship a sidebar of
    // dotted identifiers rather than words.
    for (const locale of LOCALES) {
      for (const { labelKey } of WEB_DESTINATIONS) {
        expect(tForLocale(locale, labelKey), `${locale}:${labelKey}`).not.toBe(labelKey);
      }
    }
  });

  it('labels every group heading in every locale', () => {
    for (const locale of LOCALES) {
      for (const { labelKey } of WEB_DESTINATION_GROUPS) {
        if (!labelKey) continue;
        expect(tForLocale(locale, labelKey), `${locale}:${labelKey}`).not.toBe(labelKey);
      }
    }
  });

  it('names only settings categories that actually exist', () => {
    // A typo here would render an empty page: the panel switch matches on this
    // string and has no branch that reports not recognising one.
    for (const { category } of WEB_DESTINATIONS) {
      if (category === undefined) continue;
      expect(SETTINGS_CATEGORY_IDS, category).toContain(category);
    }
  });

  it('gives every category a distinct destination', () => {
    // Two routes onto one category is the duplication the old rail-plus-sidebar
    // split had to be policed for.
    const categories = WEB_DESTINATIONS.flatMap((d) => (d.category ? [d.category] : []));
    expect(new Set(categories).size).toBe(categories.length);
  });

  it('reaches every category a browser can show', () => {
    // The point of merging the two navigations: nothing is left behind in a
    // list that no longer exists.
    const reachable = new Set(WEB_DESTINATIONS.map((d) => d.category));
    const missing = SETTINGS_CATEGORY_IDS.filter(
      (id) => !DESKTOP_ONLY.includes(id) && !reachable.has(id)
    );
    expect(missing).toEqual([]);
  });

  it('sends the retired settings route at a destination that exists', () => {
    expect(WEB_DESTINATIONS.map((d) => d.path)).toContain(LEGACY_SETTINGS_TARGET);
  });
});
