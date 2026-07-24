import React from 'react';
import { SuzentLogo } from '../SuzentLogo';

const CUBE_SIZE = 82;
const HALF_CUBE = CUBE_SIZE / 2;

const faceStyle = (transform: string): React.CSSProperties => ({ transform });

interface GreetingCubeProps {
  engaged?: boolean;
}

export const GreetingCube: React.FC<GreetingCubeProps> = React.memo(({ engaged = false }) => {
  const presenceRef = React.useRef<HTMLDivElement>(null);

  const handlePointerMove = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (event.pointerType !== 'mouse') return;

    const bounds = event.currentTarget.getBoundingClientRect();
    const normalizedX = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
    const normalizedY = ((event.clientY - bounds.top) / bounds.height) * 2 - 1;

    event.currentTarget.style.setProperty('--suzent-pointer-x', `${normalizedX * 12}deg`);
    event.currentTarget.style.setProperty('--suzent-pointer-y', `${normalizedY * -7}deg`);
  }, []);

  const resetPointer = React.useCallback(() => {
    presenceRef.current?.style.setProperty('--suzent-pointer-x', '0deg');
    presenceRef.current?.style.setProperty('--suzent-pointer-y', '0deg');
  }, []);

  return (
  <div
    ref={presenceRef}
    className={`suzent-greeting-presence ${engaged ? 'is-input-engaged' : ''}`}
    aria-hidden="true"
    onPointerMove={handlePointerMove}
    onPointerLeave={resetPointer}
  >
    <style>{`
      @keyframes suzentGreetingFloat {
        0%, 100% { transform: translateY(2px); }
        50% { transform: translateY(-5px); }
      }
      @keyframes suzentGreetingShadow {
        0%, 100% { opacity: .14; transform: translateX(-50%) scaleX(1); }
        50% { opacity: .08; transform: translateX(-50%) scaleX(.78); }
      }
      @keyframes suzentGreetingIdleTurn {
        0%, 100% { transform: rotateX(0deg) rotateY(0deg) rotateZ(-1deg); }
        32% { transform: rotateX(-4deg) rotateY(14deg) rotateZ(1deg); }
        66% { transform: rotateX(4deg) rotateY(6deg) rotateZ(0deg); }
      }
      @keyframes suzentGreetingSigilTurn {
        to { transform: rotate(360deg); }
      }
      @keyframes suzentGreetingSigilTurnReverse {
        to { transform: rotate(-360deg); }
      }
      @keyframes suzentGreetingSignal {
        0%, 68%, 100% { opacity: .16; stroke-dashoffset: 18; }
        74%, 88% { opacity: .72; stroke-dashoffset: 0; }
      }
      @keyframes suzentGreetingNodePulse {
        0%, 100% { opacity: .28; }
        50% { opacity: .72; }
      }
      .suzent-greeting-presence {
        --suzent-cube-back: #050505;
        --suzent-cube-right: #181818;
        --suzent-cube-left: #070707;
        --suzent-cube-top: #303030;
        --suzent-cube-bottom: #030303;
        --suzent-cube-edge: rgba(255, 255, 255, .3);
        --suzent-pointer-x: 0deg;
        --suzent-pointer-y: 0deg;
        position: relative;
        display: flex;
        width: 156px;
        height: 142px;
        align-items: center;
        justify-content: center;
        isolation: isolate;
        appearance: none;
        padding: 0;
        border: 0;
        background: transparent;
        color: inherit;
      }
      .suzent-greeting-sigil {
        position: absolute;
        inset: -7px;
        z-index: -1;
        color: currentColor;
        opacity: .1;
        transform: scale(.9);
        transition:
          opacity 500ms ease,
          transform 700ms cubic-bezier(.2, .8, .2, 1);
      }
      .suzent-greeting-sigil-outer,
      .suzent-greeting-sigil-inner {
        transform-box: fill-box;
        transform-origin: center;
      }
      .suzent-greeting-sigil-outer {
        animation: suzentGreetingSigilTurn 32s linear infinite;
      }
      .suzent-greeting-sigil-inner {
        animation: suzentGreetingSigilTurnReverse 24s linear infinite;
      }
      .suzent-greeting-sigil-axis {
        animation: suzentGreetingSignal 6.4s steps(3, end) infinite;
      }
      .suzent-greeting-sigil-node {
        animation: suzentGreetingNodePulse 4s ease-in-out infinite;
      }
      .suzent-greeting-sigil-node:nth-of-type(2) { animation-delay: -1s; }
      .suzent-greeting-sigil-node:nth-of-type(3) { animation-delay: -2s; }
      .suzent-greeting-sigil-node:nth-of-type(4) { animation-delay: -3s; }
      .suzent-greeting-presence:is(:hover, .is-input-engaged) .suzent-greeting-sigil {
        opacity: .5;
        transform: scale(1.1);
      }
      .suzent-greeting-presence:is(:hover, .is-input-engaged) .suzent-greeting-sigil-outer {
        animation-duration: 16s;
        stroke-width: 1.05;
      }
      .suzent-greeting-presence:is(:hover, .is-input-engaged) .suzent-greeting-sigil-inner {
        animation-duration: 11s;
        stroke-width: .95;
      }
      .suzent-greeting-presence:is(:hover, .is-input-engaged) .suzent-greeting-sigil-axis {
        animation-duration: 2.6s;
      }
      .suzent-greeting-presence:is(:hover, .is-input-engaged) .suzent-greeting-sigil-node {
        animation-duration: 1.5s;
      }
      .suzent-greeting-float {
        position: relative;
        z-index: 1;
        width: ${CUBE_SIZE}px;
        height: ${CUBE_SIZE}px;
        perspective: 410px;
        transform-style: preserve-3d;
        animation: suzentGreetingFloat 5.4s ease-in-out infinite;
        transition: translate 500ms cubic-bezier(.2, .8, .2, 1);
      }
      .suzent-greeting-presence:is(:hover, .is-input-engaged) .suzent-greeting-float {
        translate: 0 -3px;
      }
      .suzent-greeting-idle {
        position: absolute;
        inset: 0;
        transform-style: preserve-3d;
        animation: suzentGreetingIdleTurn 8s cubic-bezier(.45, 0, .25, 1) infinite;
      }
      .suzent-greeting-cube {
        position: absolute;
        inset: 0;
        transform-style: preserve-3d;
        transform:
          rotateX(calc(-22deg + var(--suzent-pointer-y)))
          rotateY(calc(30deg + var(--suzent-pointer-x)));
        transition: transform 180ms cubic-bezier(.2, .75, .25, 1);
        will-change: transform;
      }
      .suzent-greeting-presence.is-input-engaged:not(:hover) .suzent-greeting-cube {
        transform: rotateX(-27deg) rotateY(30deg);
      }
      .suzent-greeting-face {
        position: absolute;
        inset: 0;
        overflow: hidden;
        border: 1px solid var(--suzent-cube-edge);
        backface-visibility: hidden;
      }
      .suzent-greeting-face:nth-child(1) {
        overflow: hidden;
        border: 1px solid var(--suzent-cube-edge);
        background: #000;
        transition: box-shadow 500ms ease;
      }
      .suzent-greeting-presence:is(:hover, .is-input-engaged) .suzent-greeting-face:nth-child(1) {
        box-shadow:
          inset 0 0 0 1px rgba(255, 255, 255, .1),
          0 0 12px rgba(255, 255, 255, .12);
      }
      .suzent-greeting-face:nth-child(2) { background: var(--suzent-cube-back); }
      .suzent-greeting-face:nth-child(3) { background: var(--suzent-cube-right); }
      .suzent-greeting-face:nth-child(4) { background: var(--suzent-cube-left); }
      .suzent-greeting-face:nth-child(5) { background: var(--suzent-cube-top); }
      .suzent-greeting-face:nth-child(6) { background: var(--suzent-cube-bottom); }
      .suzent-greeting-logo {
        display: block;
        width: 100%;
        height: 100%;
      }
      .suzent-greeting-logo rect:not(:first-child) {
        transform-box: fill-box;
        transform-origin: center;
        transition: transform 420ms cubic-bezier(.16, 1, .3, 1) !important;
      }
      .suzent-greeting-presence:not(:hover):not(.is-input-engaged) .suzent-greeting-logo rect:not(:first-child) {
        transform: scaleY(.08) !important;
      }
      .suzent-greeting-presence.is-input-engaged:not(:hover) .suzent-greeting-logo rect:not(:first-child) {
        transform: translateY(1px) !important;
      }
      .suzent-greeting-shadow {
        position: absolute;
        bottom: 10px;
        left: 50%;
        width: 62px;
        height: 7px;
        border-radius: 50%;
        color: #000;
        background: currentColor;
        filter: blur(6px);
        animation: suzentGreetingShadow 5.4s ease-in-out infinite;
        transition:
          width 500ms ease,
          opacity 500ms ease;
      }
      .suzent-greeting-presence:is(:hover, .is-input-engaged) .suzent-greeting-shadow {
        width: 52px;
        opacity: .08;
      }
      .dark .suzent-greeting-presence {
        --suzent-cube-back: #050505;
        --suzent-cube-right: #111;
        --suzent-cube-left: #080808;
        --suzent-cube-top: #202020;
        --suzent-cube-bottom: #030303;
        --suzent-cube-edge: rgba(255, 255, 255, .3);
      }
      .dark .suzent-greeting-shadow {
        color: #fff;
      }
      @media (prefers-reduced-motion: reduce) {
        .suzent-greeting-float,
        .suzent-greeting-idle,
        .suzent-greeting-cube,
        .suzent-greeting-shadow,
        .suzent-greeting-sigil-outer,
        .suzent-greeting-sigil-inner,
        .suzent-greeting-sigil-axis,
        .suzent-greeting-sigil-node {
          animation: none !important;
        }
        .suzent-greeting-cube {
          transform: rotateX(-22deg) rotateY(30deg);
        }
      }
    `}</style>

    <svg className="suzent-greeting-sigil" viewBox="0 0 156 156">
      <g className="suzent-greeting-sigil-outer" fill="none" stroke="currentColor" strokeWidth=".8">
        <path d="M78 8 L148 78 L78 148 L8 78 Z" />
        <path d="M28 28 H128 V128 H28 Z" />
        <path d="M78 8 V20 M148 78 H136 M78 148 V136 M8 78 H20" />
      </g>
      <g className="suzent-greeting-sigil-inner" fill="none" stroke="currentColor" strokeWidth=".7">
        <path d="M78 30 L120 104 H36 Z" />
        <path d="M78 126 L36 52 H120 Z" />
      </g>
      <path
        className="suzent-greeting-sigil-axis"
        d="M78 18 V138 M18 78 H138"
        fill="none"
        stroke="currentColor"
        strokeDasharray="4 14"
        strokeWidth=".7"
      />
      <rect className="suzent-greeting-sigil-node" x="75.5" y="5.5" width="5" height="5" fill="currentColor" />
      <rect className="suzent-greeting-sigil-node" x="145.5" y="75.5" width="5" height="5" fill="currentColor" />
      <rect className="suzent-greeting-sigil-node" x="75.5" y="145.5" width="5" height="5" fill="currentColor" />
      <rect className="suzent-greeting-sigil-node" x="5.5" y="75.5" width="5" height="5" fill="currentColor" />
    </svg>

    <div className="suzent-greeting-float">
      <div className="suzent-greeting-idle">
        <div className="suzent-greeting-cube">
          <div className="suzent-greeting-face" style={faceStyle(`translateZ(${HALF_CUBE}px)`)}>
            <SuzentLogo className="suzent-greeting-logo" interactive />
          </div>
          <div className="suzent-greeting-face" style={faceStyle(`rotateY(180deg) translateZ(${HALF_CUBE}px)`)} />
          <div className="suzent-greeting-face" style={faceStyle(`rotateY(90deg) translateZ(${HALF_CUBE}px)`)} />
          <div className="suzent-greeting-face" style={faceStyle(`rotateY(-90deg) translateZ(${HALF_CUBE}px)`)} />
          <div className="suzent-greeting-face" style={faceStyle(`rotateX(90deg) translateZ(${HALF_CUBE}px)`)} />
          <div className="suzent-greeting-face" style={faceStyle(`rotateX(-90deg) translateZ(${HALF_CUBE}px)`)} />
        </div>
      </div>
    </div>

    <div className="suzent-greeting-shadow" />
  </div>
  );
});

GreetingCube.displayName = 'GreetingCube';
