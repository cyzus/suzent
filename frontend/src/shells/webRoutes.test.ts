import { describe, expect, it } from 'vitest';

import { tForLocale, type Locale } from '../i18n';
import {
  CHAT_PATH,
  LEGACY_SETTINGS_TARGET,
  OFFLINE_CATEGORIES,
  categoryForPath,
  offlineCategoryForPath,
  pathForCategory,
} from './webRoutes';
import {
  SETTINGS_CATEGORY_IDS,
  isCategoryAvailable,
  visibleCategoryGroups,
} from '../components/settings/SettingsNavigation';

const LOCALES: Locale[] = ['en', 'zh-CN'];

/** Categories a browser cannot show: both drive Tauri commands. */
const DESKTOP_ONLY = ['browser', 'service'];

describe('web routes', () => {
  it('round-trips every category a browser can show', () => {
    for (const id of SETTINGS_CATEGORY_IDS) {
      if (DESKTOP_ONLY.includes(id)) continue;
      expect(categoryForPath(pathForCategory(id)), id).toBe(id);
    }
  });

  it('keeps desktop-only categories unroutable', () => {
    for (const id of DESKTOP_ONLY) {
      expect(categoryForPath(`/${id}`), id).toBeNull();
    }
  });

  it('treats chat and unknown paths as chat', () => {
    expect(categoryForPath(CHAT_PATH)).toBeNull();
    expect(categoryForPath('/no-such-page')).toBeNull();
  });

  it('sends the retired settings route at a category that exists', () => {
    expect(categoryForPath(LEGACY_SETTINGS_TARGET)).not.toBeNull();
  });

  it('opens only the troubleshooting pages without the host', () => {
    expect(offlineCategoryForPath('/devices')).toBe('devices');
    expect(offlineCategoryForPath('/ops')).toBe('ops');
    expect(offlineCategoryForPath('/providers')).toBeNull();
    for (const id of OFFLINE_CATEGORIES) expect(isCategoryAvailable(id), id).toBe(true);
  });
});

describe('settings navigation in a browser', () => {
  it('lists every category a browser can show exactly once', () => {
    const listed = visibleCategoryGroups().flatMap((group) =>
      group.categories.map((category) => category.id)
    );
    expect(new Set(listed).size).toBe(listed.length);
    const expected = SETTINGS_CATEGORY_IDS.filter((id) => !DESKTOP_ONLY.includes(id));
    expect([...listed].sort()).toEqual([...expected].sort());
  });

  it('gathers the pages about the host into one group', () => {
    const host = visibleCategoryGroups().find((group) => group.id === 'host');
    expect(host?.categories.map((category) => category.id)).toEqual([
      'devices',
      'mesh',
      'ops',
      'usage',
    ]);
  });

  it('labels every group and category in every locale', () => {
    // A missing key falls back to the key itself, which would ship a sidebar of
    // dotted identifiers rather than words.
    for (const locale of LOCALES) {
      for (const group of visibleCategoryGroups()) {
        expect(tForLocale(locale, group.labelKey), `${locale}:${group.labelKey}`).not.toBe(
          group.labelKey
        );
        for (const { labelKey } of group.categories) {
          expect(tForLocale(locale, labelKey), `${locale}:${labelKey}`).not.toBe(labelKey);
        }
      }
    }
  });
});
