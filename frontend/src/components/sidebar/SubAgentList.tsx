/**
 * SubAgentList — every sub-agent spawned in the current session.
 *
 * History comes from /subagents; live state is overlaid from the shared
 * useSubAgentStatus EventSource. The overlay now includes the terminal update,
 * so a run that finishes flips to DONE/STOPPED in place instead of sitting on a
 * stale "running" row until someone reopened the panel.
 */
import React, { useEffect, useRef, useState } from 'react';
import { getApiBase } from '../../lib/api';
import { useSubAgentStatus, SubAgentSummary } from '../../hooks/useSubAgentStatus';
import { isSubAgentActive, SubAgentStatusBadge } from '../chat/subAgentStatus';
import { getProviderInitials, getProviderVisualForModel } from '../../lib/providerVisuals';
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

/**
 * Tools are registered under class-style names (`RunCommandTool`); the suffix
 * is noise on a chip. Naming what an agent can actually do reads as capability,
 * where a bare "1 tools" only reads as a row in a ledger.
 */
function toolLabel(name: string): string {
  return name.replace(/Tool$/, '');
}

/**
 * Identity tile. The provider's own colour with its initials -- deliberately
 * not its logo: those are remote CDN URLs and the desktop app's CSP blocks
 * off-origin images, so a logo here would render as a silent blank.
 */
const AgentAvatar: React.FC<{ model?: string | null; status?: string }> = ({ model, status }) => {
  const visual = getProviderVisualForModel(model ?? undefined);
  const background = visual ? `#${visual.color}` : '#525252';
  const initials = visual ? getProviderInitials(visual.label) : 'AI';
  const active = isSubAgentActive(status);

  return (
    <div className="relative shrink-0">
      <div
        className="w-7 h-7 flex items-center justify-center border-2 border-brutal-black dark:border-white rounded-sm text-[9px] font-bold tracking-tight text-white"
        style={{ backgroundColor: background }}
        aria-hidden="true"
      >
        {initials}
      </div>
      {/* Presence, the way a roster shows it -- additive to the status badge
          below, which stays the shared vocabulary across every surface. */}
      <span
        className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-white dark:border-zinc-800 ${
          active ? 'bg-brutal-blue animate-pulse' : 'bg-neutral-300 dark:bg-zinc-600'
        }`}
      />
    </div>
  );
};

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

  const activeCount = tasks.filter((task) => isSubAgentActive(task.status)).length;

  return (
    <div className="flex flex-col h-full min-h-0 font-mono">
      <div className="px-3 py-2 border-b-3 border-brutal-black bg-white dark:bg-zinc-800 shrink-0">
        <span className="text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-500 dark:text-neutral-400">
          {t('subAgents.heading', { count: tasks.length })}
        </span>
        {activeCount > 0 && (
          <span className="ml-2 inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest font-mono text-brutal-blue">
            <span className="w-1.5 h-1.5 rounded-full bg-brutal-blue animate-pulse" />
            {activeCount} {t('subAgents.live')}
          </span>
        )}
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
              className={`w-full text-left px-2 py-2 rounded-sm border-2 transition-colors cursor-pointer group ${
                isActive
                  ? 'bg-white dark:bg-zinc-800 border-brutal-blue'
                  : 'bg-neutral-50 dark:bg-zinc-800 border-neutral-200 dark:border-zinc-600 hover:border-brutal-black dark:hover:border-white'
              }`}
            >
              <div className="flex items-start gap-2">
                <AgentAvatar model={task.model_override} status={task.status} />
                <div className="flex-1 min-w-0">
                  {/* What this agent was sent to do -- its name, in effect. */}
                  <div className="text-[11px] font-bold text-neutral-800 dark:text-neutral-100 leading-snug line-clamp-2 group-hover:text-neutral-900 dark:group-hover:text-white">
                    {task.description}
                  </div>

                  {/* One quiet line of provenance: who ran it, and for how
                      long. The model belongs up here beside the agent rather
                      than trailing the card as an afterthought. */}
                  {task.model_override && (
                    <div
                      className="mt-0.5 text-[9px] text-neutral-500 dark:text-neutral-400 truncate"
                      title={`${t('subAgents.model')}: ${task.model_override}`}
                    >
                      {task.model_override}
                    </div>
                  )}

                  {/* Meta row: status + time + stop button */}
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
