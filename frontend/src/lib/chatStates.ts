import { getApiBase } from './api';

export type ChatState = 'waiting' | 'running' | 'idle' | 'resolved';
/** What a waiting chat waits on: an open question, a tool approval, a stuck task, or its last reply. */
export type WaitingKind = 'question' | 'approval' | 'task' | 'reply';

export const CHAT_STATES: readonly ChatState[] = ['waiting', 'running', 'idle', 'resolved'];

export interface ChatStateRow {
  chatId: string;
  title: string;
  projectId: string;
  projectName: string | null;
  state: ChatState;
  waitingKind: WaitingKind | null;
  waitingReason: string | null;
  /** One line on where the work stands, or the chat's last message. */
  summary: string | null;
  lastActiveAt: string | null;
  resolvedAt: string | null;
  openTasks: number;
  doneTasks: number;
}

export interface ChatStates {
  chats: ChatStateRow[];
  counts: Record<ChatState, number>;
}

export async function fetchChatStates(): Promise<ChatStates> {
  const response = await fetch(`${getApiBase()}/focal/chats`, {
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new Error('Chat states fetch failed');
  return response.json();
}

/** One chat's row, however long it has been quiet, or null when the board doesn't track it. */
export async function fetchChatState(chatId: string): Promise<ChatStateRow | null> {
  const response = await fetch(
    `${getApiBase()}/focal/chats?chat_id=${encodeURIComponent(chatId)}`,
    { signal: AbortSignal.timeout(15000) }
  );
  if (!response.ok) throw new Error('Chat state fetch failed');
  const body: ChatStates = await response.json();
  return body.chats[0] ?? null;
}

/**
 * Whether resolving would change the row. A question or approval held open
 * outranks resolving until it is answered in the chat.
 */
export function canResolve(row: ChatStateRow): boolean {
  return !(row.waitingKind === 'question' || row.waitingKind === 'approval');
}

export async function setChatResolved(chatId: string, resolved: boolean): Promise<void> {
  const response = await fetch(`${getApiBase()}/chats/${encodeURIComponent(chatId)}/resolved`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resolved }),
  });
  if (!response.ok) throw new Error(`Failed to update chat: ${response.status}`);
}

/** Projects that have chats on the board, by name. */
export function chatProjects(rows: ChatStateRow[]): { id: string; label: string }[] {
  const projects = new Map<string, string>();
  for (const row of rows) projects.set(row.projectId, row.projectName ?? row.projectId);
  return [...projects]
    .map(([id, label]) => ({ id, label }))
    .sort((a, b) => a.label.localeCompare(b.label));
}
