import React, { useState } from 'react';
import type { Task } from '../../types/api';
import type { KanbanData } from '../../hooks/useGoalTasks';
import { useI18n } from '../../i18n';
import { TaskProgressCard } from './TaskProgressCard';

interface ProjectKanbanViewProps {
  projectName?: string | null;
  projectId?: string | null;
  kanban: KanbanData | null;
  chatTitles?: Record<string, string>;
  headerControls?: React.ReactNode;
  summary?: React.ReactNode;
  narrow?: boolean;
  selectedTaskId?: number | null;
  pendingTaskId?: number | null;
  onOpenTask: (task: Task) => void;
  onResult: (task: Task) => void;
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
  narrow = false,
  selectedTaskId,
  pendingTaskId,
  onOpenTask,
  onResult,
  onOpenChat,
  loading = false,
  error,
  onRetry,
}) => {
  const { t } = useI18n();
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({
    completed: true,
  });
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
  const renderTasks = (items: Task[]): React.ReactNode =>
    items.map((task) => (
      <TaskProgressCard
        compact
        key={task.id}
        selected={task.id === selectedTaskId}
        opening={task.id === pendingTaskId}
        disabled={pendingTaskId != null}
        task={task}
        tasks={tasks}
        chatTitle={task.chatId ? chatTitles[task.chatId] : undefined}
        onOpen={onOpenTask}
        onResult={onResult}
      />
    ));
  return (
    <div className="flex flex-col h-full min-h-0 bg-white dark:bg-zinc-900 text-brutal-black dark:text-white">
      <header className="task-header shrink-0 border-b-2 border-brutal-black bg-white dark:bg-zinc-800 px-5 py-4 space-y-4">
        <div className="task-heading flex items-start justify-between gap-3">
          <div>
            <p className="text-xs text-neutral-500 dark:text-zinc-400">{projectName}</p>
            <h1 className="text-xl font-black mt-1">{t('sidebar.tabs.plan')}</h1>
            {kanban && !error && (
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
              {t(narrow ? 'taskFlow.chatEmpty' : 'taskFlow.projectEmpty')}
            </p>
          </div>
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
            {groups
              .filter((group) => group.tasks.length > 0)
              .map((group) => (
                <details
                  key={group.key}
                  open={!collapsedGroups[group.key]}
                  onToggle={(event) => {
                    const collapsed = !event.currentTarget.open;
                    setCollapsedGroups((previous) =>
                      previous[group.key] === collapsed
                        ? previous
                        : { ...previous, [group.key]: collapsed }
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
                    {t(`taskFlow.groups.${group.key}`)}{' '}
                    <span
                      className={`ml-auto min-w-5 border border-brutal-black px-1 text-center font-mono ${group.key === 'attention' || group.key === 'waiting' ? 'bg-brutal-yellow text-brutal-black' : group.key === 'active' ? 'bg-brutal-blue text-white' : group.key === 'completed' ? 'bg-brutal-green text-brutal-black' : 'bg-white text-brutal-black'}`}
                    >
                      {group.tasks.length}
                    </span>
                  </summary>
                  <div className="py-1">{renderTasks(group.tasks)}</div>
                </details>
              ))}
          </div>
        )}
      </div>
    </div>
  );
};
