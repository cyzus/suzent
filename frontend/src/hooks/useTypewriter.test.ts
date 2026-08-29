import { describe, expect, it } from 'vitest';
import { createRevealClock, getRevealStep } from './useTypewriter';

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

describe('getRevealStep under load', () => {
  /** Backlog the reveal settles at when frames take `frameMs` and text keeps arriving. */
  function steadyStateBacklogAt(charsPerSecond: number, frameMs: number): number {
    let remaining = 0;
    for (let frame = 0; frame < 600; frame += 1) {
      remaining += (charsPerSecond * frameMs) / 1000;
      remaining = Math.max(0, remaining - getRevealStep(remaining, frameMs));
    }
    return remaining;
  }

  it('does not fall further behind when the tab renders slowly', () => {
    // 400 chars/sec is a fast turn. The lag must stay a fixed slice of time,
    // not grow with how long each frame takes — that coupling is what made a
    // busy tab display text a second or more behind what had arrived.
    const fast = steadyStateBacklogAt(400, 1000 / 60);
    const slow = steadyStateBacklogAt(400, 200);
    expect(fast).toBeLessThanOrEqual(60);
    expect(slow).toBeLessThanOrEqual(fast + 1);
  });

  it('shows everything at once after a long gap, e.g. a backgrounded tab', () => {
    expect(getRevealStep(900, 5000)).toBe(900);
  });
});

describe('createRevealClock', () => {
  it('charges a nominal frame for the first reveal of a batch', () => {
    const clock = createRevealClock();
    expect(clock.elapsed(12_345)).toBeCloseTo(1000 / 60);
  });

  it('measures real time between reveals within a batch', () => {
    const clock = createRevealClock();
    clock.elapsed(1000);
    expect(clock.elapsed(1200)).toBe(200);
  });

  it('does not charge the wait for the next chunk to the animation', () => {
    // Gaps of several hundred ms between SSE chunks are ordinary. Counted as
    // reveal time they exceed CATCH_UP_MS, so getRevealStep would dump each
    // chunk whole the moment it arrived and nothing would ever be smoothed.
    const clock = createRevealClock();
    clock.elapsed(1000);
    clock.reset(); // backlog drained
    const backlog = 200;
    const step = getRevealStep(backlog, clock.elapsed(1500));
    expect(step).toBeLessThan(backlog);
  });
});
