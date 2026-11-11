import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const core = vi.hoisted(() => ({ invoke: vi.fn(async () => undefined) }));
const events = vi.hoisted(() => ({
  handler: null as null | ((event: { payload: number }) => void),
  listen: vi.fn(async (_name: string, handler: (event: { payload: number }) => void) => {
    events.handler = handler;
    return () => undefined;
  }),
}));
const hooks = vi.hoisted(() => ({
  effects: [] as (() => void)[],
  setters: [] as ReturnType<typeof vi.fn>[],
}));

vi.mock('@tauri-apps/api/core', () => core);
vi.mock('@tauri-apps/api/event', () => ({ listen: events.listen }));
vi.mock('../i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock('react', async (original) => ({
  ...(await original<typeof import('react')>()),
  useState: (initial: unknown) => {
    const setter = vi.fn();
    hooks.setters.push(setter);
    return [initial === false ? true : initial, setter];
  },
  useEffect: (effect: () => void) => hooks.effects.push(effect),
}));

import { ClosePrompt } from './ClosePrompt';

interface DialogProps {
  open: boolean;
  actions: { label: string; tone?: string; onClick: () => Promise<void> }[];
}

describe('ClosePrompt', () => {
  beforeEach(() => {
    vi.stubGlobal('window', { __TAURI__: {} });
    core.invoke.mockClear();
    hooks.effects = [];
    hooks.setters = [];
  });
  afterEach(() => vi.unstubAllGlobals());

  it('offers tray as the primary choice and remembers by default', async () => {
    const element = ClosePrompt() as React.ReactElement<DialogProps>;
    const [quit, tray] = element.props.actions;
    expect(tray).toMatchObject({ label: 'closePrompt.tray', tone: 'primary' });
    expect(quit.label).toBe('closePrompt.quit');

    await tray.onClick();
    expect(core.invoke).toHaveBeenCalledWith('resolve_close', { choice: 'tray', remember: true });
    await quit.onClick();
    expect(core.invoke).toHaveBeenCalledWith('resolve_close', { choice: 'quit', remember: true });
  });

  it('acknowledges the shell prompt so the window is not hidden behind the dialog', async () => {
    ClosePrompt();
    hooks.effects.forEach((effect) => effect());
    await vi.waitFor(() => expect(events.handler).not.toBeNull());

    events.handler?.({ payload: 7 });
    expect(core.invoke).toHaveBeenCalledWith('ack_close_prompt', { seq: 7 });
    const [setOpen, setRemember] = hooks.setters;
    expect(setOpen).toHaveBeenCalledWith(true);
    expect(setRemember).toHaveBeenCalledWith(true);
  });

  it('renders nothing in the browser build', () => {
    vi.stubGlobal('window', {});
    expect(ClosePrompt()).toBeNull();
  });
});
