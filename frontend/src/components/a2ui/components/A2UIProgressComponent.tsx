import React from 'react';
import type { A2UIProgress } from '../../../types/a2ui';

interface Props { component: A2UIProgress; }

export const A2UIProgressComponent: React.FC<Props> = ({ component }) => {
  const clamped = Math.min(100, Math.max(0, component.value));
  return (
    <div className="flex flex-col gap-1">
      {component.label && (
        <div className="flex justify-between text-xs font-bold text-brutal-black dark:text-white">
          <span>{component.label}</span>
          <span>{clamped.toFixed(0)}%</span>
        </div>
      )}
      <div className="h-4 border-2 border-brutal-black bg-neutral-100 dark:bg-zinc-700 overflow-hidden">
        <div
          className="h-full bg-brutal-yellow transition-all duration-300"
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
};
