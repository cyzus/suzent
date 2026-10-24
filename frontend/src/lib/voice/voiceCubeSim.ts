import type { VoiceSessionStatus } from '../../hooks/useVoiceSession';

export const CUBE_GRID = 24;
export const VOXEL_UNIT = 1 / CUBE_GRID;

export interface VoxelCell {
  i: number;
  j: number;
  k: number;
  row: number;
  front: boolean;
  top: boolean;
  bot: boolean;
  right: boolean;
  left: boolean;
  px: number;
  py: number;
  pz: number;
  r0: number;
  rx: number;
  ry: number;
  rz: number;
  baseL: number;
  sparkHash: number;
  d: number;
  glow: number;
}

const DROPS = [
  { x: -0.18, y: -0.12, z: 0.5, rate: 0.78, phase: 0.08 },
  { x: 0.18, y: -0.18, z: 0.5, rate: 0.7, phase: 0.46 },
  { x: 0.02, y: 0.18, z: 0.5, rate: 0.84, phase: 0.78 },
  { x: -0.06, y: 0.5, z: 0.06, rate: 0.74, phase: 0.24 },
  { x: 0.5, y: 0.02, z: 0.08, rate: 0.68, phase: 0.62 },
  { x: -0.5, y: 0.04, z: 0.12, rate: 0.8, phase: 0.91 },
];

const IDLE_KEYFRAMES: [number, number, number, number][] = [
  [0, 0, 0, -1],
  [0.32, -4, 14, 1],
  [0.66, 4, 6, 0],
  [1, 0, 0, -1],
];

const ease = (x: number) => x * x * (3 - 2 * x);

export function idlePose(t: number): [number, number, number] {
  const p = (t % 8) / 8;
  let a = IDLE_KEYFRAMES[0];
  let b = IDLE_KEYFRAMES[1];
  for (let i = 0; i < 3; i += 1) {
    if (p >= IDLE_KEYFRAMES[i][0] && p <= IDLE_KEYFRAMES[i + 1][0]) {
      a = IDLE_KEYFRAMES[i];
      b = IDLE_KEYFRAMES[i + 1];
    }
  }
  const f = ease((p - a[0]) / (b[0] - a[0]));
  return [a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f, a[3] + (b[3] - a[3]) * f];
}

export function syllableEnvelope(t: number, seed: number): number {
  const a = 0.5 + 0.5 * Math.sin(t * 2 * Math.PI * (3.2 + seed * 0.7));
  const b = 0.5 + 0.5 * Math.sin(t * 2.0 + seed * 5);
  return Math.min(1, 0.45 + 0.55 * a ** 1.25 * (0.55 + 0.45 * b));
}

export function buildVoxelShell(): VoxelCell[] {
  const vox: VoxelCell[] = [];
  for (let i = 0; i < CUBE_GRID; i += 1) {
    for (let j = 0; j < CUBE_GRID; j += 1) {
      const row = CUBE_GRID - 1 - j;
      for (let k = 0; k < CUBE_GRID; k += 1) {
        const front = k === CUBE_GRID - 1;
        const back = k === 0;
        const top = j === CUBE_GRID - 1;
        const bot = j === 0;
        const right = i === CUBE_GRID - 1;
        const left = i === 0;
        if (!(front || back || top || bot || right || left)) continue;
        const px = (i + 0.5) * VOXEL_UNIT - 0.5;
        const py = (j + 0.5) * VOXEL_UNIT - 0.5;
        const pz = (k + 0.5) * VOXEL_UNIT - 0.5;
        const r0 = Math.hypot(px, py, pz);
        let baseL = 0.04;
        if (top) baseL = 0.28 + 0.22 * (k / (CUBE_GRID - 1)) + 0.12 * (i / (CUBE_GRID - 1));
        else if (right) baseL = 0.14 + 0.18 * (j / (CUBE_GRID - 1)) + 0.08 * (k / (CUBE_GRID - 1));
        else if (left) baseL = 0.08 + 0.13 * (j / (CUBE_GRID - 1)) + 0.06 * (k / (CUBE_GRID - 1));
        else if (front) baseL = 0.03 + 0.06 * (j / (CUBE_GRID - 1)) + 0.04 * (i / (CUBE_GRID - 1));
        const sparkHash = ((i * 73 + j * 151 + k * 283) & 255) / 255;
        vox.push({
          i,
          j,
          k,
          row,
          front,
          top,
          bot,
          right,
          left,
          px,
          py,
          pz,
          r0,
          rx: px / r0,
          ry: py / r0,
          rz: pz / r0,
          baseL,
          sparkHash,
          d: 0,
          glow: baseL,
        });
      }
    }
  }
  return vox;
}

export interface StepInput {
  status: VoiceSessionStatus;
  working: boolean;
  userLevel: number;
  agentLevel: number;
  dark: boolean;
  t: number;
  dt: number;
}

/**
 * Updates the 24³ Kryptonian Liquid-Geo voxel shell in-place and writes
 * instance attributes (posX, posY, posZ, scaleX, scaleY, scaleZ, lum) into `out`
 * starting at `offsetFloats`.
 */
export function stepVoxelShell(
  vox: VoxelCell[],
  input: StepInput,
  out: Float32Array,
  offsetFloats = 7
): void {
  const { status: st, working, userLevel: U, agentLevel: A, dark, t, dt } = input;
  const duck = U > 0.2 ? 0.35 : 1;
  const voiceOn = st === 'speaking';
  const spkAmp = voiceOn ? A * duck : 0;

  // Thinking (C2): 3 roaming magnetic ferrofluid attractors
  const c2Ax = 0.28 * Math.cos(t * 1.5);
  const c2Ay = 0.24 * Math.sin(t * 1.9);
  const c2Az = 0.5;
  const c2Bx = -0.22 * Math.sin(t * 1.3);
  const c2By = 0.5;
  const c2Bz = 0.22 * Math.cos(t * 1.7);
  const c2Cx = 0.5;
  const c2Cy = -0.18 * Math.cos(t * 1.6);
  const c2Cz = 0.24 * Math.sin(t * 1.4);

  // Working (Option 1): 1-voxel-thin razor scan slice indices
  const scanIdxJ = Math.floor(t * 10) % CUBE_GRID;
  const scanIdxI = Math.floor(t * 8 + 7) % CUBE_GRID;

  const kD = dt > 0 ? 0.28 : 1.0;
  const kG = dt > 0 ? 0.36 : 1.0;

  for (let n = 0; n < vox.length; n += 1) {
    const v = vox[n];
    let d = 0;
    let lum = dark ? v.baseL * 0.86 : v.baseL;

    // 1. CONNECTING: wake-up wave
    if (st === 'connecting') {
      const w = Math.max(0, Math.sin(v.py * 8.0 - t * 6.0)) ** 2;
      d += w * 0.85;
      lum += w * 0.28;
    }

    // 2. USER SPEAKING: Medium concentric water ripples (R = 0.78)
    if (U > 0.02) {
      let crest = 0;
      let trough = 0;
      for (let m = 0; m < DROPS.length; m += 1) {
        const dr = DROPS[m];
        const age = (t * dr.rate + dr.phase) % 1.0;
        const R = age * 0.78;
        const dist = Math.hypot(v.px - dr.x, v.py - dr.y, v.pz - dr.z);
        const fade = (1 - age * 0.7) * Math.min(1, age * 8.5);
        const d1 = (dist - R) / 0.04;
        const d2 = (dist - (R - 0.15)) / 0.042;
        const dtrough = (dist - (R - 0.075)) / 0.036;
        const r1 = Math.exp(-d1 * d1) * fade;
        const r2 = R > 0.16 ? Math.exp(-d2 * d2) * 0.65 * fade : 0;
        const tr = R > 0.09 ? Math.exp(-dtrough * dtrough) * 0.6 * fade : 0;
        crest += r1 + r2;
        trough += tr;
      }
      d += (crest - trough) * U * 1.48;
      if (crest > 0.06) lum = Math.min(0.9, lum + crest * U * 0.48);
      if (trough > 0.1) lum = Math.max(0.02, lum - trough * U * 0.16);
    }

    // 3. THINKING (C2): Roaming magnetic ferrofluid clusters
    if (st === 'thinking') {
      const dA = Math.hypot(v.px - c2Ax, v.py - c2Ay, v.pz - c2Az);
      const dB = Math.hypot(v.px - c2Bx, v.py - c2By, v.pz - c2Bz);
      const dC = Math.hypot(v.px - c2Cx, v.py - c2Cy, v.pz - c2Cz);
      const blob =
        Math.exp(-dA * dA * 22.0) + Math.exp(-dB * dB * 22.0) + Math.exp(-dC * dC * 22.0);
      const minD = Math.min(dA, dB, dC);
      const ring = Math.max(0, Math.sin(minD * 28.0 - t * 5.5)) * Math.min(1, blob * 1.4);
      d += blob * 1.85 + ring * 0.55;
      lum = Math.min(0.88, lum + blob * 0.48 + ring * 0.18);
    }

    // 4. SPEAKING (C3): 3D Spherical Harmonic Force-Field Sculpture
    if (spkAmp > 0.01) {
      const nx = v.rx;
      const ny = v.ry;
      const nz = v.rz;
      const y32 = nx * ny * nz * 3.6;
      const y40 = (35 * ny ** 4 - 30 * ny ** 2 + 3) * 0.18;
      const y22 = (nx * nx - nz * nz) * 1.35;
      const field =
        Math.sin(t * 4.8) * y22 + Math.cos(t * 3.9) * y32 + Math.sin(t * 5.7 + 1.2) * y40;
      const lobe = Math.max(0, field) ** 1.35 * spkAmp;
      const indent = Math.min(0, field) * 0.65 * spkAmp;
      d += lobe * 5.4 + indent * 2.2;
      if (field > 0.08) lum = Math.min(0.92, lum + lobe ** 0.9 * 0.72);
      else lum *= Math.max(0.25, 1.0 + field * 0.55);
    }

    // 5. WORKING (Option 1): Strictly 1-voxel-thin orthogonal razor scan slice
    if (working && st !== 'error') {
      if (v.j === scanIdxJ || v.i === scanIdxI) {
        d += 0.65;
        lum = Math.max(lum, 0.88);
      }
    }

    // 6. ERROR (Option 4): Core Instability / Jagged Ferrofluid Thorns
    if (st === 'error') {
      if (v.sparkHash > 0.86) {
        const spike = (0.55 + 0.45 * Math.sin(t * 22 + v.sparkHash * 40)) * 5.2;
        d += spike;
        lum = spike > 3.2 ? 0.92 : 0.62;
      } else {
        d -= 0.9;
        lum *= 0.35;
      }
    }

    v.d += (d - v.d) * kD;
    v.glow += (lum - v.glow) * kG;

    // Seamless Kryptonian Pin Extrusion:
    // At rest (|d| ~ 0), tangential scale is flush (1.005) so there are zero sub-pixel Moire lines;
    // when pins extrude, tangential scale tapers to 0.95 * tipFactor for crisp pin relief.
    const dPos = Math.max(0, v.d);
    const activity = Math.min(1, Math.abs(v.d) * 1.5);
    const fillRatio = 1.005 * (1 - activity) + 0.95 * activity;
    const tipFactor = 1 + (v.d * VOXEL_UNIT) / v.r0;
    const centerFactor = 1 + ((v.d - dPos * 0.38) * VOXEL_UNIT) / v.r0;
    const sTan = fillRatio * Math.max(0.86, tipFactor) * VOXEL_UNIT;
    const sCol = (fillRatio * Math.max(0.86, tipFactor) + dPos * 0.78) * VOXEL_UNIT;

    const base = offsetFloats + n * 7;
    out[base] = v.px * centerFactor;
    out[base + 1] = v.py * centerFactor;
    out[base + 2] = v.pz * centerFactor;
    if (v.top || v.bot) {
      out[base + 3] = sTan;
      out[base + 4] = sCol;
      out[base + 5] = sTan;
    } else if (v.right || v.left) {
      out[base + 3] = sCol;
      out[base + 4] = sTan;
      out[base + 5] = sTan;
    } else {
      out[base + 3] = sTan;
      out[base + 4] = sTan;
      out[base + 5] = sCol;
    }
    // Dynamic energy above baseL (passed to shader so per-face normal shading stays crisp on edges!)
    const boost = Math.max(0, v.glow - (dark ? v.baseL * 0.86 : v.baseL));
    out[base + 6] = Math.min(0.92, boost);
  }
}
