import { HEAD_C } from "../suzentBotGeometry";
import {
  ActEvalContext,
  FullBodyActPose,
  createDefaultActPose,
} from "./actTypes";

/** S1: Sherlock large magnifying glass sweeping across the foreground */
export function evalBigLoupe({ t, fade }: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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

/** S2: Dual scout binoculars panning left & right */
export function evalBinoculars({
  t,
  fade,
  headPose,
}: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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

/** S3: Outward bright searchlight beam projecting to the right with an illuminated spotlight ellipse */
export function evalBrightBeam({ t, fade }: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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

/** S4: Hide-and-seek peeking left & right + concentric sonar pulses */
export function evalPeekRadar({ t, fade }: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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

  let rings = "";
  for (let i = 0; i < 2; i++) {
    const rp = (t * 0.9 + i * 0.5) % 1;
    const r = 118 + rp * 38;
    const op = (1 - rp) * 0.65 * fade;
    rings += `<circle cx="${(HEAD_C + px * 0.5).toFixed(1)}" cy="${(HEAD_C + py * 0.5).toFixed(1)}" r="${r.toFixed(1)}" fill="none" stroke="var(--fg)" stroke-width="${(6 * (1 - 0.4 * rp)).toFixed(1)}" opacity="${op.toFixed(2)}" />`;
  }
  pose.backHtml = rings;
  return pose;
}
