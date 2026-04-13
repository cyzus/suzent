import type { ApprovalState } from './ToolCallBlock';

export function getToolIcon(toolName: string, approvalState?: ApprovalState): string {
  if (approvalState === 'pending') return '⏳';
  if (approvalState === 'denied') return '🚫';
  if (toolName.includes('search') || toolName.includes('web')) return '🔍';
  if (toolName.includes('file') || toolName.includes('dir') || toolName.includes('read') || toolName.includes('write')) return '📁';
  if (toolName.includes('bash') || toolName.includes('shell') || toolName.includes('python') || toolName.includes('cmd')) return '💻';
  if (toolName.includes('database') || toolName.includes('sql')) return '🗄️';
  if (toolName.includes('plan')) return '📋';
  return '🔧';
}

export function getToolIconClassName(isStreaming = false, hasOutput = false, monochrome = false): string {
  return [
    'tool-group-icon',
    'inline-flex',
    'items-center',
    'justify-center',
    'text-xs',
    'leading-none',
    'shrink-0',
    monochrome ? 'tool-group-icon--mono' : '',
    isStreaming && !hasOutput ? 'animate-pulse text-brutal-blue' : '',
  ]
    .filter(Boolean)
    .join(' ');
}