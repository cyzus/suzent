import React, { useState } from 'react';
import { useI18n } from '../../i18n';
import { MarkdownRenderer } from './MarkdownRenderer';
import { WebSearchRenderer } from './WebSearchRenderer';
import { ToolGroupIcon } from './toolGroupIcon';
import { FileDiffViewer } from './FileDiffViewer';
import { BashCommandRenderer, BashOutputRenderer } from './BashRenderer';
import type { ApprovalRememberScope } from '../../hooks/useAGUI';

export interface ToolRendererProps {
  toolName: string;
  parsedArgs: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
  output?: string;
}

// Renders in the args section; stays visible after execution.
const ARGS_RENDERERS: Record<string, React.FC<ToolRendererProps> | undefined> = {
  bash_execute: BashCommandRenderer,
  edit_file: FileDiffViewer,
  write_file: FileDiffViewer,
};

// Renders in the output section when output arrives.
// For bash: args section stays, output section shows stdout separately.
const OUTPUT_RENDERERS: Record<string, React.FC<ToolRendererProps> | undefined> = {
  bash_execute: BashOutputRenderer,
  read_file: FileDiffViewer,
};

export type ApprovalState = 'pending' | 'approved' | 'denied' | undefined;

interface ToolResultEnvelope {
  success?: boolean;
  message?: string;
  metadata?: unknown;
  error_code?: string;
}

function stripJsonFence(value: string): string {
  const trimmed = value.trim();
  const match = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  return match ? match[1].trim() : trimmed;
}

function parseToolResultEnvelope(output: string | undefined): ToolResultEnvelope | null {
  if (!output) return null;

  let current: unknown = output;
  for (let i = 0; i < 3; i += 1) {
    if (typeof current === 'string') {
      try {
        current = JSON.parse(stripJsonFence(current));
        continue;
      } catch {
        // Python repr fallback: {'success': True, 'message': '...', 'metadata': {...}}
        if (typeof current !== 'string') return null;
        const repr = current;
        const msgMatch = repr.match(/'message':\s*'((?:[^'\\]|\\.)*)'/s)
          ?? repr.match(/"message":\s*"((?:[^"\\]|\\.)*)"/s);
        if (!msgMatch) return null;
        const message = msgMatch[1].replace(/\\n/g, '\n').replace(/\\'/g, "'").replace(/\\"/g, '"');
        const rcMatch = repr.match(/'returncode':\s*(-?\d+)/);
        const cwdMatch = repr.match(/'cwd':\s*'((?:[^'\\]|\\.)*)'/);
        return {
          message,
          metadata: {
            returncode: rcMatch ? parseInt(rcMatch[1], 10) : undefined,
            cwd: cwdMatch ? cwdMatch[1] : undefined,
          },
        };
      }
    }

    if (current && typeof current === 'object' && !Array.isArray(current)) {
      const candidate = current as ToolResultEnvelope & {
        result?: unknown;
        content?: unknown;
        output?: unknown;
      };
      if (typeof candidate.message === 'string') return candidate;
      const nested = candidate.result ?? candidate.content ?? candidate.output;
      if (typeof nested === 'string') {
        current = nested;
        continue;
      }
      if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
        current = nested;
        continue;
      }
      return null;
    }

    return null;
  }

  const messageMatch = stripJsonFence(output).match(/"message"\s*:\s*"((?:\\.|[^"\\])*)"/);
  if (messageMatch) {
    try {
      return { message: JSON.parse(`"${messageMatch[1]}"`) };
    } catch {
      return { message: messageMatch[1].replace(/\\n/g, '\n').replace(/\\"/g, '"') };
    }
  }

  return null;
}

function formatToolArgsForDisplay(args: string | undefined): string {
  if (!args) return '';
  try {
    return JSON.stringify(JSON.parse(args), null, 2);
  } catch {
    return args;
  }
}

interface ToolCallBlockProps {
  toolName: string;
  toolArgs?: string;
  output?: string;
  defaultCollapsed?: boolean;
  approvalState?: ApprovalState;
  isStreaming?: boolean;
  onApprove?: (remember: ApprovalRememberScope) => void;
  onDeny?: () => void;
  isAutoApproved?: boolean;
  onRemovePolicy?: () => void;
  toolCallId?: string;
  onForceWebContext?: (contextId: string) => void;
  inActivityRail?: boolean;
}

export const ToolCallBlock: React.FC<ToolCallBlockProps> = ({
  toolName,
  toolArgs,
  output,
  defaultCollapsed = true,
  approvalState,
  isStreaming = false,
  onApprove,
  onDeny,
  isAutoApproved = false,
  onRemovePolicy,
  toolCallId,
  onForceWebContext,
  inActivityRail = false,
}) => {
  const [expanded, setExpanded] = useState(!defaultCollapsed);
  const { t } = useI18n();

  // Track whether the current expansion was forced open by a pending approval
  // (vs. opened by the user clicking), so we can auto-collapse it once resolved
  // without overriding a deliberate user expand.
  const autoExpandedByPendingRef = React.useRef(false);
  const userToggledRef = React.useRef(false);

  // Auto-expand when approval is requested; auto-collapse once the approval is
  // resolved and the result has arrived — unless the user manually toggled it.
  React.useEffect(() => {
    if (approvalState === 'pending') {
      autoExpandedByPendingRef.current = true;
      setExpanded(true);
    } else if (autoExpandedByPendingRef.current && output && !userToggledRef.current) {
      // Approval was granted/denied and output landed → collapse back to default.
      autoExpandedByPendingRef.current = false;
      setExpanded(false);
    }
  }, [approvalState, output]);

  // Format tool name for display: snake_case → readable
  const displayName = toolName.replace(/_/g, ' ');

  const hasDetails = !!(toolArgs || output);
  const hasOutput = !!output;
  const isPending = approvalState === 'pending';
  const isDenied = approvalState === 'denied';
  const isWebTool = toolName === 'web_search' || toolName === 'webpage_fetch';
  const isBashTool = toolName === 'bash_execute';
  const ArgsRenderer = ARGS_RENDERERS[toolName];
  const OutputRenderer = OUTPUT_RENDERERS[toolName];

  const parsedOutput = React.useMemo<ToolResultEnvelope | null>(() => {
    return parseToolResultEnvelope(output);
  }, [output]);

  const rendererMetadata = React.useMemo<Record<string, unknown> | undefined>(() => {
    const m = parsedOutput?.metadata;
    return m && typeof m === 'object' && !Array.isArray(m)
      ? m as Record<string, unknown>
      : undefined;
  }, [parsedOutput]);

  const parsedToolArgs = React.useMemo<Record<string, unknown> | null>(() => {
    if (!toolArgs) return null;
    try {
      const parsed = JSON.parse(toolArgs);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        return null;
      }
      return parsed as Record<string, unknown>;
    } catch {
      return null;
    }
  }, [toolArgs]);

  const { addedLines, removedLines } = React.useMemo(() => {
    let added = 0;
    let removed = 0;
    const isEditOrWrite = toolName === 'edit_file' || toolName === 'write_file';
    if (!isEditOrWrite) return { addedLines: 0, removedLines: 0 };
    
    try {
      const original = typeof rendererMetadata?.old_content === 'string' 
        ? rendererMetadata.old_content 
        : typeof parsedToolArgs?.old_string === 'string'
          ? parsedToolArgs.old_string
          : '';
      const modified = typeof rendererMetadata?.new_content === 'string'
        ? rendererMetadata.new_content
        : typeof parsedToolArgs?.new_string === 'string'
          ? parsedToolArgs.new_string
          : typeof parsedToolArgs?.content === 'string'
            ? parsedToolArgs.content
            : '';
      
      if (!original && !modified) return { addedLines: 0, removedLines: 0 };

      const originalLines = original.split('\n');
      const modifiedLines = modified.split('\n');
      const lengths = Array.from({ length: originalLines.length + 1 }, () =>
        Array<number>(modifiedLines.length + 1).fill(0)
      );

      for (let i = originalLines.length - 1; i >= 0; i -= 1) {
        for (let j = modifiedLines.length - 1; j >= 0; j -= 1) {
          lengths[i][j] = originalLines[i] === modifiedLines[j]
            ? lengths[i + 1][j + 1] + 1
            : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
        }
      }

      let i = 0;
      let j = 0;

      while (i < originalLines.length && j < modifiedLines.length) {
        if (originalLines[i] === modifiedLines[j]) {
          i += 1;
          j += 1;
        } else if (lengths[i + 1][j] >= lengths[i][j + 1]) {
          removed += 1;
          i += 1;
        } else {
          added += 1;
          j += 1;
        }
      }

      removed += originalLines.length - i;
      added += modifiedLines.length - j;
    } catch {
      // pass
    }
    return { addedLines: added, removedLines: removed };
  }, [toolName, parsedToolArgs, rendererMetadata]);

  const toolResultMessage = typeof parsedOutput?.message === 'string'
    ? parsedOutput.message
    : null;
  const displayToolArgs = React.useMemo(() => formatToolArgsForDisplay(toolArgs), [toolArgs]);

  const descriptionText = (() => {
    const raw = parsedToolArgs?.description;
    if (typeof raw !== 'string') return '';
    return raw.trim().replace(/\s+/g, ' ');
  })();

  const previewRememberedCommand = (() => {
    if (!isBashTool || !parsedToolArgs) return '';

    const rawCommand = typeof parsedToolArgs.content === 'string'
      ? parsedToolArgs.content
      : typeof parsedToolArgs.command === 'string'
        ? parsedToolArgs.command
        : '';

    const compact = rawCommand.trim().replace(/\s+/g, ' ');
    if (!compact) return '';
    return compact.length > 120 ? `${compact.slice(0, 117)}...` : compact;
  })();

  const headerClassName = [
    'group/tool-header inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-mono font-bold uppercase tracking-wide rounded-sm transition-colors select-none',
    hasDetails ? 'cursor-pointer hover:bg-neutral-100 dark:hover:bg-zinc-700' : 'cursor-default',
    expanded ? 'bg-neutral-100 dark:bg-zinc-700 text-brutal-black dark:text-white' : 'bg-transparent text-neutral-500 dark:text-neutral-400 hover:text-brutal-black dark:hover:text-white',
    isPending && inActivityRail
      ? 'tool-call-header-pending'
      : isStreaming && !hasOutput
        ? 'brutal-running-mono !text-brutal-black dark:!text-white border-2 !border-brutal-black dark:!border-white'
        : 'border-2 border-transparent',
  ].join(' ');

  const approveButtonClass = inActivityRail
    ? 'inline-flex items-center gap-1 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide bg-brutal-black text-white dark:bg-white dark:text-brutal-black border-2 border-brutal-black dark:border-white rounded-sm hover:-translate-y-[1px] hover:shadow-[3px_3px_0_#000] dark:hover:shadow-[3px_3px_0_#fff] active:translate-y-[1px] active:shadow-none transition-all'
    : 'inline-flex items-center gap-1 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide bg-green-50 text-green-700 border-2 border-green-600 rounded-sm hover:bg-green-100 transition-colors';
  const rememberSessionButtonClass = inActivityRail
    ? 'inline-flex items-center gap-1 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide bg-white dark:bg-zinc-900 text-brutal-black dark:text-white border-2 border-brutal-black dark:border-white rounded-sm hover:bg-neutral-100 dark:hover:bg-zinc-800 transition-colors'
    : 'inline-flex items-center gap-1 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide bg-blue-50 text-blue-700 border-2 border-blue-600 rounded-sm hover:bg-blue-100 transition-colors';
  const rememberGlobalButtonClass = inActivityRail
    ? 'inline-flex items-center gap-1 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide bg-white dark:bg-zinc-900 text-brutal-black dark:text-white border-2 border-brutal-black dark:border-white rounded-sm hover:bg-neutral-100 dark:hover:bg-zinc-800 transition-colors'
    : 'inline-flex items-center gap-1 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide bg-violet-50 text-violet-700 border-2 border-violet-600 rounded-sm hover:bg-violet-100 transition-colors';
  const denyButtonClass = inActivityRail
    ? 'inline-flex items-center gap-1 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide bg-white dark:bg-zinc-900 text-red-700 dark:text-red-300 border-2 border-red-700 dark:border-red-300 rounded-sm hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors'
    : 'inline-flex items-center gap-1 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide bg-red-50 text-red-700 border-2 border-red-600 rounded-sm hover:bg-red-100 transition-colors';

  return (
    <div className={`${inActivityRail ? 'my-0' : 'my-1.5'} min-w-0 w-full overflow-x-hidden`}>
      {/* Compact pill header */}
      {/* Header is a div (not button) so the inline auto-approve badge button
          below is valid HTML — a <button> cannot nest inside a <button>. */}
      <div
        role="button"
        tabIndex={hasDetails ? 0 : -1}
        aria-expanded={hasDetails ? expanded : undefined}
        onClick={() => {
          if (!hasDetails) return;
          userToggledRef.current = true;
          setExpanded(!expanded);
        }}
        onKeyDown={(e) => {
          if (!hasDetails) return;
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            userToggledRef.current = true;
            setExpanded(!expanded);
          }
        }}
        className={headerClassName}
      >
        {/* Icon */}
        <ToolGroupIcon
          toolName={toolName}
          approvalState={approvalState}
          isStreaming={isStreaming}
          hasOutput={hasOutput}
        />

        {/* Tool name */}
        <span className="truncate max-w-[280px]">{displayName}</span>

        {/* Diff lines if available */}
        {!expanded && (addedLines > 0 || removedLines > 0) && (
          <span className="flex items-center gap-1.5 opacity-90 text-[10px] ml-1 shrink-0 font-bold">
            {addedLines > 0 && <span className="text-green-600 dark:text-green-400">+{addedLines}</span>}
            {removedLines > 0 && <span className="text-red-600 dark:text-red-400">-{removedLines}</span>}
          </span>
        )}

        {/* Status badges */}
        {isPending && (
          <span className="flex items-center gap-0.5 shrink-0">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
          </span>
        )}
        {hasOutput && !isPending && !isDenied && (
          <span className="flex items-center gap-0.5 shrink-0">
            <svg className="w-2.5 h-2.5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </span>
        )}
        {isDenied && (
          <span className="text-[10px] text-red-500 font-bold shrink-0">DENIED</span>
        )}

        {/* Auto-approval badge (only shown when collapsed) */}
        {!expanded && isAutoApproved && !isPending && !isDenied && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRemovePolicy?.();
            }}
            className="flex items-center gap-1 px-1.5 py-0.5 bg-blue-50 border border-blue-600 rounded-sm hover:bg-blue-100 transition-colors shrink-0"
            title="This tool is auto-approved. Click to remove."
          >
            <svg className="w-2.5 h-2.5 text-blue-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            <span className="text-[9px] font-bold text-blue-700 uppercase">Auto</span>
            <svg className="w-2 h-2 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}

        {/* Expand/collapse chevron */}
        {hasDetails && !inActivityRail && (
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
        {hasDetails && inActivityRail && (
          <svg
            className={`w-3 h-3 text-neutral-400 opacity-0 transition-all duration-150 shrink-0 group-hover/tool-header:opacity-100 ${expanded ? 'rotate-90' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={3}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        )}
      </div>

      {/* Expandable content */}
      <div className={`
        grid transition-[grid-template-rows] duration-200 ease-out overflow-hidden w-full
        ${expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}
      `}>
        <div className="overflow-hidden min-h-0 min-w-0 w-full">
          <div className={`${inActivityRail ? 'ml-0 pl-0 pr-0 border-l-0' : 'ml-2 pl-3 pr-2 border-l-2 border-neutral-200 dark:border-zinc-700'} mt-1 mb-2 space-y-3 min-w-0 overflow-x-hidden`}>
            {/* Arguments or Running status */}
            {(toolArgs || (isStreaming && !output)) && !(OutputRenderer && hasOutput && !ArgsRenderer) && (
              <div className="min-w-0 w-full overflow-hidden">
                <div className="text-[10px] font-mono font-bold text-neutral-400 dark:text-neutral-500 uppercase mb-1.5 flex items-center gap-2 tracking-wide">
            {isStreaming && !output ? (
              <>
                      <span className="text-brutal-black dark:text-neutral-300 animate-pulse">
                        {isPending ? 'Approval needed' : `Running ${displayName}...`}
                      </span>
                      {!isPending && (
                        <div className="h-[2px] flex-1 bg-neutral-100 dark:bg-zinc-700 overflow-hidden rounded-full">
                          <div className="h-full bg-brutal-black dark:bg-neutral-400 w-1/3 animate-neo-scan" />
                        </div>
                      )}
                    </>
                  ) : (
                    t('toolCallBlock.arguments')
                  )}
                </div>
                {toolArgs && (
                  ArgsRenderer ? (
                    <ArgsRenderer
                      toolName={toolName}
                      parsedArgs={parsedToolArgs}
                      metadata={rendererMetadata}
                    />
                  ) : OutputRenderer ? (
                    <OutputRenderer
                      toolName={toolName}
                      parsedArgs={parsedToolArgs}
                      metadata={rendererMetadata}
                    />
                  ) : (
                    <div className="max-h-[220px] overflow-y-auto scrollbar-thin w-full rounded-sm bg-neutral-50/70 dark:bg-zinc-800/40 px-2.5 py-2" style={{ overflowX: 'hidden' }}>
                      <pre className="tool-call-pre font-mono text-[12px] leading-5 text-neutral-600 dark:text-neutral-300 w-full m-0">
                        {displayToolArgs}
                      </pre>
                    </div>
                  )
                )}
              </div>
            )}

            {isPending && descriptionText && (
              <div className={`${inActivityRail ? 'border-brutal-black bg-white dark:bg-zinc-900 text-brutal-black dark:text-neutral-100' : 'border-amber-500 bg-amber-50 text-amber-900'} w-full min-w-0 rounded-sm border-2 border-solid px-2.5 py-2 overflow-hidden`}>
                <div className={`${inActivityRail ? 'text-brutal-black dark:text-neutral-300' : 'text-amber-700'} text-[10px] font-mono font-bold uppercase tracking-wide`}>
                  Requested Action
                </div>
                <div className="mt-1 text-[12px] leading-relaxed break-words whitespace-pre-wrap">
                  {descriptionText}
                </div>
              </div>
            )}

            {/* Approval buttons — shown when tool is waiting for user decision */}
            {isPending && onApprove && onDeny && (
              <>
                <div className="flex items-center gap-2 py-2">
                  <button
                    onClick={() => onApprove(null)}
                    className={approveButtonClass}
                  >
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                    Allow
                  </button>
                  <>
                    <button
                      onClick={() => onApprove('session')}
                      className={rememberSessionButtonClass}
                      title={
                        isBashTool
                          ? (previewRememberedCommand
                            ? `Remember this exact bash command for the rest of this session: ${previewRememberedCommand}`
                            : 'Remember this exact bash command for the rest of this session')
                          : `Always allow ${displayName} for the rest of this session`
                      }
                    >
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                      </svg>
                      {isBashTool ? 'Remember This Command' : 'Always Allow (Session)'}
                    </button>
                    <button
                      onClick={() => onApprove('global')}
                      className={rememberGlobalButtonClass}
                      title={
                        isBashTool
                          ? (previewRememberedCommand
                            ? `Allow this exact bash command globally: ${previewRememberedCommand}`
                            : 'Allow this exact bash command globally')
                          : `Always allow ${displayName} globally`
                      }
                    >
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 9.75L12 4l9 5.75M4.5 10.5v7.25L12 22l7.5-4.25V10.5" />
                      </svg>
                      Always Allow (Global)
                    </button>
                  </>
                  <button
                    onClick={() => onDeny()}
                    className={denyButtonClass}
                  >
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                    Deny
                  </button>
                </div>
                <div className="space-y-1 text-[10px] text-neutral-500 leading-tight min-w-0 w-full overflow-hidden">
                  {isBashTool ? (
                    <>
                      {previewRememberedCommand ? (
                        <div className="break-words">
                          Applies to:{' '}
                          <span className="font-mono text-neutral-700 dark:text-neutral-300 break-all whitespace-pre-wrap">
                            {previewRememberedCommand}
                          </span>
                        </div>
                      ) : (
                        <div className="break-words">
                          These buttons remember the exact bash command, not the whole bash tool.
                        </div>
                      )}
                      <div className="break-words">
                        Remember This Command applies only for the current session. Always Allow (Global) writes a reusable bash command rule.
                      </div>
                    </>
                  ) : (
                    <div className="break-words">
                      Always Allow (Session) applies only in this chat session. Always Allow (Global) applies to this tool by name in future approvals.
                    </div>
                  )}
                </div>
              </>
            )}

            {/* Output section */}
            {output && (
              <div className="min-w-0 w-full overflow-hidden mt-2">
                <div className="text-[10px] flex items-center justify-between font-mono font-bold text-neutral-400 dark:text-neutral-500 uppercase mb-1.5 tracking-wide">
                  <span>{t('toolCallBlock.output')}</span>
                </div>
                {OutputRenderer ? (
                  <OutputRenderer
                    toolName={toolName}
                    parsedArgs={parsedToolArgs}
                    metadata={rendererMetadata}
                    output={toolResultMessage ?? output}
                  />
                ) : (
                  <div className="max-h-[320px] overflow-y-auto scrollbar-thin w-full rounded-sm bg-neutral-50/70 dark:bg-zinc-800/40 px-2.5 py-2" style={{ overflowX: 'hidden' }}>
                    {isWebTool ? (
                      <WebSearchRenderer output={output} />
                    ) : toolResultMessage ? (
                      <div className="tool-result-markdown text-[13px] leading-6 text-neutral-700 dark:text-neutral-300 break-words">
                        <MarkdownRenderer content={toolResultMessage} />
                      </div>
                    ) : toolName.includes('search') || toolName.includes('web') ? (
                      <WebSearchRenderer output={output} />
                    ) : (
                      <pre className="tool-call-pre font-mono text-[12px] leading-5 text-neutral-600 dark:text-neutral-300 w-full m-0">
                        {output}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
