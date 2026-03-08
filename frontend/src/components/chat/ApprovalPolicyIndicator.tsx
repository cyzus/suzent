import React, { useState } from 'react';
import { XMarkIcon, ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/24/outline';

interface ApprovalPolicyIndicatorProps {
  toolApprovalPolicy?: Record<string, string>;
  onRemovePolicy?: (toolName: string) => void;
}

/**
 * Displays active "Always Allow" tool approval policies.
 * Shows which tools are currently auto-approved for this chat.
 */
export const ApprovalPolicyIndicator: React.FC<ApprovalPolicyIndicatorProps> = ({
  toolApprovalPolicy = {},
  onRemovePolicy,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  // Get list of auto-approved tools
  const approvedTools = Object.entries(toolApprovalPolicy)
    .filter(([_, policy]) => policy === 'always_allow')
    .map(([toolName, _]) => toolName);

  // Don't render if no policies are active
  if (approvedTools.length === 0) {
    return null;
  }

  // Format tool name for display: bash_execute → Bash
  const formatToolName = (toolName: string): string => {
    // Remove common suffixes
    const cleaned = toolName.replace(/_execute$|_file$|_message$/i, '');
    // Capitalize first letter
    return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  };

  return (
    <div className="mb-2 bg-blue-50 border-2 border-blue-600 rounded-sm p-2">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 w-full text-left"
      >
        <div className="flex items-center gap-1.5 flex-1">
          <svg className="w-3.5 h-3.5 text-blue-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          <span className="text-[11px] font-bold text-blue-700 uppercase tracking-wide">
            {approvedTools.length} Auto-Approved Tool{approvedTools.length !== 1 ? 's' : ''}
          </span>
        </div>
        {isExpanded ? (
          <ChevronUpIcon className="w-3.5 h-3.5 text-blue-700" />
        ) : (
          <ChevronDownIcon className="w-3.5 h-3.5 text-blue-700" />
        )}
      </button>

      {/* Expanded list */}
      {isExpanded && (
        <div className="mt-2 space-y-1">
          {approvedTools.map((toolName) => (
            <div
              key={toolName}
              className="flex items-center justify-between gap-2 bg-white border-2 border-blue-400 rounded-sm px-2 py-1"
            >
              <span className="text-[11px] font-mono font-bold text-blue-800">
                {formatToolName(toolName)}
              </span>
              {onRemovePolicy && (
                <button
                  onClick={() => onRemovePolicy(toolName)}
                  className="p-0.5 hover:bg-red-50 rounded transition-colors"
                  title="Remove auto-approval for this tool"
                >
                  <XMarkIcon className="w-3 h-3 text-red-600" />
                </button>
              )}
            </div>
          ))}
          <div className="text-[10px] text-blue-600 mt-1">
            These tools won't require approval in this chat until you remove them or start a new chat.
          </div>
        </div>
      )}
    </div>
  );
};
