import React, { useState, useEffect, useMemo } from 'react';
import type { Message } from '../../types/api';
import type { AGUIPart, ApprovalRememberScope } from '../../hooks/useAGUI';
import { splitAssistantContent, generateBlockKey, ContentBlock, formatMessageTime } from '../../lib/chatUtils';
import { useTypewriter } from '../../hooks/useTypewriter';
import { ThinkingAnimation, AgentBadge, RobotIcon } from './ThinkingAnimation';
import { MarkdownRenderer } from './MarkdownRenderer';
import { LogBlock } from './LogBlock';
import { ToolCallBlock } from './ToolCallBlock';
import { SubAgentCallBlock } from './SubAgentCallBlock';
import type { SubAgentStatus } from './SubAgentCallBlock';
import { ToolGroupIcon } from './toolGroupIcon';
import { CodeBlockComponent } from './CodeBlockComponent';
import { CopyButton } from './CopyButton';
import { RobotAvatar } from './RobotAvatar';
import { A2UIRenderer } from '../a2ui/A2UIRenderer';
import type { A2UISurface } from '../../types/a2ui';

interface AssistantMessageProps {
  message: Message;
  messageIndex: number;
  isStreaming: boolean;
  isLastMessage: boolean;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
  /** Streaming usage data */
  usage?: any;
  /** When provided, renders from AG-UI streaming parts instead of legacy HTML parsing */
  aguiParts?: AGUIPart[];
  /** HITL approval handler: (approvalId, toolCallId, approved, remember?, toolName?) */
  onToolApproval?: (approvalId: string, toolCallId: string, approved: boolean, remember?: ApprovalRememberScope, toolName?: string) => void;
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

// Renders a group of tool calls, potentially collapsed if many
const ToolSequenceGroup: React.FC<{
  tools: Array<{
    toolCallId?: string;
    toolName: string;
    toolArgs?: string;
    output?: string;
    approvalState?: 'pending' | 'denied' | undefined;
    onApprove?: (remember: ApprovalRememberScope) => void;
    onDeny?: () => void;
  }>;
  isStreaming?: boolean;
  toolApprovalPolicy?: Record<string, string>;
  onRemoveApprovalPolicy?: (toolName: string) => void;
  onForceWebContext?: (contextId: string) => void;
}> = ({ tools, isStreaming, toolApprovalPolicy, onRemoveApprovalPolicy, onForceWebContext }) => {
  const hasPending = tools.some(t => t.approvalState === 'pending');
  const isAnyRunning = isStreaming && tools.some(t => !t.output);
  // Use a ref to track if we've already auto-expanded for this set of tools
  // or just rely on state + effect/memo. For simplicity, we force expanded if hasPending.
  const [expanded, setExpanded] = useState(hasPending);

  // Sync expanded state if a new pending tool arrives
  useEffect(() => {
    if (hasPending) {
      setExpanded(true);
    }
  }, [hasPending]);

  const shouldGroup = tools.length > 2;

  if (!shouldGroup) {
    return (
      <div className="flex flex-col space-y-1">
        {tools.map((t, i) => {
          const isAutoApproved = toolApprovalPolicy?.[t.toolName] === 'always_allow';
          return (
            <ToolCallBlock
              key={t.toolCallId || i}
              toolName={t.toolName}
              toolArgs={t.toolArgs}
              output={t.output}
              defaultCollapsed={t.approvalState !== 'pending'}
              approvalState={t.approvalState}
              isStreaming={isStreaming}
              onApprove={t.onApprove}
              onDeny={t.onDeny}
              isAutoApproved={isAutoApproved}
              onRemovePolicy={isAutoApproved && onRemoveApprovalPolicy ? () => onRemoveApprovalPolicy(t.toolName) : undefined}
              onForceWebContext={onForceWebContext}
              toolCallId={t.toolCallId}
            />
          );
        })}
      </div>
    );
  }

  return (
    <div className="flex flex-col space-y-1">
      {/* Unified Header Toggle */}
      <button
        onClick={() => setExpanded(!expanded)}
        className={`tool-group-summary group/tools transition-all ${
          hasPending ? 'active-approval' : ''
        } ${
          isAnyRunning ? 'brutal-running-mono border-2 !border-brutal-black dark:!border-white' : 'border-2 border-transparent'
        }`}
      >
        <div className={`flex items-center gap-2 w-full ${isAnyRunning ? 'text-brutal-black dark:text-white' : 'text-neutral-500 dark:text-neutral-400 group-hover/tools:text-brutal-black dark:group-hover/tools:text-white transition-colors'}`}>
          {!expanded ? (
            <>
              <div className="tool-group-icons">
                {tools.map((t, i) => {
                  if (i > 3) return null;
                  return (
                    <ToolGroupIcon
                      key={i}
                      toolName={t.toolName}
                      approvalState={t.approvalState}
                      isStreaming={isStreaming && !t.output}
                      hasOutput={Boolean(t.output)}
                    />
                  );
                })}
                {tools.length > 4 && (
                  <span className="text-[10px] font-mono font-bold ml-1">+{tools.length - 4}</span>
                )}
              </div>
              <span className="text-[10px] font-mono font-bold uppercase tracking-tight">
                {isAnyRunning ? 'Running' : tools.length} Steps
              </span>
            </>
          ) : (
            <span className="text-[10px] font-mono font-bold uppercase tracking-tight">
              {isAnyRunning ? 'Running' : 'Hide'} {tools.length} Steps
            </span>
          )}
          <svg
            className={`w-3 h-3 transition-transform duration-200 ml-auto ${expanded ? 'rotate-180' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={3}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {/* Expanded Tools List */}
      <div className={`
        grid transition-[grid-template-rows] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)] overflow-hidden w-full
        ${expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}
      `}>
        <div className="overflow-hidden min-h-0 min-w-0 w-full ml-1 pl-1.5 space-y-1">
          {tools.map((t, i) => {
            const isAutoApproved = toolApprovalPolicy?.[t.toolName] === 'always_allow';
            return (
              <ToolCallBlock
                key={t.toolCallId || i}
                toolName={t.toolName}
                toolArgs={t.toolArgs}
                output={t.output}
                defaultCollapsed={t.approvalState !== 'pending'}
                approvalState={t.approvalState}
                isStreaming={isStreaming && !t.output}
                onApprove={t.onApprove}
                onDeny={t.onDeny}
                isAutoApproved={isAutoApproved}
                onRemovePolicy={isAutoApproved && onRemoveApprovalPolicy ? () => onRemoveApprovalPolicy(t.toolName) : undefined}
                onForceWebContext={onForceWebContext}
                toolCallId={t.toolCallId}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
};

// Renders just the tool call / code step pills (no box wrapper)
const StepPills: React.FC<{
  blocks: ContentBlock[];
  messageIndex: number;
  isStreaming?: boolean;
  onToolApproval?: (approvalId: string, toolCallId: string, approved: boolean, remember?: ApprovalRememberScope, toolName?: string) => void;
  toolApprovalPolicy?: Record<string, string>;
  onRemoveApprovalPolicy?: (toolName: string) => void;
  onForceWebContext?: (contextId: string) => void;
}> = ({ blocks, messageIndex, isStreaming, onToolApproval, toolApprovalPolicy, onRemoveApprovalPolicy, onForceWebContext }) => {
  const tools = blocks
    .filter(b => b.type === 'toolCall')
    .map((b, bi) => {
      const isPending = b.approvalState === 'pending';
      return {
        toolCallId: b.toolCallId || `historical-${bi}`,
        toolName: b.toolName || 'unknown',
        toolArgs: b.toolArgs,
        output: b.content || undefined,
        approvalState: (b.approvalState as 'pending' | 'denied' | undefined),
        onApprove: (isPending && b.approvalId && onToolApproval)
          ? (remember: ApprovalRememberScope) => onToolApproval(b.approvalId!, b.toolCallId || '', true, remember, b.toolName)
          : undefined,
        onDeny: (isPending && b.approvalId && onToolApproval)
          ? () => onToolApproval(b.approvalId!, b.toolCallId || '', false, null, b.toolName)
          : undefined,
      };
    });

  if (tools.length === 0) return null;
  return <ToolSequenceGroup tools={tools} isStreaming={isStreaming} toolApprovalPolicy={toolApprovalPolicy} onRemoveApprovalPolicy={onRemoveApprovalPolicy} onForceWebContext={onForceWebContext} />;
};

const StreamingMarkdownBlock: React.FC<{
  content: string;
  isLastBlock: boolean;
  showCursor: boolean;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
}> = ({ content, isLastBlock, showCursor, onFileClick }) => {
  const typedContent = useTypewriter(content, 10, isLastBlock);
  const renderedContent = isLastBlock ? typedContent : content;

  return (
    <>
      <MarkdownRenderer content={renderedContent} onFileClick={onFileClick} streamingLite={isLastBlock} />
      {isLastBlock && showCursor && <span className="animate-brutal-blink inline-block w-2.5 h-4 bg-brutal-black align-middle ml-1" />}
    </>
  );
};

// Streaming content with typewriter effect
const StreamingContent: React.FC<{
  blocks: ContentBlock[];
  messageIndex: number;
  showCursor?: boolean;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
}> = ({ blocks, messageIndex, showCursor = true, onFileClick }) => {
  return (
    <>
      {blocks.map((b, bi) => {
        const blockKey = generateBlockKey(b, bi, messageIndex);
        const isLastBlock = bi === blocks.length - 1;

        if (b.type === 'markdown') {
          return (
            <StreamingMarkdownBlock
              key={blockKey}
              content={b.content}
              isLastBlock={isLastBlock}
              showCursor={showCursor}
              onFileClick={onFileClick}
            />
          );
        } else if (b.type === 'log') {
          return <LogBlock key={blockKey} title={b.title} content={b.content} />;
        } else if (b.type === 'toolCall') {
          return null; // Handled outside in StepPills
        } else if (b.type === 'code') {
          // During live streaming, fenced blocks can be incomplete.
          // Always keep code rendering in lightweight preview mode here.
          return (
            <div key={blockKey} className="border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900/70">
              <div className="px-3 py-1 border-b-2 border-brutal-black text-[10px] font-mono font-bold uppercase text-neutral-600 dark:text-neutral-300 bg-white dark:bg-zinc-800">
                {(b as any).lang || 'text'}
              </div>
              <pre className="p-3 text-xs font-mono leading-relaxed whitespace-pre-wrap break-all overflow-x-auto max-h-[48vh]">
                <code>{b.content}</code>
                {isLastBlock && showCursor && <span className="animate-brutal-blink inline-block w-2 h-4 bg-neutral-700 dark:bg-neutral-300 align-middle ml-1" />}
              </pre>
            </div>
          );
        } else {
          return <CodeBlockComponent key={blockKey} lang={(b as any).lang} content={b.content} isStreaming={isLastBlock} />;
        }
      })}
    </>
  );
};

/** Extract sub-agent task_id from spawn_subagent tool output text. */
function parseSubAgentTaskId(output: string | undefined): string | undefined {
  if (!output) return undefined;
  const m = output.match(/ID:\s*`?(sub_[a-z0-9]+)`?/);
  return m ? m[1] : undefined;
}

// Static content (non-streaming)
const StaticContent: React.FC<{
  blocks: ContentBlock[];
  messageIndex: number;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
  onToolApproval?: (approvalId: string, toolCallId: string, approved: boolean, remember?: ApprovalRememberScope, toolName?: string) => void;
  toolApprovalPolicy?: Record<string, string>;
  onRemoveApprovalPolicy?: (toolName: string) => void;
  onInlineAction?: (surfaceId: string, action: string, context: Record<string, unknown>) => void;
  subAgentTasks?: Record<string, { status: SubAgentStatus; resultSummary?: string; error?: string }>;
  onOpenSubAgentSidebar?: (taskId: string) => void;
  onStopSubAgent?: (taskId: string) => void;
  onForceWebContext?: (contextId: string) => void;
}> = ({ blocks, messageIndex, onFileClick, onToolApproval, toolApprovalPolicy, onRemoveApprovalPolicy, onInlineAction, subAgentTasks, onOpenSubAgentSidebar, onStopSubAgent, onForceWebContext }) => {
  return (
    <>
      {blocks.map((b, bi) => {
        const blockKey = generateBlockKey(b, bi, messageIndex);
        if (b.type === 'markdown') {
          return <MarkdownRenderer key={blockKey} content={b.content} onFileClick={onFileClick} />;
        } else if (b.type === 'log') {
          return <LogBlock key={blockKey} title={b.title} content={b.content} />;
        } else if (b.type === 'a2ui' && b.a2uiSurface) {
          const surface = b.a2uiSurface as A2UISurface;
          return (
            <div key={blockKey} className="my-2">
              <A2UIRenderer
                component={surface.component}
                onAction={(action, context) => onInlineAction?.(surface.id, action, context ?? {})}
              />
            </div>
          );
        } else if (b.type === 'toolCall') {
          const isPending = b.approvalState === 'pending';
          const isAutoApproved = toolApprovalPolicy?.[b.toolName || ''] === 'always_allow';

          // Sub-agent special rendering
          if (b.toolName === 'spawn_subagent') {
            const taskId = parseSubAgentTaskId(b.content || undefined);
            const taskState = taskId ? subAgentTasks?.[taskId] : undefined;
            const args = b.toolArgs ? (() => { try { return JSON.parse(b.toolArgs!); } catch { return {}; } })() : {};
            // If the tool already has output, the call returned a result — it's done.
            // Default to 'completed' so linear (synchronous) subagents don't stay stuck
            // on 'running' forever. Polling in SubAgentCallBlock will correct to the
            // real backend status if needed (e.g. background agents still in-flight).
            const defaultStatus = b.content ? 'completed' : 'running';
            return (
              <SubAgentCallBlock
                key={blockKey}
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
          }

          return (
            <ToolCallBlock
              key={blockKey}
              toolName={b.toolName || 'unknown'}
              toolArgs={b.toolArgs}
              output={b.content || undefined}
              approvalState={b.approvalState as 'pending' | 'denied' | undefined}
              onApprove={(isPending && b.approvalId && onToolApproval)
                ? (remember) => onToolApproval(b.approvalId!, b.toolCallId || '', true, remember, b.toolName)
                : undefined}
              onDeny={(isPending && b.approvalId && onToolApproval)
                ? () => onToolApproval(b.approvalId!, b.toolCallId || '', false, null, b.toolName)
                : undefined}
              defaultCollapsed={!isPending}
              isAutoApproved={isAutoApproved}
              onRemovePolicy={isAutoApproved && onRemoveApprovalPolicy && b.toolName ? () => onRemoveApprovalPolicy(b.toolName!) : undefined}
              onForceWebContext={onForceWebContext}
              toolCallId={b.toolCallId}
            />
          );
        } else {
          return <CodeBlockComponent key={blockKey} lang={(b as any).lang} content={b.content} />;
        }
      })}
    </>
  );
};

// ── AG-UI Parts-based rendering (for streaming messages) ────────────

// Helper to extract the first line of reasoning for the header
const getReasoningHeader = (text: string, isStreaming: boolean = false) => {
  const firstLine = text.trim().split('\n')[0].replace(/^[#*>-\s]+/, '').replace(/\*\*/g, '').trim();
  const summary = firstLine.length > 80 ? firstLine.substring(0, 77) + '...' : firstLine || 'Processing...';
  const prefix = isStreaming ? 'Thinking' : 'Thought';
  return `${prefix}: ${summary}`;
};

const AGUIPartsContent: React.FC<{
  parts: AGUIPart[];
  messageIndex: number;
  isStreaming?: boolean;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
  onToolApproval?: (approvalId: string, toolCallId: string, approved: boolean, remember?: ApprovalRememberScope, toolName?: string) => void;
  toolApprovalPolicy?: Record<string, string>;
  onRemoveApprovalPolicy?: (toolName: string) => void;
  onInlineAction?: (surfaceId: string, action: string, context: Record<string, unknown>) => void;
  subAgentTasks?: Record<string, { status: SubAgentStatus; resultSummary?: string; error?: string }>;
  onOpenSubAgentSidebar?: (taskId: string) => void;
  onStopSubAgent?: (taskId: string) => void;
  onForceWebContext?: (contextId: string) => void;
}> = ({ parts, messageIndex, isStreaming, onFileClick, onToolApproval, toolApprovalPolicy, onRemoveApprovalPolicy, onInlineAction, subAgentTasks, onOpenSubAgentSidebar, onStopSubAgent, onForceWebContext }) => {
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

  return (
    <>
      {chunks.map((chunk, ci) => {
        if (chunk.type === 'tool') {
          const tools = chunk.items.map((tp, ti) => {
            const approvalState = tp.state === 'approval-requested' ? 'pending' as const
              : tp.state === 'error' ? 'denied' as const
                : undefined;

            return {
              toolCallId: tp.toolCallId || `tool-${ci}-${ti}`,
              toolName: tp.toolName || 'unknown',
              toolArgs: tp.args || undefined,
              output: tp.output || undefined,
              approvalState,
              onApprove: (approvalState === 'pending' && tp.approvalId && onToolApproval)
                ? (remember: ApprovalRememberScope) => onToolApproval(tp.approvalId!, tp.toolCallId || '', true, remember, tp.toolName)
                : undefined,
              onDeny: (approvalState === 'pending' && tp.approvalId && onToolApproval)
                ? () => onToolApproval(tp.approvalId!, tp.toolCallId || '', false, null, tp.toolName)
                : undefined,
            };
          });

          // Separate spawn_subagent calls from regular tool calls
          const subAgentTools = tools.filter(t => t.toolName === 'spawn_subagent');
          const regularTools = tools.filter(t => t.toolName !== 'spawn_subagent');

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
              {isLastChunk && (
                <span className="animate-brutal-blink inline-block w-2.5 h-4 bg-brutal-black align-middle ml-1" />
              )}
            </div>
          </div>
        );
      })}
    </>
  );
};

export const AssistantMessage: React.FC<AssistantMessageProps> = ({
  message,
  messageIndex,
  isStreaming,
  isLastMessage,
  onFileClick,
  aguiParts,
  onToolApproval,
  usage,
  toolApprovalPolicy,
  onRemoveApprovalPolicy,
  onInlineAction,
  subAgentTasks,
  onOpenSubAgentSidebar,
  onStopSubAgent,
  onForceWebContext,
}) => {
  const isStreamingThis = isStreaming && isLastMessage;
  const hasParts = aguiParts && aguiParts.length > 0;
  const isThinking = isStreamingThis && !message.content && !hasParts;

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
    if (aguiParts) {
      return aguiParts
        .filter(p => p.type === 'text')
        .map(p => p.text || '')
        .join('')
        .trim();
    } else {
      const parsedBlocks = filterBlocks(splitAssistantContent(message.content || ''));
      return parsedBlocks
        .filter(b => b.type !== 'log' && b.type !== 'reasoning' && b.type !== 'toolCall' && b.type !== 'a2ui')
        .map(b => (b.type === 'code' ? '```' + (b.lang || '') + '\n' + b.content + '\n```' : b.content))
        .join('\n\n')
        .trim();
    }
  }, [aguiParts, message.content]);

  // 1. 抓取当前正在跑的 Tool 和 错误状态
  let currentToolName: string | undefined = undefined;
  let hasError: boolean = false;
  let isPendingApproval: boolean = false;

  if (aguiParts && aguiParts.length > 0) {
    hasError = aguiParts.some(p => p.type === 'tool' && p.state === 'error');
    isPendingApproval = aguiParts.some(p => p.type === 'tool' && p.state === 'approval-requested');

    // 优先找正在 running 的 tool
    const runningTool = aguiParts.find(p => p.type === 'tool' && !p.output);
    if (runningTool) {
      currentToolName = runningTool.toolName;
    } else {
      // 没有正在运行的，看最后一个 block 是不是 tool (做完了但没新东西)
      const lastPart = aguiParts[aguiParts.length - 1];
      if (lastPart && lastPart.type === 'tool') {
        currentToolName = lastPart.toolName;
      }
    }
  } else {
    // For legacy blocks, check if there's a pending tool call
    const blocks = splitAssistantContent(message.content || '');
    isPendingApproval = blocks.some(b => b.type === 'toolCall' && b.approvalState === 'pending');
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
  if (aguiParts !== undefined) {
    return (
      <div className="group w-full max-w-4xl break-all overflow-x-hidden text-sm leading-relaxed relative pr-4 md:pr-12 animate-brutal-pop">
        {/* Badge/Assembly Container */}
        {badgeContainer}

        <div className={`grid transition-[grid-template-rows] duration-500 ease-out ${isThinking ? 'grid-rows-[0fr]' : 'grid-rows-[1fr]'}`}>
          <div className="overflow-hidden min-h-0 min-w-0 flex flex-col space-y-3 pr-2 pb-2">
            {hasParts ? (
              <AGUIPartsContent
                parts={aguiParts}
                messageIndex={messageIndex}
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

  const blocks = filterBlocks(splitAssistantContent(message.content));

  // If after filtering there are no blocks (e.g. only final_answer tool call), don't render
  if (!isStreamingThis && blocks.length === 0) {
    return null;
  }

  // Detect tool-only messages — but spawn_subagent always needs StaticContent
  // because it renders SubAgentCallBlock, not a step pill.
  const hasSubAgentCall = blocks.some(b => b.type === 'toolCall' && b.toolName === 'spawn_subagent');
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

  return (
    <div className="group w-full max-w-4xl break-all overflow-x-hidden text-sm leading-relaxed relative pr-4 md:pr-12 animate-brutal-pop">
      {/* Badge/Assembly Container is rendered at the top of the entire message timeline */}
      {badgeContainer}

      <div className={`grid transition-[grid-template-rows] duration-500 ease-out ${isThinking ? 'grid-rows-[0fr]' : 'grid-rows-[1fr]'}`}>
        <div className="overflow-hidden min-h-0 flex flex-col space-y-3 pr-2 pb-2">
          {validChunks.map((chunk, idx) => {
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
                            <MarkdownRenderer content={rb.content} onFileClick={onFileClick} streamingLite={isChunkStreaming && ri === chunk.blocks.length - 1} />
                          </div>
                        </div>
                      </details>
                    </div>
                  ))}
                </div>
              );
            }

            if (chunk.type === 'toolCall') {
              const subAgentBlocks = chunk.blocks.filter(b => b.toolName === 'spawn_subagent');
              const regularBlocks = chunk.blocks.filter(b => b.toolName !== 'spawn_subagent');
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
