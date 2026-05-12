import React, { useCallback, useRef, useState } from 'react';

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
}

const MAX_OFFSET = 1.5;

export const SuzentLogo: React.FC<SuzentLogoProps> = ({ className = '', interactive = false }) => {
    const svgRef = useRef<SVGSVGElement>(null);
    const [offset, setOffset] = useState({ x: 0, y: 0 });

    const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
        const rect = svgRef.current?.getBoundingClientRect();
        if (!rect) return;
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const dx = (e.clientX - cx) / (rect.width / 2);
        const dy = (e.clientY - cy) / (rect.height / 2);
        setOffset({
            x: Math.max(-1, Math.min(1, dx)) * MAX_OFFSET,
            y: Math.max(-1, Math.min(1, dy)) * MAX_OFFSET,
        });
    }, []);

    const handleMouseLeave = useCallback(() => setOffset({ x: 0, y: 0 }), []);

    const eyeStyle: React.CSSProperties = interactive
        ? { transform: `translate(${offset.x}px, ${offset.y}px)`, transition: 'transform 0.08s ease-out' }
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
            <rect x="0" y="0" width="24" height="24" rx="4" fill="#000000" />
            <rect x="5" y="8" width="5" height="5" rx="1.5" fill="#FFFFFF" style={eyeStyle} />
            <rect x="14" y="8" width="5" height="5" rx="1.5" fill="#FFFFFF" style={eyeStyle} />
        </svg>
    );
};
