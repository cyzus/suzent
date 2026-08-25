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
 * Frames the reveal aims to take to drain whatever is queued.
 *
 * Draining a fixed share per frame rather than a fixed number of characters is
 * what keeps the lag bounded: the rate rises with the backlog, so the display
 * settles a constant few frames behind however fast the agent emits, and a
 * burst still eases out instead of snapping.
 */
const CATCH_UP_FRAMES = 6;

/** Characters to reveal this frame given how far the buffer has run ahead. */
export const getRevealStep = (remaining: number): number =>
  Math.max(1, Math.ceil(remaining / CATCH_UP_FRAMES));

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
      indexRef.current += getRevealStep(remaining);
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
