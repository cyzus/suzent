import type { ApprovalState } from './ToolCallBlock';
import {
  CircleStackIcon,
  CommandLineIcon,
  ComputerDesktopIcon,
  DocumentTextIcon,
  FolderIcon,
  MagnifyingGlassIcon,
  NoSymbolIcon,
  WrenchScrewdriverIcon,
  ClockIcon,
  ClipboardDocumentListIcon,
} from '@heroicons/react/24/outline';

type ToolGroupIconProps = {
  toolName: string;
  approvalState?: ApprovalState;
  isStreaming?: boolean;
  hasOutput?: boolean;
};

function pickIcon(toolName: string, approvalState?: ApprovalState) {
  if (approvalState === 'pending') return ClockIcon;
  if (approvalState === 'denied') return NoSymbolIcon;
  if (toolName.includes('search') || toolName.includes('web')) return MagnifyingGlassIcon;
  if (toolName.includes('file') || toolName.includes('dir')) return FolderIcon;
  if (toolName.includes('read') || toolName.includes('write')) return DocumentTextIcon;
  if (toolName.includes('bash') || toolName.includes('shell') || toolName.includes('python') || toolName.includes('cmd')) return CommandLineIcon;
  if (toolName.includes('database') || toolName.includes('sql')) return CircleStackIcon;
  if (toolName.includes('plan')) return ClipboardDocumentListIcon;
  if (toolName.includes('agent') || toolName.includes('subagent')) return ComputerDesktopIcon;
  return WrenchScrewdriverIcon;
}

export function ToolGroupIcon({ toolName, approvalState, isStreaming = false, hasOutput = false }: ToolGroupIconProps) {
  const Icon = pickIcon(toolName, approvalState);

  return (
    <span
      className={`tool-group-icon inline-flex items-center justify-center shrink-0 ${isStreaming && !hasOutput ? 'animate-spin-slow' : ''}`}
      aria-hidden="true"
    >
      <Icon className="w-3.5 h-3.5 stroke-[2.25]" />
    </span>
  );
}