import { describe, expect, it } from 'vitest';
import { buildOrderByMessageIndex, orderForMessageIndex } from './chatMinimapPosition';

const markers = [
  { targetIndex: 0, relatedIndices: [1, 2] },
  { targetIndex: 3, relatedIndices: [4] },
  { targetIndex: 7, relatedIndices: [] },
];

describe('minimap position mapping', () => {
  it('maps a marker and everything it speaks for to one tick', () => {
    const byIndex = buildOrderByMessageIndex(markers);
    expect(orderForMessageIndex(byIndex, 0)).toBe(0);
    expect(orderForMessageIndex(byIndex, 2)).toBe(0);
    expect(orderForMessageIndex(byIndex, 3)).toBe(1);
    expect(orderForMessageIndex(byIndex, 7)).toBe(2);
  });

  it('puts a row with no tick of its own on the turn it sits inside', () => {
    const byIndex = buildOrderByMessageIndex(markers);
    // 5 and 6 fall between marker 1 (index 3) and marker 2 (index 7).
    expect(orderForMessageIndex(byIndex, 5)).toBe(1);
    expect(orderForMessageIndex(byIndex, 6)).toBe(1);
    // Past the last marker, it still belongs to that last turn.
    expect(orderForMessageIndex(byIndex, 99)).toBe(2);
  });

  it('does not claim a message that precedes every marker', () => {
    const byIndex = buildOrderByMessageIndex([{ targetIndex: 5, relatedIndices: [] }]);
    expect(orderForMessageIndex(byIndex, 2)).toBeNull();
  });

  it('lets the first marker win an index two markers both mention', () => {
    const byIndex = buildOrderByMessageIndex([
      { targetIndex: 0, relatedIndices: [1] },
      { targetIndex: 2, relatedIndices: [1] },
    ]);
    expect(orderForMessageIndex(byIndex, 1)).toBe(0);
  });

  it('handles an empty rail', () => {
    expect(orderForMessageIndex(buildOrderByMessageIndex([]), 0)).toBeNull();
  });
});
