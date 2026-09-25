import React, { useEffect, useState } from 'react';
import { ArrowPathIcon, CommandLineIcon, StopIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { getApiBase } from '../../lib/api';
import { useI18n } from '../../i18n';
import { BackgroundTaskSummary, useBackgroundTasks } from '../../hooks/useBackgroundTasks';
import { isStreamStateStale, isSubAgentActive, SubAgentStatusBadge } from '../chat/subAgentStatus';
import { SubAgentView } from './SubAgentView';

interface Props {
  taskId: string;
  onClose?: () => void;
}

function ShellCommandView({ taskId, onClose }: Props): React.ReactElement {
  const { t } = useI18n();
  const { taskStates } = useBackgroundTasks();
  const [fetched, setFetched] = useState<BackgroundTaskSummary | null>(null);
  const [error, setError] = useState('');
  const [stopping, setStopping] = useState(false);
  const streamed = taskStates[taskId];
  const task = isStreamStateStale(streamed?.status, fetched?.status)
    ? fetched
    : (streamed ?? fetched);

  useEffect(() => {
    let active = true;
    setFetched(null);
    setError('');
    const refresh = async () => {
      try {
        const res = await fetch(`${getApiBase()}/background-tasks/${encodeURIComponent(taskId)}`);
        if (!res.ok) throw new Error();
        const data = await res.json();
        if (active) {
          setFetched(data.task);
          setError('');
        }
      } catch {
        if (active) setError('backgroundTasks.loadFailed');
      }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 2000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [taskId]);

  const stop = async () => {
    setStopping(true);
    try {
      const res = await fetch(
        `${getApiBase()}/background-tasks/${encodeURIComponent(taskId)}/stop`,
        { method: 'POST' }
      );
      if (!res.ok) throw new Error();
      const refreshed = await fetch(
        `${getApiBase()}/background-tasks/${encodeURIComponent(taskId)}`
      );
      if (refreshed.ok) setFetched((await refreshed.json()).task);
    } catch {
      setError('backgroundTasks.stopFailed');
    } finally {
      setStopping(false);
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0 font-mono">
      <div className="flex items-center gap-2 p-3 border-b-3 border-brutal-black">
        <CommandLineIcon className="w-5 h-5 shrink-0" />
        <span className="text-xs font-bold flex-1">{t('backgroundTasks.shell')}</span>
        {task && isSubAgentActive(task.status) && (
          <button
            disabled={stopping}
            onClick={() => void stop()}
            className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-sm border border-transparent text-red-600 dark:text-red-400 hover:border-red-200 dark:hover:border-red-800 hover:bg-red-50 dark:hover:bg-red-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 disabled:opacity-50 disabled:cursor-wait transition-colors"
            type="button"
            title={t(stopping ? 'subAgents.stopping' : 'subAgents.stop')}
            aria-label={t(stopping ? 'subAgents.stopping' : 'subAgents.stop')}
            aria-busy={stopping}
          >
            {stopping ? (
              <ArrowPathIcon className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <StopIcon className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        )}
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-sm border border-transparent text-neutral-400 hover:border-neutral-200 dark:hover:border-zinc-600 hover:bg-neutral-100 dark:hover:bg-zinc-700 hover:text-neutral-700 dark:hover:text-neutral-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue transition-colors"
            title={t('subAgents.close')}
            aria-label={t('subAgents.close')}
          >
            <XMarkIcon className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      </div>
      <div className="flex-1 overflow-auto p-3 space-y-3 text-xs">
        {error && (
          <p role="alert" className="text-red-600">
            {t(error)}
          </p>
        )}
        {!task && !error && <p>{t('subAgents.loading')}</p>}
        {task && (
          <>
            <p className="font-bold break-words">{task.description}</p>
            <SubAgentStatusBadge status={task.status} t={t} />
            <p className="text-neutral-500 break-all">{task.command_id}</p>
            {task.started_at && (
              <p>
                {new Date(task.started_at).toLocaleString()}
                {task.finished_at && ` → ${new Date(task.finished_at).toLocaleTimeString()}`}
              </p>
            )}
            {task.exit_code != null && (
              <p>{t('backgroundTasks.exitCode', { code: task.exit_code })}</p>
            )}
            {task.error && <p className="text-red-600 break-words">{task.error}</p>}
            <p className="font-bold">{t('backgroundTasks.output')}</p>
            <pre className="whitespace-pre-wrap break-all bg-neutral-50 dark:bg-zinc-800 p-2">
              {task.result_summary}
            </pre>
          </>
        )}
      </div>
    </div>
  );
}

export function BackgroundTaskView(props: Props): React.ReactElement {
  return props.taskId.startsWith('shell_') ? (
    <ShellCommandView key={props.taskId} {...props} />
  ) : (
    <SubAgentView {...props} />
  );
}
