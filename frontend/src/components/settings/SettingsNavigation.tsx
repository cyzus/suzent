import React from 'react';
import {
  AdjustmentsHorizontalIcon,
  BoltIcon,
  ChartBarIcon,
  ChatBubbleLeftRightIcon,
  CircleStackIcon,
  ClockIcon,
  CloudArrowUpIcon,
  ComputerDesktopIcon,
  Cog6ToothIcon,
  CpuChipIcon,
  InformationCircleIcon,
  PaintBrushIcon,
  ServerStackIcon,
  ShareIcon,
  ShieldCheckIcon,
  WrenchScrewdriverIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

import { useI18n } from '../../i18n';
import { BrutalButton } from '../BrutalButton';
import { BrutalSelect } from '../BrutalSelect';

export type SettingsCategory =
  | 'providers'
  | 'roles'
  | 'memory'
  | 'automation'
  | 'social'
  | 'mcp'
  | 'acp-agents'
  | 'devices'
  | 'mesh'
  | 'appearance'
  | 'service'
  | 'security'
  | 'data'
  | 'usage'
  | 'about';

type CategoryDefinition = {
  id: SettingsCategory;
  labelKey: string;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
};

type CategoryGroup = {
  id: 'agent' | 'connections' | 'application';
  labelKey: string;
  categories: CategoryDefinition[];
};

const CATEGORY_GROUPS: CategoryGroup[] = [
  {
    id: 'agent',
    labelKey: 'settings.groups.agent',
    categories: [
      { id: 'providers', labelKey: 'settings.categories.providers', icon: ServerStackIcon },
      { id: 'roles', labelKey: 'settings.categories.roles', icon: AdjustmentsHorizontalIcon },
      { id: 'memory', labelKey: 'settings.categories.memory', icon: CircleStackIcon },
      { id: 'automation', labelKey: 'settings.categories.automation', icon: ClockIcon },
    ],
  },
  {
    id: 'connections',
    labelKey: 'settings.groups.connections',
    categories: [
      { id: 'social', labelKey: 'settings.categories.social', icon: ChatBubbleLeftRightIcon },
      { id: 'mcp', labelKey: 'settings.categories.mcp', icon: WrenchScrewdriverIcon },
      { id: 'acp-agents', labelKey: 'settings.categories.acpAgents', icon: BoltIcon },
      { id: 'devices', labelKey: 'settings.categories.devices', icon: ComputerDesktopIcon },
      { id: 'mesh', labelKey: 'settings.categories.mesh', icon: ShareIcon },
    ],
  },
  {
    id: 'application',
    labelKey: 'settings.groups.application',
    categories: [
      { id: 'appearance', labelKey: 'settings.categories.appearance', icon: PaintBrushIcon },
      { id: 'service', labelKey: 'settings.categories.service', icon: CpuChipIcon },
      { id: 'security', labelKey: 'settings.categories.security', icon: ShieldCheckIcon },
      { id: 'data', labelKey: 'settings.categories.data', icon: CloudArrowUpIcon },
      { id: 'usage', labelKey: 'settings.categories.usage', icon: ChartBarIcon },
      { id: 'about', labelKey: 'settings.categories.about', icon: InformationCircleIcon },
    ],
  },
];

interface SettingsNavigationProps {
  activeCategory: SettingsCategory;
  onCategoryChange: (category: SettingsCategory) => void;
  onClose: () => void;
}

function SettingsTitle({ onClose }: { onClose: () => void }): React.ReactElement {
  const { t } = useI18n();

  return (
    <div className="flex items-center justify-between gap-3 border-b-4 border-brutal-black bg-brutal-yellow px-4 py-3 text-brutal-black">
      <div className="flex min-w-0 items-center gap-2.5">
        <Cog6ToothIcon className="h-6 w-6 shrink-0" aria-hidden="true" />
        <h1 className="truncate font-brutal text-xl font-bold uppercase tracking-tight">
          {t('settings.title')}
        </h1>
      </div>
      <BrutalButton
        type="button"
        variant="light"
        size="icon-lg"
        onClick={onClose}
        aria-label={t('common.close')}
        title={t('common.close')}
        className="shrink-0"
      >
        <XMarkIcon className="h-5 w-5" aria-hidden="true" />
      </BrutalButton>
    </div>
  );
}

export function SettingsNavigation({
  activeCategory,
  onCategoryChange,
  onClose,
}: SettingsNavigationProps): React.ReactElement {
  const { t } = useI18n();

  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r-4 border-brutal-black bg-white dark:bg-zinc-800 md:flex lg:w-64">
      <SettingsTitle onClose={onClose} />
      <nav
        className="flex-1 overflow-y-auto px-3 py-3 scrollbar-thin"
        aria-label={t('settings.title')}
      >
        <div className="space-y-3">
          {CATEGORY_GROUPS.map((group) => (
            <section key={group.id} aria-labelledby={`settings-group-${group.id}`}>
              <h2
                id={`settings-group-${group.id}`}
                className="mb-1.5 px-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-neutral-500 dark:text-neutral-400"
              >
                {t(group.labelKey)}
              </h2>
              <div className="space-y-0.5">
                {group.categories.map(({ id, labelKey, icon: Icon }) => {
                  const active = activeCategory === id;
                  return (
                    <button
                      key={id}
                      type="button"
                      onClick={() => onCategoryChange(id)}
                      aria-current={active ? 'page' : undefined}
                      className={`group flex w-full items-center gap-3 border-l-4 px-3 py-1.5 text-left text-sm font-bold transition-colors ${
                        active
                          ? 'border-brutal-yellow bg-brutal-black text-white dark:border-brutal-black dark:bg-brutal-yellow dark:text-brutal-black'
                          : 'border-transparent text-neutral-700 hover:border-neutral-300 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:border-zinc-500 dark:hover:bg-zinc-700'
                      }`}
                    >
                      <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
                      <span className="min-w-0 truncate">{t(labelKey)}</span>
                    </button>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      </nav>
    </aside>
  );
}

export function SettingsMobileNavigation({
  activeCategory,
  onCategoryChange,
  onClose,
}: SettingsNavigationProps): React.ReactElement {
  const { t } = useI18n();
  const options = CATEGORY_GROUPS.flatMap((group) =>
    group.categories.map((category) => ({
      value: category.id,
      label: t(category.labelKey),
      group: t(group.labelKey),
    }))
  );

  return (
    <div className="border-b-4 border-brutal-black bg-white dark:bg-zinc-800 md:hidden">
      <SettingsTitle onClose={onClose} />
      <div className="p-3">
        <BrutalSelect
          value={activeCategory}
          onChange={(value) => onCategoryChange(value as SettingsCategory)}
          options={options}
          label={t('settings.category')}
          buttonClassName="py-2"
        />
      </div>
    </div>
  );
}
