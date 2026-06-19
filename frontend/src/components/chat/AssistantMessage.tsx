import React, { useState, useEffect, useMemo } from 'react';
import type { Message } from '../../types/api';
import type { AGUIPart, ApprovalRememberScope } from '../../hooks/useAGUI';
import { splitAssistantContent, ContentBlock, formatMessageTime } from '../../lib/chatUtils';
import { ThinkingAnimation, AgentBadge, RobotIcon } from './ThinkingAnimation';
import { MarkdownRenderer } from './MarkdownRenderer';
import { ToolCallBlock } from './ToolCallBlock';
import { SubAgentCallBlock } from './SubAgentCallBlock';
import type { SubAgentStatus } from './SubAgentCallBlock';
import { CopyButton } from './CopyButton';
import { A2UIRenderer } from '../a2ui/A2UIRenderer';
import type { A2UISurface } from '../../types/a2ui';
import {
  StaticContent,
  StepPills,
  StreamingContent,
  ToolSequenceGroup,
  parseSubAgentTaskId,
} from './AssistantContent';
import {
  ActivityRail,
  ActivityRailItem,
  ReasoningRailItem,
  countActivityItems,
  getActivityGroupOrdinal,
  getAguiActivityLabel,
  getLegacyActivityLabel,
  getReasoningHeader,
  getTimestampDeltaSeconds,
  groupActivityChunks,
  hasAguiPendingApproval,
  hasLegacyPendingApproval,
} from './ActivityRail';

const LARGE_MARKDOWN_RENDER_THRESHOLD = 12000;

interface AssistantMessageProps {
  message: Message;
  previousMessageTimestamp?: string;
  messageIndex: number;
  isStreaming: boolean;
  isLastMessage: boolean;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
  /** Streaming usage data */
  usage?: any;
  /** When provided, renders from AG-UI streaming parts instead of legacy HTML parsing */
  aguiParts?: AGUIPart[];
  /** Wall-clock start time (ms) of the active stream, so the activity timer resumes across reconnects */
  streamStartedAtMs?: number;
  /** HITL approval handler: (approvalId, toolCallId, approved, remember?, toolName?) */
  onToolApproval?: (approvalId: string, toolCallId: string, approved: boolean, remember?: ApprovalRememberScope, toolName?: string, actionId?: string, feedback?: string) => void;
  /** Tool approval policy for showing auto-approval badges */
  toolApprovalPolicy?: Record<string, string>;
  /** Callback to remove a tool from auto-approval */
  onRemoveApprovalPolicy?: (toolName: string) => void;
  /** Handler for inline A2UI button actions */
  onInlineAction?: (surfaceId: string, action: string, context: Record<string, unknown>) => void;
  /** Sub-agent task state map: taskId -> status (driven by SSE events) */
  subAgentTasks?: Record<string, { status: SubAgentStatus; resultSummary?: string; error?: string }>;
  /** Open the SubAgentView sidebar for the given task_id */
  onOpenSubAgentSidebar?: (taskId: string) => void;
  /** Stop a running sub-agent */
  onStopSubAgent?: (taskId: string) => void;
  /** Force web context to open right sidebar with specific context */
  onForceWebContext?: (contextId: string) => void;
  /** Retry handler — re-runs the last user message from this point */
  onRetry?: () => void;
}

// Names that should be filtered out from tool call display
const IGNORED_TOOL_NAMES = ['final_answer', 'final answer'];

function isIgnoredToolCall(block: ContentBlock): boolean {
  if (block.type !== 'toolCall') return false;
  const name = (block.toolName || '').toLowerCase();
  return IGNORED_TOOL_NAMES.includes(name);
}

/** Regex to detect raw final_answer(...) calls that leaked into content */
const FINAL_ANSWER_CALL_RE = /^\s*final_answer\s*\([\s\S]*\)\s*$/;

function filterBlocks(blocks: ContentBlock[]): ContentBlock[] {
  return blocks
    .filter(b => !isIgnoredToolCall(b))
    .filter(b => {
      // Strip markdown blocks that are just raw final_answer(...) calls
      if (b.type === 'markdown' && FINAL_ANSWER_CALL_RE.test(b.content.trim())) return false;
      // Strip code blocks that only call final_answer
      if (b.type === 'code' && /^\s*final_answer\s*\(/i.test(b.content.trim())) return false;
      return true;
    });
}

/** Check if a message consists only of toolCall/codeStep blocks (no real prose/code content) */
function isToolOnlyMessage(blocks: ContentBlock[]): boolean {
  return blocks.length > 0 && blocks.every(b => b.type === 'toolCall' || b.type === 'codeStep');
}

// ── AG-UI Parts-based rendering (for streaming messages) ────────────

const AGUIPartsContent: React.FC<{
  parts: AGUIPart[];
  messageIndex: number;
  workedDurationSeconds?: number;
  streamStartedAtMs?: number;
  isStreaming?: boolean;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
  onToolApproval?: (approvalId: string, toolCallId: string, approved: boolean, remember?: ApprovalRememberScope, toolName?: string, actionId?: string, feedback?: string) => void;
  toolApprovalPolicy?: Record<string, string>;
  onRemoveApprovalPolicy?: (toolName: string) => void;
  onInlineAction?: (surfaceId: string, action: string, context: Record<string, unknown>) => void;
  subAgentTasks?: Record<string, { status: SubAgentStatus; resultSummary?: string; error?: string }>;
  onOpenSubAgentSidebar?: (taskId: string) => void;
  onStopSubAgent?: (taskId: string) => void;
  onForceWebContext?: (contextId: string) => void;
}> = ({ parts, messageIndex, workedDurationSeconds, streamStartedAtMs, isStreaming, onFileClick, onToolApproval, toolApprovalPolicy, onRemoveApprovalPolicy, onInlineAction, subAgentTasks, onOpenSubAgentSidebar, onStopSubAgent, onForceWebContext }) => {
  // Normalize tool parts: when resume/recovery emits another tool part with the
  // same toolCallId later in the stream, merge it into the first occurrence so
  // output stays under the initial tool call instead of rendering a split block.
  const normalizedParts = useMemo<AGUIPart[]>(() => {
    const result: AGUIPart[] = [];
    const toolIndexById = new Map<string, number>();
    for (const part of parts) {
      if (part.type === 'tool' && part.toolCallId) {
        const existingIndex = toolIndexById.get(part.toolCallId);
        if (existingIndex !== undefined) {
          const existing = result[existingIndex];
          result[existingIndex] = {
            ...existing,
            ...part,
            // Prefer freshest non-empty payload fields.
            toolName: part.toolName || existing.toolName,
            args: part.args ?? existing.args,
            output: part.output ?? existing.output,
            approvalId: part.approvalId ?? existing.approvalId,
            permission: part.permission ?? existing.permission,
            state: part.state ?? existing.state,
          };
          continue;
        }
        toolIndexById.set(part.toolCallId, result.length);
      }
      result.push(part);
    }
    return result;
  }, [parts]);

  // Group consecutive parts of the same type into chunks
  const chunks: { type: 'tool' | 'reasoning' | 'text' | 'a2ui'; items: AGUIPart[] }[] = [];
  let current: AGUIPart[] = [];
  let currentType: 'tool' | 'reasoning' | 'text' | 'a2ui' | null = null;

  for (const part of normalizedParts) {
    const type = part.type as 'tool' | 'reasoning' | 'text' | 'a2ui';
    if (current.length === 0) {
      currentType = type;
      current.push(part);
    } else if (currentType === type) {
      current.push(part);
    } else {
      if (currentType) {
        chunks.push({ type: currentType, items: current });
      }
      currentType = type;
      current = [part];
    }
  }
  if (current.length > 0 && currentType) {
    chunks.push({ type: currentType, items: current });
  }

  const renderGroups = groupActivityChunks(
    chunks,
    chunk => chunk.type === 'tool' || chunk.type === 'reasoning',
  );

  return (
    <>
      {renderGroups.map((group, gi) => {
        if (group.type === 'activity') {
          const activityGroupOrdinal = getActivityGroupOrdinal(renderGroups, gi);
          return (
            <ActivityRail
              key={`activity-${gi}`}
              itemCount={countActivityItems(group.chunks)}
              durationSeconds={workedDurationSeconds}
              startedAtMs={activityGroupOrdinal === 0 ? streamStartedAtMs : undefined}
              showDuration={activityGroupOrdinal === 0}
              defaultExpanded={Boolean(isStreaming)}
              isActive={Boolean(isStreaming)}
              hasPending={hasAguiPendingApproval(group.chunks)}
              currentLabel={getAguiActivityLabel(group.chunks, Boolean(isStreaming))}
            >
              {group.chunks.map(({ chunk, index: ci }) => {
                if (chunk.type === 'reasoning') {
                  const reasoningText = chunk.items.map(p => p.text || '').join('');
                  if (!reasoningText.trim()) return null;
                  const isChunkStreaming = isStreaming && ci === chunks.length - 1;
                  return (
                    <ReasoningRailItem
                      key={`reasoning-${ci}`}
                      text={reasoningText}
                      isStreaming={isChunkStreaming}
                      onFileClick={onFileClick}
                    />
                  );
                }

                const tools = chunk.items.map((tp, ti) => {
                  // A historical approval snapshot without an actionable ID is
                  // unresolved/stale, not proof that the user denied the call.
                  const isActionablyPending = tp.state === 'approval-requested' && !tp.output && !!tp.approvalId && !!isStreaming;
                  const approvalState = isActionablyPending ? 'pending' as const
                    : tp.state === 'error' ? 'denied' as const
                      : undefined;

                  return {
                    toolCallId: tp.toolCallId || `tool-${ci}-${ti}`,
                    toolName: tp.toolName || 'unknown',
                    toolArgs: tp.args || undefined,
                    output: tp.output || undefined,
                    approvalState,
                    permission: tp.permission,
                    onApprove: (isActionablyPending && tp.approvalId && onToolApproval)
                      ? (remember: ApprovalRememberScope, actionId?: string, feedback?: string) => onToolApproval(tp.approvalId!, tp.toolCallId || '', true, remember, tp.toolName, actionId, feedback)
                      : undefined,
                    onDeny: (isActionablyPending && tp.approvalId && onToolApproval)
                      ? (actionId?: string, feedback?: string) => onToolApproval(tp.approvalId!, tp.toolCallId || '', false, null, tp.toolName, actionId, feedback)
                      : undefined,
                  };
                });

                return tools.map((t, i) => {
                  const itemState = t.approvalState === 'pending'
                    ? 'pending' as const
                    : t.approvalState === 'denied'
                      ? 'error' as const
                    : isStreaming && !t.output
                      ? 'active' as const
                      : t.output
                      ? 'done' as const
                      : 'neutral' as const;

                  if (t.toolName === 'agent') {
                    const taskId = parseSubAgentTaskId(t.output);
                    const taskState = taskId ? subAgentTasks?.[taskId] : undefined;
                    const args = t.toolArgs ? (() => { try { return JSON.parse(t.toolArgs!); } catch { return {}; } })() : {};
                    const defaultStatus = t.approvalState === 'pending' ? 'queued'
                      : t.output ? 'completed'
                      : 'running';
                    return (
                      <ActivityRailItem key={t.toolCallId || `sa-${ci}-${i}`} state={itemState}>
                        <SubAgentCallBlock
                          taskId={taskId}
                          description={args.description}
                          toolsAllowed={args.tools_allowed}
                          status={taskState?.status ?? defaultStatus}
                          resultSummary={taskState?.resultSummary}
                          error={taskState?.error}
                          onOpenSidebar={onOpenSubAgentSidebar}
                          onStop={onStopSubAgent}
                        />
                      </ActivityRailItem>
                    );
                  }

                  const isAutoApproved = toolApprovalPolicy?.[t.toolName] === 'always_allow';
                  return (
                    <ActivityRailItem key={t.toolCallId || `tool-${ci}-${i}`} state={itemState}>
                      <ToolCallBlock
                        toolName={t.toolName}
                        toolArgs={t.toolArgs}
                        output={t.output}
                        defaultCollapsed={t.approvalState !== 'pending'}
                        approvalState={t.approvalState}
                        isStreaming={isStreaming && !t.output}
                        onApprove={t.onApprove}
                        onDeny={t.onDeny}
                        permission={t.permission}
                        isAutoApproved={isAutoApproved}
                        onRemovePolicy={isAutoApproved && onRemoveApprovalPolicy ? () => onRemoveApprovalPolicy(t.toolName) : undefined}
                        onForceWebContext={onForceWebContext}
                        toolCallId={t.toolCallId}
                        inActivityRail
                      />
                    </ActivityRailItem>
                  );
                });
              })}
            </ActivityRail>
          );
        }

        const { chunk, index: ci } = group;
        if (chunk.type === 'tool') {
          const tools = chunk.items.map((tp, ti) => {
            // A historical approval snapshot without an actionable ID is
            // unresolved/stale, not proof that the user denied the call.
            const isActionablyPending = tp.state === 'approval-requested' && !tp.output && !!tp.approvalId && !!isStreaming;
            const approvalState = isActionablyPending ? 'pending' as const
              : tp.state === 'error' ? 'denied' as const
                : undefined;

            return {
              toolCallId: tp.toolCallId || `tool-${ci}-${ti}`,
              toolName: tp.toolName || 'unknown',
              toolArgs: tp.args || undefined,
              output: tp.output || undefined,
              approvalState,
              onApprove: (isActionablyPending && tp.approvalId && onToolApproval)
                ? (remember: ApprovalRememberScope, actionId?: string, feedback?: string) => onToolApproval(tp.approvalId!, tp.toolCallId || '', true, remember, tp.toolName, actionId, feedback)
                : undefined,
              onDeny: (isActionablyPending && tp.approvalId && onToolApproval)
                ? (actionId?: string, feedback?: string) => onToolApproval(tp.approvalId!, tp.toolCallId || '', false, null, tp.toolName, actionId, feedback)
                : undefined,
            };
          });

          // Separate agent calls from regular tool calls
          const subAgentTools = tools.filter(t => t.toolName === 'agent');
          const regularTools = tools.filter(t => t.toolName !== 'agent');

          return (
            <div key={ci} className="pl-1 min-w-0 overflow-x-hidden">
              {subAgentTools.map((t, i) => {
                const taskId = parseSubAgentTaskId(t.output);
                const taskState = taskId ? subAgentTasks?.[taskId] : undefined;
                const args = t.toolArgs ? (() => { try { return JSON.parse(t.toolArgs!); } catch { return {}; } })() : {};
                // If output exists, the tool call returned — default to 'completed'.
                // This correctly handles linear (synchronous) subagents that run inline
                // without emitting SSE events. Polling will correct if the backend
                // reports a different status (e.g. background agent still in-flight).
                const defaultStatus = t.approvalState === 'pending' ? 'queued'
                  : t.output ? 'completed'
                  : 'running';
                return (
                  <SubAgentCallBlock
                    key={t.toolCallId || `sa-${i}`}
                    taskId={taskId}
                    description={args.description}
                    toolsAllowed={args.tools_allowed}
                    status={taskState?.status ?? defaultStatus}
                    resultSummary={taskState?.resultSummary}
                    error={taskState?.error}
                    onOpenSidebar={onOpenSubAgentSidebar}
                    onStop={onStopSubAgent}
                  />
                );
              })}
              {regularTools.length > 0 && (
                <ToolSequenceGroup tools={regularTools} isStreaming={isStreaming} toolApprovalPolicy={toolApprovalPolicy} onRemoveApprovalPolicy={onRemoveApprovalPolicy} onForceWebContext={onForceWebContext} />
              )}
            </div>
          );
        }

        if (chunk.type === 'reasoning') {
          const reasoningText = chunk.items.map(p => p.text || '').join('');
          if (!reasoningText.trim()) return null;
          const isChunkStreaming = isStreaming && ci === chunks.length - 1;
          const header = getReasoningHeader(reasoningText, !!isChunkStreaming);

          return (
            <div key={ci} className="my-1.5 min-w-0 w-full pl-1">
              <details className="group">
                <summary className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-mono font-bold tracking-wide uppercase border-2 rounded-sm transition-all select-none cursor-pointer max-w-full ${
                  isChunkStreaming 
                    ? 'brutal-running-mono !text-brutal-black dark:!text-white border-brutal-black dark:border-white shadow-[2px_2px_0px_#000] dark:shadow-[2px_2px_0px_#fff]' 
                    : 'bg-transparent text-neutral-600 dark:text-neutral-400 border-neutral-400 dark:border-zinc-600 hover:border-brutal-black dark:hover:border-white hover:text-brutal-black dark:hover:text-white hover:shadow-[2px_2px_0px_#000] dark:hover:shadow-[2px_2px_0px_#fff]'
                }`}>
                  <span className="truncate flex items-center gap-1.5 flex-1 min-w-0 font-mono">
                    {header}
                  </span>
                </summary>
                <div className="mt-1.5 p-4 bg-neutral-50 dark:bg-zinc-900 border-2 rounded-sm border-brutal-black dark:border-white w-full overflow-x-hidden shadow-[2px_2px_0px_#000] dark:shadow-[2px_2px_0px_#fff]">
                  <div className="text-[13px] md:text-sm text-brutal-black/90 dark:text-neutral-300 leading-relaxed break-words opacity-90">
                    <MarkdownRenderer content={reasoningText} onFileClick={onFileClick} streamingLite={isChunkStreaming} />
                  </div>
                </div>
              </details>
            </div>
          );
        }

        if (chunk.type === 'a2ui') {
          return (
            <React.Fragment key={ci}>
              {chunk.items.map((p, pi) => {
                const surface = p.surface as A2UISurface | undefined;
                if (!surface) return null;
                return (
                  <div key={pi} className="my-2">
                    <A2UIRenderer
                      component={surface.component}
                      onAction={(action, context) => onInlineAction?.(surface.id, action, context ?? {})}
                    />
                  </div>
                );
              })}
            </React.Fragment>
          );
        }

        // Text chunk
        const fullText = chunk.items.map(p => p.text || '').join('');
        const isLastChunk = ci === chunks.length - 1;
        if (!fullText.trim() && !isLastChunk) return null;
        return (
          <div key={ci} className="border-3 border-brutal-black shadow-brutal-lg bg-white dark:bg-zinc-800 px-6 py-5 relative">
            <div className="space-y-4">
              <MarkdownRenderer content={fullText} onFileClick={onFileClick} streamingLite={Boolean(isStreaming && isLastChunk)} />
              {isStreaming && isLastChunk && (
                <span className="animate-brutal-blink inline-block w-2.5 h-4 bg-brutal-black align-middle ml-1" />
              )}
            </div>
          </div>
        );
      })}
    </>
  );
};

const RetryButton: React.FC<{ onClick: () => void; className?: string }> = ({ onClick, className }) => {
  const [retrying, setRetrying] = useState(false);

  const handleClick = async () => {
    if (retrying) return;
    setRetrying(true);
    try {
      await onClick();
    } finally {
      setRetrying(false);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={retrying}
      title="Retry"
      className={`group/retry w-6 h-6 flex items-center justify-center bg-transparent text-neutral-400 hover:text-brutal-black dark:hover:text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${className ?? ''}`}
    >
      <svg
        className={`w-3.5 h-3.5 transition-transform duration-300 ${retrying ? 'animate-spin' : 'group-hover/retry:-rotate-180'}`}
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2.5}
      >
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h5M20 20v-5h-5M4 9a9 9 0 0115-3M20 15a9 9 0 01-15 3" />
      </svg>
    </button>
  );
};

export const AssistantMessage: React.FC<AssistantMessageProps> = ({
  message,
  previousMessageTimestamp,
  messageIndex,
  isStreaming,
  isLastMessage,
  onFileClick,
  aguiParts,
  streamStartedAtMs,
  onToolApproval,
  usage,
  toolApprovalPolicy,
  onRemoveApprovalPolicy,
  onInlineAction,
  subAgentTasks,
  onOpenSubAgentSidebar,
  onStopSubAgent,
  onForceWebContext,
  onRetry,
}) => {
  const isStreamingThis = isStreaming && isLastMessage;
  const effectiveParts = aguiParts ?? message.parts;
  const hasParts = effectiveParts && effectiveParts.length > 0;
  const isThinking = isStreamingThis && !message.content && !hasParts;
  const workedDurationSeconds = useMemo(
    () => getTimestampDeltaSeconds(previousMessageTimestamp, message.timestamp),
    [previousMessageTimestamp, message.timestamp],
  );
  const legacyBlocks = useMemo(
    () => (effectiveParts === undefined ? filterBlocks(splitAssistantContent(message.content || '')) : []),
    [effectiveParts, message.content],
  );

  // Suppress the streaming cursor during the assembly→reveal animation.
  // Delay showing the cursor so it doesn't flash while the box is still opening.
  const [cursorReady, setCursorReady] = useState(!isStreamingThis);

  useEffect(() => {
    if (isStreamingThis && !cursorReady) {
      // Wait for assembly + reveal animation to complete before showing cursor
      const timer = setTimeout(() => setCursorReady(true), 900);
      return () => clearTimeout(timer);
    }
    if (!isStreamingThis) {
      setCursorReady(true);
    }
  }, [isStreamingThis, cursorReady]);

  // ── Compute full message text for copying ──
  const fullMessageText = useMemo(() => {
    if (effectiveParts) {
      return effectiveParts
        .filter(p => p.type === 'text')
        .map(p => p.text || '')
        .join('')
        .trim();
    } else {
      return legacyBlocks
        .filter(b => b.type !== 'log' && b.type !== 'reasoning' && b.type !== 'toolCall' && b.type !== 'a2ui')
        .map(b => (b.type === 'code' ? '```' + (b.lang || '') + '\n' + b.content + '\n```' : b.content))
        .join('\n\n')
        .trim();
    }
  }, [effectiveParts, legacyBlocks]);

  // 1. 抓取当前正在跑的 Tool 和 错误状态
  let currentToolName: string | undefined = undefined;
  let hasError: boolean = false;
  let isPendingApproval: boolean = false;

  if (effectiveParts && effectiveParts.length > 0) {
    hasError = effectiveParts.some(p => p.type === 'tool' && p.state === 'error');
    isPendingApproval = effectiveParts.some(p => p.type === 'tool' && p.state === 'approval-requested');

    // 优先找正在 running 的 tool
    const runningTool = effectiveParts.find(p => p.type === 'tool' && !p.output);
    if (runningTool) {
      currentToolName = runningTool.toolName;
    } else {
      // 没有正在运行的，看最后一个 block 是不是 tool (做完了但没新东西)
      const lastPart = effectiveParts[effectiveParts.length - 1];
      if (lastPart && lastPart.type === 'tool') {
        currentToolName = lastPart.toolName;
      }
    }
  } else {
    // For legacy blocks, check if there's a pending tool call
    isPendingApproval = legacyBlocks.some(b => b.type === 'toolCall' && b.approvalState === 'pending');
  }

  // 2. 核心动画容器 (丝滑形变 UI)
  const isHistory = !isLastMessage && !isPendingApproval;
  const badgeContainer = (
    <div className={`
      relative overflow-hidden transition-all duration-500 ease-[cubic-bezier(0.4,0,0.2,1)]
      ml-0 mr-auto
      ${isThinking
        ? 'w-[400px] h-[80px] bg-white dark:bg-zinc-800 border-3 border-brutal-black shadow-brutal-lg mb-3'
        : isHistory
          ? 'w-[75px] h-[24px] bg-transparent border-0 border-transparent shadow-none mb-1 mt-1' // 变成历史记录的样式
          : 'w-[90px] h-[40px] bg-white dark:bg-zinc-800 border-3 border-brutal-black shadow-brutal-lg mb-3'
      }
    `}>
      {/* 活跃状态：动态机器人 */}
      <div className={`
        absolute inset-0 transition-all duration-500 
        ${isHistory ? 'opacity-0 scale-75 pointer-events-none' : 'opacity-100 scale-100'}
      `}>
        <ThinkingAnimation isThinking={isThinking} />
        <AgentBadge 
          isThinking={isThinking} 
          isStreaming={isStreamingThis} 
          currentToolName={currentToolName}
          hasError={hasError}
          isPendingApproval={isPendingApproval}
        />
      </div>

      {/* 历史状态：静态小图标 */}
      <div className={`
        absolute inset-0 flex items-center gap-1.5 text-neutral-400 dark:text-neutral-500
        transition-all duration-700 ease-[cubic-bezier(0.34,1.56,0.64,1)]
        ${isHistory ? 'opacity-100 scale-100 translate-x-0' : 'opacity-0 scale-50 -translate-x-4 pointer-events-none'}
      `}>
        <RobotIcon className={`w-4 h-4 transition-transform duration-700 ${isHistory ? 'rotate-0' : '-rotate-90'}`} />
        <span className="text-[10px] font-mono font-bold uppercase tracking-wider">
          Suzent
        </span>
      </div>
    </div>
  );

  // ── AG-UI parts-based rendering path (for streaming messages) ──
  if (effectiveParts !== undefined) {
    return (
      <div className="group w-full max-w-4xl break-all overflow-x-hidden text-sm leading-relaxed relative pr-4 md:pr-12 animate-brutal-pop">
        {/* Badge/Assembly Container */}
        {badgeContainer}

        <div className={`grid transition-[grid-template-rows] duration-500 ease-out ${isThinking ? 'grid-rows-[0fr]' : 'grid-rows-[1fr]'}`}>
          <div className="overflow-hidden min-h-0 min-w-0 flex flex-col space-y-3 pr-2 pb-2">
            {hasParts ? (
              <AGUIPartsContent
                parts={effectiveParts}
                messageIndex={messageIndex}
                workedDurationSeconds={workedDurationSeconds}
                streamStartedAtMs={streamStartedAtMs}
                isStreaming={isStreamingThis}
                onFileClick={onFileClick}
                onToolApproval={onToolApproval}
                toolApprovalPolicy={toolApprovalPolicy}
                onRemoveApprovalPolicy={onRemoveApprovalPolicy}
                onInlineAction={onInlineAction}
                subAgentTasks={subAgentTasks}
                onOpenSubAgentSidebar={onOpenSubAgentSidebar}
                onStopSubAgent={onStopSubAgent}
                onForceWebContext={onForceWebContext}
              />
            ) : null}
            <div className="flex items-center gap-2 mt-2 pl-1">
              {fullMessageText && !isThinking && (
                <CopyButton text={fullMessageText} className="relative" />
              )}
              {onRetry && !isStreamingThis && !isThinking && (
                <RetryButton onClick={onRetry} />
              )}
              {message.timestamp && !isStreamingThis && (
                <div className="text-[10px] text-neutral-400 select-none">
                  {formatMessageTime(message.timestamp)}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Legacy HTML rendering path (for historical store messages) ──

  // Don't render empty messages unless we're actively streaming
  if (!isStreamingThis && !message.content?.trim()) {
    return null;
  }

  const blocks = legacyBlocks;

  // If after filtering there are no blocks (e.g. only final_answer tool call), don't render
  if (!isStreamingThis && blocks.length === 0) {
    return null;
  }

  // Detect tool-only messages — but agent tool always needs StaticContent
  // because it renders SubAgentCallBlock, not a step pill.
  const hasSubAgentCall = blocks.some(b => b.type === 'toolCall' && b.toolName === 'agent');
  const toolOnly = !isStreamingThis && isToolOnlyMessage(blocks) && !hasSubAgentCall;

  if (toolOnly) {
    return (
      <div className="group w-full max-w-4xl break-all overflow-x-hidden text-sm leading-relaxed relative pr-4 md:pr-12 animate-brutal-pop">
        {badgeContainer}
        <div className="pl-1 pr-2 pb-1">
          <StepPills
            blocks={blocks}
            messageIndex={messageIndex}
            onToolApproval={onToolApproval}
            toolApprovalPolicy={toolApprovalPolicy}
            onRemoveApprovalPolicy={onRemoveApprovalPolicy}
            onForceWebContext={onForceWebContext}
          />
        </div>
      </div>
    );
  }

  // Chunk blocks into alternating contiguous groups of "content" and "step"
  const chunks: { type: string; blocks: ContentBlock[] }[] = [];
  let currentGroup: ContentBlock[] = [];
  let currentType = '';

  for (const b of blocks) {
    const isStep = b.type === 'toolCall';
    const isReasoning = b.type === 'reasoning';
    // Use the type directly for chunking to preserve interleaved order
    const type = (b.type === 'markdown' || b.type === 'code' || b.type === 'log') ? 'content' : b.type === 'a2ui' ? 'a2ui' : b.type;

    if (currentGroup.length === 0) {
      currentType = type;
      currentGroup.push(b);
    } else if (currentType === type) {
      currentGroup.push(b);
    } else {
      chunks.push({ type: currentType, blocks: currentGroup });
      currentType = type;
      currentGroup = [b];
    }
  }
  if (currentGroup.length > 0) {
    chunks.push({ type: currentType, blocks: currentGroup });
  }

  // Filter out empty content chunks, unless it's the active streaming head
  const validChunks = chunks.filter((chunk, idx) => {
    if (chunk.type !== 'content') return true;
    const hasText = chunk.blocks.some(b => b.content.trim().length > 0);
    const isLastAndStreaming = isStreamingThis && idx === chunks.length - 1;
    return hasText || isLastAndStreaming;
  });

  if (validChunks.length === 0 && !isStreamingThis) {
    return null;
  }

  const legacyRenderGroups = groupActivityChunks(
    validChunks,
    chunk => chunk.type === 'reasoning' || chunk.type === 'toolCall',
  );

  return (
    <div className="group w-full max-w-4xl break-all overflow-x-hidden text-sm leading-relaxed relative pr-4 md:pr-12 animate-brutal-pop">
      {/* Badge/Assembly Container is rendered at the top of the entire message timeline */}
      {badgeContainer}

      <div className={`grid transition-[grid-template-rows] duration-500 ease-out ${isThinking ? 'grid-rows-[0fr]' : 'grid-rows-[1fr]'}`}>
        <div className="overflow-hidden min-h-0 flex flex-col space-y-3 pr-2 pb-2">
          {legacyRenderGroups.map((group, groupIndex) => {
            if (group.type === 'activity') {
              const activityGroupOrdinal = getActivityGroupOrdinal(legacyRenderGroups, groupIndex);
              return (
                <ActivityRail
                  key={`legacy-activity-${groupIndex}`}
                  itemCount={countActivityItems(group.chunks)}
                  durationSeconds={workedDurationSeconds}
                  showDuration={activityGroupOrdinal === 0}
                  defaultExpanded={isStreamingThis}
                  isActive={isStreamingThis}
                  hasPending={hasLegacyPendingApproval(group.chunks)}
                  currentLabel={getLegacyActivityLabel(group.chunks, isStreamingThis)}
                >
                  {group.chunks.map(({ chunk, index: idx }) => {
                    if (chunk.type === 'reasoning') {
                      const isChunkStreaming = isStreamingThis && idx === validChunks.length - 1;
                      return chunk.blocks.map((rb, ri) => (
                        <ReasoningRailItem
                          key={`legacy-reasoning-${idx}-${ri}`}
                          text={rb.content}
                          isStreaming={isChunkStreaming && ri === chunk.blocks.length - 1}
                          onFileClick={onFileClick}
                        />
                      ));
                    }

                    return chunk.blocks.map((b, bi) => {
                      const isPending = b.approvalState === 'pending' && !b.content;
                      const isActive = isStreamingThis && !b.content;
                      const isDenied = b.approvalState === 'denied';
                      const isDone = Boolean(b.content);
                      return (
                        <ActivityRailItem
                          key={`legacy-tool-${idx}-${bi}`}
                          state={isPending ? 'pending' : isDenied ? 'error' : isActive ? 'active' : isDone ? 'done' : 'neutral'}
                        >
                          <StaticContent
                            blocks={[b]}
                            messageIndex={messageIndex}
                            onFileClick={onFileClick}
                            onToolApproval={onToolApproval}
                            toolApprovalPolicy={toolApprovalPolicy}
                            onRemoveApprovalPolicy={onRemoveApprovalPolicy}
                            onInlineAction={onInlineAction}
                            subAgentTasks={subAgentTasks}
                            onOpenSubAgentSidebar={onOpenSubAgentSidebar}
                            onStopSubAgent={onStopSubAgent}
                            onForceWebContext={onForceWebContext}
                            inActivityRail
                          />
                        </ActivityRailItem>
                      );
                    });
                  })}
                </ActivityRail>
              );
            }

            const { chunk, index: idx } = group;
            if (chunk.type === 'reasoning') {
              const isChunkStreaming = isStreamingThis && idx === validChunks.length - 1;
              return (
                <div key={idx} className="flex flex-col space-y-2">
                  {chunk.blocks.map((rb, ri) => (
                    <div key={`rb-${idx}-${ri}`} className="my-1.5 min-w-0 w-full pl-1">
                      <details className="group">
                        <summary className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-mono font-bold tracking-wide uppercase border-2 rounded-sm transition-all select-none cursor-pointer max-w-full ${
                          isChunkStreaming 
                            ? 'brutal-running-mono !text-brutal-black dark:!text-white border-brutal-black dark:border-white shadow-[2px_2px_0px_#000] dark:shadow-[2px_2px_0px_#fff]' 
                            : 'bg-transparent text-neutral-600 dark:text-neutral-400 border-neutral-400 dark:border-zinc-600 hover:border-brutal-black dark:hover:border-white hover:text-brutal-black dark:hover:text-white hover:shadow-[2px_2px_0px_#000] dark:hover:shadow-[2px_2px_0px_#fff]'
                        }`}>
                          <span className="truncate flex items-center gap-1.5 flex-1 min-w-0 font-mono">
                            {getReasoningHeader(rb.content, !!isChunkStreaming)}
                          </span>
                        </summary>
                        <div className="mt-1.5 p-4 bg-neutral-50 dark:bg-zinc-900 border-2 rounded-sm border-brutal-black dark:border-white w-full overflow-x-hidden shadow-[2px_2px_0px_#000] dark:shadow-[2px_2px_0px_#fff]">
                          <div className="text-[13px] md:text-sm text-brutal-black/90 dark:text-neutral-300 leading-relaxed break-words opacity-90">
                            <MarkdownRenderer
                              content={rb.content}
                              onFileClick={onFileClick}
                              streamingLite={(isChunkStreaming && ri === chunk.blocks.length - 1) || rb.content.length > LARGE_MARKDOWN_RENDER_THRESHOLD}
                            />
                          </div>
                        </div>
                      </details>
                    </div>
                  ))}
                </div>
              );
            }

            if (chunk.type === 'toolCall') {
              const subAgentBlocks = chunk.blocks.filter(b => b.toolName === 'agent');
              const regularBlocks = chunk.blocks.filter(b => b.toolName !== 'agent');
              return (
                <div key={idx} className="flex flex-col space-y-2">
                  {subAgentBlocks.length > 0 && (
                    <div className="pl-1">
                      <StaticContent blocks={subAgentBlocks} messageIndex={messageIndex} onFileClick={onFileClick} onToolApproval={onToolApproval} toolApprovalPolicy={toolApprovalPolicy} onRemoveApprovalPolicy={onRemoveApprovalPolicy} onInlineAction={onInlineAction} subAgentTasks={subAgentTasks} onOpenSubAgentSidebar={onOpenSubAgentSidebar} onStopSubAgent={onStopSubAgent} />
                    </div>
                  )}
                  {regularBlocks.length > 0 && (
                    <div className="pl-1">
                      <StepPills blocks={regularBlocks} messageIndex={messageIndex} isStreaming={isStreamingThis} onToolApproval={onToolApproval} toolApprovalPolicy={toolApprovalPolicy} onRemoveApprovalPolicy={onRemoveApprovalPolicy} />
                    </div>
                  )}
                </div>
              );
            }

            if (chunk.type === 'a2ui') {
              return (
                <div key={idx} className="flex flex-col space-y-2">
                  {chunk.blocks.map((b, bi) => {
                    const surface = b.a2uiSurface as A2UISurface | undefined;
                    if (!surface) return null;
                    return (
                      <div key={bi} className="my-2">
                        <A2UIRenderer
                          component={surface.component}
                          onAction={(action, context) => onInlineAction?.(surface.id, action, context ?? {})}
                        />
                      </div>
                    );
                  })}
                </div>
              );
            }

            const cleanContent = chunk.blocks
              .filter(b => b.type !== 'log' && b.type !== 'reasoning')
              .map(b => (b.type === 'code' ? '```' + (b.lang || '') + '\n' + b.content + '\n```' : b.content))
              .join('').trim();

            const isThought = cleanContent.startsWith('Thought:');
            const hasStepInfo = !!message.stepInfo;
            const showCopyButton = cleanContent && !isThought && !hasStepInfo;
            const isLastChunk = idx === validChunks.length - 1;
            const isStreamingChunk = isStreamingThis && isLastChunk;

            // For non-step chunks, filter out reasoning (should only appear in step chunks)
            const contentBlocks = chunk.type === 'reasoning' || chunk.type === 'toolCall'
              ? chunk.blocks
              : chunk.blocks.filter(b => b.type !== 'reasoning');

            return (
              <div key={idx} className="border-3 border-brutal-black shadow-brutal-lg bg-white dark:bg-zinc-800 px-6 py-5 relative">
                <div className="space-y-4">
                  {isStreamingChunk ? (
                    <StreamingContent blocks={contentBlocks} messageIndex={messageIndex} showCursor={cursorReady} onFileClick={onFileClick} />
                  ) : (
                    <StaticContent blocks={contentBlocks} messageIndex={messageIndex} onFileClick={onFileClick} onToolApproval={onToolApproval} toolApprovalPolicy={toolApprovalPolicy} onRemoveApprovalPolicy={onRemoveApprovalPolicy} onInlineAction={onInlineAction} subAgentTasks={subAgentTasks} onOpenSubAgentSidebar={onOpenSubAgentSidebar} onStopSubAgent={onStopSubAgent} />
                  )}
                </div>
              </div>
            );
          })}
          <div className="flex items-center gap-2 mt-2 pl-1">
            {fullMessageText && !isThinking && (
              <CopyButton text={fullMessageText} className="relative" />
            )}
            {onRetry && !isStreamingThis && !isThinking && (
              <RetryButton onClick={onRetry} />
            )}
            {message.timestamp && !isStreamingThis && (
              <div className="text-[10px] text-neutral-400 select-none">
                {formatMessageTime(message.timestamp)}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
