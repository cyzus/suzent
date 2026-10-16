import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  DEFAULT_NOTIFICATION_PREFERENCES,
  readNotificationPreferences,
  shouldNotifyForCompletion,
  writeNotificationPreferences,
} from './notificationPreferences';

const STORAGE_KEY = 'suzent-notification-preferences';

function createMemoryStorage(): Storage {
  const map = new Map<string, string>();
  return {
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
    getItem: (key: string) => (map.has(key) ? map.get(key)! : null),
    key: (index: number) => Array.from(map.keys())[index] ?? null,
    removeItem: (key: string) => {
      map.delete(key);
    },
    setItem: (key: string, value: string) => {
      map.set(key, String(value));
    },
  } as Storage;
}

function setVisibility(state: 'visible' | 'hidden'): void {
  vi.stubGlobal('document', { visibilityState: state });
}

describe('notification preferences', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', createMemoryStorage());
  });

  afterEach(() => vi.unstubAllGlobals());

  it('defaults to always notify with a chime when nothing is stored', () => {
    expect(readNotificationPreferences()).toEqual(DEFAULT_NOTIFICATION_PREFERENCES);
  });

  it('round-trips a stored preference', () => {
    writeNotificationPreferences({ when: 'never', sound: 'ping' });
    expect(readNotificationPreferences()).toEqual({ when: 'never', sound: 'ping' });
  });

  it('drops corrupt values and falls back to defaults', () => {
    localStorage.setItem(STORAGE_KEY, '{not json');
    expect(readNotificationPreferences()).toEqual(DEFAULT_NOTIFICATION_PREFERENCES);

    localStorage.setItem(STORAGE_KEY, JSON.stringify({ when: 'bogus', sound: 'bogus' }));
    expect(readNotificationPreferences()).toEqual(DEFAULT_NOTIFICATION_PREFERENCES);
  });

  it('never notifies when the policy is "never"', () => {
    expect(shouldNotifyForCompletion('never')).toBe(false);
  });

  it('always notifies when the policy is "always"', () => {
    setVisibility('visible');
    expect(shouldNotifyForCompletion('always')).toBe(true);
  });

  it('notifies in the background only when the window is hidden', () => {
    setVisibility('visible');
    expect(shouldNotifyForCompletion('background')).toBe(false);

    setVisibility('hidden');
    expect(shouldNotifyForCompletion('background')).toBe(true);
  });
});
