import React from 'react';
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
}

// Names that should be filtered out from tool call display
const IGNORED_TOOL_NAMES = ['final_answer', 'final answer'];

function isIgnoredToolCall(block: ContentBlock): boolean {
  if (block.type !== 'toolCall') return false;
  const name = (block.toolName || '').toLowerCase();
  return IGNORED_TOOL_NAMES.includes(name);
}

function filterBlocks(blocks: ContentBlock[]): ContentBlock[] {
  return blocks.filter(b => !isIgnoredToolCall(b));
}

/** Check if a message consists only of toolCall blocks (no real prose/code content) */
function isToolOnlyMessage(blocks: ContentBlock[]): boolean {
  return blocks.length > 0 && blocks.every(b => b.type === 'toolCall');
}

// Renders just the tool call pills (no box wrapper)
const ToolCallPills: React.FC<{
  blocks: ContentBlock[];
  messageIndex: number;
}> = ({ blocks, messageIndex }) => (
  <>
    {blocks.map((b, bi) => {
      const blockKey = generateBlockKey(b, bi, messageIndex);
      if (b.type === 'toolCall') {
        return <ToolCallBlock key={blockKey} toolName={b.toolName || 'unknown'} toolArgs={b.toolArgs} output={b.content || undefined} defaultCollapsed />;
      }
      return null;
    })}
  </>
);

// Streaming content with typewriter effect
const StreamingContent: React.FC<{
  content: string;
  messageIndex: number;
  onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
}> = ({ content, messageIndex, onFileClick }) => {
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
              {isLastBlock && <span className="animate-brutal-blink inline-block w-2.5 h-4 bg-brutal-black align-middle ml-1" />}
            </React.Fragment>
          );
        } else if (b.type === 'log') {
          return <LogBlock key={blockKey} title={b.title} content={b.content} />;
        } else if (b.type === 'toolCall') {
          return <ToolCallBlock key={blockKey} toolName={b.toolName || 'unknown'} toolArgs={b.toolArgs} output={b.content || undefined} defaultCollapsed />;
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

  // Don't render empty messages unless we're actively streaming
  if (!isStreamingThis && !message.content?.trim()) {
    return null;
  }

  const blocks = filterBlocks(splitAssistantContent(message.content));

  // If after filtering there are no blocks (e.g. only final_answer tool call), don't render
  if (!isStreamingThis && blocks.length === 0) {
    return null;
  }

  // Detect tool-only messages: render without robot badge and white box
  const toolOnly = !isStreamingThis && isToolOnlyMessage(blocks);

  if (toolOnly) {
    return (
      <div className="w-full max-w-4xl text-sm leading-relaxed pl-2">
        <ToolCallPills blocks={blocks} messageIndex={messageIndex} />
      </div>
    );
  }

  // Content blocks for the white box (exclude toolCalls — they render above the box)
  const toolCallBlocks = blocks.filter(b => b.type === 'toolCall');
  const contentBlocks = blocks.filter(b => b.type !== 'toolCall');

  // Check if content blocks have any meaningful content to display
  const hasContent = isStreamingThis || contentBlocks.some(b => b.content.trim().length > 0);

  // If there's no real content, just render the tool call pills (no box)
  if (!hasContent && toolCallBlocks.length > 0) {
    return (
      <div className="w-full max-w-4xl text-sm leading-relaxed pl-2">
        <ToolCallPills blocks={toolCallBlocks} messageIndex={messageIndex} />
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
      {/* Tool call pills rendered outside the box, before the badge */}
      {toolCallBlocks.length > 0 && (
        <div className="mb-2 pl-1">
          <ToolCallPills blocks={toolCallBlocks} messageIndex={messageIndex} />
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
                <StreamingContent content={message.content} messageIndex={messageIndex} onFileClick={onFileClick} />
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
