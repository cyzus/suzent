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
  // When the last reveal happened, so each step can be sized by real elapsed
  // time instead of assuming every frame is the same length.
  const lastRevealAtRef = useRef(0);

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
      return;
    }

    if (indexRef.current >= text.length) return;

    let frameId = 0;

    const tick = () => {
      const remaining = text.length - indexRef.current;
      if (remaining <= 0) {
        frameId = 0;
        return;
      }
      const now = performance.now();
      const elapsed = lastRevealAtRef.current === 0 ? FRAME_MS : now - lastRevealAtRef.current;
      lastRevealAtRef.current = now;
      indexRef.current += getRevealStep(remaining, elapsed);
      setDisplayedText(text.slice(0, indexRef.current));
      frameId = window.requestAnimationFrame(tick);
    };

    frameId = window.requestAnimationFrame(tick);
    return () => {
      if (frameId) window.cancelAnimationFrame(frameId);
    };
  }, [text, isEnabled]);

  return displayedText;
};
