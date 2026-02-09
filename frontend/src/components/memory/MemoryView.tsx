/**
 * Main Memory View Component
 * Displays core memory blocks, archival memories, daily logs, MEMORY.md, and transcripts
 */

import { useEffect, useState, useRef } from 'react';
import { useMemory } from '../../hooks/useMemory';
import { useChatStore } from '../../hooks/useChatStore';
import { CoreMemoryBlock } from './CoreMemoryBlock';
import { ArchivalMemoryList } from './ArchivalMemoryList';
import { MemoryStatsComponent } from './MemoryStats';
import { DailyLogsPanel } from './DailyLogsPanel';
import { MemoryFilePanel } from './MemoryFilePanel';
import { TranscriptPanel } from './TranscriptPanel';
import type { CoreMemoryLabel } from '../../types/memory';

type MemoryTab = 'overview' | 'daily-logs' | 'memory-file' | 'transcripts';

const TABS: { id: MemoryTab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'daily-logs', label: 'Daily Logs' },
  { id: 'memory-file', label: 'MEMORY.md' },
  { id: 'transcripts', label: 'Transcripts' },
];

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

  const [activeTab, setActiveTab] = useState<MemoryTab>('overview');
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

  if (coreMemoryLoading && !coreMemory && activeTab === 'overview') {
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

  if (coreMemoryError && activeTab === 'overview') {
    return (
      <div className="p-6 space-y-4">
        <div className="border-3 border-brutal-red bg-white p-6 animate-brutal-shake shadow-brutal">
          <div className="flex items-start gap-4">
            <span className="text-4xl">&#9888;&#65039;</span>
            <div className="flex-1">
              <h3 className="font-brutal text-xl text-brutal-red mb-2 uppercase">System Error</h3>
              <p className="text-brutal-black font-mono text-sm mb-4">{coreMemoryError}</p>
              <button
                onClick={() => loadCoreMemory()}
                className="px-6 py-2 border-3 border-brutal-black bg-white hover:bg-neutral-100 font-bold uppercase shadow-[2px_2px_0_0_#000] brutal-btn transition-all"
              >
                Retry Connection
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full w-full overflow-y-auto scrollbar-thin memory-scroll px-4 md:px-8 py-8 space-y-6 max-w-7xl mx-auto">
      {/* Sub-navigation tabs */}
      <div className="flex border-3 border-brutal-black bg-white shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`
              flex-1 px-4 py-2.5 font-bold uppercase text-xs md:text-sm transition-colors border-r-3 border-brutal-black last:border-r-0
              ${activeTab === tab.id ? 'bg-brutal-black text-white' : 'bg-white text-brutal-black hover:bg-neutral-100'}
            `}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'overview' && (
        <div className="space-y-8 animate-view-fade">
          {/* Stats Dashboard */}
          <section>
            <MemoryStatsComponent stats={stats} isLoading={statsLoading} />
          </section>

          <div className="grid grid-cols-1 xl:grid-cols-12 gap-8">
            {/* Core Memory Section */}
            <div className="xl:col-span-5 space-y-4">
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
                  {showCoreMemory ? '\u2212' : '+'}
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

            {/* Archival Memory Section */}
            <div className="xl:col-span-7 space-y-4">
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
      )}

      {activeTab === 'daily-logs' && (
        <div className="animate-view-fade">
          <DailyLogsPanel />
        </div>
      )}

      {activeTab === 'memory-file' && (
        <div className="animate-view-fade">
          <MemoryFilePanel />
        </div>
      )}

      {activeTab === 'transcripts' && (
        <div className="animate-view-fade">
          <TranscriptPanel />
        </div>
      )}
    </div>
  );
};
