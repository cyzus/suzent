import { useEffect, useRef } from 'react';

// Spelled out rather than read off the `Node` global, which does not exist in
// the test environment.
const DOCUMENT_POSITION_PRECEDING = 2;
const DOCUMENT_POSITION_FOLLOWING = 4;
const DOCUMENT_POSITION_CONTAINED_BY = 16;

/**
 * Where a selection focus that escaped the container should be pulled back to.
 * `null` means the focus is still inside and needs no clamping.
 */
export type ClampTarget = 'start' | 'end' | null;

/**
 * Decide which edge of `container` an out-of-bounds selection focus maps to.
 *
 * Exported for testing: the DOM plumbing around it is hard to exercise in
 * jsdom, but this is where the actual decision lives.
 */
export function resolveClampTarget(container: Node, focusNode: Node | null): ClampTarget {
  if (!focusNode) return null;
  if (focusNode === container) return null;

  const position = container.compareDocumentPosition(focusNode);
  if (position & DOCUMENT_POSITION_CONTAINED_BY) return null;
  if (position & DOCUMENT_POSITION_PRECEDING) return 'start';
  if (position & DOCUMENT_POSITION_FOLLOWING) return 'end';

  // Disconnected (e.g. the node was re-rendered away mid-drag): leave it alone.
  return null;
}

/**
 * Keep a drag-selection that started inside `ref` from escaping it.
 *
 * Native selection is linear over the document, not box-shaped: nudging the
 * cursor a few pixels above a long code line swallows every block above it.
 * CSS `user-select: contain` is specified for exactly this but Chrome does not
 * implement it, so we clamp the focus edge by hand while the pointer is down.
 */
export function useSelectionContainment<T extends HTMLElement>(
  ref: React.RefObject<T | null>,
  enabled = true
) {
  const isDraggingRef = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || !enabled) return;

    const onPointerDown = (event: PointerEvent) => {
      // Only a primary-button drag creates a selection.
      if (event.button === 0) isDraggingRef.current = true;
    };

    const endDrag = () => {
      isDraggingRef.current = false;
    };

    const onSelectionChange = () => {
      if (!isDraggingRef.current) return;

      const selection = window.getSelection();
      if (!selection || selection.rangeCount === 0) return;

      // The drag must have started inside us; otherwise it is someone else's
      // selection that merely happens to pass through.
      const { anchorNode, focusNode } = selection;
      if (!anchorNode || !el.contains(anchorNode)) return;

      const target = resolveClampTarget(el, focusNode);
      if (!target) return;

      try {
        selection.extend(el, target === 'start' ? 0 : el.childNodes.length);
      } catch {
        // extend() throws if the selection was torn down between the event and
        // this call; nothing useful to do but let the native behaviour stand.
      }
    };

    el.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('pointerup', endDrag);
    window.addEventListener('pointercancel', endDrag);
    document.addEventListener('selectionchange', onSelectionChange);

    return () => {
      el.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('pointerup', endDrag);
      window.removeEventListener('pointercancel', endDrag);
      document.removeEventListener('selectionchange', onSelectionChange);
      isDraggingRef.current = false;
    };
  }, [ref, enabled]);
}
