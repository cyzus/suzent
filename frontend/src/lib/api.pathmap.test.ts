import { describe, expect, it } from 'vitest';
import { parseVolumeString, mapHostPathToVirtual } from './api';

describe('parseVolumeString', () => {
  it('parses a Windows host with a drive-letter colon', () => {
    expect(parseVolumeString('D:\\workspace\\suzent:/mnt/suzent')).toEqual([
      'D:\\workspace\\suzent',
      '/mnt/suzent',
    ]);
  });

  it('parses a unix host:container pair', () => {
    expect(parseVolumeString('/home/user/proj:/mnt/proj')).toEqual([
      '/home/user/proj',
      '/mnt/proj',
    ]);
  });

  it('returns null for malformed strings', () => {
    expect(parseVolumeString('nonsense')).toBeNull();
    expect(parseVolumeString('')).toBeNull();
  });
});

describe('mapHostPathToVirtual', () => {
  const volumes = ['D:\\workspace\\suzent:/mnt/suzent'];

  it('maps a windows host path (from file://) to its container path', () => {
    // file:// on Windows produces "/D:/workspace/suzent/docs/x.md"
    expect(
      mapHostPathToVirtual('/D:/workspace/suzent/docs/plans/x.md', volumes),
    ).toBe('/mnt/suzent/docs/plans/x.md');
  });

  it('maps the mount root itself', () => {
    expect(mapHostPathToVirtual('/D:/workspace/suzent', volumes)).toBe('/mnt/suzent');
  });

  it('leaves an existing virtual path untouched', () => {
    expect(mapHostPathToVirtual('/mnt/suzent/docs/x.md', volumes)).toBe(
      '/mnt/suzent/docs/x.md',
    );
    expect(mapHostPathToVirtual('/workspace/a.txt', volumes)).toBe('/workspace/a.txt');
  });

  it('returns a normalized path when no volume matches', () => {
    expect(mapHostPathToVirtual('/E:/other/x.md', volumes)).toBe('E:/other/x.md');
  });

  it('prefers the longest matching mount', () => {
    const nested = [
      'D:\\workspace:/mnt/ws',
      'D:\\workspace\\suzent:/mnt/suzent',
    ];
    expect(mapHostPathToVirtual('/D:/workspace/suzent/docs/x.md', nested)).toBe(
      '/mnt/suzent/docs/x.md',
    );
  });
});
