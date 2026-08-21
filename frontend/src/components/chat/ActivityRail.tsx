import React, { useEffect, useState } from 'react';
import type { AGUIPart } from '../../hooks/useAGUI';
import type { ContentBlock } from '../../lib/chatUtils';
import { MarkdownRenderer } from './MarkdownRenderer';
import { getRepeatedToolLabel, getToolSummary, normalizeToolName } from './toolSummary';
import { tForLocale } from '../../i18n';

export type ActivityRenderGroup<T> =
  | { type: 'activity'; chunks: Array<{ chunk: T; index: number }> }
  | { type: 'single'; chunk: T; index: number };

export function groupActivityChunks<T>(
  chunks: T[],
  isActivityChunk: (chunk: T) => boolean,
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

export function getActivityGroupOrdinal<T>(groups: ActivityRenderGroup<T>[], index: number): number {
  return groups
    .slice(0, index)
    .filter(group => group.type === 'activity')
    .length;
}

function findLastIndex<T>(items: T[], predicate: (item: T) => boolean): number {
  for (let i = items.length - 1; i >= 0; i -= 1) {
    if (predicate(items[i])) return i;
  }
  return -1;
}

export function getReasoningHeader(text: string, isStreaming: boolean = false): string {
  const firstLine = text.trim().split('\n')[0].replace(/^[#*>-\s]+/, '').replace(/\*\*/g, '').trim();
  const summary = firstLine.length > 80 ? firstLine.substring(0, 77) + '...' : firstLine || 'Processing...';
  const prefix = isStreaming ? 'Thinking' : 'Thought';
  return `${prefix}: ${summary}`;
}

export function countActivityItems(chunks: Array<{ chunk: { type: string; items?: unknown[]; blocks?: unknown[] } }>): number {
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
export function formatActivityToolName(toolName: string | undefined, args?: string): string {
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
  const summary = getToolSummary(toolName, parsed, railT);
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
 */
function formatActiveToolLabel(
  toolNames: Array<string | undefined>,
  toolName: string | undefined,
  args: string | undefined,
): string {
  // Two calls still read fine individually; from three on, the count says more
  // than a label that rewrites itself every second.
  const streak = trailingToolRunLength(toolNames);
  if (streak >= REPEAT_LABEL_THRESHOLD && toolName) return getRepeatedToolLabel(toolName, streak, railT);
  return formatActivityToolName(toolName, args);
}

export function isActionableAguiApproval(part: AGUIPart): boolean {
  return part.state === 'approval-requested' && !part.output && Boolean(part.approvalId);
}

export function getTimestampDeltaSeconds(previousTimestamp?: string, currentTimestamp?: string): number | undefined {
  if (!previousTimestamp || !currentTimestamp) return undefined;
  const previousTime = new Date(previousTimestamp).getTime();
  const currentTime = new Date(currentTimestamp).getTime();
  if (!Number.isFinite(previousTime) || !Number.isFinite(currentTime)) return undefined;
  const deltaSeconds = Math.floor((currentTime - previousTime) / 1000);
  return deltaSeconds >= 0 ? deltaSeconds : undefined;
}

export function getAguiActivityLabel(chunks: Array<{ chunk: { type: string; items?: AGUIPart[] } }>, isStreaming: boolean): string | undefined {
  for (let i = chunks.length - 1; i >= 0; i -= 1) {
    const chunk = chunks[i].chunk;
    if (chunk.type === 'tool') {
      const pendingTool = [...(chunk.items ?? [])].reverse().find(isActionableAguiApproval);
      if (pendingTool) return `Approval needed: ${formatActivityToolName(pendingTool.toolName, pendingTool.args)}`;
      // Count the streak across the whole group, not just this chunk: the
      // agent's own thinking between two shell calls does not make them
      // unrelated pieces of work.
      const items = chunks
        .slice(0, i + 1)
        .flatMap(entry => (entry.chunk.type === 'tool' ? entry.chunk.items ?? [] : []));
      const toolIndex = findLastIndex(items, part => !part.output || part.state === 'approval-requested');
      if (toolIndex >= 0) {
        const tool = items[toolIndex];
        return formatActiveToolLabel(
          items.slice(0, toolIndex + 1).map(part => part.toolName),
          tool.toolName,
          tool.args,
        );
      }
    }
    if (chunk.type === 'reasoning') {
      const text = (chunk.items ?? []).map(part => part.text || '').join('').trim();
      if (text) return getReasoningHeader(text, isStreaming);
    }
  }
  return undefined;
}

export function hasAguiPendingApproval(chunks: Array<{ chunk: { type: string; items?: AGUIPart[] } }>): boolean {
  return chunks.some(({ chunk }) => (
    chunk.type === 'tool'
    && (chunk.items ?? []).some(isActionableAguiApproval)
  ));
}

export function getLegacyActivityLabel(chunks: Array<{ chunk: { type: string; blocks?: ContentBlock[] } }>, isStreaming: boolean): string | undefined {
  for (let i = chunks.length - 1; i >= 0; i -= 1) {
    const chunk = chunks[i].chunk;
    if (chunk.type === 'toolCall') {
      const pendingTool = [...(chunk.blocks ?? [])].reverse().find(block => block.approvalState === 'pending' && !block.content && !!block.approvalId);
      if (pendingTool) return `Approval needed: ${formatActivityToolName(pendingTool.toolName, pendingTool.toolArgs)}`;
      const blocks = chunks
        .slice(0, i + 1)
        .flatMap(entry => (entry.chunk.type === 'toolCall' ? entry.chunk.blocks ?? [] : []));
      const toolIndex = findLastIndex(blocks, block => !block.content || block.approvalState === 'pending');
      if (toolIndex >= 0) {
        const tool = blocks[toolIndex];
        return formatActiveToolLabel(
          blocks.slice(0, toolIndex + 1).map(block => block.toolName),
          tool.toolName,
          tool.toolArgs,
        );
      }
    }
    if (chunk.type === 'reasoning') {
      const text = (chunk.blocks ?? []).map(block => block.content).join('\n').trim();
      if (text) return getReasoningHeader(text, isStreaming);
    }
  }
  return undefined;
}

export function hasLegacyPendingApproval(chunks: Array<{ chunk: { type: string; blocks?: ContentBlock[] } }>): boolean {
  return chunks.some(({ chunk }) => (
    chunk.type === 'toolCall'
    && (chunk.blocks ?? []).some(block => block.approvalState === 'pending' && !block.content && !!block.approvalId)
  ));
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
  isActive?: boolean;
  hasPending?: boolean;
  currentLabel?: string;
}> = ({ children, itemCount, durationSeconds, startedAtMs, showDuration = true, defaultExpanded = false, isActive = false, hasPending = false, currentLabel }) => {
  const [expanded, setExpanded] = useState(defaultExpanded);
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

  useEffect(() => {
    if (defaultExpanded) {
      setExpanded(true);
    }
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

  const displayedSeconds = durationSeconds ?? elapsedSeconds;
  const durationLabel = `Worked for ${formatActivityDuration(displayedSeconds)}`;
  // Only the turn's first rail reports the worked time. When assistant text
  // splits a turn into several rails they all belong to one stretch of work, so
  // the later ones show what is happening instead of starting a second clock.
  const headerLabel = showDuration
    ? durationLabel
    : currentLabel ?? (isActive ? durationLabel : 'Activity');

  return (
    <div className="activity-rail-shell min-w-0 w-full">
      <button
        type="button"
        onClick={() => setExpanded(value => !value)}
        className={`activity-rail-header ${
          hasPending && !expanded
            ? 'activity-rail-header-pending'
            : isActive && !expanded
              ? 'activity-rail-header-active'
              : ''
        }`}
      >
        <span className="truncate min-w-0">
          {hasPending && !expanded
            ? currentLabel ?? 'Approval needed'
            : headerLabel}
        </span>
        {hasPending && !expanded && (
          <span className="activity-rail-pending-badge">Pending</span>
        )}
        <span className="text-neutral-300 dark:text-neutral-600" aria-hidden="true">|</span>
        <span className="text-neutral-500 dark:text-neutral-400">
          {itemCount} {itemCount === 1 ? 'step' : 'steps'}
        </span>
        <svg
          className={`w-3 h-3 text-neutral-500 dark:text-neutral-400 transition-transform duration-200 ${expanded ? 'rotate-90' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={3}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
      </button>
      <div className={`grid transition-[grid-template-rows] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)] overflow-hidden ${expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}>
        <div className="min-h-0 overflow-hidden">
          <div className="activity-rail-scroll min-w-0 w-full">
            <div className="activity-rail min-w-0 w-full">
              {children}
            </div>
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
    <div className={`activity-rail-card ${
      state === 'pending'
        ? 'activity-rail-card-pending'
        : state === 'error'
          ? 'activity-rail-card-error'
        : state === 'active'
          ? 'activity-rail-card-active'
          : ''
    }`}>
      {children}
    </div>
  </div>
);

export const ReasoningRailItem: React.FC<{
  text: string;
  isStreaming?: boolean;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
}> = ({ text, isStreaming, onFileClick }) => {
  const [expanded, setExpanded] = useState(false);
  return (
    <ActivityRailItem state={isStreaming ? 'active' : 'done'}>
      <div className="min-w-0">
        <button
          type="button"
          onClick={() => setExpanded(value => !value)}
          className="group/thought-header inline-flex items-center gap-1.5 px-2.5 cursor-pointer select-none min-w-0 max-w-full"
        >
          <span className="text-[11px] font-mono font-bold uppercase tracking-wide text-neutral-500 dark:text-neutral-400 shrink-0">
            Thought
          </span>
          <svg
            className={`w-3 h-3 text-neutral-400 opacity-0 transition-all duration-150 shrink-0 group-hover/thought-header:opacity-100 ${expanded ? 'rotate-90' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={3}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </button>
        <div className={`grid transition-[grid-template-rows] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)] overflow-hidden ${expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}>
          <div className="min-h-0 overflow-hidden">
            <div className="mt-2 pt-1">
              <div className="text-[13px] md:text-sm text-brutal-black/85 dark:text-neutral-300 leading-relaxed break-words opacity-90">
                <MarkdownRenderer content={text} onFileClick={onFileClick} streamingLite={isStreaming} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </ActivityRailItem>
  );
};
