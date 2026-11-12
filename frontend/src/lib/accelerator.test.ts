import { describe, expect, it } from 'vitest';
import { acceleratorFromKeyPress, acceleratorKeycaps } from './accelerator';

const press = (
  code: string,
  mods: Partial<Record<'ctrl' | 'meta' | 'alt' | 'shift', boolean>> = {}
) => ({
  code,
  ctrlKey: !!mods.ctrl,
  metaKey: !!mods.meta,
  altKey: !!mods.alt,
  shiftKey: !!mods.shift,
});

describe('acceleratorFromKeyPress', () => {
  it('maps Ctrl on Windows and Cmd on macOS to CommandOrControl', () => {
    expect(acceleratorFromKeyPress(press('Space', { ctrl: true, shift: true }), false)).toEqual({
      kind: 'done',
      accelerator: 'CommandOrControl+Shift+Space',
    });
    expect(acceleratorFromKeyPress(press('KeyK', { meta: true }), true)).toEqual({
      kind: 'done',
      accelerator: 'CommandOrControl+K',
    });
  });

  it('keeps Control distinct from Cmd on macOS', () => {
    expect(acceleratorFromKeyPress(press('Digit1', { ctrl: true, alt: true }), true)).toEqual({
      kind: 'done',
      accelerator: 'Control+Alt+1',
    });
  });

  it('reports held modifiers while waiting for the key', () => {
    expect(acceleratorFromKeyPress(press('ShiftLeft', { ctrl: true, shift: true }), false)).toEqual(
      {
        kind: 'partial',
        modifiers: ['CommandOrControl', 'Shift'],
      }
    );
  });

  it('refuses keys that would steal typing', () => {
    expect(acceleratorFromKeyPress(press('KeyA'), false).kind).toBe('needs_modifier');
    expect(acceleratorFromKeyPress(press('KeyA', { shift: true }), false).kind).toBe(
      'needs_modifier'
    );
  });

  it('allows function keys on their own', () => {
    expect(acceleratorFromKeyPress(press('F13'), false)).toEqual({
      kind: 'done',
      accelerator: 'F13',
    });
  });

  it('rejects keys the shortcut API cannot name', () => {
    expect(acceleratorFromKeyPress(press('Numpad5', { ctrl: true }), false).kind).toBe(
      'unsupported'
    );
  });
});

describe('acceleratorKeycaps', () => {
  it('labels keys per platform', () => {
    const parts = 'CommandOrControl+Shift+Space'.split('+');
    expect(acceleratorKeycaps(parts, true)).toEqual(['⌘', '⇧', 'Space']);
    expect(acceleratorKeycaps(parts, false)).toEqual(['Ctrl', 'Shift', 'Space']);
    expect(acceleratorKeycaps(['Alt', 'Backquote'], false)).toEqual(['Alt', '`']);
  });
});
