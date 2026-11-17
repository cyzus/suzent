import { normalizeToolName } from './normalizeToolName';
import { clamp } from './suzentBotGeometry';
import { cubicInOut, cubicOut, springValue, stepSpring } from './suzentBotPhysics';
import { VElement, sceneFromTree, type SceneFrame } from './suzentBotScene';

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

export function pickToolSvgGlyphKind(toolName: string, animKind: string): ToolSvgGlyphKind {
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


export const toolGlyphMarkup: Record<ToolSvgGlyphKind, string> = {
  "read": "<path d=\"M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z\" />\n          <path d=\"M14 3v6h6\" />\n          <line class=\"tg-read-line\" x1=\"8.2\" y1=\"11.2\" x2=\"15.6\" y2=\"11.2\" />\n          <line class=\"tg-read-line\" x1=\"8.2\" y1=\"14.6\" x2=\"15.6\" y2=\"14.6\" />\n          <line class=\"tg-read-line\" x1=\"8.2\" y1=\"18.0\" x2=\"13.0\" y2=\"18.0\" />\n          <circle\n            class=\"tg-read-dot\"\n            cx=\"15.6\"\n            cy=\"11.2\"\n            r=\"1.35\"\n            fill=\"currentColor\"\n            stroke=\"none\"\n          />",
  "write": "<path d=\"M11 4H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-6\" />\n          <line class=\"tg-write-ink1\" x1=\"7.5\" y1=\"14.5\" x2=\"13.5\" y2=\"14.5\" />\n          <line class=\"tg-write-ink2\" x1=\"7.5\" y1=\"17.5\" x2=\"11.5\" y2=\"17.5\" opacity=\"0\" />\n          <g class=\"tg-write-pen\">\n            <path d=\"M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z\" />\n          </g>",
  "search": "<g class=\"tg-search-glass\">\n          <circle cx=\"10.5\" cy=\"10.5\" r=\"6.5\" />\n          <path class=\"tg-search-glint\" d=\"M8 8.2a3.2 3.2 0 0 1 4.2-.4\" stroke-width=\"1.8\" />\n          <line x1=\"15.2\" y1=\"15.2\" x2=\"20.5\" y2=\"20.5\" stroke-width=\"2.6\" />\n        </g>",
  "globe": "<circle cx=\"12\" cy=\"12\" r=\"9\" />\n          <line x1=\"3.4\" y1=\"9\" x2=\"20.6\" y2=\"9\" stroke-width=\"1.8\" />\n          <line x1=\"3.4\" y1=\"15\" x2=\"20.6\" y2=\"15\" stroke-width=\"1.8\" />\n          <ellipse class=\"tg-globe-meridian\" cx=\"12\" cy=\"12\" rx=\"4.2\" ry=\"9\" />\n          <circle\n            class=\"tg-globe-sat\"\n            cx=\"20.5\"\n            cy=\"12\"\n            r=\"1.5\"\n            fill=\"currentColor\"\n            stroke=\"none\"\n          />",
  "folder": "<path d=\"M3 7V17a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-6.5l-2-2H5a2 2 0 0 0-2 2z\" />\n          <rect class=\"tg-folder-sheet\" x=\"6.5\" y=\"7.5\" width=\"11\" height=\"6\" rx=\"1\" />\n          <path\n            class=\"tg-folder-front\"\n            d=\"M3 11.5h18l-1.2 6a1.8 1.8 0 0 1-1.8 1.5H6a1.8 1.8 0 0 1-1.8-1.5L3 11.5z\"\n          />",
  "terminal": "<rect x=\"2.5\" y=\"4\" width=\"19\" height=\"16\" rx=\"2.5\" />\n          <path class=\"tg-term-chev\" d=\"M6.8 9.5L10.3 12L6.8 14.5\" />\n          <line\n            class=\"tg-term-cursor\"\n            x1=\"12.5\"\n            y1=\"14.8\"\n            x2=\"17.2\"\n            y2=\"14.8\"\n            stroke-width=\"2.6\"\n          />",
  "memory": "<rect x=\"6\" y=\"6\" width=\"12\" height=\"12\" rx=\"2\" />\n          <rect\n            class=\"tg-mem-core\"\n            x=\"9.5\"\n            y=\"9.5\"\n            width=\"5\"\n            height=\"5\"\n            rx=\"0.8\"\n            fill=\"currentColor\"\n          />\n          <line class=\"tg-mem-pin\" x1=\"9\" y1=\"2.5\" x2=\"9\" y2=\"6\" />\n          <line class=\"tg-mem-pin\" x1=\"15\" y1=\"2.5\" x2=\"15\" y2=\"6\" />\n          <line class=\"tg-mem-pin\" x1=\"9\" y1=\"18\" x2=\"9\" y2=\"21.5\" />\n          <line class=\"tg-mem-pin\" x1=\"15\" y1=\"18\" x2=\"15\" y2=\"21.5\" />\n          <line class=\"tg-mem-pin\" x1=\"2.5\" y1=\"9\" x2=\"6\" y2=\"9\" />\n          <line class=\"tg-mem-pin\" x1=\"2.5\" y1=\"15\" x2=\"6\" y2=\"15\" />\n          <line class=\"tg-mem-pin\" x1=\"18\" y1=\"9\" x2=\"21.5\" y2=\"9\" />\n          <line class=\"tg-mem-pin\" x1=\"18\" y1=\"15\" x2=\"21.5\" y2=\"15\" />",
  "tasks": "<rect x=\"4\" y=\"3.5\" width=\"16\" height=\"17.5\" rx=\"2\" />\n          <path\n            class=\"tg-task-check\"\n            d=\"M7.2 10.2l1.6 1.6 2.8-3\"\n            stroke-dasharray=\"10\"\n            stroke-dashoffset=\"0\"\n          />\n          <line class=\"tg-task-bar1\" x1=\"11.5\" y1=\"15\" x2=\"16.5\" y2=\"15\" />\n          <line class=\"tg-task-bar2\" x1=\"11.5\" y1=\"18\" x2=\"15.5\" y2=\"18\" />",
  "bolt": "<path class=\"tg-bolt-main\" d=\"M13 2L4.5 13.5h6.5L10 22l9.5-12h-6.5L13 2z\" />\n          <circle\n            class=\"tg-bolt-spark\"\n            cx=\"4.5\"\n            cy=\"5.5\"\n            r=\"1.2\"\n            fill=\"currentColor\"\n            stroke=\"none\"\n          />\n          <circle\n            class=\"tg-bolt-spark\"\n            cx=\"19.5\"\n            cy=\"18.5\"\n            r=\"1.2\"\n            fill=\"currentColor\"\n            stroke=\"none\"\n          />",
  "cursor": "<circle class=\"tg-cursor-ring\" cx=\"9\" cy=\"9\" r=\"3\" stroke-width=\"1.8\" opacity=\"0\" />\n          <path\n            class=\"tg-cursor-arrow\"\n            d=\"M5.5 4.5l13 5.2-5.6 1.9-2.2 5.9-5.2-13z\"\n            fill=\"currentColor\"\n          />",
  "signal": "<circle cx=\"6\" cy=\"18\" r=\"2\" fill=\"currentColor\" stroke=\"none\" />\n          <path class=\"tg-sig-wave\" d=\"M6 12a6 6 0 0 1 6 6\" />\n          <path class=\"tg-sig-wave\" d=\"M6 7a11 11 0 0 1 11 11\" />\n          <path class=\"tg-sig-wave\" d=\"M6 2a16 16 0 0 1 16 16\" />",
  "pending": "<circle cx=\"12\" cy=\"12\" r=\"9\" />\n          <line class=\"tg-clock-hour\" x1=\"12\" y1=\"12\" x2=\"12\" y2=\"8.2\" stroke-width=\"2.5\" />\n          <line class=\"tg-clock-min\" x1=\"12\" y1=\"12\" x2=\"12\" y2=\"5.6\" stroke-width=\"2\" />"
};

interface GlyphNode { setAttribute(name: string, value: string): void }
interface GlyphRoot {
  querySelector(selector: string): GlyphNode | null;
  querySelectorAll(selector: string): { forEach(callback: (node: GlyphNode, index: number) => void): void };
}

export function createToolGlyphAnimator(svg: GlyphRoot, kind: ToolSvgGlyphKind): (seconds: number) => void {
  const springA = springValue(0);
  const springB = springValue(0);
  let stepIndex = -1;
  let lastTime = 0;
  return (t: number) => {
    const dt = clamp(t - lastTime, 0.001, 0.05);
    lastTime = t;
if (kind === 'read') {
  // Document page with sequential line-by-line reading reveal + sliding reading pointer dot
  const cyc = (t / 1.25) % 1;
  const row = cyc < 0.32 ? 0 : cyc < 0.64 ? 1 : 2;
  const rowY = row === 0 ? 11.2 : row === 1 ? 14.6 : 18.0;
  springA.target = rowY;
  stepSpring(springA, 22, 0.76, dt);

  const dot = svg.querySelector('.tg-read-dot');
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
  const pen = svg.querySelector('.tg-write-pen');
  const ink1 = svg.querySelector('.tg-write-ink1');
  const ink2 = svg.querySelector('.tg-write-ink2');
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
  const glass = svg.querySelector('.tg-search-glass');
  const glint = svg.querySelector('.tg-search-glint');
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
  const meridian = svg.querySelector('.tg-globe-meridian');
  const sat = svg.querySelector('.tg-globe-sat');
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
  const sheet = svg.querySelector('.tg-folder-sheet');
  const front = svg.querySelector('.tg-folder-front');
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
  const chev = svg.querySelector('.tg-term-chev');
  const cur = svg.querySelector('.tg-term-cursor');
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
  const core = svg.querySelector('.tg-mem-core');
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
  const check = svg.querySelector('.tg-task-check');
  const bar1 = svg.querySelector('.tg-task-bar1');
  const bar2 = svg.querySelector('.tg-task-bar2');
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
  const bolt = svg.querySelector('.tg-bolt-main');
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
  const arrow = svg.querySelector('.tg-cursor-arrow');
  const ring = svg.querySelector('.tg-cursor-ring');
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
    const phase = (((t * 1.6 - idx * 0.28) % 1) + 1) % 1;
    const op = Math.sin(phase * Math.PI);
    w.setAttribute('opacity', clamp(op, 0.2, 1).toFixed(2));
  });
} else if (kind === 'pending') {
  // Clock with long sweeping minute hand & short spring-stepping hour hand
  // Every full 360° sweep of the minute hand (1.5s), the short hour hand steps 30° (1 hour)!
  const minHand = svg.querySelector('.tg-clock-min');
  const hourHand = svg.querySelector('.tg-clock-hour');
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
  };
}

export class ToolGlyphScene {
  private readonly root = new VElement('svg');
  private readonly animate: (seconds: number) => void;
  constructor(kind: ToolSvgGlyphKind) {
    this.root.setAttribute('viewBox', '0 0 24 24');
    this.root.innerHTML = toolGlyphMarkup[kind];
    const inherit = (node: VElement, parent: Record<string, string>) => {
      const attrs = { ...parent, ...node.attrs };
      for (const key of ['fill', 'stroke', 'stroke-width']) node.setAttribute(key, attrs[key]);
      node.children.forEach(child => inherit(child, attrs));
    };
    this.root.children.forEach(node => inherit(node, { fill: 'none', stroke: 'currentColor', 'stroke-width': '2.25' }));
    this.animate = createToolGlyphAnimator(this.root, kind);
  }
  frame(seconds: number, reduced: boolean): SceneFrame {
    if (!reduced) this.animate(seconds);
    return sceneFromTree(this.root, { fg: 'currentColor', bg: 'none', settled: reduced });
  }
}
