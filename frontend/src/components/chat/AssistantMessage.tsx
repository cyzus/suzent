import React, { useState, useEffect } from 'react';
import type { Message } from '../../types/api';
import { splitAssistantContent, generateBlockKey, ContentBlock } from '../../lib/chatUtils';
import { useTypewriter } from '../../hooks/useTypewriter';
import { ThinkingAnimation, AgentBadge } from './ThinkingAnimation';
import { MarkdownRenderer } from './MarkdownRenderer';
import { LogBlock } from './LogBlock';
import { ToolCallBlock } from './ToolCallBlock';
import { CodeStepBlock } from './CodeStepBlock';
import { CodeBlockComponent } from './CodeBlockComponent';
import { CopyButton } from './CopyButton';
import { RobotAvatar } from './RobotAvatar';

interface AssistantMessageProps {
  message: Message;
  messageIndex: number;
  isStreaming: boolean;
  isLastMessage: boolean;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
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

// Renders just the tool call / code step pills (no box wrapper)
const StepPills: React.FC<{
  blocks: ContentBlock[];
  messageIndex: number;
}> = ({ blocks, messageIndex }) => (
  <>
    {blocks.map((b, bi) => {
      const blockKey = generateBlockKey(b, bi, messageIndex);
      if (b.type === 'toolCall') {
        return <ToolCallBlock key={blockKey} toolName={b.toolName || 'unknown'} toolArgs={b.toolArgs} output={b.content || undefined} defaultCollapsed />;
      }
      if (b.type === 'codeStep') {
        return <CodeStepBlock key={blockKey} thought={b.thought || ''} codeContent={b.codeContent} executionLogs={b.executionLogs} result={b.result} defaultCollapsed />;
      }
      return null;
    })}
  </>
);

// Streaming content with typewriter effect
const StreamingContent: React.FC<{
  content: string;
  messageIndex: number;
  showCursor?: boolean;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
}> = ({ content, messageIndex, showCursor = true, onFileClick }) => {
  const displayedContent = useTypewriter(content, 10, true);
  const blocks = filterBlocks(splitAssistantContent(displayedContent));

  return (
    <>
      {blocks.map((b, bi) => {
        const blockKey = generateBlockKey(b, bi, messageIndex);
        const isLastBlock = bi === blocks.length - 1;

        if (b.type === 'markdown') {
          return (
            <React.Fragment key={blockKey}>
              <MarkdownRenderer content={b.content} onFileClick={onFileClick} />
              {isLastBlock && showCursor && <span className="animate-brutal-blink inline-block w-2.5 h-4 bg-brutal-black align-middle ml-1" />}
            </React.Fragment>
          );
        } else if (b.type === 'log') {
          return <LogBlock key={blockKey} title={b.title} content={b.content} />;
        } else if (b.type === 'toolCall') {
          return <ToolCallBlock key={blockKey} toolName={b.toolName || 'unknown'} toolArgs={b.toolArgs} output={b.content || undefined} defaultCollapsed />;
        } else if (b.type === 'codeStep') {
          return <CodeStepBlock key={blockKey} thought={b.thought || ''} codeContent={b.codeContent} executionLogs={b.executionLogs} result={b.result} defaultCollapsed />;
        } else {
          return <CodeBlockComponent key={blockKey} lang={(b as any).lang} content={b.content} isStreaming={isLastBlock} />;
        }
      })}
    </>
  );
};

// Static content (non-streaming) — only non-toolCall blocks
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
        } else if (b.type === 'codeStep') {
          return <CodeStepBlock key={blockKey} thought={b.thought || ''} codeContent={b.codeContent} executionLogs={b.executionLogs} result={b.result} defaultCollapsed />;
        } else {
          return <CodeBlockComponent key={blockKey} lang={(b as any).lang} content={b.content} />;
        }
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
}) => {
  const isStreamingThis = isStreaming && isLastMessage;
  const isThinking = isStreamingThis && !message.content;

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

  // Don't render empty messages unless we're actively streaming
  if (!isStreamingThis && !message.content?.trim()) {
    return null;
  }

  const blocks = filterBlocks(splitAssistantContent(message.content));

  // If after filtering there are no blocks (e.g. only final_answer tool call), don't render
  if (!isStreamingThis && blocks.length === 0) {
    return null;
  }

  // Streaming CodeAgent step: render as expanded pill directly (skip box and badge)
  if (isStreamingThis && !isThinking) {
    const codeStepBlock = blocks.find(b => b.type === 'codeStep');
    if (codeStepBlock) {
      return (
        <div className="w-full max-w-4xl text-sm leading-relaxed pl-2">
          <CodeStepBlock
            thought={codeStepBlock.thought || ''}
            codeContent={codeStepBlock.codeContent}
            executionLogs={codeStepBlock.executionLogs}
            result={codeStepBlock.result}
            isStreaming
          />
        </div>
      );
    }

    // stepInfo is the definitive signal — every CodeAgent intermediate step has it.
    // Also fall back to content heuristics (Thought: prefix, code+logs) for in-flight messages.
    const isCodeAgentStep = !!message.stepInfo
      || message.content?.trim().startsWith('Thought:')
      || (blocks.some(b => b.type === 'code' && b.content.trim()) && blocks.some(b => b.type === 'log' && b.title === 'Execution Logs'));

    if (isCodeAgentStep) {
      // Assemble a codeStep from raw blocks
      const mdBlocks = blocks.filter(b => b.type === 'markdown' && b.content.trim());
      const codeBlock = blocks.find(b => b.type === 'code' && b.content.trim());
      const logBlock = blocks.find(b => b.type === 'log' && b.title === 'Execution Logs');
      const thoughtText = mdBlocks.map(b => b.content.trim()).join('\n').replace(/^Thought:\s*/i, '') || '';
      return (
        <div className="w-full max-w-4xl text-sm leading-relaxed pl-2">
          <CodeStepBlock
            thought={thoughtText}
            codeContent={codeBlock?.content}
            executionLogs={logBlock?.content}
            isStreaming
          />
        </div>
      );
    }
  }

  // Detect tool-only messages: render without robot badge and white box
  const toolOnly = !isStreamingThis && isToolOnlyMessage(blocks);

  if (toolOnly) {
    return (
      <div className="w-full max-w-4xl text-sm leading-relaxed pl-2">
        <StepPills blocks={blocks} messageIndex={messageIndex} />
      </div>
    );
  }

  // Content blocks for the white box (exclude toolCalls and codeSteps — they render above the box)
  const stepBlocks = blocks.filter(b => b.type === 'toolCall' || b.type === 'codeStep');
  const contentBlocks = blocks.filter(b => b.type !== 'toolCall' && b.type !== 'codeStep');

  // Check if content blocks have any meaningful content to display
  const hasContent = isStreamingThis || contentBlocks.some(b => b.content.trim().length > 0);

  // If there's no real content, just render the step pills (no box)
  if (!hasContent && stepBlocks.length > 0) {
    return (
      <div className="w-full max-w-4xl text-sm leading-relaxed pl-2">
        <StepPills blocks={stepBlocks} messageIndex={messageIndex} />
      </div>
    );
  }

  // If there's no content at all, don't render
  if (!hasContent && !isStreamingThis) {
    return null;
  }

  // Calculate clean content for copy (excluding logs and toolCalls)
  const cleanContent = contentBlocks
    .filter(b => b.type !== 'log')
    .map(b => {
      if (b.type === 'code') {
        return '```' + (b.lang || '') + '\n' + b.content + '\n```';
      }
      return b.content;
    })
    .join('').trim();

  // Determine if we should show the main copy button
  const isThought = cleanContent.startsWith('Thought:');
  const hasStepInfo = !!message.stepInfo;
  const showCopyButton = cleanContent && !isThought && !hasStepInfo;

  return (
    <div className="group w-full max-w-4xl break-words overflow-visible text-sm leading-relaxed relative pr-4 md:pr-12 animate-brutal-pop">
      {/* Step pills rendered outside the box, before the badge */}
      {stepBlocks.length > 0 && (
        <div className="mb-2 pl-1">
          <StepPills blocks={stepBlocks} messageIndex={messageIndex} />
        </div>
      )}

      {/* Badge/Assembly Container */}
      <div className={`
        border-3 border-brutal-black shadow-brutal-lg overflow-hidden relative
        transition-all duration-700 ease-out
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

      {/* White Message Box - smooth height reveal via CSS Grid 0fr→1fr */}
      <div className={`
        grid mt-3 transition-[grid-template-rows] duration-500 ease-out
        ${isThinking ? 'grid-rows-[0fr]' : 'grid-rows-[1fr]'}
      `}>
        <div className="overflow-hidden min-h-0">
          <div className="border-3 border-brutal-black shadow-brutal-lg bg-white px-6 py-5 relative">
            {showCopyButton && !isThinking && (
              <CopyButton
                text={cleanContent}
                className="absolute top-2 right-2 z-10"
              />
            )}
            <div className="space-y-4">
              {isStreamingThis ? (
                <StreamingContent content={message.content} messageIndex={messageIndex} showCursor={cursorReady} onFileClick={onFileClick} />
              ) : (
                <StaticContent blocks={contentBlocks} messageIndex={messageIndex} onFileClick={onFileClick} />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
