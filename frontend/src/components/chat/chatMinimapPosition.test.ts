import { describe, expect, it } from 'vitest';
import {
  buildOrderByMessageIndex,
  isAtScrollEnd,
  orderForMessageIndex,
  probeOffsetPx,
} from './chatMinimapPosition';

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

describe('isAtScrollEnd', () => {
  it('is true at the bottom, so the final tick can light up', () => {
    // A short last message rests against the bottom edge and never reaches the
    // middle of the viewport, so nothing else would ever select it.
    expect(isAtScrollEnd(4000, 600, 4600)).toBe(true);
  });

  it('tolerates the sub-pixel gap a fractional scroll leaves behind', () => {
    expect(isAtScrollEnd(3999.4, 600, 4600)).toBe(true);
  });

  it('is false while there is still content below', () => {
    expect(isAtScrollEnd(3000, 600, 4600)).toBe(false);
  });

  it('is true when the content does not fill the viewport', () => {
    expect(isAtScrollEnd(0, 600, 400)).toBe(true);
  });
});

describe('probeOffsetPx', () => {
  it('asks at the top edge when scrolled to the top', () => {
    // The first message rests against the top edge and never reaches the
    // middle, which is why the first tick could not be selected.
    expect(probeOffsetPx(0, 600, 4600)).toBe(0);
  });

  it('asks at the bottom edge when scrolled to the end', () => {
    expect(probeOffsetPx(4000, 600, 4600)).toBe(600);
  });

  it('asks at the middle halfway through', () => {
    expect(probeOffsetPx(2000, 600, 4600)).toBe(300);
  });

  it('falls back to the middle when there is nothing to scroll', () => {
    expect(probeOffsetPx(0, 600, 400)).toBe(300);
  });

  it('clamps a rubber-banded scroll position', () => {
    expect(probeOffsetPx(-50, 600, 4600)).toBe(0);
    expect(probeOffsetPx(99999, 600, 4600)).toBe(600);
  });
});
