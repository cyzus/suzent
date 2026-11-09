import { useEffect, useState } from 'react';

import { DESKTOP_BREAKPOINT_PX } from './layout';

/** One line of the composer's text, including its vertical padding. */
export const COMPOSER_EDITOR_MIN_HEIGHT_PX = 40;

/**
 * Narrow layouts keep this cap. A taller field fights the on-screen keyboard
 * and the stacked mobile chrome.
 */
export const MOBILE_COMPOSER_EDITOR_MAX_HEIGHT_PX = 120;

/**
 * About twelve lines of `text-lg` / `leading-7`. Tall enough to revise a long
 * prompt, and exactly what the default 760px desktop window can spare once
 * the header, a readable transcript, and the composer controls are reserved.
 */
export const DESKTOP_COMPOSER_EDITOR_MAX_HEIGHT_PX = 360;

/**
 * Space that stays outside the editor on a desktop window: the 48px header,
 * roughly 240px of transcript, and the attach / send / model / permission
 * controls that are not part of the editor's own max-height.
 */
export const DESKTOP_COMPOSER_RESERVED_HEIGHT_PX = 400;

export function composerEditorMaxHeightPx(viewport: {
  viewportWidth: number;
  viewportHeight: number;
}): number {
  if (!Number.isFinite(viewport.viewportWidth) || viewport.viewportWidth < DESKTOP_BREAKPOINT_PX) {
    return MOBILE_COMPOSER_EDITOR_MAX_HEIGHT_PX;
  }
  const fitted = viewport.viewportHeight - DESKTOP_COMPOSER_RESERVED_HEIGHT_PX;
  return Math.min(
    DESKTOP_COMPOSER_EDITOR_MAX_HEIGHT_PX,
    Math.max(COMPOSER_EDITOR_MIN_HEIGHT_PX, Math.floor(fitted))
  );
}

/** Content height, never below one line and never past the current cap. */
export function composerEditorHeightPx(contentHeight: number, maxHeight: number): number {
  const content = Number.isFinite(contentHeight) ? contentHeight : COMPOSER_EDITOR_MIN_HEIGHT_PX;
  return Math.min(maxHeight, Math.max(COMPOSER_EDITOR_MIN_HEIGHT_PX, content));
}

export function composerViewport(): { viewportWidth: number; viewportHeight: number } {
  if (typeof window === 'undefined') {
    return { viewportWidth: 1440, viewportHeight: 900 };
  }
  return { viewportWidth: window.innerWidth, viewportHeight: window.innerHeight };
}

export function useComposerEditorMaxHeight(): number {
  const [maxHeight, setMaxHeight] = useState(() => composerEditorMaxHeightPx(composerViewport()));

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const update = () => setMaxHeight(composerEditorMaxHeightPx(composerViewport()));
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  return maxHeight;
}
