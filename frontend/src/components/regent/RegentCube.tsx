import React from 'react';
import type { RegentState } from './RegentMark';

interface RegentCubeProps {
  /** Edge of the cube in px. */
  size: number;
  state?: RegentState;
  /** Turn slowly even when idle, as the first-run greeting does. */
  alwaysTurn?: boolean;
  className?: string;
}

const EDGE = 82;
const HALF = EDGE / 2;
const SEGMENTS = 32;
const RADIUS = 22;
const BAND = 10;
const SEGMENT_WIDTH = 2 * RADIUS * Math.tan(Math.PI / SEGMENTS) + 0.7;

// Shade each band segment as if lit from the front left, separately per theme.
const BAND_SEGMENTS = Array.from({ length: SEGMENTS }, (_, index) => {
  const angle = ((index + 0.5) * 360) / SEGMENTS;
  const light = 0.5 + 0.5 * Math.cos(((angle - 50) * Math.PI) / 180);
  const shade = (base: number, range: number): string => {
    const value = Math.round(base + range * light);
    return `rgb(${value}, ${value}, ${value})`;
  };
  return { angle, light: shade(58, 62), dark: shade(70, 60) };
});

const FACES: Array<{ transform: string; tone: string }> = [
  { transform: `rotateY(180deg) translateZ(${HALF}px)`, tone: 'back' },
  { transform: `rotateY(90deg) translateZ(${HALF}px)`, tone: 'right' },
  { transform: `rotateY(-90deg) translateZ(${HALF}px)`, tone: 'left' },
  { transform: `rotateX(90deg) translateZ(${HALF}px)`, tone: 'top' },
  { transform: `rotateX(-90deg) translateZ(${HALF}px)`, tone: 'bottom' },
];

/**
 * Regent as Suzent's greeting cube wearing its circlet. Used where Regent is
 * shown large: the head of its conversation and its first-run greeting.
 */
export function RegentCube({
  size,
  state = 'idle',
  alwaysTurn = false,
  className = '',
}: RegentCubeProps): React.ReactElement {
  return (
    <span
      className={`regent-cube-scene ${className}`}
      data-regent-state={state}
      style={{ width: Math.round(size * 1.2), height: Math.round(size * 1.3) }}
      aria-hidden="true"
    >
      <span
        className="regent-cube-scale"
        style={{ transform: `scale(${size / EDGE})`, marginBottom: Math.round(size * 0.06) }}
      >
        <span className={`regent-cube ${alwaysTurn ? 'regent-cube-turning' : ''}`}>
          <span
            className="regent-cube-face regent-cube-front"
            style={{ transform: `translateZ(${HALF}px)` }}
          >
            <svg width={EDGE} height={EDGE} viewBox="0 0 24 24">
              <g className="regent-eyes">
                <rect x="5" y="8" width="5" height="5" rx="1.5" fill="#fff" />
                <rect x="14" y="8" width="5" height="5" rx="1.5" fill="#fff" />
              </g>
            </svg>
          </span>
          {FACES.map((face) => (
            <span
              key={face.tone}
              className={`regent-cube-face regent-cube-${face.tone}`}
              style={{ transform: face.transform }}
            />
          ))}
          <span className="regent-cube-circlet">
            {BAND_SEGMENTS.map((segment) => (
              <span
                key={segment.angle}
                className="regent-cube-band"
                style={
                  {
                    left: -SEGMENT_WIDTH / 2,
                    top: -BAND,
                    width: SEGMENT_WIDTH,
                    height: BAND,
                    transform: `rotateY(${segment.angle}deg) translateZ(${RADIUS}px)`,
                    '--regent-band-light': segment.light,
                    '--regent-band-dark': segment.dark,
                  } as React.CSSProperties
                }
              />
            ))}
            <span
              className="regent-cube-rim"
              style={{
                left: -RADIUS - 1.5,
                top: -RADIUS - 1.5,
                width: 2 * RADIUS + 3,
                height: 2 * RADIUS + 3,
              }}
            />
            <span
              className="regent-gem regent-cube-gem"
              style={{
                top: -BAND / 2 - 4,
                transform: `translateZ(${RADIUS + 0.5}px) rotate(45deg)`,
              }}
            />
          </span>
        </span>
      </span>
    </span>
  );
}
