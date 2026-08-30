import React, { useEffect, useState } from 'react';
import type { AGUIPart } from '../../hooks/useAGUI';
import { useDisclosureBody } from '../../hooks/useDisclosureBody';
import type { ContentBlock } from '../../lib/chatUtils';
import { MarkdownRenderer } from './MarkdownRenderer';
import { getRepeatedToolLabel, getToolSummary, normalizeToolName } from './toolSummary';
import type { ToolTense } from './toolSummary';
import { useTypewriter } from '../../hooks/useTypewriter';
import { tForLocale, useI18n } from '../../i18n';
import { DisclosureChevron } from '../DisclosureChevron';

export type AguiChunkType =
  'tool' | 'reasoning' | 'text' | 'a2ui' | 'acp-permission' | 'acp-notice';

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
  isActivityChunk: (chunk: T) => boolean
): ActivityRenderGroup<T>[] {
  const renderGroups: ActivityRenderGroup<T>[] = [];
  let activityChunks: Array<{ chunk: T; index: number }> = [];

  chunks.forEach((chunk, index) => {
    if (isActivityChunk(chunk)) {
      activityChunks.push({ chunk, index });
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

function findLastIndex<T>(items: T[], predicate: (item: T) => boolean): number {
  for (let i = items.length - 1; i >= 0; i -= 1) {
    if (predicate(items[i])) return i;
  }
  return -1;
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
  return summary.detail ? `${summary.verb} ${summary.detail}` : fallback;
}

const REPEAT_LABEL_THRESHOLD = 3;

/**
 * How many calls to the same tool the run ends with, e.g. ten `run_command`
 * calls in a row. One line saying "Ran 10 commands" beats a label that keeps
 * flickering between ten near-identical command names.
 */
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

/**
 * Status label for the tool the rail is on now: the repeat summary when the
 * same tool has been called several times running, otherwise the single call.
 *
 * `tense` says whether that last call is still in flight, which decides whether
 * the label reads "Running 10 commands" or "Ran 10 commands".
 */
function formatActiveToolLabel(
  toolNames: Array<string | undefined>,
  toolName: string | undefined,
  args: string | undefined,
  tense: ToolTense
): string {
  // Two calls still read fine individually; from three on, the count says more
  // than a label that rewrites itself every second.
  const streak = trailingToolRunLength(toolNames);
  if (streak >= REPEAT_LABEL_THRESHOLD && toolName) {
    return getRepeatedToolLabel(toolName, streak, railT, tense);
  }
  return formatActivityToolName(toolName, args, tense);
}

export function isActionableAguiApproval(part: AGUIPart): boolean {
  return part.state === 'approval-requested' && !part.output && Boolean(part.approvalId);
}

export function getTimestampDeltaSeconds(
  previousTimestamp?: string,
  currentTimestamp?: string
): number | undefined {
  if (!previousTimestamp || !currentTimestamp) return undefined;
  const previousTime = new Date(previousTimestamp).getTime();
  const currentTime = new Date(currentTimestamp).getTime();
  if (!Number.isFinite(previousTime) || !Number.isFinite(currentTime)) return undefined;
  const deltaSeconds = Math.floor((currentTime - previousTime) / 1000);
  return deltaSeconds >= 0 ? deltaSeconds : undefined;
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
      // Count the streak across the whole group, not just this chunk: the
      // agent's own thinking between two shell calls does not make them
      // unrelated pieces of work.
      const items = chunks
        .slice(0, i + 1)
        .flatMap((entry) => (entry.chunk.type === 'tool' ? (entry.chunk.items ?? []) : []));
      // Prefer the call still in flight; once the group has finished, describe
      // what it ended on so a settled rail still says what it did.
      const unfinishedIndex = findLastIndex(
        items,
        (part) => !part.output || part.state === 'approval-requested'
      );
      const toolIndex = unfinishedIndex >= 0 ? unfinishedIndex : items.length - 1;
      if (toolIndex >= 0) {
        const tool = items[toolIndex];
        return formatActiveToolLabel(
          items.slice(0, toolIndex + 1).map((part) => part.toolName),
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
      const unfinishedIndex = findLastIndex(
        blocks,
        (block) => !block.content || block.approvalState === 'pending'
      );
      const toolIndex = unfinishedIndex >= 0 ? unfinishedIndex : blocks.length - 1;
      if (toolIndex >= 0) {
        const tool = blocks[toolIndex];
        return formatActiveToolLabel(
          blocks.slice(0, toolIndex + 1).map((block) => block.toolName),
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

export const ActivityRail: React.FC<{
  children: React.ReactNode;
  itemCount: number;
  durationSeconds?: number;
  startedAtMs?: number;
  showDuration?: boolean;
  defaultExpanded?: boolean;
  /** The turn is still streaming — keeps the worked-for clock running. */
  isActive?: boolean;
  /**
   * This rail is the one the agent is working in right now. A turn that
   * interleaves prose with tool calls renders several rails, and only the last
   * of them is live: the earlier ones are finished work and must not animate.
   */
  isCurrent?: boolean;
  hasPending?: boolean;
  currentLabel?: string;
}> = ({
  children,
  itemCount,
  durationSeconds,
  startedAtMs,
  showDuration = true,
  defaultExpanded = false,
  isActive = false,
  isCurrent = isActive,
  hasPending = false,
  currentLabel,
}) => {
  const [expanded, setExpanded] = useState(defaultExpanded);
  // Once the user has opened or closed a rail themselves, stop steering it —
  // auto-collapsing a rail they deliberately opened is worse than leaving it.
  const userToggledRef = React.useRef(false);
  // Use the caller-provided start time when available so the timer resumes from
  // the original start across remounts (e.g. reconnecting to a stream after a
  // chat switch); otherwise fall back to mount time.
  const startedAtRef = React.useRef(startedAtMs ?? Date.now());
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  // Adopt a later-arriving start time (the prop may be undefined on first render
  // and resolve once the streaming chat's start timestamp is known).
  useEffect(() => {
    if (startedAtMs && startedAtMs !== startedAtRef.current) {
      startedAtRef.current = startedAtMs;
    }
  }, [startedAtMs]);

  // Follow the caller in both directions so a rail the agent has moved past
  // folds itself away instead of leaving the whole turn expanded at once.
  useEffect(() => {
    if (userToggledRef.current) return;
    setExpanded(defaultExpanded);
  }, [defaultExpanded]);

  useEffect(() => {
    if (!isActive) return undefined;
    const updateElapsed = () => {
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAtRef.current) / 1000)));
    };
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(timer);
  }, [isActive]);

  // See useDisclosureBody: the body is not mounted while collapsed, is held one
  // transition past close so the animation still plays, and stays pinned while
  // an approval is pending so a half-typed rejection reason survives.
  const bodyMounted = useDisclosureBody(expanded, { keepMounted: hasPending });

  const displayedSeconds = durationSeconds ?? elapsedSeconds;
  const durationLabel = `Worked for ${formatActivityDuration(displayedSeconds)}`;
  // Only the turn's first rail reports the worked time. When assistant text
  // splits a turn into several rails they all belong to one stretch of work, so
  // the later ones show what is happening instead of starting a second clock.
  const headerLabel = showDuration ? durationLabel : (currentLabel ?? 'Activity');

  return (
    <div className="activity-rail-shell min-w-0 w-full">
      <button
        type="button"
        onClick={() => {
          userToggledRef.current = true;
          setExpanded((value) => !value);
        }}
        className={`activity-rail-header ${
          hasPending && !expanded
            ? 'activity-rail-header-pending'
            : isCurrent && !expanded
              ? 'activity-rail-header-active'
              : ''
        }`}
      >
        <span className="truncate min-w-0">
          {hasPending && !expanded ? (currentLabel ?? 'Approval needed') : headerLabel}
        </span>
        {hasPending && !expanded && <span className="activity-rail-pending-badge">Pending</span>}
        <span className="text-neutral-300 dark:text-neutral-600" aria-hidden="true">
          |
        </span>
        <span className="text-neutral-500 dark:text-neutral-400">
          {itemCount} {itemCount === 1 ? 'step' : 'steps'}
        </span>
        <DisclosureChevron
          expanded={expanded}
          className="w-3 h-3 text-neutral-500 dark:text-neutral-400 transition-transform duration-200"
        />
      </button>
      <div
        className={`grid transition-[grid-template-rows] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)] overflow-hidden ${expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
      >
        <div className="min-h-0 overflow-hidden">
          <div className="activity-rail-scroll min-w-0 w-full">
            <div className="activity-rail min-w-0 w-full">{bodyMounted ? children : null}</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export const ActivityRailItem: React.FC<{
  state?: 'active' | 'done' | 'error' | 'neutral' | 'pending';
  children: React.ReactNode;
}> = ({ state = 'neutral', children }) => (
  <div className="activity-rail-item min-w-0">
    <span
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
                  streamingLite={isStreaming}
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
