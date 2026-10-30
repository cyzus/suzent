import type { HeartbeatPulse as Pulse } from '../hooks/useHeartbeatPulse';

const EKG_CLASS: Record<Pulse['ekg'], string> = {
  fast: 'ekg-active-wave [animation-duration:1.5s]',
  active: 'ekg-active-wave [animation-duration:3s]',
  slow: 'ekg-active-wave [animation-duration:6s] opacity-50',
  flat: 'ekg-flatline',
};

/** The pixel heart and EKG line; `lineClassName` lets the header hide the line on narrow screens. */
export function HeartbeatPulse({
  pulse,
  lineClassName = '',
}: {
  pulse: Pick<Pulse, 'ekg' | 'heartClass'>;
  lineClassName?: string;
}): JSX.Element {
  const path =
    pulse.ekg !== 'flat'
      ? 'M 0 25 L 10 25 L 14 30 L 22 5 L 28 45 L 34 25 L 100 25'
      : 'M 0 25 L 100 25';
  return (
    <>
      <svg
        className={`w-3 h-3 flex-shrink-0 ${pulse.heartClass}`}
        viewBox="0 0 24 24"
        fill="currentColor"
        aria-hidden="true"
      >
        <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
      </svg>
      <div className={`w-8 h-3 flex-shrink-0 ${lineClassName}`} aria-hidden="true">
        <svg viewBox="0 0 100 50" preserveAspectRatio="none" className="w-full h-full">
          <path
            className={EKG_CLASS[pulse.ekg]}
            pathLength="100"
            fill="none"
            stroke="currentColor"
            strokeWidth="6"
            d={path}
          />
        </svg>
      </div>
    </>
  );
}
