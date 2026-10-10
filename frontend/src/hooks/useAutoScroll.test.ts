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

  it('follows the last message growing and newly appended messages', () => {
    vi.useFakeTimers();
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
    const container = { children: [{}, last], scrollHeight: 800, scrollTo: vi.fn() };
    hook.scrollContainerRef.current = container as unknown as HTMLDivElement;
    const cleanup = effects[2]();
    expect(observe).toHaveBeenCalledWith(last);
    container.scrollHeight = 1100;
    onResize();
    expect(container.scrollTo).toHaveBeenLastCalledWith({ top: 1100, behavior: 'auto' });
    const appended = {};
    container.children.push(appended);
    onMutation();
    expect(observe).toHaveBeenCalledWith(appended);
    if (cleanup) cleanup();
    expect(disconnect).toHaveBeenCalled();
  });
});
