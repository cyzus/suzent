/**
 * Full-body physical acts & stage mapping for the Suzent Bot Engine.
 *
 * Maps Suzent's streaming / thinking / tool states into expressive eye pools,
 * full-body squash-and-stretch choreography (`workout`, `eureka_levitate`,
 * `speed_reader`, `dj_groove`, `peek_radar`, `constellation_command`), and
 * periodic 180° 3D-turn geometric morph previews (`dots`, `radar`, `receive`,
 * `pencil`, `wave`, `orbit`, `send`, `gather`, `progress`, `bang`).
 */

import {
  HEAD_C,
  PENCIL_GLYPH,
  PENCIL_RING,
  Point2D,
  SUZENT_BODY_PATH,
  SUZENT_BODY_RING,
  clamp,
  ringOutline,
} from './suzentBotGeometry';
import { normalizeToolName } from '../../components/chat/toolSummary';

export type SuzentBotStageId =
  | 'idle'
  | 'thinking'
  | 'searching'
  | 'reading'
  | 'ingesting'
  | 'writing'
  | 'bash'
  | 'starting'
  | 'subagent'
  | 'vision'
  | 'skill'
  | 'social'
  | 'tasks'
  | 'approval'
  | 'error'
  | 'done';

export type SuzentFullBodyAct =
  | 'none'
  | 'workout'
  | 'eureka_levitate'
  | 'speed_reader'
  | 'chomp_file'
  | 'floating_doc'
  | 'thought_cloud'
  | 'full_gear'
  | 'question_eureka'
  | 'big_loupe'
  | 'bright_beam'
  | 'binoculars'
  | 'laptop_type'
  | 'fountain_pen'
  | 'turbo_sprinter'
  | 'dj_groove'
  | 'peek_radar'
  | 'constellation_command'
  | 'agent_twin_split'
  | 'agent_portal_spawn'
  | 'agent_megaphone_rally'
  | 'agent_antenna_dispatch'
  | 'agent_squad_march';

export type SuzentMorphId =
  | 'none'
  | 'dots'
  | 'orbit'
  | 'radar'
  | 'progress'
  | 'gather'
  | 'wave'
  | 'send'
  | 'receive'
  | 'pencil'
  | 'bang';

export type SuzentGrokBaseState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'searching'
  | 'working'
  | 'suspicious'
  | 'curious'
  | 'playful'
  | 'humming'
  | 'notifying'
  | 'celebrate';

export interface SuzentStageSpec {
  id: SuzentBotStageId;
  baseState: SuzentGrokBaseState;
  act: SuzentFullBodyAct;
  /** Multiple full-body acts that rotate automatically while the bot stays in this stage. */
  acts: readonly SuzentFullBodyAct[];
  cycleMorph: SuzentMorphId;
  expressionPool: readonly number[];
  humming: boolean;
  notifying: boolean;
  celebrating: boolean;
}

export const STAGE_SPECS: Record<SuzentBotStageId, SuzentStageSpec> = {
  idle: {
    id: 'idle',
    baseState: 'idle',
    act: 'none',
    acts: ['none'],
    cycleMorph: 'none',
    expressionPool: [0, 8, 2, 20],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  thinking: {
    id: 'thinking',
    baseState: 'suspicious',
    act: 'thought_cloud',
    acts: ['thought_cloud', 'full_gear', 'eureka_levitate'],
    cycleMorph: 'dots',
    expressionPool: [5, 14, 9, 18, 3],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  searching: {
    id: 'searching',
    baseState: 'searching',
    act: 'big_loupe',
    acts: ['big_loupe', 'peek_radar'],
    cycleMorph: 'radar',
    expressionPool: [6, 9, 18, 12, 22],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  reading: {
    id: 'reading',
    baseState: 'curious',
    act: 'speed_reader',
    acts: ['speed_reader'],
    cycleMorph: 'receive',
    expressionPool: [0, 8, 9, 2, 3],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  ingesting: {
    id: 'ingesting',
    baseState: 'curious',
    act: 'chomp_file',
    acts: ['chomp_file'],
    cycleMorph: 'receive',
    expressionPool: [0, 8, 9, 2, 3],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  writing: {
    id: 'writing',
    baseState: 'working',
    act: 'fountain_pen',
    acts: ['fountain_pen'],
    cycleMorph: 'pencil',
    expressionPool: [7, 10, 24, 6],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  bash: {
    id: 'bash',
    baseState: 'working',
    act: 'laptop_type',
    acts: ['laptop_type', 'dj_groove'],
    cycleMorph: 'wave',
    expressionPool: [10, 16, 7, 24],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  starting: {
    id: 'starting',
    baseState: 'working',
    act: 'workout',
    acts: ['workout'],
    cycleMorph: 'wave',
    expressionPool: [7, 10, 24, 6],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  subagent: {
    id: 'subagent',
    baseState: 'playful',
    act: 'constellation_command',
    acts: ['constellation_command', 'agent_twin_split', 'agent_portal_spawn'],
    cycleMorph: 'orbit',
    expressionPool: [17, 23, 6, 10, 3],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  vision: {
    id: 'vision',
    baseState: 'curious',
    act: 'big_loupe',
    acts: ['big_loupe', 'speed_reader'],
    cycleMorph: 'gather',
    expressionPool: [9, 18, 15, 6, 3],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  skill: {
    id: 'skill',
    baseState: 'playful',
    act: 'full_gear',
    acts: ['full_gear', 'eureka_levitate'],
    cycleMorph: 'orbit',
    expressionPool: [16, 3, 10, 2, 17],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  social: {
    id: 'social',
    baseState: 'playful',
    act: 'none',
    acts: ['none'],
    cycleMorph: 'send',
    expressionPool: [2, 8, 3, 19, 0],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  tasks: {
    id: 'tasks',
    baseState: 'curious',
    act: 'thought_cloud',
    acts: ['thought_cloud', 'eureka_levitate'],
    cycleMorph: 'progress',
    expressionPool: [9, 18, 6, 3, 24],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  approval: {
    id: 'approval',
    baseState: 'notifying',
    act: 'none',
    acts: ['none'],
    cycleMorph: 'bang',
    expressionPool: [21, 3, 1],
    humming: false,
    notifying: true,
    celebrating: false,
  },
  error: {
    id: 'error',
    baseState: 'notifying',
    act: 'none',
    acts: ['none'],
    cycleMorph: 'bang',
    expressionPool: [21, 5, 7],
    humming: false,
    notifying: true,
    celebrating: false,
  },
  done: {
    id: 'done',
    baseState: 'celebrate',
    act: 'none',
    acts: ['none'],
    cycleMorph: 'none',
    expressionPool: [2, 3, 19, 11],
    humming: false,
    notifying: false,
    celebrating: true,
  },
};

export function resolveSuzentStage(options: {
  isThinking?: boolean;
  hasPending?: boolean;
  isError?: boolean;
  toolName?: string;
  isActive?: boolean;
}): SuzentBotStageId {
  if (options.hasPending) return 'approval';
  if (options.isError) return 'error';
  if (options.isThinking) return 'thinking';
  if (!options.toolName) return options.isActive ? 'thinking' : 'idle';

  const canonical = normalizeToolName(options.toolName);
  switch (canonical) {
    case 'read_file':
    case 'agent_read':
      return 'reading';
    case 'webpage_fetch':
      return 'ingesting';
    case 'write_file':
    case 'edit_file':
      return 'writing';
    case 'glob_search':
    case 'grep_search':
    case 'web_search':
    case 'search_tools':
      return 'searching';
    case 'memory_search':
    case 'session_search':
      return 'ingesting';
    case 'run_command':
    case 'check_command':
      return 'bash';
    case 'start_command':
    case 'stop_command':
      return 'starting';
    case 'agent':
    case 'agent_send':
    case 'agent_list':
    case 'agent_stop':
      return 'subagent';
    case 'analyze_visual':
    case 'analyze_image':
    case 'render_ui':
    case 'browser_action':
    case 'generate_image':
    case 'edit_image':
    case 'generate_video':
      return 'vision';
    case 'skill_execute':
    case 'run_code':
      return 'skill';
    case 'send_file':
    case 'social_message':
    case 'speak':
    case 'ask_question':
      return 'social';
    case 'create_tasks':
    case 'update_task':
    case 'list_tasks':
    case 'manage_goal':
    case 'schedule_cron':
      return 'tasks';
    default:
      if (
        canonical.includes('search') ||
        canonical.includes('grep') ||
        canonical.includes('glob')
      ) {
        return 'searching';
      }
      if (canonical.includes('read') || canonical.includes('fetch')) return 'reading';
      if (canonical.includes('write') || canonical.includes('edit')) return 'writing';
      if (canonical.includes('agent')) return 'subagent';
      return 'bash';
  }
}

export interface FullBodyActPose {
  x: number;
  y: number;
  rot: number;
  sx: number;
  sy: number;
  gazeX: number;
  gazeY: number;
  backHtml: string;
  frontHtml: string;
  targetRing?: readonly Point2D[];
  ringBlend?: number;
  hideEyes?: boolean;
}

/**
 * 96-point 8-tooth precision mechanical gear contour (centered at HEAD_C = 114.2705)
 * for spline-morphing the Suzent body directly into a rotating cog in `full_gear` (T2).
 */
export const GEAR_COG_RING: Point2D[] = Array.from({ length: 96 }, (_, i) => {
  const theta = (i / 96) * Math.PI * 2;
  const toothWave = Math.cos(8 * theta);
  const toothEnv = clamp((toothWave - 0.15) / 0.55, 0, 1);
  const smoothTooth = toothEnv * toothEnv * (3 - 2 * toothEnv);
  const r = 82 + 30 * smoothTooth;
  return [HEAD_C + r * Math.cos(theta), HEAD_C + r * Math.sin(theta)];
});

const PENCIL_NIB_PATH: string = ringOutline(PENCIL_RING);

/**
 * Compute a 96-point organic cell-division (peanut / figure-8) contour as `pinch` goes 0 -> 1.
 */
export function buildMitosisPinchRing(
  baseRing: readonly Point2D[],
  pinch: number,
  stretchX: number
): Point2D[] {
  return baseRing.map(([x, y]) => {
    const dx = x - HEAD_C;
    const dy = y - HEAD_C;
    const nx = dx / 114.22;
    // Gaussian waist pinch at the center vertical axis (nx ≈ 0) + lobe widening at sides
    const waist = Math.exp(-(nx * nx) / 0.14);
    const lobeBulge = 1 + 0.16 * pinch * (1 - waist);
    const sy = Math.max(0.14, 1 - 0.82 * pinch * waist) * lobeBulge;
    const sx = stretchX + 0.18 * pinch * Math.sign(dx) * Math.abs(nx);
    return [HEAD_C + dx * sx, HEAD_C + dy * sy];
  });
}

/**
 * Evaluate the current full-body physical act pose and foreground/background SVG layers.
 */
export function evaluateFullBodyAct(
  act: SuzentFullBodyAct,
  elapsedSec: number,
  morphAmount: number,
  headPose: { x: number; y: number; rot: number }
): FullBodyActPose {
  const fade = Math.max(0, 1 - morphAmount * 1.5);
  const pose: FullBodyActPose = {
    x: 0,
    y: 0,
    rot: 0,
    sx: 1,
    sy: 1,
    gazeX: 0,
    gazeY: 0,
    backHtml: '',
    frontHtml: '',
  };

  if (act === 'none' || fade <= 0.02) return pose;
  const t = Math.max(0, elapsedSec);

  if (act === 'workout') {
    // Deep squat + explosive overhead barbell press with bending steel bar
    const cyc = (t / 1.65) % 1;
    let squat = 0;
    let press = 0;
    if (cyc < 0.36) {
      const p = Math.sin((cyc / 0.36) * Math.PI);
      squat = p;
      press = -0.12 * p;
    } else if (cyc < 0.78) {
      const p = (cyc - 0.36) / 0.42;
      const lock = 1 - (1 - Math.min(1, p * 1.4)) ** 3;
      press = lock;
      squat = -0.55 * Math.sin(p * Math.PI);
    } else {
      const p = (cyc - 0.78) / 0.22;
      press = 1 - p * p * (3 - 2 * p);
      squat = 0.2 * Math.sin(p * Math.PI);
    }
    pose.y = squat * 22;
    pose.sx = 1 + squat * 0.14;
    pose.sy = 1 - squat * 0.16;

    const barY = HEAD_C - 96 - press * 44 + pose.y * 0.85;
    const armBottomY = HEAD_C - 20 + pose.y;
    const bend =
      press > 0.5
        ? Math.sin((cyc - 0.36) * 28) * 4.5 * Math.exp(-(cyc - 0.36) * 4) + 5
        : -3 * squat;

    pose.backHtml = `
      <g opacity="${fade.toFixed(2)}">
        <line x1="22" y1="${armBottomY.toFixed(1)}" x2="10" y2="${barY.toFixed(1)}" stroke="var(--fg)" stroke-width="14" stroke-linecap="round" />
        <line x1="206" y1="${armBottomY.toFixed(1)}" x2="218" y2="${barY.toFixed(1)}" stroke="var(--fg)" stroke-width="14" stroke-linecap="round" />
      </g>
    `;
    pose.frontHtml = `
      <g opacity="${fade.toFixed(2)}">
        <path d="M-38 ${barY.toFixed(1)} Q${HEAD_C} ${(barY - bend * 2.2).toFixed(1)} 266 ${barY.toFixed(1)}" fill="none" stroke="var(--fg)" stroke-width="12" stroke-linecap="round" />
        <rect x="-24" y="${(barY - 26).toFixed(1)}" width="14" height="52" rx="4" fill="var(--fg)" />
        <rect x="-44" y="${(barY - 38).toFixed(1)}" width="16" height="76" rx="5" fill="var(--fg)" />
        <rect x="238" y="${(barY - 26).toFixed(1)}" width="14" height="52" rx="4" fill="var(--fg)" />
        <rect x="256" y="${(barY - 38).toFixed(1)}" width="16" height="76" rx="5" fill="var(--fg)" />
      </g>
    `;
    return pose;
  }

  if (act === 'eureka_levitate') {
    // Zero-G levitation + breathing ground shadow + 360° Eureka mid-air somersault
    const cyc = (t / 2.8) % 1;
    let liftY = 0;
    let flipRot = 0;
    let sx = 1;
    let sy = 1;
    let ringExpand = 0;

    if (cyc < 0.55) {
      const p = cyc / 0.55;
      liftY = -24 * Math.sin(p * Math.PI);
      flipRot = -12 * Math.sin(p * Math.PI * 2);
      sx = 1 - 0.04 * Math.sin(p * Math.PI);
      sy = 1 + 0.05 * Math.sin(p * Math.PI);
    } else if (cyc < 0.68) {
      const p = (cyc - 0.55) / 0.13;
      const s = Math.sin(p * Math.PI);
      liftY = 18 * s;
      sx = 1 + 0.16 * s;
      sy = 1 - 0.18 * s;
    } else if (cyc < 0.92) {
      const p = (cyc - 0.68) / 0.24;
      const ease = p < 0.5 ? 2 * p * p : 1 - (-2 * p + 2) ** 2 / 2;
      liftY = -36 * Math.sin(p * Math.PI);
      flipRot = ease * 360;
      ringExpand = p;
    } else {
      const p = (cyc - 0.92) / 0.08;
      const s = Math.sin(p * Math.PI);
      liftY = 8 * s;
      sx = 1 + 0.08 * s;
      sy = 1 - 0.08 * s;
    }

    pose.y = liftY;
    pose.rot = flipRot;
    pose.sx = sx;
    pose.sy = sy;

    const shadowScale = clamp(1 + liftY / 75, 0.45, 1.25);
    const shadowOp = 0.18 * shadowScale * fade;
    let ringSvg = '';
    if (ringExpand > 0) {
      const r = 90 + ringExpand * 65;
      const rOp = (1 - ringExpand) * 0.75 * fade;
      ringSvg = `<circle cx="${HEAD_C}" cy="${(HEAD_C + liftY).toFixed(1)}" r="${r.toFixed(1)}" fill="none" stroke="var(--fg)" stroke-width="${(8 * (1 - 0.5 * ringExpand)).toFixed(1)}" opacity="${rOp.toFixed(2)}" />`;
    }
    pose.backHtml = `
      <ellipse cx="${HEAD_C}" cy="248" rx="${(82 * shadowScale).toFixed(1)}" ry="${(11 * shadowScale).toFixed(1)}" fill="var(--fg)" opacity="${shadowOp.toFixed(2)}" />
      ${ringSvg}
    `;
    return pose;
  }

  if (act === 'speed_reader') {
    // R1: HOLDING OPEN BOOK & PAGE FLIPPING (捧书翻页阅读)
    const cyc = (t / 1.4) % 1;
    let scanX = 0;
    let nodY = 0;
    let pageFlip = -1;
    if (cyc < 0.72) {
      const p = cyc / 0.72;
      scanX = -16 + p * 32;
      nodY = 3.5 * Math.abs(Math.sin(p * Math.PI * 2));
    } else {
      const p = (cyc - 0.72) / 0.28;
      pageFlip = p;
      scanX = 16 * (1 - p) - 16 * p;
      nodY = -10 * Math.sin(p * Math.PI);
    }

    pose.x = scanX * 0.42;
    pose.y = nodY - 10;
    pose.rot = scanX * 0.25;
    pose.gazeX = scanX * 1.05;
    pose.gazeY = 18;

    const bx = HEAD_C + pose.x * 0.6;
    const by = 224;
    let flipSvg = '';
    if (pageFlip >= 0) {
      const ang = pageFlip * Math.PI;
      const fx = bx + Math.cos(ang) * 68;
      const fy = by - 26 - Math.sin(ang) * 32;
      flipSvg = `<path d="M ${bx.toFixed(1)} ${(by + 10).toFixed(1)} L ${fx.toFixed(1)} ${fy.toFixed(1)} L ${fx.toFixed(1)} ${(fy - 34).toFixed(1)} L ${bx.toFixed(1)} ${(by - 24).toFixed(1)} Z" fill="var(--bg)" stroke="var(--fg)" stroke-width="8" stroke-linejoin="round" />`;
    }

    pose.frontHtml = `
      <g opacity="${fade.toFixed(2)}">
        <path d="M ${(bx - 76).toFixed(1)} ${(by - 30).toFixed(1)} L ${bx.toFixed(1)} ${(by - 14).toFixed(1)} L ${(bx + 76).toFixed(1)} ${(by - 30).toFixed(1)} L ${(bx + 76).toFixed(1)} ${(by + 16).toFixed(1)} L ${bx.toFixed(1)} ${(by + 30).toFixed(1)} L ${(bx - 76).toFixed(1)} ${(by + 16).toFixed(1)} Z" fill="var(--bg)" stroke="var(--fg)" stroke-width="11" stroke-linejoin="round" />
        <line x1="${bx.toFixed(1)}" y1="${(by - 14).toFixed(1)}" x2="${bx.toFixed(1)}" y2="${(by + 30).toFixed(1)}" stroke="var(--fg)" stroke-width="9" stroke-linecap="round" />
        <line x1="${(bx - 56).toFixed(1)}" y1="${(by - 10).toFixed(1)}" x2="${(bx - 18).toFixed(1)}" y2="${(by - 2).toFixed(1)}" stroke="var(--fg)" stroke-width="6.5" stroke-linecap="round" />
        <line x1="${(bx - 56).toFixed(1)}" y1="${(by + 5).toFixed(1)}" x2="${(bx - 22).toFixed(1)}" y2="${(by + 12).toFixed(1)}" stroke="var(--fg)" stroke-width="6.5" stroke-linecap="round" />
        <line x1="${(bx + 18).toFixed(1)}" y1="${(by - 2).toFixed(1)}" x2="${(bx + 56).toFixed(1)}" y2="${(by - 10).toFixed(1)}" stroke="var(--fg)" stroke-width="6.5" stroke-linecap="round" />
        <line x1="${(bx + 22).toFixed(1)}" y1="${(by + 12).toFixed(1)}" x2="${(bx + 56).toFixed(1)}" y2="${(by + 5).toFixed(1)}" stroke="var(--fg)" stroke-width="6.5" stroke-linecap="round" />
        ${flipSvg}
      </g>
    `;
    return pose;
  }

  if (act === 'chomp_file') {
    // R3 (No-Clipping!): Bite-by-bite file chomp on the right side with scalloped bite marks & flying paper crumbs
    const cyc = (t / 1.8) % 1;
    const biteIdx = cyc < 0.3 ? 0 : cyc < 0.6 ? 1 : cyc < 0.85 ? 2 : 3;
    const localP =
      biteIdx === 0
        ? cyc / 0.3
        : biteIdx === 1
          ? (cyc - 0.3) / 0.3
          : biteIdx === 2
            ? (cyc - 0.6) / 0.25
            : (cyc - 0.85) / 0.15;

    const lunge = biteIdx < 3 ? Math.sin(localP * Math.PI) : 0;
    const chew = biteIdx === 3 ? Math.sin(localP * Math.PI * 2) : 0;

    pose.x = -18 + lunge * 28;
    pose.y = -lunge * 10 + chew * 8;
    pose.sx = 1 + lunge * 0.14 + chew * 0.12;
    pose.sy = 1 - lunge * 0.12 - chew * 0.12;
    pose.rot = lunge * 11 - chew * 5;
    pose.gazeX = 20;
    pose.gazeY = biteIdx === 0 ? -8 : biteIdx === 1 ? 4 : 14;

    const dx = HEAD_C + 104;
    const dy = HEAD_C + 6;
    let docSvg = '';

    if (biteIdx < 3) {
      const topY = biteIdx === 0 ? dy - 56 : biteIdx === 1 ? dy - 16 : dy + 20;
      const hasDogEar = biteIdx === 0;
      const docPath = hasDogEar
        ? `M ${dx - 34} ${topY} L ${dx + 12} ${topY} L ${dx + 34} ${topY + 22} L ${dx + 34} ${dy + 56} L ${dx - 34} ${dy + 56} Z`
        : `M ${dx - 34} ${topY} Q ${dx - 17} ${topY + 12} ${dx} ${topY} Q ${dx + 17} ${topY + 12} ${dx + 34} ${topY} L ${dx + 34} ${dy + 56} L ${dx - 34} ${dy + 56} Z`;

      docSvg += `
        <path d="${docPath}" fill="var(--bg)" stroke="var(--fg)" stroke-width="10" stroke-linejoin="round" />
        ${hasDogEar ? `<path d="M ${dx + 12} ${topY} L ${dx + 12} ${topY + 22} L ${dx + 34} ${topY + 22}" fill="none" stroke="var(--fg)" stroke-width="8" stroke-linejoin="round" />` : ''}
        ${biteIdx <= 0 ? `<line x1="${dx - 18}" y1="${dy - 24}" x2="${dx + 16}" y2="${dy - 24}" stroke="var(--fg)" stroke-width="7" stroke-linecap="round" />` : ''}
        ${biteIdx <= 1 ? `<line x1="${dx - 18}" y1="${dy + 4}" x2="${dx + 18}" y2="${dy + 4}" stroke="var(--fg)" stroke-width="7" stroke-linecap="round" />` : ''}
        <line x1="${dx - 18}" y1="${dy + 32}" x2="${dx + 10}" y2="${dy + 32}" stroke="var(--fg)" stroke-width="7" stroke-linecap="round" />
      `;

      if (localP > 0.35 && localP < 0.85) {
        const cp = (localP - 0.35) / 0.5;
        const cOp = (1 - cp) * fade;
        docSvg += `
          <circle cx="${(dx - 36 - cp * 24).toFixed(1)}" cy="${(topY - cp * 26).toFixed(1)}" r="6" fill="var(--fg)" opacity="${cOp.toFixed(2)}" />
          <circle cx="${(dx - 20 - cp * 18).toFixed(1)}" cy="${(topY + 14 + cp * 22).toFixed(1)}" r="5" fill="var(--fg)" opacity="${cOp.toFixed(2)}" />
        `;
      }
    }

    pose.frontHtml = `<g opacity="${fade.toFixed(2)}">${docSvg}</g>`;
    return pose;
  }

  if (act === 'floating_doc') {
    // R2: Floating dog-eared file card on the right + sightline scan
    const cyc = (t / 1.5) % 1;
    const scanY = cyc < 0.78 ? -16 + (cyc / 0.78) * 32 : 16 - ((cyc - 0.78) / 0.22) * 32;
    const hop = cyc >= 0.78 ? Math.sin(((cyc - 0.78) / 0.22) * Math.PI) : 0;

    pose.x = -24 + Math.sin(t * 4) * 3;
    pose.y = scanY * 0.45 - hop * 12;
    pose.rot = 6 + scanY * 0.2;
    pose.gazeX = 22;
    pose.gazeY = scanY * 0.9;

    const dx = HEAD_C + 102;
    const dy = HEAD_C + Math.sin(t * 3.2) * 6;
    const lineHighlightY = dy - 18 + ((scanY + 16) / 32) * 44;

    pose.frontHtml = `
      <g opacity="${fade.toFixed(2)}">
        <path d="M ${dx - 38} ${dy - 58} L ${dx + 14} ${dy - 58} L ${dx + 38} ${dy - 34} L ${dx + 38} ${dy + 58} L ${dx - 38} ${dy + 58} Z" fill="var(--bg)" stroke="var(--fg)" stroke-width="11" stroke-linejoin="round" />
        <path d="M ${dx + 14} ${dy - 58} L ${dx + 14} ${dy - 34} L ${dx + 38} ${dy - 34}" fill="none" stroke="var(--fg)" stroke-width="9" stroke-linejoin="round" />
        <line x1="${dx - 20}" y1="${dy - 14}" x2="${dx + 20}" y2="${dy - 14}" stroke="var(--fg)" stroke-width="7.5" stroke-linecap="round" />
        <line x1="${dx - 20}" y1="${dy + 8}" x2="${dx + 20}" y2="${dy + 8}" stroke="var(--fg)" stroke-width="7.5" stroke-linecap="round" />
        <line x1="${dx - 14}" y1="${dy + 30}" x2="${dx + 8}" y2="${dy + 30}" stroke="var(--fg)" stroke-width="7.5" stroke-linecap="round" />
        <line x1="${(HEAD_C + pose.x + 68).toFixed(1)}" y1="${(HEAD_C + pose.y + pose.gazeY).toFixed(1)}" x2="${dx - 28}" y2="${lineHighlightY.toFixed(1)}" stroke="var(--fg)" stroke-width="6" stroke-dasharray="8 8" stroke-linecap="round" opacity="0.65" />
      </g>
    `;
    return pose;
  }

  if (act === 'thought_cloud') {
    // T1: Upper-right thought cloud with "..." pulsing dots that flash into "!" idea rays
    const cyc = (t / 2.4) % 1;
    const ponder = Math.sin(cyc * Math.PI * 2);
    const ideaFlash = cyc > 0.58 && cyc < 0.88 ? Math.sin(((cyc - 0.58) / 0.3) * Math.PI) : 0;

    pose.x = -18 + ponder * 5;
    pose.y = 18 - ideaFlash * 16;
    pose.rot = -6 + ponder * 6;
    pose.sx = 1 - ideaFlash * 0.06;
    pose.sy = 1 + ideaFlash * 0.08;
    pose.gazeX = 18;
    pose.gazeY = -16;

    const cx = HEAD_C + 92;
    const cy = 6 - ideaFlash * 6;

    pose.frontHtml = `
      <g opacity="${fade.toFixed(2)}">
        <circle cx="${(HEAD_C + 42).toFixed(1)}" cy="46" r="6.5" fill="var(--bg)" stroke="var(--fg)" stroke-width="6.5" />
        <circle cx="${(HEAD_C + 58).toFixed(1)}" cy="28" r="9.5" fill="var(--bg)" stroke="var(--fg)" stroke-width="7" />
        <rect x="${(cx - 38).toFixed(1)}" y="${(cy - 22).toFixed(1)}" width="76" height="44" rx="22" fill="var(--bg)" stroke="var(--fg)" stroke-width="10" />
        ${
          ideaFlash > 0.25
            ? `
          <line x1="${cx.toFixed(1)}" y1="${(cy - 12).toFixed(1)}" x2="${cx.toFixed(1)}" y2="${(cy + 1).toFixed(1)}" stroke="var(--fg)" stroke-width="9" stroke-linecap="round" />
          <circle cx="${cx.toFixed(1)}" cy="${(cy + 11).toFixed(1)}" r="4.5" fill="var(--fg)" />
          <line x1="${cx}" y1="${cy - 32}" x2="${cx}" y2="${cy - 46}" stroke="var(--fg)" stroke-width="7.5" stroke-linecap="round" />
          <line x1="${cx + 46}" y1="${cy - 16}" x2="${cx + 60}" y2="${cy - 24}" stroke="var(--fg)" stroke-width="7.5" stroke-linecap="round" />
        `
            : `
          <circle cx="${(cx - 16).toFixed(1)}" cy="${cy.toFixed(1)}" r="5.5" fill="var(--fg)" opacity="${(0.35 + 0.65 * Math.abs(Math.sin(t * 5))).toFixed(2)}" />
          <circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="5.5" fill="var(--fg)" opacity="${(0.35 + 0.65 * Math.abs(Math.sin(t * 5 - 1))).toFixed(2)}" />
          <circle cx="${(cx + 16).toFixed(1)}" cy="${cy.toFixed(1)}" r="5.5" fill="var(--fg)" opacity="${(0.35 + 0.65 * Math.abs(Math.sin(t * 5 - 2))).toFixed(2)}" />
        `
        }
      </g>
    `;
    return pose;
  }

  if (act === 'full_gear') {
    // T2: TRUE SPLINE MORPH INTO AN 8-TOOTH MECHANICAL GEAR COG!
    // The 96-point Suzent square body smoothly spline-morphs into GEAR_COG_RING,
    // ticks in 45° escapement steps with a central axle bore, and meshes with a companion gear!
    const cyc = (t / 3.4) % 1;
    // Smoothly morph into a pure gear (0 -> 0.14), spin as a gear (0.14 -> 0.84), morph back (0.84 -> 1.0)
    const gearBlend =
      cyc < 0.14 ? clamp(cyc / 0.14, 0, 1) : cyc < 0.84 ? 1 : clamp((1 - cyc) / 0.16, 0, 1);
    const smoothBlend = gearBlend * gearBlend * (3 - 2 * gearBlend);
    const stepTick = Math.floor(t * 2.5) * 45 + ((t * 2.5) % 1) ** 3 * 45;
    const pulse = Math.sin(t * 5);

    pose.x = -12 * smoothBlend;
    pose.y = 6 * smoothBlend;
    pose.rot = stepTick * smoothBlend;
    pose.sx = 1 - 0.12 * smoothBlend + 0.025 * pulse * smoothBlend;
    pose.sy = 1 - 0.12 * smoothBlend - 0.025 * pulse * smoothBlend;
    pose.targetRing = GEAR_COG_RING;
    pose.ringBlend = smoothBlend;
    pose.hideEyes = smoothBlend > 0.45;

    const gx = HEAD_C + headPose.x * (1 - smoothBlend) + pose.x;
    const gy = HEAD_C + headPose.y * (1 - smoothBlend) + pose.y;
    const subAng = -stepTick * 1.6 + 22.5;
    const subOp = fade * smoothBlend;

    // Companion meshing gear at upper-right
    pose.backHtml = `
      <g opacity="${subOp.toFixed(2)}">
        <g transform="translate(${(gx + 114).toFixed(1)} ${(gy - 86).toFixed(1)}) rotate(${subAng.toFixed(1)})">
          <circle cx="0" cy="0" r="30" fill="var(--fg)" />
          <rect x="-9" y="-42" width="18" height="84" rx="4" fill="var(--fg)" />
          <rect x="-42" y="-9" width="84" height="18" rx="4" fill="var(--fg)" />
          <rect x="-9" y="-42" width="18" height="84" rx="4" fill="var(--fg)" transform="rotate(45)" />
          <rect x="-42" y="-9" width="84" height="18" rx="4" fill="var(--fg)" transform="rotate(45)" />
          <circle cx="0" cy="0" r="13" fill="var(--bg)" />
        </g>
      </g>
    `;
    // Central mechanical axle cutout & inner rim on the morphed gear body
    pose.frontHtml =
      smoothBlend > 0.35
        ? `
      <g opacity="${(((smoothBlend - 0.35) / 0.65) * fade).toFixed(2)}">
        <circle cx="${gx.toFixed(1)}" cy="${gy.toFixed(1)}" r="${(30 * smoothBlend).toFixed(1)}" fill="var(--bg)" />
        <circle cx="${gx.toFixed(1)}" cy="${gy.toFixed(1)}" r="${(12 * smoothBlend).toFixed(1)}" fill="var(--fg)" />
      </g>
    `
        : '';
    return pose;
  }

  if (act === 'question_eureka') {
    // T3: "?" puzzled wobble -> 360° "!" Eureka flip
    const cyc = (t / 2.6) % 1;
    if (cyc < 0.62) {
      const p = cyc / 0.62;
      const wobble = Math.sin(p * Math.PI * 2);
      pose.x = -12 + wobble * 8;
      pose.y = 14;
      pose.rot = wobble * 12;
      pose.gazeX = 14;
      pose.gazeY = -16;
      const qx = HEAD_C + 82 + wobble * 8;
      const qy = 16 + Math.abs(wobble) * 6;
      pose.frontHtml = `
        <g transform="translate(${qx.toFixed(1)} ${qy.toFixed(1)}) rotate(${(wobble * 14).toFixed(1)})" opacity="${fade.toFixed(2)}">
          <path d="M -16 -22 A 18 16 0 1 1 8 -4 Q 0 2 0 12" fill="none" stroke="var(--fg)" stroke-width="13" stroke-linecap="round" />
          <circle cx="0" cy="28" r="7" fill="var(--fg)" />
        </g>
      `;
    } else {
      const p = (cyc - 0.62) / 0.38;
      const jump = Math.sin(p * Math.PI);
      const ease = p < 0.5 ? 2 * p * p : 1 - (-2 * p + 2) ** 2 / 2;
      pose.y = -20 * jump;
      pose.rot = ease * 360;
      pose.sx = 1 - 0.08 * jump;
      pose.sy = 1 + 0.1 * jump;
      pose.frontHtml = `
        <g transform="translate(${HEAD_C + 86} ${(8 - jump * 12).toFixed(1)}) scale(${(0.9 + 0.25 * jump).toFixed(2)})" opacity="${fade.toFixed(2)}">
          <line x1="0" y1="-32" x2="0" y2="6" stroke="var(--fg)" stroke-width="15" stroke-linecap="round" />
          <circle cx="0" cy="24" r="8" fill="var(--fg)" />
          <line x1="-24" y1="-16" x2="-38" y2="-28" stroke="var(--fg)" stroke-width="8" stroke-linecap="round" />
          <line x1="24" y1="-16" x2="38" y2="-28" stroke="var(--fg)" stroke-width="8" stroke-linecap="round" />
        </g>
      `;
    }
    return pose;
  }

  if (act === 'big_loupe') {
    // S1: Sherlock large magnifying glass sweeping across the foreground
    const sweep = Math.sin(t * 2.8);
    pose.x = -sweep * 10;
    pose.y = Math.abs(sweep) * 5;
    pose.rot = sweep * 7;
    pose.gazeX = sweep * 22;
    pose.gazeY = 4;

    const lx = HEAD_C + sweep * 52;
    const ly = HEAD_C + 4 + Math.cos(t * 5.6) * 10;
    const handleX = lx + (sweep >= 0 ? 58 : -58);
    const handleY = ly + 58;

    pose.frontHtml = `
      <g opacity="${fade.toFixed(2)}">
        <line x1="${(lx + (sweep >= 0 ? 32 : -32)).toFixed(1)}" y1="${(ly + 32).toFixed(1)}" x2="${handleX.toFixed(1)}" y2="${handleY.toFixed(1)}" stroke="var(--bg)" stroke-width="24" stroke-linecap="round" />
        <line x1="${(lx + (sweep >= 0 ? 32 : -32)).toFixed(1)}" y1="${(ly + 32).toFixed(1)}" x2="${handleX.toFixed(1)}" y2="${handleY.toFixed(1)}" stroke="var(--fg)" stroke-width="16" stroke-linecap="round" />
        <circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="48" fill="none" stroke="var(--bg)" stroke-width="18" />
        <circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="48" fill="none" stroke="var(--fg)" stroke-width="12" />
        <path d="M ${(lx - 26).toFixed(1)} ${(ly - 20).toFixed(1)} A 32 32 0 0 1 ${(lx + 14).toFixed(1)} ${(ly - 30).toFixed(1)}" fill="none" stroke="var(--bg)" stroke-width="7" stroke-linecap="round" />
      </g>
    `;
    return pose;
  }

  if (act === 'bright_beam') {
    // S3 (Fixed!): Outward bright searchlight beam projecting to the right with an illuminated spotlight ellipse
    const sweep = Math.sin(t * 3.0);
    pose.x = -18;
    pose.y = sweep * 8;
    pose.rot = sweep * 10;
    pose.gazeX = 22;
    pose.gazeY = sweep * 16;

    const ox = HEAD_C + pose.x + 88;
    const oy = HEAD_C + pose.y + sweep * 16;
    const targetX = HEAD_C + 148;
    const targetY = HEAD_C + sweep * 62;

    pose.frontHtml = `
      <g opacity="${fade.toFixed(2)}">
        <rect x="${(ox - 12).toFixed(1)}" y="${(oy - 18).toFixed(1)}" width="20" height="36" rx="6" fill="var(--bg)" stroke="var(--fg)" stroke-width="8" />
        <polygon points="${(ox + 8).toFixed(1)},${(oy - 10).toFixed(1)} ${targetX.toFixed(1)},${(targetY - 38).toFixed(1)} ${targetX.toFixed(1)},${(targetY + 38).toFixed(1)} ${(ox + 8).toFixed(1)},${(oy + 10).toFixed(1)}" fill="var(--fg)" opacity="0.16" />
        <line x1="${(ox + 10).toFixed(1)}" y1="${(oy - 12).toFixed(1)}" x2="${targetX.toFixed(1)}" y2="${(targetY - 38).toFixed(1)}" stroke="var(--fg)" stroke-width="7.5" stroke-dasharray="12 8" stroke-linecap="round" />
        <line x1="${(ox + 10).toFixed(1)}" y1="${(oy + 12).toFixed(1)}" x2="${targetX.toFixed(1)}" y2="${(targetY + 38).toFixed(1)}" stroke="var(--fg)" stroke-width="7.5" stroke-dasharray="12 8" stroke-linecap="round" />
        <ellipse cx="${targetX.toFixed(1)}" cy="${targetY.toFixed(1)}" rx="14" ry="38" fill="var(--bg)" stroke="var(--fg)" stroke-width="8" />
        <circle cx="${targetX.toFixed(1)}" cy="${targetY.toFixed(1)}" r="7" fill="var(--fg)" />
      </g>
    `;
    return pose;
  }

  if (act === 'binoculars') {
    // S2: Dual scout binoculars panning left & right
    const cyc = (t / 2.2) % 1;
    let pan = 0;
    let zoom = 1;
    if (cyc < 0.42) {
      pan = -Math.sin((cyc / 0.42) * Math.PI);
      zoom = 1 + 0.14 * Math.abs(pan);
    } else if (cyc < 0.84) {
      pan = Math.sin(((cyc - 0.42) / 0.42) * Math.PI);
      zoom = 1 + 0.14 * Math.abs(pan);
    }
    pose.x = pan * 16;
    pose.y = -6 * Math.abs(pan);
    pose.rot = pan * 9;
    pose.gazeX = pan * 18;
    const bx = HEAD_C + headPose.x + pose.x + pan * 12;
    const by = HEAD_C + headPose.y + pose.y - 10;
    pose.frontHtml = `
      <g transform="translate(${bx.toFixed(1)} ${by.toFixed(1)}) rotate(${pose.rot.toFixed(1)}) scale(${zoom.toFixed(2)})" opacity="${fade.toFixed(2)}">
        <rect x="-18" y="-12" width="36" height="16" rx="4" fill="var(--fg)" stroke="var(--bg)" stroke-width="5" />
        <circle cx="-46" cy="0" r="38" fill="var(--fg)" stroke="var(--bg)" stroke-width="9" />
        <circle cx="-46" cy="0" r="22" fill="var(--bg)" />
        <circle cx="-52" cy="-6" r="7" fill="var(--fg)" />
        <circle cx="46" cy="0" r="38" fill="var(--fg)" stroke="var(--bg)" stroke-width="9" />
        <circle cx="46" cy="0" r="22" fill="var(--bg)" />
        <circle cx="40" cy="-6" r="7" fill="var(--fg)" />
      </g>
    `;
    return pose;
  }

  if (act === 'laptop_type') {
    // E1: Furious laptop coding with >_ terminal emblem
    const tap = Math.sin(t * 26);
    const bounce = Math.abs(Math.sin(t * 13));
    pose.x = tap * 5;
    pose.y = -4 - bounce * 8;
    pose.rot = tap * 5;
    pose.sx = 1 + (1 - bounce) * 0.08;
    pose.sy = 1 - (1 - bounce) * 0.08;
    pose.gazeX = tap * 8;
    pose.gazeY = 16;
    const lx = HEAD_C;
    const ly = 224;
    pose.frontHtml = `
      <g opacity="${fade.toFixed(2)}">
        <circle cx="${(lx - 58).toFixed(1)}" cy="${(ly - 8 + tap * 10).toFixed(1)}" r="15" fill="var(--fg)" stroke="var(--bg)" stroke-width="5" />
        <circle cx="${(lx + 58).toFixed(1)}" cy="${(ly - 8 - tap * 10).toFixed(1)}" r="15" fill="var(--fg)" stroke="var(--bg)" stroke-width="5" />
        <rect x="${lx - 48}" y="${ly - 42}" width="96" height="58" rx="8" fill="var(--fg)" stroke="var(--bg)" stroke-width="6" />
        <path d="M ${lx - 20} ${ly - 22} L ${lx - 6} ${ly - 13} L ${lx - 20} ${ly - 4}" fill="none" stroke="var(--bg)" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" />
        <line x1="${lx + 2}" y1="${ly - 4}" x2="${lx + 20}" y2="${ly - 4}" stroke="var(--bg)" stroke-width="7" stroke-linecap="round" opacity="${Math.sin(t * 12) > 0 ? 1 : 0.2}" />
        <line x1="${lx - 68}" y1="${ly + 18}" x2="${lx + 68}" y2="${ly + 18}" stroke="var(--fg)" stroke-width="12" stroke-linecap="round" />
      </g>
    `;
    return pose;
  }

  if (act === 'turbo_sprinter') {
    // E2: Full-throttle sprinter with pumping feet & trailing speed lines
    const stride = Math.sin(t * 22);
    const strideCos = Math.cos(t * 22);
    pose.x = 12 + Math.cos(t * 11) * 5;
    pose.y = -Math.abs(stride) * 16;
    pose.rot = 16 + stride * 4;
    pose.sx = 1 + (1 - Math.abs(stride)) * 0.11;
    pose.sy = 1 - (1 - Math.abs(stride)) * 0.09;
    pose.gazeX = 18;
    pose.gazeY = 2;

    let windSvg = '';
    for (let i = 0; i < 3; i++) {
      const wp = (t * 2.8 + i / 3) % 1;
      const wx = 8 - wp * 56;
      const wy = 52 + i * 58;
      const op = Math.sin(wp * Math.PI) * 0.85 * fade;
      windSvg += `<line x1="${wx.toFixed(1)}" y1="${wy}" x2="${(wx - 38).toFixed(1)}" y2="${wy}" stroke="var(--fg)" stroke-width="8.5" stroke-linecap="round" opacity="${op.toFixed(2)}" />`;
    }
    const foot1X = HEAD_C + pose.x + stride * 42;
    const foot1Y = 236 - Math.max(0, strideCos) * 22;
    const foot2X = HEAD_C + pose.x - stride * 42;
    const foot2Y = 236 - Math.max(0, -strideCos) * 22;

    pose.backHtml = windSvg;
    pose.frontHtml = `
      <g opacity="${fade.toFixed(2)}">
        <ellipse cx="${foot1X.toFixed(1)}" cy="${foot1Y.toFixed(1)}" rx="20" ry="11" fill="var(--fg)" transform="rotate(${(stride * 25).toFixed(1)} ${foot1X.toFixed(1)} ${foot1Y.toFixed(1)})" />
        <ellipse cx="${foot2X.toFixed(1)}" cy="${foot2Y.toFixed(1)}" rx="20" ry="11" fill="var(--fg)" transform="rotate(${(-stride * 25).toFixed(1)} ${foot2X.toFixed(1)} ${foot2Y.toFixed(1)})" />
      </g>
    `;
    return pose;
  }

  if (act === 'dj_groove') {
    // Studio headphones + heavy bass squash-and-stretch headbanging
    const beat = Math.abs(Math.sin(t * Math.PI * 3.2));
    pose.y = (1 - beat) * 14 - 6;
    pose.sx = 1 + (1 - beat) * 0.08;
    pose.sy = 1 - (1 - beat) * 0.08;
    pose.rot = Math.sin(t * Math.PI * 1.6) * 8;

    const hx = headPose.x + pose.x;
    const hy = headPose.y + pose.y;
    const hrot = headPose.rot + pose.rot;

    pose.frontHtml = `
      <g transform="translate(${(HEAD_C + hx).toFixed(1)} ${(HEAD_C + hy).toFixed(1)}) rotate(${hrot.toFixed(1)}) scale(${pose.sx.toFixed(3)} ${pose.sy.toFixed(3)}) translate(${-HEAD_C} ${-HEAD_C})" opacity="${fade.toFixed(2)}">
        <path d="M-12,98 L-12,56 Q-12,-28 ${HEAD_C},-28 Q240,-28 240,56 L240,98" fill="none" stroke="var(--fg)" stroke-width="18" stroke-linecap="round" />
        <rect x="-32" y="64" width="32" height="84" rx="12" fill="var(--fg)" stroke="var(--bg)" stroke-width="5" />
        <rect x="228" y="64" width="32" height="84" rx="12" fill="var(--fg)" stroke="var(--bg)" stroke-width="5" />
      </g>
    `;
    return pose;
  }

  if (act === 'peek_radar') {
    // Hide-and-seek peeking left & right + concentric sonar pulses
    const cyc = (t / 2.4) % 1;
    let py = 0;
    let px = 0;
    let prot = 0;
    if (cyc < 0.35) {
      const p = Math.sin((cyc / 0.35) * Math.PI);
      px = -16 * p;
      py = -14 * p;
      prot = -10 * p;
    } else if (cyc < 0.7) {
      const p = Math.sin(((cyc - 0.35) / 0.35) * Math.PI);
      px = 16 * p;
      py = -14 * p;
      prot = 10 * p;
    } else {
      const p = (cyc - 0.7) / 0.3;
      py = 18 * Math.sin(p * Math.PI);
    }
    pose.x = px;
    pose.y = py;
    pose.rot = prot;

    let rings = '';
    for (let i = 0; i < 2; i++) {
      const rp = (t * 0.9 + i * 0.5) % 1;
      const r = 118 + rp * 38;
      const op = (1 - rp) * 0.65 * fade;
      rings += `<circle cx="${(HEAD_C + px * 0.5).toFixed(1)}" cy="${(HEAD_C + py * 0.5).toFixed(1)}" r="${r.toFixed(1)}" fill="none" stroke="var(--fg)" stroke-width="${(6 * (1 - 0.4 * rp)).toFixed(1)}" opacity="${op.toFixed(2)}" />`;
    }
    pose.backHtml = rings;
    return pose;
  }

  if (act === 'constellation_command') {
    // Redesigned Sub-agent Act (replaces `twin_clone_sync`!):
    // Suzent stays centered as the sovereign commander with `❖ ❖` diamond matrix eyes and `< >` parallel link eyes,
    // floating gently while a crisp tilted 3D planetary ring + 3 monochrome satellite nodes orbit around it
    // in front (`z >= 0`) and behind (`z < 0`) with true depth occlusion!
    const floatWave = Math.sin(t * 2.4);
    pose.y = -10 * floatWave;
    pose.rot = 5 * Math.sin(t * 1.2);
    pose.sx = 1 + 0.03 * floatWave;
    pose.sy = 1 - 0.03 * floatWave;

    const tiltRad = 0.36; // ~20 deg tilt
    const rollDeg = -16 + 6 * Math.sin(t * 0.8);
    const orbitRx = 144;
    const orbitRy = orbitRx * Math.sin(tiltRad);

    // Back half of the orbital ring + satellites with z < 0
    let backNodes = `<path d="M ${HEAD_C - orbitRx} ${HEAD_C} A ${orbitRx} ${orbitRy.toFixed(1)} 0 0 1 ${HEAD_C + orbitRx} ${HEAD_C}" fill="none" stroke="var(--fg)" stroke-width="5" opacity="${(0.28 * fade).toFixed(2)}" />`;
    // Front half of the orbital ring + satellites with z >= 0
    let frontNodes = `<path d="M ${HEAD_C - orbitRx} ${HEAD_C} A ${orbitRx} ${orbitRy.toFixed(1)} 0 0 0 ${HEAD_C + orbitRx} ${HEAD_C}" fill="none" stroke="var(--fg)" stroke-width="6.5" opacity="${(0.65 * fade).toFixed(2)}" />`;

    for (let i = 0; i < 3; i++) {
      const a = t * 2.5 + (i * Math.PI * 2) / 3;
      const sx = HEAD_C + orbitRx * Math.cos(a);
      const sy = HEAD_C + orbitRy * Math.sin(a);
      const z = Math.sin(a); // +1 = front (bottom of tilted ellipse), -1 = back (top of tilted ellipse)
      const r = 13 + 5.5 * z;
      const op = (0.45 + 0.55 * ((z + 1) / 2)) * fade;
      const nodeMarkup = `<circle cx="${sx.toFixed(1)}" cy="${sy.toFixed(1)}" r="${r.toFixed(1)}" fill="var(--fg)" stroke="var(--bg)" stroke-width="3.5" opacity="${op.toFixed(2)}" />`;
      if (z < 0) backNodes += nodeMarkup;
      else frontNodes += nodeMarkup;
    }

    pose.backHtml = `<g transform="rotate(${rollDeg.toFixed(1)} ${HEAD_C} ${HEAD_C})">${backNodes}</g>`;
    pose.frontHtml = `<g transform="rotate(${rollDeg.toFixed(1)} ${HEAD_C} ${HEAD_C})">${frontNodes}</g>`;
    return pose;
  }

  if (act === 'fountain_pen') {
    // W2: WRITING / EDITING FILES (与 pencil morph 完全一致的笔和波浪墨迹线条!)
    // Suzent leans back to the upper-left while holding the exact 2-part pencil assembly
    // (`PENCIL_GLYPH` barrel + `PENCIL_NIB_PATH` teardrop nib) clearly to the right so the entire pencil is unobstructed!
    const cyc = (t / 2.2) % 1;
    let penX = 0;
    let penY = 58;
    let wiggle = 0;
    let penRot = 24;
    let prog = 0;
    let lift = false;

    if (cyc < 0.72) {
      prog = cyc / 0.72;
      const env = clamp(prog / 0.06, 0, 1) * clamp((1 - prog) / 0.08, 0, 1);
      wiggle = (5.5 * Math.sin(26 * prog) + 2.5 * Math.cos(13 * prog)) * env;
      penX = 18 + prog * 108;
      penY = 58;
      penRot = 24 + 4 * Math.cos(26 * prog) * env;
      lift = false;
    } else {
      const p = (cyc - 0.72) / 0.28;
      const ease = p < 0.5 ? 4 * p * p * p : 1 - (-2 * p + 2) ** 3 / 2;
      prog = 1 - ease;
      penX = 126 - 108 * ease;
      penY = 58 - 28 * Math.sin(ease * Math.PI);
      penRot = 24 - 6 * Math.sin(ease * Math.PI);
      lift = true;
    }

    pose.x = -34 + (penX - 72) * 0.16;
    pose.y = -22 + wiggle * 0.25;
    pose.rot = -6 + (penX - 72) * 0.09;
    pose.sx = 0.88;
    pose.sy = 0.88;
    pose.gazeX = 18 + (penX - 72) * 0.16;
    pose.gazeY = 18;

    // Build the exact wavy ink path across [18, 18 + 108 * drawProg]
    const drawProg = lift ? 1 : prog;
    const steps = Math.max(2, Math.round(drawProg * 36));
    let trailPath = '';
    if (!lift && drawProg > 0.03) {
      for (let i = 0; i <= steps; i++) {
        const s = (i / steps) * drawProg;
        const env = clamp(s / 0.06, 0, 1) * clamp((1 - s) / 0.08, 0, 1);
        const w = (5.5 * Math.sin(26 * s) + 2.5 * Math.cos(13 * s)) * env;
        const tx = HEAD_C + 18 + s * 108;
        const ty = HEAD_C + 58 + 0.5 * w + 26;
        trailPath += `${i === 0 ? 'M' : 'L'}${tx.toFixed(1)} ${ty.toFixed(1)}`;
      }
    }

    const angle = ((penRot - 90) * Math.PI) / 180;
    const offsetX = 68 * Math.cos(angle);
    const offsetY = 68 * Math.sin(angle);
    const gx = HEAD_C + penX + offsetX;
    const gy = HEAD_C + penY + 0.15 * wiggle + offsetY;
    const nibCenterX = HEAD_C + penX;
    const nibCenterY = HEAD_C + penY + 0.5 * wiggle;
    const nibScale = (28 / HEAD_C).toFixed(4);

    // Exact 2-part pencil assembly from `renderPencil` (teardrop PENCIL_RING nib + PENCIL_GLYPH barrel)
    pose.frontHtml = `
      <g opacity="${fade.toFixed(2)}">
        ${trailPath ? `<path d="${trailPath}" fill="none" stroke="var(--fg)" stroke-width="10" stroke-linecap="round" stroke-linejoin="round" />` : ''}
        <g transform="translate(${gx.toFixed(1)} ${gy.toFixed(1)}) rotate(${penRot.toFixed(1)}) translate(${-HEAD_C} ${-HEAD_C})">
          <path d="${PENCIL_GLYPH}" fill="var(--bg)" stroke="var(--bg)" stroke-width="14" stroke-linejoin="round" />
          <path d="${PENCIL_GLYPH}" fill="var(--fg)" />
        </g>
        <g transform="translate(${nibCenterX.toFixed(1)} ${nibCenterY.toFixed(1)}) rotate(${penRot.toFixed(1)}) scale(${nibScale}) translate(${-HEAD_C} ${-HEAD_C})">
          <path d="${PENCIL_NIB_PATH}" fill="var(--bg)" stroke="var(--bg)" stroke-width="48" stroke-linejoin="round" />
          <path d="${PENCIL_NIB_PATH}" fill="var(--fg)" />
        </g>
      </g>
    `;
    return pose;
  }

  if (act === 'agent_twin_split') {
    // A2: TRUE ORGANIC MITOSIS TWIN-AGENT MORPH & SPLIT!
    // Phase 1 (0 -> 0.24): The 96-point Suzent body stretches and pinches at the waist into a peanut/figure-8 contour!
    // Phase 2 (0.24 -> 0.80): The waist snaps cleanly in two (`split` 0 -> 1) and two twin bots bounce on left & right!
    // Phase 3 (0.80 -> 1.00): The twins rush back together, pinch-fuse at the waist, and rebound into one bot!
    const cyc = (t / 2.6) % 1;
    let pinch = 0;
    let split = 0;
    let stretchX = 1;
    let stretchY = 1;
    let bob = 0;

    if (cyc < 0.24) {
      const p = cyc / 0.24;
      const ease = p * p * (3 - 2 * p);
      pinch = ease;
      stretchX = 1 + 0.34 * ease;
      stretchY = 1 - 0.14 * Math.sin(p * Math.PI);
      split = 0;
    } else if (cyc < 0.8) {
      const p = (cyc - 0.24) / 0.56;
      const snap = Math.min(1, p * 5.2);
      pinch = Math.max(0, 1 - p * 6.5);
      split = 1 - (1 - snap) ** 3;
      bob = Math.sin(p * Math.PI * 4) * 16 * split;
      // Elastic recoil right after the mitosis waist snaps!
      const recoil = Math.exp(-p * 9) * Math.cos(p * 28);
      stretchX = 1 - 0.16 * recoil + 0.06 * Math.cos(p * Math.PI * 4);
      stretchY = 1 + 0.16 * recoil - 0.06 * Math.cos(p * Math.PI * 4);
    } else {
      const p = (cyc - 0.8) / 0.2;
      if (p < 0.55) {
        const mp = p / 0.55;
        split = 1 - mp * mp;
        pinch = mp;
      } else {
        const fp = (p - 0.55) / 0.45;
        split = 0;
        pinch = 1 - fp * fp * (3 - 2 * fp);
        const pop = Math.sin(fp * Math.PI);
        stretchX = 1 - 0.14 * pop;
        stretchY = 1 + 0.16 * pop;
        bob = -14 * pop;
      }
    }

    if (pinch > 0.01 && split < 0.25) {
      pose.targetRing = buildMitosisPinchRing(SUZENT_BODY_RING, pinch, stretchX);
      pose.ringBlend = Math.min(1, pinch * 1.25) * (1 - split * 4);
    }

    const bodyScale = 1 - 0.46 * split; // 1.0 -> 0.54 when separated
    // Smooth continuity at the snap transition: during pinch, lobes sit at ±42; after snap, they spring out to ±78!
    const offset = split > 0 ? 34 + 44 * split : 0;
    pose.x = -offset;
    pose.y = bob;
    pose.sx = bodyScale * (split > 0 ? stretchX : 1);
    pose.sy = bodyScale * stretchY;
    pose.rot = -10 * split + (split > 0.5 ? Math.sin(t * 10) * 5 : 0);
    pose.gazeX = split > 0.2 ? 14 : 0;

    if (pinch > 0.22 && split <= 0.02) {
      // During the figure-8 waist pinch before snap, show a second pair of eyes budding in the right lobe!
      const lobeEyeOp = clamp((pinch - 0.22) / 0.55, 0, 1) * fade;
      const rightLobeX = HEAD_C + 44 * pinch;
      pose.frontHtml = `
        <g opacity="${lobeEyeOp.toFixed(2)}" transform="translate(${rightLobeX.toFixed(1)} ${HEAD_C}) scale(${(0.55 + 0.1 * pinch).toFixed(3)}) translate(${-HEAD_C} ${-HEAD_C})">
          <rect x="44" y="74" width="48" height="48" rx="14" fill="var(--bg)" />
          <rect x="136" y="74" width="48" height="48" rx="14" fill="var(--bg)" />
        </g>
      `;
    } else if (split > 0.02) {
      const cloneX = HEAD_C + offset;
      const cloneY = HEAD_C - bob;
      const cloneRot = 10 * split - (split > 0.5 ? Math.sin(t * 10) * 5 : 0);
      const cloneScaleX = (bodyScale * stretchX).toFixed(3);
      const cloneScaleY = (bodyScale * stretchY).toFixed(3);
      const cloneOp = Math.min(1, split * 3.5) * fade;
      // Snapping cytoplasmic strand right as they pull apart (0.02 < split < 0.55)
      const strandOp = split < 0.55 ? (1 - split / 0.55) * fade : 0;
      const strandHalf = 18 + 26 * split;
      const strandSvg =
        strandOp > 0.04
          ? `<path d="M ${(HEAD_C - strandHalf).toFixed(1)} ${(HEAD_C - 10 * (1 - split)).toFixed(1)} Q ${HEAD_C} ${HEAD_C} ${(HEAD_C + strandHalf).toFixed(1)} ${(HEAD_C - 10 * (1 - split)).toFixed(1)} M ${(HEAD_C - strandHalf).toFixed(1)} ${(HEAD_C + 10 * (1 - split)).toFixed(1)} Q ${HEAD_C} ${HEAD_C} ${(HEAD_C + strandHalf).toFixed(1)} ${(HEAD_C + 10 * (1 - split)).toFixed(1)}" fill="none" stroke="var(--fg)" stroke-width="${(12 * (1 - split / 0.55)).toFixed(1)}" stroke-linecap="round" opacity="${strandOp.toFixed(2)}" />`
          : '';
      pose.frontHtml = `
        <g opacity="${cloneOp.toFixed(2)}">
          ${strandSvg}
          <g transform="translate(${cloneX.toFixed(1)} ${cloneY.toFixed(1)}) rotate(${cloneRot.toFixed(1)}) scale(${cloneScaleX} ${cloneScaleY}) translate(${-HEAD_C} ${-HEAD_C})">
            <path d="${SUZENT_BODY_PATH}" fill="var(--fg)" stroke="var(--bg)" stroke-width="10" />
            <rect x="44" y="74" width="48" height="48" rx="14" fill="var(--bg)" />
            <rect x="136" y="74" width="48" height="48" rx="14" fill="var(--bg)" />
          </g>
        </g>
      `;
    }
    return pose;
  }

  if (act === 'agent_portal_spawn') {
    // A3: PORTAL SUMMONING MINI-BOT (传送门召唤：右侧地面传送阵升起迷你小机器人!)
    const cyc = (t / 2.2) % 1;
    let emerge = 0;
    let portalScale = 1;
    if (cyc < 0.25) {
      emerge = cyc / 0.25;
      portalScale = emerge;
    } else if (cyc < 0.78) {
      emerge = 1;
      portalScale = 1 + 0.08 * Math.sin(t * 10);
    } else {
      emerge = 1 - (cyc - 0.78) / 0.22;
      portalScale = emerge;
    }

    const bob = Math.sin(t * 7) * 10 * emerge;
    pose.x = -26;
    pose.y = -bob * 0.4;
    pose.rot = -5 + Math.sin(t * 3.5) * 4;
    pose.gazeX = 20;
    pose.gazeY = 6;

    const px = HEAD_C + 106;
    const py = 228;
    const miniY = py - 58 * emerge + bob;
    const miniScale = (0.44 * emerge).toFixed(3);

    pose.frontHtml = `
      <g opacity="${fade.toFixed(2)}">
        <ellipse cx="${px}" cy="${py}" rx="${(44 * portalScale).toFixed(1)}" ry="${(12 * portalScale).toFixed(1)}" fill="var(--bg)" stroke="var(--fg)" stroke-width="9" />
        <g transform="translate(${px} ${miniY.toFixed(1)}) scale(${miniScale}) translate(${-HEAD_C} ${-HEAD_C})">
          <path d="${SUZENT_BODY_PATH}" fill="var(--fg)" stroke="var(--bg)" stroke-width="14" />
          <rect x="44" y="74" width="48" height="48" rx="14" fill="var(--bg)" />
          <rect x="136" y="74" width="48" height="48" rx="14" fill="var(--bg)" />
        </g>
      </g>
    `;
    return pose;
  }

  if (act === 'agent_megaphone_rally') {
    // A4: COMMANDER MEGAPHONE CALL (指挥官大喇叭号令召唤)
    const shout = Math.abs(Math.sin(t * 6.5));
    pose.x = -18;
    pose.y = -6 * shout;
    pose.sx = 1 + 0.06 * shout;
    pose.sy = 1 - 0.05 * shout;
    pose.rot = -8 * shout;
    pose.gazeX = 18;
    pose.gazeY = -4;

    const mx = HEAD_C + pose.x + 76;
    const my = HEAD_C + pose.y + 8;
    const wave1 = (t * 2.2) % 1;
    const wave2 = (t * 2.2 + 0.5) % 1;

    pose.frontHtml = `
      <g opacity="${fade.toFixed(2)}">
        <polygon points="${mx},${my - 12} ${mx + 56},${my - 38} ${mx + 56},${my + 38} ${mx},${my + 12}" fill="var(--fg)" stroke="var(--bg)" stroke-width="6" stroke-linejoin="round" />
        <line x1="${mx + 14}" y1="${my + 14}" x2="${mx + 8}" y2="${my + 38}" stroke="var(--fg)" stroke-width="12" stroke-linecap="round" />
        <path d="M ${mx + 68 + wave1 * 28} ${my - 26 - wave1 * 12} A 36 36 0 0 1 ${mx + 68 + wave1 * 28} ${my + 26 + wave1 * 12}" fill="none" stroke="var(--fg)" stroke-width="9" stroke-linecap="round" opacity="${(1 - wave1).toFixed(2)}" />
        <path d="M ${mx + 68 + wave2 * 28} ${my - 26 - wave2 * 12} A 36 36 0 0 1 ${mx + 68 + wave2 * 28} ${my + 26 + wave2 * 12}" fill="none" stroke="var(--fg)" stroke-width="9" stroke-linecap="round" opacity="${(1 - wave2).toFixed(2)}" />
      </g>
    `;
    return pose;
  }

  if (act === 'agent_antenna_dispatch') {
    // A5: TELEPATHIC ANTENNA DISPATCH TO MINI-AGENT (头顶天线远程遥控子 Agent)
    const pulse = (t * 2.0) % 1;
    pose.x = -24;
    pose.y = Math.sin(t * 4) * 5;
    pose.rot = 5 * Math.sin(t * 2);
    pose.gazeX = 20;
    pose.gazeY = 8;

    const ax = HEAD_C + headPose.x + pose.x;
    const ay = HEAD_C + headPose.y + pose.y - 96;
    const mx = HEAD_C + 108;
    const my = HEAD_C + 36 + Math.cos(t * 6) * 10;

    pose.frontHtml = `
      <g opacity="${fade.toFixed(2)}">
        <line x1="${ax.toFixed(1)}" y1="${(ay + 12).toFixed(1)}" x2="${ax.toFixed(1)}" y2="${(ay - 28).toFixed(1)}" stroke="var(--fg)" stroke-width="13" stroke-linecap="round" />
        <circle cx="${ax.toFixed(1)}" cy="${(ay - 32).toFixed(1)}" r="13" fill="var(--fg)" />
        <circle cx="${ax.toFixed(1)}" cy="${(ay - 32).toFixed(1)}" r="${(14 + pulse * 34).toFixed(1)}" fill="none" stroke="var(--fg)" stroke-width="7" opacity="${(1 - pulse).toFixed(2)}" />
        <g transform="translate(${mx} ${my.toFixed(1)}) scale(0.42) translate(${-HEAD_C} ${-HEAD_C})">
          <path d="${SUZENT_BODY_PATH}" fill="var(--fg)" stroke="var(--bg)" stroke-width="14" />
          <rect x="44" y="74" width="48" height="48" rx="14" fill="var(--bg)" />
          <rect x="136" y="74" width="48" height="48" rx="14" fill="var(--bg)" />
        </g>
      </g>
    `;
    return pose;
  }

  if (act === 'agent_squad_march') {
    // A6: TANDEM SQUAD FORMATION (主从三机编队齐步跳跃!)
    const hop = Math.abs(Math.sin(t * 7));
    const hop2 = Math.abs(Math.sin(t * 7 - 0.9));
    const hop3 = Math.abs(Math.sin(t * 7 - 1.8));
    pose.x = -34;
    pose.y = -18 * hop + 6;
    pose.sx = 0.86 + (1 - hop) * 0.08;
    pose.sy = 0.86 - (1 - hop) * 0.06;
    pose.gazeX = 16;

    const m1Y = HEAD_C + 28 - 22 * hop2;
    const m2Y = HEAD_C + 44 - 22 * hop3;

    pose.frontHtml = `
      <g opacity="${fade.toFixed(2)}">
        <g transform="translate(${HEAD_C + 68} ${m1Y.toFixed(1)}) scale(0.42) translate(${-HEAD_C} ${-HEAD_C})">
          <path d="${SUZENT_BODY_PATH}" fill="var(--fg)" stroke="var(--bg)" stroke-width="14" />
          <rect x="44" y="74" width="48" height="48" rx="14" fill="var(--bg)" />
          <rect x="136" y="74" width="48" height="48" rx="14" fill="var(--bg)" />
        </g>
        <g transform="translate(${HEAD_C + 132} ${m2Y.toFixed(1)}) scale(0.32) translate(${-HEAD_C} ${-HEAD_C})">
          <path d="${SUZENT_BODY_PATH}" fill="var(--fg)" stroke="var(--bg)" stroke-width="16" />
          <rect x="44" y="74" width="48" height="48" rx="14" fill="var(--bg)" />
          <rect x="136" y="74" width="48" height="48" rx="14" fill="var(--bg)" />
        </g>
      </g>
    `;
    return pose;
  }

  return pose;
}
