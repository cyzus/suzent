/**
 * One line of what memory did this week — picked up, corrected, heard again — so
 * the page opens on change rather than on a wall of cards.
 */

import React, { useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import { memoryApi } from '../../lib/memoryApi';
import type { MemoryKind, RecentMemoryChanges } from '../../types/memory';

const KIND_ORDER: MemoryKind[] = ['user', 'experience', 'world'];

export const RecentChanges: React.FC<{ refreshKey?: number }> = ({ refreshKey }) => {
  const { t } = useI18n();
  const [changes, setChanges] = useState<RecentMemoryChanges | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    memoryApi
      .getRecentChanges()
      .then((next) => {
        if (!cancelled) setChanges(next);
      })
      .catch(() => {
        // The strip is a nicety; the list below still works without it.
        if (!cancelled) setChanges(null);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (!changes) return null;

  const added = KIND_ORDER.filter((kind) => (changes.added[kind] ?? 0) > 0).map((kind) =>
    t(`memoryView.recent.added.${kind}`, { count: String(changes.added[kind]) })
  );
  const parts = [
    ...added,
    changes.revised.length > 0 &&
      t('memoryView.recent.revised', { count: String(changes.revised.length) }),
    changes.confirmed.length > 0 &&
      t('memoryView.recent.confirmed', { count: String(changes.confirmed.length) }),
  ].filter(Boolean) as string[];
  const hasDetail = changes.revised.length > 0 || changes.confirmed.length > 0;

  return (
    <div className="border-2 border-brutal-black bg-brutal-yellow/30 px-3 py-2 text-xs text-brutal-black dark:bg-zinc-800 dark:text-white">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="font-bold uppercase tracking-wide">{t('memoryView.recent.title')}</span>
        <span>{parts.length > 0 ? parts.join(' · ') : t('memoryView.recent.quiet')}</span>
        {hasDetail && (
          <button
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            className="ml-auto font-bold underline-offset-2 hover:underline"
          >
            {open ? t('memoryView.recent.hide') : t('memoryView.recent.show')}
          </button>
        )}
      </div>
      {open && (
        <ul className="mt-2 space-y-1 border-t border-dashed border-brutal-black/40 pt-2">
          {changes.revised.map((item) => (
            <li key={`r-${item.id}`}>
              <span className="mr-1.5 font-bold">{t('memoryView.recent.revisedLabel')}</span>
              {item.content}
            </li>
          ))}
          {changes.confirmed.map((item) => (
            <li key={`c-${item.content}`}>
              <span className="mr-1.5 font-bold">{t('memoryView.recent.confirmedLabel')}</span>
              {item.content}
              {item.count > 1 && <span className="ml-1 font-mono opacity-60">×{item.count}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
