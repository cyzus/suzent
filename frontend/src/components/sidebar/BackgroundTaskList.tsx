/** Shared task list; polling repairs state after a dropped event stream. */
import { ArrowPathIcon, CommandLineIcon, StopIcon } from '@heroicons/react/24/outline';
import React, { useEffect, useState } from 'react';
import { getApiBase } from '../../lib/api';
import { useBackgroundTasks, BackgroundTaskSummary } from '../../hooks/useBackgroundTasks';
import { isStreamStateStale, isSubAgentActive, SubAgentStatusBadge } from '../chat/subAgentStatus';
import { AgentAvatar } from './subAgentDisplay';
import { toolLabel } from '../chat/toolSummary';
import { useI18n } from '../../i18n';

interface BackgroundTaskListProps {
  chatId: string;
  onSelect: (taskId: string) => void;
}

type BackgroundTaskRow = BackgroundTaskSummary;

function formatDuration(
  startedAt: string | null | undefined,
  finishedAt: string | null | undefined
): string {
  if (!startedAt) return '';
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const ms = end - new Date(startedAt).getTime();
  if (ms < 0) return '';
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

/** Newest first, with anything still working pinned to the top. */
function sortRows(rows: BackgroundTaskRow[]): BackgroundTaskRow[] {
  return [...rows].sort((a, b) => {
    const activeDelta = Number(isSubAgentActive(b.status)) - Number(isSubAgentActive(a.status));
    if (activeDelta !== 0) return activeDelta;
    const key = (r: BackgroundTaskRow) => r.finished_at || r.started_at || '';
    return key(b).localeCompare(key(a));
  });
}

async function stopBackgroundTask(taskId: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/background-tasks/${encodeURIComponent(taskId)}/stop`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error();
}

export const BackgroundTaskList: React.FC<BackgroundTaskListProps> = ({ chatId, onSelect }) => {
  const { t } = useI18n();
  const [historicTasks, setHistoricTasks] = useState<BackgroundTaskRow[]>([]);
  const [stopError, setStopError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [stopping, setStopping] = useState<Set<string>>(new Set());
  const { taskStates } = useBackgroundTasks();

  useEffect(() => {
    setLoading(true);
    setHistoricTasks([]);
    let active = true;
    const refresh = async () => {
      try {
        const res = await fetch(
          `${getApiBase()}/background-tasks?parent_chat_id=${encodeURIComponent(chatId)}`
        );
        if (res.ok && active) {
          const data = await res.json();
          if (active) setHistoricTasks(data.tasks ?? []);
        }
      } finally {
        if (active) setLoading(false);
      }
    };
    void refresh().catch(() => {});
    const timer = setInterval(() => void refresh().catch(() => {}), 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [chatId]);

  const liveTasks = Object.values(taskStates).filter((task) => task.parent_chat_id === chatId);

  const liveById = new Map(liveTasks.map((task) => [task.task_id, task]));
  const merged = [
    ...liveTasks.map((task) => {
      const fetched = historicTasks.find((h) => h.task_id === task.task_id);
      return isStreamStateStale(task.status, fetched?.status) ? fetched! : { ...fetched, ...task };
    }),
    ...historicTasks.filter((task) => !liveById.has(task.task_id)),
  ];
  const tasks = sortRows(merged as BackgroundTaskRow[]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-400 animate-pulse">
        {t('subAgents.loading')}
      </div>
    );
  }

  if (tasks.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-400">
        {t('backgroundTasks.empty')}
      </div>
    );
  }

  const activeCount = tasks.filter((task) => isSubAgentActive(task.status)).length;

  return (
    <div className="flex flex-col h-full min-h-0 font-mono">
      <div className="px-3 py-2 border-b-3 border-brutal-black bg-white dark:bg-zinc-800 shrink-0">
        <span className="text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-500 dark:text-neutral-400">
          {t('backgroundTasks.heading', { count: tasks.length })}
        </span>
        {activeCount > 0 && (
          <span className="ml-2 inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest font-mono text-brutal-blue">
            <span className="w-1.5 h-1.5 rounded-full bg-brutal-blue animate-pulse" />
            {activeCount} {t('subAgents.live')}
          </span>
        )}
      </div>
      {stopError && (
        <p role="alert" className="text-xs text-red-600 p-2">
          {t('backgroundTasks.stopFailed')}
        </p>
      )}
      <div className="flex-1 overflow-y-auto scrollbar-thin p-2 space-y-1 min-h-0">
        {tasks.map((task) => {
          const isActive = isSubAgentActive(task.status);
          const duration = formatDuration(task.started_at, task.finished_at);
          const hasWorktree = task.isolation === 'worktree';

          return (
            <div
              key={task.task_id}
              role="button"
              tabIndex={0}
              onClick={() => onSelect(task.task_id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onSelect(task.task_id);
                }
              }}
              className={`w-full text-left px-2 py-2 rounded-sm border-2 transition-colors cursor-pointer group ${
                isActive
                  ? 'bg-white dark:bg-zinc-800 border-brutal-blue'
                  : 'bg-neutral-50 dark:bg-zinc-800 border-neutral-200 dark:border-zinc-600 hover:border-brutal-black dark:hover:border-white'
              }`}
            >
              <div className="flex items-start gap-2">
                {task.kind === 'shell' ? (
                  <CommandLineIcon className="w-6 h-6 shrink-0 text-neutral-500" />
                ) : (
                  <AgentAvatar model={task.model_override} status={task.status} />
                )}
                <div className="flex-1 min-w-0">
                  {/* What this agent was sent to do -- its name, in effect. */}
                  <div className="text-[11px] font-bold text-neutral-800 dark:text-neutral-100 leading-snug line-clamp-2 group-hover:text-neutral-900 dark:group-hover:text-white">
                    {task.description}
                  </div>

                  {/* One quiet line of provenance: who ran it, and for how
                      long. The model belongs up here beside the agent rather
                      than trailing the card as an afterthought. */}
                  {(task.model_override || task.kind === 'shell') && (
                    <div
                      className="mt-0.5 text-[9px] text-neutral-500 dark:text-neutral-400 truncate"
                      title={
                        task.kind === 'shell'
                          ? t('backgroundTasks.shell')
                          : `${t('subAgents.model')}: ${task.model_override}`
                      }
                    >
                      {task.kind === 'shell' ? t('backgroundTasks.shell') : task.model_override}
                    </div>
                  )}

                  {/* Meta row: status + time + stop button */}
                  <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                    <SubAgentStatusBadge status={task.status} t={t} />
                    {isActive && (
                      <button
                        onKeyDown={(e) => e.stopPropagation()}
                        onClick={(e) => {
                          e.stopPropagation();
                          setStopping((s) => new Set(s).add(task.task_id));
                          setStopError(false);
                          stopBackgroundTask(task.task_id)
                            .catch(() => setStopError(true))
                            .finally(() =>
                              setStopping((s) => {
                                const n = new Set(s);
                                n.delete(task.task_id);
                                return n;
                              })
                            );
                        }}
                        disabled={stopping.has(task.task_id)}
                        className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-sm border border-transparent text-red-600 dark:text-red-400 hover:border-red-200 dark:hover:border-red-800 hover:bg-red-50 dark:hover:bg-red-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 disabled:opacity-50 disabled:cursor-wait transition-colors"
                        type="button"
                        title={t(
                          stopping.has(task.task_id) ? 'subAgents.stopping' : 'subAgents.stop'
                        )}
                        aria-label={t(
                          stopping.has(task.task_id) ? 'subAgents.stopping' : 'subAgents.stop'
                        )}
                        aria-busy={stopping.has(task.task_id)}
                      >
                        {stopping.has(task.task_id) ? (
                          <ArrowPathIcon className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                        ) : (
                          <StopIcon className="h-3.5 w-3.5" aria-hidden="true" />
                        )}
                      </button>
                    )}

                    {task.started_at && (
                      <span className="text-[9px] text-neutral-400">
                        {new Date(task.started_at).toLocaleTimeString()}
                      </span>
                    )}

                    {duration && !isActive && (
                      <span className="text-[9px] text-neutral-400">{duration}</span>
                    )}
                  </div>

                  {/* What it was allowed to do. Named, not counted: "1 tools"
                      says nothing about the agent, "RunCommand" says what it
                      is for. */}
                  {task.tools_allowed.length > 0 && (
                    <div className="flex items-center gap-1 mt-1 flex-wrap">
                      {task.tools_allowed.slice(0, 3).map((tool) => (
                        <span
                          key={tool}
                          className="text-[9px] px-1 py-px bg-neutral-100 dark:bg-zinc-900 border border-neutral-300 dark:border-zinc-600 text-neutral-600 dark:text-neutral-300 rounded-sm truncate max-w-[7.5rem]"
                          title={tool}
                        >
                          {toolLabel(tool)}
                        </span>
                      ))}
                      {task.tools_allowed.length > 3 && (
                        <span className="text-[9px] text-neutral-400">
                          +{task.tools_allowed.length - 3}
                        </span>
                      )}
                    </div>
                  )}

                  {/* Why a stopped or failed run ended, right on the row. */}
                  {!isActive && task.status !== 'completed' && task.error && (
                    <div
                      className={`mt-1 text-[10px] leading-snug line-clamp-2 ${
                        task.status === 'failed'
                          ? 'text-red-600 dark:text-red-400'
                          : 'text-neutral-500 dark:text-neutral-400'
                      }`}
                    >
                      {task.error}
                    </div>
                  )}

                  {/* Context / Isolation badges */}
                  {(task.inherit_context || hasWorktree) && (
                    <div className="flex items-center gap-1 mt-1 flex-wrap">
                      {task.inherit_context && (
                        <span className="text-[9px] px-1 py-px bg-white dark:bg-zinc-900 border-2 border-neutral-400 dark:border-zinc-500 text-neutral-600 dark:text-neutral-300 rounded-sm font-bold uppercase tracking-wide">
                          {t('subAgents.contextForked')}
                        </span>
                      )}
                      {hasWorktree && (
                        <span className="text-[9px] px-1 py-px bg-white dark:bg-zinc-900 border-2 border-neutral-400 dark:border-zinc-500 text-neutral-600 dark:text-neutral-300 rounded-sm font-bold uppercase tracking-wide truncate max-w-full">
                          {task.worktree_branch ?? t('subAgents.worktree')}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
