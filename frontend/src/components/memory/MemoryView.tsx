/**
 * Main Memory View Component
 * Displays core memory blocks and archival memories with enhanced stats
 */

import React, { useEffect, useState, useRef } from 'react';
import { useMemory } from '../../hooks/useMemory';
import { useChatStore } from '../../hooks/useChatStore';
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
  const { isStreaming } = useChatStore();
  const prevStreamingRef = useRef(isStreaming);

  const [showCoreMemory, setShowCoreMemory] = useState(true);

  useEffect(() => {
    loadCoreMemory(); // No chatId - loads user-level blocks for Memory tab view
    loadStats();
  }, []);

  // Auto-refresh when agent finishes streaming
  useEffect(() => {
    if (prevStreamingRef.current && !isStreaming) {
      loadCoreMemory();
      loadStats();
    }
    prevStreamingRef.current = isStreaming;
  }, [isStreaming]);

  if (coreMemoryLoading && !coreMemory) {
    return (
      <div className="h-full w-full flex flex-col items-center justify-center p-8">
        <div className="max-w-md w-full space-y-4">
          <div className="border-3 border-brutal-black bg-white p-6 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
            <h2 className="font-brutal text-2xl uppercase mb-4 animate-pulse">
              Initializing Memory System...
            </h2>
            <div className="space-y-2 font-mono text-xs text-brutal-black">
              <div className="flex justify-between">
                <span>{'>'} CONNECTING_TO_CORE</span>
                <span>[OK]</span>
              </div>
              <div className="flex justify-between">
                <span>{'>'} LOADING_VECTORS</span>
                <span className="animate-pulse">...</span>
              </div>
              <div className="flex justify-between opacity-50">
                <span>{'>'} INDEXING_ARCHIVES</span>
                <span>WAITING</span>
              </div>
            </div>
            <div className="mt-6 h-4 border-2 border-brutal-black p-0.5">
              <div className="h-full bg-brutal-black w-2/3 animate-[shimmer_2s_infinite]"></div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (coreMemoryError) {
    return (
      <div className="p-6 space-y-4">
        <div className="border-3 border-brutal-red bg-white p-6 animate-brutal-shake shadow-brutal">
          <div className="flex items-start gap-4">
            <span className="text-4xl">⚠️</span>
            <div className="flex-1">
              <h3 className="font-brutal text-xl text-brutal-red mb-2 uppercase">System Error</h3>
              <p className="text-brutal-black font-mono text-sm mb-4">{coreMemoryError}</p>
              <button
                onClick={() => loadCoreMemory()}
                className="px-6 py-2 border-3 border-brutal-black bg-white hover:bg-neutral-100 font-bold uppercase shadow-brutal active:translate-x-[1px] active:translate-y-[1px] active:shadow-none transition-all"
              >
                🔄 Retry Connection
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full w-full overflow-y-auto scrollbar-thin scrollbar-offset-top memory-scroll px-4 md:px-8 pb-8 space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 animate-brutal-drop border-b-3 border-brutal-black pb-6">
        <div>
          <h2 className="font-brutal text-4xl uppercase tracking-tight text-brutal-black mb-2">
            Memory System
          </h2>
          <p className="text-neutral-600 font-mono text-sm">
            // LONG_TERM_STORAGE_ACCESS_TERMINAL
          </p>
        </div>
        {/* Auto-refresh indicator instead of manual button */}
        <div className="flex items-center gap-2 text-xs font-mono text-neutral-400">
          <div className={`w-2 h-2 rounded-full ${isStreaming ? 'bg-brutal-yellow animate-pulse' : 'bg-brutal-green'}`}></div>
          <span>{isStreaming ? 'SYNCING...' : 'SYSTEM_READY'}</span>
        </div>
      </div>

      {/* Stats Dashboard */}
      <section>
        <MemoryStatsComponent stats={stats} isLoading={statsLoading} />
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-8">
        {/* Core Memory Section - Takes 4 columns on large screens */}
        <div className="xl:col-span-5 space-y-4 animate-brutal-drop" style={{ animationDelay: '0.1s' }}>
          <div className="flex items-center justify-between bg-brutal-black text-white p-3 border-3 border-brutal-black">
            <div>
              <h3 className="font-brutal text-xl uppercase tracking-tight">
                Core Memory
              </h3>
              <p className="text-xs text-neutral-300 font-mono">
                READ_WRITE_ACCESS
              </p>
            </div>
            <button
              onClick={() => setShowCoreMemory(!showCoreMemory)}
              className="px-2 py-1 border-2 border-white bg-brutal-black hover:bg-white hover:text-brutal-black font-bold text-xs uppercase transition-all"
            >
              {showCoreMemory ? '−' : '+'}
            </button>
          </div>

          {showCoreMemory && (
            <div className="space-y-4">
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

        {/* Archival Memory Section - Takes 8 columns on large screens */}
        <div className="xl:col-span-7 space-y-4 animate-brutal-drop" style={{ animationDelay: '0.15s' }}>
          <div className="bg-white p-1 border-b-3 border-brutal-black mb-2">
             <h3 className="font-brutal text-xl uppercase tracking-tight text-brutal-black">
              Archival Database
            </h3>
            <p className="text-xs text-neutral-600 font-mono">
              READ_ONLY_SEARCH_INDEX
            </p>
          </div>
          <ArchivalMemoryList />
        </div>
      </div>
    </div>
  );
};
