import React from 'react';

interface SettingsHeaderProps {
  title: string;
  subtitle?: string;
  /** Optional controls rendered on the right side of the header (e.g. a sync button). */
  actions?: React.ReactNode;
}

/**
 * Shared header for settings tabs. Renders the boxed brutalist title block used
 * consistently across every tab so headers don't drift in size/style.
 */
export function SettingsHeader({ title, subtitle, actions }: SettingsHeaderProps): React.ReactElement {
  return (
    <header className="relative flex flex-col gap-3 overflow-hidden border-2 border-brutal-black bg-brutal-black px-4 py-4 text-white shadow-brutal-sm sm:flex-row sm:items-center sm:justify-between sm:px-5">
      <div className="absolute inset-y-0 left-0 w-1.5 bg-brutal-yellow" aria-hidden="true" />
      <div className="min-w-0">
        <h2 className="font-brutal text-xl uppercase leading-none tracking-tight sm:text-2xl">{title}</h2>
        {subtitle && <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-neutral-300">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 sm:shrink-0 sm:justify-end">{actions}</div>}
    </header>
  );
}
