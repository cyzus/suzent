import React from 'react';

interface SidebarToggleIconProps {
  /** Which edge of the window the panel this icon controls lives on. */
  side: 'left' | 'right';
  /** Whether that panel is currently open. */
  open: boolean;
  className?: string;
}

const EASE = 'cubic-bezier(0.4, 0, 0.2, 1)';

/**
 * The panel glyph shared by both sidebar toggles.
 *
 * Both rails used to render the same static outline, so the button said which
 * panel it controlled but never whether that panel was open. Here the panel
 * column fills in and its divider slides outward as the sidebar opens, in step
 * with the 300ms slide of the sidebar itself — so the icon reads as the same
 * motion, just smaller.
 *
 * Geometry is fixed and the state change is expressed with transforms only:
 * `x1`/`x2` are SVG attributes, not CSS properties, so a line moved by
 * attribute would jump rather than slide.
 */
export function SidebarToggleIcon({
  side,
  open,
  className = 'h-6 w-6',
}: SidebarToggleIconProps): React.ReactElement {
  const isLeft = side === 'left';
  // Closed: the divider tucks toward its frame edge. Open: full panel width.
  const slide = open ? 0 : isLeft ? -1.5 : 1.5;
  const dividerX = isLeft ? 9 : 15;

  const slideStyle: React.CSSProperties = {
    transform: `translateX(${slide}px)`,
    transition: `transform 300ms ${EASE}`,
  };

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
      aria-hidden="true"
    >
      <rect
        x={isLeft ? 4 : dividerX}
        y={4}
        width={5}
        height={16}
        fill="currentColor"
        stroke="none"
        style={{
          ...slideStyle,
          transformBox: 'fill-box',
          transformOrigin: isLeft ? 'left center' : 'right center',
          transform: `translateX(${slide}px) scaleX(${open ? 1 : 0.7})`,
          opacity: open ? 0.22 : 0,
          transition: `transform 300ms ${EASE}, opacity 220ms ease`,
        }}
      />
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <line x1={dividerX} y1="4" x2={dividerX} y2="20" style={slideStyle} />
    </svg>
  );
}
