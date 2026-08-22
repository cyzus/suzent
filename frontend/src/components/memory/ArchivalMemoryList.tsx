/**
 * Archival Memory List Component
 * Displays list of archival memories with search, filtering, and sorting
 */

import React, { useState, useEffect, useMemo } from 'react';
import { useI18n } from '../../i18n';
import { useMemory } from '../../hooks/useMemory';
import { MemoryCard } from './MemoryCard';
import { BrutalButton } from '../BrutalButton';
import { BrutalSelect } from '../BrutalSelect';
import type { ArchivalMemory, ArchivalQueryOptions } from '../../types/memory';

type SortOption = 'date-desc' | 'date-asc' | 'importance-desc' | 'importance-asc' | 'relevance' | 'access-desc';
type ImportanceFilter = 'all' | 'high' | 'medium' | 'low';

/**
 * Sorting and filtering happen in the database, not over the loaded pages —
 * "oldest first" has to mean the oldest memory, not the oldest of the first 20.
 */
const SORT_PARAMS: Record<
  Exclude<SortOption, 'relevance'>,
  { orderBy: NonNullable<ArchivalQueryOptions['orderBy']>; orderDesc: boolean }
> = {
  'date-desc': { orderBy: 'created_at', orderDesc: true },
  'date-asc': { orderBy: 'created_at', orderDesc: false },
  'importance-desc': { orderBy: 'importance', orderDesc: true },
  'importance-asc': { orderBy: 'importance', orderDesc: false },
  'access-desc': { orderBy: 'access_count', orderDesc: true },
};

/** Half-open bands, so high/medium/low tile the range without overlapping. */
const IMPORTANCE_BANDS: Record<
  Exclude<ImportanceFilter, 'all'>,
  { minImportance?: number; maxImportance?: number }
> = {
  high: { minImportance: 0.8 },
  medium: { minImportance: 0.5, maxImportance: 0.8 },
  low: { maxImportance: 0.5 },
};

/**
 * Day buckets give the list a journal-like rhythm — a wall of undifferentiated
 * cards is what makes archival memory unpleasant to read.
 */
interface MemoryGroup {
  key: string;
  label: string;
  memories: ArchivalMemory[];
}

export const ArchivalMemoryList: React.FC = () => {
  const { t } = useI18n();
  const {
    archivalMemories,
    archivalLoading,
    archivalError,
    archivalHasMore,
    archivalTotal,
    loadArchivalMemories,
    deleteArchivalMemory,
  } = useMemory();

  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [sortBy, setSortBy] = useState<SortOption>('date-desc');
  const [importanceFilter, setImportanceFilter] = useState<ImportanceFilter>('all');
  const [showFilters, setShowFilters] = useState(false);
  const [isCompact, setIsCompact] = useState(false);

  // Debounce search query
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(searchQuery);
    }, 500);

    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Relevance ordering needs similarity scores, which only a search returns.
  useEffect(() => {
    if (!debouncedQuery && sortBy === 'relevance') {
      setSortBy('date-desc');
    }
  }, [debouncedQuery, sortBy]);

  const queryOptions = useMemo<ArchivalQueryOptions>(() => {
    const sort = sortBy === 'relevance' ? undefined : SORT_PARAMS[sortBy];
    const band = importanceFilter === 'all' ? undefined : IMPORTANCE_BANDS[importanceFilter];
    return { ...sort, ...band };
  }, [sortBy, importanceFilter]);

  // Refetch from the top whenever the query, the ordering, or the band changes —
  // page 1 of the new ordering is a different set of rows, not a re-sort of this one.
  useEffect(() => {
    loadArchivalMemories(debouncedQuery, false, queryOptions);
  }, [debouncedQuery, queryOptions]);

  const handleLoadMore = () => {
    loadArchivalMemories(debouncedQuery, true, queryOptions);
  };

  // The server already ordered and filtered the list path. A relevance search comes
  // back ranked by similarity, so re-sorting it here is the one case left — and it
  // can only reach the results already loaded.
  const processedMemories = useMemo(() => {
    if (!debouncedQuery || sortBy === 'relevance') return archivalMemories;

    return [...archivalMemories].sort((a, b) => {
      switch (sortBy) {
        case 'date-desc':
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        case 'date-asc':
          return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
        case 'importance-desc':
          return b.importance - a.importance;
        case 'importance-asc':
          return a.importance - b.importance;
        case 'access-desc':
          return b.access_count - a.access_count;
        default:
          return 0;
      }
    });
  }, [archivalMemories, debouncedQuery, sortBy]);

  // Grouping only makes sense while the list is in date order; under relevance or
  // importance ordering the dates interleave and headers would be meaningless.
  const isDateOrdered = sortBy === 'date-desc' || sortBy === 'date-asc';

  const groupedMemories = useMemo<MemoryGroup[]>(() => {
    if (!isDateOrdered) return [];

    const groups: MemoryGroup[] = [];
    for (const memory of processedMemories) {
      const date = new Date(memory.created_at);
      const key = Number.isNaN(date.getTime()) ? 'unknown' : date.toDateString();
      const last = groups[groups.length - 1];
      if (last && last.key === key) {
        last.memories.push(memory);
      } else {
        groups.push({ key, label: formatDayLabel(date), memories: [memory] });
      }
    }
    return groups;
  }, [processedMemories, isDateOrdered]);

  function formatDayLabel(date: Date): string {
    if (Number.isNaN(date.getTime())) return t('archival.group.unknownDate');

    const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    const diffDays = Math.round((startOfDay(new Date()) - startOfDay(date)) / 86400000);
    if (diffDays === 0) return t('memoryCard.today');
    if (diffDays === 1) return t('memoryCard.yesterday');
    if (diffDays < 7) return date.toLocaleDateString(undefined, { weekday: 'long' });

    return date.toLocaleDateString(undefined, {
      year: date.getFullYear() === new Date().getFullYear() ? undefined : 'numeric',
      month: 'long',
      day: 'numeric',
    });
  }

  const activeFiltersCount = (importanceFilter !== 'all' ? 1 : 0);

  return (
    <div className="space-y-4">
      {/* Search and Filters Header */}
      <div className="border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-brutal p-4">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="min-w-0">
            <h3 className="font-brutal text-lg uppercase tracking-tight leading-none text-brutal-black dark:text-white">
              {t('archival.title')}
            </h3>
            <p className="text-[11px] text-neutral-600 dark:text-neutral-400 font-mono">
              {t('memoryView.archivalDesc')}
            </p>
          </div>
          <div className="flex shrink-0 gap-2">
            <BrutalButton
              onClick={() => setIsCompact(!isCompact)}
              size="xs"
              isActive={isCompact}
              title={isCompact ? t('archival.view.switchToCards') : t('archival.view.switchToList')}
            >
              {isCompact ? t('archival.view.list') : t('archival.view.cards')}
            </BrutalButton>
            <BrutalButton
              onClick={() => setShowFilters(!showFilters)}
              size="xs"
              isActive={showFilters}
              aria-expanded={showFilters}
            >
              {t('archival.filters')}
              {activeFiltersCount > 0 && ` (${activeFiltersCount})`}
            </BrutalButton>
          </div>
        </div>

        {/* Search Bar */}
        <div className="relative mb-3">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('archival.searchPlaceholder')}
            className="w-full pl-3 pr-10 py-2 border-3 border-brutal-black rounded-none focus:outline-none focus:ring-4 focus:ring-brutal-black text-sm font-sans transition-all bg-white dark:bg-zinc-700 text-brutal-black dark:text-white placeholder:text-neutral-400"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 w-6 h-6 border-2 border-brutal-black bg-white dark:bg-zinc-600 dark:text-white hover:bg-brutal-black hover:text-white flex items-center justify-center font-bold transition-colors"
            >
              ×
            </button>
          )}
        </div>

        {searchQuery !== debouncedQuery && (
          <div className="flex items-center gap-2 text-xs text-neutral-500">
            <div className="w-3 h-3 border-2 border-brutal-black border-t-transparent animate-spin rounded-full"></div>
            <span>{t('archival.searching')}</span>
          </div>
        )}

        {/* Filters Panel */}
        {showFilters && (
          <div className="mt-3 pt-3 border-t-2 border-brutal-black space-y-3 animate-brutal-slide">
            {/* Sort By */}
            <div className="flex items-center gap-3">
              <label className="w-24 shrink-0 text-[10px] font-bold uppercase text-neutral-600 dark:text-neutral-400">
                {t('archival.sortBy')}
              </label>
              <BrutalSelect
                value={sortBy}
                onChange={(value) => setSortBy(value as SortOption)}
                className="flex-1"
                buttonClassName="py-1.5 text-xs"
                options={[
                  { value: 'date-desc', label: t('archival.sort.newestFirst') },
                  { value: 'date-asc', label: t('archival.sort.oldestFirst') },
                  { value: 'importance-desc', label: t('archival.sort.highToLow') },
                  { value: 'importance-asc', label: t('archival.sort.lowToHigh') },
                  { value: 'access-desc', label: t('archival.sort.mostAccessed') },
                  {
                    value: 'relevance',
                    label: t('archival.sort.mostRelevant'),
                    // Similarity only comes back from a search response.
                    disabled: !debouncedQuery,
                    hint: !debouncedQuery ? t('archival.sort.relevanceNeedsQuery') : undefined,
                  },
                ]}
              />
            </div>

            {/* Importance Filter */}
            <div className="flex items-center gap-3">
              <label className="w-24 shrink-0 text-[10px] font-bold uppercase text-neutral-600 dark:text-neutral-400">
                {t('archival.importanceLevel')}
              </label>
              <div className="flex flex-1 flex-wrap gap-2">
                {[
                  { value: 'all', label: t('archival.importance.all') },
                  { value: 'high', label: t('archival.importance.highRange') },
                  { value: 'medium', label: t('archival.importance.mediumRange') },
                  { value: 'low', label: t('archival.importance.lowRange') },
                ].map((option) => (
                  <BrutalButton
                    key={option.value}
                    onClick={() => setImportanceFilter(option.value as ImportanceFilter)}
                    size="xs"
                    isActive={importanceFilter === option.value}
                  >
                    {option.label}
                  </BrutalButton>
                ))}
              </div>
            </div>

            {/* Clear Filters */}
            {activeFiltersCount > 0 && (
              <BrutalButton
                onClick={() => {
                  setImportanceFilter('all');
                  setSortBy('date-desc');
                }}
                size="xs"
                className="w-full"
              >
                {t('archival.clearFilters')}
              </BrutalButton>
            )}
          </div>
        )}
      </div>

      {/* Results Count */}
      {processedMemories.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-neutral-600 dark:text-neutral-400 px-1">
          <span>
            {archivalTotal === null
              ? t('archival.showingCount', { count: String(processedMemories.length) })
              : t('archival.showingOfTotal', {
                  count: String(processedMemories.length),
                  total: String(archivalTotal),
                })}
            {importanceFilter !== 'all' && ` (${t('archival.filteredBy', { importance: importanceFilter })})`}
          </span>
          {/* Only a relevance search still sorts over the loaded pages. */}
          {archivalHasMore && debouncedQuery && sortBy !== 'relevance' && (
            <span className="font-mono text-[10px] text-neutral-500 dark:text-neutral-500">
              {t('archival.loadedOnlyNote')}
            </span>
          )}
        </div>
      )}

      {/* Error State */}
      {archivalError && (
        <div className="border-3 border-brutal-black bg-white dark:bg-zinc-800 p-6 animate-brutal-shake">
          <div className="flex items-start gap-3">
            <span className="text-3xl">⚠️</span>
            <div>
              <p className="font-bold text-brutal-black dark:text-white mb-1">{t('archival.errorTitle')}</p>
              <p className="text-sm text-brutal-black dark:text-neutral-300">{archivalError}</p>
            </div>
          </div>
        </div>
      )}

      {/* Empty State */}
      {processedMemories.length === 0 && !archivalLoading && (
        <div className="border-3 border-brutal-black bg-white dark:bg-zinc-800 p-12 text-center">
          <h4 className="font-brutal text-2xl uppercase mb-2 dark:text-white">
            {debouncedQuery || importanceFilter !== 'all'
              ? t('archival.empty.noMatchesTitle')
              : t('archival.empty.noMemoriesTitle')}
          </h4>
          <p className="text-neutral-600 dark:text-neutral-400 text-sm max-w-md mx-auto">
            {debouncedQuery
              ? t('archival.empty.noMatchesDesc')
              : importanceFilter !== 'all'
                ? t('archival.empty.noImportanceDesc', { importance: importanceFilter })
                : t('archival.empty.noMemoriesDesc')}
          </p>
          {(debouncedQuery || importanceFilter !== 'all') && (
            <button
              onClick={() => {
                setSearchQuery('');
                setImportanceFilter('all');
              }}
              className="mt-4 px-4 py-2 border-2 border-brutal-black bg-white dark:bg-zinc-700 dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-600 font-bold text-xs uppercase shadow-brutal-sm"
            >
              {t('archival.clearAllFilters')}
            </button>
          )}
        </div>
      )}

      {/* Memory Cards */}
      {isDateOrdered ? (
        <div className="space-y-6">
          {groupedMemories.map((group) => (
            <section key={group.key} className="space-y-2">
              <div className="sticky top-0 z-10 -mx-1 flex items-baseline gap-2 bg-neutral-100/95 px-1 py-1 backdrop-blur dark:bg-zinc-900/95">
                <h4 className="font-brutal text-sm uppercase tracking-tight text-brutal-black dark:text-white">
                  {group.label}
                </h4>
                <span className="h-px flex-1 bg-brutal-black/20 dark:bg-white/20" />
                <span className="font-mono text-[10px] text-neutral-500 dark:text-neutral-400">
                  {group.memories.length}
                </span>
              </div>
              <div className={isCompact ? 'space-y-2' : 'space-y-3'}>
                {group.memories.map((memory) => (
                  <MemoryCard
                    key={memory.id}
                    memory={memory}
                    onDelete={deleteArchivalMemory}
                    searchQuery={debouncedQuery}
                    compact={isCompact}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      ) : (
        <div className={isCompact ? 'space-y-2' : 'space-y-3'}>
          {processedMemories.map((memory) => (
            <MemoryCard
              key={memory.id}
              memory={memory}
              onDelete={deleteArchivalMemory}
              searchQuery={debouncedQuery}
              compact={isCompact}
            />
          ))}
        </div>
      )}

      {/* Loading State */}
      {archivalLoading && (
        <div className="border-3 border-brutal-black bg-white dark:bg-zinc-800 p-8 text-center">
          <div className="flex items-center justify-center gap-3 mb-2">
            <div className="w-4 h-4 border-3 border-brutal-black dark:border-white border-t-transparent animate-spin rounded-full"></div>
            <p className="text-neutral-800 dark:text-white font-bold uppercase">{t('archival.loading')}</p>
          </div>
        </div>
      )}

      {/* Load More Button */}
      {archivalHasMore && !archivalLoading && archivalMemories.length > 0 && (
        <BrutalButton onClick={handleLoadMore} className="w-full py-3">
          {t('archival.loadMore')}
        </BrutalButton>
      )}
    </div>
  );
};
