/**
 * InlineSurfaceContext — what an A2UI surface rendered in the chat needs from
 * the chat around it: a way to pop it out to the side panel, and to know when
 * a later render of the same surface id has superseded it.
 */

import React, {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useSyncExternalStore,
  useCallback,
  useRef,
} from 'react';
import { createPortal } from 'react-dom';
import type { A2UISurface } from '../../types/a2ui';
import { SurfaceWorkspace, type SurfaceEntry } from '../../lib/surfaceWorkspace';
import { htmlContentHeight } from '../../lib/a2uiHtml';
import { A2UIRenderer } from './A2UIRenderer';
import { A2UIHtmlComponent } from './components/A2UIHtmlComponent';

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
  openInCanvas: (surface: A2UISurface, expanded?: boolean) => void;
  revisions: SurfaceRevisions;
  workspace: SurfaceWorkspace;
}

const InlineSurfaceContext = createContext<InlineSurfaceContextValue | null>(null);

export const InlineSurfaceProvider: React.FC<{
  openInCanvas: (surface: A2UISurface, expanded?: boolean) => void;
  surfaces: A2UISurface[];
  onAction: (surfaceId: string, action: string, context: Record<string, unknown>) => void;
  children: React.ReactNode;
}> = ({ openInCanvas, surfaces, onAction, children }) => {
  const revisions = useMemo(() => new SurfaceRevisions(), []);
  const workspace = useMemo(() => new SurfaceWorkspace(), []);
  const entries = useSyncExternalStore(workspace.subscribe, workspace.snapshot);
  useLayoutEffect(() => {
    surfaces.filter((surface) => !surface.deferred).forEach((surface) => workspace.upsert(surface));
  }, [surfaces, workspace]);
  const value = useMemo(
    () => ({
      openInCanvas: (surface: A2UISurface, expanded?: boolean): void => {
        workspace.upsert(surface);
        workspace.place(surface.id, 'canvas');
        openInCanvas(surface, expanded);
      },
      revisions,
      workspace,
    }),
    [openInCanvas, revisions, workspace]
  );
  return (
    <InlineSurfaceContext.Provider value={value}>
      {children}
      <div ref={workspace.setParking} hidden />
      {entries.map((entry) => (
        <SharedSurfaceBody key={entry.surface.id} entry={entry} onAction={onAction} />
      ))}
    </InlineSurfaceContext.Provider>
  );
};

function SharedSurfaceBody({
  entry,
  onAction,
}: {
  entry: SurfaceEntry;
  onAction: (surfaceId: string, action: string, context: Record<string, unknown>) => void;
}): React.ReactElement {
  const { surface, host, location } = entry;
  const fixed =
    location === 'canvas' &&
    surface.component.type === 'html' &&
    htmlContentHeight(surface.component.height) !== null;
  useLayoutEffect(() => {
    host.style.height = fixed ? '100%' : '';
  }, [host, fixed]);
  const dispatch = (action: string, context: Record<string, unknown>): void =>
    onAction(surface.id, action, context);
  return createPortal(
    <div
      className={`${fixed ? 'h-full' : ''} ${location === 'canvas' && surface.component.type !== 'html' ? 'p-4' : ''}`}
    >
      {surface.component.type === 'html' ? (
        <A2UIHtmlComponent
          component={surface.component}
          onAction={dispatch}
          framed={location === 'inline'}
        />
      ) : (
        <A2UIRenderer component={surface.component} onAction={dispatch} />
      )}
    </div>,
    host
  );
}

export function useInlineSurfaceContext(): InlineSurfaceContextValue | null {
  return useContext(InlineSurfaceContext);
}

const noopSubscribe = () => () => {};
const emptyEntries: SurfaceEntry[] = [];

export function useSurfaceEntry(id: string): SurfaceEntry | undefined {
  const ctx = useInlineSurfaceContext();
  return useSyncExternalStore(
    ctx?.workspace.subscribe ?? noopSubscribe,
    ctx?.workspace.snapshot ?? (() => emptyEntries)
  ).find((entry) => entry.surface.id === id);
}

export function useSurfaceSlot(
  id: string,
  slot: 'inline' | 'canvas' | 'fullscreen',
  enabled = true
): (node: HTMLDivElement | null) => void {
  const workspace = useInlineSurfaceContext()?.workspace;
  const cleanup = useRef<(() => void) | undefined>();
  // Ref detachment happens before DOM removal, so move live iframes out while
  // their old slot is still connected (layout-effect cleanup can be too late).
  return useCallback(
    (node: HTMLDivElement | null) => {
      cleanup.current?.();
      cleanup.current =
        node && enabled && workspace ? workspace.register(id, slot, node) : undefined;
    },
    [workspace, id, slot, enabled]
  );
}

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
