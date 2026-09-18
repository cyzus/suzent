import { describe, expect, it } from 'vitest';
import { resolveProjectMenuPosition } from './projectMenuPosition';

const VIEWPORT = { width: 1280, height: 900 };
const MARGIN = 16;

/** A centred trigger, the way the new-chat screen lays it out. */
function trigger(top: number, height = 30, width = 220) {
  return { top, bottom: top + height, left: VIEWPORT.width / 2 - width / 2, width };
}

describe('resolveProjectMenuPosition', () => {
  it('drops below the trigger when there is room', () => {
    const geometry = resolveProjectMenuPosition(trigger(200), VIEWPORT);

    expect(geometry.dropUp).toBe(false);
    if (geometry.dropUp) throw new Error('expected a downward menu');
    expect(geometry.top).toBe(234); // bottom (230) + gap (4)
    expect(geometry.maxHeight).toBe(296);
  });

  it('centres the menu on the trigger', () => {
    const geometry = resolveProjectMenuPosition(trigger(200), VIEWPORT);

    const menuCentre = geometry.left + geometry.width / 2;
    expect(menuCentre).toBe(VIEWPORT.width / 2);
  });

  it('flips above the trigger when below is tighter', () => {
    // 60px of room below, plenty above.
    const geometry = resolveProjectMenuPosition(trigger(810), VIEWPORT);

    expect(geometry.dropUp).toBe(true);
    if (!geometry.dropUp) throw new Error('expected a drop-up menu');
    // Anchored to the trigger's top edge, minus the gap.
    expect(geometry.bottom).toBe(VIEWPORT.height - (810 - 4));
  });

  it('anchors a drop-up menu by its bottom edge, not a height-derived top', () => {
    // The menu only sets `max-height`, so a short project list renders shorter
    // than `maxHeight`. Anchoring by `bottom` keeps it against the trigger
    // whatever it renders at; a `top` derived from the cap would not.
    const geometry = resolveProjectMenuPosition(trigger(810), VIEWPORT);

    if (!geometry.dropUp) throw new Error('expected a drop-up menu');
    expect(geometry).not.toHaveProperty('top');

    // Whatever height it renders at, its bottom sits just above the trigger.
    for (const renderedHeight of [80, 160, geometry.maxHeight]) {
      const topEdge = VIEWPORT.height - geometry.bottom - renderedHeight;
      expect(topEdge + renderedHeight).toBe(810 - 4);
      expect(topEdge).toBeGreaterThanOrEqual(0);
    }
  });

  it('keeps a drop-up menu inside the top edge when room is scarce', () => {
    // Very little space above, and even less below, so it flips into a gap
    // smaller than the minimum height.
    const geometry = resolveProjectMenuPosition(trigger(90), { width: 1280, height: 190 });

    if (!geometry.dropUp) throw new Error('expected a drop-up menu');
    const topEdge = 190 - geometry.bottom - geometry.maxHeight;
    expect(topEdge).toBeGreaterThanOrEqual(MARGIN);
  });

  it('keeps a downward menu inside the bottom edge', () => {
    // High in a short window: below is still the roomier side, but not roomy
    // enough for the full menu.
    const viewport = { width: 1280, height: 300 };
    const geometry = resolveProjectMenuPosition(trigger(30), viewport);

    if (geometry.dropUp) throw new Error('expected a downward menu');
    expect(geometry.maxHeight).toBeLessThan(296);
    expect(geometry.top + geometry.maxHeight).toBeLessThanOrEqual(viewport.height - MARGIN);
  });

  it('shrinks rather than overflowing when neither side has room', () => {
    // A short window: the menu must stay on screen even if it has to scroll.
    const viewport = { width: 1280, height: 300 };
    const geometry = resolveProjectMenuPosition(trigger(130), viewport);

    if (geometry.dropUp) throw new Error('expected a downward menu');
    expect(geometry.top).toBeGreaterThanOrEqual(MARGIN);
    expect(geometry.maxHeight).toBeLessThan(296);
    expect(geometry.top + geometry.maxHeight).toBeLessThanOrEqual(viewport.height - MARGIN);
  });

  it('clamps a trigger near the right edge back into the viewport', () => {
    const geometry = resolveProjectMenuPosition(
      { top: 200, bottom: 230, left: 1260, width: 220 },
      VIEWPORT
    );

    expect(geometry.left + geometry.width).toBeLessThanOrEqual(VIEWPORT.width - MARGIN);
  });

  it('clamps a trigger near the left edge back into the viewport', () => {
    const geometry = resolveProjectMenuPosition(
      { top: 200, bottom: 230, left: -80, width: 220 },
      VIEWPORT
    );

    expect(geometry.left).toBe(MARGIN);
  });

  it('narrows the menu on a viewport too small to hold it', () => {
    const viewport = { width: 200, height: 900 };
    const geometry = resolveProjectMenuPosition(trigger(200), viewport);

    expect(geometry.width).toBe(viewport.width - MARGIN * 2);
    expect(geometry.left).toBe(MARGIN);
  });
});
