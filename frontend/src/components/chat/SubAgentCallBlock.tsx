/**
 * SubAgentCallBlock — the transcript card for an `agent` tool call.
 *
 * It is a tool call like any other, so it wears the same pill as ToolCallBlock:
 * mono uppercase headline, the task itself as the detail, a status chip on the
 * right. Live state comes off the shared sub-agent EventSource, with a poll as
 * a fallback for when the parent stream ended before the child did.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { useI18n } from '../../i18n';
import { AgentAvatar } from '../sidebar/subAgentDisplay';
import { useSubAgentStatus, watchSubAgentTask } from '../../hooks/useSubAgentStatus';
import { useSubAgentActivity } from '../../hooks/useSubAgentActivity';
import {
  isSubAgentActive,
  isSubAgentTerminal,
  subAgentOutcomeLabel,
  SubAgentStatus,
  subAgentStatusLabel,
} from './subAgentStatus';
import { DisclosureChevron } from '../DisclosureChevron';
import { SubAgentSteerBox } from './SubAgentSteerBox';
import { SubAgentActivityFeed } from './SubAgentActivityFeed';
import { MarkdownRenderer } from './MarkdownRenderer';
import { hoverText } from '../../lib/hoverText';

export type { SubAgentStatus } from './subAgentStatus';

interface SubAgentCallBlockProps {
  taskId?: string;
  /** The tool call this card renders, used to find its child before it ends. */
  toolCallId?: string;
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
  taskId: taskIdFromResult,
  toolCallId,
  description,
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
  // A blocking call reports its task id only in the result it returns, so for
  // the whole run the user actually watches, the card would have no idea which
  // child is its own. The spawn event carries the tool call id, so match on
  // that until the result arrives with the id itself.
  const spawnedTask = useMemo(() => {
    if (taskIdFromResult || !toolCallId) return undefined;
    return Object.values(taskStates).find((task) => task.tool_call_id === toolCallId);
  }, [taskIdFromResult, toolCallId, taskStates]);
  const taskId = taskIdFromResult ?? spawnedTask?.task_id;
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

  const [expanded, setExpanded] = useState(!runInBackground && isSubAgentActive(externalStatus));
  const bodyId = React.useId();
  const [showFullTask, setShowFullTask] = useState(false);
  const compactTask = (description ?? '').replace(/\s+/g, ' ').trim();
  const taskPreview = compactTask.length > 220 ? `${compactTask.slice(0, 220)}…` : compactTask;
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
    'group/agent-header hover-tint-text inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-mono font-bold uppercase tracking-wide rounded-sm cursor-pointer hover:bg-neutral-100 dark:hover:bg-zinc-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 transition-colors select-none max-w-full min-w-0',
    expanded
      ? 'bg-neutral-100 dark:bg-zinc-700 text-brutal-black dark:text-white'
      : 'bg-transparent text-neutral-500 dark:text-neutral-400 hover:text-brutal-black dark:hover:text-white',
    isRunning
      ? 'brutal-running-mono !text-brutal-black dark:!text-white border-2 !border-brutal-black dark:!border-white'
      : 'border-2 border-transparent',
  ].join(' ');

  return (
    <div className="my-1.5 [.activity-rail_&]:my-0 min-w-0 w-full">
      {/* Compact pill header — same shape as every other tool call */}
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={bodyId}
        onClick={() => setExpanded(!expanded)}
        className={headerClassName}
        title={hoverText(description)}
      >
        {/* Identity, not outcome. A green check here only repeated the DONE
            outcome icon, and said nothing about which agent ran.
            The provider's own colour does, and the profile it was spawned as
            ('verify', 'explore') says what kind of agent it was -- both are in
            the tool result's metadata already. */}
        <AgentAvatar model={model} status={status} className="w-4 h-4 text-[7px] leading-none" />

        <span className="shrink-0">
          {subagentType ? subagentType.toUpperCase() : t('subAgents.delegated')}
        </span>
        <span className="truncate min-w-0 font-normal normal-case tracking-normal opacity-80">
          {headline(description, t('subAgents.title'))}
        </span>

        <span className="sr-only">{subAgentStatusLabel(status, t)}</span>

        {/* Chevron: points right while collapsed and turns down to open, the
            way the activity rail's own disclosures already behave. It used to
            point down when shut and flip up when open, which reads as "there
            is something below" in both states. */}
        <DisclosureChevron
          expanded={expanded}
          className="w-3 h-3 shrink-0 text-neutral-400 transition-all duration-150 [@media(hover:hover)]:opacity-0 group-hover/agent-header:opacity-100 group-focus-visible/agent-header:opacity-100"
        />
      </button>

      {/* Expandable body */}
      <div
        id={bodyId}
        aria-hidden={!expanded}
        style={{ visibility: expanded ? 'visible' : 'hidden' }}
        className={`grid transition-[grid-template-rows] duration-200 ease-out overflow-hidden w-full
        ${expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
      >
        <div className="overflow-hidden min-h-0 min-w-0 w-full">
          <div className="ml-2 pl-3 border-l border-neutral-200 dark:border-zinc-700 mt-2 mb-2 space-y-3 min-w-0">
            {/* Action buttons */}
            <div className="flex items-center gap-2 min-h-6">
              <span className="mr-auto text-[10px] font-mono text-neutral-500 dark:text-neutral-400">
                {subAgentStatusLabel(status, t)}
              </span>
              {taskId && onOpenSidebar && (
                <button
                  onClick={() => onOpenSidebar(taskId)}
                  title={taskId}
                  className="inline-flex items-center gap-1 px-1.5 py-1 text-[10px] font-mono text-neutral-500 dark:text-neutral-400 rounded-sm hover:bg-neutral-100 dark:hover:bg-zinc-800 hover:text-brutal-black dark:hover:text-white transition-colors"
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
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-red-700 dark:text-red-300 border border-transparent rounded-sm hover:bg-red-100 dark:hover:bg-red-900 transition-colors"
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

            {/* What it is doing right now — blocking calls only, and only
                while the run is live. The sidebar keeps the full log. */}
            {isBlocking && isRunning && <SubAgentActivityFeed activity={activity} />}

            {/* Redirect this child in place. Steering the composer still goes
                to the parent (which cancels a blocking child), so the target
                has to be the card to be unambiguous when several run at once. */}
            {isBlocking && taskId && <SubAgentSteerBox taskId={taskId} canSend={isRunning} />}

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
                <div className="min-w-0">
                  <div
                    className={`break-words text-xs leading-relaxed w-full ${
                      status === 'failed'
                        ? 'text-red-600 dark:text-red-400'
                        : 'text-neutral-600 dark:text-neutral-300'
                    }`}
                  >
                    <MarkdownRenderer content={outcomeText} compact />
                  </div>
                </div>
              </div>
            )}

            {description && headline(description, '') !== description.trim() && (
              <div className="min-w-0 rounded-sm bg-neutral-100/60 dark:bg-zinc-800/50 px-3 py-2.5">
                <div className="flex items-center justify-between gap-3 mb-1.5">
                  <span className="text-[10px] font-mono font-bold text-neutral-400 dark:text-neutral-500 uppercase tracking-wide">
                    {t('subAgents.task')}
                  </span>
                  {compactTask.length > 220 && (
                    <button
                      type="button"
                      aria-expanded={showFullTask}
                      onClick={() => setShowFullTask((value) => !value)}
                      className="shrink-0 text-[10px] font-mono text-neutral-500 dark:text-neutral-400 hover:text-brutal-black dark:hover:text-white underline-offset-2 hover:underline focus-visible:underline"
                    >
                      {t(showFullTask ? 'subAgents.hideTask' : 'subAgents.showTask')}
                    </button>
                  )}
                </div>
                <p className="m-0 whitespace-pre-wrap break-words text-xs text-neutral-600 dark:text-neutral-400 leading-relaxed [overflow-wrap:anywhere]">
                  {showFullTask ? description : taskPreview}
                </p>
              </div>
            )}
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
