import { HEAD_C, PENCIL_GLYPH, PENCIL_RING, clamp, ringOutline } from '../suzentBotGeometry';
import { ActEvalContext, FullBodyActPose, createDefaultActPose } from './actTypes';

const PENCIL_NIB_PATH: string = ringOutline(PENCIL_RING);

/** W2: Writing/editing files with the exact 2-part pencil assembly (`PENCIL_GLYPH` + `PENCIL_RING`) and wavy ink trail */
export function evalFountainPen({ t, fade }: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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

/** W1: Deep squat + explosive overhead barbell press (`start_command`, `stop_command`) */
export function evalWorkout({ t, fade }: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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
    press > 0.5 ? Math.sin((cyc - 0.36) * 28) * 4.5 * Math.exp(-(cyc - 0.36) * 4) + 5 : -3 * squat;

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

/** E1: Furious laptop coding with >_ terminal emblem (`run_command`, `check_command`) */
export function evalLaptopType({ t, fade }: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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

/** E2: Full-throttle sprinter with pumping feet & trailing speed lines */
export function evalTurboSprinter({ t, fade }: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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

/** E4: Studio headphones + heavy bass squash-and-stretch headbanging */
export function evalDjGroove({ t, fade, headPose }: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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
