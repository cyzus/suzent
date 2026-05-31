import React from 'react';
import type { Goal, Task, TaskStatus } from '../../types/api';
import type { KanbanData } from '../../hooks/useGoalTasks';
import { useI18n } from '../../i18n';

interface ProjectKanbanViewProps {
  projectName?: string | null;
  kanban: KanbanData | null;
}

const COLUMN_ORDER: TaskStatus[] = ['in_progress', 'pending', 'blocked', 'completed'];

const COLUMN_LABELS: Record<TaskStatus, string> = {
  in_progress: 'Active',
  pending: 'Todo',
  blocked: 'Blocked',
  completed: 'Done',
  cancelled: 'Cancelled',
};

const COLUMN_COLORS: Record<TaskStatus, string> = {
  in_progress: 'border-brutal-blue',
  pending: 'border-brutal-black',
  blocked: 'border-brutal-yellow',
  completed: 'border-brutal-green',
  cancelled: 'border-neutral-300',
};

const CARD_COLORS: Record<TaskStatus, string> = {
  in_progress: 'bg-white dark:bg-zinc-700 shadow-[2px_2px_0_0_#3b82f6]',
  pending: 'bg-white dark:bg-zinc-800',
  blocked: 'bg-brutal-yellow/10 dark:bg-zinc-800',
  completed: 'bg-brutal-green/10 dark:bg-zinc-800 opacity-60',
  cancelled: 'bg-neutral-100 dark:bg-zinc-900 opacity-40',
};

const BADGE_COLORS: Record<TaskStatus, string> = {
  in_progress: 'bg-brutal-blue text-white',
  pending: 'bg-white dark:bg-zinc-700 text-brutal-black dark:text-white',
  blocked: 'bg-brutal-yellow text-brutal-black',
  completed: 'bg-brutal-green text-brutal-black',
  cancelled: 'bg-neutral-200 text-neutral-500',
};

export const ProjectKanbanView: React.FC<ProjectKanbanViewProps> = ({ projectName, kanban }) => {
  const { t } = useI18n();

  if (!kanban) {
    return (
      <div className="flex items-center justify-center h-full text-[10px] font-mono font-bold uppercase tracking-widest text-neutral-400 dark:text-neutral-500">
        No project data.
      </div>
    );
  }

  const { goals, tasks } = kanban;

  const tasksByStatus: Partial<Record<TaskStatus, Task[]>> = {};
  for (const status of COLUMN_ORDER) {
    const bucket = tasks.filter(t => t.status === status);
    if (bucket.length > 0) tasksByStatus[status] = bucket;
  }

  const visibleColumns = COLUMN_ORDER.filter(s => tasksByStatus[s]?.length);

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Header */}
      <div className="shrink-0 px-3 py-2 border-b-3 border-brutal-black bg-white dark:bg-zinc-800">
        <div className="text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-500 dark:text-neutral-400">
          {t('projectBoard.title')}
        </div>
        {projectName && (
          <div className="text-xs font-bold text-brutal-black dark:text-white mt-0.5 truncate">
            {projectName}
          </div>
        )}
      </div>

      {/* Goals summary — compact chips */}
      {goals.length > 0 && (
        <div className="shrink-0 px-3 py-2 border-b border-neutral-200 dark:border-zinc-700 flex flex-wrap gap-1.5">
          {goals.map(goal => (
            <div key={goal.id} className="flex items-center gap-1 bg-brutal-blue/10 dark:bg-brutal-blue/20 border border-brutal-blue/40 px-2 py-0.5 max-w-full">
              <div className="w-1.5 h-1.5 rounded-full bg-brutal-blue shrink-0 animate-pulse" />
              <span className="text-[9px] font-bold text-brutal-black dark:text-white truncate">
                {goal.objective}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Kanban columns */}
      <div className="flex-1 overflow-y-auto min-h-0 p-2">
        {tasks.length === 0 ? (
          <div className="text-[10px] font-mono font-bold uppercase tracking-widest text-neutral-400 dark:text-neutral-500 text-center pt-6">
            {t('projectBoard.noTasks')}
          </div>
        ) : (
          <div className="space-y-3">
            {visibleColumns.map(status => (
              <div key={status}>
                <div className={`text-[9px] font-bold uppercase tracking-wider font-mono mb-1.5 pb-1 border-b-2 ${COLUMN_COLORS[status]} text-neutral-500 dark:text-neutral-400`}>
                  {COLUMN_LABELS[status]} ({tasksByStatus[status]!.length})
                </div>
                <div className="space-y-1.5">
                  {tasksByStatus[status]!.map(task => (
                    <div
                      key={task.id}
                      className={`border-2 border-brutal-black p-2 ${CARD_COLORS[task.status]}`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-start gap-1.5 min-w-0">
                          <span className="text-[8px] font-mono font-bold text-neutral-400 shrink-0 mt-0.5">
                            #{task.id}
                          </span>
                          <span className="text-[11px] font-bold text-brutal-black dark:text-white leading-snug">
                            {task.status === 'in_progress' && task.activeForm
                              ? task.activeForm
                              : task.title}
                          </span>
                        </div>
                        <span className={`text-[8px] font-bold px-1 py-0.5 border border-brutal-black shrink-0 ${BADGE_COLORS[task.status]}`}>
                          {COLUMN_LABELS[task.status]}
                        </span>
                      </div>
                      <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5">
                        {task.assignee && (
                          <span className="text-[8px] font-mono text-neutral-500 dark:text-neutral-400">
                            {task.assignee}
                          </span>
                        )}
                        {task.chatId && (
                          <span className="text-[8px] font-mono text-neutral-400">
                            {task.chatId.slice(0, 8)}…
                          </span>
                        )}
                        {task.blocks.length > 0 && (
                          <span className="text-[8px] font-mono text-neutral-400">
                            blocks {task.blocks.map(b => `#${b}`).join(', ')}
                          </span>
                        )}
                        {task.blockedBy.length > 0 && (
                          <span className="text-[8px] font-mono text-brutal-yellow">
                            blocked by {task.blockedBy.map(b => `#${b}`).join(', ')}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
