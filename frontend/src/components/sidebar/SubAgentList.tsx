/**
 * SubAgentList — shows all sub-agents spawned in the current session.
 * Fetches history from /subagents once on mount, then overlays live state
 * from the shared useSubAgentStatus EventSource hook.
 */
import React, { useEffect, useRef, useState } from 'react';
import { getApiBase } from '../../lib/api';
import { useSubAgentStatus, SubAgentSummary } from '../../hooks/useSubAgentStatus';

interface SubAgentListProps {
  chatId: string;
  onSelect: (taskId: string) => void;
}

// Extend SubAgentSummary locally with Phase 2/3 fields that come from the API
// but are not yet in the shared type.
interface SubAgentRow extends SubAgentSummary {
  finished_at?: string | null;
  inherit_context?: boolean;
  isolation?: string;
  worktree_branch?: string | null;
}

const STATUS_BADGE: Record<string, string> = {
  running:   'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  queued:    'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300',
  completed: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
  failed:    'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
};

const STATUS_ICON: Record<string, string> = {
  running:   '🤖',
  queued:    '⏳',
  completed: '✅',
  failed:    '❌',
};

function formatDuration(startedAt: string | null | undefined, finishedAt: string | null | undefined): string {
  if (!startedAt) return '';
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const ms = end - new Date(startedAt).getTime();
  if (ms < 0) return '';
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

export const SubAgentList: React.FC<SubAgentListProps> = ({ chatId, onSelect }) => {
  const [historicTasks, setHistoricTasks] = useState<SubAgentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const { activeTasks } = useSubAgentStatus();
  const knownActiveIdsRef = useRef<Set<string>>(new Set());

  const fetchTasks = (chatId: string) =>
    fetch(`${getApiBase()}/subagents?parent_chat_id=${encodeURIComponent(chatId)}`)
      .then(r => r.json())
      .then(d => setHistoricTasks(d.tasks ?? []))
      .catch(() => {});

  useEffect(() => {
    setLoading(true);
    knownActiveIdsRef.current = new Set();
    fetchTasks(chatId).finally(() => setLoading(false));
  }, [chatId]);

  useEffect(() => {
    const newIds = activeTasks
      .filter(t => t.parent_chat_id === chatId)
      .map(t => t.task_id)
      .filter(id => !knownActiveIdsRef.current.has(id));
    if (newIds.length > 0) {
      newIds.forEach(id => knownActiveIdsRef.current.add(id));
      fetchTasks(chatId);
    }
  }, [activeTasks, chatId]);

  const chatActiveTasks = activeTasks.filter(t => t.parent_chat_id === chatId) as SubAgentRow[];
  const activeIds = new Set(chatActiveTasks.map(t => t.task_id));
  const tasks: SubAgentRow[] = [
    ...chatActiveTasks,
    ...historicTasks.filter(t => !activeIds.has(t.task_id)),
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-400 animate-pulse">
        Loading...
      </div>
    );
  }

  if (tasks.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-400">
        No sub-agents in this session
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0 font-mono">
      <div className="px-3 py-2 border-b-3 border-brutal-black bg-white dark:bg-zinc-800 shrink-0">
        <span className="text-[10px] font-bold uppercase tracking-widest font-mono text-neutral-500 dark:text-neutral-400">
          Sub-agents ({tasks.length})
        </span>
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin p-2 space-y-1 min-h-0">
        {tasks.map((task) => {
          const isActive = task.status === 'running' || task.status === 'queued';
          const duration = formatDuration(task.started_at, task.finished_at);
          const hasWorktree = task.isolation === 'worktree';
          const hasContext = task.inherit_context;

          return (
            <button
              key={task.task_id}
              onClick={() => onSelect(task.task_id)}
              className="w-full text-left px-2 py-2 rounded-sm bg-neutral-50 dark:bg-zinc-800 hover:bg-neutral-100 dark:hover:bg-zinc-700 border border-neutral-200 dark:border-zinc-600 transition-colors group"
            >
              <div className="flex items-start gap-2">
                <span className="text-[11px] shrink-0 mt-0.5">
                  {STATUS_ICON[task.status] ?? '🤖'}
                </span>
                <div className="flex-1 min-w-0">
                  {/* Description */}
                  <div className="text-[11px] text-neutral-700 dark:text-neutral-200 leading-snug line-clamp-2 group-hover:text-neutral-900 dark:group-hover:text-white">
                    {task.description}
                  </div>

                  {/* Meta row: status + time + tool count */}
                  <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                    <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-sm ${STATUS_BADGE[task.status] ?? ''}`}>
                      {task.status}
                      {isActive && (
                        <span className="inline-block w-1 h-1 rounded-full bg-current ml-1 animate-pulse" />
                      )}
                    </span>

                    {task.started_at && (
                      <span className="text-[9px] text-neutral-400">
                        {new Date(task.started_at).toLocaleTimeString()}
                      </span>
                    )}

                    {duration && !isActive && (
                      <span className="text-[9px] text-neutral-400">⏱ {duration}</span>
                    )}

                    {task.tools_allowed.length > 0 && (
                      <span className="text-[9px] text-neutral-400">
                        🔧 {task.tools_allowed.length}
                      </span>
                    )}
                  </div>

                  {/* Context / Isolation badges */}
                  {(hasContext || hasWorktree) && (
                    <div className="flex items-center gap-1 mt-1 flex-wrap">
                      {hasContext && (
                        <span className="text-[9px] px-1 py-px bg-purple-50 dark:bg-purple-950 border border-purple-200 dark:border-purple-800 text-purple-600 dark:text-purple-400 rounded-sm font-bold uppercase">
                          forked
                        </span>
                      )}
                      {hasWorktree && (
                        <span className="text-[9px] px-1 py-px bg-orange-50 dark:bg-orange-950 border border-orange-200 dark:border-orange-800 text-orange-600 dark:text-orange-400 rounded-sm font-bold uppercase">
                          {task.worktree_branch ?? 'worktree'}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
