import React from 'react';
import {
  ChevronDoubleLeftIcon,
  ChevronDoubleRightIcon,
  MoonIcon,
  SunIcon,
} from '@heroicons/react/24/outline';
import { useLocation } from 'wouter';

import { useBackendHealth } from '../hooks/useBackendHealth';
import { useI18n } from '../i18n';
import { useTheme } from '../hooks/useTheme';
import { WEB_DESTINATION_GROUPS } from './webRoutes';

const HEALTH_DOT: Record<string, string> = {
  checking: 'bg-neutral-400',
  online: 'bg-brutal-green',
  offline: 'bg-brutal-red',
};

const COLLAPSE_KEY = 'suzent.console.navCollapsed';

/**
 * Whether the sidebar shows labels.
 *
 * Expanded by default -- on a console page nothing else is in the gutter --
 * and collapsed to a rail for anyone who would rather have the width. The
 * choice is remembered because it is a statement about how the console should
 * look, not about the page it was made on.
 */
function useCollapsed(): [boolean, () => void] {
  const [collapsed, setCollapsed] = React.useState<boolean>(() => {
    try {
      return window.localStorage.getItem(COLLAPSE_KEY) === 'true';
    } catch {
      return false;
    }
  });

  const toggle = React.useCallback(() => {
    setCollapsed((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(COLLAPSE_KEY, String(next));
      } catch {
        // A console opened in a private window still navigates; it just
        // forgets the choice.
      }
      return next;
    });
  }, []);

  return [collapsed, toggle];
}

/**
 * The console's navigation.
 *
 * Every page the console can reach is here, grouped: there is no second list
 * and no page that lives only behind another one. Collapsed it is the icon
 * rail the console shipped with; expanded it is that rail with its labels and
 * group headings, which is what the settings sidebar used to supply for half
 * the destinations.
 *
 * On chat it is the rail and only the rail. Chat brings its own column of
 * projects and conversations, and two labelled sidebars side by side read as
 * two applications sharing a window; a 56px rail beside that column reads as
 * one navigation with a list in it, which is what it is.
 */
interface ConsoleSidebarProps {
  /**
   * Stay a rail: no labels, no toggle, and a hairline instead of the heavy
   * outer border, so the column beside it reads as part of the same thing.
   */
  railOnly?: boolean;
}

export function ConsoleSidebar({ railOnly = false }: ConsoleSidebarProps): React.ReactElement {
  const { t } = useI18n();
  const [location, navigate] = useLocation();
  const health = useBackendHealth();
  const { theme, toggleTheme } = useTheme();
  const [preference, toggleCollapsed] = useCollapsed();
  const collapsed = railOnly || preference;

  // Below `md` there is no room for labels whatever the preference says, so the
  // width and the label visibility are CSS rather than state.
  const width = collapsed ? 'w-14' : 'w-14 md:w-60 lg:w-64';
  const labels = collapsed ? 'hidden' : 'hidden md:block';
  const edge = railOnly
    ? 'border-r-2 border-neutral-300 dark:border-zinc-700'
    : 'border-r-4 border-brutal-black';
  // A 56px rail has no room to spare: its own border, the list's padding, the
  // row's active accent and a scrollbar together leave less than an icon's
  // width, which clipped them. Collapsed, the row is the icon and nothing else.
  const gutter = collapsed ? 'px-0' : 'px-0 md:px-2';
  const row = collapsed
    ? 'justify-center gap-0 px-0'
    : 'justify-center gap-0 px-0 md:justify-start md:gap-3 md:px-2';
  const themeLabel = theme === 'dark' ? t('settings.switchToLight') : t('settings.switchToDark');

  return (
    <nav
      aria-label={t('console.nav.label')}
      className={`flex ${width} ${edge} shrink-0 flex-col bg-white transition-[width] dark:bg-zinc-800`}
    >
      <div className="flex h-12 items-center justify-between gap-2 border-b-4 border-brutal-black bg-brutal-yellow px-2 text-brutal-black">
        <h1
          className={`${labels} min-w-0 truncate pl-1 font-brutal text-lg font-bold uppercase tracking-tight`}
        >
          {t('console.nav.title')}
        </h1>
        {railOnly ? (
          // The mark stands in for the toggle, which has nothing to do here.
          // Keeping the bar means the rail lines up with the header beside it
          // instead of starting a second, shorter grid.
          <span
            className="mx-auto font-brutal text-lg font-bold leading-none"
            title={t('console.nav.title')}
            aria-hidden="true"
          >
            &#9642;
          </span>
        ) : (
          <button
            type="button"
            onClick={toggleCollapsed}
            title={t(collapsed ? 'console.nav.expand' : 'console.nav.collapse')}
            aria-label={t(collapsed ? 'console.nav.expand' : 'console.nav.collapse')}
            aria-expanded={!collapsed}
            className="mx-auto flex h-8 w-8 shrink-0 items-center justify-center border-2 border-transparent text-brutal-black transition-colors hover:border-brutal-black hover:bg-brutal-black/10 md:mx-0"
          >
            {collapsed ? (
              <ChevronDoubleRightIcon className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ChevronDoubleLeftIcon className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        )}
      </div>

      <div className={`flex-1 overflow-y-auto overflow-x-hidden ${gutter} py-2 scrollbar-thin`}>
        {WEB_DESTINATION_GROUPS.map((group) => (
          <section key={group.labelKey || 'top'} className="mb-3 last:mb-0">
            {group.labelKey && (
              <h2
                className={`${labels} mb-1.5 px-2 md:px-4 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-neutral-500 dark:text-neutral-400`}
              >
                {t(group.labelKey)}
              </h2>
            )}
            <div className="space-y-0.5">
              {group.destinations.map(({ path, labelKey, icon: Icon }) => {
                const active = location === path;
                return (
                  <button
                    key={path}
                    type="button"
                    onClick={() => navigate(path)}
                    title={t(labelKey)}
                    aria-label={t(labelKey)}
                    aria-current={active ? 'page' : undefined}
                    className={`group flex w-full items-center border-l-4 ${row} py-1.5 text-left text-sm font-bold transition-colors ${
                      active
                        ? 'border-brutal-yellow bg-brutal-black text-white dark:border-brutal-black dark:bg-brutal-yellow dark:text-brutal-black'
                        : 'border-transparent text-neutral-700 hover:border-neutral-300 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:border-zinc-500 dark:hover:bg-zinc-700'
                    }`}
                  >
                    <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
                    <span className={`${labels} min-w-0 truncate`}>{t(labelKey)}</span>
                  </button>
                );
              })}
            </div>
          </section>
        ))}
      </div>

      {/* Light and dark belong to the window, not to the conversation, so the
          switch sits with the navigation rather than in the chat header: one
          place on every route, including the rail, where the header the
          desktop puts it in is not drawn at all. */}
      <div className={`border-t-2 border-neutral-300 pt-1 dark:border-zinc-600 ${gutter}`}>
        <button
          type="button"
          onClick={toggleTheme}
          title={themeLabel}
          aria-label={themeLabel}
          className={`group flex w-full items-center border-l-4 border-transparent ${row} py-1.5 text-left text-sm font-bold text-neutral-700 transition-colors hover:border-neutral-300 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:border-zinc-500 dark:hover:bg-zinc-700`}
        >
          {theme === 'dark' ? (
            <SunIcon className="h-5 w-5 shrink-0" aria-hidden="true" />
          ) : (
            <MoonIcon className="h-5 w-5 shrink-0" aria-hidden="true" />
          )}
          <span className={`${labels} min-w-0 truncate`}>{themeLabel}</span>
        </button>
      </div>

      {/* The host and its reachability, pinned low. A browser pointed at a
          remote Suzent cannot tell a stopped server from a dropped tunnel from
          a revoked token until it sends a request, so the console keeps the
          answer -- and which host it is talking to -- permanently on screen. */}
      <div
        className={`flex items-center gap-2 border-t border-neutral-200 py-2 dark:border-zinc-700 ${
          collapsed ? 'justify-center px-0' : 'px-3'
        }`}
        title={`${window.location.host} - ${t(`console.health.${health}`)}`}
      >
        <span
          className={`h-2.5 w-2.5 shrink-0 rounded-full ${HEALTH_DOT[health]}`}
          aria-hidden="true"
        />
        <span
          className={`${labels} min-w-0 truncate font-mono text-[11px] text-neutral-500 dark:text-neutral-400`}
        >
          {window.location.host}
        </span>
        <span className="sr-only">{t(`console.health.${health}`)}</span>
      </div>
    </nav>
  );
}
