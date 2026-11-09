import { useEffect, useState } from 'react';

import { DESKTOP_BREAKPOINT_PX } from './layout';

/** One line of the composer's text, including its vertical padding. */
export const COMPOSER_EDITOR_MIN_HEIGHT_PX = 40;

/**
 * Narrow layouts keep this cap. A taller field fights the on-screen keyboard
 * and the stacked mobile chrome.
 */
export const MOBILE_COMPOSER_EDITOR_MAX_HEIGHT_PX = 120;

/** Desktop long text may use half the current window. Empty text stays one line. */
export const DESKTOP_COMPOSER_MAX_HEIGHT_RATIO = 0.5;

/**
 * Always-visible controls outside the editor: attach, send, model, and
 * permission. Attachments scroll inside their own cap and are not deducted,
 * so a normal window stays at exactly half.
 */
export const DESKTOP_COMPOSER_CHROME_PX = 112;

/**
 * A few lines of transcript that must remain when the window is tiny.
 * Half the window is only reduced once the viewport is shorter than
 * `2 * (chrome + this)`, which is below the desktop app's 560px minimum.
 */
export const DESKTOP_COMPOSER_MIN_TRANSCRIPT_PX = 96;

export function composerEditorMaxHeightPx(viewport: {
  viewportWidth: number;
  viewportHeight: number;
}): number {
  if (!Number.isFinite(viewport.viewportWidth) || viewport.viewportWidth < DESKTOP_BREAKPOINT_PX) {
    return MOBILE_COMPOSER_EDITOR_MAX_HEIGHT_PX;
  }
  if (!Number.isFinite(viewport.viewportHeight) || viewport.viewportHeight <= 0) {
    return COMPOSER_EDITOR_MIN_HEIGHT_PX;
  }
  const half = Math.floor(viewport.viewportHeight * DESKTOP_COMPOSER_MAX_HEIGHT_RATIO);
  const roomBesideChrome =
    viewport.viewportHeight - DESKTOP_COMPOSER_CHROME_PX - DESKTOP_COMPOSER_MIN_TRANSCRIPT_PX;
  return Math.max(COMPOSER_EDITOR_MIN_HEIGHT_PX, Math.min(half, Math.floor(roomBesideChrome)));
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
