import React, { useState } from 'react';
import type { Task } from '../../types/api';
import type { KanbanData } from '../../hooks/useGoalTasks';
import { useI18n } from '../../i18n';
import { TaskProgressCard } from './TaskProgressCard';
import {
  SESSION_GROUP_KEYS,
  buildSessions,
  isActionable,
  sessionGroupKey,
  splitSessionTasks,
  type SessionCard,
  type SessionGroupKey,
} from '../../lib/sessionGroups';

export type KanbanGroupBy = 'status' | 'session';

interface ProjectKanbanViewProps {
  projectName?: string | null;
  projectId?: string | null;
  kanban: KanbanData | null;
  chatTitles?: Record<string, string>;
  headerControls?: React.ReactNode;
  summary?: React.ReactNode;
  scope?: 'chat' | 'project';
  /** Project scope only: group tasks by status, or by the chat session that owns them. */
  groupBy?: KanbanGroupBy;
  selectedTaskId?: number | null;
  pendingTaskId?: number | null;
  onOpenTask: (task: Task) => void;

  onOpenChat?: (chatId: string) => void;
  loading?: boolean;
  error?: boolean;
  onRetry?: () => void;
}

export const ProjectKanbanView: React.FC<ProjectKanbanViewProps> = ({
  projectName,
  kanban,
  chatTitles = {},
  headerControls,
  summary,
  scope = 'project',
  groupBy = 'status',
  selectedTaskId,
  pendingTaskId,
  onOpenTask,
  onOpenChat,
  loading = false,
  error,
  onRetry,
}) => {
  const { t } = useI18n();
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({
    completed: true,
    'session-completed': true,
  });
  // Session cards start folded to their header and reason; tasks are one click away.
  const [expandedSessions, setExpandedSessions] = useState<Record<string, boolean>>({});
  const tasks = kanban?.tasks ?? [];
  const goalsWithoutTasks = (kanban?.goals ?? []).filter(
    (goal) => goal.status !== 'cancelled' && !tasks.some((task) => task.chatId === goal.chatId)
  );
  const groups = [
    {
      key: 'attention',
      tasks: tasks.filter(
        (task) =>
          task.status === 'blocked' && (task.waitingKind === 'user' || task.waitingKind === 'error')
      ),
    },
    { key: 'active', tasks: tasks.filter((task) => task.status === 'in_progress') },
    {
      key: 'waiting',
      tasks: tasks.filter(
        (task) =>
          task.status === 'blocked' && task.waitingKind !== 'user' && task.waitingKind !== 'error'
      ),
    },
    { key: 'pending', tasks: tasks.filter((task) => task.status === 'pending') },
    { key: 'completed', tasks: tasks.filter((task) => task.status === 'completed') },
  ];
  const visibleCount = groups.reduce((count, group) => count + group.tasks.length, 0);
  const sessionGroups =
    scope === 'project' && groupBy === 'session'
      ? SESSION_GROUP_KEYS.map((key) => ({
          key,
          sessions: buildSessions(tasks, chatTitles).filter(
            (session) => sessionGroupKey(session) === key
          ),
        }))
      : null;
  const renderTasks = (items: Task[], checklist = scope === 'chat'): React.ReactNode =>
    items.map((task) => (
      <TaskProgressCard
        compact
        checklist={checklist}
        key={task.id}
        selected={task.id === selectedTaskId}
        opening={task.id === pendingTaskId}
        disabled={pendingTaskId != null}
        task={task}
        tasks={tasks}
        chatTitle={task.chatTitle ?? (task.chatId ? chatTitles[task.chatId] : undefined)}
        onOpen={onOpenTask}
      />
    ));
  const badgeClass = (key: string): string =>
    key === 'attention' || key === 'waiting' || key === 'stalled'
      ? 'bg-brutal-yellow text-brutal-black'
      : key === 'active'
        ? 'bg-brutal-blue text-white'
        : key === 'completed'
          ? 'bg-brutal-green text-brutal-black'
          : 'bg-white text-brutal-black';
  const renderSection = (
    key: string,
    label: string,
    count: number,
    tone: string,
    children: React.ReactNode
  ): React.ReactNode => (
    <details
      key={key}
      open={!collapsedGroups[key]}
      onToggle={(event) => {
        const collapsed = !event.currentTarget.open;
        setCollapsedGroups((previous) =>
          previous[key] === collapsed ? previous : { ...previous, [key]: collapsed }
        );
      }}
      className="group/task-section"
    >
      <summary className="flex items-center gap-2 cursor-pointer select-none list-none [&::-webkit-details-marker]:hidden border-y-2 border-brutal-black bg-neutral-100 dark:bg-zinc-800 px-3 py-2 text-xs font-black font-mono tracking-wide text-brutal-black dark:text-white hover:bg-neutral-200 dark:hover:bg-zinc-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue">
        <span
          aria-hidden="true"
          className="inline-block transition-transform group-open/task-section:rotate-90"
        >
          ▸
        </span>
        {label}{' '}
        <span
          className={`ml-auto min-w-5 border border-brutal-black px-1 text-center font-mono ${badgeClass(tone)}`}
        >
          {count}
        </span>
      </summary>
      <div className="py-1">{children}</div>
    </details>
  );
  const sessionReason = (session: SessionCard, group: SessionGroupKey): string | null => {
    if (group === 'attention' && session.blocker) {
      return (
        [
          session.blocker.waitingReason,
          session.blocker.nextAction
            ? t('taskFlow.nextAction', { action: session.blocker.nextAction })
            : null,
        ]
          .filter(Boolean)
          .join(' · ') || null
      );
    }
    if (group === 'stalled') {
      return t('taskFlow.stalledReason', {
        count: session.tasks.filter(isActionable).length,
      });
    }
    if (group === 'waiting') {
      return session.tasks.find((task) => task.status === 'blocked')?.waitingReason ?? null;
    }
    return null;
  };
  const renderSession = (session: SessionCard): React.ReactNode => {
    const group = sessionGroupKey(session);
    const title =
      session.title || (session.chatId ? session.chatId : t('taskFlow.unassignedSession'));
    const reason = sessionReason(session, group);
    const { open, done } = splitSessionTasks(session);
    const expanded = Boolean(expandedSessions[session.key]);
    const tasksId = `session-tasks-${session.key}`;
    return (
      <section
        key={session.key}
        aria-label={title}
        className="m-2 border-2 border-brutal-black bg-white dark:bg-zinc-800 shadow-[2px_2px_0_0_#000]"
      >
        <header className="border-b-2 border-brutal-black px-3 py-2 space-y-1">
          {session.chatId && onOpenChat ? (
            <button
              type="button"
              className="block w-full text-left text-sm font-black leading-snug line-clamp-2 break-words hover:underline underline-offset-4"
              title={`${title} · ${t('taskFlow.openChat')}`}
              onClick={() => onOpenChat(session.chatId!)}
            >
              {title}
            </button>
          ) : (
            <h2 className="text-sm font-black leading-snug line-clamp-2 break-words">{title}</h2>
          )}
          {(session.projectLabel || group !== 'completed') && (
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 min-w-0">
              {session.projectLabel && (
                <span className="min-w-0 truncate text-[11px] text-neutral-500 dark:text-zinc-400">
                  {session.projectLabel}
                </span>
              )}
              {group === 'active' ? (
                <span className="shrink-0 flex items-center gap-1 font-mono text-[10px] font-bold uppercase">
                  <span
                    aria-hidden="true"
                    className="w-1.5 h-1.5 bg-brutal-blue animate-brutal-blink"
                  />
                  {t('taskFlow.sessionRunning')}
                </span>
              ) : group === 'attention' && session.blocker ? (
                <span className="shrink-0 border border-brutal-black bg-brutal-yellow px-1 font-mono text-[10px] font-bold text-brutal-black">
                  {t(`taskFlow.wait.${session.blocker.waitingKind}`)}
                </span>
              ) : group === 'stalled' ? (
                <span className="shrink-0 border border-brutal-black bg-white dark:bg-zinc-700 px-1 font-mono text-[10px] font-bold uppercase">
                  {t('taskFlow.sessionIdle')}
                </span>
              ) : null}
            </div>
          )}
        </header>
        {reason && (
          <p
            className={`border-b border-brutal-black/20 px-3 py-2 text-xs leading-relaxed ${group === 'attention' ? 'bg-brutal-yellow/20' : 'bg-neutral-50 dark:bg-zinc-900'}`}
          >
            {reason}
          </p>
        )}
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={tasksId}
          onClick={() =>
            setExpandedSessions((previous) => ({ ...previous, [session.key]: !expanded }))
          }
          className="group/toggle flex w-full items-center gap-2 px-3 py-1.5 text-left font-mono text-[11px] font-bold text-neutral-500 hover:bg-neutral-50 hover:text-brutal-black dark:text-zinc-400 dark:hover:bg-zinc-700 dark:hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue"
        >
          <span
            aria-hidden="true"
            className={`inline-block transition-transform ${expanded ? 'rotate-90' : ''}`}
          >
            ▸
          </span>
          {[
            open.length > 0 ? t('taskFlow.openCount', { count: open.length }) : null,
            done.length > 0 ? t('taskFlow.doneCount', { count: done.length }) : null,
          ]
            .filter(Boolean)
            .join(' · ')}
        </button>
        <div
          id={tasksId}
          hidden={!expanded}
          className="border-t border-brutal-black/10 dark:border-zinc-700"
        >
          {open.length > 0 && <div>{renderTasks(open, true)}</div>}
          {done.length > 0 &&
            (open.length > 0 ? (
              <details className="group/done border-t border-brutal-black/10 dark:border-zinc-700">
                <summary className="flex items-center gap-2 cursor-pointer select-none list-none [&::-webkit-details-marker]:hidden px-4 py-2 font-mono text-[11px] font-bold text-neutral-500 dark:text-zinc-400 hover:text-brutal-black dark:hover:text-white">
                  <span
                    aria-hidden="true"
                    className="inline-block transition-transform group-open/done:rotate-90"
                  >
                    ▸
                  </span>
                  ✓ {t('taskFlow.doneCount', { count: done.length })}
                </summary>
                {renderTasks(done, true)}
              </details>
            ) : (
              <div>{renderTasks(done, true)}</div>
            ))}
        </div>
      </section>
    );
  };
  return (
    <div className="flex flex-col h-full min-h-0 bg-white dark:bg-zinc-900 text-brutal-black dark:text-white">
      <header className="task-header shrink-0 border-b-2 border-brutal-black bg-white dark:bg-zinc-800 px-5 py-4 space-y-4">
        <div className="task-heading flex items-start justify-between gap-3">
          <div>
            {scope === 'project' && (
              <p className="text-xs text-neutral-500 dark:text-zinc-400">{projectName}</p>
            )}
            <h1 className="text-xl font-black mt-1">{t('sidebar.tabs.plan')}</h1>
            {scope === 'project' && kanban && !error && (
              <p className="mt-2 text-sm text-neutral-500 dark:text-zinc-400">
                {t('taskFlow.overview', {
                  attention: groups[0].tasks.length,
                  active: groups[1].tasks.length,
                })}
              </p>
            )}
          </div>
        </div>
        {headerControls}
      </header>
      <div className="task-scroll flex-1 overflow-auto [scrollbar-gutter:stable] p-4 md:p-6 min-h-0">
        {summary && <div className="max-w-5xl mx-auto mb-4">{summary}</div>}
        {error ? (
          <div role="alert" className="text-sm space-y-3">
            <p>{t('taskFlow.loadError')}</p>
            <button onClick={onRetry} className="underline">
              {t('taskFlow.retry')}
            </button>
          </div>
        ) : loading ? (
          <p role="status" className="text-sm text-neutral-500">
            {t('taskFlow.loading')}
          </p>
        ) : visibleCount === 0 && goalsWithoutTasks.length === 0 && !summary ? (
          <div className="task-empty max-w-md mx-auto py-12 space-y-3 text-center">
            <h2 className="text-lg font-bold">{t('taskFlow.emptyTitle')}</h2>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-zinc-300">
              {t(scope === 'chat' ? 'taskFlow.chatEmpty' : 'taskFlow.projectEmpty')}
            </p>
          </div>
        ) : scope === 'chat' ? (
          <section className="max-w-3xl mx-auto" aria-label={t('taskFlow.checklist')}>
            {visibleCount > 0 && (
              <div className="mb-3 flex items-center justify-between gap-3 text-xs font-mono text-neutral-500 dark:text-zinc-400">
                <span className="font-bold text-brutal-black dark:text-white">
                  {t('taskFlow.checklist')}
                </span>
                <span>
                  {t('taskFlow.checklistProgress', {
                    completed: groups[4].tasks.length,
                    total: visibleCount,
                  })}
                </span>
              </div>
            )}
            <ol className="list-none m-0 p-0">
              {tasks
                .filter((task) => task.status !== 'cancelled')
                .slice()
                .sort((a, b) => a.id - b.id)
                .map((task) => (
                  <li key={task.id}>{renderTasks([task])}</li>
                ))}
            </ol>
          </section>
        ) : (
          <div className="max-w-5xl mx-auto space-y-3">
            {goalsWithoutTasks.map((goal) => (
              <section
                key={`goal-${goal.id}`}
                className="border-2 border-brutal-black bg-white dark:bg-zinc-800 p-4 space-y-2"
              >
                <p className="text-xs text-neutral-600 dark:text-zinc-300">
                  {t('goal.title')} · {t(`goal.status.${goal.status}`)}
                </p>
                <h2 className="text-sm font-bold">{goal.objective}</h2>
                {goal.chatId && onOpenChat && (
                  <button
                    type="button"
                    className="text-xs font-bold underline underline-offset-4"
                    onClick={() => onOpenChat(goal.chatId!)}
                  >
                    {t('taskFlow.openChat')} →
                  </button>
                )}
              </section>
            ))}
            {sessionGroups
              ? sessionGroups
                  .filter((group) => group.sessions.length > 0)
                  .map((group) =>
                    renderSection(
                      `session-${group.key}`,
                      t(`taskFlow.sessionGroups.${group.key}`),
                      group.sessions.length,
                      group.key,
                      group.sessions.map(renderSession)
                    )
                  )
              : groups
                  .filter((group) => group.tasks.length > 0)
                  .map((group) =>
                    renderSection(
                      group.key,
                      t(`taskFlow.groups.${group.key}`),
                      group.tasks.length,
                      group.key,
                      renderTasks(group.tasks)
                    )
                  )}
          </div>
        )}
      </div>
    </div>
  );
};
