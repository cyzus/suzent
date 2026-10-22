import { afterEach, describe, expect, it, vi } from 'vitest';
import { A2UIHtmlComponent } from './A2UIHtmlComponent';

const state = vi.hoisted(() => ({
  source: {},
  setHeight: vi.fn(),
  effects: [] as Array<() => void | (() => void)>,
}));
vi.mock('react', async (original) => ({
  ...(await original<typeof import('react')>()),
  useRef: () => ({ current: { contentWindow: state.source } }),
  useState: () => [160, state.setHeight],
  useEffect: (effect: () => void | (() => void)) => state.effects.push(effect),
}));

afterEach(() => {
  state.effects = [];
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

function mount(height?: number) {
  const listeners = new Map<string, (event: Partial<MessageEvent>) => void>();
  vi.stubGlobal('window', {
    addEventListener: (name: string, handler: (event: Partial<MessageEvent>) => void) =>
      listeners.set(name, handler),
    removeEventListener: (name: string) => listeners.delete(name),
  });
  A2UIHtmlComponent({
    component: { type: 'html', html: '<p>News</p>', height },
    onAction: vi.fn(),
  });
  state.effects.forEach((effect) => effect());
  return (value: number, source = state.source) =>
    listeners.get('message')?.({
      source: source as Window,
      data: { type: 'a2ui:resize', height: value },
    });
}

describe('HTML iframe resize messages', () => {
  it('grows beyond 4000px and shrinks after reflow', () => {
    const resize = mount();
    resize(5766);
    resize(3160);
    expect(state.setHeight.mock.calls).toEqual([[5766], [3160]]);
  });

  it('ignores invalid heights and messages from other frames', () => {
    const resize = mount();
    resize(NaN);
    resize(Infinity);
    resize(-1);
    resize(5766, {});
    expect(state.setHeight).not.toHaveBeenCalled();
  });

  it('leaves explicit heights under the application’s control', () => {
    mount(600)(5766);
    expect(state.setHeight).not.toHaveBeenCalled();
  });
});
