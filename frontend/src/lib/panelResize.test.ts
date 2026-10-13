import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { startPanelResize, type PanelResizeOptions } from './panelResize';

class FakeElement extends EventTarget {
  style = { width: '320px', cssText: '' };
  captured = false;
  removed = false;
  getBoundingClientRect = () => ({ width: 320 });
  setPointerCapture = () => {
    this.captured = true;
  };
  hasPointerCapture = () => this.captured;
  releasePointerCapture = () => {
    this.captured = false;
  };
  remove = () => {
    this.removed = true;
  };
}

let target: EventTarget;
let panel: FakeElement;
let handle: FakeElement;
let shield: FakeElement;
let body: { style: { cursor: string; userSelect: string }; appendChild: ReturnType<typeof vi.fn> };
let frames: Map<number, FrameRequestCallback>;
let frameId: number;

function pointer(type: string, clientX: number, pointerId = 1): void {
  target.dispatchEvent(Object.assign(new Event(type), { clientX, pointerId }));
}

function start(
  direction: 1 | -1 = 1,
  thresholds: Pick<
    PanelResizeOptions,
    | 'collapseThreshold'
    | 'coverThreshold'
    | 'dockThreshold'
    | 'initialMode'
    | 'dockMaxWidth'
    | 'coverWidth'
    | 'onPreview'
  > = {}
) {
  const onFinish = vi.fn();
  const cleanup = startPanelResize({
    panel: panel as unknown as HTMLElement,
    handle: handle as unknown as HTMLElement,
    pointerId: 1,
    startX: 320,
    direction,
    minWidth: 240,
    maxWidth: 480,
    onFinish,
    ...thresholds,
  });
  return { cleanup, onFinish };
}

beforeEach(() => {
  target = new EventTarget();
  panel = new FakeElement();
  handle = new FakeElement();
  shield = new FakeElement();
  body = { style: { cursor: 'default', userSelect: 'text' }, appendChild: vi.fn() };
  frames = new Map();
  frameId = 0;
  vi.stubGlobal('window', target);
  vi.stubGlobal('document', { body, createElement: () => shield });
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    frames.set(++frameId, callback);
    return frameId;
  });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id));
});
afterEach(() => vi.unstubAllGlobals());

describe('panel resize gestures', () => {
  it.each([1, -1] as const)('flushes the final pointer position for direction %s', (direction) => {
    const { onFinish } = start(direction);
    pointer('pointermove', 350);
    pointer('pointermove', 360);
    expect(frames.size).toBe(1);
    expect(onFinish).not.toHaveBeenCalled();
    pointer('pointerup', 370);
    expect(panel.style.width).toBe(`${320 + direction * 50}px`);
    expect(onFinish).toHaveBeenCalledExactlyOnceWith(320 + direction * 50);
    expect(frames.size).toBe(0);
    expect(shield.removed).toBe(true);
    expect(body.style).toEqual({ cursor: 'default', userSelect: 'text' });
    expect(handle.captured).toBe(false);
  });

  it('moves immediately back from a limit without a dead zone', () => {
    const { onFinish } = start();
    pointer('pointermove', 900);
    pointer('pointerup', 890);
    expect(onFinish).toHaveBeenCalledWith(470);
  });

  it('ignores other pointers and restores the initial width on cancellation', () => {
    const { onFinish } = start();
    pointer('pointermove', 400);
    for (const frame of frames.values()) frame(0);
    pointer('pointerup', 470, 2);
    expect(onFinish).not.toHaveBeenCalled();
    pointer('pointercancel', 400);
    expect(panel.style.width).toBe('320px');
    expect(onFinish).toHaveBeenCalledExactlyOnceWith(null);
  });

  it('commits on window blur and removes listeners', () => {
    const { onFinish } = start();
    pointer('pointermove', 400);
    target.dispatchEvent(new Event('blur'));
    pointer('pointerup', 450);
    expect(onFinish).toHaveBeenCalledExactlyOnceWith(400);
    expect(panel.style.width).toBe('400px');
  });

  it.each(['Escape', 'unmount', 'lostpointercapture'])('cleans up on %s', (reason) => {
    const { cleanup, onFinish } = start();
    pointer('pointermove', 400);
    if (reason === 'Escape')
      target.dispatchEvent(Object.assign(new Event('keydown'), { key: 'Escape' }));
    else if (reason === 'lostpointercapture')
      handle.dispatchEvent(Object.assign(new Event(reason), { pointerId: 1 }));
    else cleanup();
    cleanup();
    expect(onFinish).toHaveBeenCalledExactlyOnceWith(null);
    expect(frames.size).toBe(0);
    expect(shield.removed).toBe(true);
    expect(body.style.userSelect).toBe('text');
  });
});

function flushFrames(): void {
  const callbacks = [...frames.values()];
  frames.clear();
  callbacks.forEach((callback) => callback(0));
}

describe('reversible panel resize previews', () => {
  it.each([1, -1] as const)(
    'can pull direction %s back after collapse without releasing the pointer',
    (direction) => {
      const onPreview = vi.fn();
      const { onFinish } = start(direction, { collapseThreshold: 176, onPreview });
      pointer('pointermove', 320 - direction * 150);
      flushFrames();
      expect(onPreview).toHaveBeenLastCalledWith(240, 'collapse');
      expect(onFinish).not.toHaveBeenCalled();
      expect(handle.captured).toBe(true);
      expect(shield.removed).toBe(false);
      pointer('pointermove', 320 - direction * 70);
      flushFrames();
      expect(onPreview).toHaveBeenLastCalledWith(256, 'dock');
      pointer('pointerup', 320 - direction * 70);
      expect(onFinish).toHaveBeenCalledExactlyOnceWith(256);
    }
  );

  it('commits collapse only on release and keeps the prior width for reopening', () => {
    const { onFinish } = start(1, { collapseThreshold: 176 });
    pointer('pointermove', 176);
    expect(onFinish).not.toHaveBeenCalled();
    pointer('pointerup', 176);
    expect(onFinish).toHaveBeenCalledExactlyOnceWith(240, 'collapse');
    expect(panel.style.width).toBe('320px');
    expect(shield.removed).toBe(true);
  });

  it('previews cover, dock, and cover again within one captured gesture', () => {
    const onPreview = vi.fn();
    const { onFinish } = start(-1, {
      coverThreshold: 544,
      dockThreshold: 432,
      coverWidth: 900,
      onPreview,
    });
    pointer('pointermove', 96);
    flushFrames();
    expect(onPreview).toHaveBeenLastCalledWith(900, 'cover');
    expect(onFinish).not.toHaveBeenCalled();
    expect(handle.captured).toBe(true);
    pointer('pointermove', 208);
    flushFrames();
    expect(onPreview).toHaveBeenLastCalledWith(432, 'dock');
    pointer('pointermove', 96);
    flushFrames();
    expect(onPreview).toHaveBeenLastCalledWith(900, 'cover');
    pointer('pointerup', 96);
    expect(onFinish).toHaveBeenCalledExactlyOnceWith(900, 'cover');
  });

  it('releases in dock mode after pulling back from cover', () => {
    const { onFinish } = start(-1, { coverThreshold: 544, dockThreshold: 432, coverWidth: 900 });
    pointer('pointermove', 96);
    pointer('pointerup', 220);
    expect(onFinish).toHaveBeenCalledExactlyOnceWith(420);
  });

  it('follows the pointer when a snapped panel is grabbed again, then docks at the threshold', () => {
    const first = start(-1, { coverThreshold: 544, dockThreshold: 432, coverWidth: 900 });
    pointer('pointerup', 96);
    expect(first.onFinish).toHaveBeenCalledExactlyOnceWith(900, 'cover');

    panel.getBoundingClientRect = () => ({ width: 900 });
    const onPreview = vi.fn();
    const onFinish = vi.fn();
    startPanelResize({
      panel: panel as unknown as HTMLElement,
      handle: handle as unknown as HTMLElement,
      pointerId: 1,
      startX: 0,
      direction: -1,
      minWidth: 240,
      maxWidth: 900,
      dockMaxWidth: 480,
      coverWidth: 900,
      coverThreshold: 544,
      dockThreshold: 432,
      initialMode: 'cover',
      onPreview,
      onFinish,
    });
    for (const x of [1, 100, 300, 467]) {
      pointer('pointermove', x);
      flushFrames();
      expect(onPreview).toHaveBeenLastCalledWith(900 - x, 'cover');
    }
    pointer('pointermove', 468);
    flushFrames();
    expect(onPreview).toHaveBeenLastCalledWith(432, 'dock');
    pointer('pointerup', 468);
    expect(onFinish).toHaveBeenCalledExactlyOnceWith(432, 'dock');
  });

  it.each([1, 100, 467])('previews a %spx pull but snaps back to cover on release', (distance) => {
    panel.getBoundingClientRect = () => ({ width: 900 });
    const onPreview = vi.fn();
    const onFinish = vi.fn();
    startPanelResize({
      panel: panel as unknown as HTMLElement,
      handle: handle as unknown as HTMLElement,
      pointerId: 1,
      startX: 0,
      direction: -1,
      minWidth: 240,
      maxWidth: 900,
      dockMaxWidth: 480,
      coverWidth: 900,
      coverThreshold: 544,
      dockThreshold: 432,
      initialMode: 'cover',
      onPreview,
      onFinish,
    });
    pointer('pointermove', distance);
    flushFrames();
    expect(onPreview).toHaveBeenLastCalledWith(900 - distance, 'cover');
    expect(onFinish).not.toHaveBeenCalled();
    pointer('pointerup', distance);
    expect(onFinish).toHaveBeenCalledExactlyOnceWith(900);
  });

  it('can start in cover mode and return after previewing dock', () => {
    panel.getBoundingClientRect = () => ({ width: 800 });
    const onPreview = vi.fn();
    const { onFinish } = start(-1, {
      initialMode: 'cover',
      dockMaxWidth: 480,
      coverWidth: 800,
      coverThreshold: 544,
      dockThreshold: 432,
      onPreview,
    });
    pointer('pointermove', 688);
    flushFrames();
    expect(onPreview).toHaveBeenLastCalledWith(432, 'dock');
    pointer('pointermove', 576);
    flushFrames();
    expect(onPreview).toHaveBeenLastCalledWith(800, 'cover');
    pointer('pointerup', 576);
    expect(onFinish).toHaveBeenCalledExactlyOnceWith(800);
  });

  it('avoids flickering at the collapse and cover thresholds', () => {
    const onPreview = vi.fn();
    const { cleanup } = start(-1, {
      collapseThreshold: 176,
      coverThreshold: 544,
      dockThreshold: 432,
      coverWidth: 900,
      onPreview,
    });
    pointer('pointermove', 464);
    pointer('pointermove', 454);
    flushFrames();
    expect(onPreview).toHaveBeenLastCalledWith(240, 'collapse');
    pointer('pointermove', 320);
    pointer('pointermove', 96);
    pointer('pointermove', 106);
    flushFrames();
    expect(onPreview).toHaveBeenLastCalledWith(900, 'cover');
    cleanup();
  });

  it.each(['Escape', 'pointercancel', 'unmount'])('cancels a threshold preview on %s', (reason) => {
    const { onFinish, cleanup } = start(-1, { coverThreshold: 544, coverWidth: 900 });
    pointer('pointermove', 96);
    flushFrames();
    if (reason === 'Escape')
      target.dispatchEvent(Object.assign(new Event('keydown'), { key: 'Escape' }));
    else if (reason === 'pointercancel') pointer('pointercancel', 96);
    else cleanup();
    expect(onFinish).toHaveBeenCalledExactlyOnceWith(null);
    expect(panel.style.width).toBe('320px');
    expect(shield.removed).toBe(true);
    expect(handle.captured).toBe(false);
  });
});
