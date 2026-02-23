import React, { useState, useEffect, useRef } from 'react';
import { useI18n } from '../../i18n';
import { normalizePythonCode } from '../../lib/chatUtils';

interface CodeStepBlockProps {
  thought: string;
  codeContent?: string;
  executionLogs?: string;
  result?: string;
  defaultCollapsed?: boolean;
  isStreaming?: boolean;
}

export const CodeStepBlock: React.FC<CodeStepBlockProps> = ({
  thought,
  codeContent,
  executionLogs,
  result,
  defaultCollapsed = true,
  isStreaming = false,
}) => {
  const [expanded, setExpanded] = useState(!defaultCollapsed || isStreaming);
  const wasStreamingRef = useRef(isStreaming);
  const { t } = useI18n();

  // Expand when streaming starts (only on initial mount or transition to streaming)
  useEffect(() => {
    if (isStreaming && !wasStreamingRef.current) setExpanded(true);
    wasStreamingRef.current = isStreaming;
  }, [isStreaming]);

  // Auto-collapse when streaming ends
  useEffect(() => {
    if (!isStreaming && wasStreamingRef.current) {
      const timer = setTimeout(() => setExpanded(false), 600);
      return () => clearTimeout(timer);
    }
  }, [isStreaming]);

  // Truncate thought for collapsed view
  const firstLine = thought.split('\n')[0];
  const truncated = firstLine.length > 80 ? firstLine.slice(0, 77) + '...' : firstLine;
  const hasDetails = !!(thought || codeContent || executionLogs || result);
  const isDone = !!(result || executionLogs);
  const isExecuting = isStreaming && !!codeContent && !executionLogs;

  // Smooth cursor for streaming
  const cursor = <span className="inline-block w-1.5 h-3.5 bg-neutral-400 align-middle ml-0.5 animate-pulse rounded-sm" />;

  return (
    <div className="my-1.5">
      {/* Compact pill header */}
      <div className="relative">
        <button
          onClick={() => hasDetails && setExpanded(!expanded)}
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-mono font-bold uppercase tracking-wide rounded-sm transition-colors select-none relative overflow-hidden ${
            hasDetails ? 'cursor-pointer hover:bg-neutral-100' : 'cursor-default'
          } ${isStreaming
            ? 'bg-neutral-100 text-brutal-black border border-neutral-300'
            : expanded
              ? 'bg-neutral-100 text-brutal-black'
              : 'bg-transparent text-neutral-500 hover:text-brutal-black'
          }`}
        >
          {/* Streaming: sliding progress bar at bottom of pill */}
          {isStreaming && (
            <span className="absolute bottom-0 left-0 w-full h-[3px]">
              <span className="absolute inset-0 bg-neutral-200" />
              <span className="absolute top-0 left-0 h-full w-1/3 bg-brutal-black animate-[brutalSlideBar_1.2s_ease-in-out_infinite]" />
            </span>
          )}

          {/* Icon state */}
          {isExecuting ? (
            <span className="shrink-0 text-[10px] font-bold tracking-widest text-brutal-black">▶</span>
          ) : isStreaming ? (
            <span className="relative w-2.5 h-2.5 shrink-0">
              <span className="absolute inset-0 rounded-full bg-brutal-black opacity-30 animate-ping" />
              <span className="relative block w-2.5 h-2.5 rounded-full bg-brutal-black" />
            </span>
          ) : (
            <span className="text-xs shrink-0">💭</span>
          )}

          {/* Truncated thought */}
          <span className="truncate max-w-[320px] normal-case tracking-normal">{truncated}</span>

          {/* Executing label */}
          {isExecuting && (
            <span className="text-[9px] font-mono font-bold text-neutral-400 uppercase tracking-widest shrink-0">running</span>
          )}

          {/* Done badge */}
          {isDone && !isStreaming && (
            <span className="flex items-center gap-0.5 shrink-0">
              <svg className="w-2.5 h-2.5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </span>
          )}

          {/* Expand/collapse chevron */}
          {hasDetails && (
            <svg
              className={`w-3 h-3 text-neutral-400 transition-transform duration-200 shrink-0 ${expanded ? 'rotate-180' : ''}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={3}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          )}
        </button>
      </div>

      {/* Expandable content */}
      <div className={`
        grid transition-[grid-template-rows] duration-500 ease-in-out
        ${expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}
      `}>
        <div className="overflow-hidden min-h-0">
          <div className="ml-2 pl-3 border-l-2 border-neutral-200 mt-1 mb-2 space-y-2">
            {/* Thought section */}
            {thought && (
              <div>
                <div className="text-[10px] font-mono font-bold text-neutral-400 uppercase mb-0.5">{t('codeStepBlock.thought')}</div>
                <div className="text-[11px] text-neutral-600 leading-relaxed whitespace-pre-wrap break-words max-h-[200px] overflow-y-auto scrollbar-thin font-mono">
                  {thought}{isStreaming && !codeContent && cursor}
                </div>
              </div>
            )}
            {/* Code section — dark bg, horizontal scroll, no word wrap */}
            {codeContent && (
              <div>
                <div className="text-[10px] font-mono font-bold text-neutral-400 uppercase mb-0.5">{t('codeStepBlock.code')}</div>
                <pre className="text-[11px] font-mono text-neutral-800 leading-relaxed whitespace-pre overflow-x-auto overflow-y-auto max-h-[300px] scrollbar-thin bg-neutral-100 rounded p-2.5 border border-neutral-200">
                  {normalizePythonCode(codeContent)}{isStreaming && !executionLogs && <span className="inline-block w-1.5 h-3.5 bg-neutral-400 align-middle ml-0.5 animate-pulse rounded-sm" />}
                </pre>
              </div>
            )}
            {/* Executing indicator — shown after code is written, before logs arrive */}
            {isStreaming && codeContent && !executionLogs && (
              <div className="flex items-center gap-2 py-1">
                <span className="text-[10px] font-mono font-bold text-neutral-400 uppercase tracking-wider">executing</span>
              </div>
            )}
            {/* Execution Logs section */}
            {executionLogs && (
              <div>
                <div className="text-[10px] font-mono font-bold text-neutral-400 uppercase mb-0.5">{t('codeStepBlock.executionLogs')}</div>
                <div className="text-[11px] text-neutral-600 leading-relaxed whitespace-pre-wrap break-words max-h-[200px] overflow-y-auto scrollbar-thin font-mono">
                  {executionLogs}
                </div>
              </div>
            )}
            {/* Result section */}
            {result && (
              <div>
                <div className="text-[10px] font-mono font-bold text-neutral-400 uppercase mb-0.5">{t('codeStepBlock.result')}</div>
                <div className="text-[11px] text-neutral-600 leading-relaxed whitespace-pre-wrap break-words max-h-[200px] overflow-y-auto scrollbar-thin font-mono">
                  {result}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
