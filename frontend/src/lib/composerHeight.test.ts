import { describe, expect, it } from 'vitest';

import {
  COMPOSER_EDITOR_MIN_HEIGHT_PX,
  DESKTOP_COMPOSER_CHROME_PX,
  DESKTOP_COMPOSER_MAX_HEIGHT_RATIO,
  DESKTOP_COMPOSER_MIN_TRANSCRIPT_PX,
  MOBILE_COMPOSER_EDITOR_MAX_HEIGHT_PX,
  composerEditorHeightPx,
  composerEditorMaxHeightPx,
  composerViewport,
} from './composerHeight';

const desktop = (viewportHeight: number) =>
  composerEditorMaxHeightPx({ viewportWidth: 1280, viewportHeight });

const half = (viewportHeight: number) =>
  Math.floor(viewportHeight * DESKTOP_COMPOSER_MAX_HEIGHT_RATIO);

describe('composer editor height', () => {
  it('keeps the historical 120px cap on narrow screens', () => {
    expect(MOBILE_COMPOSER_EDITOR_MAX_HEIGHT_PX).toBe(120);
    expect(composerEditorMaxHeightPx({ viewportWidth: 390, viewportHeight: 844 })).toBe(120);
    expect(composerEditorMaxHeightPx({ viewportWidth: 390, viewportHeight: 500 })).toBe(120);
    expect(composerEditorMaxHeightPx({ viewportWidth: 1023, viewportHeight: 900 })).toBe(120);
  });

  it('caps a desktop window at half its current height', () => {
    expect(DESKTOP_COMPOSER_MAX_HEIGHT_RATIO).toBe(0.5);
    for (const height of [560, 650, 760, 900, 1080, 1440]) {
      expect(desktop(height)).toBe(half(height));
    }
    expect(desktop(761)).toBe(380);
  });

  it('follows a resize instead of a fixed pixel cap', () => {
    expect(desktop(800)).toBe(400);
    expect(desktop(1000)).toBe(500);
    expect(desktop(1000)).toBeGreaterThan(desktop(800));
    expect(desktop(800) / 800).toBe(0.5);
  });

  it('only backs off half the window when the controls would not fit', () => {
    const safetyFloor = 2 * (DESKTOP_COMPOSER_CHROME_PX + DESKTOP_COMPOSER_MIN_TRANSCRIPT_PX);
    expect(safetyFloor).toBeLessThan(560);
    expect(desktop(400)).toBe(192);
    expect(desktop(240)).toBe(COMPOSER_EDITOR_MIN_HEIGHT_PX);
    expect(desktop(560)).toBe(half(560));
  });

  it('stays one line when empty and shrinks again after text is removed', () => {
    const cap = desktop(900);
    expect(cap).toBe(450);
    expect(composerEditorHeightPx(0, cap)).toBe(40);
    expect(composerEditorHeightPx(40, cap)).toBe(40);
    expect(composerEditorHeightPx(96, cap)).toBe(96);
    expect(composerEditorHeightPx(900, cap)).toBe(450);
    expect(composerEditorHeightPx(48, cap)).toBe(48);
  });

  it('assumes a normal desktop window outside the browser', () => {
    expect(composerViewport()).toEqual({ viewportWidth: 1440, viewportHeight: 900 });
    expect(composerEditorMaxHeightPx(composerViewport())).toBe(450);
  });

  it('still scrolls inside the mobile cap instead of growing', () => {
    const cap = composerEditorMaxHeightPx({ viewportWidth: 390, viewportHeight: 844 });
    expect(composerEditorHeightPx(800, cap)).toBe(120);
    expect(composerEditorHeightPx(48, cap)).toBe(48);
  });
});
