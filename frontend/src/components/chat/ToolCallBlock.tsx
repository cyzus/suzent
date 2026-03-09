import React, { useState } from 'react';
import { useI18n } from '../../i18n';

export type ApprovalState = 'pending' | 'approved' | 'denied' | undefined;

interface ToolCallBlockProps {
  toolName: string;
  toolArgs?: string;
  output?: string;
  defaultCollapsed?: boolean;
  approvalState?: ApprovalState;
  isStreaming?: boolean;
  onApprove?: (remember: 'session' | null) => void;
  onDeny?: () => void;
  isAutoApproved?: boolean;
  onRemovePolicy?: () => void;
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

  return (
    <div className="my-1.5 min-w-0 w-full overflow-x-hidden">
      {/* Compact pill header */}
      <button
        onClick={() => hasDetails && setExpanded(!expanded)}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-mono font-bold uppercase tracking-wide rounded-sm transition-colors select-none ${hasDetails ? 'cursor-pointer hover:bg-neutral-100 dark:hover:bg-zinc-700' : 'cursor-default'
          } ${expanded ? 'bg-neutral-100 dark:bg-zinc-700 text-brutal-black dark:text-white' : 'bg-transparent text-neutral-500 dark:text-neutral-400 hover:text-brutal-black dark:hover:text-white'}`}
      >
        {/* Icon */}
        <span className={`text-xs shrink-0 ${isStreaming && !hasOutput ? 'animate-spin-slow' : ''}`}>
          {isPending ? '⏳' : isDenied ? '🚫' : '🔧'}
        </span>

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
          <div className="ml-2 pl-3 border-l-2 border-neutral-200 mt-1 mb-2 space-y-2 min-w-0 w-full overflow-x-hidden">
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

            {/* Approval buttons — shown when tool is waiting for user decision */}
            {isPending && onApprove && onDeny && (
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
                <button
                  onClick={() => onApprove('session')}
                  className="inline-flex items-center gap-1 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide bg-blue-50 text-blue-700 border-2 border-blue-600 rounded-sm hover:bg-blue-100 transition-colors"
                  title="Allow this tool for the rest of this session"
                >
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                  </svg>
                  Always Allow
                </button>
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
            )}

            {/* Output section */}
            {output && (
              <div className="min-w-0 w-full overflow-hidden">
                <div className="text-[10px] font-mono font-bold text-neutral-400 dark:text-neutral-500 uppercase mb-0.5">{t('toolCallBlock.output')}</div>
                <div className="max-h-[200px] overflow-y-auto scrollbar-thin w-full" style={{ overflowX: 'hidden' }}>
                  <pre className="tool-call-pre text-[11px] text-neutral-600 dark:text-neutral-300 leading-relaxed font-mono w-full">
                    {output}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
