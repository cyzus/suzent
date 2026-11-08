import { afterEach, describe, expect, it } from 'vitest';
import {
  clearTouchPoint,
  menuFrame,
  noteTouchPoint,
  placeMenu,
  pointerMenuPoint,
} from './menuPlacement';

afterEach(() => clearTouchPoint());

describe('placeMenu', () => {
  const frame = { left: 8, top: 8, right: 392, bottom: 792 };

  it('leaves a menu that fits at the press', () => {
    expect(placeMenu(40, 80, 180, 120, frame)).toMatchObject({ left: 40, top: 80 });
  });

  it('pulls a bottom-right press back inside the frame', () => {
    expect(placeMenu(370, 760, 180, 120, frame)).toEqual({
      left: 212,
      top: 672,
      maxWidth: 384,
      maxHeight: 784,
    });
  });

  it('pins a tall menu to the top of a short landscape frame and reports the scroll size', () => {
    const landscape = { left: 8, top: 8, right: 792, bottom: 352 };
    const placed = placeMenu(700, 300, 220, 500, landscape);
    expect(placed.left).toBe(572);
    expect(placed.top).toBe(8);
    expect(placed.maxHeight).toBe(344);
  });
});

describe('menuFrame', () => {
  it('keeps the desktop inset when the visual viewport matches the window', () => {
    expect(
      menuFrame(
        8,
        null,
        { offsetLeft: 0, offsetTop: 0, width: 1200, height: 800 },
        { width: 1200, height: 800 }
      )
    ).toEqual({ left: 8, top: 8, right: 1192, bottom: 792 });
  });

  it('uses the visible viewport when a mobile keyboard shrinks it', () => {
    expect(
      menuFrame(
        8,
        null,
        { offsetLeft: 0, offsetTop: 0, width: 400, height: 320 },
        { width: 400, height: 800 }
      )
    ).toEqual({ left: 8, top: 8, right: 392, bottom: 312 });
  });

  it('stays inside a sidebar boundary', () => {
    expect(
      menuFrame(
        8,
        { left: 0, top: 0, right: 280, bottom: 800 },
        { offsetLeft: 0, offsetTop: 0, width: 1200, height: 800 },
        { width: 1200, height: 800 }
      )
    ).toEqual({ left: 8, top: 8, right: 272, bottom: 792 });
  });
});

describe('pointerMenuPoint', () => {
  it('uses a real pointer and ignores an older touch', () => {
    noteTouchPoint(10, 20, 1_000);
    expect(pointerMenuPoint({ clientX: 400, clientY: 500 }, { x: 1, y: 1 }, 1_100)).toEqual({
      x: 400,
      y: 500,
    });
  });

  it('uses the finger when Android reports the context menu at 0,0', () => {
    noteTouchPoint(312, 640, 1_000);
    expect(pointerMenuPoint({ clientX: 0, clientY: 0 }, { x: 12, y: 12 }, 1_400)).toEqual({
      x: 312,
      y: 640,
    });
  });

  it('keeps the focused element when a keyboard menu has no recent touch', () => {
    noteTouchPoint(312, 640, 1_000);
    expect(pointerMenuPoint({ clientX: 0, clientY: 0 }, { x: 48, y: 90 }, 3_000)).toEqual({
      x: 48,
      y: 90,
    });
  });
});
