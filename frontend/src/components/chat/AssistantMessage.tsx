import React from 'react';
import type { Message } from '../../types/api';
import { splitAssistantContent, generateBlockKey } from '../../lib/chatUtils';
import { useTypewriter } from '../../hooks/useTypewriter';
import { ThinkingAnimation, AgentBadge } from './ThinkingAnimation';
import { MarkdownRenderer } from './MarkdownRenderer';
import { LogBlock } from './LogBlock';
import { CodeBlockComponent } from './CodeBlockComponent';
import { CopyButton } from './CopyButton';

interface AssistantMessageProps {
  message: Message;
  messageIndex: number;
  isStreaming: boolean;
  isLastMessage: boolean;
}

// Streaming content with typewriter effect
const StreamingContent: React.FC<{
  content: string;
  messageIndex: number;
}> = ({ content, messageIndex }) => {
  const displayedContent = useTypewriter(content, 10, true);
  const blocks = splitAssistantContent(displayedContent);

  return (
    <>
      {blocks.map((b, bi) => {
        const blockKey = generateBlockKey(b, bi, messageIndex);
        const isLastBlock = bi === blocks.length - 1;

        if (b.type === 'markdown') {
          const contentWithCursor = isLastBlock
            ? b.content + ' <span class="animate-brutal-blink inline-block w-2.5 h-4 bg-brutal-black align-middle ml-1"></span>'
            : b.content;
          return <MarkdownRenderer key={blockKey} content={contentWithCursor} />;
        } else if (b.type === 'log') {
          return <LogBlock key={blockKey} title={b.title} content={b.content} />;
        } else {
          return <CodeBlockComponent key={blockKey} lang={(b as any).lang} content={b.content} isStreaming={isLastBlock} />;
        }
      })}
    </>
  );
};

// Static content (non-streaming)
const StaticContent: React.FC<{
  blocks: ReturnType<typeof splitAssistantContent>;
  messageIndex: number;
}> = ({ blocks, messageIndex }) => {
  return (
    <>
      {blocks.map((b, bi) => {
        const blockKey = generateBlockKey(b, bi, messageIndex);
        if (b.type === 'markdown') {
          return <MarkdownRenderer key={blockKey} content={b.content} />;
        } else if (b.type === 'log') {
          return <LogBlock key={blockKey} title={b.title} content={b.content} />;
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
  isLastMessage
}) => {
  const isStreamingThis = isStreaming && isLastMessage;
  const isThinking = isStreamingThis && !message.content;
  const blocks = splitAssistantContent(message.content);

  // Calculate clean content for copy (excluding logs)
  const cleanContent = blocks
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

  // Eye animation classes
  const eyeClass = isStreamingThis ? 'robot-eye robot-eye-blink' : 'robot-eye robot-eye-idle';
  const rightEyeStyle = isStreamingThis ? undefined : { animationDelay: '1.8s' };

  return (
    <div className="group w-full max-w-4xl break-words overflow-visible space-y-0 text-sm leading-relaxed relative pr-4 md:pr-12 animate-brutal-pop">
      {/* Badge/Assembly Container */}
      <div className={`
        border-3 border-brutal-black shadow-brutal-lg overflow-hidden relative
        transition-all duration-700 ease-out
        ${isThinking
          ? 'w-[300px] h-[90px] bg-white'
          : 'w-[90px] h-[28px] bg-brutal-black'
        }
      `}>
        <ThinkingAnimation isThinking={isThinking} />
        <AgentBadge
          isThinking={isThinking}
          isStreaming={isStreamingThis}
          eyeClass={eyeClass}
          rightEyeStyle={rightEyeStyle}
        />
      </div>

      {/* White Message Box */}
      <div className={`
        border-3 border-brutal-black shadow-brutal-lg overflow-hidden relative -mt-[3px]
        transition-all duration-700 ease-out
        ${isThinking
          ? 'w-[300px] h-0 opacity-0'
          : 'w-full h-auto bg-white px-6 py-5 opacity-100'
        }
      `}>
        <div className={`
          transition-opacity duration-500 delay-200 space-y-4
          ${isThinking ? 'opacity-0 invisible absolute' : 'opacity-100 visible relative'}
        `}>
          {showCopyButton && (
            <CopyButton
              text={cleanContent}
              className="absolute top-2 right-2 z-10"
            />
          )}
          {isStreamingThis ? (
            <StreamingContent content={message.content} messageIndex={messageIndex} />
          ) : (
            <StaticContent blocks={blocks} messageIndex={messageIndex} />
          )}
        </div>
      </div>
    </div>
  );
};
