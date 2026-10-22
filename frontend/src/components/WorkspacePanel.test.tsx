import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { WorkspacePanel } from './WorkspacePanel';

const state = vi.hoisted(() => ({
  context: null as unknown,
  panel: null as unknown,
  effects: [] as Array<() => void | (() => void)>,
}));
vi.mock('react', async (original) => ({
  ...(await original<typeof import('react')>()),
  useContext: () => state.context,
  useId: () => 'panel',
  useRef: (initial: unknown) => ({ current: initial === null ? state.panel : initial }),
  useEffect: (effect: () => void | (() => void)) => state.effects.push(effect),
}));
const portal = vi.hoisted(() => vi.fn((child: React.ReactElement, _host: unknown) => child));
vi.mock('react-dom', () => ({ createPortal: portal }));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  state.effects = [];
  state.context = null;
});

function setup(topmost = true, closeOnEscape = true) {
  const panel = { focus: vi.fn() };
  const host = { lastElementChild: topmost ? panel : {} };
  state.panel = panel;
  state.context = { host, navigationKey: 'chat' };
  class Element {
    isConnected = true;
    focus = vi.fn();
  }
  const previous = new Element();
  vi.stubGlobal('HTMLElement', Element);
  vi.stubGlobal('document', { activeElement: previous });
  const listeners = new Map<string, (event: KeyboardEvent) => void>();
  vi.stubGlobal('window', {
    addEventListener: (name: string, handler: (event: KeyboardEvent) => void) =>
      listeners.set(name, handler),
    removeEventListener: (name: string) => listeners.delete(name),
  });
  const onClose = vi.fn();
  WorkspacePanel({ open: true, onClose, closeOnEscape, children: 'content' });
  const cleanup = state.effects.map((effect) => effect());
  return { host, panel, previous, onClose, listeners, cleanup };
}

describe('workspace panels', () => {
  it('renders in the workspace host and restores focus on exit', () => {
    const { host, panel, previous, cleanup, listeners } = setup();
    expect(portal.mock.calls[0][1]).toBe(host);
    expect(panel.focus).toHaveBeenCalledOnce();
    cleanup.forEach((dispose) => dispose?.());
    expect(previous.focus).toHaveBeenCalledOnce();
    expect(listeners.size).toBe(0);
  });

  it.each([
    [true, true, false, false, 1],
    [false, true, false, false, 0],
    [true, false, false, false, 0],
    [true, true, true, false, 0],
    [true, true, false, true, 0],
  ])(
    'respects panel order, editing, IME and handled Escape (%s, %s, %s, %s)',
    (topmost, enabled, composing, prevented, calls) => {
      const { listeners, onClose } = setup(Boolean(topmost), Boolean(enabled));
      listeners.get('keydown')?.({
        key: 'Escape',
        isComposing: composing,
        defaultPrevented: prevented,
        preventDefault: vi.fn(),
      } as unknown as KeyboardEvent);
      expect(onClose).toHaveBeenCalledTimes(Number(calls));
    }
  );

  it('does not render a closed panel', () => {
    expect(WorkspacePanel({ open: false, children: 'content' })).toBeNull();
    expect(portal).not.toHaveBeenCalled();
  });
});
