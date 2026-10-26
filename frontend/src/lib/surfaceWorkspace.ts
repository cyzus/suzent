import type { A2UISurface } from '../types/a2ui';

export type SurfaceLocation = 'inline' | 'canvas';
type SurfaceSlot = SurfaceLocation | 'fullscreen';

export interface SurfaceEntry {
  surface: A2UISurface;
  host: HTMLDivElement;
  location: SurfaceLocation;
}

/** One live renderer per surface; slots only decide where its DOM is displayed. */
export class SurfaceWorkspace {
  private entries: SurfaceEntry[] = [];
  private slots = new Map<string, Partial<Record<SurfaceSlot, HTMLElement>>>();
  private listeners = new Set<() => void>();
  private parking: HTMLElement | null = null;
  private scroll = new Map<string, number>();

  snapshot = (): SurfaceEntry[] => this.entries;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private notify(): void {
    this.listeners.forEach((listener) => listener());
  }

  setParking = (node: HTMLDivElement | null): void => {
    this.parking = node;
    this.entries.forEach((entry) => this.move(entry));
  };

  upsert(surface: A2UISurface): void {
    const entry = this.entries.find((item) => item.surface.id === surface.id);
    if (entry && (entry.surface === surface || (entry.surface.rev ?? 0) > (surface.rev ?? 0)))
      return;
    const next = entry
      ? { ...entry, surface }
      : {
          surface,
          host: document.createElement('div'),
          location: surface.target === 'canvas' ? ('canvas' as const) : ('inline' as const),
        };
    this.entries = entry
      ? this.entries.map((item) => (item === entry ? next : item))
      : [...this.entries, next];
    this.move(next);
    this.notify();
  }

  place(id: string, location: SurfaceLocation): void {
    this.entries = this.entries.map((entry) =>
      entry.surface.id === id ? { ...entry, location } : entry
    );
    const entry = this.entries.find((item) => item.surface.id === id);
    if (entry) this.move(entry);
    this.notify();
  }

  register(id: string, slot: SurfaceSlot, node: HTMLElement): () => void {
    const slots = this.slots.get(id) ?? {};
    slots[slot] = node;
    this.slots.set(id, slots);
    const entry = this.entries.find((item) => item.surface.id === id);
    if (entry) this.move(entry);
    return () => {
      if (slots[slot] !== node) return;
      delete slots[slot];
      const current = this.entries.find((item) => item.surface.id === id);
      if (current) this.move(current);
    };
  }

  hasInline(id: string): boolean {
    return Boolean(this.slots.get(id)?.inline);
  }

  private move(entry: SurfaceEntry): void {
    const slots = this.slots.get(entry.surface.id);
    const target = slots?.fullscreen ?? slots?.[entry.location] ?? this.parking;
    if (!target || target === entry.host.parentElement) return;
    const previous = entry.host.parentElement;
    if (previous && previous !== this.parking && previous !== slots?.inline)
      this.scroll.set(entry.surface.id, previous.scrollTop);
    // moveBefore preserves iframe execution state; appendChild is the fallback
    // for older webviews and still preserves React component/form state.
    const movable = target as HTMLElement & {
      moveBefore?: (node: Node, before: Node | null) => void;
    };
    if (movable.moveBefore && entry.host.isConnected && target.isConnected)
      movable.moveBefore(entry.host, null);
    else target.appendChild(entry.host);
    if (target !== this.parking) target.scrollTop = this.scroll.get(entry.surface.id) ?? 0;
  }
}
