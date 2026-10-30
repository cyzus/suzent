/**
 * The overview's memory section: what the latest turn recalled, what this chat
 * saved, and a light hint of the background organizing that spans every chat.
 */

import { useEffect, useState } from 'react';
import { ChevronRightIcon } from '@heroicons/react/24/outline';
import { useChatCoreStore } from '../../hooks/useChatStore';
import { useDreamStatus } from '../../hooks/useDreamStatus';
import type { MemorySection } from '../../hooks/useMemorySection';
import { useI18n } from '../../i18n';
import { formatRelativeTime } from '../../lib/chatUtils';
import { memoryApi } from '../../lib/memoryApi';
import type { MemoryKind, RecentMemoryChanges } from '../../types/memory';
import { OverviewList } from '../chat/SidebarOverview';

const KIND_ORDER: MemoryKind[] = ['user', 'experience', 'world'];

export function MemoryCount({ section }: { section: MemorySection }): JSX.Element | null {
  const { t } = useI18n();
  if (!section.enabled) return <>{t('sidebar.memory.off')}</>;
  const used = section.activity?.recalled?.items.length ?? 0;
  return used > 0 ? <>{t('sidebar.memory.used', { count: String(used) })}</> : null;
}

/** The collapsed preview: the memories the latest turn drew on. */
export function MemoryPreview({ section }: { section: MemorySection }): JSX.Element | null {
  const items = section.enabled ? (section.activity?.recalled?.items ?? []) : [];
  if (items.length === 0) return null;
  return (
    <ul className="mt-1.5 space-y-0.5">
      {items.slice(0, 2).map((item) => (
        <li
          key={item.id}
          className="flex items-center gap-2 text-xs text-neutral-500 dark:text-neutral-400"
        >
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-neutral-300 dark:bg-zinc-600" />
          <span className="truncate">{item.content}</span>
        </li>
      ))}
    </ul>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }): JSX.Element {
  return (
    <div className="mb-2">
      <div className="mb-0.5 text-[10px] uppercase tracking-wide text-neutral-400 dark:text-neutral-500">
        {title}
      </div>
      {children}
    </div>
  );
}

function Dot(): JSX.Element {
  return <span className="h-1.5 w-1.5 rounded-full bg-neutral-300 dark:bg-zinc-600" />;
}

function OrganizeHint(): JSX.Element {
  const { t, locale } = useI18n();
  const { status, loading } = useDreamStatus();
  const [changes, setChanges] = useState<RecentMemoryChanges | null>(null);

  useEffect(() => {
    let cancelled = false;
    memoryApi
      .getRecentChanges()
      .then((next) => {
        if (!cancelled) setChanges(next);
      })
      .catch(() => {
        // Only a hint; the organize status above still reads fine without it.
        if (!cancelled) setChanges(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const pendingDays = status?.pending_count ?? 0;
  const headline =
    loading && !status
      ? t('memoryView.organize.loading')
      : !status?.active || !status.enabled
        ? t('memoryView.organize.off')
        : status.running
          ? t('memoryView.organize.running')
          : pendingDays > 0
            ? t('memoryView.organize.waiting', { count: String(pendingDays) })
            : t('memoryView.organize.caughtUp');
  const lastRun = formatRelativeTime(status?.last_ingest_finished_at, locale);

  const recent = changes
    ? ([
        ...KIND_ORDER.filter((kind) => (changes.added[kind] ?? 0) > 0).map((kind) =>
          t(`memoryView.recent.added.${kind}`, { count: String(changes.added[kind]) })
        ),
        changes.revised.length > 0 &&
          t('memoryView.recent.revised', { count: String(changes.revised.length) }),
        changes.confirmed.length > 0 &&
          t('memoryView.recent.confirmed', { count: String(changes.confirmed.length) }),
      ].filter(Boolean) as string[])
    : [];

  return (
    <div className="space-y-0.5 text-xs text-neutral-600 dark:text-neutral-300">
      <div className="flex items-baseline justify-between gap-3">
        <span className="truncate">{headline}</span>
        {lastRun && (
          <span className="shrink-0 font-mono text-[11px] text-neutral-400 dark:text-neutral-500">
            {lastRun}
          </span>
        )}
      </div>
      {changes && (
        <div className="truncate text-neutral-500 dark:text-neutral-400">
          {t('memoryView.recent.title')} ·{' '}
          {recent.length > 0 ? recent.join(' · ') : t('memoryView.recent.quiet')}
        </div>
      )}
    </div>
  );
}

export function MemoryDetails({ section }: { section: MemorySection }): JSX.Element | null {
  const { t } = useI18n();
  const { switchToView } = useChatCoreStore();
  if (!section.enabled) return null;
  const recalled = section.activity?.recalled?.items ?? [];
  const saved = section.activity?.saved ?? [];

  return (
    <div>
      <Group title={t('sidebar.memory.thisTurn')}>
        <OverviewList
          items={recalled}
          empty={t('sidebar.memory.noneUsed')}
          getKey={(item) => item.id}
          renderMarker={() => <Dot />}
          renderLabel={(item) => <span title={item.content}>{item.content}</span>}
        />
      </Group>
      <Group title={t('sidebar.memory.savedHere')}>
        {section.extracting && (
          <p className="py-0.5 text-xs text-neutral-500 dark:text-neutral-400">
            {t('sidebar.memory.saving')}
          </p>
        )}
        {(saved.length > 0 || !section.extracting) && (
          <OverviewList
            items={saved}
            empty={t('sidebar.memory.noneSaved')}
            getKey={(fact) => `${fact.date}-${fact.time}-${fact.content}`}
            renderMarker={() => <Dot />}
            renderLabel={(fact) => (
              <span title={fact.content}>
                {fact.revision && (
                  <span className="mr-1 text-neutral-400 dark:text-neutral-500">
                    {t('memoryView.recent.revisedLabel')}
                  </span>
                )}
                {fact.content}
              </span>
            )}
          />
        )}
      </Group>
      <Group title={t('sidebar.memory.organize')}>
        <OrganizeHint />
      </Group>
      <button
        type="button"
        onClick={() => switchToView?.('memory')}
        className="inline-flex items-center gap-0.5 text-xs text-neutral-400 hover:text-brutal-black dark:hover:text-white"
      >
        {t('sidebar.memory.openPage')}
        <ChevronRightIcon className="h-3 w-3" />
      </button>
    </div>
  );
}
