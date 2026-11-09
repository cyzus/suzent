import React from 'react';
import { useI18n } from '../../i18n';

interface StreamingPeekButtonProps {
  visible: boolean;
  onClick: () => void;
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
  React.useEffect(() => {
    if (styleInjected || typeof document === 'undefined') return;
    const el = document.createElement('style');
    el.setAttribute('data-suzent-streaming-peek', '');
    el.textContent = STYLE;
    document.head.appendChild(el);
    styleInjected = true;
  }, []);
}

export const StreamingPeekButton: React.FC<StreamingPeekButtonProps> = React.memo(
  ({ visible, onClick }) => {
    const { t } = useI18n();
    usePeekStyles();

    const label = t('chatWindow.scrollToBottom');

    return (
      <div
        className="pointer-events-none absolute inset-x-0 bottom-full z-10 flex justify-center overflow-hidden"
        aria-hidden={!visible}
      >
        <button
          type="button"
          tabIndex={visible ? 0 : -1}
          onClick={onClick}
          title={label}
          aria-label={label}
          className={`suzent-peek-btn flex flex-col items-center px-4 pt-1.5 pb-0 overflow-hidden text-brutal-black dark:text-white focus:outline-none ${
            visible ? 'is-visible pointer-events-auto cursor-pointer' : 'pointer-events-none'
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
