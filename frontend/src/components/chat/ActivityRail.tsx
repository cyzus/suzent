import React, { useEffect, useState } from 'react';
import type { AGUIPart } from '../../hooks/useAGUI';
import type { ContentBlock } from '../../lib/chatUtils';
import { MarkdownRenderer } from './MarkdownRenderer';

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

export function formatActivityToolName(toolName: string | undefined): string {
  return toolName ? toolName.replace(/_/g, ' ') : 'unknown tool';
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
      const pendingTool = [...(chunk.items ?? [])].reverse().find(part => part.state === 'approval-requested' && !part.output);
      if (pendingTool) return `Approval needed: ${formatActivityToolName(pendingTool.toolName)}`;
      const tool = [...(chunk.items ?? [])].reverse().find(part => !part.output || part.state === 'approval-requested');
      if (tool) return `Using ${formatActivityToolName(tool.toolName)}`;
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
    && (chunk.items ?? []).some(part => part.state === 'approval-requested' && !part.output)
  ));
}

export function getLegacyActivityLabel(chunks: Array<{ chunk: { type: string; blocks?: ContentBlock[] } }>, isStreaming: boolean): string | undefined {
  for (let i = chunks.length - 1; i >= 0; i -= 1) {
    const chunk = chunks[i].chunk;
    if (chunk.type === 'toolCall') {
      const pendingTool = [...(chunk.blocks ?? [])].reverse().find(block => block.approvalState === 'pending' && !block.content);
      if (pendingTool) return `Approval needed: ${formatActivityToolName(pendingTool.toolName)}`;
      const tool = [...(chunk.blocks ?? [])].reverse().find(block => !block.content || block.approvalState === 'pending');
      if (tool) return `Using ${formatActivityToolName(tool.toolName)}`;
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
    && (chunk.blocks ?? []).some(block => block.approvalState === 'pending' && !block.content)
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
  const headerLabel = showDuration || isActive
    ? durationLabel
    : currentLabel ?? 'Activity';

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
          <div className="activity-rail min-w-0 w-full">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
};

export const ActivityRailItem: React.FC<{
  state?: 'active' | 'done' | 'neutral' | 'pending';
  children: React.ReactNode;
}> = ({ state = 'neutral', children }) => (
  <div className="activity-rail-item min-w-0">
    <span
      className={`activity-rail-dot ${
        state === 'pending'
          ? 'activity-rail-dot-pending'
          : state === 'active'
          ? 'activity-rail-dot-active'
          : state === 'done'
            ? 'activity-rail-dot-done'
            : ''
      }`}
    />
    <div className={`activity-rail-card ${
      state === 'pending'
        ? 'activity-rail-card-pending'
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
