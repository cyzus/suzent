/**
 * Which shell is hosting the frontend.
 *
 * The same bundle runs inside the desktop shell (Electron, or Tauri while it
 * still ships) and in a plain browser pointed at the backend. Desktop-only
 * capabilities (window controls, native dialogs, the background service,
 * self-update) must be gated on `isDesktop()` rather than assumed, and shell
 * calls must go through `lib/desktop.ts`, never run in web mode.
 */

export { isDesktop } from './desktop';
import { isDesktop } from './desktop';

export function isWeb(): boolean {
  return !isDesktop();
}
