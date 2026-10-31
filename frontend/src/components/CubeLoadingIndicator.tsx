import React from 'react';
import './CubeLoadingIndicator.css';

interface CubeLoadingIndicatorProps {
  variant: 'settings' | 'skills';
  label: string;
}

export function CubeLoadingIndicator({
  variant,
  label,
}: CubeLoadingIndicatorProps): React.ReactElement {
  return (
    <div
      className="flex h-full w-full flex-col items-center justify-center gap-6 p-8"
      role="status"
    >
      <div className={`cube-loading cube-loading-${variant}`} aria-hidden="true">
        {Array.from({ length: variant === 'settings' ? 3 : 4 }, (_, index) => (
          <div
            className="cube-loading-unit"
            key={index}
            style={{ '--index': index } as React.CSSProperties}
          >
            <div className="cube-loading-solid">
              {[
                '',
                'rotateY(180deg)',
                'rotateY(90deg)',
                'rotateY(-90deg)',
                'rotateX(90deg)',
                'rotateX(-90deg)',
              ].map((rotation) => (
                <span
                  key={rotation}
                  style={{ transform: `${rotation} translateZ(calc(var(--edge) / 2))` }}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
      <span className="text-xs font-medium tracking-wide text-neutral-500 dark:text-neutral-400">
        {label}
      </span>
    </div>
  );
}
