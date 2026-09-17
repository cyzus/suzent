import React from 'react';
import { Route, Router, Switch, useLocation } from 'wouter';
import { useHashLocation } from 'wouter/use-hash-location';

import App from '../App';
import { AboutTab } from '../components/settings/AboutTab';
import { DevicesTab } from '../components/settings/DevicesTab';
import { MeshTab } from '../components/settings/MeshTab';
import { UsageTab } from '../components/settings/UsageTab';
import { SettingsModal } from '../components/settings/SettingsModal';
import { useBackendHealth } from '../hooks/useBackendHealth';
import { useI18n } from '../i18n';
import { ConsolePage } from './ConsolePage';
import { OpsTab } from './OpsTab';
import { WEB_DESTINATIONS } from './webRoutes';

const HEALTH_DOT: Record<string, string> = {
  checking: 'bg-neutral-400',
  online: 'bg-brutal-green',
  offline: 'bg-brutal-red',
};

function NavRail(): React.ReactElement {
  const { t } = useI18n();
  const [location, navigate] = useLocation();
  const health = useBackendHealth();

  return (
    <nav
      aria-label={t('console.nav.label')}
      className="flex w-14 shrink-0 flex-col items-center border-r-3 border-brutal-black bg-neutral-100 py-2 dark:bg-zinc-900"
    >
      <div className="flex flex-col items-center gap-1">
        {WEB_DESTINATIONS.map(({ path, labelKey, icon: Icon }) => {
          const active = location === path;
          return (
            <button
              key={path}
              type="button"
              onClick={() => navigate(path)}
              title={t(labelKey)}
              aria-label={t(labelKey)}
              aria-current={active ? 'page' : undefined}
              className={`flex h-10 w-10 items-center justify-center border-2 transition-colors ${
                active
                  ? 'border-brutal-black bg-brutal-yellow text-brutal-black shadow-brutal-sm'
                  : 'border-transparent text-neutral-600 hover:border-brutal-black hover:bg-neutral-200 dark:text-neutral-400 dark:hover:bg-zinc-800'
              }`}
            >
              <Icon className="h-5 w-5" />
            </button>
          );
        })}
      </div>

      {/* The host and its reachability, pinned low. A browser pointed at a
          remote Suzent cannot tell a stopped server from a dropped tunnel from
          a revoked token until it sends a request, so the console keeps the
          answer -- and which host it is talking to -- permanently on screen. */}
      <div
        className="mt-auto flex flex-col items-center gap-1 pb-1"
        title={`${window.location.host} - ${t(`console.health.${health}`)}`}
      >
        <span className={`h-2.5 w-2.5 rounded-full ${HEALTH_DOT[health]}`} aria-hidden="true" />
        <span className="sr-only">{t(`console.health.${health}`)}</span>
      </div>
    </nav>
  );
}

function ConsoleSettings(): React.ReactElement {
  const [, navigate] = useLocation();
  // SettingsModal owns a great deal of cross-category state; hosting it whole
  // is what keeps every category reachable in the console without forking it.
  // It reads the chat store, so it has to sit inside App's provider stack --
  // which also means it waits on the backend, as the desktop modal does.
  //
  // `embedded` drops the dialog chrome: here settings is a destination that
  // already owns the pane, not something floating over the screen it took you
  // away from.
  return (
    <App>
      <SettingsModal isOpen embedded onClose={() => navigate('/')} />
    </App>
  );
}

/**
 * The web console.
 *
 * The desktop app is a chat window that hides its operational surfaces in a
 * modal, which is right when the machine is in front of you. A browser session
 * is the opposite case -- a headless host, reached from elsewhere -- so here
 * those surfaces are destinations of their own and chat is one of them.
 */
export function WebShell(): React.ReactElement {
  return (
    <Router hook={useHashLocation}>
      <div className="flex h-full w-full overflow-hidden">
        <NavRail />
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <Switch>
            <Route path="/ops">
              <ConsolePage>
                <OpsTab />
              </ConsolePage>
            </Route>
            <Route path="/devices">
              <ConsolePage>
                <DevicesTab />
              </ConsolePage>
            </Route>
            <Route path="/mesh">
              <ConsolePage>
                <MeshTab />
              </ConsolePage>
            </Route>
            <Route path="/usage">
              <ConsolePage wide>
                <UsageTab />
              </ConsolePage>
            </Route>
            <Route path="/settings">
              <ConsoleSettings />
            </Route>
            <Route path="/about">
              <ConsolePage>
                <AboutTab />
              </ConsolePage>
            </Route>
            {/* Chat is the fallback as well as "/": an unknown hash lands
                somewhere usable rather than on an empty pane.

                Note what is deliberately *outside* App above: Devices, Mesh,
                Usage and About mount without its readiness gate, so a console
                opened at a struggling host still shows the pages you would
                open it to look at. */}
            <Route>
              <App />
            </Route>
          </Switch>
        </div>
      </div>
    </Router>
  );
}
