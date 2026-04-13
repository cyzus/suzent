/**
 * SubAgentView — sidebar panel showing a sub-agent's execution status and log.
 * Polls /subagents/{task_id} for status, and /chats/{chat_id} for tool call log.
 */
import React, { useEffect, useState, useRef, useCallback } from 'react';
import { getApiBase } from '../../lib/api';

interface SubAgentTask {
  task_id: string;
  parent_chat_id: string;
  chat_id: string;
  description: string;
  tools_allowed: string[];
  status: 'queued' | 'running' | 'completed' | 'failed';
  result_summary: string | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

interface ToolLogEntry {
  toolName: string;
  args: string;
  output?: string;
}

interface SubAgentViewProps {
  taskId: string;
  onClose?: () => void;
}

function elapsed(startedAt: string | null): string {
  if (!startedAt) return '';
  const ms = Date.now() - new Date(startedAt).getTime();
  if (ms < 0) return '';
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

/** Parse tool call log from /chats/{chatId} messages */
function extractToolLog(messages: any[]): ToolLogEntry[] {
  const entries: ToolLogEntry[] = [];
  const outputs: Record<string, string> = {};

  for (const msg of messages) {
    if (msg.role === 'tool' && msg.tool_call_id) {
      outputs[msg.tool_call_id] = msg.content ?? '';
    }
  }
  for (const msg of messages) {
    if (msg.role === 'assistant' && Array.isArray(msg.tool_calls)) {
      for (const tc of msg.tool_calls) {
        entries.push({
          toolName: tc.function?.name ?? 'unknown',
          args: tc.function?.arguments ?? '',
          output: outputs[tc.id],
        });
      }
    }
  }
  return entries;
}

export const SubAgentView: React.FC<SubAgentViewProps> = ({ taskId, onClose }) => {
  const [task, setTask] = useState<SubAgentTask | null>(null);
  const [toolLog, setToolLog] = useState<ToolLogEntry[]>([]);
  const [elapsedTime, setElapsedTime] = useState('');
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const elapsedRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const taskRef = useRef<SubAgentTask | null>(null);

  const fetchChatLog = useCallback(async (chatId: string) => {
    try {
      const res = await fetch(`${getApiBase()}/chats/${chatId}`);
      if (!res.ok) return;
      const data = await res.json();
      const entries = extractToolLog(data.messages ?? []);
      if (entries.length > 0) setToolLog(entries);
    } catch { /* ignore */ }
  }, []);

  const fetchTask = useCallback(async () => {
    try {
      const res = await fetch(`${getApiBase()}/subagents/${taskId}`);
      if (!res.ok) return;
      const data = await res.json();
      const t: SubAgentTask = data.task;
      setTask(t);
      taskRef.current = t;
      // Always fetch the tool log — shows live progress while running and final result when done
      if (t.chat_id) {
        fetchChatLog(t.chat_id);
      }
    } catch { /* ignore */ }
  }, [taskId, fetchChatLog]);

  const stopAgent = async () => {
    try {
      await fetch(`${getApiBase()}/subagents/${taskId}/stop`, { method: 'POST' });
      fetchTask();
    } catch { /* ignore */ }
  };

  useEffect(() => {
    setTask(null);
    setToolLog([]);
    taskRef.current = null;

    fetchTask();

    intervalRef.current = setInterval(() => {
      const current = taskRef.current;
      if (current?.status === 'completed' || current?.status === 'failed') {
        if (intervalRef.current) clearInterval(intervalRef.current);
        intervalRef.current = null;
        return;
      }
      fetchTask();
    }, 2000);

    elapsedRef.current = setInterval(() => {
      const current = taskRef.current;
      if (current?.started_at) {
        setElapsedTime(elapsed(current.started_at));
      }
    }, 1000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (elapsedRef.current) clearInterval(elapsedRef.current);
    };
  }, [taskId]);

  // Stop polling when task finishes
  useEffect(() => {
    if ((task?.status === 'completed' || task?.status === 'failed') && intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (task?.started_at) {
      setElapsedTime(elapsed(task.started_at));
    }
  }, [task?.status]);

  const isRunning = task?.status === 'running' || task?.status === 'queued';

  return (
        <div className="flex flex-col h-full min-h-0 font-mono">
      {/* Header */}
      <div className="flex items-start justify-between px-3 py-2 border-b-3 border-brutal-black bg-white dark:bg-zinc-800 shrink-0 gap-2">
        <div className="flex items-start gap-2 min-w-0 pt-0.5">
          <span className="text-[14px] drop-shadow-sm leading-none shrink-0 mt-0.5">
            {task?.status === 'completed' ? '✅' : task?.status === 'failed' ? '❌' : '🤖'}
          </span>
          <div className="min-w-0">
            <div className="text-[10px] font-bold uppercase tracking-widest font-mono truncate flex items-center gap-1.5 text-neutral-600 dark:text-neutral-300">
              <span>Sub-agent</span>
              <span className="opacity-70 normal-case tracking-normal truncate">{task?.task_id ?? taskId}</span>
              {isRunning && (
                <span className="text-[9px] leading-none px-1 py-[2px] border border-brutal-black bg-brutal-yellow text-brutal-black font-bold uppercase tracking-normal">
                  Live
                </span>
              )}
            </div>
            <div className="text-[12px] font-bold text-brutal-black dark:text-white leading-snug mt-0.5 max-h-[2.5rem] overflow-hidden line-clamp-2">
              {task?.description || 'Loading task...'}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 self-start mt-0.5">
          {isRunning && elapsedTime && (
            <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">⏱ {elapsedTime}</span>
          )}
          {isRunning && (
            <button
              onClick={stopAgent}
              className="px-2 py-1 text-[10px] leading-none font-bold uppercase bg-red-50 text-red-700 border-2 border-red-400 hover:bg-red-100 transition-colors"
            >
              Stop
            </button>
          )}
          {onClose && (
            <button
              onClick={onClose}
              className="p-1 aspect-square flex items-center justify-center text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 transition-colors"
              title="Close"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto scrollbar-thin p-3 space-y-3 min-h-0">
        {!task && (
          <div className="text-[11px] text-neutral-400 animate-pulse">Loading...</div>
        )}

        {task && (
          <>
            {/* Task description */}
            <div>
              <div className="text-[10px] font-bold uppercase text-neutral-400 dark:text-neutral-500 mb-0.5">Task</div>
              <div className="text-[11px] text-neutral-700 dark:text-neutral-300 leading-relaxed">
                {task.description}
              </div>
            </div>

            {/* Tools */}
            {task.tools_allowed.length > 0 && (
              <div>
                <div className="text-[10px] font-bold uppercase text-neutral-400 dark:text-neutral-500 mb-1">Tools</div>
                <div className="flex flex-wrap gap-1">
                  {task.tools_allowed.map((t) => (
                    <span key={t} className="text-[10px] px-1.5 py-0.5 bg-neutral-100 dark:bg-zinc-700 rounded-sm border border-neutral-200 dark:border-zinc-600 text-neutral-600 dark:text-neutral-300">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Status */}
            <div>
              <div className="text-[10px] font-bold uppercase text-neutral-400 dark:text-neutral-500 mb-0.5">Status</div>
              <div className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded-sm
                ${task.status === 'running' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300' :
                  task.status === 'queued' ? 'bg-amber-100 text-amber-700' :
                  task.status === 'completed' ? 'bg-green-100 text-green-700' :
                  'bg-red-100 text-red-700'}`
              }>
                {task.status}
                {isRunning && (
                  <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                )}
              </div>
              {task.started_at && (
                <div className="mt-1 text-[10px] text-neutral-400">
                  Started: {new Date(task.started_at).toLocaleTimeString()}
                  {task.finished_at && ` → ${new Date(task.finished_at).toLocaleTimeString()}`}
                </div>
              )}
            </div>

            {/* Tool call log */}
            {toolLog.length > 0 && (
              <div>
                <div className="text-[10px] font-bold uppercase text-neutral-400 dark:text-neutral-500 mb-1">
                  Tool Calls ({toolLog.length})
                </div>
                <div className="space-y-1">
                  {toolLog.map((entry, i) => (
                    <details key={i} className="text-[10px] group">
                      <summary className="flex items-center gap-1.5 cursor-pointer list-none select-none py-0.5 px-1 rounded-sm bg-neutral-50 dark:bg-zinc-800 hover:bg-neutral-100 dark:hover:bg-zinc-700">
                        <span className="text-neutral-400">🔧</span>
                        <span className="font-bold text-neutral-700 dark:text-neutral-200 truncate">{entry.toolName}</span>
                        {entry.output !== undefined && (
                          <span className="text-green-600 dark:text-green-400 ml-auto shrink-0">✓</span>
                        )}
                      </summary>
                      <div className="mt-1 pl-2 border-l-2 border-neutral-200 dark:border-zinc-600 space-y-1">
                        {entry.args && (
                          <pre className="text-[10px] text-neutral-500 dark:text-neutral-400 whitespace-pre-wrap break-all">
                            {entry.args.length > 200 ? entry.args.slice(0, 200) + '…' : entry.args}
                          </pre>
                        )}
                        {entry.output !== undefined && (
                          <pre className="text-[10px] text-neutral-600 dark:text-neutral-300 whitespace-pre-wrap break-all bg-neutral-50 dark:bg-zinc-800 p-1 rounded-sm">
                            {entry.output.length > 300 ? entry.output.slice(0, 300) + '…' : entry.output}
                          </pre>
                        )}
                      </div>
                    </details>
                  ))}
                </div>
              </div>
            )}

            {/* Result */}
            {task.status === 'completed' && task.result_summary && (
              <div>
                <div className="text-[10px] font-bold uppercase text-neutral-400 dark:text-neutral-500 mb-0.5">Result</div>
                <pre className="text-[11px] text-neutral-700 dark:text-neutral-300 leading-relaxed whitespace-pre-wrap bg-neutral-50 dark:bg-zinc-800 p-2 rounded-sm border border-neutral-200 dark:border-zinc-600 max-h-[300px] overflow-y-auto scrollbar-thin">
                  {task.result_summary}
                </pre>
              </div>
            )}

            {/* Error */}
            {task.status === 'failed' && task.error && (
              <div>
                <div className="text-[10px] font-bold uppercase text-red-400 mb-0.5">Error</div>
                <pre className="text-[11px] text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950 p-2 rounded-sm border border-red-200 dark:border-red-900 whitespace-pre-wrap max-h-[200px] overflow-y-auto scrollbar-thin">
                  {task.error}
                </pre>
              </div>
            )}

            {/* Running indicator */}
            {isRunning && (
              <div className="flex items-center gap-2 text-[10px] text-neutral-400 animate-pulse">
                <div className="h-[2px] flex-1 bg-neutral-100 dark:bg-zinc-700 overflow-hidden rounded-full">
                  <div className="h-full bg-blue-500 w-1/3 animate-neo-scan" />
                </div>
                <span>Executing...</span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};
