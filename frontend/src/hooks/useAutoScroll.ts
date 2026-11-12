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

// The stale scroll layer after a resize is a WebKit compositor bug, not a Tauri
// one: Safari and WebKitGTK are affected too. Chromium-based UAs also say
// "AppleWebKit", so they have to be excluded explicitly.
function isWebKitEngine(): boolean {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent ?? '';
  return /AppleWebKit/.test(ua) && !/Chrome|Chromium|Edg\/|OPR\//.test(ua);
}

// Block elements whose text is distinctive enough to find again after the
// message holding them is re-rendered from scratch.
const ANCHOR_TEXT_TAGS = new Set([
  'P',
  'LI',
  'PRE',
  'H1',
  'H2',
  'H3',
  'H4',
  'H5',
  'H6',
  'BLOCKQUOTE',
  'TD',
  'TH',
]);

// A sticky header pinned to the viewport top never moves, so anchoring to it
// would never correct anything; out-of-flow boxes do not track the text either.
function isInFlow(node: Element): boolean {
  if (typeof getComputedStyle !== 'function') return true;
  const { position } = getComputedStyle(node);
  return position !== 'sticky' && position !== 'fixed' && position !== 'absolute';
}

export function useAutoScroll(dependencies: unknown[], options: UseAutoScrollOptions = {}) {
  const { tolerance = 50, resetKey, smooth = true } = options;

  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  // A keyed chat subtree replaces the DOM node without remounting this hook.
  // Ref.current alone cannot rebind observers or event listeners to that node.
  const [scrollContainer, setScrollContainer] = useState<HTMLDivElement | null>(null);
  const attachScrollContainer = useCallback((node: HTMLDivElement | null) => {
    scrollContainerRef.current = node;
    setScrollContainer(node);
  }, []);
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

  // Only the bottom-following mode owns scroll geometry. History browsing
  // keeps native anchoring and off-screen rendering optimizations.
  useLayoutEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    el.dataset.followingBottom = String(!showScrollButton);
    return () => {
      delete el.dataset.followingBottom;
    };
  }, [showScrollButton, scrollContainer]);

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

    const pauseFollowing = () => {
      autoScrollEnabledRef.current = false;
      autoScrollInProgress.current = false;
      setShowScrollButton(true);
    };

    const onWheel = (event: WheelEvent) => {
      // Pause before the browser scrolls: streaming resizes can otherwise
      // pull a small upward gesture back into the bottom tolerance zone.
      if (event.deltaY < 0) {
        markUserIntent();
        pauseFollowing();
      } else if (event.deltaY > 0 && !autoScrollEnabledRef.current) {
        markUserIntent();
      }
    };

    let touchY: number | undefined;
    const onTouchStart = (event: TouchEvent) => {
      markUserIntent();
      touchY = event.touches[0]?.clientY;
    };
    const onTouchMove = (event: TouchEvent) => {
      markUserIntent();
      const nextY = event.touches[0]?.clientY;
      if (nextY !== undefined && touchY !== undefined && nextY > touchY) pauseFollowing();
      touchY = nextY;
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
        const target = event.target as HTMLElement | null;
        if (target?.closest('input, textarea, select, [contenteditable="true"]')) return;
        markUserIntent();
        if (
          ['PageUp', 'ArrowUp', 'Home'].includes(event.key) ||
          (event.key === ' ' && event.shiftKey)
        ) {
          pauseFollowing();
        }
      }
    };

    let lastTop = el.scrollTop;
    let lastHeight = el.scrollHeight;
    const onUserScroll = () => {
      const movedUp = el.scrollTop < lastTop - 1 && el.scrollHeight >= lastHeight;
      lastTop = el.scrollTop;
      lastHeight = el.scrollHeight;
      // A held pointer (scrollbar drag) outlives the short intent window.
      const hasIntent = userScrollIntentRef.current || isPointerSelectingRef.current;
      if (hasIntent && movedUp && autoScrollEnabledRef.current) {
        // Within the bottom tolerance a small upward drag would otherwise be
        // pulled straight back down by the next streamed token.
        pauseFollowing();
        return;
      }
      // A deliberate user scroll wins even mid-animation: our own programmatic
      // scrolls never set the intent flag, so this cannot swallow itself.
      if (!hasIntent && autoScrollEnabledRef.current && !smooth) {
        // Layout/anchoring can move scrollTop without resizing an observed
        // box. Streaming must repair that drift too, not wait for another token.
        if (!isSelectionDragActive() && el.scrollHeight - el.scrollTop - el.clientHeight > 1) {
          el.scrollTo({ top: el.scrollHeight, behavior: 'auto' });
        }
        return;
      }
      if (autoScrollInProgress.current && !hasIntent) return;
      const atBottom = autoScrollEnabledRef.current
        ? isAtBottom(el)
        : el.scrollHeight - el.scrollTop - el.clientHeight <= 1;

      // Collapsing completed activity can clamp a paused viewport to the end.
      // That is not a request to follow the tail when content grows again.
      if (atBottom && (autoScrollEnabledRef.current || hasIntent)) {
        autoScrollInProgress.current = false;
        autoScrollEnabledRef.current = true;
        setShowScrollButton(false);
        return;
      }

      // Ignore layout-induced scroll shifts (resize/text reflow/transition).
      // Only disable autoscroll when there is clear user scroll intent.
      if (!hasIntent) {
        return;
      }

      autoScrollEnabledRef.current = false;
      setShowScrollButton(true);
    };

    el.addEventListener('scroll', onUserScroll, { passive: true });
    el.addEventListener('wheel', onWheel, { passive: true });
    el.addEventListener('touchstart', onTouchStart, { passive: true });
    el.addEventListener('touchmove', onTouchMove, { passive: true });
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
      el.removeEventListener('wheel', onWheel);
      el.removeEventListener('touchstart', onTouchStart);
      el.removeEventListener('touchmove', onTouchMove);
      el.removeEventListener('pointerdown', onPointerDown);
      el.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('pointerup', endPointerSelection);
      window.removeEventListener('pointercancel', endPointerSelection);
      window.removeEventListener('blur', endPointerSelection);
      window.removeEventListener('pointermove', onPointerMove);
      if (userScrollIntentTimeoutRef.current) {
        clearTimeout(userScrollIntentTimeoutRef.current);
      }
      userScrollIntentRef.current = false;
      isPointerSelectingRef.current = false;
    };
  }, [isAtBottom, isSelectionDragActive, smooth, scrollContainer]);

  // Helper for programmatically scrolling
  const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const performAutoScroll = useCallback(
    (behavior: ScrollBehavior = 'auto', { force = false }: { force?: boolean } = {}) => {
      const container = scrollContainerRef.current;
      if (!container) return;

      // Keep the viewport still while the user is dragging a text selection.
      if (!force && isSelectionDragActive()) {
        if (!isAtBottom(scrollContainerRef.current)) {
          setShowScrollButton(true);
        }
        return;
      }

      // Set flag to ignore subsequent scroll events triggered by this action
      autoScrollInProgress.current = true;
      container.scrollTo({ top: container.scrollHeight, behavior });

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
            if (atBottom && autoScrollEnabledRef.current) {
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

      // Content updates must not start an animation toward a soon-stale height.
      // In particular, finishing a stream can still reflow its final message.
      performAutoScroll('auto');

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

    let settleFrame = 0;
    let repaintFrame = 0;
    let repaintTimer: ReturnType<typeof setTimeout> | undefined;
    // Undoes a repaint nudge that is mid-flight (scrollTop off by a pixel, or a
    // temporary compositing layer). It must run if the nudge is interrupted,
    // or the transcript would be left offset and autoscroll left suppressed.
    let finishRepaint: (() => void) | null = null;
    let lastWidth = el.clientWidth;
    let lastScrollHeight = el.scrollHeight;

    const cancelPendingRepaint = () => {
      clearTimeout(repaintTimer);
      cancelAnimationFrame(repaintFrame);
      const finish = finishRepaint;
      finishRepaint = null;
      finish?.();
    };

    // When the transcript gets shorter or wider (a sidebar toggle, a collapsed
    // tool block), layout clamps scrollTop but WKWebView's scrolling layer
    // keeps the old offset and shows blank space until the next scroll.
    // Scrollable: a one-pixel round trip over two frames is a real scroll, so
    // it resyncs the layer. Not scrollable (a short chat that now fits): there
    // is nothing to scroll, so a throwaway compositing layer forces the repaint.
    const forceRepaint = () => {
      if (userScrollIntentRef.current || isSelectionDragActive()) return;
      if (el.scrollHeight > el.clientHeight) {
        const top = el.scrollTop;
        autoScrollInProgress.current = true;
        el.scrollTop = top > 0 ? top - 1 : top + 1;
        const nudgedTop = el.scrollTop;
        finishRepaint = () => {
          // Momentum scrolling or a new layout can move the viewport between
          // frames. Never restore a stale position over that newer movement.
          if (
            el.scrollTop !== nudgedTop ||
            userScrollIntentRef.current ||
            isSelectionDragActive()
          ) {
            autoScrollInProgress.current = false;
            return;
          }
          el.scrollTop = top;
          if (autoScrollEnabledRef.current) {
            performAutoScroll('auto');
          } else {
            autoScrollInProgress.current = false;
          }
        };
      } else {
        const previous = el.style.transform;
        el.style.transform = 'translateZ(0)';
        finishRepaint = () => {
          el.style.transform = previous;
        };
      }
      repaintFrame = requestAnimationFrame(() => {
        const finish = finishRepaint;
        finishRepaint = null;
        finish?.();
      });
    };

    // Repaint on the first frames after the layout change, not after a fixed
    // delay: docked sidebars resize instantly, so waiting only prolongs the
    // blank. The trailing pass catches anything that settles later (descendants
    // that reflow after the notification, drags, window resizes).
    const scheduleRepaint = (trailingDelayMs: number) => {
      cancelPendingRepaint();
      repaintFrame = requestAnimationFrame(() => {
        repaintFrame = requestAnimationFrame(forceRepaint);
      });
      repaintTimer = setTimeout(() => {
        cancelPendingRepaint();
        forceRepaint();
      }, trailingDelayMs);
    };
    const needsResizeRepaint = el.closest('.macos-tauri-webview') !== null || isWebKitEngine();

    // WebKit has no native scroll anchoring, so while the user reads above the
    // tail, any height change above the viewport (activity folding when a turn
    // finishes, a streamed block re-rendering) slides the text out from under
    // them. Track the deepest element at the viewport top and hold it in place.
    // The stylesheet disables native anchoring so Chromium does not correct twice.
    let anchor: { node: Element; top: number }[] = [];
    // A finished turn swaps the live message for the saved one, so every node
    // above can disappear at once. The same paragraph exists in the saved copy:
    // remember a text block to find it again.
    let textAnchor: { tag: string; text: string; top: number } | null = null;
    const viewportTop = () => el.getBoundingClientRect().top;
    const captureAnchor = () => {
      anchor = [];
      textAnchor = null;
      if (autoScrollEnabledRef.current || typeof el.getBoundingClientRect !== 'function') return;
      const viewTop = viewportTop();
      let parent: Element = el;
      for (let depth = 0; depth < 16; depth++) {
        let next: Element | undefined;
        for (const child of parent.children) {
          const rect = child.getBoundingClientRect();
          if (rect.height > 0 && rect.bottom > viewTop && isInFlow(child)) {
            next = child;
            anchor.push({ node: child, top: rect.top - viewTop });
            break;
          }
        }
        if (!next) break;
        parent = next;
      }
      for (let i = anchor.length - 1; i >= 0; i--) {
        const { node, top } = anchor[i];
        if (!ANCHOR_TEXT_TAGS.has(node.tagName)) continue;
        const text = node.textContent?.trim() ?? '';
        if (text.length >= 8) {
          textAnchor = { tag: node.tagName, text, top };
          break;
        }
      }
    };
    const findByText = (): Element | null => {
      if (!textAnchor || typeof el.querySelectorAll !== 'function') return null;
      const { tag, text } = textAnchor;
      const matches = Array.from(el.querySelectorAll(tag)).filter(
        (node) => node.textContent?.trim() === text
      );
      // The newest copy is the one that replaced what the user was reading.
      return matches[matches.length - 1] ?? null;
    };
    const restoreAnchor = () => {
      const alignTo = (node: Element, top: number) => {
        const delta = node.getBoundingClientRect().top - viewportTop() - top;
        if (Math.abs(delta) >= 1) el.scrollTop += delta;
      };
      const isLive = (node: Element) => node.isConnected && el.contains(node);
      const deepest = anchor[anchor.length - 1];
      if (deepest && !isLive(deepest.node)) {
        const match = findByText();
        if (match && textAnchor) {
          alignTo(match, textAnchor.top);
          captureAnchor();
          return;
        }
      }
      // Skip the scroller's direct children: a wrapper spanning the whole
      // transcript keeps its top no matter what moved inside it.
      for (let i = anchor.length - 1; i >= 1; i--) {
        if (!isLive(anchor[i].node)) continue;
        alignTo(anchor[i].node, anchor[i].top);
        captureAnchor();
        return;
      }
      if (deepest && !isLive(deepest.node) && typeof el.querySelectorAll === 'function') {
        // Nothing survived (the user was inside activity that has now folded):
        // land on the start of the newest message rather than a clamped tail.
        const rows = el.querySelectorAll('[data-message-index]');
        const last = rows[rows.length - 1];
        if (last) alignTo(last, 0);
      }
      captureAnchor();
    };
    // A turn finishing can lay out a briefly shorter transcript mid-commit, and
    // WebKit clamps scrollTop to it. That scroll event arrives in the same frame
    // as, and before, the resize that should undo it, so capturing here would
    // overwrite the reader's anchor with the clamped spot. Only a user's own
    // scroll is captured at once; any other waits until the resize has run.
    let captureTimer: ReturnType<typeof setTimeout> | undefined;
    const onAnchorScroll = () => {
      clearTimeout(captureTimer);
      if (userScrollIntentRef.current || isSelectionDragActive()) {
        captureAnchor();
        return;
      }
      captureTimer = setTimeout(captureAnchor, 0);
    };
    el.addEventListener('scroll', onAnchorScroll, { passive: true });

    const resizeObserver = new ResizeObserver(() => {
      if (needsResizeRepaint) {
        const widthChanged = el.clientWidth !== lastWidth;
        const shrank = el.scrollHeight < lastScrollHeight;
        lastWidth = el.clientWidth;
        lastScrollHeight = el.scrollHeight;
        if (widthChanged || shrank) {
          scheduleRepaint(widthChanged ? 350 : 100);
        }
      }
      cancelAnimationFrame(settleFrame);
      if (!autoScrollEnabledRef.current) restoreAnchor();
      if (autoScrollEnabledRef.current) {
        performAutoScroll('auto');
        // Sidebar drags can reflow descendants after this resize notification.
        settleFrame = requestAnimationFrame(() => {
          if (autoScrollEnabledRef.current) performAutoScroll('auto');
        });
      }
    });
    const observeMessages = () => {
      resizeObserver.disconnect();
      resizeObserver.observe(el);
      for (const child of el.children) {
        resizeObserver.observe(child);
      }
    };
    observeMessages();

    // Messages are siblings; the last one can grow after streaming finishes.
    const mutationObserver = new MutationObserver(observeMessages);
    mutationObserver.observe(el, { childList: true });

    return () => {
      el.removeEventListener('scroll', onAnchorScroll);
      clearTimeout(captureTimer);
      cancelAnimationFrame(settleFrame);
      cancelPendingRepaint();
      mutationObserver.disconnect();
      resizeObserver.disconnect();
    };
  }, [performAutoScroll, scrollContainer, isSelectionDragActive]);

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

  // Always a jump: callers fire this right before content arrives (a send, an
  // approval), and WKWebView leaves its scroll layer blank when the layout
  // changes under a smooth scroll, until the user scrolls by hand.
  const scrollToBottom = useCallback(() => {
    autoScrollEnabledRef.current = true;
    setShowScrollButton(false);
    userScrollIntentRef.current = false;
    performAutoScroll('auto', { force: true });
  }, [performAutoScroll]);

  return {
    scrollContainerRef,
    attachScrollContainer,
    bottomRef,
    showScrollButton,
    scrollToBottom,
    /** True only while a pointer drag is in progress inside the scroller. */
    isSelectionDragActive,
  };
}
