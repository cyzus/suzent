import React from 'react';
import { Redirect, Router, useLocation } from 'wouter';
import { useHashLocation } from 'wouter/use-hash-location';

import App from '../App';
import { AboutTab } from '../components/settings/AboutTab';
import { DevicesTab } from '../components/settings/DevicesTab';
import { MeshTab } from '../components/settings/MeshTab';
import { UsageTab } from '../components/settings/UsageTab';
import { SettingsModal } from '../components/settings/SettingsModal';
import type { SettingsCategory } from '../components/settings/SettingsNavigation';
import { ConsolePage } from './ConsolePage';
import { ConsoleSidebar } from './ConsoleSidebar';
import { OpsTab } from './OpsTab';
import {
  LEGACY_SETTINGS_PATH,
  LEGACY_SETTINGS_TARGET,
  WEB_DESTINATIONS,
  type WebDestination,
} from './webRoutes';

/**
 * Categories that can render with the backend still down.
 *
 * These four take no props and read no shared settings state, which is what
 * lets the console show them while the backend is still coming up -- and a
 * console opened at a struggling host is opened to look at exactly these.
 * Everything else needs the providers, role models and social config that the
 * settings state loads once, so it waits like the desktop modal does.
 */
const UNGATED: Partial<Record<SettingsCategory, React.ComponentType>> = {
  devices: DevicesTab,
  mesh: MeshTab,
  usage: UsageTab,
  about: AboutTab,
};

function CategoryPage({ destination }: { destination: WebDestination }): React.ReactElement {
  const [, navigate] = useLocation();
  const category = destination.category as SettingsCategory;
  const Ungated = UNGATED[category];

  const page = Ungated ? (
    <Ungated />
  ) : (
    // Mounted inside App because the panels read the chat store. It stays
    // mounted across these routes -- only its category changes -- so moving
    // between them costs nothing and the debounced autosave is never cut off
    // halfway by a navigation.
    <SettingsModal
      isOpen
      category={category}
      onCategoryChange={(next) => {
        const target = WEB_DESTINATIONS.find((d) => d.category === next);
        if (target) navigate(target.path);
      }}
      onClose={() => navigate('/')}
    />
  );

  const framed = <ConsolePage wide={destination.wide}>{page}</ConsolePage>;
  return Ungated ? framed : <App>{framed}</App>;
}

function ConsoleRoute(): React.ReactElement {
  const [location] = useLocation();

  if (location === LEGACY_SETTINGS_PATH) return <Redirect to={LEGACY_SETTINGS_TARGET} replace />;

  const destination = WEB_DESTINATIONS.find((candidate) => candidate.path === location);

  // Chat is the fallback as well as "/": an unknown hash lands somewhere
  // usable rather than on an empty pane.
  if (!destination || !destination.framed) return <App />;

  if (!destination.category) {
    return (
      <ConsolePage wide={destination.wide}>
        <OpsTab />
      </ConsolePage>
    );
  }

  return <CategoryPage destination={destination} />;
}

/**
 * The web console.
 *
 * The desktop app is a chat window that hides its operational surfaces in a
 * modal, which is right when the machine is in front of you. A browser session
 * is the opposite case -- a headless host, reached from elsewhere -- so here
 * those surfaces are destinations of their own and chat is one of them.
 *
 * Routed by lookup rather than by a <Switch> of <Route>s: the sidebar and the
 * router then read the same list, and a destination cannot be listed without
 * being reachable.
 */
function ConsoleLayout(): React.ReactElement {
  const [location] = useLocation();

  // Chat is the one destination that arrives with a column of its own, so the
  // navigation shrinks to its rail there rather than standing a second
  // labelled sidebar next to the first. Everywhere else it keeps its labels.
  const onChat = !WEB_DESTINATIONS.some(
    (candidate) => candidate.path === location && candidate.path !== '/'
  );

  return (
    <div className="flex h-full w-full overflow-hidden">
      <ConsoleSidebar railOnly={onChat} />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden bg-dot-pattern">
        <ConsoleRoute />
      </div>
    </div>
  );
}

export function WebShell(): React.ReactElement {
  return (
    <Router hook={useHashLocation}>
      <ConsoleLayout />
    </Router>
  );
}
