/**
 * Native notifications for work that finishes while the user is looking
 * elsewhere. Desktop only: in web mode every call is a no-op, and when Suzent
 * has focus the in-app status bar already tells the user.
 */
import { isDesktop } from './runtime';

const MAX_BODY_LENGTH = 200;

// Asked once per session. The OS remembers the answer, and re-asking after a
// denial would only show the prompt again on platforms that allow it.
let permission: Promise<boolean> | null = null;

// Chats where the user started a turn and is waiting for the reply.
const awaitingReply = new Set<string>();

function ensurePermission(): Promise<boolean> {
  if (!permission) {
    permission = (async () => {
      const { isPermissionGranted, requestPermission } =
        await import('@tauri-apps/plugin-notification');
      if (await isPermissionGranted()) return true;
      return (await requestPermission()) === 'granted';
    })().catch(() => false);
  }
  return permission;
}

export function isUserAway(): boolean {
  return document.visibilityState === 'hidden' || !document.hasFocus();
}

export function truncateNotificationBody(body: string): string {
  const flat = body.replace(/\s+/g, ' ').trim();
  return flat.length > MAX_BODY_LENGTH ? `${flat.slice(0, MAX_BODY_LENGTH - 1)}…` : flat;
}

export async function notifyIfAway(title: string, body: string): Promise<void> {
  if (!isDesktop() || !isUserAway()) return;
  try {
    if (!(await ensurePermission())) return;
    const { sendNotification } = await import('@tauri-apps/plugin-notification');
    sendNotification({ title, body: truncateNotificationBody(body) });
  } catch (err) {
    console.warn('[notifications] failed to show notification:', err);
  }
}

export function watchForReply(chatId: string): void {
  awaitingReply.add(chatId);
}

/** True once per watched turn: the caller owns announcing that reply. */
export function takeAwaitedReply(chatId: string): boolean {
  return awaitingReply.delete(chatId);
}
