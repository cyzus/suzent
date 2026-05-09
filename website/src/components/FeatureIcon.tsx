import React from 'react';

interface IconProps {
  className?: string;
}

const shared = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2.5,
  strokeLinecap: 'square' as const,
  strokeLinejoin: 'miter' as const,
};

export const IconModelAgnostic = ({ className }: IconProps) => (
  <svg {...shared} className={className}>
    <circle cx="5" cy="12" r="3" strokeLinecap="square" />
    <circle cx="19" cy="12" r="3" strokeLinecap="square" />
    <line x1="8" y1="12" x2="16" y2="12" />
    <line x1="12" y1="9" x2="12" y2="15" />
  </svg>
);

export const IconMemory = ({ className }: IconProps) => (
  <svg {...shared} className={className}>
    <rect x="3" y="4" width="18" height="5" />
    <rect x="3" y="11" width="18" height="5" />
    <line x1="7" y1="20" x2="17" y2="20" />
    <line x1="12" y1="16" x2="12" y2="20" />
  </svg>
);

export const IconLock = ({ className }: IconProps) => (
  <svg {...shared} className={className}>
    <rect x="5" y="11" width="14" height="10" />
    <path d="M8 11V7a4 4 0 0 1 8 0v4" strokeLinecap="square" />
    <line x1="12" y1="15" x2="12" y2="17" />
  </svg>
);

export const IconClock = ({ className }: IconProps) => (
  <svg {...shared} className={className}>
    <circle cx="12" cy="12" r="9" />
    <polyline points="12 7 12 12 16 14" />
    <line x1="12" y1="3" x2="12" y2="5" />
    <line x1="12" y1="19" x2="12" y2="21" />
    <line x1="3" y1="12" x2="5" y2="12" />
    <line x1="19" y1="12" x2="21" y2="12" />
  </svg>
);

export const IconSkills = ({ className }: IconProps) => (
  <svg {...shared} className={className}>
    <rect x="3" y="3" width="8" height="8" />
    <rect x="13" y="3" width="8" height="8" />
    <rect x="3" y="13" width="8" height="8" />
    <rect x="13" y="13" width="8" height="8" />
  </svg>
);

export const IconTerminal = ({ className }: IconProps) => (
  <svg {...shared} className={className}>
    <rect x="2" y="3" width="20" height="18" />
    <polyline points="7 9 11 12 7 15" />
    <line x1="13" y1="15" x2="19" y2="15" />
  </svg>
);
