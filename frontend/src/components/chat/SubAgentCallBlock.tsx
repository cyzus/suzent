/**
 * SubAgentCallBlock — the transcript card for an `agent` tool call.
 *
 * It is a tool call like any other, so it wears the same pill as ToolCallBlock:
 * mono uppercase headline, the task itself as the detail, a status chip on the
 * right. Live state comes off the shared sub-agent EventSource, with a poll as
 * a fallback for when the parent stream ended before the child did.
 */
import React, { useState, useEffect, useRef } from 'react';
import { getApiBase } from '../../lib/api';
import { useI18n } from '../../i18n';
import { useSubAgentStatus } from '../../hooks/useSubAgentStatus';
import {
  isStreamStateStale,
  isSubAgentActive,
  isSubAgentTerminal,
  subAgentOutcomeLabel,
  SubAgentStatus,
  SubAgentStatusBadge,
  SubAgentStatusIcon,
} from './subAgentStatus';

export type { SubAgentStatus } from './subAgentStatus';

interface SubAgentCallBlockProps {
  taskId?: string;
  description?: string;
  toolsAllowed?: string[];
  status: SubAgentStatus;
  resultSummary?: string;
  error?: string;
  /** Called when user clicks "View log" */
  onOpenSidebar?: (taskId: string) => void;
  /** Called when user clicks "Stop" */
  onStop?: (taskId: string) => void;
}

export interface SubAgentArgs {
  description?: string;
  toolsAllowed?: string[];
}

const EMPTY_SUB_AGENT_ARGS: SubAgentArgs = {};
/**
 * Parsed `agent` call arguments, cached by the raw JSON string.
 *
 * The transcript re-renders on every streamed token, so parsing the args inline
 * meant re-parsing every delegated task's prompt for each character of the
 * answer — and handing the card a new object and a new array each time, which
 * defeated its memo. Keyed by the exact args string, so a call whose args are
 * still arriving simply gets a fresh entry.
 */
const subAgentArgsCache = new Map<string, SubAgentArgs>();
/** Bounded so a very long session cannot grow the cache without limit. */
const SUB_AGENT_ARGS_CACHE_MAX = 512;

export function parseSubAgentArgs(args: string | undefined): SubAgentArgs {
  if (!args) return EMPTY_SUB_AGENT_ARGS;
  const cached = subAgentArgsCache.get(args);
  if (cached) return cached;
  let parsed: SubAgentArgs = EMPTY_SUB_AGENT_ARGS;
  try {
    const candidate: unknown = JSON.parse(args);
    if (candidate && typeof candidate === 'object' && !Array.isArray(candidate)) {
      const record = candidate as Record<string, unknown>;
      const toolsAllowed = record.tools_allowed;
      parsed = {
        description: typeof record.description === 'string' ? record.description : undefined,
        toolsAllowed: Array.isArray(toolsAllowed) ? (toolsAllowed as string[]) : undefined,
      };
    }
  } catch {
    parsed = EMPTY_SUB_AGENT_ARGS;
  }
  if (subAgentArgsCache.size >= SUB_AGENT_ARGS_CACHE_MAX) subAgentArgsCache.clear();
  subAgentArgsCache.set(args, parsed);
  return parsed;
}

/** Long enough to carry a real task, short enough to stay a headline. */
const HEADLINE_MAX = 72;

function headline(description: string | undefined, fallback: string): string {
  const compact = (description ?? '').replace(/\s+/g, ' ').trim();
  if (!compact) return fallback;
  return compact.length <= HEADLINE_MAX ? compact : `${compact.slice(0, HEADLINE_MAX - 1)}…`;
}

const SubAgentCallBlockComponent: React.FC<SubAgentCallBlockProps> = ({
  taskId,
  description,
  toolsAllowed,
  status: externalStatus,
  resultSummary: externalResultSummary,
  error: externalError,
  onOpenSidebar,
  onStop,
}) => {
  const { t } = useI18n();
  const { taskStates } = useSubAgentStatus();
  // Self-poll to get real status when the parent SSE stream may have ended before completion
  const [polledStatus, setPolledStatus] = useState<SubAgentStatus | null>(null);
  const [polledResultSummary, setPolledResultSummary] = useState<string | undefined>(undefined);
  const [polledError, setPolledError] = useState<string | undefined>(undefined);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Use a ref so the poll callback always sees the latest resolved status without
  // being captured in a stale closure — avoids polling when already done.
  const resolvedStatusRef = useRef<SubAgentStatus>(externalStatus);

  const streamTask = taskId ? taskStates[taskId] : undefined;
  // The poll exists precisely for when the stream is not there; if it has seen
  // the run end, its answer outranks whatever the stream last managed to say.
  const liveTask = isStreamStateStale(streamTask?.status, polledStatus ?? undefined)
    ? undefined
    : streamTask;
  const status = liveTask?.status ?? polledStatus ?? externalStatus;
  const resultSummary = liveTask?.result_summary ?? polledResultSummary ?? externalResultSummary;
  const error = liveTask?.error ?? polledError ?? externalError;

  // Keep ref in sync on every render
  resolvedStatusRef.current = status;

  useEffect(() => {
    if (!taskId) return;
    // Already terminal — no need to poll
    if (isSubAgentTerminal(resolvedStatusRef.current)) return;

    const poll = async () => {
      // Stop polling if status was resolved externally while waiting
      if (isSubAgentTerminal(resolvedStatusRef.current)) {
        if (timerRef.current) clearInterval(timerRef.current);
        return;
      }
      try {
        const res = await fetch(`${getApiBase()}/subagents/${taskId}`);
        if (!res.ok) return;
        const data = await res.json();
        const task = data.task;
        if (task) {
          setPolledStatus(task.status);
          if (task.result_summary) setPolledResultSummary(task.result_summary);
          if (task.error) setPolledError(task.error);
          if (isSubAgentTerminal(task.status)) {
            if (timerRef.current) clearInterval(timerRef.current);
          }
        }
      } catch {
        /* ignore */
      }
    };

    poll();
    timerRef.current = setInterval(poll, 3000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [taskId]);

  // Stop polling immediately when the status resolves elsewhere (stream arrived)
  useEffect(() => {
    if (isSubAgentTerminal(status) && timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, [status]);

  const [expanded, setExpanded] = useState(true);
  // Auto-collapse when completed
  useEffect(() => {
    if (status === 'completed') setExpanded(false);
  }, [status]);

  const isRunning = isSubAgentActive(status);
  const outcomeText = status === 'completed' ? resultSummary : error;

  const headerClassName = [
    'inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-mono font-bold uppercase tracking-wide rounded-sm cursor-pointer transition-colors select-none',
    expanded
      ? 'bg-neutral-100 dark:bg-zinc-700 text-brutal-black dark:text-white'
      : 'bg-transparent text-neutral-500 dark:text-neutral-400 hover:text-brutal-black dark:hover:text-white',
    isRunning
      ? 'brutal-running-mono !text-brutal-black dark:!text-white border-2 !border-brutal-black dark:!border-white'
      : 'border-2 border-transparent',
  ].join(' ');

  return (
    <div className="my-2 min-w-0 w-full">
      {/* Compact pill header — same shape as every other tool call */}
      <button
        onClick={() => setExpanded(!expanded)}
        className={headerClassName}
        title={description || undefined}
      >
        <SubAgentStatusIcon status={status} />

        {/* The job the sub-agent was given reads better than "spawn subagent" */}
        <span className="shrink-0">{t('subAgents.delegated')}</span>
        <span className="truncate min-w-0 max-w-[320px] font-normal normal-case tracking-normal opacity-80">
          {headline(description, t('subAgents.title'))}
        </span>

        <SubAgentStatusBadge status={status} t={t} />

        {/* Chevron */}
        <svg
          className={`w-3 h-3 text-neutral-400 transition-transform duration-200 shrink-0 ${expanded ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={3}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Expandable body */}
      <div
        className={`grid transition-[grid-template-rows] duration-200 ease-out overflow-hidden w-full
        ${expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
      >
        <div className="overflow-hidden min-h-0 min-w-0 w-full">
          <div className="ml-2 pl-3 border-l-2 border-neutral-200 dark:border-zinc-600 mt-1 mb-2 space-y-2 min-w-0 w-full overflow-x-hidden">
            {/* Task description */}
            {description && (
              <div className="min-w-0">
                <div className="text-[10px] font-mono font-bold text-neutral-400 dark:text-neutral-500 uppercase tracking-wide mb-0.5">
                  {t('subAgents.task')}
                </div>
                <div className="text-[11px] text-neutral-700 dark:text-neutral-300 leading-relaxed">
                  {description}
                </div>
              </div>
            )}

            {/* Tools whitelist */}
            {toolsAllowed && toolsAllowed.length > 0 && (
              <div className="min-w-0">
                <div className="text-[10px] font-mono font-bold text-neutral-400 dark:text-neutral-500 uppercase tracking-wide mb-0.5">
                  {t('subAgents.tools', { count: toolsAllowed.length })}
                </div>
                <div className="flex flex-wrap gap-1">
                  {toolsAllowed.map((toolName) => (
                    <span
                      key={toolName}
                      className="text-[10px] font-mono px-1.5 py-0.5 bg-neutral-100 dark:bg-zinc-700 text-neutral-600 dark:text-neutral-300 rounded-sm border border-neutral-200 dark:border-zinc-600"
                    >
                      {toolName}
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

            {/* How the run ended: a result, or why it stopped. Only a genuine
                failure is painted red — a stop is not an error. */}
            {!isRunning && outcomeText && (
              <div className="min-w-0">
                <div
                  className={`text-[10px] font-mono font-bold uppercase tracking-wide mb-0.5 ${
                    status === 'failed' ? 'text-red-500' : 'text-neutral-400 dark:text-neutral-500'
                  }`}
                >
                  {subAgentOutcomeLabel(status, t)}
                </div>
                <div className="max-h-[120px] overflow-y-auto scrollbar-thin">
                  <pre
                    className={`tool-call-pre text-[11px] leading-relaxed font-mono w-full whitespace-pre-wrap ${
                      status === 'failed'
                        ? 'text-red-600 dark:text-red-400'
                        : 'text-neutral-600 dark:text-neutral-300'
                    }`}
                  >
                    {outcomeText}
                  </pre>
                </div>
              </div>
            )}

            {/* Action buttons */}
            <div className="flex items-center gap-2 pt-1">
              {taskId && onOpenSidebar && (
                <button
                  onClick={() => onOpenSidebar(taskId)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide bg-white dark:bg-zinc-900 text-brutal-black dark:text-white border-2 border-brutal-black dark:border-white rounded-sm hover:bg-neutral-100 dark:hover:bg-zinc-800 transition-colors"
                >
                  <svg
                    className="w-3 h-3"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
                    />
                  </svg>
                  {t('subAgents.viewLog')}
                </button>
              )}
              {taskId && isRunning && onStop && (
                <button
                  onClick={() => onStop(taskId)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-300 border-2 border-red-600 rounded-sm hover:bg-red-100 dark:hover:bg-red-900 transition-colors"
                >
                  <svg
                    className="w-3 h-3"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2.5}
                  >
                    <rect x="6" y="6" width="12" height="12" rx="1" />
                  </svg>
                  {t('subAgents.stop')}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

/**
 * Memoized: a delegated task's card is unchanged by the answer text arriving
 * around it, and re-rendering every card on every token is what made a long
 * turn's display crawl. Its own live state comes from the sub-agent status
 * context and its poll, neither of which the memo blocks.
 */
export const SubAgentCallBlock = React.memo(SubAgentCallBlockComponent);
