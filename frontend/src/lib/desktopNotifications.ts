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

export type ReplyOutcome = 'ready' | 'approval' | 'failed' | 'stopped';

interface WatchedReply {
  preview: string;
  failed: boolean;
  stopped: boolean;
  pendingApprovals: Set<string>;
}

// Chats where the user started a turn and is waiting for the reply.
const awaitingReply = new Map<string, WatchedReply>();

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
  awaitingReply.set(chatId, {
    preview: '',
    failed: false,
    stopped: false,
    pendingApprovals: new Set(),
  });
}

export function forgetReply(chatId: string): void {
  awaitingReply.delete(chatId);
}

/**
 * Note how a watched turn is going from a raw SSE chunk off the event bus.
 * A stream also ends when it pauses for approval, fails, or is stopped, and
 * each of those deserves a different message, or none.
 */
export function recordReplyChunk(chatId: string, rawData: string): void {
  const watched = awaitingReply.get(chatId);
  if (!watched) return;
  for (const line of rawData.split('\n')) {
    if (!line.startsWith('data:')) continue;
    let frame: {
      type?: string;
      code?: string;
      name?: string;
      delta?: string;
      value?: Record<string, unknown>;
    };
    try {
      frame = JSON.parse(line.slice(5));
    } catch {
      continue;
    }
    if (frame.type === 'TEXT_MESSAGE_START') {
      watched.preview = '';
    } else if (frame.type === 'TEXT_MESSAGE_CONTENT' && typeof frame.delta === 'string') {
      watched.preview = (watched.preview + frame.delta)
        .replace(/\s+/g, ' ')
        .trimStart()
        .slice(0, MAX_BODY_LENGTH + 1);
    } else if (frame.type === 'RUN_ERROR') {
      if (frame.code === 'stream_stopped') watched.stopped = true;
      else watched.failed = true;
    } else if (frame.type === 'error') {
      watched.failed = true;
    } else if (frame.type === 'CUSTOM') {
      const toolCallId = frame.value?.toolCallId;
      if (typeof toolCallId !== 'string') continue;
      if (frame.name === 'tool_approval_request') watched.pendingApprovals.add(toolCallId);
      else if (frame.name === 'tool_approval_result') watched.pendingApprovals.delete(toolCallId);
    }
  }
}

/** The watched turn's outcome, once: the caller owns announcing it. */
export function takeReplyOutcome(
  chatId: string
): { outcome: ReplyOutcome; preview: string } | null {
  const watched = awaitingReply.get(chatId);
  if (!watched) return null;
  awaitingReply.delete(chatId);
  const outcome: ReplyOutcome = watched.stopped
    ? 'stopped'
    : watched.failed
      ? 'failed'
      : watched.pendingApprovals.size > 0
        ? 'approval'
        : 'ready';
  return { outcome, preview: truncateNotificationBody(watched.preview) };
}
