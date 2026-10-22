import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SurfaceWorkspace } from './surfaceWorkspace';
import type { A2UISurface } from '../types/a2ui';

class Slot {
  parentElement: Slot | null = null;
  isConnected = true;
  scrollTop = 0;
  appendChild = vi.fn((node: Slot) => {
    node.parentElement = this;
  });
  moveBefore = vi.fn((node: Slot) => {
    node.parentElement = this;
  });
  asElement(): HTMLDivElement {
    return this as unknown as HTMLDivElement;
  }
}

const surface: A2UISurface = { id: 'news', rev: 1, component: { type: 'html', html: '<input>' } };

beforeEach(() => vi.stubGlobal('document', { createElement: () => new Slot() }));
afterEach(() => vi.unstubAllGlobals());

describe('shared surface placement', () => {
  it('moves one host between inline, canvas and fullscreen while retaining its identity', () => {
    const workspace = new SurfaceWorkspace();
    const inline = new Slot();
    const canvas = new Slot();
    const full = new Slot();
    workspace.setParking(new Slot().asElement());
    workspace.upsert(surface);
    workspace.register(surface.id, 'inline', inline.asElement());
    workspace.register(surface.id, 'canvas', canvas.asElement());
    const host = workspace.snapshot()[0].host;
    expect(host.parentElement).toBe(inline);
    workspace.place(surface.id, 'canvas');
    expect(host.parentElement).toBe(canvas);
    canvas.scrollTop = 240;
    const closeFullscreen = workspace.register(surface.id, 'fullscreen', full.asElement());
    expect(host.parentElement).toBe(full);
    expect(full.scrollTop).toBe(240);
    closeFullscreen();
    expect(host.parentElement).toBe(canvas);
    workspace.place(surface.id, 'inline');
    expect(host.parentElement).toBe(inline);
    workspace.place(surface.id, 'canvas');
    expect(canvas.scrollTop).toBe(240);
    expect(workspace.snapshot()).toHaveLength(1);
    expect(workspace.snapshot()[0].host).toBe(host);
    expect(canvas.moveBefore).toHaveBeenCalled();
  });

  it('treats target as an initial placement and does not reset a user choice on updates', () => {
    const workspace = new SurfaceWorkspace();
    workspace.upsert({ ...surface, target: 'canvas' });
    expect(workspace.snapshot()[0].location).toBe('canvas');
    workspace.place(surface.id, 'inline');
    const host = workspace.snapshot()[0].host;
    workspace.upsert({ ...surface, target: 'canvas', rev: 3 });
    workspace.upsert({ ...surface, rev: 2 });
    expect(workspace.snapshot()[0].location).toBe('inline');
    expect(workspace.snapshot()[0].surface.rev).toBe(3);
    expect(workspace.snapshot()[0].host).toBe(host);
  });

  it('parks inactive surfaces and ignores cleanup from a replaced slot', () => {
    const workspace = new SurfaceWorkspace();
    const parking = new Slot();
    const old = new Slot();
    const current = new Slot();
    workspace.setParking(parking.asElement());
    workspace.upsert(surface);
    const removeOld = workspace.register(surface.id, 'inline', old.asElement());
    const removeCurrent = workspace.register(surface.id, 'inline', current.asElement());
    removeOld();
    expect(workspace.snapshot()[0].host.parentElement).toBe(current);
    removeCurrent();
    expect(workspace.snapshot()[0].host.parentElement).toBe(parking);
    expect(workspace.hasInline(surface.id)).toBe(false);
  });
});
