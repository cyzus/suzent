/**
 * SubAgentList — shows all sub-agents spawned in the current session.
 * Fetches /subagents?parent_chat_id=... on mount and on a short poll while
 * any task is still running/queued.
 */
import React, { useEffect, useRef, useState } from 'react';
import { getApiBase } from '../../lib/api';

interface SubAgentSummary {
  task_id: string;
  description: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  started_at: string | null;
  finished_at: string | null;
}

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
  const [tasks, setTasks] = useState<SubAgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchTasks = async () => {
    try {
      const res = await fetch(`${getApiBase()}/subagents?parent_chat_id=${encodeURIComponent(chatId)}`);
      if (!res.ok) return;
      const data = await res.json();
      setTasks(data.tasks ?? []);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    fetchTasks();

    intervalRef.current = setInterval(() => {
      fetchTasks();
    }, 3000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [chatId]);

  // Stop polling once all tasks are terminal
  useEffect(() => {
    const allDone = tasks.length > 0 && tasks.every(
      (t) => t.status === 'completed' || t.status === 'failed',
    );
    if (allDone && intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, [tasks]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-[11px] text-neutral-400 font-mono animate-pulse">
        Loading...
      </div>
    );
  }

  if (tasks.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-[11px] text-neutral-400 font-mono">
        No sub-agents in this session
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0 font-mono">
      <div className="px-3 py-2 border-b border-neutral-200 dark:border-zinc-700 shrink-0">
        <span className="text-[10px] font-bold uppercase text-neutral-500 dark:text-neutral-400">
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
