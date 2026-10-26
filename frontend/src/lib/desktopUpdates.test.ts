import { beforeEach, describe, expect, it, vi } from 'vitest';

import { isNewerVersion, takeUpdatedVersion } from './desktopUpdates';

describe('isNewerVersion', () => {
  it('compares release numbers, not strings', () => {
    expect(isNewerVersion('0.17.0', '0.9.1')).toBe(true);
    expect(isNewerVersion('v0.17.1', '0.17.0')).toBe(true);
    expect(isNewerVersion('0.17.0', '0.17.0')).toBe(false);
    expect(isNewerVersion('0.16.9', '0.17.0')).toBe(false);
    expect(isNewerVersion('', '0.17.0')).toBe(false);
  });
});

describe('takeUpdatedVersion', () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => store.set(key, value),
    });
  });

  it('reports a version change once and stays quiet on first run', () => {
    expect(takeUpdatedVersion('0.16.0')).toBeNull();
    expect(takeUpdatedVersion('0.17.0')).toBe('0.17.0');
    expect(takeUpdatedVersion('0.17.0')).toBeNull();
  });

  it('does not report a downgrade', () => {
    takeUpdatedVersion('0.17.0');
    expect(takeUpdatedVersion('0.16.0')).toBeNull();
  });
});
