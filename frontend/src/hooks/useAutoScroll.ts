import { useEffect, useLayoutEffect, useRef, useState, useCallback } from 'react';

interface UseAutoScrollOptions {
  tolerance?: number;
  resetKey?: unknown;
  /**
   * Set to false while content streams in: high-frequency smooth scrolls
   * fight each other and make the viewport crawl behind the content.
   */
  smooth?: boolean;
}

export function useAutoScroll(dependencies: any[], options: UseAutoScrollOptions = {}) {
  const { tolerance = 50, resetKey, smooth = true } = options;

  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const autoScrollEnabledRef = useRef(true);
  const [showScrollButton, setShowScrollButton] = useState(false);

  // Helper to determine if at bottom
  const isAtBottom = useCallback(
    (el: Element | null) => {
      if (!el) return true;
      // Allow a larger tolerance for pixel rounding and intermediate layout shifts
      return el.scrollHeight - el.scrollTop - el.clientHeight <= tolerance + 10;
    },
    [tolerance]
  );

  // Use a ref to ignore scroll events triggered by our own programmatic scrolling
  const autoScrollInProgress = useRef(false);
  const userScrollIntentRef = useRef(false);
  const userScrollIntentTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // While the user is selecting text inside the scroller, any programmatic
  // scroll drags the content out from under the cursor and the browser extends
  // the selection to whatever text lands there — the classic "selection drift".
  const isPointerSelectingRef = useRef(false);

  // Deliberately scoped to a live drag rather than "a selection exists": a
  // resting selection stays anchored to its own DOM nodes, so scrolling or
  // prepending around it is harmless. Gating on a resting selection instead
  // wedges the scroller — autoscroll and older-message loading both stop until
  // the user happens to click the selection away.
  const isSelectionDragActive = useCallback(() => isPointerSelectingRef.current, []);

  // Set up scroll listeners
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;

    const markUserIntent = () => {
      userScrollIntentRef.current = true;
      if (userScrollIntentTimeoutRef.current) {
        clearTimeout(userScrollIntentTimeoutRef.current);
      }
      userScrollIntentTimeoutRef.current = setTimeout(() => {
        userScrollIntentRef.current = false;
      }, 250);
    };

    const onPointerDown = (event: PointerEvent) => {
      markUserIntent();
      // Only a primary-button drag can create a selection.
      if (event.button === 0) {
        isPointerSelectingRef.current = true;
      }
    };

    const endPointerSelection = () => {
      isPointerSelectingRef.current = false;
    };

    const onPointerMove = (event: PointerEvent) => {
      if (isPointerSelectingRef.current && event.buttons === 0) {
        endPointerSelection();
      }
    };

    // Keyboard scrolling produces a bare scroll event with no wheel/pointer to
    // pair it with; without this it reads as a layout shift and gets ignored.
    const SCROLL_KEYS = new Set([
      'PageUp',
      'PageDown',
      'ArrowUp',
      'ArrowDown',
      'Home',
      'End',
      ' ',
      'Spacebar',
    ]);
    const onKeyDown = (event: KeyboardEvent) => {
      if (SCROLL_KEYS.has(event.key)) {
        markUserIntent();
      }
    };

    const onUserScroll = () => {
      // A deliberate user scroll wins even mid-animation: our own programmatic
      // scrolls never set the intent flag, so this cannot swallow itself.
      if (autoScrollInProgress.current && !userScrollIntentRef.current) return;
      const atBottom = isAtBottom(el);

      // Always re-enable autoscroll once we are back at bottom.
      if (atBottom) {
        autoScrollInProgress.current = false;
        autoScrollEnabledRef.current = true;
        setShowScrollButton(false);
        return;
      }

      // Ignore layout-induced scroll shifts (resize/text reflow/transition).
      // Only disable autoscroll when there is clear user scroll intent.
      if (!userScrollIntentRef.current) {
        return;
      }

      autoScrollEnabledRef.current = false;
      setShowScrollButton(true);
    };

    el.addEventListener('scroll', onUserScroll, { passive: true });
    el.addEventListener('wheel', markUserIntent, { passive: true });
    el.addEventListener('touchstart', markUserIntent, { passive: true });
    el.addEventListener('pointerdown', onPointerDown, { passive: true });
    el.addEventListener('keydown', onKeyDown, { passive: true });
    window.addEventListener('pointerup', endPointerSelection, { passive: true });
    window.addEventListener('pointercancel', endPointerSelection, { passive: true });
    // Insurance against a dropped pointerup (release outside the window, a
    // swallowed event): a stuck flag would silently wedge the scroller.
    window.addEventListener('blur', endPointerSelection);
    window.addEventListener('pointermove', onPointerMove, { passive: true });

    return () => {
      el.removeEventListener('scroll', onUserScroll);
      el.removeEventListener('wheel', markUserIntent);
      el.removeEventListener('touchstart', markUserIntent);
      el.removeEventListener('pointerdown', onPointerDown);
      el.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('pointerup', endPointerSelection);
      window.removeEventListener('pointercancel', endPointerSelection);
      window.removeEventListener('blur', endPointerSelection);
      window.removeEventListener('pointermove', onPointerMove);
      if (userScrollIntentTimeoutRef.current) {
        clearTimeout(userScrollIntentTimeoutRef.current);
      }
    };
  }, [isAtBottom]);

  // Helper for programmatically scrolling
  const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const performAutoScroll = useCallback(
    (behavior: ScrollBehavior = 'auto', { force = false }: { force?: boolean } = {}) => {
      if (!bottomRef.current) return;

      // Never move the viewport under an in-progress or existing selection —
      // doing so makes the selection run away from the cursor. Autoscroll stays
      // armed and resumes as soon as the selection is cleared.
      if (!force && isSelectionDragActive()) {
        if (!isAtBottom(scrollContainerRef.current)) {
          setShowScrollButton(true);
        }
        return;
      }

      // Set flag to ignore subsequent scroll events triggered by this action
      autoScrollInProgress.current = true;
      bottomRef.current.scrollIntoView({ behavior });

      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }

      // Reset flag after browser has had time to process the scroll.
      // A smooth scroll animates well past the 150ms an instant jump needs.
      scrollTimeoutRef.current = setTimeout(
        () => {
          autoScrollInProgress.current = false;

          // Double check if we need to update state after forced scroll
          if (scrollContainerRef.current) {
            const atBottom = isAtBottom(scrollContainerRef.current);
            if (atBottom) {
              setShowScrollButton(false);
              autoScrollEnabledRef.current = true;
            }
          }
        },
        behavior === 'smooth' ? 450 : 150
      );
    },
    [isAtBottom, isSelectionDragActive]
  );

  const previousResetKeyRef = useRef(resetKey);
  const skipNextSmoothScrollRef = useRef(false);

  useLayoutEffect(() => {
    if (previousResetKeyRef.current === resetKey) return;

    previousResetKeyRef.current = resetKey;
    skipNextSmoothScrollRef.current = true;
    autoScrollEnabledRef.current = true;
    setShowScrollButton(false);
    // Switching chats: any selection belongs to the outgoing conversation.
    performAutoScroll('auto', { force: true });
  }, [resetKey, performAutoScroll]);

  // Auto-scroll when dependencies change
  useEffect(() => {
    if (autoScrollEnabledRef.current) {
      if (skipNextSmoothScrollRef.current) {
        skipNextSmoothScrollRef.current = false;
        performAutoScroll('auto');
        return;
      }

      performAutoScroll(smooth ? 'smooth' : 'auto');

      // Re-apply after layout transitions (e.g. sidebar width animation)
      // to avoid being left slightly above bottom after rapid toggle/resizes.
      const settleTimer = setTimeout(() => {
        if (autoScrollEnabledRef.current) {
          performAutoScroll('auto');
        }
      }, 360);

      return () => clearTimeout(settleTimer);
    }
  }, dependencies);

  // ResizeObserver to handle layout changes (like sidebar toggles causing text wraps)
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;

    const resizeObserver = new ResizeObserver(() => {
      if (autoScrollEnabledRef.current) {
        performAutoScroll('auto');
      }
    });

    // Observe the single child or the element itself
    resizeObserver.observe(el);
    if (el.firstElementChild) {
      resizeObserver.observe(el.firstElementChild);
    }

    return () => resizeObserver.disconnect();
  }, [performAutoScroll]);

  useEffect(() => {
    return () => {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
      if (userScrollIntentTimeoutRef.current) {
        clearTimeout(userScrollIntentTimeoutRef.current);
      }
    };
  }, []);

  // Manual scroll to bottom
  const scrollToBottom = useCallback(() => {
    autoScrollEnabledRef.current = true;
    setShowScrollButton(false);
    performAutoScroll('smooth', { force: true });
  }, [performAutoScroll]);

  return {
    scrollContainerRef,
    bottomRef,
    showScrollButton,
    scrollToBottom,
    /** True only while a pointer drag is in progress inside the scroller. */
    isSelectionDragActive,
  };
}
