import React from 'react';
import type { Goal, Task, GoalStatus, TaskStatus } from '../../types/api';
import { useI18n } from '../../i18n';

interface GoalTaskViewProps {
  goal: Goal | null;
  tasks: Task[];
}

const STATUS_COLORS: Record<GoalStatus, string> = {
  active: 'bg-brutal-blue text-white',
  paused: 'bg-brutal-yellow text-brutal-black',
  completed: 'bg-brutal-green text-brutal-black',
  cancelled: 'bg-neutral-300 text-neutral-600',
};

const TASK_STATUS_COLORS: Record<TaskStatus, string> = {
  pending: 'bg-white dark:bg-zinc-700 text-brutal-black dark:text-white',
  in_progress: 'bg-brutal-blue text-white',
  completed: 'bg-brutal-green text-brutal-black',
  blocked: 'bg-brutal-yellow text-brutal-black',
  cancelled: 'bg-neutral-200 dark:bg-zinc-700 text-neutral-500',
};

export const GoalTaskView: React.FC<GoalTaskViewProps> = ({ goal, tasks }) => {
  const { t } = useI18n();
  const [subgoalsExpanded, setSubgoalsExpanded] = React.useState(true);

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* ── Goal section ──────────────────────────────────────────── */}
      <div className="shrink-0 border-b-3 border-brutal-black bg-white dark:bg-zinc-800">
        <div className="px-3 py-2 flex items-start justify-between gap-2">
          <div className="text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-500 dark:text-neutral-400">
            {t('goal.title')}
          </div>
          {goal && (
            <span className={`text-[9px] font-bold px-1.5 py-0.5 border border-brutal-black shrink-0 ${STATUS_COLORS[goal.status]}`}>
              {t(`goal.status.${goal.status}`)}
            </span>
          )}
        </div>

        {goal ? (
          <div className="px-3 pb-2 space-y-2">
            <div className="text-xs font-bold leading-snug text-brutal-black dark:text-white">
              {goal.objective}
            </div>

            {/* Turns progress */}
            {goal.maxTurns != null && (
              <div className="space-y-0.5">
                <div className="flex justify-between text-[9px] font-mono font-bold uppercase text-neutral-500 dark:text-neutral-400">
                  <span>{t('goal.turns', { elapsed: String(goal.turnsElapsed), max: String(goal.maxTurns) })}</span>
                  <span>{Math.round((goal.turnsElapsed / goal.maxTurns) * 100)}%</span>
                </div>
                <div className="w-full h-1.5 bg-neutral-200 dark:bg-zinc-700 border border-brutal-black overflow-hidden">
                  <div
                    className="h-full bg-brutal-blue transition-all duration-300"
                    style={{ width: `${Math.min(100, (goal.turnsElapsed / goal.maxTurns) * 100)}%` }}
                  />
                </div>
              </div>
            )}

            {/* Subgoals */}
            {goal.subgoals.length > 0 && (
              <div>
                <button
                  onClick={() => setSubgoalsExpanded(v => !v)}
                  className="text-[9px] font-bold uppercase tracking-wider font-mono text-neutral-500 dark:text-neutral-400 flex items-center gap-1"
                >
                  <svg className={`w-2.5 h-2.5 transition-transform ${subgoalsExpanded ? '' : '-rotate-90'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                  {t('goal.subgoals')} ({goal.subgoals.length})
                </button>
                {subgoalsExpanded && (
                  <ul className="mt-1 space-y-0.5">
                    {goal.subgoals.map((sg, i) => (
                      <li key={i} className="text-[10px] text-brutal-black dark:text-white flex gap-1.5">
                        <span className="text-neutral-400 shrink-0">·</span>
                        <span>{sg}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="px-3 pb-2 text-[10px] font-mono text-neutral-400 dark:text-neutral-500 uppercase tracking-widest">
            {t('goal.noGoal')}
          </div>
        )}
      </div>

      {/* ── Tasks section ─────────────────────────────────────────── */}
      <div className="shrink-0 px-3 py-1.5 border-b-2 border-brutal-black bg-white dark:bg-zinc-800">
        <div className="text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-500 dark:text-neutral-400">
          {t('task.title')}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin scrollbar-track-neutral-200 dark:scrollbar-track-zinc-700 scrollbar-thumb-brutal-black bg-neutral-50 dark:bg-zinc-900 p-2 space-y-2 min-h-0">
        {tasks.length === 0 ? (
          <div className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500 uppercase tracking-widest text-center pt-4">
            {t('task.noTasks')}
          </div>
        ) : (
          tasks.map(task => (
            <div
              key={task.id}
              className={`border-2 border-brutal-black p-2 ${task.status === 'completed' ? 'opacity-60' : ''}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-start gap-1.5 min-w-0">
                  <span className="text-[9px] font-mono font-bold text-neutral-400 shrink-0 mt-0.5">
                    #{task.id}
                  </span>
                  <div className="min-w-0">
                    <div className="text-xs font-bold leading-snug text-brutal-black dark:text-white">
                      {task.title}
                    </div>
                    <div className="text-[10px] text-neutral-500 dark:text-neutral-400 leading-snug mt-0.5">
                      {task.description}
                    </div>
                  </div>
                </div>
                <span className={`text-[9px] font-bold px-1 py-0.5 border border-brutal-black shrink-0 whitespace-nowrap ${TASK_STATUS_COLORS[task.status]}`}>
                  {t(`task.status.${task.status.replace('_', '')}`)}
                </span>
              </div>

              {/* Meta: assignee, deps */}
              <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5">
                {task.assignee && (
                  <span className="text-[9px] font-mono text-neutral-500 dark:text-neutral-400">
                    {t('task.assignee', { name: task.assignee })}
                  </span>
                )}
                {task.blocks.length > 0 && (
                  <span className="text-[9px] font-mono text-neutral-500 dark:text-neutral-400">
                    {t('task.blocks', { ids: task.blocks.map(b => `#${b}`).join(', ') })}
                  </span>
                )}
                {task.blockedBy.length > 0 && (
                  <span className="text-[9px] font-mono text-brutal-yellow">
                    {t('task.blockedBy', { ids: task.blockedBy.map(b => `#${b}`).join(', ') })}
                  </span>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
