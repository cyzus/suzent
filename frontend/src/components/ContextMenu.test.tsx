import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ContextMenu } from './ContextMenu';

const state = vi.hoisted(() => ({ menu: null as unknown }));
vi.mock('react', async (original) => ({
  ...(await original<typeof import('react')>()),
  useRef: () => ({ current: state.menu }),
  useState: () => [{ left: 0, top: 0 }, vi.fn()],
  useEffect: vi.fn(),
  useLayoutEffect: vi.fn(),
}));
vi.mock('react-dom', () => ({ createPortal: (child: React.ReactElement) => child }));

afterEach(() => vi.unstubAllGlobals());

function setup(): {
  press: (key: string, composing?: boolean) => void;
  buttons: { focus: ReturnType<typeof vi.fn> }[];
  onClose: ReturnType<typeof vi.fn>;
  onEscape: ReturnType<typeof vi.fn>;
} {
  const buttons = [0, 1, 2].map(() => ({ focus: vi.fn() }));
  state.menu = { querySelectorAll: () => buttons };
  vi.stubGlobal('document', { body: {}, activeElement: buttons[0] });
  const onClose = vi.fn();
  const onEscape = vi.fn();
  const element = ContextMenu({ anchor: { x: 0, y: 0 }, children: null, onClose, onEscape });
  return {
    buttons,
    onClose,
    onEscape,
    press: (key, composing = false) =>
      element.props.onKeyDown({
        key,
        nativeEvent: { isComposing: composing },
        preventDefault: vi.fn(),
        stopPropagation: vi.fn(),
      }),
  };
}

describe('ContextMenu keyboard interaction', () => {
  it('wraps navigation and supports first and last item shortcuts', () => {
    const { press, buttons } = setup();
    press('ArrowUp');
    expect(buttons[2].focus).toHaveBeenCalledOnce();
    press('ArrowDown');
    expect(buttons[1].focus).toHaveBeenCalledOnce();
    press('Home');
    expect(buttons[0].focus).toHaveBeenCalledOnce();
    press('End');
    expect(buttons[2].focus).toHaveBeenCalledTimes(2);
  });

  it('lets nested views handle Escape while Tab closes the entire menu', () => {
    const { press, onClose, onEscape } = setup();
    press('Escape');
    expect(onEscape).toHaveBeenCalledOnce();
    expect(onClose).not.toHaveBeenCalled();
    press('Tab');
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('does not navigate or dismiss during IME composition', () => {
    const { press, onEscape, buttons } = setup();
    press('Escape', true);
    press('ArrowDown', true);
    expect(onEscape).not.toHaveBeenCalled();
    expect(buttons[1].focus).not.toHaveBeenCalled();
  });
});
