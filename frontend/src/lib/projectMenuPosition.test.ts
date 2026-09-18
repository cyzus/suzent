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
    expect(geometry.top).toBe(810 - 4 - geometry.maxHeight);
    expect(geometry.top).toBeGreaterThanOrEqual(MARGIN);
  });

  it('keeps a downward menu inside the bottom edge', () => {
    const geometry = resolveProjectMenuPosition(trigger(200), { width: 1280, height: 420 });

    expect(geometry.top + geometry.maxHeight).toBeLessThanOrEqual(420 - MARGIN);
  });

  it('shrinks rather than overflowing when neither side has room', () => {
    // A short window: the menu must stay on screen even if it has to scroll.
    const viewport = { width: 1280, height: 300 };
    const geometry = resolveProjectMenuPosition(trigger(130), viewport);

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
