import { useState, useEffect, useRef } from 'react';

/**
 * Backlog past which the reveal gives up and jumps forward.
 *
 * The point of the animation is to hide the unevenness of delivery, not to
 * pace the agent. Once the buffer is this far ahead, catching up a few
 * characters at a time stops reading as typing and starts reading as lag.
 */
const MAX_ANIMATED_BACKLOG = 3000;

/**
 * Wall-clock time the reveal aims to take to drain whatever is queued.
 *
 * Draining a fixed *share* of the backlog rather than a fixed number of
 * characters is what keeps the lag bounded: the rate rises with the backlog,
 * so the display settles a constant moment behind however fast the agent
 * emits, and a burst still eases out instead of snapping.
 *
 * The share is taken per millisecond elapsed, not per frame. Frame-based
 * pacing quietly couples the reveal to how busy the tab is: a frame that takes
 * 200ms to render still advanced the text by one frame's worth, so under load
 * — long message, heavy tool output, background tab — the display fell a
 * second or more behind text that had already arrived, and stayed there.
 * Metered against the clock, a slow frame simply reveals proportionally more.
 */
const CATCH_UP_MS = 100;

/** Nominal frame at 60fps; the assumed gap when no elapsed time is supplied. */
const FRAME_MS = 1000 / 60;

/**
 * Characters to reveal given how far the buffer has run ahead and how long it
 * has been since the last reveal. A gap at or past CATCH_UP_MS reveals the
 * whole backlog: at that frame rate there is no smoothing left to do, and
 * showing what the agent has actually said beats animating stale text.
 */
export const getRevealStep = (remaining: number, elapsedMs: number = FRAME_MS): number =>
  Math.max(1, Math.ceil(remaining * Math.min(1, Math.max(0, elapsedMs) / CATCH_UP_MS)));

/**
 * The reveal's own clock, measuring time spent animating rather than time
 * passed.
 *
 * Waiting for the next chunk is not animation time. Left running across a
 * drained backlog, the clock would hand the first frame of the next chunk the
 * whole idle gap — and gaps between SSE chunks routinely exceed CATCH_UP_MS,
 * so every chunk would be dumped whole and nothing would ever be smoothed.
 * Callers reset it whenever the reveal has caught up, so the next batch starts
 * from a nominal frame.
 */
export function createRevealClock() {
  let lastRevealAt = 0;
  return {
    /** Milliseconds to charge this reveal, and marks it as just happened. */
    elapsed(now: number): number {
      const ms = lastRevealAt === 0 ? FRAME_MS : now - lastRevealAt;
      lastRevealAt = now;
      return ms;
    },
    /** The reveal is idle; the pause that follows is not animation time. */
    reset(): void {
      lastRevealAt = 0;
    },
  };
}

/**
 * Reveal appended text at a steady rate instead of in the bursts it arrives in.
 *
 * SSE hands over whatever accumulated since the last read — a few characters,
 * sometimes a whole paragraph — and the model emits unevenly on top of that, so
 * raw streaming lands in visible jerks. Keeping the rendered text a little
 * behind the buffer and closing the gap every frame reads as flowing text.
 *
 * Only growth after mount is animated. A component that mounts onto a turn
 * already in progress — switching back to a streaming chat, remounting after a
 * reconnect — shows what is already there rather than replaying it.
 */
export const useTypewriter = (text: string, isEnabled: boolean = true) => {
  const [displayedText, setDisplayedText] = useState(text);
  const indexRef = useRef(text.length);
  const prevTextRef = useRef(text);
  // Sizes each step by real elapsed time instead of assuming every frame is the
  // same length. Reset whenever the reveal catches up, so the wait for the next
  // chunk is not charged to the frame that starts revealing it.
  const clockRef = useRef<ReturnType<typeof createRevealClock> | null>(null);
  if (clockRef.current === null) clockRef.current = createRevealClock();
  const clock = clockRef.current;

  // Content replaced rather than appended to (a different message reusing this
  // node): adopt it whole. Rewinding to replay text the user has already read
  // is worse than showing it.
  useEffect(() => {
    if (prevTextRef.current !== '' && !text.startsWith(prevTextRef.current)) {
      indexRef.current = text.length;
      setDisplayedText(text);
    }
    prevTextRef.current = text;
  }, [text]);

  useEffect(() => {
    // Not animating, or the agent has run so far ahead that the reveal would
    // read as lag. Measured against the backlog, not the total length, so a
    // long answer keeps its smoothing all the way down.
    if (!isEnabled || text.length - indexRef.current > MAX_ANIMATED_BACKLOG) {
      indexRef.current = text.length;
      setDisplayedText(text);
      clock.reset();
      return;
    }

    if (indexRef.current >= text.length) {
      clock.reset();
      return;
    }

    let frameId = 0;

    const tick = () => {
      const remaining = text.length - indexRef.current;
      if (remaining <= 0) {
        // Caught up. The pause until the next chunk belongs to the stream, not
        // to the animation.
        clock.reset();
        frameId = 0;
        return;
      }
      indexRef.current += getRevealStep(remaining, clock.elapsed(performance.now()));
      setDisplayedText(text.slice(0, indexRef.current));
      frameId = window.requestAnimationFrame(tick);
    };

    frameId = window.requestAnimationFrame(tick);
    return () => {
      if (frameId) window.cancelAnimationFrame(frameId);
    };
  }, [text, isEnabled, clock]);

  return displayedText;
};
