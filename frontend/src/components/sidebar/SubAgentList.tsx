/**
 * SubAgentList — every sub-agent spawned in the current session.
 *
 * History comes from /subagents; live state is overlaid from the shared
 * useSubAgentStatus EventSource. The overlay now includes the terminal update,
 * so a run that finishes flips to DONE/STOPPED in place instead of sitting on a
 * stale "running" row until someone reopened the panel.
 */
import React, { useEffect, useRef, useState } from 'react';
import { CpuChipIcon } from '@heroicons/react/24/outline';
import { getApiBase } from '../../lib/api';
import { useSubAgentStatus, SubAgentSummary } from '../../hooks/useSubAgentStatus';
import { isSubAgentActive, SubAgentStatusBadge, SubAgentStatusIcon } from '../chat/subAgentStatus';
import { useI18n } from '../../i18n';

interface SubAgentListProps {
  chatId: string;
  onSelect: (taskId: string) => void;
}

type SubAgentRow = SubAgentSummary;

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
function sortRows(rows: SubAgentRow[]): SubAgentRow[] {
  return [...rows].sort((a, b) => {
    const activeDelta = Number(isSubAgentActive(b.status)) - Number(isSubAgentActive(a.status));
    if (activeDelta !== 0) return activeDelta;
    const key = (r: SubAgentRow) => r.finished_at || r.started_at || '';
    return key(b).localeCompare(key(a));
  });
}

async function stopSubAgent(taskId: string): Promise<void> {
  await fetch(`${getApiBase()}/subagents/${encodeURIComponent(taskId)}/stop`, { method: 'POST' });
}

export const SubAgentList: React.FC<SubAgentListProps> = ({ chatId, onSelect }) => {
  const { t } = useI18n();
  const [historicTasks, setHistoricTasks] = useState<SubAgentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [stopping, setStopping] = useState<Set<string>>(new Set());
  const { taskStates } = useSubAgentStatus();
  const lastSignatureRef = useRef('');

  const fetchTasks = (chatId: string) =>
    fetch(`${getApiBase()}/subagents?parent_chat_id=${encodeURIComponent(chatId)}`)
      .then((r) => r.json())
      .then((d) => setHistoricTasks(d.tasks ?? []))
      .catch(() => {});

  useEffect(() => {
    setLoading(true);
    lastSignatureRef.current = '';
    fetchTasks(chatId).finally(() => setLoading(false));
  }, [chatId]);

  const liveTasks = Object.values(taskStates).filter((task) => task.parent_chat_id === chatId);

  // Refetch whenever a task appears or changes state, so persisted-only fields
  // (worktree branch, result summary) catch up with the live overlay.
  const signature = liveTasks
    .map((task) => `${task.task_id}:${task.status}`)
    .sort()
    .join('|');
  useEffect(() => {
    if (!signature || signature === lastSignatureRef.current) return;
    lastSignatureRef.current = signature;
    fetchTasks(chatId);
  }, [signature, chatId]);

  const liveById = new Map(liveTasks.map((task) => [task.task_id, task]));
  const merged = [
    ...liveTasks.map((task) => ({
      ...historicTasks.find((h) => h.task_id === task.task_id),
      ...task,
    })),
    ...historicTasks.filter((task) => !liveById.has(task.task_id)),
  ];
  const tasks = sortRows(merged as SubAgentRow[]);

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
        {t('subAgents.empty')}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0 font-mono">
      <div className="px-3 py-2 border-b-3 border-brutal-black bg-white dark:bg-zinc-800 shrink-0">
        <span className="text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-500 dark:text-neutral-400">
          {t('subAgents.heading', { count: tasks.length })}
        </span>
      </div>
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
              className="w-full text-left px-2 py-2 rounded-sm bg-neutral-50 dark:bg-zinc-800 border-2 border-neutral-200 dark:border-zinc-600 hover:border-brutal-black dark:hover:border-white transition-colors cursor-pointer group"
            >
              <div className="flex items-start gap-2">
                <SubAgentStatusIcon status={task.status} className="w-3.5 h-3.5 mt-0.5" />
                <div className="flex-1 min-w-0">
                  {/* Description */}
                  <div className="text-[11px] text-neutral-700 dark:text-neutral-200 leading-snug line-clamp-2 group-hover:text-neutral-900 dark:group-hover:text-white">
                    {task.description}
                  </div>

                  {/* Meta row: status + time + tool count + stop button */}
                  <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                    <SubAgentStatusBadge status={task.status} t={t} />
                    {isActive && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setStopping((s) => new Set(s).add(task.task_id));
                          stopSubAgent(task.task_id).finally(() =>
                            setStopping((s) => {
                              const n = new Set(s);
                              n.delete(task.task_id);
                              return n;
                            })
                          );
                        }}
                        disabled={stopping.has(task.task_id)}
                        className="text-[9px] font-bold uppercase tracking-wide px-1.5 py-px border-2 border-red-600 bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-300 rounded-sm hover:bg-red-100 dark:hover:bg-red-900 disabled:opacity-50 transition-colors"
                        title={t('subAgents.stop')}
                      >
                        {stopping.has(task.task_id) ? t('subAgents.stopping') : t('subAgents.stop')}
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

                    {task.tools_allowed.length > 0 && (
                      <span className="inline-flex items-center gap-1 text-[9px] text-neutral-400">
                        <CpuChipIcon className="w-2.5 h-2.5" />
                        {t('subAgents.toolCount', { count: task.tools_allowed.length })}
                      </span>
                    )}
                  </div>

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

                  {task.model_override && (
                    <div className="mt-1">
                      <span
                        className="inline-block text-[9px] text-neutral-400 dark:text-neutral-500 truncate max-w-full font-mono"
                        title={`${t('subAgents.model')}: ${task.model_override}`}
                      >
                        {task.model_override}
                      </span>
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
