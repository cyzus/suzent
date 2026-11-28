import React from 'react';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import { useLocation } from 'wouter';

import { AboutTab } from '../components/settings/AboutTab';
import { DevicesTab } from '../components/settings/DevicesTab';
import { MeshTab } from '../components/settings/MeshTab';
import { UsageTab } from '../components/settings/UsageTab';
import {
  categoryDefinition,
  type SettingsCategory,
} from '../components/settings/SettingsNavigation';
import { HostStatus } from '../components/sidebar/HostStatus';
import { useI18n } from '../i18n';
import { ConsolePage } from './ConsolePage';
import { OpsTab } from './OpsTab';
import { CHAT_PATH, OFFLINE_CATEGORIES, pathForCategory } from './webRoutes';

const PAGES: Partial<Record<SettingsCategory, React.ComponentType>> = {
  devices: DevicesTab,
  mesh: MeshTab,
  ops: OpsTab,
  usage: UsageTab,
  about: AboutTab,
};

/**
 * The troubleshooting pages, for a host that does not answer.
 *
 * Everything else waits for the backend, the way the desktop does. These five
 * read nothing the chat providers load, and they are what someone opens when
 * the host is struggling, so they get a frame of their own instead of the
 * loading screen.
 */
export function OfflineConsole({ category }: { category: SettingsCategory }): React.ReactElement {
  const { t } = useI18n();
  const [, navigate] = useLocation();
  const Page = PAGES[category];

  return (
    <div className="flex h-full w-full overflow-hidden bg-neutral-50 text-brutal-black dark:bg-zinc-900 dark:text-white">
      <nav
        aria-label={t('settings.title')}
        className="flex w-14 shrink-0 flex-col border-r-3 border-brutal-black bg-white dark:bg-zinc-800 md:w-60"
      >
        <button
          type="button"
          onClick={() => navigate(CHAT_PATH)}
          className="flex h-12 shrink-0 items-center justify-center gap-2 border-b-3 border-brutal-black px-4 text-sm font-bold hover:bg-neutral-100 dark:hover:bg-zinc-700 md:justify-start"
          title={t('console.nav.chat')}
        >
          <ArrowLeftIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="hidden truncate md:inline">{t('console.nav.chat')}</span>
        </button>
        <p className="hidden px-4 py-3 text-xs leading-5 text-neutral-500 dark:text-neutral-400 md:block">
          {t('console.offline.notice')}
        </p>
        <div className="flex-1 space-y-0.5 overflow-y-auto py-2 md:px-3">
          {OFFLINE_CATEGORIES.map((id) => {
            const definition = categoryDefinition(id);
            if (!definition) return null;
            const { labelKey, icon: Icon } = definition;
            const active = id === category;
            return (
              <button
                key={id}
                type="button"
                onClick={() => navigate(pathForCategory(id))}
                title={t(labelKey)}
                aria-current={active ? 'page' : undefined}
                className={`flex w-full items-center justify-center gap-3 border-l-4 py-1.5 text-left text-sm font-bold transition-colors md:justify-start md:px-3 ${
                  active
                    ? 'border-brutal-black bg-brutal-yellow text-brutal-black dark:border-brutal-yellow'
                    : 'border-transparent text-neutral-700 hover:border-neutral-300 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-zinc-700'
                }`}
              >
                <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
                <span className="hidden min-w-0 truncate md:inline">{t(labelKey)}</span>
              </button>
            );
          })}
        </div>
        <HostStatus />
      </nav>
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden bg-dot-pattern">
        <ConsolePage wide={category === 'usage'}>{Page ? <Page /> : null}</ConsolePage>
      </div>
    </div>
  );
}
