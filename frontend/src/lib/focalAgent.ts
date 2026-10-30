import { getApiBase } from './api';
import type { ChatState } from './chatStates';

/** The singleton Regent chat that orchestrates work across every project. */
export const FOCAL_CHAT_ID = 'focal-suzent';
/** Board scope spanning every non-archived project. */
export const ALL_PROJECTS_KANBAN_ID = '__all__';

const FOCAL_REQUEST_HEADER = new RegExp(
  `^\\[Agent message from [^\\n]*\\(${FOCAL_CHAT_ID}\\)\\]\\s*`
);
const INBOX_MARKER = /<!--\s*suzent-agent-inbox:[\s\S]*?-->\s*/gi;

/**
 * The words Regent sent a session, from the row that started the turn, or null
 * for any other trigger. Regent relays the user's own requests, so the session
 * shows them as the user's message rather than as a background trigger.
 */
export function focalRequestText(content: string | undefined): string | null {
  const raw = (content ?? '').trim();
  if (!FOCAL_REQUEST_HEADER.test(raw)) return null;
  const text = raw.replace(FOCAL_REQUEST_HEADER, '').replace(INBOX_MARKER, '').trim();
  return text || null;
}

export interface FocalAgentStatus {
  chatId: string;
  title: string;
  /** Chats waiting on the user. */
  waiting: number;
  running: boolean;
  /** Messages Regent added since the user last opened it, e.g. from a check-in. */
  unread?: number;
  lastMessage?: string | null;
  /** When Regent last said something, ISO 8601. */
  lastMessageAt?: string | null;
  /** Project chats by where they stand for the user. */
  states?: Record<ChatState, number>;
  /** Chats waiting on the user, by project id and by chat id. */
  waitingByProject?: Record<string, number>;
  waitingByChat?: Record<string, number>;
}

export async function fetchFocalAgentStatus(): Promise<FocalAgentStatus> {
  const response = await fetch(`${getApiBase()}/focal`, { signal: AbortSignal.timeout(15000) });
  if (!response.ok) throw new Error('Focal Agent status fetch failed');
  return response.json();
}

export interface FocalTool {
  id: string;
  name: string;
  description: string;
  runtimeName: string;
}

export interface FocalWakeup {
  id: number;
  name: string;
  kind: 'reminder' | 'check';
  schedule: string;
  scheduleKind: 'once' | 'interval' | 'cron';
  nextRunAt: string | null;
  /** Why the last run failed, until a run succeeds. */
  lastError?: string | null;
}

export interface FocalPanel {
  tools: FocalTool[];
  wakeups: FocalWakeup[];
}

export async function fetchFocalPanel(): Promise<FocalPanel> {
  const response = await fetch(`${getApiBase()}/focal/panel`, {
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new Error('Focal Agent panel fetch failed');
  return response.json();
}

export async function cancelFocalWakeup(id: number): Promise<void> {
  const response = await fetch(`${getApiBase()}/focal/wakeups/${id}`, { method: 'DELETE' });
  if (!response.ok) throw new Error('Cancelling the wake-up failed');
}

// Renamed when the board started closed: the old key holds "true" for nearly
// everyone, since it also recorded the board opening on its own.
const BOARD_OPEN_KEY = 'suzent.focal.boardOpen.v2';
const PROJECT_FILTER_KEY = 'suzent.focal.projectFilter';

function readSetting(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeSetting(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Remembering is a convenience; without storage the board uses its defaults.
  }
}

/**
 * Whether the board should open when arriving on the Focal chat. Closed unless
 * opened there: the sidebar already lists what waits on the user.
 */
export function readFocalBoardOpen(): boolean {
  return readSetting(BOARD_OPEN_KEY) === 'true';
}

export function writeFocalBoardOpen(open: boolean): void {
  writeSetting(BOARD_OPEN_KEY, String(open));
}

export function readFocalProjectFilter(): string | null {
  return readSetting(PROJECT_FILTER_KEY);
}

export function writeFocalProjectFilter(projectId: string): void {
  writeSetting(PROJECT_FILTER_KEY, projectId);
}
