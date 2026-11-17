/**
 * Polling for data that is only ever shown inside the window.
 *
 * While the window is hidden (minimised, in the tray, a background tab) the
 * ticks are skipped, and the moment it is shown again `refresh` runs once so
 * nothing on screen is stale. Polls whose results reach the user while the
 * window is hidden -- desktop notifications, for one -- must not use this.
 */

export function isDocumentHidden(): boolean {
  return typeof document !== 'undefined' && document.visibilityState === 'hidden';
}

/** Run `refresh` every `intervalMs` while visible. Returns the stop function. */
export function pollWhileVisible(refresh: () => void, intervalMs: number): () => void {
  const tick = () => {
    if (!isDocumentHidden()) refresh();
  };
  const timer = setInterval(tick, intervalMs);
  const onVisibilityChange = () => {
    if (!isDocumentHidden()) refresh();
  };
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibilityChange);
  }
  return () => {
    clearInterval(timer);
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', onVisibilityChange);
    }
  };
}
