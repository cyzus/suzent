/**
 * SubAgentCallBlock — the transcript card for an `agent` tool call.
 *
 * It is a tool call like any other, so it wears the same pill as ToolCallBlock:
 * mono uppercase headline, the task itself as the detail, a status chip on the
 * right. Live state comes off the shared sub-agent EventSource, with a poll as
 * a fallback for when the parent stream ended before the child did.
 */
import React, { useCallback, useState, useEffect } from 'react';
import { useI18n } from '../../i18n';
import { toolLabel } from './toolSummary';
import { AgentAvatar } from '../sidebar/subAgentDisplay';
import { useSubAgentStatus, watchSubAgentTask } from '../../hooks/useSubAgentStatus';
import { useSubAgentActivity } from '../../hooks/useSubAgentActivity';
import {
  isSubAgentActive,
  isSubAgentTerminal,
  subAgentOutcomeLabel,
  SubAgentStatus,
  SubAgentStatusBadge,
} from './subAgentStatus';
import { DisclosureChevron } from '../DisclosureChevron';
import { SubAgentSteerBox } from './SubAgentSteerBox';
import { SubAgentActivityFeed } from './SubAgentActivityFeed';

export type { SubAgentStatus } from './subAgentStatus';

interface SubAgentCallBlockProps {
  taskId?: string;
  description?: string;
  toolsAllowed?: string[];
  status: SubAgentStatus;
  resultSummary?: string;
  error?: string;
  /** Which model ran it, for the identity mark in the header. */
  model?: string;
  /** Profile it was spawned as ('verify', 'explore', …), if recorded. */
  subagentType?: string;
  /** Called when user clicks "View log" */
  onOpenSidebar?: (taskId: string) => void;
  /** Called when user clicks "Stop" */
  onStop?: (taskId: string) => void;
  /** False for a blocking call, whose parent turn is suspended on this child. */
  runInBackground?: boolean;
}

export interface SubAgentArgs {
  description?: string;
  toolsAllowed?: string[];
  /** False means the parent's turn is suspended waiting on this child. */
  runInBackground?: boolean;
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
        // Absent means the tool's own default, which is background.
        runInBackground:
          typeof record.run_in_background === 'boolean' ? record.run_in_background : true,
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
  model: externalModel,
  subagentType,
  onOpenSidebar,
  onStop,
  runInBackground = true,
}) => {
  const { t } = useI18n();
  const { taskStates } = useSubAgentStatus();

  // Presentation only: status comes from the shared store, which merges the
  // sub-agent stream and the shared fallback poll and refuses to walk a
  // finished run back to 'running'. This block used to run its own 3s poll and
  // reconcile it against the stream itself, which meant N blocks made N
  // requests and each stopped covering its task the moment it unmounted.
  const streamTask = taskId ? taskStates[taskId] : undefined;
  const status = streamTask?.status ?? externalStatus;
  const model = streamTask?.model_override ?? externalModel;
  const resultSummary = streamTask?.result_summary ?? externalResultSummary;
  const error = streamTask?.error ?? externalError;

  // Register with the shared poll only while this task is unfinished. The
  // transcript is the only place a task from an earlier session is named, so
  // without this a chat reopened mid-run would never learn how it ended.
  useEffect(() => {
    if (!taskId || isSubAgentTerminal(status)) return;
    return watchSubAgentTask(taskId);
  }, [taskId, status]);

  const [expanded, setExpanded] = useState(true);
  // Auto-collapse when completed
  useEffect(() => {
    if (status === 'completed') setExpanded(false);
  }, [status]);

  const isRunning = isSubAgentActive(status);
  const outcomeText = status === 'completed' ? resultSummary : error;

  // Only a blocking call gets the inline feed. A background child runs while
  // the parent keeps talking, and several can run at once, so inlining those
  // would interleave into noise -- the sidebar is the right home for them.
  // A blocking call is the opposite case: the transcript is frozen until it
  // returns, so without this the card is the only thing on screen and it does
  // not move.
  const isBlocking = !runInBackground;
  const childChatId = streamTask?.chat_id;
  const activity = useSubAgentActivity(childChatId, isBlocking && isRunning);

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
        {/* Identity, not outcome. A green check here only repeated the DONE
            badge two elements along, and said nothing about which agent ran.
            The provider's own colour does, and the profile it was spawned as
            ('verify', 'explore') says what kind of agent it was -- both are in
            the tool result's metadata already. */}
        <AgentAvatar model={model} status={status} className="w-4 h-4 text-[7px] leading-none" />

        <span className="shrink-0">
          {subagentType ? subagentType.toUpperCase() : t('subAgents.delegated')}
        </span>
        <span className="truncate min-w-0 max-w-[320px] font-normal normal-case tracking-normal opacity-80">
          {headline(description, t('subAgents.title'))}
        </span>

        <SubAgentStatusBadge status={status} t={t} />

        {/* Chevron: points right while collapsed and turns down to open, the
            way the activity rail's own disclosures already behave. It used to
            point down when shut and flip up when open, which reads as "there
            is something below" in both states. */}
        <DisclosureChevron
          expanded={expanded}
          className="w-3 h-3 text-neutral-400 transition-transform duration-200"
        />
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
                      title={toolName}
                    >
                      {toolLabel(toolName)}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* What it is doing right now — blocking calls only, and only
                while the run is live. The sidebar keeps the full log. */}
            {isBlocking && isRunning && <SubAgentActivityFeed activity={activity} />}

            {/* Redirect this child in place. Steering the composer still goes
                to the parent (which cancels a blocking child), so the target
                has to be the card to be unambiguous when several run at once. */}
            {isBlocking && isRunning && taskId && <SubAgentSteerBox taskId={taskId} />}

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
