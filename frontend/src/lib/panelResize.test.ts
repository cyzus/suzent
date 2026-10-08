import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { startPanelResize } from './panelResize';

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

function start(direction: 1 | -1 = 1) {
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
