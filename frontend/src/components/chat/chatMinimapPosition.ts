/**
 * Placing the reader on the minimap rail.
 *
 * The rail is an ordinal axis: one tick per marker, evenly spaced, whatever
 * the messages behind them weigh. Anything derived from scrollTop is a pixel
 * axis over only the messages currently mounted. Mapping between the two is
 * what makes the position marker wrong, so the position is resolved in tick
 * order instead -- these helpers are that mapping.
 */

export interface MarkerIndices {
  targetIndex: number;
  relatedIndices: number[];
}

/** Every message index a marker speaks for, mapped to that marker's order. */
export function buildOrderByMessageIndex(markers: MarkerIndices[]): Map<number, number> {
  const byIndex = new Map<number, number>();
  markers.forEach((marker, order) => {
    byIndex.set(marker.targetIndex, order);
    for (const related of marker.relatedIndices) {
      if (!byIndex.has(related)) byIndex.set(related, order);
    }
  });
  return byIndex;
}

/**
 * The tick a message belongs to. A row with no tick of its own -- a notice, a
 * system turn -- belongs to the turn it sits inside: the nearest tick at or
 * above it. Returns null for a message that precedes every marker.
 */
export function orderForMessageIndex(byIndex: Map<number, number>, index: number): number | null {
  const exact = byIndex.get(index);
  if (exact !== undefined) return exact;

  let best: number | null = null;
  let bestIndex = -1;
  for (const [messageIndex, order] of byIndex) {
    if (messageIndex <= index && messageIndex > bestIndex) {
      bestIndex = messageIndex;
      best = order;
    }
  }
  return best;
}

/**
 * Whether the scroller has reached the end.
 *
 * The reader's position is otherwise taken from whatever sits at the middle of
 * the viewport, and the last message usually never gets there: a short final
 * turn rests against the bottom edge with earlier content still filling the
 * middle. Reaching the end is its own answer -- the last turn is what is being
 * read -- and without this the final tick could never light up.
 */
export function isAtScrollEnd(
  scrollTop: number,
  clientHeight: number,
  scrollHeight: number,
  tolerance = 8
): boolean {
  return scrollHeight - scrollTop - clientHeight <= tolerance;
}
