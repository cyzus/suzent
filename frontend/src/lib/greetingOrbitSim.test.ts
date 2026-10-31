import { describe, expect, it } from 'vitest';
import {
  ORBIT_RINGS,
  REST_SCALE,
  type OrbitState,
  buildOrbitFrame,
  createOrbitState,
  stepOrbits,
} from './greetingOrbitSim';

const DT = 1 / 60;
const AXES = ['comet', 'spin'] as const;

const run = (state: OrbitState, seconds: number, engaged: boolean, onFrame?: () => void) => {
  for (let t = 0; t < seconds; t += DT) {
    stepOrbits(state, engaged, DT);
    onFrame?.();
  }
};

describe('greetingOrbitSim', () => {
  it('ramps up over a few frames instead of jumping to full speed', () => {
    const state = createOrbitState();
    stepOrbits(state, true, DT);
    state.rings.forEach((ring, i) =>
      expect(ring.comet.speed - ORBIT_RINGS[i].comet).toBeLessThan(3)
    );

    run(state, 0.3, true);
    state.rings.forEach((ring, i) =>
      expect(ring.comet.speed).toBeGreaterThan(ORBIT_RINGS[i].comet + 6)
    );
  });

  it('never reverses any rotation through the kick and the coast down', () => {
    const state = createOrbitState();
    run(state, 6, true, () =>
      state.rings.forEach((ring, i) =>
        AXES.forEach((axis) =>
          expect(Math.sign(ring[axis].speed)).toBe(Math.sign(ORBIT_RINGS[i][axis]))
        )
      )
    );
  });

  it('coasts back to cruise speed on every axis', () => {
    const state = createOrbitState();
    run(state, 6, true);
    state.rings.forEach((ring, i) =>
      AXES.forEach((axis) => expect(ring[axis].speed).toBeCloseTo(ORBIT_RINGS[i][axis], 1))
    );
    expect(state.visible).toBeCloseTo(1, 2);
    expect(state.scale).toBeCloseTo(1, 2);
  });

  it('expands without overshooting past full size', () => {
    const state = createOrbitState();
    let peak = 0;
    run(state, 3, true, () => {
      peak = Math.max(peak, state.scale);
    });
    expect(peak).toBeLessThanOrEqual(1.001);
  });

  it('only kicks on the rising edge, not every engaged frame', () => {
    const state = createOrbitState();
    run(state, 6, true);
    const speeds = state.rings.map((ring) => ring.comet.speed);
    run(state, 0.5, true);
    state.rings.forEach((ring, i) => expect(ring.comet.speed).toBeCloseTo(speeds[i], 1));
  });

  it('fades out and shrinks back to rest when released', () => {
    const state = createOrbitState();
    run(state, 2, true);
    run(state, 4, false);
    expect(state.visible).toBeLessThan(0.002);
    expect(state.scale).toBeCloseTo(REST_SCALE, 2);
  });

  it('tumbles the rings about distinct axes so they never move in lockstep', () => {
    const axes = ORBIT_RINGS.map(({ axis }) => {
      const length = Math.hypot(...axis);
      return axis.map((c) => c / length);
    });
    for (let a = 0; a < axes.length; a += 1) {
      for (let b = a + 1; b < axes.length; b += 1) {
        const cosine = axes[a].reduce((sum, c, k) => sum + c * axes[b][k], 0);
        expect(Math.abs(cosine)).toBeLessThan(0.7);
      }
    }
  });

  it('splits every ring into a far half and a near half', () => {
    const frames = buildOrbitFrame(createOrbitState());
    expect(frames).toHaveLength(ORBIT_RINGS.length);
    frames.forEach((frame) => {
      expect(frame.back).toMatch(/^M/);
      expect(frame.front).toMatch(/^M/);
    });
  });
});
