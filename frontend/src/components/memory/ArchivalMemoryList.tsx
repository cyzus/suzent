/**
 * Archival Memory List Component
 * Displays list of archival memories with search and pagination
 */

import React, { useState, useEffect } from 'react';
import { useMemory } from '../../hooks/useMemory';
import { MemoryCard } from './MemoryCard';

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

  return (
    <div className="space-y-4">
      <div className="border-3 border-brutal-black bg-white shadow-[4px_4px_0_0_#000000] rounded-none p-4">
        <h3 className="font-brutal text-lg uppercase tracking-tight text-brutal-black mb-3">
          Archival Memory
        </h3>

        <div className="relative">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search memories..."
            className="w-full px-3 py-2 border-3 border-brutal-black rounded-none focus:outline-none focus:ring-4 focus:ring-brutal-black text-sm font-sans"
            style={{ backgroundColor: '#ffffff', color: '#000000' }}
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 w-6 h-6 border-2 border-brutal-black bg-white hover:bg-neutral-100 flex items-center justify-center font-bold"
            >
              ×
            </button>
          )}
        </div>

        {searchQuery !== debouncedQuery && (
          <p className="text-xs text-neutral-500 mt-2">Searching...</p>
        )}
      </div>

      {archivalError && (
        <div className="border-3 border-red-500 bg-red-50 p-4 text-red-700">
          <p className="font-bold">Error loading memories</p>
          <p className="text-sm mt-1">{archivalError}</p>
        </div>
      )}

      {archivalMemories.length === 0 && !archivalLoading && (
        <div className="border-3 border-brutal-black bg-neutral-50 p-8 text-center">
          <p className="text-neutral-600">
            {debouncedQuery
              ? 'No memories found matching your search'
              : 'No memories stored yet'}
          </p>
        </div>
      )}

      <div className="space-y-3">
        {archivalMemories.map((memory) => (
          <MemoryCard
            key={memory.id}
            memory={memory}
            onDelete={deleteArchivalMemory}
          />
        ))}
      </div>

      {archivalLoading && (
        <div className="border-3 border-brutal-black bg-neutral-50 p-4 text-center">
          <p className="text-neutral-600 font-bold animate-pulse">Loading memories...</p>
        </div>
      )}

      {archivalHasMore && !archivalLoading && archivalMemories.length > 0 && (
        <button
          onClick={handleLoadMore}
          className="w-full py-3 border-3 border-brutal-black bg-white hover:bg-neutral-100 active:translate-y-[2px] active:shadow-none shadow-[4px_4px_0_0_#000000] font-bold uppercase transition-all"
        >
          Load More
        </button>
      )}
    </div>
  );
};
