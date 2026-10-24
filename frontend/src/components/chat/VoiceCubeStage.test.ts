import { describe, expect, it } from 'vitest';
import { buildVoxelShell, idlePose, stepVoxelShell } from '../../lib/voice/voiceCubeSim';

describe('VoiceCubeStage Liquid-Geo simulation', () => {
  it('builds the 24^3 surface shell (24^3 - 22^3 = 3176 voxels) with unit radial vectors', () => {
    const vox = buildVoxelShell();
    expect(vox.length).toBe(24 ** 3 - 22 ** 3);
    for (const v of vox) {
      const len = Math.hypot(v.rx, v.ry, v.rz);
      expect(len).toBeCloseTo(1, 5);
    }
  });

  it('cycles smoothly through the 8s GreetingCube idle keyframes', () => {
    expect(idlePose(0)).toEqual([0, 0, -1]);
    expect(idlePose(8)).toEqual([0, 0, -1]);
    const mid = idlePose(2.56);
    expect(mid[0]).toBeCloseTo(-4, 2);
    expect(mid[1]).toBeCloseTo(14, 2);
  });

  it('lights the 1-voxel razor scan slices when working (Option 1)', () => {
    const vox = buildVoxelShell();
    const out = new Float32Array((1 + vox.length) * 7);
    const t = 1.25;
    const scanIdxJ = Math.floor(t * 10) % 24;
    const scanIdxI = Math.floor(t * 8 + 7) % 24;

    stepVoxelShell(
      vox,
      {
        status: 'listening',
        working: true,
        userLevel: 0,
        agentLevel: 0,
        dark: false,
        t,
        dt: 0,
      },
      out,
      7
    );

    const onSlice = vox.filter((v) => v.j === scanIdxJ || v.i === scanIdxI);
    const offSlice = vox.filter((v) => v.j !== scanIdxJ && v.i !== scanIdxI);
    expect(onSlice.every((v) => v.d > 0.6 && v.glow >= 0.879)).toBe(true);
    expect(offSlice.every((v) => v.d === 0)).toBe(true);
  });

  it('forms roaming ferrofluid clusters in thinking (C2) and spherical harmonic lobes in speaking (C3)', () => {
    const vox = buildVoxelShell();
    const out = new Float32Array((1 + vox.length) * 7);

    stepVoxelShell(
      vox,
      {
        status: 'thinking',
        working: false,
        userLevel: 0,
        agentLevel: 0,
        dark: false,
        t: 2.1,
        dt: 0,
      },
      out,
      7
    );
    const maxThinkD = Math.max(...vox.map((v) => v.d));
    expect(maxThinkD).toBeGreaterThan(1.2);

    stepVoxelShell(
      vox,
      {
        status: 'speaking',
        working: false,
        userLevel: 0,
        agentLevel: 0.9,
        dark: false,
        t: 1.7,
        dt: 0,
      },
      out,
      7
    );
    const maxSpeakD = Math.max(...vox.map((v) => v.d));
    const minSpeakD = Math.min(...vox.map((v) => v.d));
    // C3 has both positive harmonic lobes and negative concave indentations
    expect(maxSpeakD).toBeGreaterThan(2.0);
    expect(minSpeakD).toBeLessThan(-0.3);
  });

  it('extrudes jagged ferrofluid thorns on high-hash voxels in error state (Option 4)', () => {
    const vox = buildVoxelShell();
    const out = new Float32Array((1 + vox.length) * 7);

    stepVoxelShell(
      vox,
      {
        status: 'error',
        working: false,
        userLevel: 0,
        agentLevel: 0,
        dark: false,
        t: 0.8,
        dt: 0,
      },
      out,
      7
    );

    const spikes = vox.filter((v) => v.sparkHash > 0.86);
    const recessed = vox.filter((v) => v.sparkHash <= 0.86);
    expect(spikes.every((v) => v.d > 0.4)).toBe(true);
    expect(recessed.every((v) => v.d < -0.8)).toBe(true);
  });
});
