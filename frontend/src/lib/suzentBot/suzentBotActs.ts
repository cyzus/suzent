/**
 * Full-body physical acts & stage mapping for the Suzent Bot Engine.
 *
 * Maps Suzent's streaming / thinking / tool states into expressive eye pools,
 * full-body squash-and-stretch choreography (`workout`, `eureka_levitate`,
 * `speed_reader`, `dj_groove`, `peek_radar`, `constellation_command`), and
 * periodic 180° 3D-turn geometric morph previews (`dots`, `radar`, `receive`,
 * `pencil`, `wave`, `orbit`, `send`, `gather`, `progress`, `bang`).
 */

import { HEAD_C, clamp } from './suzentBotGeometry';
import { normalizeToolName } from '../../components/chat/toolSummary';

export type SuzentBotStageId =
  | 'idle'
  | 'thinking'
  | 'searching'
  | 'reading'
  | 'writing'
  | 'bash'
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
  | 'dj_groove'
  | 'peek_radar'
  | 'constellation_command';

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
    cycleMorph: 'none',
    expressionPool: [0, 8, 2, 20],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  thinking: {
    id: 'thinking',
    baseState: 'suspicious',
    act: 'eureka_levitate',
    cycleMorph: 'dots',
    expressionPool: [5, 14, 9, 18, 3],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  searching: {
    id: 'searching',
    baseState: 'searching',
    act: 'peek_radar',
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
    cycleMorph: 'receive',
    expressionPool: [0, 8, 9, 2, 3],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  writing: {
    id: 'writing',
    baseState: 'working',
    act: 'workout',
    cycleMorph: 'pencil',
    expressionPool: [7, 10, 24, 6],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  bash: {
    id: 'bash',
    baseState: 'humming',
    act: 'dj_groove',
    cycleMorph: 'wave',
    expressionPool: [10, 16, 7, 24],
    humming: true,
    notifying: false,
    celebrating: false,
  },
  subagent: {
    id: 'subagent',
    baseState: 'playful',
    act: 'constellation_command',
    cycleMorph: 'orbit',
    expressionPool: [17, 23, 6, 10, 3],
    humming: true,
    notifying: false,
    celebrating: false,
  },
  vision: {
    id: 'vision',
    baseState: 'curious',
    act: 'speed_reader',
    cycleMorph: 'gather',
    expressionPool: [9, 18, 15, 6, 3],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  skill: {
    id: 'skill',
    baseState: 'playful',
    act: 'eureka_levitate',
    cycleMorph: 'orbit',
    expressionPool: [16, 3, 10, 2, 17],
    humming: true,
    notifying: false,
    celebrating: false,
  },
  social: {
    id: 'social',
    baseState: 'playful',
    act: 'none',
    cycleMorph: 'send',
    expressionPool: [2, 8, 3, 19, 0],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  tasks: {
    id: 'tasks',
    baseState: 'curious',
    act: 'eureka_levitate',
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
    case 'webpage_fetch':
    case 'agent_read':
      return 'reading';
    case 'write_file':
    case 'edit_file':
      return 'writing';
    case 'glob_search':
    case 'grep_search':
    case 'web_search':
    case 'memory_search':
    case 'session_search':
    case 'search_tools':
      return 'searching';
    case 'run_command':
    case 'start_command':
    case 'check_command':
    case 'stop_command':
      return 'bash';
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
    // Pure expressive character speed-reading: no face-cluttering props!
    // Left-to-right 3-beat saccade scan + crisp carriage-return head snap & squash-and-stretch nod.
    const cyc = (t / 1.4) % 1;
    let scanX = 0;
    let nodY = 0;
    let tilt = 0;
    let sx = 1;
    let sy = 1;

    if (cyc < 0.74) {
      const p = cyc / 0.74;
      // 3 distinct eye/head reading stops across the line
      const stepWave = Math.sin(p * Math.PI * 6);
      const smoothStep = p + 0.055 * stepWave;
      scanX = -18 + smoothStep * 36;
      nodY = 4.5 * Math.abs(Math.sin(p * Math.PI * 3));
      tilt = (smoothStep - 0.5) * 10;
      sx = 1 + 0.025 * Math.abs(stepWave);
      sy = 1 - 0.025 * Math.abs(stepWave);
    } else {
      // Crisp carriage-return snap back to the left + page-turn nod
      const p = (cyc - 0.74) / 0.26;
      const ease = 1 - (1 - p) ** 3;
      const snapArc = Math.sin(p * Math.PI);
      scanX = 18 - ease * 36;
      nodY = -14 * snapArc;
      tilt = (0.5 - ease) * 13;
      sx = 1 - 0.06 * snapArc;
      sy = 1 + 0.07 * snapArc;
    }

    pose.x = scanX * 0.55;
    pose.y = nodY;
    pose.rot = tilt;
    pose.sx = sx;
    pose.sy = sy;
    pose.gazeX = scanX * 1.1;
    pose.gazeY = 3.5;
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

  return pose;
}
