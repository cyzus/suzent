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
    expect(scrollTo).toHaveBeenCalledWith({ top: 1200, behavior: 'auto' });
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it('keeps following when content grows during a downward wheel gesture', () => {
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
    container.dispatchEvent(Object.assign(new Event('wheel'), { deltaY: 10 }));
    container.scrollHeight = 1400;
    container.dispatchEvent(new Event('scroll'));
    effects[1]();
    expect(container.scrollTo).toHaveBeenLastCalledWith({ top: 1400, behavior: 'auto' });
    if (cleanup) cleanup();
  });

  it('returns to the bottom instantly while streaming', () => {
    vi.useFakeTimers();
    const hook = useAutoScroll([], { smooth: false });
    const scrollTo = vi.fn();
    hook.scrollContainerRef.current = { scrollHeight: 1200, scrollTo } as unknown as HTMLDivElement;
    hook.scrollToBottom();
    expect(scrollTo).toHaveBeenCalledWith({ top: 1200, behavior: 'auto' });
  });

  it('does not start a smooth animation for settled content updates', () => {
    vi.useFakeTimers();
    const hook = useAutoScroll([], { smooth: true });
    const scrollTo = vi.fn();
    hook.scrollContainerRef.current = { scrollHeight: 1200, scrollTo } as unknown as HTMLDivElement;
    const cleanup = effects[1]();
    expect(scrollTo).toHaveBeenCalledWith({ top: 1200, behavior: 'auto' });
    if (cleanup) cleanup();
  });

  it('does not resume following when finishing content shrinks and clamps a paused viewport', () => {
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
    container.dispatchEvent(Object.assign(new Event('wheel'), { deltaY: -100 }));
    container.scrollTop = 1800;
    container.dispatchEvent(new Event('scroll'));
    vi.advanceTimersByTime(300);
    // The completed turn folds its activity; the browser clamps to the new end.
    container.scrollHeight = 2000;
    container.scrollTop = 1400;
    container.dispatchEvent(new Event('scroll'));
    // A final render grows again. The user never asked to follow the tail.
    container.scrollHeight = 2600;
    effects[1]();
    expect(container.scrollTo).not.toHaveBeenCalled();
    container.dispatchEvent(Object.assign(new Event('wheel'), { deltaY: 600 }));
    container.scrollTop = 2000;
    container.dispatchEvent(new Event('scroll'));
    container.scrollHeight = 2700;
    effects[1]();
    expect(container.scrollTo).toHaveBeenLastCalledWith({ top: 2700, behavior: 'auto' });
    if (cleanup) cleanup();
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
      dispatch('wheel', { deltaY: 10 });
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
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
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

  it('pauses when a held scrollbar drags up inside the bottom tolerance', () => {
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
    container.dispatchEvent(Object.assign(new Event('pointerdown'), { button: 0 }));
    // Still held well after the short intent window has lapsed.
    vi.advanceTimersByTime(1000);
    container.scrollTop = 770;
    container.dispatchEvent(new Event('scroll'));
    expect(container.scrollTo).not.toHaveBeenCalled();
    window.dispatchEvent(new Event('pointerup'));
    container.scrollHeight = 1300;
    effects[1]();
    expect(container.scrollTo).not.toHaveBeenCalled();
    if (cleanup) cleanup();
  });

  it('holds the text at the viewport top when content above it folds while paused', () => {
    vi.useFakeTimers();
    vi.stubGlobal('window', new EventTarget());
    vi.stubGlobal('requestAnimationFrame', () => 1);
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
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
    // Layout in content coordinates; rects are derived from the scroll offset.
    const box = (contentTop: number, height: number, children: unknown[] = []) => {
      const node = {
        contentTop,
        height,
        children,
        isConnected: true,
        getBoundingClientRect: () => ({
          top: node.contentTop - container.scrollTop,
          bottom: node.contentTop + node.height - container.scrollTop,
          height: node.height,
        }),
      };
      return node;
    };
    // A sticky header stays pinned at the viewport top and must not be the anchor.
    const header = {
      children: [],
      sticky: true,
      getBoundingClientRect: () => ({ top: 0, bottom: 40, height: 40 }),
    };
    vi.stubGlobal('getComputedStyle', (node: { sticky?: boolean }) => ({
      position: node.sticky ? 'sticky' : 'static',
    }));
    const activity = box(0, 1500);
    const paragraph = box(1600, 200);
    const row = box(0, 2400, [header, activity, paragraph]);
    const container = Object.assign(new EventTarget(), {
      children: [row],
      scrollHeight: 2400,
      clientHeight: 600,
      clientWidth: 900,
      scrollTop: 1800,
      scrollTo: vi.fn(),
      closest: () => null,
      contains: () => true,
      getBoundingClientRect: () => ({ top: 0, bottom: 600, height: 600 }),
    });
    const hook = useAutoScroll([], { smooth: false });
    hook.scrollContainerRef.current = container as unknown as HTMLDivElement;
    const cleanupListeners = effects[0]();
    const cleanupResize = effects[2]();
    container.dispatchEvent(Object.assign(new Event('wheel'), { deltaY: -100 }));
    container.scrollTop = 1650;
    container.dispatchEvent(new Event('scroll'));
    // The finished turn folds its activity above the paragraph being read.
    activity.height = 40;
    paragraph.contentTop = 140;
    row.height = 940;
    container.scrollHeight = 940;
    container.scrollTop = 340;
    onResize();
    expect(paragraph.getBoundingClientRect().top).toBe(-50);
    expect(container.scrollTop).toBe(190);
    if (cleanupResize) cleanupResize();
    if (cleanupListeners) cleanupListeners();
  });

  it('undoes a clamp from a briefly shorter layout instead of anchoring to it', () => {
    vi.useFakeTimers();
    vi.stubGlobal('window', new EventTarget());
    vi.stubGlobal('requestAnimationFrame', () => 1);
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
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
    vi.stubGlobal('getComputedStyle', () => ({ position: 'static' }));
    const box = (contentTop: number, height: number, children: unknown[] = []) => {
      const node = {
        contentTop,
        height,
        children,
        isConnected: true,
        getBoundingClientRect: () => ({
          top: node.contentTop - container.scrollTop,
          bottom: node.contentTop + node.height - container.scrollTop,
          height: node.height,
        }),
      };
      return node;
    };
    const paragraph = box(1600, 200);
    const row = box(0, 2400, [box(0, 1500), paragraph]);
    const container = Object.assign(new EventTarget(), {
      children: [row],
      scrollHeight: 2400,
      clientHeight: 600,
      clientWidth: 900,
      scrollTop: 1800,
      scrollTo: vi.fn(),
      closest: () => null,
      contains: () => true,
      getBoundingClientRect: () => ({ top: 0, bottom: 600, height: 600 }),
    });
    const hook = useAutoScroll([], { smooth: false });
    hook.scrollContainerRef.current = container as unknown as HTMLDivElement;
    const cleanupListeners = effects[0]();
    const cleanupResize = effects[2]();
    container.dispatchEvent(Object.assign(new Event('wheel'), { deltaY: -100 }));
    container.scrollTop = 1650;
    container.dispatchEvent(new Event('scroll'));
    vi.advanceTimersByTime(300);
    // The turn finishing lays out a shorter transcript mid-commit; WebKit clamps
    // scrollTop to it, and that scroll event lands before the resize.
    container.scrollTop = 1300;
    container.dispatchEvent(new Event('scroll'));
    row.height = 2420;
    container.scrollHeight = 2420;
    onResize();
    expect(container.scrollTop).toBe(1650);
    expect(paragraph.getBoundingClientRect().top).toBe(-50);
    if (cleanupResize) cleanupResize();
    if (cleanupListeners) cleanupListeners();
  });

  it('finds the paragraph being read again when the live message is swapped for the saved one', () => {
    vi.useFakeTimers();
    vi.stubGlobal('window', new EventTarget());
    vi.stubGlobal('requestAnimationFrame', () => 1);
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
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
    type Box = {
      tagName: string;
      contentTop: number;
      height: number;
      children: Box[];
      textContent: string;
      isConnected: boolean;
      getBoundingClientRect: () => { top: number; bottom: number; height: number };
    };
    const box = (
      tagName: string,
      contentTop: number,
      height: number,
      text = '',
      children: Box[] = []
    ) => {
      const node: Box = {
        tagName,
        contentTop,
        height,
        children,
        textContent: text,
        isConnected: true,
        getBoundingClientRect: () => ({
          top: node.contentTop - container.scrollTop,
          bottom: node.contentTop + node.height - container.scrollTop,
          height: node.height,
        }),
      };
      return node;
    };
    const reading = 'The second paragraph of the answer.';
    const liveParagraph = box('P', 2600, 200, reading);
    const live = box('DIV', 1000, 2400, '', [box('DIV', 1000, 1500), liveParagraph]);
    const history = box('DIV', 0, 1000);
    const container = Object.assign(new EventTarget(), {
      children: [history, live],
      scrollHeight: 3400,
      clientHeight: 600,
      clientWidth: 900,
      scrollTop: 2650,
      scrollTo: vi.fn(),
      closest: () => null,
      contains: () => true,
      getBoundingClientRect: () => ({ top: 0, bottom: 600, height: 600 }),
      querySelectorAll: (selector: string) =>
        selector === 'P' ? [savedParagraph].filter((node) => node.isConnected) : [],
    });
    const hook = useAutoScroll([], { smooth: false });
    hook.scrollContainerRef.current = container as unknown as HTMLDivElement;
    const cleanupListeners = effects[0]();
    const cleanupResize = effects[2]();
    container.dispatchEvent(Object.assign(new Event('wheel'), { deltaY: -100 }));
    container.dispatchEvent(new Event('scroll'));
    // The saved message replaces the live one, its activity already folded.
    const savedParagraph = box('P', 1100, 200, reading);
    history.height = 2000;
    history.children = [box('DIV', 1000, 400, '', [savedParagraph])];
    live.isConnected = false;
    liveParagraph.isConnected = false;
    container.children = [history];
    container.scrollHeight = 2000;
    container.scrollTop = 1400;
    onResize();
    expect(savedParagraph.getBoundingClientRect().top).toBe(-50);
    expect(container.scrollTop).toBe(1150);
    if (cleanupResize) cleanupResize();
    if (cleanupListeners) cleanupListeners();
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
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
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

    it.each(['next frame', 'another resize', 'cleanup'])(
      'does not overwrite momentum scrolling when the nudge ends via %s',
      (ending) => {
        const { container, onResize, flushFrame, cleanup } = useScrollerHarness();
        container.clientWidth = 1200;
        onResize();
        flushFrame();
        flushFrame();
        expect(container.scrollTop).toBe(2399);
        container.scrollTop = 1700;
        container.scrollTo.mockClear();
        if (ending === 'next frame') flushFrame();
        if (ending === 'another resize') {
          container.clientWidth = 1000;
          onResize();
        }
        if (cleanup) cleanup();
        expect(container.scrollTop).toBe(1700);
        if (ending !== 'another resize') expect(container.scrollTo).not.toHaveBeenCalled();
      }
    );

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
