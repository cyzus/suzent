import { afterEach, describe, expect, it, vi } from 'vitest';

const { effects } = vi.hoisted(() => ({ effects: [] as (() => void | (() => void))[] }));
vi.mock('react', () => ({
  useEffect: (effect: () => void | (() => void)) => effects.push(effect),
  useLayoutEffect: () => {},
  useRef: (current: unknown) => ({ current }),
  useState: (value: unknown) => [value, vi.fn()],
  useCallback: (callback: unknown) => callback,
}));

import { useAutoScroll } from './useAutoScroll';

afterEach(() => {
  effects.length = 0;
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('message bottom scrolling', () => {
  it('scrolls the message container without moving ancestors', () => {
    vi.useFakeTimers();
    const hook = useAutoScroll([]);
    const scrollTo = vi.fn();
    hook.scrollContainerRef.current = { scrollHeight: 1200, scrollTo } as unknown as HTMLDivElement;
    const scrollIntoView = vi.fn();
    hook.bottomRef.current = { scrollIntoView } as unknown as HTMLDivElement;
    hook.scrollToBottom();
    expect(scrollTo).toHaveBeenCalledWith({ top: 1200, behavior: 'smooth' });
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it('repairs an upward layout jump during streaming without waiting for a resize', () => {
    vi.useFakeTimers();
    vi.stubGlobal('window', new EventTarget());
    const hook = useAutoScroll([], { smooth: false });
    const container = Object.assign(new EventTarget(), {
      scrollHeight: 3000,
      clientHeight: 600,
      scrollTop: 2400,
      scrollTo: vi.fn(),
    });
    hook.scrollContainerRef.current = container as unknown as HTMLDivElement;
    const cleanup = effects[0]();
    effects[1]();
    container.scrollTo.mockClear();

    // A layout shift can move the viewport during our programmatic scroll.
    container.scrollTop = 800;
    container.dispatchEvent(new Event('scroll'));
    expect(container.scrollTo).toHaveBeenLastCalledWith({ top: 3000, behavior: 'auto' });

    // Once settled at the bottom, scroll events must not create a feedback loop.
    container.scrollTo.mockClear();
    container.scrollTop = 2400;
    container.dispatchEvent(new Event('scroll'));
    expect(container.scrollTo).not.toHaveBeenCalled();

    // A live text selection still owns the viewport.
    container.dispatchEvent(Object.assign(new Event('pointerdown'), { button: 0 }));
    vi.advanceTimersByTime(300);
    container.scrollTo.mockClear();
    container.scrollTop = 800;
    container.dispatchEvent(new Event('scroll'));
    expect(container.scrollTo).not.toHaveBeenCalled();
    if (cleanup) cleanup();
  });

  it.each(['wheel', 'touch', 'keyboard'])(
    'pauses on upward %s input before streaming can pull the viewport back',
    (input) => {
      vi.useFakeTimers();
      vi.stubGlobal('window', new EventTarget());
      const hook = useAutoScroll([], { smooth: false });
      const container = Object.assign(new EventTarget(), {
        scrollHeight: 1200,
        clientHeight: 400,
        scrollTop: 800,
        scrollTo: vi.fn(),
      });
      hook.scrollContainerRef.current = container as unknown as HTMLDivElement;
      const cleanup = effects[0]();
      effects[1]();
      container.scrollTo.mockClear();
      const dispatch = (type: string, fields: object) =>
        container.dispatchEvent(Object.assign(new Event(type), fields));

      if (input === 'wheel') dispatch('wheel', { deltaY: -10 });
      if (input === 'touch') {
        dispatch('touchstart', { touches: [{ clientY: 100 }] });
        vi.advanceTimersByTime(300);
        dispatch('touchmove', { touches: [{ clientY: 110 }] });
      }
      if (input === 'keyboard') {
        Object.assign(container, { closest: () => null });
        dispatch('keydown', { key: 'ArrowUp' });
      }
      container.scrollTop = 790;
      dispatch('scroll', {});
      vi.advanceTimersByTime(500);
      effects[1]();
      expect(container.scrollTo).not.toHaveBeenCalled();

      // Returning to the actual bottom resumes following new content.
      container.scrollTop = 800;
      dispatch('scroll', {});
      container.scrollHeight = 1300;
      effects[1]();
      expect(container.scrollTo).toHaveBeenLastCalledWith({ top: 1300, behavior: 'auto' });
      if (cleanup) cleanup();
    }
  );

  it('follows the last message growing and newly appended messages', () => {
    vi.useFakeTimers();
    let settle: FrameRequestCallback = () => {};
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      settle = callback;
      return 1;
    });
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
    const observe = vi.fn();
    const disconnect = vi.fn();
    let onResize = () => {};
    let onMutation = () => {};
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(callback: () => void) {
          onResize = callback;
        }
        observe = observe;
        disconnect = disconnect;
      }
    );
    vi.stubGlobal(
      'MutationObserver',
      class {
        constructor(callback: () => void) {
          onMutation = callback;
        }
        observe = vi.fn();
        disconnect = vi.fn();
      }
    );
    const hook = useAutoScroll([]);
    const last = {};
    const container = {
      children: [{}, last],
      scrollHeight: 800,
      scrollTo: vi.fn(),
      closest: () => null,
    };
    hook.scrollContainerRef.current = container as unknown as HTMLDivElement;
    const cleanup = effects[2]();
    expect(observe).toHaveBeenCalledWith(last);
    container.scrollHeight = 1100;
    onResize();
    expect(container.scrollTo).toHaveBeenLastCalledWith({ top: 1100, behavior: 'auto' });
    container.scrollHeight = 1250;
    settle(0);
    expect(container.scrollTo).toHaveBeenLastCalledWith({ top: 1250, behavior: 'auto' });
    const appended = {};
    container.children.push(appended);
    onMutation();
    expect(observe).toHaveBeenCalledWith(appended);
    if (cleanup) cleanup();
    expect(disconnect).toHaveBeenCalled();
  });

  describe('WebKit scroll-layer resync after the transcript resizes', () => {
    function useScrollerHarness(overrides: Record<string, unknown> = {}) {
      vi.useFakeTimers();
      let nextId = 0;
      const queue = new Map<number, FrameRequestCallback>();
      vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
        queue.set(++nextId, callback);
        return nextId;
      });
      vi.stubGlobal('cancelAnimationFrame', (id: number) => queue.delete(id));
      let onResize = () => {};
      vi.stubGlobal(
        'ResizeObserver',
        class {
          constructor(callback: () => void) {
            onResize = callback;
          }
          observe = vi.fn();
          disconnect = vi.fn();
        }
      );
      vi.stubGlobal(
        'MutationObserver',
        class {
          observe = vi.fn();
          disconnect = vi.fn();
        }
      );
      const hook = useAutoScroll([]);
      const container = {
        children: [],
        clientWidth: 900,
        clientHeight: 600,
        scrollHeight: 3000,
        scrollTop: 2400,
        scrollTo: vi.fn(),
        style: { transform: '' },
        closest: () => ({}),
        ...overrides,
      };
      hook.scrollContainerRef.current = container as unknown as HTMLDivElement;
      const cleanup = effects[2]();
      // Runs the frames queued so far; frames they queue wait for the next call.
      const flushFrame = () => {
        const pending = [...queue.entries()];
        queue.clear();
        for (const [, callback] of pending) callback(0);
      };
      return { container, onResize: () => onResize(), flushFrame, cleanup };
    }

    it('ignores height-only growth such as streaming', () => {
      const { container, onResize, flushFrame, cleanup } = useScrollerHarness();
      onResize();
      flushFrame();
      flushFrame();
      flushFrame();
      vi.advanceTimersByTime(400);
      expect(container.scrollTop).toBe(2400);
      if (cleanup) cleanup();
    });

    it('scrolls a pixel and back on the frames right after the column gets wider', () => {
      const { container, onResize, flushFrame, cleanup } = useScrollerHarness();
      container.clientWidth = 1200;
      onResize();
      flushFrame();
      expect(container.scrollTop).toBe(2400);
      flushFrame();
      expect(container.scrollTop).toBe(2399);
      container.scrollTo.mockClear();
      flushFrame();
      expect(container.scrollTop).toBe(2400);
      expect(container.scrollTo).toHaveBeenCalledWith({ top: 3000, behavior: 'auto' });
      if (cleanup) cleanup();
    });

    it('also resyncs when the transcript shrinks at the same width', () => {
      const { container, onResize, flushFrame, cleanup } = useScrollerHarness();
      container.scrollHeight = 2500;
      container.scrollTop = 1900;
      onResize();
      flushFrame();
      flushFrame();
      expect(container.scrollTop).toBe(1899);
      flushFrame();
      expect(container.scrollTop).toBe(1900);
      if (cleanup) cleanup();
    });

    it('still repaints when nothing is scrollable, by toggling a compositing layer', () => {
      const { container, onResize, flushFrame, cleanup } = useScrollerHarness({
        scrollHeight: 500,
        scrollTop: 0,
      });
      container.clientWidth = 1200;
      onResize();
      flushFrame();
      expect(container.style.transform).toBe('');
      flushFrame();
      expect(container.style.transform).toBe('translateZ(0)');
      flushFrame();
      expect(container.style.transform).toBe('');
      expect(container.scrollTop).toBe(0);
      if (cleanup) cleanup();
    });

    it('falls back to a trailing pass when the frames never get to run', () => {
      const { container, onResize, cleanup } = useScrollerHarness();
      container.clientWidth = 1200;
      onResize();
      vi.advanceTimersByTime(349);
      expect(container.scrollTop).toBe(2400);
      vi.advanceTimersByTime(1);
      expect(container.scrollTop).toBe(2399);
      if (cleanup) cleanup();
    });

    it('restores the pixel nudge when another resize interrupts it', () => {
      const { container, onResize, flushFrame, cleanup } = useScrollerHarness();
      container.clientWidth = 1200;
      onResize();
      flushFrame();
      flushFrame();
      expect(container.scrollTop).toBe(2399);

      container.clientWidth = 1000;
      onResize();
      expect(container.scrollTop).toBe(2400);
      if (cleanup) cleanup();
    });

    it('restores the pixel nudge when the hook is torn down mid-flight', () => {
      const { container, onResize, flushFrame, cleanup } = useScrollerHarness();
      container.clientWidth = 1200;
      onResize();
      flushFrame();
      flushFrame();
      expect(container.scrollTop).toBe(2399);
      if (cleanup) cleanup();
      expect(container.scrollTop).toBe(2400);
    });
  });
});
