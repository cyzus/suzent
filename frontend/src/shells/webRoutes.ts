/**
 * The browser's routes.
 *
 * A browser lays out like the desktop -- one sidebar that swaps its chat list
 * for the settings list -- but every settings category also has an address of
 * its own, so the back button, a reload and a bookmark all land where they
 * should. The desktop has no address bar and keeps settings in memory.
 */

import {
  SETTINGS_CATEGORY_IDS,
  isCategoryAvailable,
  type SettingsCategory,
} from '../components/settings/SettingsNavigation';

export const CHAT_PATH = '/';

/**
 * Where "/settings" goes now that each category has its own address.
 *
 * That URL is in released docs and in whatever anyone bookmarked, so it lands
 * on the first category rather than on chat.
 */
export const LEGACY_SETTINGS_PATH = '/settings';
export const LEGACY_SETTINGS_TARGET = '/providers';

/**
 * Pages that still open when the host does not answer.
 *
 * They take no props and read no shared settings state, so they can render
 * without the chat providers -- and a browser opened at a struggling host is
 * opened to look at exactly these.
 */
export const OFFLINE_CATEGORIES: readonly SettingsCategory[] = [
  'devices',
  'mesh',
  'ops',
  'usage',
  'about',
];

export function pathForCategory(category: SettingsCategory): string {
  return `/${category}`;
}

/** The settings category a route shows, or null for chat and unknown routes. */
export function categoryForPath(path: string): SettingsCategory | null {
  const id = path.replace(/^\//, '') as SettingsCategory;
  if (!SETTINGS_CATEGORY_IDS.includes(id)) return null;
  return isCategoryAvailable(id) ? id : null;
}

/** The troubleshooting page a route shows, if it is one. */
export function offlineCategoryForPath(path: string): SettingsCategory | null {
  const category = categoryForPath(path);
  return category && OFFLINE_CATEGORIES.includes(category) ? category : null;
}
