/**
 * InlineSurfaceContext — what an A2UI surface rendered in the chat needs from
 * the chat around it: a way to pop it out to the side panel, and to know when
 * a later render of the same surface id has superseded it.
 */

import React, { createContext, useContext, useEffect, useMemo, useSyncExternalStore } from 'react';
import type { A2UISurface } from '../../types/a2ui';

/** Revisions of every mounted inline copy, by surface id. */
export class SurfaceRevisions {
  private revs = new Map<string, Map<symbol, number>>();
  private listeners = new Set<() => void>();

  register(id: string, rev: number): () => void {
    const token = Symbol(id);
    const copies = this.revs.get(id) ?? new Map<symbol, number>();
    copies.set(token, rev);
    this.revs.set(id, copies);
    this.notify();
    return () => {
      copies.delete(token);
      if (copies.size === 0) this.revs.delete(id);
      this.notify();
    };
  }

  latest(id: string): number {
    const copies = this.revs.get(id);
    return copies ? Math.max(...copies.values()) : 0;
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private notify(): void {
    this.listeners.forEach((listener) => listener());
  }
}

interface InlineSurfaceContextValue {
  openInCanvas: (surface: A2UISurface) => void;
  revisions: SurfaceRevisions;
}

const InlineSurfaceContext = createContext<InlineSurfaceContextValue | null>(null);

export const InlineSurfaceProvider: React.FC<{
  openInCanvas: (surface: A2UISurface) => void;
  children: React.ReactNode;
}> = ({ openInCanvas, children }) => {
  const revisions = useMemo(() => new SurfaceRevisions(), []);
  const value = useMemo(() => ({ openInCanvas, revisions }), [openInCanvas, revisions]);
  return <InlineSurfaceContext.Provider value={value}>{children}</InlineSurfaceContext.Provider>;
};

export function useInlineSurfaceContext(): InlineSurfaceContextValue | null {
  return useContext(InlineSurfaceContext);
}

const noopSubscribe = () => () => {};

/**
 * True once another copy of this surface with a later rev is mounted. Copies
 * saved before revs existed carry none and are never superseded.
 */
export function useIsSuperseded(surface: A2UISurface, tracked: boolean): boolean {
  const ctx = useContext(InlineSurfaceContext);
  const revisions = tracked ? ctx?.revisions : undefined;
  const rev = surface.rev;

  useEffect(() => {
    if (!revisions || rev === undefined) return;
    return revisions.register(surface.id, rev);
  }, [revisions, surface.id, rev]);

  return useSyncExternalStore(revisions?.subscribe ?? noopSubscribe, () =>
    revisions && rev !== undefined ? rev < revisions.latest(surface.id) : false
  );
}
