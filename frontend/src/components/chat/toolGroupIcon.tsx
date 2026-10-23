import type { ApprovalState } from './ToolCallBlock';
import { normalizeToolName } from './toolSummary';
import {
  ArrowDownOnSquareIcon,
  BoltIcon,
  CalendarDaysIcon,
  ChatBubbleLeftRightIcon,
  CircleStackIcon,
  ClipboardDocumentCheckIcon,
  ClipboardDocumentListIcon,
  ClockIcon,
  CommandLineIcon,
  CpuChipIcon,
  CursorArrowRaysIcon,
  DocumentPlusIcon,
  DocumentTextIcon,
  EyeIcon,
  FilmIcon,
  FlagIcon,
  FolderIcon,
  FolderOpenIcon,
  GlobeAltIcon,
  MagnifyingGlassIcon,
  NoSymbolIcon,
  PaintBrushIcon,
  PaperAirplaneIcon,
  PencilSquareIcon,
  PhotoIcon,
  PlayIcon,
  QuestionMarkCircleIcon,
  SignalIcon,
  SpeakerWaveIcon,
  Squares2X2Icon,
  StopIcon,
  UserGroupIcon,
  WrenchScrewdriverIcon,
} from '@heroicons/react/24/outline';

export type ToolGroupIconProps = {
  toolName: string;
  approvalState?: ApprovalState;
  isStreaming?: boolean;
  hasOutput?: boolean;
};

export type ToolIconAnimationKind =
  | 'none'
  | 'pending'
  | 'terminal'
  | 'scan'
  | 'typewriter'
  | 'radar'
  | 'signal'
  | 'memory'
  | 'snap'
  | 'cursor';

export type ToolRunningSurfaceClass =
  'brutal-running-mono' | 'brutal-running-dots' | 'brutal-running-scan';

const EXACT_TOOL_ICONS = {
  // Filesystem
  read_file: DocumentTextIcon,
  write_file: DocumentPlusIcon,
  edit_file: PencilSquareIcon,
  glob_search: FolderOpenIcon,
  grep_search: MagnifyingGlassIcon,

  // Shell & Processes
  run_command: CommandLineIcon,
  start_command: PlayIcon,
  check_command: SignalIcon,
  stop_command: StopIcon,

  // Web & Browser
  web_search: GlobeAltIcon,
  webpage_fetch: ArrowDownOnSquareIcon,
  browser_action: CursorArrowRaysIcon,

  // Memory & Recall
  memory_search: CpuChipIcon,
  memory_update: CpuChipIcon,
  session_search: ChatBubbleLeftRightIcon,

  // Planning, Tasks & Automation
  manage_goal: FlagIcon,
  create_tasks: ClipboardDocumentListIcon,
  update_task: ClipboardDocumentCheckIcon,
  list_tasks: ClipboardDocumentListIcon,
  schedule_cron: CalendarDaysIcon,
  skill_execute: BoltIcon,
  search_tools: MagnifyingGlassIcon,

  // Multimodal & Interaction
  render_ui: Squares2X2Icon,
  ask_question: QuestionMarkCircleIcon,
  generate_image: PhotoIcon,
  edit_image: PaintBrushIcon,
  analyze_image: EyeIcon,
  generate_video: FilmIcon,
  check_video_status: FilmIcon,
  speak: SpeakerWaveIcon,
  social_message: PaperAirplaneIcon,

  // Delegation & Agents
  agent: UserGroupIcon,
  agent_list: UserGroupIcon,
  agent_read: UserGroupIcon,
  agent_send: UserGroupIcon,
  agent_dispatch: UserGroupIcon,
  agent_stop: UserGroupIcon,
} as const;

export function pickToolIcon(toolName: string, approvalState?: ApprovalState) {
  if (approvalState === 'pending') return ClockIcon;
  if (approvalState === 'denied') return NoSymbolIcon;

  const canonical = normalizeToolName(toolName);
  if (canonical in EXACT_TOOL_ICONS) {
    return EXACT_TOOL_ICONS[canonical as keyof typeof EXACT_TOOL_ICONS];
  }

  // Fallback heuristics for custom MCP tools or future extensions
  if (canonical.includes('agent') || canonical.includes('subagent')) return UserGroupIcon;
  if (canonical.includes('memory')) return CpuChipIcon;
  if (canonical.includes('session') || canonical.includes('chat')) return ChatBubbleLeftRightIcon;
  if (canonical.includes('browser')) return CursorArrowRaysIcon;
  if (canonical.includes('fetch') || canonical.includes('scrape')) return ArrowDownOnSquareIcon;
  if (canonical.includes('web')) return GlobeAltIcon;
  if (canonical.includes('glob') || canonical.includes('dir')) return FolderOpenIcon;
  if (canonical.includes('search') || canonical.includes('grep') || canonical.includes('find'))
    return MagnifyingGlassIcon;
  if (canonical.includes('edit') || canonical.includes('patch') || canonical.includes('replace'))
    return PencilSquareIcon;
  if (canonical.includes('write') || canonical.includes('create_file')) return DocumentPlusIcon;
  if (canonical.includes('read')) return DocumentTextIcon;
  if (canonical.includes('file') || canonical.includes('folder')) return FolderIcon;
  if (
    canonical.includes('bash') ||
    canonical.includes('shell') ||
    canonical.includes('python') ||
    canonical.includes('command') ||
    canonical.includes('cmd') ||
    canonical.includes('exec')
  )
    return CommandLineIcon;
  if (canonical.includes('database') || canonical.includes('sql') || canonical.includes('db'))
    return CircleStackIcon;
  if (canonical.includes('goal')) return FlagIcon;
  if (canonical.includes('task') || canonical.includes('plan') || canonical.includes('todo'))
    return ClipboardDocumentListIcon;
  if (canonical.includes('schedule') || canonical.includes('cron')) return CalendarDaysIcon;
  if (canonical.includes('skill')) return BoltIcon;
  if (canonical.includes('image') || canonical.includes('photo')) return PhotoIcon;
  if (canonical.includes('video')) return FilmIcon;
  if (canonical.includes('speak') || canonical.includes('audio') || canonical.includes('voice'))
    return SpeakerWaveIcon;

  return WrenchScrewdriverIcon;
}

export function pickToolAnimationKind(
  toolName: string,
  approvalState?: ApprovalState,
  isStreaming = false,
  hasOutput = false
): ToolIconAnimationKind {
  if (approvalState === 'denied') return 'none';
  if (approvalState === 'pending') return 'pending';
  if (!isStreaming || hasOutput) return 'none';

  const canonical = normalizeToolName(toolName);

  switch (canonical) {
    case 'run_command':
    case 'start_command':
    case 'stop_command':
      return 'terminal';
    case 'check_command':
    case 'speak':
    case 'social_message':
      return 'signal';
    case 'read_file':
    case 'webpage_fetch':
    case 'analyze_image':
    case 'agent_read':
      return 'scan';
    case 'write_file':
    case 'edit_file':
    case 'create_tasks':
    case 'update_task':
    case 'manage_goal':
    case 'edit_image':
    case 'generate_image':
    case 'generate_video':
    case 'render_ui':
      return 'typewriter';
    case 'glob_search':
    case 'grep_search':
    case 'web_search':
    case 'search_tools':
    case 'list_tasks':
    case 'agent_list':
      return 'radar';
    case 'memory_search':
    case 'session_search':
    case 'agent':
    case 'agent_send':
    case 'agent_dispatch':
      return 'memory';
    case 'skill_execute':
    case 'schedule_cron':
      return 'snap';
    case 'browser_action':
      return 'cursor';
    default:
      break;
  }

  if (
    canonical.includes('bash') ||
    canonical.includes('shell') ||
    canonical.includes('command') ||
    canonical.includes('cmd')
  )
    return 'terminal';
  if (canonical.includes('read') || canonical.includes('fetch')) return 'scan';
  if (canonical.includes('write') || canonical.includes('edit')) return 'typewriter';
  if (canonical.includes('search') || canonical.includes('grep') || canonical.includes('glob'))
    return 'radar';
  if (canonical.includes('memory')) return 'memory';
  if (canonical.includes('browser')) return 'cursor';

  return 'terminal';
}

export function pickToolRunningSurfaceClass(toolName: string): ToolRunningSurfaceClass {
  const canonical = normalizeToolName(toolName);

  switch (canonical) {
    // 1. Search, Recall & Observation -> Vertical laser scan beam
    case 'glob_search':
    case 'grep_search':
    case 'web_search':
    case 'memory_search':
    case 'session_search':
    case 'search_tools':
    case 'analyze_image':
    case 'list_tasks':
    case 'agent_list':
    case 'agent_read':
    case 'check_video_status':
      return 'brutal-running-scan';

    // 2. I/O Transfer, File Mutation, Network & Media -> Punched-tape data dot matrix
    case 'read_file':
    case 'write_file':
    case 'edit_file':
    case 'webpage_fetch':
    case 'browser_action':
    case 'render_ui':
    case 'ask_question':
    case 'generate_image':
    case 'edit_image':
    case 'generate_video':
    case 'speak':
    case 'social_message':
    case 'create_tasks':
    case 'update_task':
    case 'manage_goal':
    case 'agent_send':
    case 'agent_dispatch':
      return 'brutal-running-dots';

    // 3. Compute, Shell Processes, Delegation & Automation -> 45-deg hazard stripes
    case 'run_command':
    case 'start_command':
    case 'check_command':
    case 'stop_command':
    case 'skill_execute':
    case 'schedule_cron':
    case 'agent':
    case 'agent_stop':
      return 'brutal-running-mono';

    default:
      break;
  }

  if (
    canonical.includes('search') ||
    canonical.includes('grep') ||
    canonical.includes('glob') ||
    canonical.includes('memory') ||
    canonical.includes('session') ||
    canonical.includes('vision') ||
    canonical.includes('analyze')
  ) {
    return 'brutal-running-scan';
  }

  if (
    canonical.includes('read') ||
    canonical.includes('write') ||
    canonical.includes('edit') ||
    canonical.includes('file') ||
    canonical.includes('fetch') ||
    canonical.includes('browser') ||
    canonical.includes('image') ||
    canonical.includes('video') ||
    canonical.includes('speak') ||
    canonical.includes('message')
  ) {
    return 'brutal-running-dots';
  }

  return 'brutal-running-mono';
}

export function ToolGroupIcon({
  toolName,
  approvalState,
  isStreaming = false,
  hasOutput = false,
}: ToolGroupIconProps) {
  const Icon = pickToolIcon(toolName, approvalState);
  const animKind = pickToolAnimationKind(toolName, approvalState, isStreaming, hasOutput);
  const animClass = animKind !== 'none' ? `tool-icon-anim-${animKind}` : '';

  return (
    <span
      className={`tool-group-icon inline-flex items-center justify-center shrink-0 transition-opacity duration-300 ${animClass}`.trim()}
      data-anim={animKind}
      aria-hidden="true"
    >
      <Icon className="w-3.5 h-3.5 stroke-[2.25]" />
    </span>
  );
}
