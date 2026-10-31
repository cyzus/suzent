import React from 'react';
import { SuzentLogo } from '../SuzentLogo';
import {
  COMET_SEGMENTS,
  ORBIT_RINGS,
  type OrbitState,
  buildOrbitFrame,
  createOrbitState,
  settleOrbits,
  stepOrbits,
} from '../../lib/greetingOrbitSim';

const CUBE_SIZE = 82;
const HALF_CUBE = CUBE_SIZE / 2;

const ORBIT_BOX = 184;
const ORBIT_OFFSET = (CUBE_SIZE - ORBIT_BOX) / 2;

const faceStyle = (transform: string): React.CSSProperties => ({ transform });

const COMET_OPACITY = Array.from(
  { length: COMET_SEGMENTS },
  (_, j) => (1 - j / COMET_SEGMENTS) ** 1.6
);

const COMET_WIDTH = Array.from(
  { length: COMET_SEGMENTS },
  (_, j) => +(2.15 - (j / (COMET_SEGMENTS - 1)) * 1.15).toFixed(2)
);

const Orbits = React.forwardRef<SVGSVGElement, { half: 'back' | 'front' }>(({ half }, ref) => (
  <svg
    ref={ref}
    className={`suzent-greeting-orbits is-${half}`}
    viewBox={`${-ORBIT_BOX / 2} ${-ORBIT_BOX / 2} ${ORBIT_BOX} ${ORBIT_BOX}`}
  >
    {ORBIT_RINGS.map((ring) => (
      <g key={ring.node}>
        {half === 'front' && <path className="suzent-greeting-orbit-casing" />}
        <path className="suzent-greeting-orbit-ring" />
        {half === 'front' && (
          <g>
            {COMET_OPACITY.map((opacity, j) => (
              <path
                key={j}
                className="suzent-greeting-comet-casing"
                opacity={opacity}
                strokeWidth={+(COMET_WIDTH[j] + 1.3).toFixed(2)}
              />
            ))}
          </g>
        )}
        <g>
          {COMET_OPACITY.map((opacity, j) => (
            <path
              key={j}
              className="suzent-greeting-comet"
              opacity={opacity}
              strokeWidth={COMET_WIDTH[j]}
            />
          ))}
        </g>
      </g>
    ))}
  </svg>
));

Orbits.displayName = 'Orbits';

const renderOrbits = (layers: [SVGSVGElement, SVGSVGElement], state: OrbitState) => {
  const frames = buildOrbitFrame(state);
  layers.forEach((svg, layer) => {
    const isFront = layer === 1;
    svg.style.opacity = String(state.visible * (isFront ? 0.88 : 0.48));
    svg.style.transform = `scale(${state.scale})`;
    frames.forEach((frame, i) => {
      const group = svg.children[i];
      const d = isFront ? frame.front : frame.back;
      if (isFront) {
        group.children[0].setAttribute('d', d);
        group.children[1].setAttribute('d', d);
        const cometCasing = group.children[2] as SVGGElement;
        const comet = group.children[3] as SVGGElement;
        cometCasing.style.opacity = String(frame.cometGain);
        comet.style.opacity = String(frame.cometGain);
        frame.comet.forEach((segment, j) => {
          const segD = segment.front ? segment.d : '';
          cometCasing.children[j].setAttribute('d', segD);
          comet.children[j].setAttribute('d', segD);
        });
      } else {
        group.children[0].setAttribute('d', d);
        const comet = group.children[1] as SVGGElement;
        comet.style.opacity = String(frame.cometGain);
        frame.comet.forEach((segment, j) => {
          comet.children[j].setAttribute('d', !segment.front ? segment.d : '');
        });
      }
    });
  });
};

interface GreetingCubeProps {
  engaged?: boolean;
}

export const GreetingCube: React.FC<GreetingCubeProps> = React.memo(({ engaged = false }) => {
  const presenceRef = React.useRef<HTMLDivElement>(null);
  const cubeRef = React.useRef<HTMLDivElement>(null);
  const backOrbitsRef = React.useRef<SVGSVGElement>(null);
  const frontOrbitsRef = React.useRef<SVGSVGElement>(null);
  const hoveredRef = React.useRef(false);
  const engagedRef = React.useRef(engaged);
  const boundsRef = React.useRef<{
    left: number;
    top: number;
    width: number;
    height: number;
  } | null>(null);
  const pointerTargetRef = React.useRef({ x: 0, y: 0 });
  const pointerCurrentRef = React.useRef({ x: 0, y: 0 });
  const wakeOrbitsRef = React.useRef<() => void>(() => {});

  const handlePointerMove = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (event.pointerType !== 'mouse') return;

    const bounds = boundsRef.current ?? event.currentTarget.getBoundingClientRect();
    boundsRef.current = bounds;
    const normalizedX = Math.max(
      -1,
      Math.min(1, ((event.clientX - bounds.left) / bounds.width) * 2 - 1)
    );
    const normalizedY = Math.max(
      -1,
      Math.min(1, ((event.clientY - bounds.top) / bounds.height) * 2 - 1)
    );

    pointerTargetRef.current.x = normalizedX;
    pointerTargetRef.current.y = normalizedY;
    wakeOrbitsRef.current();
  }, []);

  React.useEffect(() => {
    const back = backOrbitsRef.current;
    const front = frontOrbitsRef.current;
    if (!back || !front) return;

    const layers: [SVGSVGElement, SVGSVGElement] = [back, front];
    const state = createOrbitState();
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let frameId = 0;
    let last = 0;

    const applyPose = (nx: number, ny: number, isEngaged: boolean, isHovered: boolean) => {
      const cube = cubeRef.current;
      const presence = presenceRef.current;
      if (cube) {
        const baseRx = isEngaged && !isHovered ? -27 : -22;
        const rx = baseRx + ny * -7;
        const ry = 30 + nx * 12;
        cube.style.transform = `rotateX(${rx}deg) rotateY(${ry}deg)`;
      }
      if (presence) {
        const ex = isHovered ? nx * 1.5 : 0;
        const ey = isHovered ? ny * 1.5 : isEngaged ? 1.35 : 0;
        presence.style.setProperty('--suzent-eye-x', `${ex}px`);
        presence.style.setProperty('--suzent-eye-y', `${ey}px`);
        presence.style.setProperty('--suzent-ptr-nx', String(nx));
        presence.style.setProperty('--suzent-ptr-ny', String(ny));
      }
    };

    const tick = (now: number) => {
      const dt = last > 0 ? Math.min(0.05, Math.max(0, (now - last) / 1000)) : 0;
      last = now;
      const isHovered = hoveredRef.current;
      const isEngaged = engagedRef.current;
      const active = isEngaged || isHovered;

      const ease = 1 - Math.exp(-dt / 0.065);
      const cur = pointerCurrentRef.current;
      const tgt = pointerTargetRef.current;
      cur.x += (tgt.x - cur.x) * ease;
      cur.y += (tgt.y - cur.y) * ease;
      applyPose(cur.x, cur.y, isEngaged, isHovered);

      stepOrbits(state, active, dt);
      renderOrbits(layers, state);

      const pointerSettled = Math.abs(tgt.x - cur.x) < 0.002 && Math.abs(tgt.y - cur.y) < 0.002;
      const orbitSettled =
        !active && state.visible < 0.002 && Math.abs(state.visibleVelocity) < 0.01;
      if (orbitSettled && pointerSettled) {
        cur.x = tgt.x;
        cur.y = tgt.y;
        applyPose(cur.x, cur.y, isEngaged, isHovered);
        frameId = 0;
      } else {
        frameId = requestAnimationFrame(tick);
      }
    };

    wakeOrbitsRef.current = () => {
      if (reducedMotion.matches) {
        settleOrbits(state, engagedRef.current || hoveredRef.current);
        renderOrbits(layers, state);
        applyPose(0, 0, engagedRef.current, hoveredRef.current);
        return;
      }
      if (frameId) return;
      last = 0;
      frameId = requestAnimationFrame(tick);
    };
    wakeOrbitsRef.current();

    return () => cancelAnimationFrame(frameId);
  }, []);

  React.useEffect(() => {
    engagedRef.current = engaged;
    wakeOrbitsRef.current();
  }, [engaged]);

  const handlePointerEnter = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    boundsRef.current = event.currentTarget.getBoundingClientRect();
    hoveredRef.current = true;
    wakeOrbitsRef.current();
  }, []);

  const resetPointer = React.useCallback(() => {
    hoveredRef.current = false;
    boundsRef.current = null;
    pointerTargetRef.current.x = 0;
    pointerTargetRef.current.y = 0;
    wakeOrbitsRef.current();
  }, []);

  return (
    <div
      ref={presenceRef}
      className={`suzent-greeting-presence ${engaged ? 'is-input-engaged' : ''}`}
      aria-hidden="true"
      onPointerEnter={handlePointerEnter}
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
      @keyframes suzentGreetingNaturalBlink {
        0%, 44%, 48%, 92%, 96%, 100% { transform: scaleY(1); }
        46%, 94% { transform: scaleY(0.08); }
      }
      @keyframes suzentGreetingIdleGaze {
        0%, 30%, 100% { transform: translate(0px, 0px); }
        36%, 58% { transform: translate(0.75px, -0.25px); }
        64%, 86% { transform: translate(-0.55px, 0.2px); }
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
        --suzent-eye-x: 0px;
        --suzent-eye-y: 0px;
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
      .suzent-greeting-halo {
        position: absolute;
        inset: 6px;
        z-index: -1;
        border-radius: 50%;
        background: radial-gradient(ellipse, rgba(0, 0, 0, .055), transparent 68%);
        opacity: .6;
        transition: opacity 600ms ease, transform 600ms ease;
      }
      .dark .suzent-greeting-halo {
        background: radial-gradient(ellipse, rgba(255, 255, 255, .07), transparent 68%);
      }
      .suzent-greeting-presence:is(:hover, .is-input-engaged) .suzent-greeting-halo {
        opacity: 1;
        transform: scale(1.08);
      }
      .suzent-greeting-orbits {
        position: absolute;
        top: ${ORBIT_OFFSET}px;
        left: ${ORBIT_OFFSET}px;
        width: ${ORBIT_BOX}px;
        height: ${ORBIT_BOX}px;
        overflow: visible;
        pointer-events: none;
        opacity: 0;
      }
      .suzent-greeting-orbits path {
        fill: none;
        stroke: currentColor;
        stroke-linecap: round;
        stroke-linejoin: round;
        shape-rendering: geometricPrecision;
      }
      /* Crisp inner casing keeps front arcs and comets legible across the black cube. */
      .suzent-greeting-orbits path.suzent-greeting-orbit-casing {
        stroke: rgba(255, 255, 255, .85);
        stroke-width: 2.3;
        opacity: .9;
      }
      .dark .suzent-greeting-orbits path.suzent-greeting-orbit-casing {
        stroke: rgba(0, 0, 0, .7);
      }
      .suzent-greeting-orbits path.suzent-greeting-comet-casing {
        stroke: rgba(255, 255, 255, .92);
      }
      .dark .suzent-greeting-orbits path.suzent-greeting-comet-casing {
        stroke: rgba(0, 0, 0, .75);
      }
      .suzent-greeting-orbit-ring {
        stroke-width: 1;
      }
      .suzent-greeting-float {
        position: relative;
        width: ${CUBE_SIZE}px;
        height: ${CUBE_SIZE}px;
        animation: suzentGreetingFloat 5.4s ease-in-out infinite;
        transition: translate 500ms cubic-bezier(.2, .8, .2, 1), scale 600ms cubic-bezier(.16, 1, .3, 1);
      }
      .suzent-greeting-presence:is(:hover, .is-input-engaged) .suzent-greeting-float {
        translate: 0 -6px;
        scale: 1.08;
      }
      .suzent-greeting-stage {
        position: absolute;
        inset: 0;
        perspective: 410px;
        transform-style: preserve-3d;
        pointer-events: none;
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
        transform: rotateX(-22deg) rotateY(30deg);
      }
      .suzent-greeting-face {
        position: absolute;
        inset: 0;
        border: 1px solid var(--suzent-cube-edge);
        outline: 1px solid transparent;
        backface-visibility: hidden;
        -webkit-backface-visibility: hidden;
      }
      .suzent-greeting-face:nth-child(1) {
        background:
          radial-gradient(
            90px circle at calc(35% + var(--suzent-ptr-nx, 0) * 25%) calc(25% + var(--suzent-ptr-ny, 0) * 25%),
            rgba(255, 255, 255, .14),
            transparent 70%
          ),
          linear-gradient(155deg, #161616 0%, #050505 55%, #000000 100%);
      }
      .suzent-greeting-face:nth-child(2) { background: var(--suzent-cube-back); }
      .suzent-greeting-face:nth-child(3) {
        background: linear-gradient(180deg, #242424 0%, #121212 65%, #090909 100%);
      }
      .dark .suzent-greeting-face:nth-child(3) {
        background: linear-gradient(180deg, #1e1e1e 0%, #101010 65%, #070707 100%);
      }
      .suzent-greeting-face:nth-child(4) {
        background: linear-gradient(180deg, #222222 0%, #101010 60%, #070707 100%);
      }
      .dark .suzent-greeting-face:nth-child(4) {
        background: linear-gradient(180deg, #1a1a1a 0%, #0d0d0d 60%, #060606 100%);
      }
      .suzent-greeting-face:nth-child(5) {
        background:
          radial-gradient(
            80px circle at calc(50% + var(--suzent-ptr-nx, 0) * 30%) calc(50% + var(--suzent-ptr-ny, 0) * 30%),
            rgba(255, 255, 255, .18),
            transparent 65%
          ),
          linear-gradient(135deg, #484848 0%, #2a2a2a 58%, #1a1a1a 100%);
        border-color: rgba(255, 255, 255, .44);
      }
      .dark .suzent-greeting-face:nth-child(5) {
        background:
          radial-gradient(
            80px circle at calc(50% + var(--suzent-ptr-nx, 0) * 30%) calc(50% + var(--suzent-ptr-ny, 0) * 30%),
            rgba(255, 255, 255, .15),
            transparent 65%
          ),
          linear-gradient(135deg, #383838 0%, #1f1f1f 58%, #141414 100%);
        border-color: rgba(255, 255, 255, .4);
      }
      .suzent-greeting-face:nth-child(6) { background: var(--suzent-cube-bottom); }
      .suzent-greeting-logo {
        display: block;
        width: 100%;
        height: 100%;
        shape-rendering: geometricPrecision;
      }
      .suzent-greeting-logo .suzent-logo-blink {
        transform-box: fill-box;
        transform-origin: center;
        animation: suzentGreetingNaturalBlink 6.4s ease-in-out infinite;
      }
      .suzent-greeting-presence:is(:hover, .is-input-engaged) .suzent-greeting-logo rect {
        filter: drop-shadow(0 0 .9px rgba(255, 255, 255, .95)) drop-shadow(0 0 2.2px rgba(255, 255, 255, .5));
      }
      .suzent-greeting-logo .suzent-logo-idle-gaze {
        animation: suzentGreetingIdleGaze 9s ease-in-out infinite;
      }
      .suzent-greeting-logo .suzent-logo-gaze {
        transform: translate(var(--suzent-eye-x), var(--suzent-eye-y));
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
        color: #000;
        opacity: .55;
        box-shadow: 0 0 14px 2px rgba(255, 255, 255, .12);
      }
      @media (prefers-reduced-motion: reduce) {
        .suzent-greeting-float,
        .suzent-greeting-idle,
        .suzent-greeting-cube,
        .suzent-greeting-shadow,
        .suzent-greeting-logo .suzent-logo-blink,
        .suzent-greeting-logo .suzent-logo-idle-gaze {
          animation: none !important;
        }
        .suzent-greeting-cube {
          transform: rotateX(-22deg) rotateY(30deg);
        }
      }
    `}</style>

      <div className="suzent-greeting-halo" />
      <div className="suzent-greeting-float">
        <Orbits ref={backOrbitsRef} half="back" />
        <div className="suzent-greeting-stage">
          <div className="suzent-greeting-idle">
            <div ref={cubeRef} className="suzent-greeting-cube">
              <div className="suzent-greeting-face" style={faceStyle(`translateZ(${HALF_CUBE}px)`)}>
                <SuzentLogo className="suzent-greeting-logo" faceOnly />
              </div>
              <div
                className="suzent-greeting-face"
                style={faceStyle(`rotateY(180deg) translateZ(${HALF_CUBE}px)`)}
              />
              <div
                className="suzent-greeting-face"
                style={faceStyle(`rotateY(90deg) translateZ(${HALF_CUBE}px)`)}
              />
              <div
                className="suzent-greeting-face"
                style={faceStyle(`rotateY(-90deg) translateZ(${HALF_CUBE}px)`)}
              />
              <div
                className="suzent-greeting-face"
                style={faceStyle(`rotateX(90deg) translateZ(${HALF_CUBE}px)`)}
              />
              <div
                className="suzent-greeting-face"
                style={faceStyle(`rotateX(-90deg) translateZ(${HALF_CUBE}px)`)}
              />
            </div>
          </div>
        </div>
        <Orbits ref={frontOrbitsRef} half="front" />
      </div>

      <div className="suzent-greeting-shadow" />
    </div>
  );
});

GreetingCube.displayName = 'GreetingCube';
