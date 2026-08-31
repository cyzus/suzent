import React from 'react';

import { useI18n } from '../../i18n';
import { type ThinkingEffort } from '../../types/api';

const MANUAL_LEVELS: ThinkingEffort[] = ['low', 'medium', 'high', 'xhigh'];
const LAST_MANUAL_INDEX = MANUAL_LEVELS.length - 1;

type ThinkingMode = 'auto' | 'manual' | 'off';
const NEXT_MODE: Record<ThinkingMode, ThinkingMode> = {
  auto: 'manual',
  manual: 'off',
  off: 'auto',
};

const STYLE = `
.suzent-ts, .suzent-ts * { box-sizing: border-box; }
.suzent-ts {
  --ts-ink: #18181b;
  --ts-paper: #fff;
  --ts-muted: #a1a1aa;
  --ts-sheen: 255, 255, 255;
  --ts-glow: 24, 24, 27;
  display: inline-flex;
  height: 24px;
  align-items: center;
  color: #52525b;
}
.dark .suzent-ts {
  --ts-ink: #f4f4f5;
  --ts-paper: #18181b;
  --ts-muted: #71717a;
  --ts-sheen: 39, 39, 42;
  --ts-glow: 244, 244, 245;
  color: #a1a1aa;
}
.suzent-ts[data-disabled='true'] { opacity: .4; pointer-events: none; }

.suzent-ts__trigger {
  height: 24px;
  flex: none;
  display: inline-flex;
  align-items: center;
  padding: 0;
  color: inherit;
  background: transparent;
  border: 0;
  font-size: 12px;
  font-weight: 500;
  line-height: 24px;
  white-space: nowrap;
  cursor: pointer;
  transition: color 120ms ease;
}
.suzent-ts__trigger:hover,
.suzent-ts__trigger[aria-expanded='true'] { color: var(--ts-ink); }
.suzent-ts__trigger:focus-visible { outline: 2px solid var(--ts-ink); outline-offset: 2px; }
.suzent-ts__summary {
  display: grid;
  grid-template-columns: 1fr;
  opacity: 1;
  transition: grid-template-columns 170ms cubic-bezier(.2,.8,.2,1), opacity 100ms ease;
}
.suzent-ts[data-open='true'] .suzent-ts__summary { grid-template-columns: 0fr; opacity: 0; }
.suzent-ts__summary-inner { min-width: 0; overflow: hidden; white-space: nowrap; }

.suzent-ts__reveal {
  display: grid;
  grid-template-columns: 0fr;
  opacity: 0;
  transform: translateX(4px);
  margin-left: 0;
  pointer-events: none;
  transition:
    grid-template-columns 180ms cubic-bezier(.2,.8,.2,1),
    opacity 120ms ease,
    transform 180ms cubic-bezier(.2,.8,.2,1),
    margin-left 180ms cubic-bezier(.2,.8,.2,1);
}
.suzent-ts[data-open='true'] .suzent-ts__reveal {
  grid-template-columns: 1fr;
  opacity: 1;
  transform: translateX(0);
  margin-left: 6px;
  pointer-events: auto;
}
.suzent-ts__reveal-inner {
  min-width: 0;
  display: flex;
  height: 18px;
  align-items: center;
  overflow: hidden;
}
.suzent-ts__mode {
  height: 18px;
  flex: none;
  padding: 0 5px;
  color: #71717a;
  background: transparent;
  border: 0;
  font-size: 8px;
  font-weight: 800;
  line-height: 18px;
  letter-spacing: .04em;
  text-transform: uppercase;
  cursor: pointer;
  transition: color 100ms ease, background-color 100ms ease;
}
.dark .suzent-ts__mode { color: #a1a1aa; }
.suzent-ts__mode:hover { opacity: .82; }
.suzent-ts__mode-current { color: var(--ts-paper); background: var(--ts-ink); }
.suzent-ts__mode:focus-visible,
.suzent-ts__meter:focus-visible { outline: 1px solid var(--ts-ink); outline-offset: 1px; }

.suzent-ts__manual {
  display: grid;
  grid-template-columns: 0fr;
  opacity: 0;
  margin-left: 0;
  transition:
    grid-template-columns 170ms cubic-bezier(.2,.8,.2,1),
    opacity 110ms ease,
    margin-left 170ms cubic-bezier(.2,.8,.2,1);
}
.suzent-ts[data-mode='manual'] .suzent-ts__manual {
  grid-template-columns: 1fr;
  opacity: 1;
  margin-left: 4px;
}
.suzent-ts__manual-inner { min-width: 0; overflow: hidden; }
.suzent-ts__meter {
  display: flex;
  width: 79px;
  height: 18px;
  align-items: center;
  gap: 3px;
  padding: 0 4px 0 6px;
  cursor: ew-resize;
  touch-action: none;
}
.suzent-ts__bar {
  width: 15px;
  height: 6px;
  flex: none;
  background: transparent;
  border: 1px solid var(--ts-muted);
  position: relative;
  transition: background-color 100ms ease, border-color 100ms ease;
}
.suzent-ts__bar[data-on='true'] { background: var(--ts-ink); border-color: var(--ts-ink); }
.suzent-ts__meter:hover .suzent-ts__bar:not([data-on='true']) { border-color: var(--ts-ink); }

/* X-High: one slow, heavy surge.
   Speed is the wrong signal here — X-High makes answers *slower*, so a racing
   streak tells the opposite story. This reads as mass instead: a crest wide
   enough (72px of plateau over a 69px strip) to flood all four bars at once,
   crossing on a 3.4s ease-in-out so it accelerates and settles like something
   with weight, while the bloom swells with it. The bars stay lit ink
   underneath, so the trough is the High look with a held glow, never empty.
   The four bars share one coordinate space: each offsets the same background
   by its own 18px pitch (15px bar + 3px gap), so the crest crosses all four
   as a single body of light.
   The crest tops out at 78% sheen rather than solid: a full inversion to paper
   white flashes, and a flash reads as a glitch, not as power. */
.suzent-ts[data-level='xhigh'] .suzent-ts__bar[data-on='true'] {
  overflow: hidden;
  animation: suzentTSPressure 3.4s ease-in-out infinite;
}

.suzent-ts[data-level='xhigh'] .suzent-ts__bar[data-on='true']::after {
  content: '';
  position: absolute;
  top: 0;
  left: calc(var(--ts-i) * -18px);
  width: 69px;
  height: 100%;
  background-image: linear-gradient(
    90deg,
    rgba(var(--ts-sheen), 0) 0%,
    rgba(var(--ts-sheen), .78) 30%,
    rgba(var(--ts-sheen), .78) 70%,
    rgba(var(--ts-sheen), 0) 100%
  );
  background-repeat: no-repeat;
  background-size: 240px 100%;
  animation: suzentTSSurge 3.4s ease-in-out infinite;
}

/* Both ends park the crest clear of the strip, where its alpha is already 0,
   so the restart has nothing to snap. */
@keyframes suzentTSSurge {
  from { background-position-x: -240px; }
  to { background-position-x: 69px; }
}
@keyframes suzentTSPressure {
  0%, 100% { box-shadow: 0 0 3px rgba(var(--ts-glow), .26); }
  50% { box-shadow: 0 0 8px rgba(var(--ts-glow), .62); }
}
@media (prefers-reduced-motion: reduce) {
  .suzent-ts__summary,
  .suzent-ts__reveal,
  .suzent-ts__manual { transition: none; }
  /* The ramp still reads without the river: the bars are lit ink underneath. */
  .suzent-ts[data-level='xhigh'] .suzent-ts__bar[data-on='true'] { animation: none; }
  .suzent-ts[data-level='xhigh'] .suzent-ts__bar[data-on='true']::after { content: none; }
}
`;

let injected = false;
function useSliderStyles(): void {
  React.useEffect(() => {
    if (injected || typeof document === 'undefined') return;
    const element = document.createElement('style');
    element.setAttribute('data-suzent-thinking-slider', '');
    element.textContent = STYLE;
    document.head.appendChild(element);
    injected = true;
  }, []);
}

interface ThinkingSliderProps {
  value: ThinkingEffort;
  onChange: (next: ThinkingEffort) => void;
  disabled?: boolean;
}

export const ThinkingSlider: React.FC<ThinkingSliderProps> = ({ value, onChange, disabled }) => {
  const { t } = useI18n();
  useSliderStyles();

  const [isOpen, setIsOpen] = React.useState(false);
  const rootRef = React.useRef<HTMLDivElement>(null);
  const meterRef = React.useRef<HTMLDivElement>(null);
  const lastManualValue = React.useRef<ThinkingEffort>(
    MANUAL_LEVELS.includes(value) ? value : 'medium'
  );
  const mode: ThinkingMode = value === 'auto' ? 'auto' : value === 'off' ? 'off' : 'manual';
  const manualIndex = Math.max(0, MANUAL_LEVELS.indexOf(value));
  const valueLabel = t(`chatInput.thinkingValues.${value}`);
  const summaryLabel = mode === 'manual' ? valueLabel : t(`chatInput.thinkingModes.${mode}`);

  React.useEffect(() => {
    if (!isOpen) return;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setIsOpen(false);
    };
    document.addEventListener('mousedown', closeOnOutsideClick);
    return () => document.removeEventListener('mousedown', closeOnOutsideClick);
  }, [isOpen]);

  React.useEffect(() => {
    if (disabled) setIsOpen(false);
  }, [disabled]);

  React.useEffect(() => {
    if (MANUAL_LEVELS.includes(value)) lastManualValue.current = value;
  }, [value]);

  const setFromPointer = React.useCallback(
    (clientX: number) => {
      const box = meterRef.current?.getBoundingClientRect();
      if (!box || box.width === 0) return;
      const ratio = Math.min(1, Math.max(0, (clientX - box.left) / box.width));
      onChange(MANUAL_LEVELS[Math.round(ratio * LAST_MANUAL_INDEX)]);
    },
    [onChange]
  );

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    meterRef.current?.focus();
    event.currentTarget.setPointerCapture(event.pointerId);
    setFromPointer(event.clientX);
  };

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) setFromPointer(event.clientX);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const step = (next: number) => {
      event.preventDefault();
      onChange(MANUAL_LEVELS[Math.min(LAST_MANUAL_INDEX, Math.max(0, next))]);
    };
    if (event.key === 'Escape') {
      event.preventDefault();
      setIsOpen(false);
    } else if (event.key === 'ArrowRight' || event.key === 'ArrowUp') step(manualIndex + 1);
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') step(manualIndex - 1);
    else if (event.key === 'Home') step(0);
    else if (event.key === 'End') step(LAST_MANUAL_INDEX);
  };

  const chooseMode = (nextMode: ThinkingMode) => {
    if (nextMode === 'auto') onChange('auto');
    else if (nextMode === 'off') onChange('off');
    else onChange(lastManualValue.current);
  };

  const cycleMode = () => chooseMode(NEXT_MODE[mode]);

  return (
    <div
      ref={rootRef}
      className="suzent-ts font-sans"
      data-level={value}
      data-mode={mode}
      data-open={isOpen ? 'true' : 'false'}
      data-disabled={disabled ? 'true' : 'false'}
      aria-disabled={disabled}
      title={t(`chatInput.thinkingDescriptions.${value}`)}
    >
      <button
        type="button"
        className="suzent-ts__trigger"
        aria-label={`${t('chatInput.thinkingTitle')}: ${summaryLabel}`}
        aria-expanded={isOpen}
        disabled={disabled}
        onClick={() => setIsOpen((open) => !open)}
      >
        <span>{t('chatInput.thinkingTitle')}</span>
        <span className="suzent-ts__summary">
          <span className="suzent-ts__summary-inner">: {summaryLabel}</span>
        </span>
      </button>

      <span className="suzent-ts__reveal" aria-hidden={!isOpen}>
        <span className="suzent-ts__reveal-inner">
          <button
            type="button"
            className="suzent-ts__mode suzent-ts__mode-current"
            aria-label={`${t('chatInput.thinkingTitle')}: ${summaryLabel}`}
            title={`${t('chatInput.thinkingModes.auto')} → ${t('chatInput.thinkingModes.manual')} → ${t('chatInput.thinkingModes.off')}`}
            disabled={disabled}
            tabIndex={isOpen ? 0 : -1}
            onClick={cycleMode}
          >
            {summaryLabel}
          </button>

          <span className="suzent-ts__manual">
            <span className="suzent-ts__manual-inner">
              <div
                ref={meterRef}
                className="suzent-ts__meter"
                role="slider"
                tabIndex={disabled || !isOpen || mode !== 'manual' ? -1 : 0}
                aria-hidden={!isOpen || mode !== 'manual'}
                aria-label={t('chatInput.thinkingSliderLabel')}
                aria-valuemin={1}
                aria-valuemax={MANUAL_LEVELS.length}
                aria-valuenow={manualIndex + 1}
                aria-valuetext={valueLabel}
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onKeyDown={onKeyDown}
              >
                {Array.from({ length: MANUAL_LEVELS.length }, (_, index) => (
                  <span
                    key={index}
                    className="suzent-ts__bar"
                    data-on={mode === 'manual' && index <= manualIndex ? 'true' : 'false'}
                    aria-hidden="true"
                    style={{ ['--ts-i' as string]: index }}
                  />
                ))}
              </div>
            </span>
          </span>
        </span>
      </span>
    </div>
  );
};
