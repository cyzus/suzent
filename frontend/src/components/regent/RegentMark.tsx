import React from 'react';

export type RegentState = 'idle' | 'working' | 'waiting';

interface RegentMarkProps {
  /** Head size in px; the circlet rises above it, so a slot keeps the plain robot's size. */
  size: number;
  state?: RegentState;
  className?: string;
}

const BODY_TOP = 9.6;
const VIEW_HEIGHT = 33.6;

function Shape({
  fill,
  eye,
  live,
}: {
  fill: string;
  eye: string;
  live: boolean;
}): React.ReactElement {
  return (
    <>
      <g className={live ? 'regent-circlet' : undefined}>
        <path d="M3 3.6 Q12 0 21 3.6 L21 6.6 Q12 10.2 3 6.6 Z" fill={fill} />
        <path
          d="M4.6 4.2 Q12 6.9 19.4 4.2"
          fill="none"
          stroke={eye}
          strokeWidth=".9"
          strokeLinecap="round"
          opacity=".55"
        />
        <rect
          className={live ? 'regent-gem' : undefined}
          x="10.3"
          y="5.3"
          width="3.4"
          height="3.4"
          rx=".8"
          transform="rotate(45 12 7)"
          fill={eye}
        />
      </g>
      <rect x="0" y={BODY_TOP} width="24" height="24" rx="4" fill={fill} />
      <g className={live ? 'regent-eyes' : undefined}>
        <rect x="5" y="17.6" width="5" height="5" rx="1.5" fill={eye} />
        <rect x="14" y="17.6" width="5" height="5" rx="1.5" fill={eye} />
      </g>
    </>
  );
}

/**
 * Regent's flat mark: the Suzent head wearing a circlet that floats just above
 * it. Used wherever Regent is small or sits in the flow of a chat.
 */
export function RegentMark({
  size,
  state = 'idle',
  className = '',
}: RegentMarkProps): React.ReactElement {
  const unit = size / 24;
  return (
    <svg
      className={`regent-mark block shrink-0 overflow-visible ${className}`}
      data-regent-state={state}
      width={size}
      height={VIEW_HEIGHT * unit}
      viewBox={`0 0 24 ${VIEW_HEIGHT}`}
      style={{ marginTop: -BODY_TOP * unit }}
      aria-hidden="true"
    >
      {/* On a dark page the black head keeps a light rim, as RobotIcon does. */}
      <g className="hidden dark:inline" stroke="#d4d4d4" strokeWidth="1.6" strokeLinejoin="round">
        <Shape fill="#000" eye="#000" live={false} />
      </g>
      <Shape fill="#000" eye="#fff" live />
    </svg>
  );
}
