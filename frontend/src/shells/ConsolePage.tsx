import React from 'react';

interface ConsolePageProps {
  children: React.ReactNode;
  /** Usage renders wide tables and needs the extra column. */
  wide?: boolean;
}

/**
 * The scroll frame around a console page.
 *
 * Deliberately thin: every page the console hosts is a settings tab that
 * already draws its own SettingsHeader, so adding a second title here would
 * double it. What the modal supplied and a route does not is the scrolling
 * column and its measure -- that is all this restores.
 */
export function ConsolePage({ children, wide = false }: ConsolePageProps): React.ReactElement {
  return (
    <div className="settings-content flex-1 overflow-y-auto p-3 scrollbar-thin sm:p-5 lg:p-6">
      <div className={`${wide ? 'max-w-6xl' : 'max-w-5xl'} mx-auto`}>{children}</div>
    </div>
  );
}
