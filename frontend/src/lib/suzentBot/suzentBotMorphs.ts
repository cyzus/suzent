/**
 * Geometric Morph Renderers for the Suzent Bot Engine:
 * `dots`, `orbit`, `radar`, `progress`, `gather`, `wave`, `send`, `receive`, `pencil`, `bang`.
 */

import {
  ALERT_GLYPH,
  CIRCLE_PATH,
  HEAD_C,
  PENCIL_GLYPH,
  Point2D,
  clamp,
} from './suzentBotGeometry';
import { backOut, cubicInOut, cubicOut, random } from './suzentBotPhysics';
import { SuzentMorphId } from './suzentBotActs';

export const MORPH_SIZES: Record<Exclude<SuzentMorphId, 'none'>, number> = {
  dots: 42,
  orbit: 40,
  radar: 40,
  progress: 40,
  gather: 40,
  wave: 32,
  send: 40,
  receive: 42,
  pencil: 36,
  bang: 34,
};

export const MORPH_EFFECT_IDS = Object.keys(MORPH_SIZES) as Array<Exclude<SuzentMorphId, 'none'>>;

export interface MorphLayer {
  group: SVGGElement | null;
  heads: SVGPathElement[];
  rings: SVGCircleElement[];
  parts: SVGCircleElement[];
  glyphs: SVGPathElement[];
}

export interface MorphRenderState {
  stageStartedAt: number;
  morphStartedAt: number;
  morphShotStartedAt: number;
  receiveCycle: number;
  receiveAngle: number;
  writingTrail: Point2D[];
  reducedMotion: boolean;
}

export function renderDotsMorph(
  layer: MorphLayer,
  amount: number,
  now: number,
  state: MorphRenderState
): void {
  const anchors = [HEAD_C - 98, HEAD_C + 98];
  for (let i = 0; i < 2; i += 1) {
    const el = layer.heads[i];
    const phase = clamp((amount - 0.12 * i) / (1 - 0.12 * i), 0, 1);
    if (phase <= 0.004) continue;
    const grow = cubicOut(phase);
    const enter = backOut(phase);
    const pulseDist = Math.abs(
      (((((now - state.morphStartedAt) / 1400 + 0.119) % 1) + 1) % 1) - (i * 2) / 3
    );
    const dist = Math.min(pulseDist, 1 - pulseDist);
    const pulse = state.reducedMotion ? 1 : Math.exp(-(dist ** 2) / 0.045);
    const lift = state.reducedMotion ? 0 : 9 * pulse * amount;
    const pop = state.reducedMotion ? 1 : 0.84 + 0.22 * pulse;
    const scale = ((42 * grow * pop) / HEAD_C) * 1.02;
    el.style.display = '';
    el.setAttribute('d', CIRCLE_PATH);
    el.setAttribute(
      'transform',
      `translate(${(HEAD_C + (anchors[i] - HEAD_C) * enter).toFixed(1)} ${(HEAD_C - lift).toFixed(1)}) scale(${scale.toFixed(4)}) translate(${-HEAD_C} ${-HEAD_C})`
    );
    el.setAttribute('opacity', (grow * (1 - 0.5 * (1 - pulse))).toFixed(3));
  }
}

export function renderOrbitMorph(layer: MorphLayer, amount: number, now: number): void {
  const radius = 104 * backOut(amount);
  for (let i = 0; i < 5; i += 1) {
    const el = layer.parts[i];
    const phase = 0.0017 * now + (i * Math.PI * 2) / 5;
    const cosine = Math.cos(phase);
    const depth = 0.65 + 0.35 * clamp(cosine, 0, 1);
    el.style.display = '';
    el.setAttribute('cx', (HEAD_C + radius * Math.sin(phase)).toFixed(1));
    el.setAttribute('cy', (HEAD_C - 0.44 * radius * Math.cos(phase)).toFixed(1));
    el.setAttribute('r', Math.max(26 * depth * cubicOut(amount), 0.5).toFixed(2));
    el.setAttribute(
      'opacity',
      (clamp((cosine + 0.4) / 0.6, 0.28, 1) * cubicOut(amount)).toFixed(3)
    );
  }
}

export function renderRadarMorph(
  layer: MorphLayer,
  amount: number,
  now: number,
  baseRadius: number
): void {
  for (let i = 0; i < 3; i += 1) {
    const el = layer.rings[i];
    const phase = (((now / 1300 + i / 3) % 1) + 1) % 1;
    el.style.display = '';
    el.setAttribute('fill', 'none');
    el.setAttribute('stroke', 'var(--fg)');
    el.setAttribute('r', (baseRadius + (116 - baseRadius) * phase).toFixed(1));
    el.setAttribute('stroke-width', (8.5 * (1 - 0.45 * phase)).toFixed(2));
    el.setAttribute('opacity', (cubicOut(amount) * (1 - phase) * 0.9).toFixed(3));
  }
}

export function renderProgressMorph(
  layer: MorphLayer,
  amount: number,
  now: number,
  state: MorphRenderState
): void {
  const radius = 76 * backOut(amount);
  const track = layer.rings[3];
  const value = layer.rings[4];
  track.style.display = '';
  track.setAttribute('fill', 'none');
  track.setAttribute('stroke', 'var(--fg)');
  track.setAttribute('r', radius.toFixed(1));
  track.setAttribute('stroke-width', '8.5');
  track.setAttribute('opacity', (0.18 * cubicOut(amount)).toFixed(3));
  const progress = clamp((now - state.morphShotStartedAt) / 2500 / 0.85, 0, 1);
  const circ = 2 * Math.PI * radius;
  value.style.display = '';
  value.setAttribute('fill', 'none');
  value.setAttribute('stroke', 'var(--fg)');
  value.setAttribute('r', radius.toFixed(1));
  value.setAttribute('stroke-width', '9.5');
  value.setAttribute('stroke-dasharray', circ.toFixed(1));
  value.setAttribute('stroke-dashoffset', (circ * (1 - progress)).toFixed(1));
  value.setAttribute('transform', `rotate(-90 ${HEAD_C} ${HEAD_C})`);
  value.setAttribute('opacity', cubicOut(amount).toFixed(3));
}

export function renderGatherMorph(
  layer: MorphLayer,
  amount: number,
  now: number,
  state: MorphRenderState
): void {
  for (let i = 0; i < 5; i += 1) {
    const el = layer.parts[i];
    const phase = clamp(((now - state.morphShotStartedAt) / 2000 - 0.09 * i) / 0.62, 0, 1);
    if (phase >= 1) continue;
    const settle = 1 - (1 - phase) ** 3;
    const angle = 2.4 * i + 2.2 * phase;
    const radius = 112 * (1 - settle);
    el.style.display = '';
    el.setAttribute('cx', (HEAD_C + radius * Math.cos(angle)).toFixed(1));
    el.setAttribute('cy', (HEAD_C + radius * Math.sin(angle) * 0.8).toFixed(1));
    el.setAttribute('r', (18.5 * (0.7 + 0.3 * settle) * cubicOut(amount)).toFixed(2));
    el.setAttribute(
      'opacity',
      (cubicOut(amount) * clamp(5 * phase, 0, 1) * (1 - 0.2 * settle)).toFixed(3)
    );
  }
}

export function renderWaveMorph(layer: MorphLayer, amount: number, now: number): void {
  const offsets = [-2, -1, 1, 2];
  for (let i = 0; i < 4; i += 1) {
    const el = i < 2 ? layer.heads[i] : layer.parts[i - 2];
    const offset = offsets[i];
    const phase = clamp((amount - 0.1 * Math.abs(offset)) / (1 - 0.1 * Math.abs(offset)), 0, 1);
    if (phase <= 0.004) continue;
    const energy =
      (0.42 +
        0.29 * Math.sin(0.0021 * now) * Math.sin(0.0034 * now) +
        0.29 * Math.sin(0.0013 * now + 1.7)) *
      (0.55 + 0.45 * Math.sin(0.012 * now - 1.05 * Math.abs(offset)));
    const size = (14.5 + 10.5 * clamp(energy, 0.08, 1)) * cubicOut(phase);
    const lift = 6 * clamp(energy, 0, 1) * phase;
    const spacing = 54;
    el.style.display = '';
    if (i < 2) {
      const scale = (size / HEAD_C) * 1.02;
      el.setAttribute('d', CIRCLE_PATH);
      el.setAttribute(
        'transform',
        `translate(${(HEAD_C + spacing * offset * backOut(phase)).toFixed(1)} ${(HEAD_C - lift).toFixed(1)}) scale(${scale.toFixed(4)}) translate(${-HEAD_C} ${-HEAD_C})`
      );
    } else {
      el.setAttribute('cx', (HEAD_C + spacing * offset * backOut(phase)).toFixed(1));
      el.setAttribute('cy', (HEAD_C - lift).toFixed(1));
      el.setAttribute('r', size.toFixed(2));
    }
    el.setAttribute('opacity', phase.toFixed(3));
  }
}

export function renderSendMorph(
  layer: MorphLayer,
  amount: number,
  now: number,
  state: MorphRenderState
): void {
  const phase = ((((now - state.stageStartedAt) / 1500) % 1) + 1) % 1;
  const travel = clamp((phase - 0.18) / 0.55, 0, 1);
  const eased = travel * travel * (0.4 + 0.6 * travel);
  const dist = 122 * eased;
  const first = layer.parts[0];
  if (travel > 0 && travel < 1) {
    first.style.display = '';
    first.setAttribute('cx', (HEAD_C + 0.74 * dist).toFixed(1));
    first.setAttribute('cy', (HEAD_C - 0.62 * dist).toFixed(1));
    first.setAttribute('r', (19 * (1 - 0.32 * eased) * cubicOut(amount)).toFixed(2));
    first.setAttribute('opacity', (cubicOut(amount) * (1 - eased * eased)).toFixed(3));
  }
  const secondTravel = clamp((phase - 0.26) / 0.55, 0, 1);
  const secondEase = secondTravel * secondTravel * (0.4 + 0.6 * secondTravel);
  const second = layer.parts[1];
  if (travel > 0 && secondTravel > 0 && secondTravel < 1) {
    const secondDist = 122 * secondEase;
    second.style.display = '';
    second.setAttribute('cx', (HEAD_C + 0.74 * secondDist).toFixed(1));
    second.setAttribute('cy', (HEAD_C - 0.62 * secondDist).toFixed(1));
    second.setAttribute('r', (13.5 * (1 - 0.32 * secondEase) * cubicOut(amount)).toFixed(2));
    second.setAttribute('opacity', (0.55 * cubicOut(amount) * (1 - secondEase)).toFixed(3));
  }
  const ringPhase = clamp((phase - 0.18) / 0.3, 0, 1);
  if (ringPhase > 0 && ringPhase < 1) {
    const ring = layer.rings[0];
    ring.style.display = '';
    ring.setAttribute('fill', 'none');
    ring.setAttribute('stroke', 'var(--fg)');
    ring.setAttribute('r', (24 + 38 * cubicOut(ringPhase)).toFixed(1));
    ring.setAttribute('stroke-width', (6.5 * (1 - ringPhase)).toFixed(2));
    ring.setAttribute('opacity', (cubicOut(amount) * (1 - ringPhase) * 0.85).toFixed(3));
  }
}

export function renderReceiveMorph(
  layer: MorphLayer,
  amount: number,
  now: number,
  state: MorphRenderState
): void {
  const elapsed = now - state.stageStartedAt;
  const cycle = Math.floor(elapsed / 1700);
  if (cycle !== state.receiveCycle) {
    state.receiveCycle = cycle;
    state.receiveAngle = random(-1.25 * Math.PI, 0.25 * Math.PI);
  }
  const phase = (((elapsed / 1700) % 1) + 1) % 1;
  const travel = clamp(phase / 0.6, 0, 1);
  const eased = 1 - (1 - travel) ** 3;
  const radius = 122 * (1 - eased);
  const orbit = 18 * Math.sin(travel * Math.PI) * (1 - 0.7 * eased);
  const cosine = Math.cos(state.receiveAngle);
  const sine = Math.sin(state.receiveAngle);
  const part = layer.parts[0];
  if (travel < 1) {
    part.style.display = '';
    part.setAttribute('cx', (HEAD_C + cosine * radius - sine * orbit).toFixed(1));
    part.setAttribute('cy', (HEAD_C + sine * radius + cosine * orbit).toFixed(1));
    part.setAttribute('r', (13 + 8 * eased).toFixed(2));
    part.setAttribute(
      'opacity',
      (cubicOut(amount) * clamp(3.5 * travel, 0, 1) * (0.45 + 0.55 * eased)).toFixed(3)
    );
  }
  const ringPhase = clamp((phase - 0.58) / 0.32, 0, 1);
  if (ringPhase > 0 && ringPhase < 1) {
    const ring = layer.rings[1];
    ring.style.display = '';
    ring.setAttribute('fill', 'none');
    ring.setAttribute('stroke', 'var(--fg)');
    ring.setAttribute('r', (24 + 30 * cubicOut(ringPhase)).toFixed(1));
    ring.setAttribute('stroke-width', (6.5 * (1 - ringPhase)).toFixed(2));
    ring.setAttribute('opacity', (cubicOut(amount) * (1 - ringPhase) * 0.85).toFixed(3));
  }
}

function pencilPose(now: number, state: MorphRenderState) {
  const elapsed = Math.max(0, now - (state.morphStartedAt || state.stageStartedAt) - 180);
  const cycle = (((elapsed / 2200) % 1) + 1) % 1;
  if (cycle < 0.72) {
    const phase = cycle / 0.72;
    const env = clamp(phase / 0.06, 0, 1) * clamp((1 - phase) / 0.08, 0, 1);
    const wave = (5.5 * Math.sin(26 * phase) + 2.5 * Math.cos(13 * phase)) * env;
    return {
      x: -68 + phase * 136,
      y: 34,
      wiggle: wave,
      rotation: 17 + 4 * Math.cos(26 * phase) * env,
      lift: false,
      phase,
    };
  }
  const phase = cubicInOut((cycle - 0.72) / 0.28);
  return {
    x: 68 - 136 * phase,
    y: 34 - 28 * Math.sin(phase * Math.PI),
    wiggle: 0,
    rotation: 17 - 6 * Math.sin(phase * Math.PI),
    lift: true,
    phase,
  };
}

export function renderPencilMorph(
  layer: MorphLayer,
  amount: number,
  now: number,
  state: MorphRenderState
) {
  const pose = pencilPose(now, state);
  const glyph = layer.glyphs[0];
  const angle = ((pose.rotation - 90) * Math.PI) / 180;
  const offsetX = 68 * Math.cos(angle);
  const offsetY = 68 * Math.sin(angle);
  glyph.style.display = '';
  glyph.setAttribute('d', PENCIL_GLYPH);
  glyph.setAttribute('fill', 'var(--fg)');
  glyph.setAttribute(
    'transform',
    `translate(${(HEAD_C + (pose.x + offsetX) * amount).toFixed(1)} ${(HEAD_C + (pose.y + 0.15 * pose.wiggle + offsetY) * amount).toFixed(1)}) rotate(${(pose.rotation * amount).toFixed(1)}) scale(${cubicOut(amount).toFixed(3)}) translate(${-HEAD_C} ${-HEAD_C})`
  );
  glyph.setAttribute('opacity', clamp(1.6 * amount - 0.3, 0, 1).toFixed(3));

  if (amount > 0.35 && !pose.lift) {
    if (pose.phase < 0.03 && state.writingTrail.length > 8) {
      state.writingTrail = [];
    }
    const nibX = HEAD_C + pose.x * amount;
    const nibY = HEAD_C + (pose.y + 0.5 * pose.wiggle) * amount + 26 * amount;
    const pt: Point2D = [nibX, nibY];
    const last = state.writingTrail[state.writingTrail.length - 1];
    const dist = last ? Math.hypot(pt[0] - last[0], pt[1] - last[1]) : 0;
    if (dist > 28) {
      state.writingTrail = [pt];
    } else if (!last || dist > 0.35) {
      state.writingTrail.push(pt);
      if (state.writingTrail.length > 140) state.writingTrail.shift();
    } else {
      last[0] = pt[0];
      last[1] = pt[1];
    }
  } else if (pose.lift) {
    state.writingTrail = [];
  } else if (state.writingTrail.length) {
    state.writingTrail.splice(0, Math.max(2, Math.ceil(state.writingTrail.length * 0.16)));
  }

  const trail = layer.glyphs[1];
  if (state.writingTrail.length >= 2) {
    const pts = state.writingTrail;
    let path = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
    if (pts.length === 2) {
      path += `L${pts[1][0].toFixed(1)} ${pts[1][1].toFixed(1)}`;
    } else {
      for (let i = 0; i < pts.length - 1; i += 1) {
        const prev = pts[Math.max(i - 1, 0)];
        const curr = pts[i];
        const next = pts[i + 1];
        const after = pts[Math.min(i + 2, pts.length - 1)];
        const c1x = curr[0] + (next[0] - prev[0]) / 6;
        const c1y = curr[1] + (next[1] - prev[1]) / 6;
        const c2x = next[0] - (after[0] - curr[0]) / 6;
        const c2y = next[1] - (after[1] - curr[1]) / 6;
        path += `C${c1x.toFixed(1)} ${c1y.toFixed(1)} ${c2x.toFixed(1)} ${c2y.toFixed(1)} ${next[0].toFixed(1)} ${next[1].toFixed(1)}`;
      }
    }
    trail.style.display = '';
    trail.setAttribute('fill', 'none');
    trail.setAttribute('stroke', 'var(--fg)');
    trail.setAttribute('stroke-width', '10');
    trail.setAttribute('stroke-linecap', 'round');
    trail.setAttribute('stroke-linejoin', 'round');
    trail.setAttribute('d', path);
    trail.setAttribute('opacity', clamp(1.2 * amount, 0, 1).toFixed(3));
  }
  return { x: pose.x, y: pose.y + 0.5 * pose.wiggle, rotation: pose.rotation };
}

export function renderBangMorph(
  layer: MorphLayer,
  amount: number,
  now: number,
  state: MorphRenderState
): void {
  const glyph = layer.glyphs[2];
  const elapsed = (now - state.stageStartedAt) / 1000;
  const enter = cubicOut(clamp(1.1 * amount, 0, 1));
  const shake = 2.2 * Math.sin(42 * elapsed) * Math.exp(-((elapsed % 2.2) * 5.5));
  glyph.style.display = '';
  glyph.setAttribute('d', ALERT_GLYPH);
  glyph.setAttribute('fill', 'var(--fg)');
  glyph.setAttribute(
    'transform',
    `translate(0 ${(-26 - (1 - enter) * 70).toFixed(1)}) rotate(${shake.toFixed(2)} ${HEAD_C} ${(HEAD_C - 74).toFixed(1)}) translate(${HEAD_C} ${HEAD_C}) scale(${clamp(1.2 * amount, 0, 1).toFixed(3)}) translate(${-HEAD_C} ${-HEAD_C})`
  );
  glyph.setAttribute('opacity', clamp(1.5 * amount - 0.2, 0, 1).toFixed(3));
}
