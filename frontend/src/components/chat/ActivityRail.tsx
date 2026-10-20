import { ToolGroupIcon, pickToolRunningSurfaceClass } from './toolGroupIcon';
import { summarizeActivity, type ActivitySummaryTool } from './activitySummary';
import React, { useEffect, useState } from 'react';
import type { AGUIPart } from '../../hooks/useAGUI';
import { useDisclosureBody } from '../../hooks/useDisclosureBody';
import type { ContentBlock } from '../../lib/chatUtils';
import { MarkdownRenderer } from './MarkdownRenderer';
import { getToolSummary, normalizeToolName } from './toolSummary';
import type { ToolTense } from './toolSummary';
import { useTypewriter } from '../../hooks/useTypewriter';
import { tForLocale, useI18n } from '../../i18n';
import { DisclosureChevron } from '../DisclosureChevron';
import { AgentAvatar } from '../sidebar/subAgentDisplay';
import { useSubAgentStatus, watchSubAgentTask } from '../../hooks/useSubAgentStatus';
import { parseSubAgentResult } from './subAgentResult';
import { isSubAgentActive, isSubAgentTerminal } from './subAgentStatus';

export type AguiChunkType =
  'tool' | 'reasoning' | 'text' | 'a2ui' | 'acp-permission' | 'acp-notice' | 'incoming-message';

export type AguiChunk = { type: AguiChunkType; items: AGUIPart[] };

/**
 * A part the rail would render as nothing at all.
 *
 * The stream opens a text message before its first token, and one per
 * assistant step -- so a step that only called tools leaves an empty text part
 * behind. Reasoning opens the same way. Neither draws anything, but both used
 * to reach the chunker, where an empty text part counted as prose and cut the
 * activity rail in two: a long turn fragmented into one collapsed rail per
 * step, with nothing visible between them. Citation sources carry metadata and
 * never had display content to begin with.
 */
function isEmptyAguiPart(part: AGUIPart): boolean {
  if (part.type === 'citation-sources') return true;
  if (part.type === 'text' || part.type === 'reasoning') return !(part.text || '').trim();
  return false;
}

/**
 * Assistant parts, cleaned up and grouped into the chunks the rail renders.
 *
 * Tool parts repeated under one `toolCallId` -- resume and recovery replay the
 * call later in the stream -- merge into the first occurrence so output stays
 * under the initial tool call instead of rendering a split block. Parts that
 * render nothing are dropped, so only something the user can actually see ends
 * one chunk and starts the next. What survives is grouped into runs of the same
 * type, preserving interleaved order.
 */
export function buildAguiActivityChunks(parts: AGUIPart[]): AguiChunk[] {
  const normalized: AGUIPart[] = [];
  const toolIndexById = new Map<string, number>();

  for (const part of parts) {
    if (part.type === 'tool' && part.toolCallId) {
      const existingIndex = toolIndexById.get(part.toolCallId);
      if (existingIndex !== undefined) {
        const existing = normalized[existingIndex];
        normalized[existingIndex] = {
          ...existing,
          ...part,
          // Prefer freshest non-empty payload fields.
          toolName: part.toolName || existing.toolName,
          args: part.args ?? existing.args,
          output: part.output ?? existing.output,
          approvalId: part.approvalId ?? existing.approvalId,
          permission: part.permission ?? existing.permission,
          permissionDecision: part.permissionDecision ?? existing.permissionDecision,
          permissionResolution: part.permissionResolution ?? existing.permissionResolution,
          outcome: part.outcome ?? existing.outcome,
          state: part.state ?? existing.state,
        };
        continue;
      }
      toolIndexById.set(part.toolCallId, normalized.length);
    }
    normalized.push(part);
  }

  const chunks: AguiChunk[] = [];
  for (const part of normalized) {
    if (isEmptyAguiPart(part)) continue;
    const type = part.type as AguiChunkType;
    const current = chunks[chunks.length - 1];
    if (current && current.type === type) {
      current.items.push(part);
      continue;
    }
    chunks.push({ type, items: [part] });
  }

  return chunks;
}

export type ActivityRenderGroup<T> =
  | { type: 'activity'; chunks: Array<{ chunk: T; index: number }> }
  | { type: 'single'; chunk: T; index: number };

export function groupActivityChunks<T>(
  chunks: T[],
  isActivityChunk: (chunk: T) => boolean,
  endsActivity: (chunk: T) => boolean = () => false
): ActivityRenderGroup<T>[] {
  const renderGroups: ActivityRenderGroup<T>[] = [];
  let activityChunks: Array<{ chunk: T; index: number }> = [];

  chunks.forEach((chunk, index) => {
    if (isActivityChunk(chunk)) {
      activityChunks.push({ chunk, index });
      if (endsActivity(chunk)) {
        renderGroups.push({ type: 'activity', chunks: activityChunks });
        activityChunks = [];
      }
      return;
    }

    if (activityChunks.length > 0) {
      renderGroups.push({ type: 'activity', chunks: activityChunks });
      activityChunks = [];
    }
    renderGroups.push({ type: 'single', chunk, index });
  });

  if (activityChunks.length > 0) {
    renderGroups.push({ type: 'activity', chunks: activityChunks });
  }

  return renderGroups;
}

export function getActivityGroupOrdinal<T>(
  groups: ActivityRenderGroup<T>[],
  index: number
): number {
  return groups.slice(0, index).filter((group) => group.type === 'activity').length;
}

export function getReasoningHeader(text: string, isStreaming: boolean = false): string {
  const firstLine = text
    .trim()
    .split('\n')[0]
    .replace(/^[#*>-\s]+/, '')
    .replace(/\*\*/g, '')
    .trim();
  const summary =
    firstLine.length > 80 ? firstLine.substring(0, 77) + '...' : firstLine || 'Processing...';
  const prefix = isStreaming ? 'Thinking' : 'Thought';
  return `${prefix}: ${summary}`;
}

export function countActivityItems(
  chunks: Array<{ chunk: { type: string; items?: unknown[]; blocks?: unknown[] } }>
): number {
  return chunks.reduce((total, { chunk }) => {
    if (chunk.type === 'reasoning') return total + 1;
    if (chunk.type === 'tool') return total + (chunk.items?.length ?? 0);
    if (chunk.type === 'toolCall') return total + (chunk.blocks?.length ?? 0);
    return total;
  }, 0);
}

const railT = (key: string, params?: Record<string, unknown>) => tForLocale('en', key, params);

function capitalize(value: string): string {
  return value ? `${value[0].toUpperCase()}${value.slice(1)}` : value;
}

/**
 * Rail status label for a tool call, e.g. "Read ToolCallBlock.tsx".
 *
 * Falls back to the bare tool name while args are still streaming in (or when
 * a tool exposes nothing worth showing), so the label never goes empty.
 */
export function formatActivityToolName(
  toolName: string | undefined,
  args?: string,
  tense: ToolTense = 'imperative'
): string {
  if (!toolName) return 'unknown tool';
  const fallback = capitalize(toolName.replace(/_/g, ' '));
  let parsed: Record<string, unknown> | null = null;
  if (args) {
    try {
      const candidate = JSON.parse(args);
      if (candidate && typeof candidate === 'object' && !Array.isArray(candidate)) {
        parsed = candidate as Record<string, unknown>;
      }
    } catch {
      parsed = null;
    }
  }
  if (!parsed) return fallback;
  // The surrounding rail copy is English-only, so resolve verbs against `en`.
  const summary = getToolSummary(toolName, parsed, railT, tense);
  // A summary with no detail still has a real verb -- a described shell call is
  // all headline ("Run the tests") -- so only unparsed args fall back.
  return summary.detail ? `${summary.verb} ${summary.detail}` : summary.verb;
}

export function trailingToolRunLength(toolNames: Array<string | undefined>): number {
  if (toolNames.length === 0) return 0;
  const last = toolNames[toolNames.length - 1];
  if (!last) return 0;
  const canonical = normalizeToolName(last);
  let count = 0;
  for (let i = toolNames.length - 1; i >= 0; i -= 1) {
    const name = toolNames[i];
    if (!name || normalizeToolName(name) !== canonical) break;
    count += 1;
  }
  return count;
}

export function isActionableAguiApproval(part: AGUIPart): boolean {
  return part.state === 'approval-requested' && !part.output && Boolean(part.approvalId);
}

export function getAguiActivityLabel(
  chunks: Array<{ chunk: { type: string; items?: AGUIPart[] } }>,
  isStreaming: boolean
): string | undefined {
  for (let i = chunks.length - 1; i >= 0; i -= 1) {
    const chunk = chunks[i].chunk;
    if (chunk.type === 'tool') {
      const pendingTool = [...(chunk.items ?? [])].reverse().find(isActionableAguiApproval);
      if (pendingTool)
        return `Approval needed: ${formatActivityToolName(pendingTool.toolName, pendingTool.args)}`;
      const items = chunks
        .slice(0, i + 1)
        .flatMap((entry) => (entry.chunk.type === 'tool' ? (entry.chunk.items ?? []) : []));
      const toolIndex = items.length - 1;
      if (toolIndex >= 0) {
        const tool = items[toolIndex];
        return formatActivityToolName(
          tool.toolName,
          tool.args,
          isStreaming && !tool.output ? 'active' : 'past'
        );
      }
    }
    if (chunk.type === 'reasoning') {
      const text = (chunk.items ?? [])
        .map((part) => part.text || '')
        .join('')
        .trim();
      if (text) return getReasoningHeader(text, isStreaming);
    }
  }
  return undefined;
}

export function hasAguiPendingApproval(
  chunks: Array<{ chunk: { type: string; items?: AGUIPart[] } }>
): boolean {
  return chunks.some(
    ({ chunk }) => chunk.type === 'tool' && (chunk.items ?? []).some(isActionableAguiApproval)
  );
}

export function getLegacyActivityLabel(
  chunks: Array<{ chunk: { type: string; blocks?: ContentBlock[] } }>,
  isStreaming: boolean
): string | undefined {
  for (let i = chunks.length - 1; i >= 0; i -= 1) {
    const chunk = chunks[i].chunk;
    if (chunk.type === 'toolCall') {
      const pendingTool = [...(chunk.blocks ?? [])]
        .reverse()
        .find((block) => block.approvalState === 'pending' && !block.content && !!block.approvalId);
      if (pendingTool)
        return `Approval needed: ${formatActivityToolName(pendingTool.toolName, pendingTool.toolArgs)}`;
      const blocks = chunks
        .slice(0, i + 1)
        .flatMap((entry) => (entry.chunk.type === 'toolCall' ? (entry.chunk.blocks ?? []) : []));
      const toolIndex = blocks.length - 1;
      if (toolIndex >= 0) {
        const tool = blocks[toolIndex];
        return formatActivityToolName(
          tool.toolName,
          tool.toolArgs,
          isStreaming && !tool.content ? 'active' : 'past'
        );
      }
    }
    if (chunk.type === 'reasoning') {
      const text = (chunk.blocks ?? [])
        .map((block) => block.content)
        .join('\n')
        .trim();
      if (text) return getReasoningHeader(text, isStreaming);
    }
  }
  return undefined;
}

export function hasLegacyPendingApproval(
  chunks: Array<{ chunk: { type: string; blocks?: ContentBlock[] } }>
): boolean {
  return chunks.some(
    ({ chunk }) =>
      chunk.type === 'toolCall' &&
      (chunk.blocks ?? []).some(
        (block) => block.approvalState === 'pending' && !block.content && !!block.approvalId
      )
  );
}

function formatActivityDuration(totalSeconds: number): string {
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`;
}

export const WorkedDuration: React.FC<{
  durationSeconds?: number;
  startedAtMs?: number;
  isActive?: boolean;
}> = ({ durationSeconds, startedAtMs, isActive = false }) => {
  const { t } = useI18n();
  // Use the caller-provided start time when available so the timer resumes from
  // the original start across remounts (e.g. reconnecting to a stream after a
  // chat switch); otherwise fall back to mount time.
  const startedAtRef = React.useRef(startedAtMs ?? Date.now());
  const [elapsedSeconds, setElapsedSeconds] = useState(() =>
    Math.max(0, Math.floor((Date.now() - startedAtRef.current) / 1000))
  );

  // Adopt a later-arriving start time (the prop may be undefined on first render
  // and resolve once the streaming chat's start timestamp is known).
  useEffect(() => {
    if (startedAtMs && startedAtMs !== startedAtRef.current) {
      startedAtRef.current = startedAtMs;
      // Re-read now rather than waiting up to a second for the next tick, or
      // the rail shows a count measured from the wrong origin in between.
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAtMs) / 1000)));
    }
  }, [startedAtMs]);

  useEffect(() => {
    if (!isActive) return undefined;
    const updateElapsed = () => {
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAtRef.current) / 1000)));
    };
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(timer);
  }, [isActive]);

  return (
    <span className="shrink-0 whitespace-nowrap py-1 text-xs font-mono text-neutral-500 dark:text-neutral-400">
      {t('activityRail.workedFor', {
        duration: formatActivityDuration(
          isActive ? elapsedSeconds : (durationSeconds ?? elapsedSeconds)
        ),
      })}
    </span>
  );
};

export function getFinalContentStart<T extends { type: string }>(
  groups: ActivityRenderGroup<T>[]
): number {
  let index = groups.length;
  while (index > 0) {
    const group = groups[index - 1];
    if (group.type !== 'single' || !['text', 'content', 'a2ui'].includes(group.chunk.type)) break;
    index -= 1;
  }
  return index;
}

export const TurnActivity: React.FC<{
  children: React.ReactNode[];
  finalStart: number;
  isStreaming: boolean;
  durationSeconds?: number;
  startedAtMs?: number;
}> = ({ children, finalStart, isStreaming, durationSeconds, startedAtMs }) => {
  const bodyId = React.useId();
  const [expanded, setExpanded] = useState(false);
  const wasStreaming = React.useRef(isStreaming);
  useEffect(() => {
    if (wasStreaming.current && !isStreaming) setExpanded(false);
    wasStreaming.current = isStreaming;
  }, [isStreaming]);
  const mounted = useDisclosureBody(expanded);
  if (isStreaming)
    return (
      <>
        <div className="activity-rail-header activity-turn-duration">
          <WorkedDuration startedAtMs={startedAtMs} isActive />
        </div>
        <div className="activity-turn-history space-y-2 py-1">{children.slice(0, finalStart)}</div>
        {children.slice(finalStart)}
      </>
    );
  return (
    <>
      {finalStart > 0 && (
        <div className="min-w-0 w-full">
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls={bodyId}
            onClick={() => setExpanded(!expanded)}
            className="activity-rail-header activity-turn-duration"
          >
            <WorkedDuration durationSeconds={durationSeconds} startedAtMs={startedAtMs} />
            <DisclosureChevron
              expanded={expanded}
              className="w-3 h-3 shrink-0 text-neutral-400 transition-transform duration-200"
            />
          </button>
          <div
            id={bodyId}
            aria-hidden={!expanded}
            style={{ visibility: expanded ? 'visible' : 'hidden' }}
            className={`grid transition-[grid-template-rows] duration-200 ease-out motion-reduce:transition-none ${expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
          >
            <div className="min-h-0 overflow-hidden">
              <div className="activity-turn-history space-y-2 py-1">
                {expanded || mounted ? children.slice(0, finalStart) : null}
              </div>
            </div>
          </div>
        </div>
      )}
      {children.slice(finalStart)}
    </>
  );
};

export const ActivityRail: React.FC<{
  children: React.ReactNode;
  itemCount: number;
  summaryTools?: ActivitySummaryTool[];
  defaultExpanded?: boolean;
  /** The turn is still streaming. */
  isActive?: boolean;
  /**
   * This rail is the one the agent is working in right now. A turn that
   * interleaves prose with tool calls renders several rails, and only the last
   * of them is live: the earlier ones are finished work and must not animate.
   */
  isCurrent?: boolean;
  isThinking?: boolean;
  hasPending?: boolean;
  currentLabel?: string;
}> = ({
  children,
  itemCount,
  summaryTools,
  defaultExpanded = false,
  isActive = false,
  isCurrent = isActive,
  isThinking = false,
  hasPending = false,
  currentLabel,
}) => {
  const { t } = useI18n();
  const bodyId = React.useId();
  const [expanded, setExpanded] = useState(defaultExpanded);
  // Once the user has opened or closed a rail themselves, stop steering it —
  // auto-collapsing a rail they deliberately opened is worse than leaving it.
  const userToggledRef = React.useRef(false);
  // Follow the caller in both directions so a rail the agent has moved past
  // folds itself away instead of leaving the whole turn expanded at once.
  useEffect(() => {
    if (userToggledRef.current) return;
    setExpanded(defaultExpanded);
  }, [defaultExpanded]);

  // See useDisclosureBody: the body is not mounted while collapsed, is held one
  // transition past close so the animation still plays, and stays pinned while
  // an approval is pending so a half-typed rejection reason survives.
  const visible = expanded || hasPending;
  const bodyMounted = useDisclosureBody(visible, { keepMounted: hasPending });

  const scrollClassName =
    'activity-rail-scroll min-w-0 w-full max-h-[min(24rem,50vh)] overflow-y-auto overscroll-contain';
  const summary = !hasPending && summaryTools ? summarizeActivity(summaryTools, t) : undefined;
  const latestTool = summaryTools?.[summaryTools.length - 1];
  const thinking = isCurrent && isThinking;
  const { taskStates } = useSubAgentStatus();
  const agentResult =
    normalizeToolName(latestTool?.toolName ?? '') === 'agent'
      ? parseSubAgentResult(latestTool?.output)
      : undefined;
  const agentTask = agentResult
    ? agentResult.taskId
      ? taskStates[agentResult.taskId]
      : Object.values(taskStates).find(
          (task) => latestTool?.toolCallId && task.tool_call_id === latestTool.toolCallId
        )
    : undefined;
  const agentStatus =
    agentTask?.status ??
    agentResult?.status ??
    (latestTool?.failed ? 'failed' : latestTool?.running ? 'running' : 'completed');
  const agentTaskId = agentTask?.task_id ?? agentResult?.taskId;
  useEffect(() => {
    if (!agentTaskId || isSubAgentTerminal(agentStatus)) return;
    return watchSubAgentTask(agentTaskId);
  }, [agentTaskId, agentStatus]);
  const runningTool =
    isCurrent &&
    !thinking &&
    !visible &&
    !hasPending &&
    (agentResult ? isSubAgentActive(agentStatus) : latestTool?.running && !latestTool.failed)
      ? latestTool?.toolName
      : undefined;
  const headerLabel =
    (isCurrent && !visible ? currentLabel : summary) ?? currentLabel ?? t('activityRail.activity');

  return (
    <div className="activity-rail-shell min-w-0 w-full" data-current-activity={isCurrent}>
      <button
        type="button"
        aria-expanded={visible}
        aria-controls={bodyId}
        onClick={() => {
          userToggledRef.current = true;
          setExpanded((value) => !value);
        }}
        className={`activity-rail-header ${
          hasPending
            ? 'activity-rail-header-pending'
            : isCurrent && !visible
              ? thinking
                ? ''
                : runningTool
                  ? `activity-turn-tool ${pickToolRunningSurfaceClass(runningTool)}`
                  : latestTool
                    ? ''
                    : 'activity-rail-header-active'
              : ''
        }`}
      >
        {thinking ? null : isCurrent && !visible && agentResult ? (
          <AgentAvatar
            model={agentTask?.model_override ?? agentResult.model}
            status={agentStatus}
            className="w-4 h-4 text-[7px] leading-none"
          />
        ) : isCurrent && !visible && latestTool?.toolName ? (
          <ToolGroupIcon
            toolName={latestTool.toolName}
            isStreaming={Boolean(runningTool)}
            hasOutput={!runningTool}
          />
        ) : null}
        <span
          className={`truncate min-w-0 ${thinking && !visible ? 'reasoning-thinking-label' : ''}`}
          title={headerLabel}
        >
          {hasPending ? (currentLabel ?? t('activityRail.approvalNeeded')) : headerLabel}
        </span>
        {hasPending && (
          <span className="activity-rail-pending-badge">{t('activityRail.pending')}</span>
        )}
        {!summary && (
          <>
            <span className="shrink-0 text-neutral-300 dark:text-neutral-600" aria-hidden="true">
              |
            </span>
            <span className="shrink-0 whitespace-nowrap text-neutral-500 dark:text-neutral-400">
              {t(itemCount === 1 ? 'activityRail.step' : 'activityRail.steps', {
                count: itemCount,
              })}
            </span>
          </>
        )}
        <DisclosureChevron
          expanded={visible}
          className="activity-rail-chevron w-3 h-3 text-neutral-500 dark:text-neutral-400 transition-all duration-200"
        />
      </button>
      <div
        id={bodyId}
        aria-hidden={!visible}
        style={{ visibility: visible ? 'visible' : 'hidden' }}
        className={`grid transition-[grid-template-rows] duration-200 ease-out motion-reduce:transition-none overflow-hidden ${visible ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
      >
        <div className="min-h-0 overflow-hidden">
          <div className={scrollClassName}>
            <div className="activity-rail min-w-0 w-full">
              {visible || bodyMounted ? children : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export const ActivityRailItem: React.FC<{
  toolName?: string;
  state?: 'active' | 'done' | 'error' | 'neutral' | 'pending';
  children: React.ReactNode;
}> = ({ state = 'neutral', toolName, children }) => {
  const rowRef = React.useRef<HTMLDivElement>(null);
  const dotRef = React.useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const row = rowRef.current;
    const dot = dotRef.current;
    const header = row?.querySelector<HTMLElement>(
      '.activity-rail-card button, .activity-rail-card [role="button"]'
    );
    if (!row || !dot || !header) return;
    const align = (): void => {
      const bounds = header.getBoundingClientRect();
      // Anchor to the header, not the full row, whose details can expand independently.
      dot.style.top = `${bounds.top - row.getBoundingClientRect().top + bounds.height / 2}px`;
      dot.style.transform = 'translateY(-50%)';
    };
    align();
    const observer = new ResizeObserver(align);
    observer.observe(header);
    observer.observe(row);
    return () => observer.disconnect();
  }, [state]);
  return (
    <div
      ref={rowRef}
      className="activity-rail-item min-w-0"
      data-activity-state={state}
      data-tool-name={toolName}
    >
      <span
        ref={dotRef}
        className={`activity-rail-dot ${
          state === 'pending'
            ? 'activity-rail-dot-pending'
            : state === 'active'
              ? 'activity-rail-dot-active'
              : state === 'error'
                ? 'activity-rail-dot-error'
                : state === 'done'
                  ? 'activity-rail-dot-done'
                  : ''
        }`}
      />
      <div
        className={`activity-rail-card ${
          state === 'pending'
            ? 'activity-rail-card-pending'
            : state === 'error'
              ? 'activity-rail-card-error'
              : state === 'active'
                ? 'activity-rail-card-active'
                : ''
        }`}
      >
        {children}
      </div>
    </div>
  );
};

const ReasoningRailItemComponent: React.FC<{
  text: string;
  isStreaming?: boolean;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
}> = ({ text, isStreaming, onFileClick }) => {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  // Reasoning arrives in the same uneven bursts as the answer; reveal it at a
  // steady rate so an expanded thought reads as flowing text.
  const revealedText = useTypewriter(text, Boolean(isStreaming) && expanded);
  const thinking = Boolean(isStreaming);
  return (
    <ActivityRailItem state={thinking ? 'active' : 'done'}>
      <div className="min-w-0">
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="group/thought-header inline-flex items-center gap-1.5 px-2.5 cursor-pointer select-none min-w-0 max-w-full"
        >
          {/* A thought carries the same two states as a tool call — in flight
              and finished. Saying only "Thought" made a reasoning block that
              was still arriving look like one that had already landed; the
              label animates while it streams and settles when it lands. */}
          <span
            className={`text-[11px] font-mono font-bold uppercase tracking-wide shrink-0 ${
              thinking
                ? 'reasoning-thinking-label text-brutal-black dark:text-neutral-100'
                : 'text-neutral-500 dark:text-neutral-400'
            }`}
          >
            {thinking ? t('activityRail.thinking') : t('activityRail.thought')}
          </span>
          <DisclosureChevron
            expanded={expanded}
            className="w-3 h-3 text-neutral-400 opacity-0 transition-all duration-150 group-hover/thought-header:opacity-100"
          />
        </button>
        <div
          className={`grid transition-[grid-template-rows] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)] overflow-hidden ${expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
        >
          <div className="min-h-0 overflow-hidden">
            <div className="mt-2 pt-1">
              <div className="text-[13px] md:text-sm text-brutal-black/85 dark:text-neutral-300 leading-relaxed break-words opacity-90">
                <MarkdownRenderer
                  content={revealedText}
                  onFileClick={onFileClick}
                  isStreaming={isStreaming}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </ActivityRailItem>
  );
};

/**
 * Memoized: a turn's earlier thoughts are settled text, and the rail re-renders
 * on every streamed token. Only the thought still arriving changes its props.
 */
export const ReasoningRailItem = React.memo(ReasoningRailItemComponent);
