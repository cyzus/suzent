import React, { useEffect, useState } from 'react';
import type { ApprovalRememberScope } from '../../hooks/useAGUI';
import type { A2UISurface } from '../../types/a2ui';
import { generateBlockKey, type ContentBlock } from '../../lib/chatUtils';
import { useTypewriter } from '../../hooks/useTypewriter';
import { A2UIRenderer } from '../a2ui/A2UIRenderer';
import { CodeBlockComponent } from './CodeBlockComponent';
import { LogBlock } from './LogBlock';
import { MarkdownRenderer } from './MarkdownRenderer';
import { SubAgentCallBlock, type SubAgentStatus } from './SubAgentCallBlock';
import { ToolCallBlock } from './ToolCallBlock';
import { ToolGroupIcon } from './toolGroupIcon';

/** Extract sub-agent task_id from agent tool output text. */
export function parseSubAgentTaskId(output: string | undefined): string | undefined {
  if (!output) return undefined;
  const m = output.match(/ID:\s*`?(sub_[a-z0-9]+)`?/);
  return m ? m[1] : undefined;
}

export const ToolSequenceGroup: React.FC<{
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
  const [expanded, setExpanded] = useState(hasPending);

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

export const StepPills: React.FC<{
  blocks: ContentBlock[];
  messageIndex: number;
  isStreaming?: boolean;
  onToolApproval?: (approvalId: string, toolCallId: string, approved: boolean, remember?: ApprovalRememberScope, toolName?: string) => void;
  toolApprovalPolicy?: Record<string, string>;
  onRemoveApprovalPolicy?: (toolName: string) => void;
  onForceWebContext?: (contextId: string) => void;
}> = ({ blocks, isStreaming, onToolApproval, toolApprovalPolicy, onRemoveApprovalPolicy, onForceWebContext }) => {
  const tools = blocks
    .filter(b => b.type === 'toolCall')
    .map((b, bi) => {
      const hasOutput = !!(b.content);
      const isActionablyPending = b.approvalState === 'pending' && !hasOutput && !!b.approvalId && !!isStreaming;
      const effectiveApprovalState = isActionablyPending
        ? 'pending'
        : (b.approvalState === 'denied' || (b.approvalState === 'pending' && !hasOutput))
          ? 'denied'
          : undefined;
      return {
        toolCallId: b.toolCallId || `historical-${bi}`,
        toolName: b.toolName || 'unknown',
        toolArgs: b.toolArgs,
        output: b.content || undefined,
        approvalState: effectiveApprovalState as 'pending' | 'denied' | undefined,
        onApprove: (isActionablyPending && b.approvalId && onToolApproval)
          ? (remember: ApprovalRememberScope) => onToolApproval(b.approvalId!, b.toolCallId || '', true, remember, b.toolName)
          : undefined,
        onDeny: (isActionablyPending && b.approvalId && onToolApproval)
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

export const StreamingContent: React.FC<{
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
          return null;
        } else if (b.type === 'code') {
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

export const StaticContent: React.FC<{
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
  inActivityRail?: boolean;
}> = ({ blocks, messageIndex, onFileClick, onToolApproval, toolApprovalPolicy, onRemoveApprovalPolicy, onInlineAction, subAgentTasks, onOpenSubAgentSidebar, onStopSubAgent, onForceWebContext, inActivityRail }) => {
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
          const isPending = b.approvalState === 'pending' && !b.content;
          const effectiveApprovalState = (isPending ? 'pending' : b.approvalState === 'denied' ? 'denied' : undefined) as 'pending' | 'denied' | undefined;
          const isAutoApproved = toolApprovalPolicy?.[b.toolName || ''] === 'always_allow';

          if (b.toolName === 'agent') {
            const taskId = parseSubAgentTaskId(b.content || undefined);
            const taskState = taskId ? subAgentTasks?.[taskId] : undefined;
            const args = b.toolArgs ? (() => { try { return JSON.parse(b.toolArgs!); } catch { return {}; } })() : {};
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
              approvalState={effectiveApprovalState}
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
              inActivityRail={inActivityRail}
            />
          );
        } else {
          return <CodeBlockComponent key={blockKey} lang={(b as any).lang} content={b.content} />;
        }
      })}
    </>
  );
};
