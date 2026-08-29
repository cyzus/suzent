import { useEffect, useState } from 'react';

/** Matches the grid-rows collapse transition; they must stay in step. */
export const DISCLOSURE_COLLAPSE_MS = 300;

/**
 * Whether a collapsed disclosure should still render its body.
 *
 * `grid-rows-[0fr]` collapses with CSS alone, so the body stays mounted, laid
 * out and painted while invisible. That is affordable for a few nodes and not
 * at all for a tool block, whose body can mount a Monaco editor -- expanding a
 * rail with a handful of file operations mounted a full code editor for each
 * one, all of them collapsed and unseen.
 *
 * Two things keep it honest:
 *  - the body is held one transition past close, so collapsing still animates
 *    rather than snapping shut on an empty box;
 *  - `keepMounted` pins it open regardless, for a body holding state the user
 *    would lose -- a half-typed rejection reason lives in the tool block's own
 *    state and is only read when Deny is pressed.
 */
export function useDisclosureBody(
  expanded: boolean,
  { keepMounted = false, holdMs = DISCLOSURE_COLLAPSE_MS } = {}
): boolean {
  const [mounted, setMounted] = useState(expanded);

  useEffect(() => {
    if (expanded) {
      setMounted(true);
      return undefined;
    }
    if (keepMounted) return undefined;
    const timer = window.setTimeout(() => setMounted(false), holdMs);
    return () => window.clearTimeout(timer);
  }, [expanded, keepMounted, holdMs]);

  return mounted;
}
