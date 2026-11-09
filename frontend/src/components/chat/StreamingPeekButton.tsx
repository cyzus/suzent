import React, { useEffect, useState } from 'react';
import { useI18n } from '../../i18n';

interface StreamingPeekButtonProps {
  visible: boolean;
  scrollContainerRef?: React.RefObject<HTMLDivElement | null>;
  onClick: () => void;
}

/**
 * Returns true only when the active turn (the latest message / streaming row,
 * or the user prompt right above it) has scrolled completely out of the
 * scroller's viewport. If any part of the latest user message or streaming
 * reply is still visible on screen, the user already sees the live turn and
 * does not need the peeking indicator yet.
 */
export function isActiveTurnOutOfView(scroller: HTMLElement | null): boolean {
  if (!scroller) return true;
  const rows = scroller.querySelectorAll<HTMLElement>('[data-message-index]');
  if (rows.length === 0) return false;

  const scrollerRect = scroller.getBoundingClientRect();
  if (scrollerRect.height <= 0) return false;

  const lastRow = rows[rows.length - 1];
  const prevRow = rows.length >= 2 ? rows[rows.length - 2] : null;
  const topAnchorRow = prevRow?.classList.contains('chat-msg-row-user') ? prevRow : lastRow;

  const topRect = topAnchorRow.getBoundingClientRect();
  // `topRect.top` is the top edge of the user's last prompt (or the live turn).
  // Once the user scrolls up far enough that even this top edge is pushed below
  // the bottom of the scroll viewport (with a 16px threshold), the entire
  // active turn is out of view below the fold.
  return topRect.top >= scrollerRect.bottom - 16;
}

const STYLE = `
@keyframes suzentPeekBreathe {
  0%, 100% { transform: translateY(6px); }
  50%      { transform: translateY(2.5px); }
}
@keyframes suzentPeekEyeScan {
  0%, 100% { transform: translateX(0); }
  25%      { transform: translateX(-1.8px); }
  75%      { transform: translateX(1.8px); }
}
@keyframes suzentPeekArrowBob {
  0%, 100% { transform: translateY(-1.5px); }
  50%      { transform: translateY(1.5px); }
}
.suzent-peek-btn .suzent-peek-head {
  transform: translateY(6px);
  transition: transform 200ms cubic-bezier(0.16, 1, 0.3, 1);
  animation: suzentPeekBreathe 2.4s ease-in-out infinite;
}
.suzent-peek-btn:not(.is-visible) .suzent-peek-head {
  animation: none;
  transform: translateY(calc(100% + 2px));
}
.suzent-peek-btn.is-visible:is(:hover, :focus-visible) .suzent-peek-head {
  animation: none;
  transform: translateY(0);
}
.suzent-peek-btn .suzent-peek-eyes {
  animation: suzentPeekEyeScan 2.2s ease-in-out infinite;
}
.suzent-peek-btn .suzent-peek-arrow {
  opacity: 0;
  transform: translateY(6px) scale(0.85);
  transition:
    opacity 160ms cubic-bezier(0.16, 1, 0.3, 1),
    transform 160ms cubic-bezier(0.16, 1, 0.3, 1);
}
.suzent-peek-btn.is-visible:is(:hover, :focus-visible) .suzent-peek-arrow {
  opacity: 1;
  transform: translateY(0) scale(1);
  animation: suzentPeekArrowBob 1s ease-in-out infinite;
}
@media (prefers-reduced-motion: reduce) {
  .suzent-peek-btn .suzent-peek-head,
  .suzent-peek-btn .suzent-peek-eyes,
  .suzent-peek-btn.is-visible:is(:hover, :focus-visible) .suzent-peek-arrow {
    animation: none;
  }
  .suzent-peek-btn.is-visible .suzent-peek-head {
    transform: translateY(4px);
  }
}
`;

let styleInjected = false;
function usePeekStyles() {
  useEffect(() => {
    if (styleInjected || typeof document === 'undefined') return;
    const el = document.createElement('style');
    el.setAttribute('data-suzent-streaming-peek', '');
    el.textContent = STYLE;
    document.head.appendChild(el);
    styleInjected = true;
  }, []);
}

export const StreamingPeekButton: React.FC<StreamingPeekButtonProps> = React.memo(
  ({ visible, scrollContainerRef, onClick }) => {
    const { t } = useI18n();
    usePeekStyles();

    const [turnOutOfView, setTurnOutOfView] = useState(true);

    useEffect(() => {
      if (!visible || !scrollContainerRef) {
        setTurnOutOfView(!scrollContainerRef);
        return;
      }
      const el = scrollContainerRef.current;
      if (!el) {
        setTurnOutOfView(true);
        return;
      }

      const check = () => {
        setTurnOutOfView(isActiveTurnOutOfView(el));
      };
      check();

      el.addEventListener('scroll', check, { passive: true });
      window.addEventListener('resize', check, { passive: true });
      const mutationObserver =
        typeof MutationObserver !== 'undefined' ? new MutationObserver(check) : null;
      mutationObserver?.observe(el, { childList: true, subtree: true });

      return () => {
        el.removeEventListener('scroll', check);
        window.removeEventListener('resize', check);
        mutationObserver?.disconnect();
      };
    }, [visible, scrollContainerRef]);

    const actuallyVisible = visible && turnOutOfView;
    const label = t('chatWindow.scrollToBottom');

    return (
      <div
        className="pointer-events-none absolute inset-x-0 bottom-full z-10 flex justify-center overflow-hidden"
        aria-hidden={!actuallyVisible}
      >
        <button
          type="button"
          tabIndex={actuallyVisible ? 0 : -1}
          onClick={onClick}
          title={label}
          aria-label={label}
          className={`suzent-peek-btn flex flex-col items-center px-4 pt-1.5 pb-0 overflow-hidden text-brutal-black dark:text-white focus:outline-none ${
            actuallyVisible
              ? 'is-visible pointer-events-auto cursor-pointer'
              : 'pointer-events-none'
          }`}
        >
          <svg
            className="suzent-peek-arrow mb-[3px] drop-shadow-[0_1px_0_rgba(250,250,250,1)] dark:drop-shadow-[0_1px_0_rgba(24,24,27,1)]"
            width="16"
            height="11"
            viewBox="0 0 14 10"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M2.5 2.5L7 7l4.5-4.5" />
          </svg>
          <svg
            className="suzent-peek-head"
            width="32"
            height="21"
            viewBox="0 0 24 16"
            fill="none"
            aria-hidden="true"
          >
            <rect x="2" y="1" width="20" height="20" rx="3" fill="currentColor" />
            <g className="suzent-peek-eyes">
              <rect
                x="6"
                y="6.5"
                width="4"
                height="4"
                rx="1"
                className="fill-white dark:fill-zinc-900"
              />
              <rect
                x="14"
                y="6.5"
                width="4"
                height="4"
                rx="1"
                className="fill-white dark:fill-zinc-900"
              />
            </g>
          </svg>
        </button>
      </div>
    );
  }
);

StreamingPeekButton.displayName = 'StreamingPeekButton';
