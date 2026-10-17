import type React from 'react';

/**
 * True while a keystroke belongs to an input method (Chinese, Japanese, Korean
 * IMEs) rather than to the page: Enter confirming a candidate, Escape dismissing
 * the candidate list, arrows moving through it.
 *
 * `isComposing` alone is not enough on macOS. WebKit — Safari and the Tauri
 * webview — fires `compositionend` before the keydown of the Enter that commits
 * the text, so that keydown reports `isComposing: false` and would send or
 * submit half-typed input. It still carries keyCode 229, the code browsers give
 * every key the IME consumes.
 */
export function isImeComposing(event: KeyboardEvent | React.KeyboardEvent): boolean {
  const native = 'nativeEvent' in event ? event.nativeEvent : event;
  return native.isComposing || native.keyCode === 229;
}
