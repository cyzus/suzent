/**
 * 120Hz fixed-timestep damped harmonic oscillator springs & math utilities
 * for the Suzent Bot Engine.
 */

import { clamp } from './suzentBotGeometry';

export interface SpringState {
  x: number;
  v: number;
  target: number;
}

export const FIXED_STEP = 1 / 120;

export function springValue(initial = 0): SpringState {
  return { x: initial, v: 0, target: initial };
}

export function stepSpring(
  spring: SpringState,
  frequency: number,
  damping: number,
  delta: number
): void {
  spring.v +=
    (-2 * damping * frequency * spring.v - frequency ** 2 * (spring.x - spring.target)) * delta;
  spring.x += spring.v * delta;
  if (!Number.isFinite(spring.x) || !Number.isFinite(spring.v)) {
    spring.x = spring.target;
    spring.v = 0;
  }
}

export function random(min: number, max: number): number {
  return min + Math.random() * (max - min);
}

export function smoothstep(t: number): number {
  const x = clamp(t, 0, 1);
  return x * x * (3 - 2 * x);
}

export function cubicOut(t: number): number {
  const x = clamp(t, 0, 1);
  return 1 - (1 - x) ** 3;
}

export function cubicInOut(t: number): number {
  const x = clamp(t, 0, 1);
  return x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2;
}

export function backOut(t: number): number {
  const x = clamp(t, 0, 1);
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2;
}
