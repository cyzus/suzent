import { describe, expect, it } from 'vitest';

import { commitUrl, releaseNotesUrl, shortInstallationId } from './desktopAbout';

describe('desktopAbout helpers', () => {
  it('shortens the installation id for display', () => {
    expect(shortInstallationId('a9099b3ff88f4315deadbeefcafebabe')).toBe('a9099b3ff88f4315');
    expect(shortInstallationId(null)).toBeNull();
  });

  it('points release notes at the matching tag when known', () => {
    expect(releaseNotesUrl('v0.23.0')).toBe('https://github.com/cyzus/suzent/releases/tag/v0.23.0');
    expect(releaseNotesUrl('0.23.0')).toBe('https://github.com/cyzus/suzent/releases/tag/v0.23.0');
    expect(releaseNotesUrl(null)).toBe('https://github.com/cyzus/suzent/releases/latest');
  });

  it('builds a commit permalink', () => {
    expect(commitUrl('2bd378ed1b8d6b')).toBe(
      'https://github.com/cyzus/suzent/commit/2bd378ed1b8d6b'
    );
  });
});
