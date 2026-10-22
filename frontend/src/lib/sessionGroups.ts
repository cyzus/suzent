import type { Task, TaskStatus } from '../types/api';
import type { KanbanData } from '../hooks/useGoalTasks';

export type SessionGroupKey = 'attention' | 'active' | 'stalled' | 'waiting' | 'completed';

/** Display order: what needs the user first, finished work last. */
export const SESSION_GROUP_KEYS: readonly SessionGroupKey[] = [
  'attention',
  'active',
  'stalled',
  'waiting',
  'completed',
];

export interface SessionCard {
  key: string;
  chatId: string | null;
  title: string | null;
  projectLabel: string | null;
  running: boolean;
  tasks: Task[];
  blocker: Task | undefined;
  updatedAt: string;
}

export const needsUser = (task: Task): boolean =>
  task.status === 'blocked' && (task.waitingKind === 'user' || task.waitingKind === 'error');

const isOpen = (task: Task): boolean => task.status !== 'completed' && task.status !== 'cancelled';

/** Tasks that would move if the session were working: not done and not waiting on something. */
export const isActionable = (task: Task): boolean =>
  task.status === 'pending' || task.status === 'in_progress';

/**
 * Where a session belongs on the board. A session that is not running but
 * still owns actionable tasks is stalled: nothing is driving that work, which
 * is different from a session that is legitimately waiting on a dependency.
 */
export function sessionGroupKey(session: SessionCard): SessionGroupKey {
  if (session.blocker) return 'attention';
  if (session.running) return 'active';
  if (session.chatId && session.tasks.some(isActionable)) return 'stalled';
  if (session.tasks.some(isOpen)) return 'waiting';
  return 'completed';
}

/** Open tasks first, in their original order, then finished ones. */
export function splitSessionTasks(session: SessionCard): { open: Task[]; done: Task[] } {
  return {
    open: session.tasks.filter(isOpen),
    done: session.tasks.filter((task) => !isOpen(task)),
  };
}

/** Collect tasks into the chat sessions that own them, most recently updated first. */
export function buildSessions(tasks: Task[], chatTitles: Record<string, string>): SessionCard[] {
  const sessions = new Map<string, SessionCard>();
  for (const task of tasks) {
    if (task.status === 'cancelled') continue;
    const chatId = task.chatId?.trim() || null;
    const key = chatId ?? `unassigned:${task.projectId}`;
    const session = sessions.get(key) ?? {
      key,
      chatId,
      title: task.chatTitle ?? (chatId ? chatTitles[chatId] : null) ?? null,
      projectLabel: task.projectName ?? task.projectSlug ?? null,
      running: false,
      tasks: [],
      blocker: undefined,
      updatedAt: '',
    };
    session.tasks.push(task);
    session.running ||= Boolean(task.chatRunning);
    if (!session.blocker && needsUser(task)) session.blocker = task;
    if ((task.updatedAt ?? '') > session.updatedAt) session.updatedAt = task.updatedAt ?? '';
    sessions.set(key, session);
  }
  return [...sessions.values()].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

/** Board filter value meaning "every project". */
export const ALL_PROJECTS = 'all';

export interface ProjectOption {
  id: string;
  label: string;
}

/** Projects that have live tasks on an all-projects board, by name. */
export function projectOptions(kanban: KanbanData | null): ProjectOption[] {
  const options = new Map<string, string>();
  for (const task of kanban?.tasks ?? []) {
    if (task.status === 'cancelled' || options.has(task.projectId)) continue;
    options.set(task.projectId, task.projectName ?? task.projectSlug ?? task.projectId);
  }
  return [...options]
    .map(([id, label]) => ({ id, label }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

export function filterKanbanByProject(
  kanban: KanbanData | null,
  projectId: string
): KanbanData | null {
  if (!kanban || projectId === ALL_PROJECTS) return kanban;
  return {
    goals: kanban.goals.filter((goal) => goal.projectId === projectId),
    tasks: kanban.tasks.filter((task) => task.projectId === projectId),
  };
}

/** What the board's row menus can do to a session's tasks, or to one task. */
export type BoardAction = 'resume' | 'complete' | 'reopen' | 'cancel';

export const BOARD_ACTIONS: readonly BoardAction[] = ['resume', 'complete', 'reopen', 'cancel'];

export interface StatusChange {
  task: Task;
  status: TaskStatus;
}

/**
 * The status each task would move to under a manual action. Resuming only
 * lifts the wait, so the work counts as stalled until a session picks it up.
 */
export function boardActionChanges(tasks: Task[], action: BoardAction): StatusChange[] {
  const target: Record<BoardAction, [(task: Task) => boolean, TaskStatus]> = {
    resume: [(task) => task.status === 'blocked', 'pending'],
    complete: [isOpen, 'completed'],
    reopen: [(task) => task.status === 'completed', 'pending'],
    cancel: [isOpen, 'cancelled'],
  };
  const [applies, status] = target[action];
  return tasks.filter(applies).map((task) => ({ task, status }));
}
