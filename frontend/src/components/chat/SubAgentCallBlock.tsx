/**
 * SubAgentCallBlock — renders a spawn_subagent tool call as a special card
 * showing live status, description, allowed tools, and a sidebar open button.
 */
import React, { useState, useEffect, useRef } from 'react';
import { getApiBase } from '../../lib/api';

export type SubAgentStatus = 'queued' | 'running' | 'completed' | 'failed';

interface SubAgentCallBlockProps {
  taskId?: string;
  description?: string;
  toolsAllowed?: string[];
  status: SubAgentStatus;
  resultSummary?: string;
  error?: string;
  /** Called when user clicks "View in sidebar" */
  onOpenSidebar?: (taskId: string) => void;
  /** Called when user clicks "Stop" */
  onStop?: (taskId: string) => void;
}

const STATUS_ICON: Record<SubAgentStatus, string> = {
  queued: '⏳',
  running: '🤖',
  completed: '✅',
  failed: '❌',
};

const STATUS_LABEL: Record<SubAgentStatus, string> = {
  queued: 'QUEUED',
  running: 'RUNNING',
  completed: 'DONE',
  failed: 'FAILED',
};

export const SubAgentCallBlock: React.FC<SubAgentCallBlockProps> = ({
  taskId,
  description,
  toolsAllowed,
  status: externalStatus,
  resultSummary: externalResultSummary,
  error: externalError,
  onOpenSidebar,
  onStop,
}) => {
  // Self-poll to get real status when the parent SSE stream may have ended before completion
  const [polledStatus, setPolledStatus] = useState<SubAgentStatus | null>(null);
  const [polledResultSummary, setPolledResultSummary] = useState<string | undefined>(undefined);
  const [polledError, setPolledError] = useState<string | undefined>(undefined);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Use a ref so the poll callback always sees the latest resolved status without
  // being captured in a stale closure — avoids polling when already done.
  const resolvedStatusRef = useRef<SubAgentStatus>(externalStatus);

  const status = polledStatus ?? externalStatus;
  const resultSummary = polledResultSummary ?? externalResultSummary;
  const error = polledError ?? externalError;

  // Keep ref in sync on every render
  resolvedStatusRef.current = status;

  useEffect(() => {
    if (!taskId) return;
    // Already terminal — no need to poll
    if (resolvedStatusRef.current === 'completed' || resolvedStatusRef.current === 'failed') return;

    const poll = async () => {
      // Stop polling if status was resolved externally while waiting
      if (resolvedStatusRef.current === 'completed' || resolvedStatusRef.current === 'failed') {
        if (timerRef.current) clearInterval(timerRef.current);
        return;
      }
      try {
        const res = await fetch(`${getApiBase()}/subagents/${taskId}`);
        if (!res.ok) return;
        const data = await res.json();
        const t = data.task;
        if (t) {
          setPolledStatus(t.status);
          if (t.result_summary) setPolledResultSummary(t.result_summary);
          if (t.error) setPolledError(t.error);
          if (t.status === 'completed' || t.status === 'failed') {
            if (timerRef.current) clearInterval(timerRef.current);
          }
        }
      } catch { /* ignore */ }
    };

    poll();
    timerRef.current = setInterval(poll, 3000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [taskId]);

  // Stop polling immediately when external status resolves (SSE arrived)
  useEffect(() => {
    if ((externalStatus === 'completed' || externalStatus === 'failed') && timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, [externalStatus]);

  const [expanded, setExpanded] = useState(true);
  // Auto-collapse when completed
  useEffect(() => {
    if (status === 'completed') setExpanded(false);
  }, [status]);

  const isRunning = status === 'running' || status === 'queued';

  return (
    <div className="my-2 min-w-0 w-full">
      {/* Pill header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-mono font-bold uppercase tracking-wide rounded-sm cursor-pointer transition-colors select-none
          ${expanded
            ? 'bg-neutral-100 dark:bg-zinc-700 text-brutal-black dark:text-white'
            : 'bg-transparent text-neutral-500 dark:text-neutral-400 hover:text-brutal-black dark:hover:text-white'
          } ${isRunning ? 'brutal-running-mono !text-brutal-black dark:!text-white border-2 !border-brutal-black dark:!border-white' : 'border-2 border-transparent'}`}
      >
        {/* Icon */}
        <span className="text-[14px] shrink-0 drop-shadow-sm flex items-center justify-center">
          {STATUS_ICON[status]}
        </span>

        {/* Label */}
        <span className="truncate max-w-[240px]">spawn subagent</span>

        {/* Status badge */}
        <span className={`text-[9px] font-bold shrink-0 px-1 py-0.5 rounded-sm
          ${status === 'running' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300' :
            status === 'queued' ? 'bg-amber-100 text-amber-700' :
            status === 'completed' ? 'bg-green-100 text-green-700' :
            'bg-red-100 text-red-700'}`
        }>
          {STATUS_LABEL[status]}
          {isRunning && (
            <span className="ml-1 inline-block w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse align-middle" />
          )}
        </span>

        {/* Chevron */}
        <svg
          className={`w-3 h-3 text-neutral-400 transition-transform duration-200 shrink-0 ${expanded ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Expandable body */}
      <div className={`grid transition-[grid-template-rows] duration-200 ease-out overflow-hidden w-full
        ${expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}>
        <div className="overflow-hidden min-h-0 min-w-0 w-full">
          <div className="ml-2 pl-3 border-l-2 border-neutral-200 dark:border-zinc-600 mt-1 mb-2 space-y-2 min-w-0 w-full overflow-x-hidden">

            {/* Task description */}
            {description && (
              <div className="min-w-0">
                <div className="text-[10px] font-mono font-bold text-neutral-400 dark:text-neutral-500 uppercase mb-0.5">Task</div>
                <div className="text-[11px] text-neutral-700 dark:text-neutral-300 leading-relaxed">
                  {description}
                </div>
              </div>
            )}

            {/* Tools whitelist */}
            {toolsAllowed && toolsAllowed.length > 0 && (
              <div className="min-w-0">
                <div className="text-[10px] font-mono font-bold text-neutral-400 dark:text-neutral-500 uppercase mb-0.5">Tools</div>
                <div className="flex flex-wrap gap-1">
                  {toolsAllowed.map((t) => (
                    <span key={t} className="text-[10px] font-mono px-1.5 py-0.5 bg-neutral-100 dark:bg-zinc-700 text-neutral-600 dark:text-neutral-300 rounded-sm border border-neutral-200 dark:border-zinc-600">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Task ID */}
            {taskId && (
              <div className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">
                ID: <span className="text-neutral-600 dark:text-neutral-400">{taskId}</span>
              </div>
            )}

            {/* Result summary (completed) */}
            {status === 'completed' && resultSummary && (
              <div className="min-w-0">
                <div className="text-[10px] font-mono font-bold text-neutral-400 dark:text-neutral-500 uppercase mb-0.5">Result</div>
                <div className="max-h-[120px] overflow-y-auto scrollbar-thin">
                  <pre className="tool-call-pre text-[11px] text-neutral-600 dark:text-neutral-300 leading-relaxed font-mono w-full whitespace-pre-wrap">
                    {resultSummary}
                  </pre>
                </div>
              </div>
            )}

            {/* Error (failed) */}
            {status === 'failed' && error && (
              <div className="text-[11px] text-red-600 dark:text-red-400 font-mono">
                {error}
              </div>
            )}

            {/* Action buttons */}
            <div className="flex items-center gap-2 pt-1">
              {taskId && onOpenSidebar && (
                <button
                  onClick={() => onOpenSidebar(taskId)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide bg-neutral-50 dark:bg-zinc-800 border border-neutral-300 dark:border-zinc-600 rounded-sm hover:bg-neutral-100 dark:hover:bg-zinc-700 transition-colors"
                >
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                  </svg>
                  View Log
                </button>
              )}
              {taskId && isRunning && onStop && (
                <button
                  onClick={() => onStop(taskId)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide bg-red-50 text-red-700 border border-red-400 rounded-sm hover:bg-red-100 transition-colors"
                >
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                  Stop
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
