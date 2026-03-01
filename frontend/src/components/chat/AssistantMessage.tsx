import React, { useState, useEffect } from 'react';
import type { Message } from '../../types/api';
import { splitAssistantContent, generateBlockKey, ContentBlock } from '../../lib/chatUtils';
import { useTypewriter } from '../../hooks/useTypewriter';
import { ThinkingAnimation, AgentBadge } from './ThinkingAnimation';
import { MarkdownRenderer } from './MarkdownRenderer';
import { LogBlock } from './LogBlock';
import { ToolCallBlock } from './ToolCallBlock';
import { CodeBlockComponent } from './CodeBlockComponent';
import { CopyButton } from './CopyButton';
import { RobotAvatar } from './RobotAvatar';

interface AssistantMessageProps {
  message: Message;
  messageIndex: number;
  isStreaming: boolean;
  isLastMessage: boolean;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
  /** When provided, renders from UIMessage.parts instead of legacy HTML parsing */
  uiParts?: any[];
  /** HITL approval handler: (approvalId, toolCallId, approved, remember?) */
  onToolApproval?: (approvalId: string, toolCallId: string, approved: boolean, remember?: 'session' | null) => void;
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
    onApprove?: (remember: 'session' | null) => void;
    onDeny?: () => void;
  }>;
}> = ({ tools }) => {
  const [expanded, setExpanded] = useState(tools.some(t => t.approvalState === 'pending'));
  const shouldGroup = tools.length > 2;

  if (!shouldGroup) {
    return (
      <div className="flex flex-col space-y-1">
        {tools.map((t, i) => (
          <ToolCallBlock
            key={t.toolCallId || i}
            toolName={t.toolName}
            toolArgs={t.toolArgs}
            output={t.output}
            defaultCollapsed={t.approvalState !== 'pending'}
            approvalState={t.approvalState}
            onApprove={t.onApprove}
            onDeny={t.onDeny}
          />
        ))}
      </div>
    );
  }

  const icons = tools.map((t, i) => {
    if (i > 3) return null;
    const icon = t.approvalState === 'pending' ? '⏳' : t.approvalState === 'denied' ? '🚫' : '🔧';
    return <span key={i} className="tool-group-icon">{icon}</span>;
  });

  return (
    <div className="flex flex-col space-y-1">
      {/* Unified Header Toggle */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="tool-group-summary group/tools"
      >
        {!expanded ? (
          <>
            <div className="tool-group-icons">
              {icons}
              {tools.length > 4 && (
                <span className="tool-group-icon bg-neutral-100 font-bold">+{tools.length - 4}</span>
              )}
            </div>
            <span className="text-[10px] font-mono font-bold text-neutral-500 uppercase tracking-tight group-hover/tools:text-brutal-black transition-colors">
              {tools.length} Steps
            </span>
          </>
        ) : (
          <span className="text-[10px] font-mono font-bold text-neutral-500 uppercase tracking-tight group-hover/tools:text-brutal-black transition-colors">
            Hide {tools.length} Steps
          </span>
        )}
        <svg
          className={`w-3 h-3 text-neutral-500 transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={3}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Expanded Tools List */}
      <div className={`
        grid transition-[grid-template-rows] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)] overflow-hidden w-full
        ${expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}
      `}>
        <div className="overflow-hidden min-h-0 min-w-0 w-full ml-1 pl-1.5 space-y-1">
          {tools.map((t, i) => (
            <ToolCallBlock
              key={t.toolCallId || i}
              toolName={t.toolName}
              toolArgs={t.toolArgs}
              output={t.output}
              defaultCollapsed={t.approvalState !== 'pending'}
              approvalState={t.approvalState}
              onApprove={t.onApprove}
              onDeny={t.onDeny}
            />
          ))}
        </div>
      </div>
    </div>
  );
};

// Renders just the tool call / code step pills (no box wrapper)
const StepPills: React.FC<{
  blocks: ContentBlock[];
  messageIndex: number;
}> = ({ blocks, messageIndex }) => {
  const tools = blocks
    .filter(b => b.type === 'toolCall')
    .map((b, bi) => ({
      toolName: b.toolName || 'unknown',
      toolArgs: b.toolArgs,
      output: b.content || undefined,
    }));

  if (tools.length === 0) return null;
  return <ToolSequenceGroup tools={tools} />;
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
            <React.Fragment key={blockKey}>
              <MarkdownRenderer content={isLastBlock ? useTypewriter(b.content, 10, true) : b.content} onFileClick={onFileClick} />
              {isLastBlock && showCursor && <span className="animate-brutal-blink inline-block w-2.5 h-4 bg-brutal-black align-middle ml-1" />}
            </React.Fragment>
          );
        } else if (b.type === 'log') {
          return <LogBlock key={blockKey} title={b.title} content={b.content} />;
        } else if (b.type === 'toolCall') {
          return null; // Handled outside in StepPills
        } else {
          return <CodeBlockComponent key={blockKey} lang={(b as any).lang} content={b.content} isStreaming={isLastBlock} />;
        }
      })}
    </>
  );
};

// Static content (non-streaming)
const StaticContent: React.FC<{
  blocks: ContentBlock[];
  messageIndex: number;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
}> = ({ blocks, messageIndex, onFileClick }) => {
  return (
    <>
      {blocks.map((b, bi) => {
        const blockKey = generateBlockKey(b, bi, messageIndex);
        if (b.type === 'markdown') {
          return <MarkdownRenderer key={blockKey} content={b.content} onFileClick={onFileClick} />;
        } else if (b.type === 'log') {
          return <LogBlock key={blockKey} title={b.title} content={b.content} />;
        } else if (b.type === 'toolCall') {
          return <ToolCallBlock key={blockKey} toolName={b.toolName || 'unknown'} toolArgs={b.toolArgs} output={b.content || undefined} defaultCollapsed />;
        } else {
          return <CodeBlockComponent key={blockKey} lang={(b as any).lang} content={b.content} />;
        }
      })}
    </>
  );
};

// ── Parts-based rendering (for useChat streaming messages) ──────────

/**
 * Check if a UIMessage part is a tool invocation.
 * The SDK creates "dynamic-tool" parts when the chunk has `dynamic: true`,
 * and static "tool-<name>" parts otherwise (e.g., "tool-bash_execute").
 * pydantic-ai's VercelAIAdapter emits static tool parts (no dynamic flag).
 */
function isToolPart(part: any): boolean {
  return part.type === 'dynamic-tool' ||
    (typeof part.type === 'string' && part.type.startsWith('tool-') && part.type !== 'tool-');
}

/** Extract the tool name from either a dynamic or static tool part. */
function getToolPartName(part: any): string {
  if (part.type === 'dynamic-tool') return part.toolName || 'unknown';
  // Static: type is "tool-<name>" — strip the "tool-" prefix
  if (typeof part.type === 'string' && part.type.startsWith('tool-')) {
    return part.type.slice(5) || 'unknown';
  }
  return 'unknown';
}

/** Check if a part is "visible content" (text or tool) vs structural/data */
function isContentPart(part: any): boolean {
  return part.type === 'text' || isToolPart(part);
}

const PartsBasedContent: React.FC<{
  parts: any[];
  messageIndex: number;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
  onToolApproval?: (approvalId: string, toolCallId: string, approved: boolean, remember?: 'session' | null) => void;
}> = ({ parts, messageIndex, onFileClick, onToolApproval }) => {
  // Separate parts into chunks: contiguous text vs tool groups
  const chunks: { isTool: boolean; items: any[] }[] = [];
  let current: any[] = [];
  let currentIsTool = false;

  for (const part of parts) {
    const isTool = isToolPart(part);
    // Ignore step-start, data-*, reasoning, and other non-content parts
    if (!isContentPart(part)) continue;

    if (current.length === 0) {
      currentIsTool = isTool;
      current.push(part);
    } else if (currentIsTool === isTool) {
      current.push(part);
    } else {
      chunks.push({ isTool: currentIsTool, items: current });
      currentIsTool = isTool;
      current = [part];
    }
  }
  if (current.length > 0) chunks.push({ isTool: currentIsTool, items: current });

  return (
    <>
      {chunks.map((chunk, ci) => {
        if (chunk.isTool) {
          const tools = chunk.items.map((tp, ti) => {
            const toolName = getToolPartName(tp);
            const argsStr = tp.input != null
              ? (typeof tp.input === 'string' ? tp.input : JSON.stringify(tp.input, null, 2))
              : (tp.rawInput != null)
                ? (typeof tp.rawInput === 'string' ? tp.rawInput : JSON.stringify(tp.rawInput, null, 2))
                : undefined;
            const outputStr = (tp.state === 'output-available' && tp.output != null)
              ? (typeof tp.output === 'string' ? tp.output : JSON.stringify(tp.output, null, 2))
              : (tp.state === 'output-error' && tp.errorText)
                ? `Error: ${tp.errorText}`
                : undefined;
            const approvalState = tp.state === 'approval-requested' ? 'pending' as const
              : tp.state === 'output-denied' ? 'denied' as const
                : undefined;

            return {
              toolCallId: tp.toolCallId || `tool-${ci}-${ti}`,
              toolName,
              toolArgs: argsStr,
              output: outputStr,
              approvalState,
              onApprove: (approvalState === 'pending' && tp.approval && onToolApproval)
                ? (remember: 'session' | null) => onToolApproval(tp.approval.id, tp.toolCallId, true, remember)
                : undefined,
              onDeny: (approvalState === 'pending' && tp.approval && onToolApproval)
                ? () => onToolApproval(tp.approval.id, tp.toolCallId, false)
                : undefined,
            };
          });

          return (
            <div key={ci} className="pl-1 min-w-0 overflow-x-hidden">
              <ToolSequenceGroup tools={tools} />
            </div>
          );
        }
        // Text chunk
        const fullText = chunk.items.map((p: any) => p.text || '').join('');
        const isLastChunk = ci === chunks.length - 1;
        const isStreamingText = isLastChunk && chunk.items.some((p: any) => p.state === 'streaming');
        if (!fullText.trim() && !isStreamingText) return null;
        return (
          <div key={ci} className="border-3 border-brutal-black shadow-brutal-lg bg-white px-6 py-5 relative">
            {fullText.trim() && (
              <CopyButton text={fullText.trim()} className="absolute top-2 right-2 z-10" />
            )}
            <div className="space-y-4">
              <MarkdownRenderer content={fullText} onFileClick={onFileClick} />
              {isStreamingText && (
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
  uiParts,
  onToolApproval,
}) => {
  const isStreamingThis = isStreaming && isLastMessage;
  // Only count visible content parts (text or tool) — not structural parts like step-start, data-*, etc.
  const hasParts = uiParts && uiParts.some(isContentPart);
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

  // ── Parts-based rendering path (for useChat streaming messages) ──
  if (uiParts !== undefined) {
    return (
      <div className="group w-full max-w-4xl break-all overflow-x-hidden text-sm leading-relaxed relative pr-4 md:pr-12 animate-brutal-pop">
        {/* Badge/Assembly Container */}
        <div className={`
          border-3 border-brutal-black shadow-brutal-lg overflow-hidden relative
          transition-all duration-700 ease-out mb-3
          ${isThinking
            ? 'w-[400px] h-[80px] bg-white left-1/2 -translate-x-1/2'
            : 'w-[90px] h-[40px] bg-white left-0 translate-x-0'
          }
        `}>
          <ThinkingAnimation isThinking={isThinking} />
          <AgentBadge isThinking={isThinking} isStreaming={isStreamingThis} />
        </div>

        <div className={`grid transition-[grid-template-rows] duration-500 ease-out ${isThinking ? 'grid-rows-[0fr]' : 'grid-rows-[1fr]'}`}>
          <div className="overflow-hidden min-h-0 min-w-0 flex flex-col space-y-3">
            {hasParts ? (
              <PartsBasedContent
                parts={uiParts}
                messageIndex={messageIndex}
                onFileClick={onFileClick}
                onToolApproval={onToolApproval}
              />
            ) : null}
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

  // Detect tool-only messages
  const toolOnly = !isStreamingThis && isToolOnlyMessage(blocks);

  if (toolOnly) {
    return (
      <div className="w-full max-w-4xl text-sm leading-relaxed pl-2">
        <StepPills blocks={blocks} messageIndex={messageIndex} />
      </div>
    );
  }

  // Chunk blocks into alternating contiguous groups of "content" and "step"
  const chunks: { isStep: boolean; blocks: ContentBlock[] }[] = [];
  let currentGroup: ContentBlock[] = [];
  let currentIsStep = false;

  for (const b of blocks) {
    const isStep = b.type === 'toolCall';
    if (currentGroup.length === 0) {
      currentIsStep = isStep;
      currentGroup.push(b);
    } else if (currentIsStep === isStep) {
      currentGroup.push(b);
    } else {
      chunks.push({ isStep: currentIsStep, blocks: currentGroup });
      currentIsStep = isStep;
      currentGroup = [b];
    }
  }
  if (currentGroup.length > 0) {
    chunks.push({ isStep: currentIsStep, blocks: currentGroup });
  }

  // Filter out empty content chunks, unless it's the active streaming head
  const validChunks = chunks.filter((chunk, idx) => {
    if (chunk.isStep) return true;
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
      <div className={`
        border-3 border-brutal-black shadow-brutal-lg overflow-hidden relative
        transition-all duration-700 ease-out mb-3
        ${isThinking
          ? 'w-[400px] h-[80px] bg-white left-1/2 -translate-x-1/2'
          : 'w-[90px] h-[40px] bg-white left-0 translate-x-0'
        }
      `}>
        <ThinkingAnimation isThinking={isThinking} />
        <AgentBadge
          isThinking={isThinking}
          isStreaming={isStreamingThis}
        />
      </div>

      <div className={`grid transition-[grid-template-rows] duration-500 ease-out ${isThinking ? 'grid-rows-[0fr]' : 'grid-rows-[1fr]'}`}>
        <div className="overflow-hidden min-h-0 flex flex-col space-y-3">
          {validChunks.map((chunk, idx) => {
            if (chunk.isStep) {
              return (
                <div key={idx} className="pl-1">
                  <StepPills blocks={chunk.blocks} messageIndex={messageIndex} />
                </div>
              );
            }

            const cleanContent = chunk.blocks
              .filter(b => b.type !== 'log')
              .map(b => (b.type === 'code' ? '```' + (b.lang || '') + '\n' + b.content + '\n```' : b.content))
              .join('').trim();

            const isThought = cleanContent.startsWith('Thought:');
            const hasStepInfo = !!message.stepInfo;
            const showCopyButton = cleanContent && !isThought && !hasStepInfo;
            const isLastChunk = idx === validChunks.length - 1;
            const isStreamingChunk = isStreamingThis && isLastChunk;

            return (
              <div key={idx} className="border-3 border-brutal-black shadow-brutal-lg bg-white px-6 py-5 relative">
                {showCopyButton && !isThinking && (
                  <CopyButton
                    text={cleanContent}
                    className="absolute top-2 right-2 z-10"
                  />
                )}
                <div className="space-y-4">
                  {isStreamingChunk ? (
                    <StreamingContent blocks={chunk.blocks} messageIndex={messageIndex} showCursor={cursorReady} onFileClick={onFileClick} />
                  ) : (
                    <StaticContent blocks={chunk.blocks} messageIndex={messageIndex} onFileClick={onFileClick} />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
