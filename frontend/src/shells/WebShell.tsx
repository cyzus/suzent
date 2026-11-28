import React from 'react';
import { Redirect, Router, useLocation } from 'wouter';
import { useHashLocation } from 'wouter/use-hash-location';

import App from '../App';
import { LEGACY_SETTINGS_PATH, LEGACY_SETTINGS_TARGET } from './webRoutes';

function WebRoutes(): React.ReactElement {
  const [location] = useLocation();
  if (location === LEGACY_SETTINGS_PATH) return <Redirect to={LEGACY_SETTINGS_TARGET} replace />;
  return <App />;
}

/**
 * The browser shell.
 *
 * Laid out like the desktop: one sidebar, whose chat list gives way to the
 * settings list when settings opens. What a browser adds is an address for
 * every settings category (hash-routed, so any static host can serve it), the
 * host it is talking to pinned under the sidebar, and a few troubleshooting
 * pages that still open when that host does not answer.
 */
export function WebShell(): React.ReactElement {
  return (
    <Router hook={useHashLocation}>
      <WebRoutes />
    </Router>
  );
}
