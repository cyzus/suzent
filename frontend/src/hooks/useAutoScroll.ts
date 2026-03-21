import { useEffect, useRef, useState, useCallback } from 'react';

interface UseAutoScrollOptions {
  tolerance?: number;
}

export function useAutoScroll(
  dependencies: any[],
  options: UseAutoScrollOptions = {}
) {
  const { tolerance = 50 } = options;

  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const autoScrollEnabledRef = useRef(true);
  const [showScrollButton, setShowScrollButton] = useState(false);

  // Helper to determine if at bottom
  const isAtBottom = useCallback((el: Element | null) => {
    if (!el) return true;
    // Allow a larger tolerance for pixel rounding and intermediate layout shifts
    return el.scrollHeight - el.scrollTop - el.clientHeight <= tolerance + 10;
  }, [tolerance]);

  // Use a ref to ignore scroll events triggered by our own programmatic scrolling
  const autoScrollInProgress = useRef(false);
  const userScrollIntentRef = useRef(false);
  const userScrollIntentTimeoutRef = useRef<NodeJS.Timeout | null>(null);

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

    const onUserScroll = () => {
      if (autoScrollInProgress.current) return;
      const atBottom = isAtBottom(el);

      // Always re-enable autoscroll once we are back at bottom.
      if (atBottom) {
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
    el.addEventListener('pointerdown', markUserIntent, { passive: true });

    return () => {
      el.removeEventListener('scroll', onUserScroll);
      el.removeEventListener('wheel', markUserIntent);
      el.removeEventListener('touchstart', markUserIntent);
      el.removeEventListener('pointerdown', markUserIntent);
      if (userScrollIntentTimeoutRef.current) {
        clearTimeout(userScrollIntentTimeoutRef.current);
      }
    };
  }, [isAtBottom]);

  // Helper for programmatically scrolling
  const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  const performAutoScroll = useCallback((behavior: ScrollBehavior = 'auto') => {
    if (!bottomRef.current) return;
    
    // Set flag to ignore subsequent scroll events triggered by this action
    autoScrollInProgress.current = true;
    bottomRef.current.scrollIntoView({ behavior });
    
    if (scrollTimeoutRef.current) {
      clearTimeout(scrollTimeoutRef.current);
    }
    
    // Reset flag after browser has had time to process the scroll
    scrollTimeoutRef.current = setTimeout(() => {
      autoScrollInProgress.current = false;
      
      // Double check if we need to update state after forced scroll
      if (scrollContainerRef.current) {
        const atBottom = isAtBottom(scrollContainerRef.current);
        if (atBottom) {
          setShowScrollButton(false);
          autoScrollEnabledRef.current = true;
        }
      }
    }, 150); // Give enough time for 'auto' or basic scrolling to settle
  }, [isAtBottom]);

  // Auto-scroll when dependencies change
  useEffect(() => {
    if (autoScrollEnabledRef.current) {
      performAutoScroll('smooth');

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
    performAutoScroll('smooth');
  }, [performAutoScroll]);

  return {
    scrollContainerRef,
    bottomRef,
    showScrollButton,
    scrollToBottom
  };
}
