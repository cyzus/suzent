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

const STATUS_BADGE: Record<string, string> = {
  running:   'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  queued:    'bg-amber-100 text-amber-700',
  completed: 'bg-green-100 text-green-700',
  failed:    'bg-red-100 text-red-700',
};

const STATUS_ICON: Record<string, string> = {
  running:   '🤖',
  queued:    '⏳',
  completed: '✅',
  failed:    '❌',
};

export const SubAgentList: React.FC<SubAgentListProps> = ({ chatId, onSelect }) => {
  const [historicTasks, setHistoricTasks] = useState<SubAgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const { activeTasks } = useSubAgentStatus();
  const knownActiveIdsRef = useRef<Set<string>>(new Set());

  const fetchTasks = (chatId: string) =>
    fetch(`${getApiBase()}/subagents?parent_chat_id=${encodeURIComponent(chatId)}`)
      .then(r => r.json())
      .then(d => setHistoricTasks(d.tasks ?? []))
      .catch(() => {});

  // Initial fetch on mount / chat switch.
  useEffect(() => {
    setLoading(true);
    knownActiveIdsRef.current = new Set();
    fetchTasks(chatId).finally(() => setLoading(false));
  }, [chatId]);

  // Re-fetch when EventSource delivers new tasks for this chat that we haven't seen yet.
  // This catches cases where the initial fetch ran before the sub-agent was spawned.
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

  // Merge: active tasks from SSE override historic tasks by task_id.
  const chatActiveTasks = activeTasks.filter(t => t.parent_chat_id === chatId);
  const activeIds = new Set(chatActiveTasks.map(t => t.task_id));
  const tasks = [
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
        {tasks.map((task) => (
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
                <div className="text-[11px] text-neutral-700 dark:text-neutral-200 leading-snug line-clamp-2 group-hover:text-neutral-900 dark:group-hover:text-white">
                  {task.description}
                </div>
                <div className="flex items-center gap-1.5 mt-1">
                  <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-sm ${STATUS_BADGE[task.status] ?? ''}`}>
                    {task.status}
                    {(task.status === 'running' || task.status === 'queued') && (
                      <span className="inline-block w-1 h-1 rounded-full bg-current ml-1 animate-pulse" />
                    )}
                  </span>
                  {task.started_at && (
                    <span className="text-[9px] text-neutral-400">
                      {new Date(task.started_at).toLocaleTimeString()}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
};
