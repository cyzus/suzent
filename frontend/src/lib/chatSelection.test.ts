import { describe, expect, it } from 'vitest';
import {
  applySelection,
  isDeleteShortcut,
  isSelectAllShortcut,
  selectionIntent,
  type SelectionState,
} from './chatSelection';

const click = (keys: Partial<{ metaKey: boolean; ctrlKey: boolean; shiftKey: boolean }> = {}) => ({
  metaKey: false,
  ctrlKey: false,
  shiftKey: false,
  ...keys,
});

const key = (
  name: string,
  keys: Partial<{ metaKey: boolean; ctrlKey: boolean; shiftKey: boolean; altKey: boolean }> = {}
) => ({ key: name, altKey: false, ...click(keys), ...keys });

const order = ['a', 'b', 'c', 'd', 'e'];
const state = (selected: string[], anchor: string | null): SelectionState => ({
  selected: new Set(selected),
  anchor,
});

describe('selectionIntent', () => {
  it('toggles with Command on macOS and Control elsewhere', () => {
    expect(selectionIntent(click({ metaKey: true }), 'macos')).toBe('toggle');
    expect(selectionIntent(click({ ctrlKey: true }), 'windows')).toBe('toggle');
    expect(selectionIntent(click({ ctrlKey: true }), 'linux')).toBe('toggle');
  });

  it('does not treat the other platform modifier as a toggle', () => {
    expect(selectionIntent(click({ metaKey: true }), 'windows')).toBe('replace');
  });

  it('leaves Control-click on macOS to the context menu', () => {
    expect(selectionIntent(click({ ctrlKey: true }), 'macos')).toBe('ignore');
  });

  it('selects a range with Shift and extends it with the toggle key held', () => {
    expect(selectionIntent(click({ shiftKey: true }), 'macos')).toBe('range');
    expect(selectionIntent(click({ shiftKey: true, metaKey: true }), 'macos')).toBe('rangeAdd');
    expect(selectionIntent(click({ shiftKey: true, ctrlKey: true }), 'windows')).toBe('rangeAdd');
  });
});

describe('applySelection', () => {
  it('toggles one item and moves the anchor to it', () => {
    const next = applySelection(state(['a'], 'a'), order, 'c', 'toggle');
    expect([...next.selected]).toEqual(['a', 'c']);
    expect(next.anchor).toBe('c');
    expect([...applySelection(next, order, 'a', 'toggle').selected]).toEqual(['c']);
  });

  it('replaces the selection with a range from the anchor in either direction', () => {
    expect([...applySelection(state(['b', 'e'], 'b'), order, 'd', 'range').selected]).toEqual([
      'b',
      'c',
      'd',
    ]);
    expect([...applySelection(state([], 'd'), order, 'b', 'range').selected]).toEqual([
      'b',
      'c',
      'd',
    ]);
  });

  it('keeps the anchor across range clicks so the range can be resized', () => {
    const first = applySelection(state(['b'], 'b'), order, 'e', 'range');
    const second = applySelection(first, order, 'c', 'range');
    expect([...second.selected]).toEqual(['b', 'c']);
  });

  it('adds a range to the existing selection', () => {
    const next = applySelection(state(['a'], 'c'), order, 'e', 'rangeAdd');
    expect([...next.selected].sort()).toEqual(['a', 'c', 'd', 'e']);
  });

  it('selects only the clicked item when the anchor is missing or off screen', () => {
    expect([...applySelection(state([], null), order, 'c', 'range').selected]).toEqual(['c']);
    expect([...applySelection(state([], 'gone'), order, 'c', 'range').selected]).toEqual(['c']);
  });
});

describe('keyboard shortcuts', () => {
  it('selects all with Command-A on macOS and Ctrl-A elsewhere', () => {
    expect(isSelectAllShortcut(key('a', { metaKey: true }), 'macos')).toBe(true);
    expect(isSelectAllShortcut(key('a', { ctrlKey: true }), 'macos')).toBe(false);
    expect(isSelectAllShortcut(key('A', { ctrlKey: true }), 'windows')).toBe(true);
    expect(isSelectAllShortcut(key('a'), 'linux')).toBe(false);
  });

  it('deletes with Delete everywhere and Command-Backspace on macOS', () => {
    expect(isDeleteShortcut(key('Delete'), 'windows')).toBe(true);
    expect(isDeleteShortcut(key('Delete'), 'macos')).toBe(true);
    expect(isDeleteShortcut(key('Backspace', { metaKey: true }), 'macos')).toBe(true);
    expect(isDeleteShortcut(key('Backspace'), 'macos')).toBe(false);
    expect(isDeleteShortcut(key('Backspace', { ctrlKey: true }), 'windows')).toBe(false);
  });
});
