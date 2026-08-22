/**
 * Main Memory View Component
 * Displays core memory blocks, archival memories, daily logs, MEMORY.md, and transcripts
 */

import { useEffect, useState, useRef } from 'react';
import { useI18n } from '../../i18n';
import { useMemory } from '../../hooks/useMemory';
import { useChatStreamingStore } from '../../hooks/useChatStore';
import { CoreMemoryBlock } from './CoreMemoryBlock';
import { ArchivalMemoryList } from './ArchivalMemoryList';
import { MemoryStatsComponent } from './MemoryStats';
import { DailyLogsPanel } from './DailyLogsPanel';
import { TranscriptPanel } from './TranscriptPanel';
import { DreamingPanel } from './DreamingPanel';
import { BrutalSegmentedTabs } from '../BrutalSegmentedTabs';
import { BrutalButton } from '../BrutalButton';
import { ChevronDownIcon } from '@heroicons/react/24/outline';
import type { CoreMemoryLabel } from '../../types/memory';

// MEMORY.md is shown in Overview as the editable 'facts' core-memory block, so it
// has no standalone tab here.
type MemoryTab = 'overview' | 'dreaming' | 'daily-logs' | 'transcripts';

const TABS: { id: MemoryTab; labelKey: string }[] = [
  { id: 'overview', labelKey: 'memoryView.tabs.overview' },
  { id: 'dreaming', labelKey: 'memoryView.tabs.dreaming' },
  { id: 'daily-logs', labelKey: 'memoryView.tabs.dailyLogs' },
  { id: 'transcripts', labelKey: 'memoryView.tabs.transcripts' },
];

export const MemoryView: React.FC<{ initialTab?: MemoryTab }> = ({ initialTab }) => {
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
  const { isStreaming } = useChatStreamingStore();
  const prevStreamingRef = useRef(isStreaming);

  const [activeTab, setActiveTab] = useState<MemoryTab>(initialTab ?? 'overview');
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

  if (coreMemoryError && activeTab === 'overview') {
    return (
      <div className="p-6 space-y-4">
        <div className="border-3 border-brutal-red bg-white dark:bg-zinc-800 p-6 animate-brutal-shake shadow-brutal">
          <div className="flex items-start gap-4">
            <span className="text-4xl">&#9888;&#65039;</span>
            <div className="flex-1">
              <h3 className="font-brutal text-xl text-brutal-red mb-2 uppercase">{t('memoryView.systemError')}</h3>
              <p className="text-brutal-black dark:text-white font-mono text-sm mb-4">{coreMemoryError}</p>
              <button
                onClick={() => loadCoreMemory()}
                className="px-6 py-2 border-3 border-brutal-black bg-white dark:bg-zinc-700 hover:bg-neutral-100 dark:hover:bg-zinc-600 font-bold uppercase shadow-[2px_2px_0_0_#000] brutal-btn transition-all"
              >
                {t('memoryView.retryConnection')}
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
      <BrutalSegmentedTabs
        tabs={TABS.map((tab) => ({ id: tab.id, label: t(tab.labelKey) }))}
        value={activeTab}
        onChange={setActiveTab}
        containerClassName="border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]"
        tabClassName="flex-1 px-4 py-2.5 font-bold text-xs md:text-sm"
      />

      {/* Tab content */}
      {activeTab === 'overview' && (
        <div className="space-y-6 animate-view-fade">
          {/* Stats Dashboard */}
          <section>
            <MemoryStatsComponent
              stats={stats}
              isLoading={statsLoading}
              onRefresh={() => {
                loadStats();
                loadCoreMemory();
              }}
            />
          </section>

          <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
            {/* Core Memory Section */}
            <div className="xl:col-span-5 space-y-4">
              <div className="flex items-center justify-between gap-3 bg-white dark:bg-zinc-800 text-brutal-black dark:text-white px-3 py-2 border-2 border-brutal-black shadow-brutal-sm">
                <div className="min-w-0">
                  <h3 className="font-brutal text-base uppercase tracking-tight leading-none">
                    {t('memoryView.coreMemoryTitle')}
                  </h3>
                  <p className="text-[11px] text-neutral-600 dark:text-neutral-400 font-mono truncate">
                    {t('memoryView.coreMemoryDesc')}
                  </p>
                </div>
                <BrutalButton
                  onClick={() => setShowCoreMemory(!showCoreMemory)}
                  size="icon"
                  aria-expanded={showCoreMemory}
                  title={showCoreMemory ? t('memoryView.collapseSection') : t('memoryView.expandSection')}
                  aria-label={showCoreMemory ? t('memoryView.collapseSection') : t('memoryView.expandSection')}
                >
                  <ChevronDownIcon className={`h-4 w-4 stroke-2 transition-transform ${showCoreMemory ? '' : '-rotate-90'}`} />
                </BrutalButton>
              </div>

              {showCoreMemory && (
                <div className="space-y-4">
                  {coreMemoryLoading && !coreMemory ? (
                    [1, 2].map((i) => (
                      <div key={i} className="border-3 border-brutal-black bg-white dark:bg-zinc-800 p-4 animate-brutal-blink">
                        <div className="h-3 bg-neutral-200 dark:bg-zinc-700 mb-3 w-1/3"></div>
                        <div className="h-16 bg-neutral-200 dark:bg-zinc-700"></div>
                      </div>
                    ))
                  ) : (
                    coreMemory &&
                    // Filter out session-scoped 'context' from the global view —
                    // it only makes sense inside an active chat session.
                    (Object.keys(coreMemory) as CoreMemoryLabel[])
                      .filter((label) => label !== 'context')
                      .map((label) => (
                        <div key={label}>
                          <CoreMemoryBlock
                            label={label}
                            content={coreMemory[label]}
                            onUpdate={updateCoreMemoryBlock}
                          />
                        </div>
                      ))
                  )}
                </div>
              )}
            </div>

            {/* Archival Memory Section — its own header lives inside the list. */}
            <div className="xl:col-span-7">
              <ArchivalMemoryList />
            </div>
          </div>
        </div>
      )}

      {activeTab === 'dreaming' && (
        <div className="animate-view-fade">
          <DreamingPanel />
        </div>
      )}

      {activeTab === 'daily-logs' && (
        <div className="animate-view-fade">
          <DailyLogsPanel />
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
