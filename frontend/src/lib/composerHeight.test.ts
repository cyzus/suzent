import { describe, expect, it } from 'vitest';

import {
  COMPOSER_EDITOR_MIN_HEIGHT_PX,
  DESKTOP_COMPOSER_EDITOR_MAX_HEIGHT_PX,
  DESKTOP_COMPOSER_RESERVED_HEIGHT_PX,
  MOBILE_COMPOSER_EDITOR_MAX_HEIGHT_PX,
  composerEditorHeightPx,
  composerEditorMaxHeightPx,
  composerViewport,
} from './composerHeight';

const desktop = (viewportHeight: number) =>
  composerEditorMaxHeightPx({ viewportWidth: 1280, viewportHeight });

describe('composer editor height', () => {
  it('keeps the historical 120px cap on narrow screens', () => {
    expect(MOBILE_COMPOSER_EDITOR_MAX_HEIGHT_PX).toBe(120);
    expect(composerEditorMaxHeightPx({ viewportWidth: 390, viewportHeight: 844 })).toBe(120);
    expect(composerEditorMaxHeightPx({ viewportWidth: 390, viewportHeight: 500 })).toBe(120);
    expect(composerEditorMaxHeightPx({ viewportWidth: 1023, viewportHeight: 900 })).toBe(120);
  });

  it('raises the desktop cap from 120px to 360px on a normal window', () => {
    expect(DESKTOP_COMPOSER_EDITOR_MAX_HEIGHT_PX).toBe(360);
    expect(desktop(760)).toBe(360);
    expect(desktop(900)).toBe(360);
    expect(desktop(1440)).toBe(360);
  });

  it('shrinks the desktop cap so a short window keeps chat and controls', () => {
    expect(DESKTOP_COMPOSER_RESERVED_HEIGHT_PX).toBe(400);
    expect(desktop(560)).toBe(160);
    expect(desktop(650)).toBe(250);
    expect(desktop(430)).toBe(COMPOSER_EDITOR_MIN_HEIGHT_PX);
    expect(desktop(320)).toBe(COMPOSER_EDITOR_MIN_HEIGHT_PX);
  });

  it('stays one line when empty and shrinks again after text is removed', () => {
    const cap = desktop(900);
    expect(composerEditorHeightPx(0, cap)).toBe(40);
    expect(composerEditorHeightPx(40, cap)).toBe(40);
    expect(composerEditorHeightPx(96, cap)).toBe(96);
    expect(composerEditorHeightPx(900, cap)).toBe(360);
    expect(composerEditorHeightPx(48, cap)).toBe(48);
  });

  it('assumes a normal desktop window outside the browser', () => {
    expect(composerViewport()).toEqual({ viewportWidth: 1440, viewportHeight: 900 });
    expect(composerEditorMaxHeightPx(composerViewport())).toBe(360);
  });

  it('still scrolls inside the mobile cap instead of growing', () => {
    const cap = composerEditorMaxHeightPx({ viewportWidth: 390, viewportHeight: 844 });
    expect(composerEditorHeightPx(800, cap)).toBe(120);
    expect(composerEditorHeightPx(48, cap)).toBe(48);
  });
});
