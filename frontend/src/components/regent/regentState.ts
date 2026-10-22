import { useEffect, useRef, useState } from 'react';
import type { FocalAgentStatus } from '../../lib/focalAgent';
import type { RegentState } from './RegentMark';

/** Working beats waiting: while Regent runs, it is the thing to watch. */
export function regentState(status: FocalAgentStatus | null): RegentState {
  if (status?.running) return 'working';
  if ((status?.waiting ?? 0) > 0) return 'waiting';
  return 'idle';
}

/**
 * A counter that ticks each time Regent has something new to say, so a keyed
 * wrapper can replay its one-off nod. Starts at 0, which plays nothing.
 */
export function useRegentNod(status: FocalAgentStatus | null): number {
  const [nods, setNods] = useState(0);
  const lastSpoke = useRef<string | null | undefined>(undefined);
  const spokeAt = status?.lastMessageAt ?? null;
  const unread = status?.unread ?? 0;

  useEffect(() => {
    if (lastSpoke.current === undefined) {
      lastSpoke.current = spokeAt;
      return;
    }
    if (spokeAt && spokeAt !== lastSpoke.current && unread > 0) setNods((count) => count + 1);
    lastSpoke.current = spokeAt;
  }, [spokeAt, unread]);

  return nods;
}
