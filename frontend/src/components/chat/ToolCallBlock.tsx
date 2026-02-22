import React, { useState } from 'react';
import { useI18n } from '../../i18n';

interface ToolCallBlockProps {
  toolName: string;
  toolArgs?: string;
  output?: string;
  defaultCollapsed?: boolean;
}

export const ToolCallBlock: React.FC<ToolCallBlockProps> = ({
  toolName,
  toolArgs,
  output,
  defaultCollapsed = true,
}) => {
  const [expanded, setExpanded] = useState(!defaultCollapsed);
  const { t } = useI18n();

  // Format tool name for display: snake_case → readable
  const displayName = toolName.replace(/_/g, ' ');

  const hasDetails = !!(toolArgs || output);
  const hasOutput = !!output;

  return (
    <div className="my-1.5">
      {/* Compact pill header */}
      <button
        onClick={() => hasDetails && setExpanded(!expanded)}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-mono font-bold uppercase tracking-wide rounded-sm transition-colors select-none ${
          hasDetails ? 'cursor-pointer hover:bg-neutral-100' : 'cursor-default'
        } ${expanded ? 'bg-neutral-100 text-brutal-black' : 'bg-transparent text-neutral-500 hover:text-brutal-black'}`}
      >
        {/* Icon */}
        <span className="text-xs shrink-0">🔧</span>

        {/* Tool name */}
        <span className="truncate max-w-[280px]">{displayName}</span>

        {/* Done badge when output is available */}
        {hasOutput && (
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

      {/* Expandable content - no outer border */}
      <div className={`
        grid transition-[grid-template-rows] duration-200 ease-out
        ${expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}
      `}>
        <div className="overflow-hidden min-h-0">
          <div className="ml-2 pl-3 border-l-2 border-neutral-200 mt-1 mb-2 space-y-2">
            {/* Arguments section */}
            {toolArgs && (
              <div>
                <div className="text-[10px] font-mono font-bold text-neutral-400 uppercase mb-0.5">{t('toolCallBlock.arguments')}</div>
                <pre className="text-[11px] text-neutral-600 leading-relaxed whitespace-pre-wrap break-all max-h-[200px] overflow-y-auto scrollbar-thin font-mono">
                  {toolArgs}
                </pre>
              </div>
            )}
            {/* Output section */}
            {output && (
              <div>
                <div className="text-[10px] font-mono font-bold text-neutral-400 uppercase mb-0.5">{t('toolCallBlock.output')}</div>
                <pre className="text-[11px] text-neutral-600 leading-relaxed whitespace-pre-wrap break-all max-h-[200px] overflow-y-auto scrollbar-thin font-mono">
                  {output}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
