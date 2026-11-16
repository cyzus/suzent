import { HEAD_C } from '../suzentBotGeometry';
import { ActEvalContext, FullBodyActPose, createDefaultActPose } from './actTypes';

/** R1: Holding open book & page flipping (`read_file`, `agent_read`) */
export function evalSpeedReader({ t, fade }: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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

/** R3: Bite-by-bite file chomp with scalloped bite marks & flying paper crumbs (`webpage_fetch`, `memory_search`, `session_search`) */
export function evalChompFile({ t, fade }: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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

/** R2: Floating dog-eared file card on the right + sightline scan */
export function evalFloatingDoc({ t, fade }: ActEvalContext): FullBodyActPose {
  const pose = createDefaultActPose();
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
