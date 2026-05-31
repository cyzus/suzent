import React from 'react';
import type { Goal, Task, GoalStatus, TaskStatus } from '../../types/api';
import { useI18n } from '../../i18n';

interface GoalTaskViewProps {
  goal: Goal | null;
  tasks: Task[];
}

const GOAL_BADGE: Record<GoalStatus, string> = {
  active:    'bg-brutal-blue text-white border-brutal-black',
  paused:    'bg-brutal-yellow text-brutal-black border-brutal-black',
  completed: 'bg-brutal-green text-brutal-black border-brutal-black',
  cancelled: 'bg-white dark:bg-zinc-700 text-neutral-500 border-brutal-black',
};

const TASK_BORDER: Record<TaskStatus, string> = {
  in_progress: 'border-brutal-black shadow-[2px_2px_0_0_#000] bg-white dark:bg-zinc-700',
  pending:     'border-brutal-black bg-white dark:bg-zinc-800',
  blocked:     'border-brutal-black bg-brutal-yellow/20 dark:bg-zinc-800',
  completed:   'border-brutal-black bg-white dark:bg-zinc-800 opacity-50',
  cancelled:   'border-brutal-black bg-neutral-100 dark:bg-zinc-900 opacity-30',
};

function TaskCheck({ status }: { status: TaskStatus }) {
  if (status === 'completed') {
    return (
      <div className="w-4 h-4 shrink-0 border-2 border-brutal-black bg-brutal-green flex items-center justify-center">
        <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      </div>
    );
  }
  if (status === 'in_progress') {
    return (
      <div className="w-4 h-4 shrink-0 border-2 border-brutal-black bg-brutal-blue flex items-center justify-center animate-pulse">
        <div className="w-1.5 h-1.5 bg-white" />
      </div>
    );
  }
  if (status === 'blocked') {
    return (
      <div className="w-4 h-4 shrink-0 border-2 border-brutal-black bg-brutal-yellow flex items-center justify-center">
        <span className="text-[8px] font-black text-brutal-black leading-none">!</span>
      </div>
    );
  }
  if (status === 'cancelled') {
    return (
      <div className="w-4 h-4 shrink-0 border-2 border-brutal-black bg-white dark:bg-zinc-700 flex items-center justify-center">
        <span className="text-[8px] font-black text-neutral-400 leading-none">✕</span>
      </div>
    );
  }
  // pending
  return <div className="w-4 h-4 shrink-0 border-2 border-brutal-black bg-white dark:bg-zinc-700" />;
}

export const GoalTaskView: React.FC<GoalTaskViewProps> = ({ goal, tasks }) => {
  const { t } = useI18n();
  const [subgoalsExpanded, setSubgoalsExpanded] = React.useState(true);

  const activeTasks = tasks.filter(t => t.status !== 'cancelled');
  const completed = tasks.filter(t => t.status === 'completed').length;
  const total = activeTasks.length;
  const progress = total > 0 ? completed / total : 0;

  return (
    <div className="flex flex-col h-full min-h-0">

      {/* ── Goal header ─────────────────────────────────────────── */}
      <div className="shrink-0 border-b-3 border-brutal-black bg-white dark:bg-zinc-800">
        {goal ? (
          <div className="p-3 space-y-2">
            {/* Label + badge */}
            <div className="flex items-center justify-between">
              <span className="text-[9px] font-black uppercase tracking-widest font-mono text-brutal-black dark:text-white">
                {t('goal.title')}
              </span>
              <span className={`text-[8px] font-black px-1.5 py-0.5 border-2 ${GOAL_BADGE[goal.status]}`}>
                {t(`goal.status.${goal.status}`)}
              </span>
            </div>

            {/* Objective */}
            <div className="text-sm font-black leading-snug text-brutal-black dark:text-white">
              {goal.objective}
            </div>

            {/* Progress bar */}
            {total > 0 && (
              <div>
                <div className="flex justify-between text-[9px] font-black font-mono uppercase text-brutal-black dark:text-white mb-1">
                  <span>{completed}/{total}</span>
                  {goal.maxTurns != null && (
                    <span>{t('goal.turns', { elapsed: String(goal.turnsElapsed), max: String(goal.maxTurns) })}</span>
                  )}
                </div>
                <div className="w-full h-3 bg-white dark:bg-zinc-700 border-2 border-brutal-black overflow-hidden shadow-[2px_2px_0_0_#000]">
                  <div
                    className={`h-full transition-all duration-300 ${progress >= 1 ? 'bg-brutal-green' : 'bg-brutal-blue'}`}
                    style={{ width: `${progress * 100}%` }}
                  />
                </div>
              </div>
            )}

            {/* Subgoals */}
            {goal.subgoals.length > 0 && (
              <div>
                <button
                  onClick={() => setSubgoalsExpanded(v => !v)}
                  className="flex items-center gap-1 text-[9px] font-black uppercase tracking-wider font-mono text-brutal-black dark:text-white"
                >
                  <svg className={`w-2.5 h-2.5 transition-transform ${subgoalsExpanded ? '' : '-rotate-90'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                  {t('goal.subgoals')} ({goal.subgoals.length})
                </button>
                {subgoalsExpanded && (
                  <ul className="mt-1 space-y-0.5 pl-1 border-l-2 border-brutal-black ml-1">
                    {goal.subgoals.map((sg, i) => (
                      <li key={i} className="text-[10px] font-bold text-brutal-black dark:text-white pl-2">
                        · {sg}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="px-3 py-4 text-center">
            <span className="text-[10px] font-black uppercase tracking-widest font-mono text-brutal-black dark:text-white opacity-30">
              {t('goal.noGoal')}
            </span>
          </div>
        )}
      </div>

      {/* ── Tasks section header ─────────────────────────────────── */}
      {activeTasks.length > 0 && (
        <div className="shrink-0 px-3 py-1.5 border-b-2 border-brutal-black bg-white dark:bg-zinc-800">
          <span className="text-[9px] font-black uppercase tracking-widest font-mono text-brutal-black dark:text-white">
            {t('task.title')}
          </span>
        </div>
      )}

      {/* ── Task list ───────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto scrollbar-thin scrollbar-track-neutral-200 dark:scrollbar-track-zinc-700 scrollbar-thumb-brutal-black bg-neutral-50 dark:bg-zinc-900 p-2 space-y-2 min-h-0">
        {activeTasks.length === 0 ? (
          <div className="text-[10px] font-black uppercase tracking-widest font-mono text-brutal-black dark:text-white opacity-30 text-center pt-4">
            {t('task.noTasks')}
          </div>
        ) : (
          activeTasks.map(task => (
            <div key={task.id} className={`border-2 p-2 ${TASK_BORDER[task.status]}`}>
              <div className="flex items-start gap-2">
                <div className="mt-0.5"><TaskCheck status={task.status} /></div>

                <div className="flex-1 min-w-0">
                  {/* Title / activeForm */}
                  <div className={`text-xs font-black leading-snug text-brutal-black dark:text-white ${task.status === 'completed' ? 'line-through opacity-50' : ''}`}>
                    {task.status === 'in_progress' && task.activeForm
                      ? task.activeForm
                      : task.title}
                  </div>
                  {/* Description — only for pending/blocked */}
                  {(task.status === 'pending' || task.status === 'blocked') && (
                    <div className="text-[10px] font-bold text-brutal-black dark:text-white opacity-50 mt-0.5 leading-snug">
                      {task.description}
                    </div>
                  )}
                  {/* Meta row */}
                  <div className="flex flex-wrap gap-x-2 mt-0.5">
                    {task.assignee && task.assignee !== 'main' && (
                      <span className="text-[8px] font-mono font-bold text-brutal-black dark:text-white opacity-50">
                        @{task.assignee}
                      </span>
                    )}
                    {task.blockedBy.length > 0 && (
                      <span className="text-[8px] font-black font-mono text-brutal-black bg-brutal-yellow px-1 border border-brutal-black">
                        {t('task.blockedBy', { ids: task.blockedBy.map(b => `#${b}`).join(', ') })}
                      </span>
                    )}
                    {task.blocks.length > 0 && (
                      <span className="text-[8px] font-mono font-bold text-brutal-black dark:text-white opacity-40">
                        {t('task.blocks', { ids: task.blocks.map(b => `#${b}`).join(', ') })}
                      </span>
                    )}
                  </div>
                </div>

                <span className="text-[8px] font-mono font-black text-brutal-black dark:text-white opacity-20 shrink-0 mt-0.5">
                  #{task.id}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
