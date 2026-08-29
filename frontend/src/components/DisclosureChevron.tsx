import React from 'react';

/**
 * The one expand/collapse chevron.
 *
 * It points right while collapsed and turns down to open. The transcript used
 * to disagree with itself about that: some disclosures pointed down when shut
 * and flipped up when open -- reading as "there is something below" in both
 * states -- and ToolCallBlock did it both ways depending on whether it was
 * inside an activity rail, so the same control changed meaning with its
 * surroundings.
 *
 * Sizing, colour and transition stay with the caller: a hover-revealed chevron
 * needs `transition-all` for its opacity, and a `<details>`-driven one turns on
 * `group-open/...:rotate-90` rather than a React flag, so it passes no
 * `expanded` at all. What is shared is the mark and the direction.
 */
export const DisclosureChevron: React.FC<{
  expanded?: boolean;
  className?: string;
}> = ({ expanded = false, className = '' }) => (
  <svg
    className={`shrink-0 ${expanded ? 'rotate-90' : ''} ${className}`}
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
    strokeWidth={3}
    aria-hidden="true"
  >
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
  </svg>
);
