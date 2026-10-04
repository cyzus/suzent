import type { DesktopPlatform } from './titleBarPlatform';

export type SelectionIntent = 'replace' | 'toggle' | 'range' | 'rangeAdd' | 'ignore';

export interface SelectionState {
  selected: ReadonlySet<string>;
  anchor: string | null;
}

interface ModifierKeys {
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
}

interface ShortcutKeys extends ModifierKeys {
  key: string;
  altKey: boolean;
}

/** The key that adds a single item to a selection: Command on macOS, Control elsewhere. */
function hasToggleModifier(event: ModifierKeys, platform: DesktopPlatform): boolean {
  return platform === 'macos' ? event.metaKey : event.ctrlKey;
}

/**
 * Maps a click's modifier keys to a selection gesture, following each OS's file
 * manager: Command-click (macOS) or Ctrl-click (Windows, Linux) toggles one item,
 * Shift-click selects a range, and both together extend the selection by a range.
 */
export function selectionIntent(event: ModifierKeys, platform: DesktopPlatform): SelectionIntent {
  // Control-click on macOS is a secondary click; the context menu handles it.
  if (platform === 'macos' && event.ctrlKey && !event.metaKey) return 'ignore';
  const toggle = hasToggleModifier(event, platform);
  if (event.shiftKey) return toggle ? 'rangeAdd' : 'range';
  return toggle ? 'toggle' : 'replace';
}

function rangeBetween(order: readonly string[], from: string | null, to: string): string[] {
  const end = order.indexOf(to);
  if (end < 0) return [];
  const start = from ? order.indexOf(from) : -1;
  if (start < 0) return [to];
  const [lo, hi] = start <= end ? [start, end] : [end, start];
  return order.slice(lo, hi + 1);
}

/** Applies a click gesture on `id` to the selection, given the on-screen order of items. */
export function applySelection(
  state: SelectionState,
  order: readonly string[],
  id: string,
  intent: Exclude<SelectionIntent, 'ignore'>
): SelectionState {
  switch (intent) {
    case 'replace':
      return { selected: new Set([id]), anchor: id };
    case 'toggle': {
      const selected = new Set(state.selected);
      if (selected.has(id)) selected.delete(id);
      else selected.add(id);
      return { selected, anchor: id };
    }
    case 'range':
      return {
        selected: new Set(rangeBetween(order, state.anchor, id)),
        anchor: state.anchor ?? id,
      };
    case 'rangeAdd':
      return {
        selected: new Set([...state.selected, ...rangeBetween(order, state.anchor, id)]),
        anchor: state.anchor ?? id,
      };
  }
}

export function isSelectAllShortcut(event: ShortcutKeys, platform: DesktopPlatform): boolean {
  return (
    event.key.toLowerCase() === 'a' &&
    hasToggleModifier(event, platform) &&
    !event.shiftKey &&
    !event.altKey
  );
}

/**
 * Delete removes the selection everywhere. macOS keyboards label Backspace as
 * "delete", and Finder moves items to the Trash with Command-Delete, so that
 * combination counts there too.
 */
export function isDeleteShortcut(event: ShortcutKeys, platform: DesktopPlatform): boolean {
  if (event.key === 'Delete') return true;
  return platform === 'macos' && event.key === 'Backspace' && event.metaKey;
}
