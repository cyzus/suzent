import React from 'react';
import type { Goal, Task, GoalStatus, TaskStatus } from '../../types/api';
import { useI18n } from '../../i18n';
import { BrutalButton } from '../BrutalButton';

interface GoalTaskViewProps {
  goal: Goal | null;
  tasks: Task[];
  onOpenBoard?: () => void;
  projectTaskCount?: number;
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

const BoardIcon = () => (
  <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
  </svg>
);

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
  return <div className="w-4 h-4 shrink-0 border-2 border-brutal-black bg-white dark:bg-zinc-700" />;
}

export const GoalTaskView: React.FC<GoalTaskViewProps> = ({ goal, tasks, onOpenBoard, projectTaskCount }) => {
  const { t } = useI18n();
  const [subgoalsExpanded, setSubgoalsExpanded] = React.useState(true);

  const activeTasks = tasks.filter(t => t.status !== 'cancelled');
  const completed = tasks.filter(t => t.status === 'completed').length;
  const total = activeTasks.length;
  const progress = total > 0 ? completed / total : 0;
  const hasContent = goal !== null || activeTasks.length > 0;

  return (
    <div className="flex flex-col h-full min-h-0">

      {/* ── Goal header (always visible) ─────────────────────────── */}
      <div className="shrink-0 border-b-2 border-brutal-black bg-white dark:bg-zinc-800">
        {goal ? (
          <div className="p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[9px] font-black uppercase tracking-widest font-mono text-brutal-black dark:text-white">
                {t('goal.title')}
              </span>
              <span className={`text-[8px] font-black px-1.5 py-0.5 border-2 ${GOAL_BADGE[goal.status]}`}>
                {t(`goal.status.${goal.status}`)}
              </span>
            </div>
            <div className="text-sm font-black leading-snug text-brutal-black dark:text-white">
              {goal.objective}
            </div>
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
                      <li key={i} className="text-[10px] font-bold text-brutal-black dark:text-white pl-2">· {sg}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="px-3 py-2 flex items-center justify-between">
            <span className="text-[9px] font-black uppercase tracking-widest font-mono text-brutal-black dark:text-white">
              {t('goal.title')}
            </span>
            <span className="text-[9px] font-black uppercase tracking-widest font-mono text-brutal-black dark:text-white opacity-30">
              {t('goal.noGoal')}
            </span>
          </div>
        )}
      </div>

      {/* ── Body: flex-1, splits based on content ────────────────── */}
      <div className="flex-1 flex flex-col min-h-0">

        {hasContent ? (
          /* Content state: tasks header + scrollable list */
          <>
            <div className="shrink-0 px-3 py-1.5 border-b-2 border-brutal-black bg-white dark:bg-zinc-800 flex items-center justify-between">
              <span className="text-[9px] font-black uppercase tracking-widest font-mono text-brutal-black dark:text-white">
                {t('task.title')}
              </span>
              {onOpenBoard && (
                <BrutalButton size="sm" onClick={onOpenBoard} title="Open full project board">
                  <BoardIcon /> Board
                </BrutalButton>
              )}
            </div>
            <div className="flex-1 overflow-y-auto scrollbar-thin scrollbar-track-neutral-200 dark:scrollbar-track-zinc-700 scrollbar-thumb-brutal-black bg-neutral-50 dark:bg-zinc-900 p-2 space-y-2 min-h-0">
              {activeTasks.map(task => (
                <div key={task.id} className={`border-2 p-2 ${TASK_BORDER[task.status]}`}>
                  <div className="flex items-start gap-2">
                    <div className="mt-0.5"><TaskCheck status={task.status} /></div>
                    <div className="flex-1 min-w-0">
                      <div className={`text-xs font-black leading-snug text-brutal-black dark:text-white ${task.status === 'completed' ? 'line-through opacity-50' : ''}`}>
                        {task.status === 'in_progress' && task.activeForm ? task.activeForm : task.title}
                      </div>
                      {(task.status === 'pending' || task.status === 'blocked') && (
                        <div className="text-[10px] font-bold text-brutal-black dark:text-white opacity-50 mt-0.5 leading-snug">
                          {task.description}
                        </div>
                      )}
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
              ))}
            </div>
          </>
        ) : (
          /* Empty state: two equal halves — grey void top, white board panel bottom */
          <>
            {/* Half top: dim "no tasks" */}
            <div className="flex-1 flex items-center justify-center border-b-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900">
              <span className="text-[9px] font-black uppercase tracking-widest font-mono text-brutal-black dark:text-white opacity-20">
                {t('task.noTasksForChat')}
              </span>
            </div>

            {/* Half bottom: board entry */}
            {onOpenBoard && (
              <div className="flex-1 flex flex-col justify-center gap-3 bg-white dark:bg-zinc-800 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-[9px] font-black uppercase tracking-widest font-mono text-brutal-black dark:text-white">
                    {t('projectBoard.title')}
                  </span>
                  <BoardIcon />
                </div>
                {projectTaskCount != null && (
                  <div>
                    <div className="text-3xl font-black text-brutal-black dark:text-white leading-none tracking-tight">
                      {projectTaskCount}
                    </div>
                    <div className="text-[8px] font-black uppercase tracking-widest font-mono text-brutal-black dark:text-white opacity-40 mt-0.5">
                      {t('projectBoard.taskCount')}
                    </div>
                  </div>
                )}
                <BrutalButton
                  variant="default"
                  size="md"
                  onClick={onOpenBoard}
                  className="w-full justify-between mt-1 font-black uppercase tracking-wider"
                >
                  <span>{t('projectBoard.open')}</span>
                  <span>→</span>
                </BrutalButton>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};
