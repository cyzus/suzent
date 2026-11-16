import { HEAD_C, Point2D, clamp } from '../suzentBotGeometry';
import { ActEvalContext, FullBodyActPose, createDefaultActPose } from './actTypes';

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

/** T1: Upper-right thought cloud with "..." pulsing dots that flash into "!" idea rays */
export function evalThoughtCloud({ t, fade }: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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

/** T2: True spline morph into an 8-tooth mechanical gear cog with meshing companion gear */
export function evalFullGear({ t, fade, headPose }: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
  const cyc = (t / 3.4) % 1;
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

/** T3: "?" puzzled wobble -> 360° "!" Eureka flip */
export function evalQuestionEureka({ t, fade }: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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

/** T4: Zero-G levitation + breathing ground shadow + 360° Eureka mid-air somersault */
export function evalEurekaLevitate({ t, fade }: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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
