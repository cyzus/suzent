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

/**
 * Where in the viewport to ask "which message is here?".
 *
 * Taking the middle always is what left the first and last ticks unreachable:
 * the first message sits against the top edge and the last against the bottom,
 * so neither ever occupies the centre, however far you scroll. The probe slides
 * with the scroll instead -- the top edge at the top, the bottom edge at the
 * bottom, the middle in between -- so the ends are ordinary positions rather
 * than special cases.
 */
export function probeOffsetPx(
  scrollTop: number,
  clientHeight: number,
  scrollHeight: number
): number {
  const maxScroll = scrollHeight - clientHeight;
  if (maxScroll <= 0) return clientHeight / 2;
  const progress = Math.max(0, Math.min(1, scrollTop / maxScroll));
  return clientHeight * progress;
}

export interface MarkerAnchor {
  order: number;
  /** Viewport-relative top of the first row belonging to that marker. */
  top: number;
}

/**
 * The reader's place on the rail, in fractional tick order.
 *
 * Interpolating within a *row* was wrong: a tick stands for a whole turn, and
 * a turn is several rows -- the prompt, the reply, whatever the agent did in
 * between. Crossing from one row of a turn into the next reset the fraction
 * from nearly one back to nearly zero while the tick order stayed put, so the
 * highlight ran ahead to the next tick and immediately snapped back. The
 * fraction has to be measured across the turn, which is what the gap between
 * consecutive anchors is.
 *
 * Anchors must be in document order. The order delta is carried through, so a
 * turn whose rows are not mounted is stepped over rather than mistaken for one.
 */
export function positionFromAnchors(anchors: MarkerAnchor[], probeY: number): number | null {
  if (anchors.length === 0) return null;
  if (probeY <= anchors[0].top) return anchors[0].order;

  for (let i = 0; i < anchors.length - 1; i += 1) {
    const start = anchors[i];
    const next = anchors[i + 1];
    if (probeY >= next.top) continue;
    const span = next.top - start.top;
    const fraction = span > 0 ? (probeY - start.top) / span : 0;
    return start.order + fraction * (next.order - start.order);
  }

  return anchors[anchors.length - 1].order;
}
