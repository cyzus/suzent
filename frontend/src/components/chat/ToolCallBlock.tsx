import React, { useState } from 'react';
import { useI18n } from '../../i18n';
import { MarkdownRenderer } from './MarkdownRenderer';
import { WebSearchRenderer } from './WebSearchRenderer';
import { ToolGroupIcon } from './toolGroupIcon';
import type { ApprovalRememberScope } from '../../hooks/useAGUI';

export type ApprovalState = 'pending' | 'approved' | 'denied' | undefined;

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
}) => {
  const [expanded, setExpanded] = useState(!defaultCollapsed);
  const { t } = useI18n();

  // Auto-expand when approval is requested
  React.useEffect(() => {
    if (approvalState === 'pending') {
      setExpanded(true);
    }
  }, [approvalState]);

  // Format tool name for display: snake_case → readable
  const displayName = toolName.replace(/_/g, ' ');

  const hasDetails = !!(toolArgs || output);
  const hasOutput = !!output;
  const isPending = approvalState === 'pending';
  const isDenied = approvalState === 'denied';
  const isWebTool = toolName === 'web_search' || toolName === 'webpage_fetch';
  const isBashTool = toolName === 'bash_execute';

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

  return (
    <div className="my-1.5 min-w-0 w-full overflow-x-hidden">
      {/* Compact pill header */}
      <button
        onClick={() => hasDetails && setExpanded(!expanded)}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-mono font-bold uppercase tracking-wide rounded-sm transition-colors select-none ${hasDetails ? 'cursor-pointer hover:bg-neutral-100 dark:hover:bg-zinc-700' : 'cursor-default'
          } ${expanded ? 'bg-neutral-100 dark:bg-zinc-700 text-brutal-black dark:text-white' : 'bg-transparent text-neutral-500 dark:text-neutral-400 hover:text-brutal-black dark:hover:text-white'
          } ${isStreaming && !hasOutput ? 'brutal-running-mono !text-brutal-black dark:!text-white border-2 !border-brutal-black dark:!border-white' : 'border-2 border-transparent'}`}
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

      {/* Expandable content */}
      <div className={`
        grid transition-[grid-template-rows] duration-200 ease-out overflow-hidden w-full
        ${expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}
      `}>
        <div className="overflow-hidden min-h-0 min-w-0 w-full">
          <div className="ml-2 pl-3 border-l-2 border-neutral-200 mt-1 mb-2 space-y-2 min-w-0 overflow-x-hidden">
            {/* Arguments or Running status */}
            {(toolArgs || (isStreaming && !output)) && (
              <div className="min-w-0 w-full overflow-hidden">
                <div className="text-[10px] font-mono font-bold text-neutral-400 dark:text-neutral-500 uppercase mb-1 flex items-center gap-2">
                  {isStreaming && !output ? (
                    <>
                      <span className="text-brutal-black dark:text-neutral-300 animate-pulse">Running {displayName}...</span>
                      <div className="h-[2px] flex-1 bg-neutral-100 dark:bg-zinc-700 overflow-hidden rounded-full">
                        <div className="h-full bg-brutal-black dark:bg-neutral-400 w-1/3 animate-neo-scan" />
                      </div>
                    </>
                  ) : (
                    t('toolCallBlock.arguments')
                  )}
                </div>
                {toolArgs && (
                  <div className="max-h-[200px] overflow-y-auto scrollbar-thin w-full" style={{ overflowX: 'hidden' }}>
                    <pre className="tool-call-pre text-[11px] text-neutral-600 dark:text-neutral-300 leading-relaxed font-mono w-full">
                      {toolArgs}
                    </pre>
                  </div>
                )}
              </div>
            )}

            {isPending && descriptionText && (
              <div className="w-full min-w-0 rounded-sm border-2 border-solid border-amber-500 bg-amber-50 px-2.5 py-2 overflow-hidden">
                <div className="text-[10px] font-mono font-bold uppercase tracking-wide text-amber-700">
                  Requested Action
                </div>
                <div className="mt-1 text-[12px] leading-relaxed text-amber-900 break-words whitespace-pre-wrap">
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
                    className="inline-flex items-center gap-1 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide bg-green-50 text-green-700 border-2 border-green-600 rounded-sm hover:bg-green-100 transition-colors"
                  >
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                    Allow
                  </button>
                  <>
                    <button
                      onClick={() => onApprove('session')}
                      className="inline-flex items-center gap-1 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide bg-blue-50 text-blue-700 border-2 border-blue-600 rounded-sm hover:bg-blue-100 transition-colors"
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
                      className="inline-flex items-center gap-1 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide bg-violet-50 text-violet-700 border-2 border-violet-600 rounded-sm hover:bg-violet-100 transition-colors"
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
                    className="inline-flex items-center gap-1 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide bg-red-50 text-red-700 border-2 border-red-600 rounded-sm hover:bg-red-100 transition-colors"
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
                <div className="text-[10px] flex items-center justify-between font-mono font-bold text-neutral-400 dark:text-neutral-500 uppercase mb-2">
                  <span>{t('toolCallBlock.output')}</span>
                </div>
                <div className="max-h-[300px] overflow-y-auto scrollbar-thin w-full" style={{ overflowX: 'hidden' }}>
                  {toolName.includes('search') || toolName.includes('web') ? (
                    <WebSearchRenderer output={output} />
                  ) : (
                    <pre className="tool-call-pre text-[11px] text-neutral-600 dark:text-neutral-300 leading-relaxed font-mono w-full">
                      {output}
                    </pre>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
