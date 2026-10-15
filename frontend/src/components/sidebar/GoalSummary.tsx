import React, { useState } from 'react';
import type { Goal, Task } from '../../types/api';
import { useI18n } from '../../i18n';
import { useGoalTasks } from '../../hooks/useGoalTasks';

export function GoalSummary({
  goal: currentGoal,
  tasks,
}: {
  goal: Goal;
  tasks: Task[];
}): React.ReactElement {
  const { t } = useI18n();
  const { goalAction } = useGoalTasks();
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const visible = tasks.filter((task) => task.status !== 'cancelled');
  const completed = visible.filter((task) => task.status === 'completed');
  const action = async (value: 'pause' | 'resume'): Promise<void> => {
    setBusy(true);
    setFeedback(null);
    try {
      await goalAction(value);
      setFeedback(t(`taskFlow.${value === 'pause' ? 'paused' : 'resumed'}`));
    } catch {
      setFeedback(t('taskFlow.actionError'));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="task-goal space-y-3 p-1">
      <div className="text-xs text-neutral-600 dark:text-zinc-300">
        {t(`goal.status.${currentGoal.status}`)}
      </div>
      <h3 className="text-base font-black break-words">{currentGoal.objective}</h3>
      {visible.length > 0 && (
        <div>
          <p className="text-xs mb-2">
            {t('taskFlow.steps', {
              completed: String(completed.length),
              total: String(visible.length),
            })}
          </p>
          <progress
            className="w-full h-1.5 accent-blue-600"
            value={completed.length}
            max={visible.length}
            aria-label={t('taskFlow.stepProgress')}
          />
        </div>
      )}
      {(currentGoal.subgoals.length > 0 || currentGoal.maxTurns != null) && (
        <details className="text-xs">
          <summary className="cursor-pointer text-neutral-600 dark:text-zinc-300">
            {t('taskFlow.details')}
          </summary>
          <ul className="mt-2 space-y-1">
            {currentGoal.subgoals.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
          {currentGoal.maxTurns != null && (
            <p className="mt-2">
              {t('taskFlow.budget', {
                elapsed: String(currentGoal.turnsElapsed),
                max: String(currentGoal.maxTurns),
              })}
            </p>
          )}
        </details>
      )}
      {(currentGoal.status === 'active' || currentGoal.status === 'paused') && (
        <button
          disabled={busy}
          onClick={() => void action(currentGoal.status === 'active' ? 'pause' : 'resume')}
          className="border-2 border-brutal-black bg-white dark:bg-zinc-800 px-3 py-1.5 text-xs font-bold font-mono shadow-[2px_2px_0_0_#000] hover:bg-brutal-yellow/20 disabled:opacity-50"
        >
          {busy
            ? t('taskFlow.working')
            : t(`goal.${currentGoal.status === 'active' ? 'pause' : 'resume'}`)}
        </button>
      )}
      {feedback && (
        <p role="status" className="text-xs">
          {feedback}
        </p>
      )}
    </section>
  );
}
