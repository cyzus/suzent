import React, { useCallback, useRef } from 'react';

/**
 * Canonical Suzent logo — matches public/favicon.svg exactly.
 * All UI placements must use this component; do not inline the SVG elsewhere.
 *
 * interactive: eyes follow the cursor within a ±1.5px SVG-unit range using
 * CSS translate. No rAF loop — pure event-driven, negligible perf cost.
 */
interface SuzentLogoProps {
  className?: string;
  interactive?: boolean;
  /** Omit the rounded outer background rect when used as a 3D cube face. */
  faceOnly?: boolean;
}

const MAX_OFFSET = 1.5;

export const SuzentLogo: React.FC<SuzentLogoProps> = ({
  className = '',
  interactive = false,
  faceOnly = false,
}) => {
  const svgRef = useRef<SVGSVGElement>(null);
  const gazeRef = useRef<SVGGElement>(null);

  const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    const rect = svgRef.current?.getBoundingClientRect();
    const gaze = gazeRef.current;
    if (!rect || !gaze) return;
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const dx = Math.max(-1, Math.min(1, (e.clientX - cx) / (rect.width / 2))) * MAX_OFFSET;
    const dy = Math.max(-1, Math.min(1, (e.clientY - cy) / (rect.height / 2))) * MAX_OFFSET;
    gaze.style.transform = `translate(${dx.toFixed(2)}px, ${dy.toFixed(2)}px)`;
  }, []);

  const handleMouseLeave = useCallback(() => {
    const gaze = gazeRef.current;
    if (gaze) gaze.style.transform = '';
  }, []);

  const eyeStyle: React.CSSProperties = interactive
    ? { transition: 'transform 0.08s ease-out' }
    : {};

  return (
    <svg
      ref={svgRef}
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      role="img"
      aria-label="Suzent Logo"
      className={className}
      onMouseMove={interactive ? handleMouseMove : undefined}
      onMouseLeave={interactive ? handleMouseLeave : undefined}
    >
      {!faceOnly && <rect x="0" y="0" width="24" height="24" rx="4" fill="#000000" />}
      <g ref={gazeRef} className="suzent-logo-gaze" style={eyeStyle}>
        <g className="suzent-logo-idle-gaze">
          <g className="suzent-logo-blink">
            <rect x="5" y="8" width="5" height="5" rx="1.5" fill="#FFFFFF" />
            <rect x="14" y="8" width="5" height="5" rx="1.5" fill="#FFFFFF" />
          </g>
        </g>
      </g>
    </svg>
  );
};
