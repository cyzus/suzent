import React from 'react';
import type { A2UIBadge } from '../../../types/a2ui';

const COLOR_CLASSES: Record<string, string> = {
  default: 'bg-neutral-100 border-neutral-400 text-neutral-700 dark:bg-zinc-700 dark:text-neutral-200',
  success: 'bg-green-100 border-green-600 text-green-800',
  warning: 'bg-brutal-yellow border-yellow-600 text-yellow-900',
  error:   'bg-red-100 border-red-600 text-red-800',
  info:    'bg-blue-100 border-blue-600 text-blue-800',
};

interface Props { component: A2UIBadge; }

export const A2UIBadgeComponent: React.FC<Props> = ({ component }) => {
  const label = component.label || (component as any).text || '';
  if (!label) return null;
  const cls = COLOR_CLASSES[component.color ?? 'default'] ?? COLOR_CLASSES.default;
  return (
    <div className="flex">
      <span className={`border-2 px-2 py-0.5 text-xs font-bold ${cls}`}>
        {label}
      </span>
    </div>
  );
};
