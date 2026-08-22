import React from 'react';

const PANEL_STYLES =
  'rounded border-2 border-brutal-black dark:border-neutral-500 bg-white dark:bg-zinc-900 shadow-lg text-[11px] text-neutral-700 dark:text-neutral-300 p-2.5';

export const InformationPopover = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className = '', ...props }, ref) => (
  <div ref={ref} className={`${PANEL_STYLES} ${className}`.trim()} {...props} />
));

InformationPopover.displayName = 'InformationPopover';
