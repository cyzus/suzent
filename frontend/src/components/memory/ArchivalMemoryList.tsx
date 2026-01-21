/**
 * Archival Memory List Component
 * Displays list of archival memories with search, filtering, and sorting
 */

import React, { useState, useEffect, useMemo } from 'react';
import { useMemory } from '../../hooks/useMemory';
import { MemoryCard } from './MemoryCard';
import type { ArchivalMemory } from '../../types/memory';

type SortOption = 'date-desc' | 'date-asc' | 'importance-desc' | 'importance-asc' | 'relevance' | 'access-desc';
type ImportanceFilter = 'all' | 'high' | 'medium' | 'low';

export const ArchivalMemoryList: React.FC = () => {
  const {
    archivalMemories,
    archivalLoading,
    archivalError,
    archivalHasMore,
    archivalQuery,
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

  // Load memories when debounced query changes
  useEffect(() => {
    loadArchivalMemories(debouncedQuery, false);
  }, [debouncedQuery]);

  // Initial load
  useEffect(() => {
    if (archivalMemories.length === 0 && !archivalLoading) {
      loadArchivalMemories('', false);
    }
  }, []);

  const handleLoadMore = () => {
    loadArchivalMemories(debouncedQuery, true);
  };

  // Filter and sort memories
  const processedMemories = useMemo(() => {
    let filtered = [...archivalMemories];

    // Apply importance filter
    if (importanceFilter !== 'all') {
      filtered = filtered.filter(m => {
        if (importanceFilter === 'high') return m.importance >= 0.8;
        if (importanceFilter === 'medium') return m.importance >= 0.5 && m.importance < 0.8;
        if (importanceFilter === 'low') return m.importance < 0.5;
        return true;
      });
    }

    // Apply sorting
    filtered.sort((a, b) => {
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
        case 'relevance':
          if (a.similarity !== undefined && b.similarity !== undefined) {
            return b.similarity - a.similarity;
          }
          return 0;
        default:
          return 0;
      }
    });

    return filtered;
  }, [archivalMemories, importanceFilter, sortBy]);

  const activeFiltersCount = (importanceFilter !== 'all' ? 1 : 0);

  return (
    <div className="space-y-4">
      {/* Search and Filters Header */}
      <div className="border-3 border-brutal-black bg-white shadow-brutal p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-brutal text-lg uppercase tracking-tight text-brutal-black">
            Archival Memory
          </h3>
          <div className="flex gap-2">
            <button
              onClick={() => setIsCompact(!isCompact)}
              className={`px-3 py-1 border-2 border-brutal-black font-bold text-xs uppercase transition-all shadow-[2px_2px_0_0_#000000] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none ${isCompact ? 'bg-brutal-black text-white' : 'bg-white hover:bg-neutral-100'
                }`}
              title={isCompact ? "Switch to Card View" : "Switch to Compact View"}
            >
              {isCompact ? '☰ List' : '☷ Cards'}
            </button>
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`px-3 py-1 border-2 border-brutal-black font-bold text-xs uppercase transition-all shadow-[2px_2px_0_0_#000000] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none ${showFilters ? 'bg-brutal-black text-white' : 'bg-white hover:bg-neutral-100'
                }`}
            >
              {showFilters ? '▲' : '▼'} Filters {activeFiltersCount > 0 && `(${activeFiltersCount})`}
            </button>
          </div>
        </div>

        {/* Search Bar */}
        <div className="relative mb-3">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search memories... (try adding keywords)"
            className="w-full pl-3 pr-10 py-2 border-3 border-brutal-black rounded-none focus:outline-none focus:ring-4 focus:ring-brutal-black text-sm font-sans transition-all"
            style={{ backgroundColor: '#ffffff', color: '#000000' }}
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 w-6 h-6 border-2 border-brutal-black bg-white hover:bg-brutal-black hover:text-white flex items-center justify-center font-bold transition-colors"
            >
              ×
            </button>
          )}
        </div>

        {searchQuery !== debouncedQuery && (
          <div className="flex items-center gap-2 text-xs text-neutral-500">
            <div className="w-3 h-3 border-2 border-brutal-black border-t-transparent animate-spin rounded-full"></div>
            <span>Searching...</span>
          </div>
        )}

        {/* Filters Panel */}
        {showFilters && (
          <div className="mt-4 pt-4 border-t-3 border-brutal-black space-y-3 animate-brutal-slide">
            {/* Sort By */}
            <div>
              <label className="block text-xs font-bold uppercase text-neutral-600 mb-2">
                Sort By
              </label>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {[
                  { value: 'date-desc', label: 'Newest First' },
                  { value: 'date-asc', label: 'Oldest First' },
                  { value: 'importance-desc', label: 'High → Low' },
                  { value: 'importance-asc', label: 'Low → High' },
                  { value: 'access-desc', label: 'Most Accessed' },
                  { value: 'relevance', label: 'Most Relevant' },
                ].map((option) => (
                  <button
                    key={option.value}
                    onClick={() => setSortBy(option.value as SortOption)}
                    className={`px-3 py-2 border-2 border-brutal-black text-xs font-bold uppercase transition-all ${sortBy === option.value
                      ? 'bg-brutal-black text-white'
                      : 'bg-white hover:bg-neutral-100'
                      }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Importance Filter */}
            <div>
              <label className="block text-xs font-bold uppercase text-neutral-600 mb-2">
                Importance Level
              </label>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {[
                  { value: 'all', label: 'All' },
                  { value: 'high', label: 'High (≥0.8)' },
                  { value: 'medium', label: 'Medium (0.5-0.8)' },
                  { value: 'low', label: 'Low (<0.5)' },
                ].map((option) => (
                  <button
                    key={option.value}
                    onClick={() => setImportanceFilter(option.value as ImportanceFilter)}
                    className={`px-3 py-2 border-2 border-brutal-black text-xs font-bold uppercase transition-all ${importanceFilter === option.value
                      ? 'bg-brutal-black text-white'
                      : 'bg-white hover:bg-neutral-100'
                      }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Clear Filters */}
            {activeFiltersCount > 0 && (
              <button
                onClick={() => {
                  setImportanceFilter('all');
                  setSortBy('date-desc');
                }}
                className="w-full py-2 border-2 border-brutal-black bg-white hover:bg-neutral-100 font-bold text-xs uppercase transition-all"
              >
                Clear Filters
              </button>
            )}
          </div>
        )}
      </div>

      {/* Results Count */}
      {processedMemories.length > 0 && (
        <div className="flex items-center justify-between text-xs text-neutral-600 px-1">
          <span>
            Showing <span className="font-bold text-brutal-black">{processedMemories.length}</span> {processedMemories.length === 1 ? 'memory' : 'memories'}
            {importanceFilter !== 'all' && ` (filtered by ${importanceFilter} importance)`}
          </span>
        </div>
      )}

      {/* Error State */}
      {archivalError && (
        <div className="border-3 border-brutal-black bg-white p-6 animate-brutal-shake">
          <div className="flex items-start gap-3">
            <span className="text-3xl">⚠️</span>
            <div>
              <p className="font-bold text-brutal-black mb-1">Error Loading Memories</p>
              <p className="text-sm text-brutal-black">{archivalError}</p>
            </div>
          </div>
        </div>
      )}

      {/* Empty State */}
      {processedMemories.length === 0 && !archivalLoading && (
        <div className="border-3 border-brutal-black bg-white p-12 text-center">
          <h4 className="font-brutal text-2xl uppercase mb-2">
            {debouncedQuery || importanceFilter !== 'all'
              ? 'No Matches Found'
              : 'No Memories Yet'}
          </h4>
          <p className="text-neutral-600 text-sm max-w-md mx-auto">
            {debouncedQuery
              ? 'Try different search terms or adjust your filters'
              : importanceFilter !== 'all'
                ? `No ${importanceFilter} importance memories found. Try changing the filter.`
                : 'Start a conversation and important facts will be automatically saved here'}
          </p>
          {(debouncedQuery || importanceFilter !== 'all') && (
            <button
              onClick={() => {
                setSearchQuery('');
                setImportanceFilter('all');
              }}
              className="mt-4 px-4 py-2 border-2 border-brutal-black bg-white hover:bg-neutral-100 font-bold text-xs uppercase shadow-brutal-sm"
            >
              Clear All Filters
            </button>
          )}
        </div>
      )}

      {/* Memory Cards */}
      <div className={isCompact ? "space-y-2" : "space-y-3"}>
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

      {/* Loading State */}
      {archivalLoading && (
        <div className="border-3 border-brutal-black bg-white p-8 text-center">
          <div className="flex items-center justify-center gap-3 mb-2">
            <div className="w-4 h-4 border-3 border-brutal-black border-t-transparent animate-spin rounded-full"></div>
            <p className="text-neutral-800 font-bold uppercase">Loading memories...</p>
          </div>
          <div className="flex gap-1 justify-center mt-3">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="w-2 h-2 bg-brutal-black animate-brutal-blink"
                style={{ animationDelay: `${i * 0.15}s` }}
              ></div>
            ))}
          </div>
        </div>
      )}

      {/* Load More Button */}
      {archivalHasMore && !archivalLoading && archivalMemories.length > 0 && (
        <button
          onClick={handleLoadMore}
          className="w-full py-3 border-3 border-brutal-black bg-white hover:bg-neutral-100 active:translate-x-[2px] active:translate-y-[2px] active:shadow-none shadow-brutal font-bold uppercase transition-all"
        >
          Load More
        </button>
      )}
    </div>
  );
};
