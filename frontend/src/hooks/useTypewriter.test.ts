import { describe, expect, it } from 'vitest';
import { getRevealStep } from './useTypewriter';

/** Frames needed to reveal a backlog of `size` with no further text arriving. */
function framesToDrain(size: number): number {
  let remaining = size;
  let frames = 0;
  while (remaining > 0) {
    remaining -= getRevealStep(remaining);
    frames += 1;
  }
  return frames;
}

/**
 * Backlog the reveal settles at when text keeps arriving at a steady
 * `charsPerFrame`, i.e. how far behind the agent the reader ends up.
 */
function steadyStateBacklog(charsPerFrame: number): number {
  let remaining = 0;
  for (let frame = 0; frame < 600; frame += 1) {
    remaining += charsPerFrame;
    remaining = Math.max(0, remaining - getRevealStep(remaining));
  }
  return remaining;
}

describe('getRevealStep', () => {
  it('drains a burst in a handful of frames however large it is', () => {
    // The animation exists to hide uneven delivery, so a paragraph landing at
    // once must not turn into seconds of typing.
    expect(framesToDrain(40)).toBeLessThanOrEqual(20);
    expect(framesToDrain(400)).toBeLessThanOrEqual(30);
    expect(framesToDrain(2000)).toBeLessThanOrEqual(40);
  });

  it('keeps the reader close behind however fast the agent emits', () => {
    // ~60 fps, so 5 chars/frame is a brisk 300 chars/sec and 20 is far beyond
    // what any model sustains. Both must settle well under a second of lag.
    expect(steadyStateBacklog(2)).toBeLessThanOrEqual(20);
    expect(steadyStateBacklog(5)).toBeLessThanOrEqual(40);
    expect(steadyStateBacklog(20)).toBeLessThanOrEqual(140);
  });

  it('always advances, so a trickle never stalls', () => {
    expect(getRevealStep(1)).toBe(1);
    expect(getRevealStep(3)).toBeGreaterThanOrEqual(1);
  });
});
