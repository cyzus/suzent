import { describe, expect, it } from 'vitest';
import { parseUnifiedDiff } from './unifiedDiff';

describe('parseUnifiedDiff', () => {
  it('reconstructs original and modified content from a unified diff', () => {
    const parsed = parseUnifiedDiff([
      '--- a/example.txt',
      '+++ b/example.txt',
      '@@ -1,2 +1,2 @@',
      ' unchanged',
      '-before',
      '+after',
      '',
    ].join('\n'));

    expect(parsed).toEqual({
      original: 'unchanged\nbefore',
      modified: 'unchanged\nafter',
    });
  });

  it('separates multiple hunks without rendering diff metadata', () => {
    const parsed = parseUnifiedDiff([
      '--- a/example.txt',
      '+++ b/example.txt',
      '@@ -1 +1 @@',
      '-first',
      '+updated first',
      '@@ -20 +20 @@',
      '-last',
      '+updated last',
    ].join('\n'));

    expect(parsed).toEqual({
      original: 'first\n⋯\nlast',
      modified: 'updated first\n⋯\nupdated last',
    });
  });

  it('returns null when no textual hunk is available', () => {
    expect(parseUnifiedDiff('')).toBeNull();
    expect(parseUnifiedDiff('Binary files differ')).toBeNull();
  });
});
