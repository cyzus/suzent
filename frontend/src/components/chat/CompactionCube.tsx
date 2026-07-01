import React from 'react';

/**
 * A small 3D cube shown while context compaction is running.
 *
 * Rather than a plain spin, it periodically *compresses* — squashing along an axis
 * and springing back as it turns — to read as "compacting". Reuses the brutalist
 * cube look of the backend preloading screen, scaled to sit inside a chat notice.
 *
 * The cube edge is derived from the `size` prop (via `--cc-half`) so it always fits
 * its box; the cube is scaled under 1 so rotated/squashed corners never poke out.
 * Self-contained: keyframes are namespaced (`suzentCC*`) and injected once.
 */

const STYLE = `
@keyframes suzentCCCompact {
  0%   { transform: scale(.7) rotateX(-24deg) rotateY(20deg) scaleY(1); }
  35%  { transform: scale(.7) rotateX(-24deg) rotateY(120deg) scaleY(1); }
  55%  { transform: scale(.7) rotateX(-24deg) rotateY(180deg) scaleY(.48); }
  74%  { transform: scale(.7) rotateX(-24deg) rotateY(240deg) scaleY(1.08); }
  100% { transform: scale(.7) rotateX(-24deg) rotateY(380deg) scaleY(1); }
}
.suzent-cc-scene { perspective: 220px; transform-style: preserve-3d; }
.suzent-cc-cube {
  transform-style: preserve-3d;
  transform: scale(.7);
  animation: suzentCCCompact 3s cubic-bezier(.5, 0, .3, 1) infinite;
}
.suzent-cc-face {
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, #1b1b1b 0%, #000 100%);
  border: 1px solid rgba(255,255,255,.25);
}
.dark .suzent-cc-face {
  background: linear-gradient(135deg, #ededed 0%, #c4c4c4 100%);
  border-color: rgba(0,0,0,.32);
}
@media (prefers-reduced-motion: reduce) {
  .suzent-cc-cube { animation: none; transform: scale(.7) rotateX(-24deg) rotateY(28deg); }
}

/* Compaction sweep: a bar that repeatedly runs left→right and squeezes shut,
   evoking context being compressed. Used as a thin footer on the notice box. */
@keyframes suzentCCSweep {
  0%   { left: 0; right: 100%; opacity: 0; }
  15%  { left: 0; right: 55%; opacity: 1; }
  50%  { left: 35%; right: 12%; opacity: 1; }
  85%  { left: 92%; right: 0; opacity: 1; }
  100% { left: 100%; right: 0; opacity: 0; }
}
.suzent-cc-sweep::after {
  content: '';
  position: absolute;
  top: 0; bottom: 0;
  left: 0; right: 100%;
  background: currentColor;
  animation: suzentCCSweep 1.8s cubic-bezier(.65, 0, .35, 1) infinite;
}
@media (prefers-reduced-motion: reduce) {
  .suzent-cc-sweep::after { animation: none; left: 0; right: 55%; }
}
`;

let injected = false;
function useCubeStyles() {
  React.useEffect(() => {
    if (injected || typeof document === 'undefined') return;
    const el = document.createElement('style');
    el.setAttribute('data-suzent-compaction-cube', '');
    el.textContent = STYLE;
    document.head.appendChild(el);
    injected = true;
  }, []);
}

export const CompactionCube: React.FC<{ size?: number; className?: string }> = ({
  size = 26,
  className = '',
}) => {
  useCubeStyles();

  const half = size / 2;
  const face = (transform: string, opacity = 1): React.CSSProperties => ({
    transform,
    opacity,
  });

  return (
    <div
      className={`suzent-cc-scene relative shrink-0 ${className}`}
      style={{ width: size, height: size, ['--cc-half' as string]: `${half}px` }}
      aria-hidden="true"
    >
      <div className="suzent-cc-cube absolute inset-0">
        <div className="suzent-cc-face" style={face(`translateZ(${half}px)`)} />
        <div className="suzent-cc-face" style={face(`rotateY(180deg) translateZ(${half}px)`, 0.7)} />
        <div className="suzent-cc-face" style={face(`rotateY(90deg) translateZ(${half}px)`, 0.85)} />
        <div className="suzent-cc-face" style={face(`rotateY(-90deg) translateZ(${half}px)`, 0.6)} />
        <div className="suzent-cc-face" style={face(`rotateX(90deg) translateZ(${half}px)`, 0.9)} />
        <div className="suzent-cc-face" style={face(`rotateX(-90deg) translateZ(${half}px)`, 0.55)} />
      </div>
    </div>
  );
};

/**
 * A thin animated bar that sweeps and squeezes left→right, evoking context being
 * compressed. Meant as a footer strip on the compaction notice box. Inherits its
 * color from `currentColor`, so set text color on the wrapper for theming.
 */
export const CompactionSweep: React.FC<{ className?: string }> = ({ className = '' }) => {
  useCubeStyles();
  return (
    <div
      className={`suzent-cc-sweep relative w-full h-0.5 overflow-hidden ${className}`}
      aria-hidden="true"
    />
  );
};

export default CompactionCube;
