import React from 'react';

interface SettingsHeaderProps {
  title: string;
  subtitle?: string;
  /** Optional controls rendered on the right side of the header (e.g. a sync button). */
  actions?: React.ReactNode;
}

/**
 * Shared title and optional decision-relevant context for settings tabs.
 */
export function SettingsHeader({
  title,
  subtitle,
  actions,
}: SettingsHeaderProps): React.ReactElement {
  return (
    <header className="relative flex flex-col gap-3 border-b-2 border-brutal-black px-1 py-3 text-brutal-black dark:text-white sm:flex-row sm:items-center sm:justify-between sm:px-5">
      <div className="min-w-0">
        <h2 className="font-brutal text-xl uppercase leading-none tracking-tight sm:text-2xl">
          {title}
        </h2>
        {subtitle && (
          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-neutral-600 dark:text-neutral-400">
            {subtitle}
          </p>
        )}
      </div>
      {actions && (
        <div className="flex flex-wrap items-center gap-2 sm:shrink-0 sm:justify-end">
          {actions}
        </div>
      )}
    </header>
  );
}
