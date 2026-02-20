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
import { useI18n } from '../../i18n';

export const MemoryView: React.FC = () => {
  const { t } = useI18n();
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
              {t('memoryView.initializing')}
            </h2>
            <div className="space-y-2 font-mono text-xs text-brutal-black">
              <div className="flex justify-between">
                <span>{'>'} {t('memoryView.connectingToCore')}</span>
                <span>{`[${t('common.ok')}]`}</span>
              </div>
              <div className="flex justify-between">
                <span>{'>'} {t('memoryView.loadingVectors')}</span>
                <span className="animate-pulse">...</span>
              </div>
              <div className="flex justify-between opacity-50">
                <span>{'>'} {t('memoryView.indexingArchives')}</span>
                <span>{t('memoryView.waiting')}</span>
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
              <h3 className="font-brutal text-xl text-brutal-red mb-2 uppercase">{t('memoryView.systemError')}</h3>
              <p className="text-brutal-black font-mono text-sm mb-4">{coreMemoryError}</p>
              <button
                onClick={() => loadCoreMemory()}
                className="px-6 py-2 border-3 border-brutal-black bg-white hover:bg-neutral-100 font-bold uppercase shadow-[2px_2px_0_0_#000] brutal-btn transition-all"
              >
                🔄 {t('memoryView.retryConnection')}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full w-full overflow-y-auto scrollbar-thin memory-scroll px-4 md:px-8 py-8 space-y-8 max-w-7xl mx-auto">
      {/* Stats Dashboard */}
      <section>
        <MemoryStatsComponent stats={stats} isLoading={statsLoading} />
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-8">
        {/* Core Memory Section - Takes 4 columns on large screens */}
        <div className="xl:col-span-5 space-y-4">
          <div className="flex items-center justify-between bg-brutal-black text-white p-3 border-3 border-brutal-black">
            <div>
              <h3 className="font-brutal text-xl uppercase tracking-tight">
                {t('memoryView.coreMemoryTitle')}
              </h3>
              <p className="text-xs text-neutral-300 font-mono">
                {t('memoryView.coreMemoryDesc')}
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
                (Object.keys(coreMemory) as CoreMemoryLabel[]).map((label) => (
                  <div key={label}>
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
        <div className="xl:col-span-7 space-y-4">
          <div className="bg-white p-1 border-b-3 border-brutal-black mb-2">
            <h3 className="font-brutal text-xl uppercase tracking-tight text-brutal-black">
              {t('memoryView.archivalTitle')}
            </h3>
            <p className="text-xs text-neutral-600 font-mono">
              {t('memoryView.archivalDesc')}
            </p>
          </div>
          <ArchivalMemoryList />
        </div>
      </div>
    </div>
  );
};
