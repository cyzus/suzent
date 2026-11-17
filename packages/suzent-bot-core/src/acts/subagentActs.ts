import {
  HEAD_C,
  Point2D,
  SUZENT_BODY_PATH,
  SUZENT_BODY_RING,
  clamp,
} from "../suzentBotGeometry";
import {
  ActEvalContext,
  FullBodyActPose,
  createDefaultActPose,
} from "./actTypes";

/**
 * Compute a 96-point organic cell-division (peanut / figure-8) contour as `pinch` goes 0 -> 1.
 */
export function buildMitosisPinchRing(
  baseRing: readonly Point2D[],
  pinch: number,
  stretchX: number,
): Point2D[] {
  return baseRing.map(([x, y]) => {
    const dx = x - HEAD_C;
    const dy = y - HEAD_C;
    const nx = dx / 114.22;
    const waist = Math.exp(-(nx * nx) / 0.14);
    const lobeBulge = 1 + 0.16 * pinch * (1 - waist);
    const sy = Math.max(0.14, 1 - 0.82 * pinch * waist) * lobeBulge;
    const sx = stretchX + 0.18 * pinch * Math.sign(dx) * Math.abs(nx);
    return [HEAD_C + dx * sx, HEAD_C + dy * sy];
  });
}

/** A1: 3D tilted planetary ring + 3 monochrome satellite nodes orbiting with front/back depth occlusion */
export function evalConstellationCommand({
  t,
  fade,
}: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
  const floatWave = Math.sin(t * 2.4);
  pose.y = -10 * floatWave;
  pose.rot = 5 * Math.sin(t * 1.2);
  pose.sx = 1 + 0.03 * floatWave;
  pose.sy = 1 - 0.03 * floatWave;

  const tiltRad = 0.36;
  const rollDeg = -16 + 6 * Math.sin(t * 0.8);
  const orbitRx = 144;
  const orbitRy = orbitRx * Math.sin(tiltRad);

  let backNodes = `<path d="M ${HEAD_C - orbitRx} ${HEAD_C} A ${orbitRx} ${orbitRy.toFixed(1)} 0 0 1 ${HEAD_C + orbitRx} ${HEAD_C}" fill="none" stroke="var(--fg)" stroke-width="5" opacity="${(0.28 * fade).toFixed(2)}" />`;
  let frontNodes = `<path d="M ${HEAD_C - orbitRx} ${HEAD_C} A ${orbitRx} ${orbitRy.toFixed(1)} 0 0 0 ${HEAD_C + orbitRx} ${HEAD_C}" fill="none" stroke="var(--fg)" stroke-width="6.5" opacity="${(0.65 * fade).toFixed(2)}" />`;

  for (let i = 0; i < 3; i++) {
    const a = t * 2.5 + (i * Math.PI * 2) / 3;
    const sx = HEAD_C + orbitRx * Math.cos(a);
    const sy = HEAD_C + orbitRy * Math.sin(a);
    const z = Math.sin(a);
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

/** A2: True organic mitosis figure-8/peanut spline morph -> clean snap into two fully separated twin bots -> fusion */
export function evalAgentTwinSplit({
  t,
  fade,
}: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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

  const bodyScale = 1 - 0.46 * split;
  const offset = split > 0 ? 34 + 44 * split : 0;
  pose.x = -offset;
  pose.y = bob;
  pose.sx = bodyScale * (split > 0 ? stretchX : 1);
  pose.sy = bodyScale * stretchY;
  pose.rot = -10 * split + (split > 0.5 ? Math.sin(t * 10) * 5 : 0);
  pose.gazeX = split > 0.2 ? 14 : 0;

  if (pinch > 0.22 && split <= 0.02) {
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
    const strandOp = split < 0.55 ? (1 - split / 0.55) * fade : 0;
    const strandHalf = 18 + 26 * split;
    const strandSvg =
      strandOp > 0.04
        ? `<path d="M ${(HEAD_C - strandHalf).toFixed(1)} ${(HEAD_C - 10 * (1 - split)).toFixed(1)} Q ${HEAD_C} ${HEAD_C} ${(HEAD_C + strandHalf).toFixed(1)} ${(HEAD_C - 10 * (1 - split)).toFixed(1)} M ${(HEAD_C - strandHalf).toFixed(1)} ${(HEAD_C + 10 * (1 - split)).toFixed(1)} Q ${HEAD_C} ${HEAD_C} ${(HEAD_C + strandHalf).toFixed(1)} ${(HEAD_C + 10 * (1 - split)).toFixed(1)}" fill="none" stroke="var(--fg)" stroke-width="${(12 * (1 - split / 0.55)).toFixed(1)}" stroke-linecap="round" opacity="${strandOp.toFixed(2)}" />`
        : "";
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

/** A3: Portal summoning mini-bot rising from a ground portal ring on the right */
export function evalAgentPortalSpawn({
  t,
  fade,
}: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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

/** A4: Commander megaphone rally call */
export function evalAgentMegaphoneRally({
  t,
  fade,
}: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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

/** A5: Telepathic antenna dispatch to mini-agent */
export function evalAgentAntennaDispatch({
  t,
  fade,
  headPose,
}: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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

/** A6: Tandem 3-bot squad formation hopping together */
export function evalAgentSquadMarch({
  t,
  fade,
}: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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
