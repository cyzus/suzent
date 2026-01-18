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
    return el.scrollHeight - el.scrollTop - el.clientHeight <= tolerance;
  }, [tolerance]);

  // Set up scroll listeners
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;

    const onUserScroll = () => {
      const atBottom = isAtBottom(el);
      autoScrollEnabledRef.current = atBottom;
      setShowScrollButton(!atBottom);
    };

    el.addEventListener('scroll', onUserScroll, { passive: true });
    el.addEventListener('wheel', onUserScroll, { passive: true });
    el.addEventListener('touchstart', onUserScroll, { passive: true });

    return () => {
      el.removeEventListener('scroll', onUserScroll);
      el.removeEventListener('wheel', onUserScroll);
      el.removeEventListener('touchstart', onUserScroll);
    };
  }, [isAtBottom]);

  // Auto-scroll when dependencies change
  useEffect(() => {
    if (autoScrollEnabledRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, dependencies);

  // Manual scroll to bottom
  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    autoScrollEnabledRef.current = true;
    setShowScrollButton(false);
  }, []);

  return {
    scrollContainerRef,
    bottomRef,
    showScrollButton,
    scrollToBottom
  };
}
