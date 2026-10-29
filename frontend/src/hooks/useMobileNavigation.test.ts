import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { effects, setDetail } = vi.hoisted(() => ({
  effects: [] as (() => void | (() => void))[],
  setDetail: vi.fn(),
}));
vi.mock('react', () => ({
  useEffect: (effect: () => void | (() => void)) => effects.push(effect),
  useState: (initial: () => boolean) => [initial(), setDetail],
  useCallback: (callback: unknown) => callback,
}));
import { useMobileNavigation } from './useMobileNavigation';

let history: {
  state: Record<string, unknown>;
  pushState: ReturnType<typeof vi.fn>;
  back: ReturnType<typeof vi.fn>;
};
beforeEach(() => {
  history = {
    state: { router: 'preserved' },
    pushState: vi.fn((state: Record<string, unknown>) => {
      history.state = state;
    }),
    back: vi.fn(),
  };
  vi.stubGlobal('window', Object.assign(new EventTarget(), { history }));
});
afterEach(() => {
  effects.length = 0;
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe('mobile page navigation', () => {
  it('starts at the list and pushes only one detail entry even when opening another chat', () => {
    const navigation = useMobileNavigation(true);
    expect(navigation.detail).toBe(false);
    navigation.open();
    navigation.open();
    expect(history.pushState).toHaveBeenCalledTimes(1);
    expect(history.state.router).toBe('preserved');
    navigation.back();
    expect(history.back).toHaveBeenCalledOnce();
  });
  it('follows browser back and forward and removes its listener on unmount', () => {
    const navigation = useMobileNavigation(true);
    const cleanup = effects[0]();
    navigation.open();
    history.state = {};
    window.dispatchEvent(new Event('popstate'));
    expect(setDetail).toHaveBeenLastCalledWith(false);
    history.state = { suzentMobileDetail: true };
    window.dispatchEvent(new Event('popstate'));
    expect(setDetail).toHaveBeenLastCalledWith(true);
    cleanup?.();
    setDetail.mockClear();
    window.dispatchEvent(new Event('popstate'));
    expect(setDetail).not.toHaveBeenCalled();
  });
  it('does not add browser history on desktop or navigate away from an initial list', () => {
    const navigation = useMobileNavigation(false);
    navigation.open();
    navigation.back();
    expect(history.pushState).not.toHaveBeenCalled();
    expect(history.back).not.toHaveBeenCalled();
  });
  it('restores a detail entry after remounting', () => {
    history.state = { suzentMobileDetail: true };
    expect(useMobileNavigation(true).detail).toBe(true);
  });
});
