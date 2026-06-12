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
    <div className="bg-brutal-black text-white p-3 border-3 border-brutal-black flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h3 className="font-brutal text-xl uppercase tracking-tight">{title}</h3>
        {subtitle && <p className="text-xs text-neutral-300 font-mono">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
    </div>
  );
}
