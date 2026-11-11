/**
 * Decide whether a right-click belongs to the app menu or to the browser.
 *
 * Links, fields, and a mouse right-click inside an existing text selection keep
 * the menu the browser (or the desktop shell's edit menu) already provides.
 * A touch long-press often highlights a word before `contextmenu` fires; that
 * is still the row's menu, so only a real mouse right-click defers to the
 * selection.
 */

export interface ContextMenuElement {
  closest(selector: string): unknown;
}

export interface ContextMenuSelection {
  isCollapsed: boolean;
  toString(): string;
  containsNode?(node: Node, partialContainment?: boolean): boolean;
}

export interface ContextMenuPointer {
  button?: number;
  pointerType?: string;
}

const NATIVE_TARGET_SELECTOR =
  'input, textarea, select, [contenteditable="true"], a[href], img, video, audio';

export function asContextMenuElement(target: EventTarget | null): ContextMenuElement | null {
  if (!target || typeof target !== 'object') return null;
  const candidate = target as unknown as ContextMenuElement & {
    parentElement?: ContextMenuElement | null;
  };
  if (typeof candidate.closest === 'function') return candidate;
  const parent = candidate.parentElement;
  if (parent && typeof parent.closest === 'function') return parent;
  return null;
}

export function isNativeLinkTarget(target: EventTarget | null): boolean {
  return Boolean(asContextMenuElement(target)?.closest('a[href]'));
}

export function isNativeMediaTarget(target: EventTarget | null): boolean {
  return Boolean(asContextMenuElement(target)?.closest('img, video, audio'));
}

export function prefersNativeContextMenu(
  target: EventTarget | null,
  selection: ContextMenuSelection | null,
  pointer: ContextMenuPointer = {}
): boolean {
  const element = asContextMenuElement(target);
  if (element?.closest(NATIVE_TARGET_SELECTOR)) return true;

  const mouseRightClick = pointer.pointerType !== 'touch' && pointer.button === 2;
  if (!mouseRightClick || !selection || selection.isCollapsed) return false;
  if (!selection.toString()) return false;
  if (!element || typeof selection.containsNode !== 'function') return false;
  try {
    return selection.containsNode(element as unknown as Node, true);
  } catch {
    return false;
  }
}

/** Claim the event for an app menu. Returns false when the browser should keep it. */
export function claimContextMenu(
  event: {
    target: EventTarget | null;
    button?: number;
    pointerType?: string;
    preventDefault(): void;
    stopPropagation(): void;
  },
  selection: ContextMenuSelection | null
): boolean {
  if (
    prefersNativeContextMenu(event.target, selection, {
      button: event.button,
      pointerType: event.pointerType,
    })
  ) {
    return false;
  }
  event.preventDefault();
  event.stopPropagation();
  return true;
}
