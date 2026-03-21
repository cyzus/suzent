import React from 'react';
import type { A2UIButton } from '../../../types/a2ui';

const VARIANT_CLASSES: Record<string, string> = {
  primary:   'bg-brutal-yellow border-brutal-black text-brutal-black hover:bg-yellow-300',
  secondary: 'bg-white border-brutal-black text-brutal-black hover:bg-neutral-100 dark:bg-zinc-800 dark:text-white dark:hover:bg-zinc-700',
  danger:    'bg-red-500 border-red-700 text-white hover:bg-red-600',
};

interface Props {
  component: A2UIButton;
  onAction: (action: string, context: Record<string, unknown>) => void;
}

export const A2UIButtonComponent: React.FC<Props> = ({ component, onAction }) => {
  const cls = VARIANT_CLASSES[component.variant ?? 'primary'] ?? VARIANT_CLASSES.primary;
  return (
    <button
      disabled={component.disabled}
      onClick={() => {
        const label = component.label || (component as any).text || '';
        const action = component.action || 'button_click';
        const rawCtx = component.context;
        const context: Record<string, unknown> = (rawCtx && typeof rawCtx === 'object' && !Array.isArray(rawCtx)) ? { ...rawCtx } : {};
        if (label) context.button_label = label;
        onAction(action, context);
      }}
      className={`border-2 px-4 py-2 text-sm font-bold uppercase tracking-wide transition-transform
        active:translate-x-[1px] active:translate-y-[1px]
        disabled:opacity-50 disabled:cursor-not-allowed ${cls}`}
    >
      {component.label || (component as any).text}
    </button>
  );
};
