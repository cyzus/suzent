/**
 * Which shell is hosting the frontend.
 *
 * The same bundle runs inside the Tauri desktop shell and in a plain browser
 * pointed at the backend. Desktop-only capabilities (window controls, native
 * dialogs, the background service, self-update) must be gated on `isDesktop()`
 * rather than assumed, and `@tauri-apps/*` calls must never run in web mode —
 * `invoke` throws synchronously when the Tauri internals are absent, so a
 * `.catch()` on the returned promise does not contain it.
 */

export function isDesktop(): boolean {
  return !!window.__TAURI__;
}

export function isWeb(): boolean {
  return !isDesktop();
}
