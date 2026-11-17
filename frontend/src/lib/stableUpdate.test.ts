import { describe, expect, it } from 'vitest';

import { shallowEqual, stableList, stableObject } from './stableUpdate';

describe('stableUpdate', () => {
  it('compares objects one level deep', () => {
    expect(shallowEqual({ a: 1, b: 'x' }, { a: 1, b: 'x' })).toBe(true);
    expect(shallowEqual({ a: 1 }, { a: 2 })).toBe(false);
    expect(shallowEqual<Record<string, number>>({ a: 1 }, { a: 1, b: 2 })).toBe(false);
  });

  it('keeps the previous object when nothing changed', () => {
    const prev = { you: 1, scheduled: 2, all: 3 };
    expect(stableObject(prev, { you: 1, scheduled: 2, all: 3 })).toBe(prev);
    const next = { you: 1, scheduled: 2, all: 4 };
    expect(stableObject(prev, next)).toBe(next);
  });

  it('returns the previous list when every item matches', () => {
    const prev = [
      { id: 'a', n: 1 },
      { id: 'b', n: 2 },
    ];
    expect(
      stableList(prev, [
        { id: 'a', n: 1 },
        { id: 'b', n: 2 },
      ])
    ).toBe(prev);
  });

  it('reuses unchanged items and swaps in changed ones', () => {
    const prev = [
      { id: 'a', n: 1 },
      { id: 'b', n: 2 },
    ];
    const changed = { id: 'b', n: 3 };
    const result = stableList(prev, [{ id: 'a', n: 1 }, changed]);
    expect(result).not.toBe(prev);
    expect(result[0]).toBe(prev[0]);
    expect(result[1]).toBe(changed);
  });

  it('treats a different length as a change', () => {
    const prev = [{ id: 'a' }];
    const result = stableList(prev, [{ id: 'a' }, { id: 'b' }]);
    expect(result).not.toBe(prev);
    expect(result[0]).toBe(prev[0]);
  });
});
