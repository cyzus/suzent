/**
 * Main Memory View Component
 * Displays core memory blocks and archival memories
 */

import React, { useEffect } from 'react';
import { useMemory } from '../../hooks/useMemory';
import { CoreMemoryBlock } from './CoreMemoryBlock';
import { ArchivalMemoryList } from './ArchivalMemoryList';
import type { CoreMemoryLabel } from '../../types/memory';

export const MemoryView: React.FC = () => {
  const {
    coreMemory,
    coreMemoryLoading,
    coreMemoryError,
    stats,
    loadCoreMemory,
    updateCoreMemoryBlock,
    loadStats,
  } = useMemory();

  useEffect(() => {
    loadCoreMemory();
    loadStats();
  }, []);

  if (coreMemoryLoading && !coreMemory) {
    return (
      <div className="p-6 space-y-4">
        <div className="border-3 border-brutal-black bg-white p-8 text-center">
          <p className="text-neutral-600 font-bold animate-pulse">Loading memory system...</p>
        </div>
      </div>
    );
  }

  if (coreMemoryError) {
    return (
      <div className="p-6 space-y-4">
        <div className="border-3 border-red-500 bg-red-50 p-6">
          <h3 className="font-brutal text-lg text-red-700 mb-2">Error Loading Memory</h3>
          <p className="text-red-600">{coreMemoryError}</p>
          <button
            onClick={loadCoreMemory}
            className="mt-4 px-4 py-2 border-2 border-brutal-black bg-white hover:bg-neutral-100 font-bold uppercase"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6 max-w-6xl mx-auto">
      {/* Header with Stats */}
      <div className="flex items-center justify-between">
        <h2 className="font-brutal text-2xl uppercase tracking-tight text-brutal-black">
          Memory System
        </h2>
        {stats && (
          <div className="flex gap-4 text-sm">
            <div className="px-3 py-1 border-2 border-brutal-black bg-white">
              <span className="font-bold">Total:</span> {stats.total_memories}
            </div>
            <div className="px-3 py-1 border-2 border-brutal-black bg-white">
              <span className="font-bold">Avg Importance:</span>{' '}
              {stats.avg_importance.toFixed(2)}
            </div>
          </div>
        )}
      </div>

      {/* Core Memory Section */}
      <div>
        <h3 className="font-brutal text-xl uppercase tracking-tight text-brutal-black mb-4">
          Core Memory
        </h3>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {coreMemory &&
            (Object.keys(coreMemory) as CoreMemoryLabel[]).map((label) => (
              <CoreMemoryBlock
                key={label}
                label={label}
                content={coreMemory[label]}
                onUpdate={updateCoreMemoryBlock}
              />
            ))}
        </div>
      </div>

      {/* Archival Memory Section */}
      <div>
        <ArchivalMemoryList />
      </div>
    </div>
  );
};
