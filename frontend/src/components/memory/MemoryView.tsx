/**
 * Main Memory View Component
 * Displays core memory blocks and archival memories with enhanced stats
 */

import React, { useEffect, useState } from 'react';
import { useMemory } from '../../hooks/useMemory';
import { CoreMemoryBlock } from './CoreMemoryBlock';
import { ArchivalMemoryList } from './ArchivalMemoryList';
import { MemoryStatsComponent } from './MemoryStats';
import type { CoreMemoryLabel } from '../../types/memory';

export const MemoryView: React.FC = () => {
  const {
    coreMemory,
    coreMemoryLoading,
    coreMemoryError,
    stats,
    statsLoading,
    loadCoreMemory,
    updateCoreMemoryBlock,
    loadStats,
  } = useMemory();

  const [showCoreMemory, setShowCoreMemory] = useState(true);

  useEffect(() => {
    loadCoreMemory(); // No chatId - loads user-level blocks for Memory tab view
    loadStats();
  }, []);

  if (coreMemoryLoading && !coreMemory) {
    return (
      <div className="p-6 space-y-4">
        <div className="border-3 border-brutal-black bg-white p-8 text-center">
          <div className="flex items-center justify-center gap-3 mb-2">
            <div className="w-4 h-4 border-3 border-brutal-black border-t-transparent animate-spin rounded-full"></div>
            <p className="text-neutral-800 font-bold uppercase">Loading memory system...</p>
          </div>
        </div>
      </div>
    );
  }

  if (coreMemoryError) {
    return (
      <div className="p-6 space-y-4">
        <div className="border-3 border-brutal-red bg-white p-6 animate-brutal-shake">
          <div className="flex items-start gap-3">
            <span className="text-3xl">⚠️</span>
            <div className="flex-1">
              <h3 className="font-brutal text-lg text-brutal-red mb-2">Error Loading Memory</h3>
              <p className="text-brutal-black">{coreMemoryError}</p>
              <button
                onClick={() => loadCoreMemory()}
                className="mt-4 px-4 py-2 border-2 border-brutal-black bg-white hover:bg-neutral-100 font-bold uppercase shadow-brutal-sm active:translate-x-[1px] active:translate-y-[1px] active:shadow-none transition-all"
              >
                🔄 Retry
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full w-full overflow-y-auto scrollbar-thin scrollbar-offset-top memory-scroll px-6 pb-6 space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between animate-brutal-drop">
        <div>
          <h2 className="font-brutal text-3xl uppercase tracking-tight text-brutal-black">
            Memory System
          </h2>
          <p className="text-sm text-neutral-600 mt-1">
            Manage your AI's long-term memory and knowledge base
          </p>
        </div>
        <button
          onClick={() => {
            loadStats();
            loadCoreMemory();
          }}
          className="px-3 py-2 border-2 border-brutal-black bg-white hover:bg-neutral-100 font-bold text-xs uppercase shadow-brutal-sm active:translate-x-[1px] active:translate-y-[1px] active:shadow-none transition-all"
          title="Refresh memory data"
        >
          Refresh
        </button>
      </div>

      {/* Stats Dashboard */}
      <MemoryStatsComponent stats={stats} isLoading={statsLoading} />

      {/* Core Memory Section */}
      <div className="animate-brutal-drop" style={{ animationDelay: '0.1s' }}>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="font-brutal text-xl uppercase tracking-tight text-brutal-black">
              Core Memory
            </h3>
            <p className="text-xs text-neutral-600 mt-1">
              Always-visible working memory blocks
            </p>
          </div>
          <button
            onClick={() => setShowCoreMemory(!showCoreMemory)}
            className="px-3 py-1 border-2 border-brutal-black bg-white hover:bg-neutral-100 font-bold text-xs uppercase shadow-brutal-sm active:translate-x-[1px] active:translate-y-[1px] active:shadow-none transition-all"
          >
            {showCoreMemory ? '▲ Collapse' : '▼ Expand'}
          </button>
        </div>

        {showCoreMemory && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {coreMemory &&
              (Object.keys(coreMemory) as CoreMemoryLabel[]).map((label, idx) => (
                <div
                  key={label}
                  className="animate-brutal-drop"
                  style={{ animationDelay: `${0.05 * idx}s` }}
                >
                  <CoreMemoryBlock
                    label={label}
                    content={coreMemory[label]}
                    onUpdate={updateCoreMemoryBlock}
                  />
                </div>
              ))}
          </div>
        )}
      </div>

      {/* Archival Memory Section */}
      <div className="animate-brutal-drop" style={{ animationDelay: '0.15s' }}>
        <ArchivalMemoryList />
      </div>
    </div>
  );
};
