/**
 * Place a menu at a point, then keep its measured size inside the visible frame.
 * A panel larger than the frame stays at the safe origin and reports that frame
 * as its max size so the menu can scroll instead of leaving the screen.
 */
export interface MenuFrame {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface MenuPlacement {
  left: number;
  top: number;
  maxWidth: number;
  maxHeight: number;
}

export function placeMenu(
  anchorX: number,
  anchorY: number,
  menuWidth: number,
  menuHeight: number,
  frame: MenuFrame
): MenuPlacement {
  const availableWidth = Math.max(0, frame.right - frame.left);
  const availableHeight = Math.max(0, frame.bottom - frame.top);
  const width = Math.min(Math.max(0, menuWidth), availableWidth);
  const height = Math.min(Math.max(0, menuHeight), availableHeight);
  const maxLeft = frame.left + (availableWidth - width);
  const maxTop = frame.top + (availableHeight - height);
  return {
    left: Math.min(Math.max(anchorX, frame.left), maxLeft),
    top: Math.min(Math.max(anchorY, frame.top), maxTop),
    maxWidth: availableWidth,
    maxHeight: availableHeight,
  };
}

/** Window frame the menu must stay inside, including an open mobile keyboard. */
export function menuFrame(
  margin: number,
  boundary?: { left: number; top: number; right: number; bottom: number } | null,
  viewport: {
    offsetLeft: number;
    offsetTop: number;
    width: number;
    height: number;
  } | null = typeof window === 'undefined' ? null : window.visualViewport,
  windowSize: { width: number; height: number } = {
    width: typeof window === 'undefined' ? 0 : window.innerWidth,
    height: typeof window === 'undefined' ? 0 : window.innerHeight,
  }
): MenuFrame {
  const originX = viewport?.offsetLeft ?? 0;
  const originY = viewport?.offsetTop ?? 0;
  const width = viewport?.width ?? windowSize.width;
  const height = viewport?.height ?? windowSize.height;
  const view: MenuFrame = {
    left: Math.max(margin, originX + margin),
    top: Math.max(margin, originY + margin),
    right: Math.min(windowSize.width, originX + width) - margin,
    bottom: Math.min(windowSize.height, originY + height) - margin,
  };
  if (!boundary) return view;
  return {
    left: Math.max(view.left, boundary.left),
    top: Math.max(view.top, boundary.top),
    right: Math.min(view.right, boundary.right - margin),
    bottom: Math.min(view.bottom, boundary.bottom - margin),
  };
}

interface TouchPoint {
  x: number;
  y: number;
  at: number;
}

let lastTouch: TouchPoint | null = null;
const TOUCH_POINT_MS = 800;

/** Android's contextmenu event often reports 0,0. The preceding touch has the finger. */
export function noteTouchPoint(x: number, y: number, at = Date.now()): void {
  lastTouch = { x, y, at };
}

export function clearTouchPoint(): void {
  lastTouch = null;
}

export function installTouchPointMemory(target: Window = window): void {
  const holder = target as Window & { __suzentTouchPoint?: boolean };
  if (holder.__suzentTouchPoint) return;
  holder.__suzentTouchPoint = true;
  const remember = (event: TouchEvent): void => {
    const touch = event.changedTouches.item(0);
    if (!touch) return;
    noteTouchPoint(touch.clientX, touch.clientY);
  };
  target.addEventListener('touchstart', remember, { capture: true, passive: true });
  target.addEventListener('touchmove', remember, { capture: true, passive: true });
  target.addEventListener('touchend', remember, { capture: true, passive: true });
}

if (typeof window !== 'undefined') installTouchPointMemory();

/** A real pointer, or the finger behind an Android context menu reported at 0,0. */
export function freshPointerPoint(
  event: { clientX: number; clientY: number },
  now = Date.now()
): { x: number; y: number } | null {
  if (event.clientX !== 0 || event.clientY !== 0) return { x: event.clientX, y: event.clientY };
  if (lastTouch && now - lastTouch.at <= TOUCH_POINT_MS) return { x: lastTouch.x, y: lastTouch.y };
  return null;
}

export function pointerMenuPoint(
  event: { clientX: number; clientY: number },
  fallback: { x: number; y: number },
  now = Date.now()
): { x: number; y: number } {
  return freshPointerPoint(event, now) ?? fallback;
}
