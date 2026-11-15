import React, { useEffect, useRef } from 'react';
import type { ApprovalState } from './ToolCallBlock';
import { normalizeToolName } from './toolSummary';
import { clamp } from '../../lib/suzentBot/suzentBotGeometry';
import { cubicInOut, cubicOut, springValue, stepSpring } from '../../lib/suzentBot/suzentBotPhysics';
import {
  ArrowDownOnSquareIcon,
  BoltIcon,
  CalendarDaysIcon,
  ChatBubbleLeftRightIcon,
  CircleStackIcon,
  CodeBracketIcon,
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
  run_code: CodeBracketIcon,

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
  analyze_visual: EyeIcon,
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
    case 'run_code':
      return 'terminal';
    case 'check_command':
    case 'speak':
    case 'social_message':
      return 'signal';
    case 'read_file':
    case 'webpage_fetch':
    case 'analyze_image':
    case 'analyze_visual':
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
    case 'analyze_visual':
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
    case 'run_code':
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

export type ToolSvgGlyphKind =
  | 'read'
  | 'write'
  | 'search'
  | 'globe'
  | 'folder'
  | 'terminal'
  | 'memory'
  | 'tasks'
  | 'bolt'
  | 'cursor'
  | 'signal'
  | 'pending';

function pickToolSvgGlyphKind(
  toolName: string,
  animKind: ToolIconAnimationKind
): ToolSvgGlyphKind {
  if (animKind === 'pending') return 'pending';
  const canonical = normalizeToolName(toolName);
  switch (canonical) {
    case 'read_file':
    case 'webpage_fetch':
    case 'agent_read':
      return 'read';
    case 'write_file':
    case 'edit_file':
    case 'edit_image':
    case 'generate_image':
    case 'generate_video':
    case 'render_ui':
      return 'write';
    case 'glob_search':
      return 'folder';
    case 'web_search':
      return 'globe';
    case 'grep_search':
    case 'search_tools':
    case 'list_tasks':
    case 'agent_list':
      return 'search';
    case 'run_command':
    case 'start_command':
    case 'stop_command':
    case 'run_code':
      return 'terminal';
    case 'memory_search':
    case 'memory_update':
    case 'session_search':
    case 'agent':
    case 'agent_send':
    case 'agent_dispatch':
      return 'memory';
    case 'create_tasks':
    case 'update_task':
    case 'manage_goal':
      return 'tasks';
    case 'skill_execute':
    case 'schedule_cron':
      return 'bolt';
    case 'browser_action':
    case 'analyze_image':
    case 'analyze_visual':
      return 'cursor';
    case 'check_command':
    case 'speak':
    case 'social_message':
      return 'signal';
    default:
      break;
  }
  switch (animKind) {
    case 'scan':
      return 'read';
    case 'typewriter':
      return 'write';
    case 'radar':
      return 'search';
    case 'terminal':
      return 'terminal';
    case 'memory':
      return 'memory';
    case 'snap':
      return 'bolt';
    case 'cursor':
      return 'cursor';
    case 'signal':
      return 'signal';
    default:
      return 'terminal';
  }
}

/**
 * Dedicated 24x24 semantic tool-icon SVG with 120Hz internal spring-physics &
 * path-choreography animation (`read`, `write`, `search`, `globe`, `folder`,
 * `terminal`, `memory`, `tasks`, `bolt`, `cursor`, `signal`, `pending`).
 *
 * Distinct from `SuzentBotMark` — uses the actual 24x24 stroke-2.25 silhouette
 * of each tool icon and animates its internal mechanical parts in real time.
 */
const AnimatedToolGlyphSvg: React.FC<{ kind: ToolSvgGlyphKind }> = React.memo(({ kind }) => {
  const svgRef = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return undefined;

    const startedAt = performance.now();
    let lastTime = startedAt;
    let frameId = 0;

    // Internal spring states for elastic micro-mechanics
    const springA = springValue(0);
    const springB = springValue(0);
    let stepIndex = -1;

    const tick = (now: number) => {
      const dt = clamp((now - lastTime) / 1000, 0.001, 0.05);
      lastTime = now;
      const t = (now - startedAt) / 1000;

      if (kind === 'read') {
        // Document page with sequential line-by-line reading reveal + sliding reading pointer dot
        const cyc = (t / 1.25) % 1;
        const row = cyc < 0.32 ? 0 : cyc < 0.64 ? 1 : 2;
        const rowY = row === 0 ? 11.2 : row === 1 ? 14.6 : 18.0;
        springA.target = rowY;
        stepSpring(springA, 22, 0.76, dt);

        const dot = svg.querySelector('.tg-read-dot') as SVGCircleElement | null;
        const lines = svg.querySelectorAll('.tg-read-line');
        let activeX2 = 12;

        lines.forEach((el, idx) => {
          const maxW = idx === 2 ? 4.8 : 7.4;
          let progress = 1;
          if (idx === row) {
            const localP = clamp((cyc - idx * 0.32) / 0.28, 0.15, 1);
            progress = cubicOut(localP);
            activeX2 = 8.2 + maxW * progress;
          } else if (idx > row) {
            progress = 0.28;
          }
          el.setAttribute('x2', (8.2 + maxW * progress).toFixed(2));
          el.setAttribute('opacity', idx === row ? '1' : idx < row ? '0.85' : '0.32');
        });

        if (dot) {
          dot.setAttribute('cx', activeX2.toFixed(2));
          dot.setAttribute('cy', springA.x.toFixed(2));
        }
      } else if (kind === 'write') {
        // Pencil nib actively scribbling across a document card + live drawn stroke
        const cyc = (t / 1.4) % 1;
        let nibX = 10;
        let nibY = 14;
        let tilt = 0;
        let lineProgress = 0;
        if (cyc < 0.74) {
          const p = cyc / 0.74;
          lineProgress = p;
          const wiggle = Math.sin(p * Math.PI * 5) * 0.85;
          nibX = 7.5 + p * 6.5;
          nibY = 14.5 + wiggle;
          tilt = Math.cos(p * Math.PI * 5) * 8;
        } else {
          const p = cubicInOut((cyc - 0.74) / 0.26);
          lineProgress = 1 - p;
          nibX = 14 - p * 6.5;
          nibY = 14.5 - 2.6 * Math.sin(p * Math.PI);
          tilt = -12 * Math.sin(p * Math.PI);
        }
        const pen = svg.querySelector('.tg-write-pen') as SVGGElement | null;
        const ink1 = svg.querySelector('.tg-write-ink1') as SVGLineElement | null;
        const ink2 = svg.querySelector('.tg-write-ink2') as SVGLineElement | null;
        if (pen) {
          const dx = nibX - 11.5;
          const dy = nibY - 12.5;
          pen.setAttribute(
            'transform',
            `translate(${dx.toFixed(2)} ${dy.toFixed(2)}) rotate(${tilt.toFixed(1)} 11.5 12.5)`
          );
        }
        if (ink1) {
          ink1.setAttribute('x2', (7.5 + 6.5 * clamp(lineProgress * 1.3, 0.15, 1)).toFixed(2));
        }
        if (ink2) {
          const p2 = clamp((lineProgress - 0.35) / 0.65, 0, 1);
          ink2.setAttribute('x2', (7.5 + 4.8 * p2).toFixed(2));
          ink2.setAttribute('opacity', p2 > 0.02 ? '0.9' : '0');
        }
      } else if (kind === 'search') {
        // Magnifying glass sweeping in a spring figure-8 + lens zoom pulse & target reticle
        const step = Math.floor(t / 0.55);
        if (step !== stepIndex) {
          stepIndex = step;
          const targets = [
            [-1.6, -1.2],
            [1.7, -0.9],
            [0.4, 1.5],
            [-1.3, 1.1],
          ];
          const [tx, ty] = targets[step % targets.length];
          springA.target = tx;
          springB.target = ty;
        }
        stepSpring(springA, 16, 0.68, dt);
        stepSpring(springB, 16, 0.68, dt);
        const glass = svg.querySelector('.tg-search-glass') as SVGGElement | null;
        const glint = svg.querySelector('.tg-search-glint') as SVGPathElement | null;
        if (glass) {
          const zoom = 1 + 0.08 * Math.sin(t * 6.5);
          glass.setAttribute(
            'transform',
            `translate(${springA.x.toFixed(2)} ${springB.x.toFixed(2)}) translate(10.5 10.5) scale(${zoom.toFixed(3)}) translate(-10.5 -10.5)`
          );
        }
        if (glint) {
          glint.setAttribute('opacity', (0.45 + 0.55 * Math.abs(Math.sin(t * 4.2))).toFixed(2));
        }
      } else if (kind === 'globe') {
        // Globe with 3D rotating meridian ellipse + latitude pulse
        const phase = (t * 0.95) % 1;
        const rx = Math.max(0.6, Math.abs(Math.cos(phase * Math.PI)) * 4.6);
        const meridian = svg.querySelector('.tg-globe-meridian') as SVGEllipseElement | null;
        const sat = svg.querySelector('.tg-globe-sat') as SVGCircleElement | null;
        if (meridian) {
          meridian.setAttribute('rx', rx.toFixed(2));
        }
        if (sat) {
          const a = t * 4.2;
          sat.setAttribute('cx', (12 + 8.5 * Math.cos(a)).toFixed(2));
          sat.setAttribute('cy', (12 + 3.6 * Math.sin(a)).toFixed(2));
        }
      } else if (kind === 'folder') {
        // Folder flap opening & closing with rising file sheet inside
        const wave = 0.5 + 0.5 * Math.sin(t * 5.2);
        const sheet = svg.querySelector('.tg-folder-sheet') as SVGRectElement | null;
        const front = svg.querySelector('.tg-folder-front') as SVGPathElement | null;
        if (sheet) {
          sheet.setAttribute('y', (8.8 - wave * 2.4).toFixed(2));
        }
        if (front) {
          front.setAttribute(
            'transform',
            `translate(12 19) scale(1 ${(1 - wave * 0.12).toFixed(3)}) translate(-12 -19)`
          );
        }
      } else if (kind === 'terminal') {
        // Terminal frame with spring-striking `>` chevron + blinking block cursor `_`
        const beat = (t * 2.2) % 1;
        springA.target = beat < 0.25 ? 1.35 : 0;
        stepSpring(springA, 22, 0.62, dt);
        const chev = svg.querySelector('.tg-term-chev') as SVGPathElement | null;
        const cur = svg.querySelector('.tg-term-cursor') as SVGLineElement | null;
        if (chev) {
          chev.setAttribute('transform', `translate(${springA.x.toFixed(2)} 0)`);
        }
        if (cur) {
          const on = Math.sin(t * Math.PI * 4.5) > -0.15;
          cur.setAttribute('opacity', on ? '1' : '0.18');
        }
      } else if (kind === 'memory') {
        // CPU / Memory chip with pulsing core die + alternating pin data firing
        const pulse = 0.86 + 0.18 * Math.sin(t * 6.0);
        const core = svg.querySelector('.tg-mem-core') as SVGRectElement | null;
        const pins = svg.querySelectorAll('.tg-mem-pin');
        if (core) {
          core.setAttribute(
            'transform',
            `translate(12 12) scale(${pulse.toFixed(3)}) translate(-12 -12)`
          );
        }
        pins.forEach((pin, idx) => {
          const active = Math.sin(t * 7.5 - idx * 1.1) > 0;
          pin.setAttribute('opacity', active ? '1' : '0.32');
        });
      } else if (kind === 'tasks') {
        // Clipboard with spring-popping checkmark & sliding task bars
        const cyc = (t / 1.5) % 1;
        const check = svg.querySelector('.tg-task-check') as SVGPathElement | null;
        const bar1 = svg.querySelector('.tg-task-bar1') as SVGLineElement | null;
        const bar2 = svg.querySelector('.tg-task-bar2') as SVGLineElement | null;
        if (check) {
          const p = clamp(cyc / 0.45, 0, 1);
          const len = 10;
          check.setAttribute('stroke-dashoffset', (len * (1 - cubicOut(p))).toFixed(2));
        }
        if (bar1) {
          const p = clamp((cyc - 0.15) / 0.5, 0.25, 1);
          bar1.setAttribute('x2', (11.5 + 4.5 * cubicOut(p)).toFixed(2));
        }
        if (bar2) {
          const p = clamp((cyc - 0.35) / 0.5, 0.2, 1);
          bar2.setAttribute('x2', (11.5 + 3.8 * cubicOut(p)).toFixed(2));
        }
      } else if (kind === 'bolt') {
        // Skill lightning bolt with high-voltage spring recoil & corner sparks
        const cyc = (t * 1.9) % 1;
        springA.target = cyc < 0.22 ? 1.16 : 0.94;
        stepSpring(springA, 24, 0.52, dt);
        const bolt = svg.querySelector('.tg-bolt-main') as SVGPathElement | null;
        const sparks = svg.querySelectorAll('.tg-bolt-spark');
        if (bolt) {
          const rot = Math.sin(t * 14) * (cyc < 0.3 ? 6 : 1);
          bolt.setAttribute(
            'transform',
            `translate(12 12) rotate(${rot.toFixed(1)}) scale(${springA.x.toFixed(3)}) translate(-12 -12)`
          );
        }
        sparks.forEach((sp, i) => {
          const op = clamp(Math.sin(t * 9 + i * 2.1), 0, 1);
          sp.setAttribute('opacity', op.toFixed(2));
        });
      } else if (kind === 'cursor') {
        // Browser pointer hopping, clicking with spring compression + expanding click ripple
        const cyc = (t / 1.3) % 1;
        const click = cyc > 0.35 && cyc < 0.58;
        springA.target = click ? 0.82 : 1;
        stepSpring(springA, 24, 0.58, dt);
        const arrow = svg.querySelector('.tg-cursor-arrow') as SVGPathElement | null;
        const ring = svg.querySelector('.tg-cursor-ring') as SVGCircleElement | null;
        if (arrow) {
          const hopX = Math.sin(t * 3.2) * 1.1;
          const hopY = Math.cos(t * 3.2) * 0.9;
          arrow.setAttribute(
            'transform',
            `translate(${hopX.toFixed(2)} ${hopY.toFixed(2)}) translate(11 11) scale(${springA.x.toFixed(3)}) translate(-11 -11)`
          );
        }
        if (ring) {
          const rp = clamp((cyc - 0.36) / 0.52, 0, 1);
          ring.setAttribute('r', (2.2 + rp * 5.8).toFixed(2));
          ring.setAttribute('opacity', rp > 0 && rp < 1 ? ((1 - rp) * 0.95).toFixed(2) : '0');
        }
      } else if (kind === 'signal') {
        // Signal broadcast waves radiating outward sequentially
        const waves = svg.querySelectorAll('.tg-sig-wave');
        waves.forEach((w, idx) => {
          const phase = ((t * 1.6 - idx * 0.28) % 1 + 1) % 1;
          const op = Math.sin(phase * Math.PI);
          w.setAttribute('opacity', clamp(op, 0.2, 1).toFixed(2));
        });
      } else if (kind === 'pending') {
        // Clock with long sweeping minute hand & short spring-stepping hour hand
        // Every full 360° sweep of the minute hand (1.5s), the short hour hand steps 30° (1 hour)!
        const minHand = svg.querySelector('.tg-clock-min') as SVGLineElement | null;
        const hourHand = svg.querySelector('.tg-clock-hour') as SVGLineElement | null;
        const period = 1.5;
        if (minHand) {
          const minDeg = ((t / period) * 360) % 360;
          minHand.setAttribute('transform', `rotate(${minDeg.toFixed(1)} 12 12)`);
        }
        if (hourHand) {
          const hourStepDeg = Math.floor(t / period) * 30;
          springA.target = hourStepDeg;
          stepSpring(springA, 22, 0.62, dt);
          hourHand.setAttribute('transform', `rotate(${(springA.x % 360).toFixed(1)} 12 12)`);
        }
      }

      frameId = requestAnimationFrame(tick);
    };

    frameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameId);
  }, [kind]);

  return (
    <svg
      ref={svgRef}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.25}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="w-3.5 h-3.5 overflow-visible"
      data-tool-svg={kind}
      aria-hidden="true"
    >
      {kind === 'read' && (
        <>
          <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
          <path d="M14 3v6h6" />
          <line className="tg-read-line" x1="8.2" y1="11.2" x2="15.6" y2="11.2" />
          <line className="tg-read-line" x1="8.2" y1="14.6" x2="15.6" y2="14.6" />
          <line className="tg-read-line" x1="8.2" y1="18.0" x2="13.0" y2="18.0" />
          <circle
            className="tg-read-dot"
            cx="15.6"
            cy="11.2"
            r="1.35"
            fill="currentColor"
            stroke="none"
          />
        </>
      )}
      {kind === 'write' && (
        <>
          <path d="M11 4H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-6" />
          <line className="tg-write-ink1" x1="7.5" y1="14.5" x2="13.5" y2="14.5" />
          <line className="tg-write-ink2" x1="7.5" y1="17.5" x2="11.5" y2="17.5" opacity="0" />
          <g className="tg-write-pen">
            <path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
          </g>
        </>
      )}
      {kind === 'search' && (
        <g className="tg-search-glass">
          <circle cx="10.5" cy="10.5" r="6.5" />
          <path className="tg-search-glint" d="M8 8.2a3.2 3.2 0 0 1 4.2-.4" strokeWidth={1.8} />
          <line x1="15.2" y1="15.2" x2="20.5" y2="20.5" strokeWidth={2.6} />
        </g>
      )}
      {kind === 'globe' && (
        <>
          <circle cx="12" cy="12" r="9" />
          <line x1="3.4" y1="9" x2="20.6" y2="9" strokeWidth={1.8} />
          <line x1="3.4" y1="15" x2="20.6" y2="15" strokeWidth={1.8} />
          <ellipse className="tg-globe-meridian" cx="12" cy="12" rx="4.2" ry="9" />
          <circle className="tg-globe-sat" cx="20.5" cy="12" r="1.5" fill="currentColor" stroke="none" />
        </>
      )}
      {kind === 'folder' && (
        <>
          <path d="M3 7V17a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-6.5l-2-2H5a2 2 0 0 0-2 2z" />
          <rect className="tg-folder-sheet" x="6.5" y="7.5" width="11" height="6" rx="1" />
          <path
            className="tg-folder-front"
            d="M3 11.5h18l-1.2 6a1.8 1.8 0 0 1-1.8 1.5H6a1.8 1.8 0 0 1-1.8-1.5L3 11.5z"
          />
        </>
      )}
      {kind === 'terminal' && (
        <>
          <rect x="2.5" y="4" width="19" height="16" rx="2.5" />
          <path className="tg-term-chev" d="M6.8 9.5L10.3 12L6.8 14.5" />
          <line className="tg-term-cursor" x1="12.5" y1="14.8" x2="17.2" y2="14.8" strokeWidth={2.6} />
        </>
      )}
      {kind === 'memory' && (
        <>
          <rect x="6" y="6" width="12" height="12" rx="2" />
          <rect className="tg-mem-core" x="9.5" y="9.5" width="5" height="5" rx="0.8" fill="currentColor" />
          <line className="tg-mem-pin" x1="9" y1="2.5" x2="9" y2="6" />
          <line className="tg-mem-pin" x1="15" y1="2.5" x2="15" y2="6" />
          <line className="tg-mem-pin" x1="9" y1="18" x2="9" y2="21.5" />
          <line className="tg-mem-pin" x1="15" y1="18" x2="15" y2="21.5" />
          <line className="tg-mem-pin" x1="2.5" y1="9" x2="6" y2="9" />
          <line className="tg-mem-pin" x1="2.5" y1="15" x2="6" y2="15" />
          <line className="tg-mem-pin" x1="18" y1="9" x2="21.5" y2="9" />
          <line className="tg-mem-pin" x1="18" y1="15" x2="21.5" y2="15" />
        </>
      )}
      {kind === 'tasks' && (
        <>
          <rect x="4" y="3.5" width="16" height="17.5" rx="2" />
          <path
            className="tg-task-check"
            d="M7.2 10.2l1.6 1.6 2.8-3"
            strokeDasharray="10"
            strokeDashoffset="0"
          />
          <line className="tg-task-bar1" x1="11.5" y1="15" x2="16.5" y2="15" />
          <line className="tg-task-bar2" x1="11.5" y1="18" x2="15.5" y2="18" />
        </>
      )}
      {kind === 'bolt' && (
        <>
          <path className="tg-bolt-main" d="M13 2L4.5 13.5h6.5L10 22l9.5-12h-6.5L13 2z" />
          <circle className="tg-bolt-spark" cx="4.5" cy="5.5" r="1.2" fill="currentColor" stroke="none" />
          <circle className="tg-bolt-spark" cx="19.5" cy="18.5" r="1.2" fill="currentColor" stroke="none" />
        </>
      )}
      {kind === 'cursor' && (
        <>
          <circle className="tg-cursor-ring" cx="9" cy="9" r="3" strokeWidth={1.8} opacity="0" />
          <path
            className="tg-cursor-arrow"
            d="M5.5 4.5l13 5.2-5.6 1.9-2.2 5.9-5.2-13z"
            fill="currentColor"
          />
        </>
      )}
      {kind === 'signal' && (
        <>
          <circle cx="6" cy="18" r="2" fill="currentColor" stroke="none" />
          <path className="tg-sig-wave" d="M6 12a6 6 0 0 1 6 6" />
          <path className="tg-sig-wave" d="M6 7a11 11 0 0 1 11 11" />
          <path className="tg-sig-wave" d="M6 2a16 16 0 0 1 16 16" />
        </>
      )}
      {kind === 'pending' && (
        <>
          <circle cx="12" cy="12" r="9" />
          <line className="tg-clock-hour" x1="12" y1="12" x2="12" y2="8.2" strokeWidth={2.5} />
          <line className="tg-clock-min" x1="12" y1="12" x2="12" y2="5.6" strokeWidth={2} />
        </>
      )}
    </svg>
  );
});
AnimatedToolGlyphSvg.displayName = 'AnimatedToolGlyphSvg';

export function ToolGroupIcon({
  toolName,
  approvalState,
  isStreaming = false,
  hasOutput = false,
}: ToolGroupIconProps) {
  const Icon = pickToolIcon(toolName, approvalState);
  const animKind = pickToolAnimationKind(toolName, approvalState, isStreaming, hasOutput);
  const animClass = animKind !== 'none' ? `tool-icon-anim-${animKind}` : '';

  if (animKind !== 'none') {
    const glyphKind = pickToolSvgGlyphKind(toolName, animKind);
    return (
      <span
        className={`tool-group-icon inline-flex items-center justify-center shrink-0 transition-opacity duration-300 ${animClass}`.trim()}
        data-anim={animKind}
        aria-hidden="true"
      >
        <AnimatedToolGlyphSvg kind={glyphKind} />
      </span>
    );
  }

  return (
    <span
      className="tool-group-icon inline-flex items-center justify-center shrink-0 transition-opacity duration-300"
      data-anim="none"
      aria-hidden="true"
    >
      <Icon className="w-3.5 h-3.5 stroke-[2.25]" />
    </span>
  );
}
