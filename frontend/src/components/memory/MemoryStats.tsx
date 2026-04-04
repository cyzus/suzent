/**
 * Memory Statistics Dashboard Component
 * Displays visual stats with neo-brutalist styling
 */

import React from 'react';
import { useI18n } from '../../i18n';
import type { MemoryStats } from '../../types/memory';

interface MemoryStatsProps {
  stats: MemoryStats | null;
  isLoading?: boolean;
}

export const MemoryStatsComponent: React.FC<MemoryStatsProps> = ({ stats, isLoading }) => {
  const { t } = useI18n();

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="border-3 border-brutal-black bg-white dark:bg-zinc-800 p-4 animate-brutal-blink"
          >
            <div className="h-4 bg-neutral-200 dark:bg-zinc-700 mb-2"></div>
            <div className="h-8 bg-neutral-200 dark:bg-zinc-700"></div>
          </div>
        ))}
      </div>
    );
  }

  if (!stats) return null;

  const toPercent = (value?: number) => `${((value || 0) * 100).toFixed(1)}%`;
  const accessDistribution = stats.access_distribution || {};
  const unaccessed = accessDistribution.unaccessed || 0;
  const light = accessDistribution.light || 0;
  const engaged = accessDistribution.engaged || 0;
  const total = unaccessed + light + engaged || 1;

  return (
    <div className="space-y-4">
      {/* Main Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Memories */}
        <div className="border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-[2px_2px_0_0_#000] p-4 brutal-btn transition-all">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold uppercase text-neutral-600 dark:text-neutral-400">{t('memoryStats.totalMemories')}</span>
          </div>
          <div className="font-brutal text-3xl text-brutal-black dark:text-white">{stats.total_memories}</div>
        </div>

        {/* Memory Utilization */}
        <div className="border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-[2px_2px_0_0_#000] p-4 brutal-btn transition-all">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold uppercase text-neutral-600 dark:text-neutral-400">{t('memoryStats.memoryUtilization')}</span>
          </div>
          <div className="font-brutal text-3xl text-brutal-black dark:text-white">
            {toPercent(stats.utilization_rate)}
          </div>
          <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
            {t('memoryStats.utilizedCount', {
              active: String(stats.utilized_memories || 0),
              total: String(stats.total_memories || 0),
            })}
          </div>
          <div className="mt-2 h-2 bg-white dark:bg-zinc-700 border-3 border-brutal-black">
            <div
              className="h-full bg-brutal-black transition-all duration-500"
              style={{ width: toPercent(stats.utilization_rate) }}
            />
          </div>
        </div>

        {/* 7d Activity */}
        <div className="border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-[2px_2px_0_0_#000] p-4 brutal-btn transition-all">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold uppercase text-neutral-600 dark:text-neutral-400">{t('memoryStats.activity7d')}</span>
          </div>
          <div className="font-brutal text-3xl text-brutal-black dark:text-white">
            {toPercent(stats.recent_activity_rate_7d)}
          </div>
          <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
            {t('memoryStats.recentCount', {
              recent: String(stats.recently_accessed_memories_7d || 0),
              total: String(stats.total_memories || 0),
            })}
          </div>
        </div>

        {/* Cold Memory Ratio */}
        <div className="border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-[2px_2px_0_0_#000] p-4 brutal-btn transition-all">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold uppercase text-neutral-600 dark:text-neutral-400">{t('memoryStats.coldMemoryRatio')}</span>
          </div>
          <div className="font-brutal text-3xl text-brutal-black dark:text-white">
            {toPercent(stats.cold_memory_ratio)}
          </div>
          <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
            {t('memoryStats.coldCount', {
              cold: String(stats.cold_memories || 0),
              total: String(stats.total_memories || 0),
            })}
          </div>
        </div>
      </div>

      {/* Access Distribution Bar */}
      {(unaccessed > 0 || light > 0 || engaged > 0) && (
        <div className="border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-brutal p-4">
          <h4 className="font-bold text-xs uppercase text-neutral-600 dark:text-neutral-400 mb-3">
            {t('memoryStats.accessDistribution')}
          </h4>
          <div className="flex h-8 border-3 border-brutal-black overflow-hidden bg-white dark:bg-zinc-700">
            {unaccessed > 0 && (
              <div
                className="bg-brutal-black flex items-center justify-center text-white text-xs font-bold transition-all duration-500"
                style={{ width: `${(unaccessed / total) * 100}%` }}
                title={t('memoryStats.distributionTooltipUnaccessed', { count: String(unaccessed) })}
              >
                {`${unaccessed}`}
              </div>
            )}
            {light > 0 && (
              <div
                className="bg-brutal-gray flex items-center justify-center text-white text-xs font-bold transition-all duration-500"
                style={{ width: `${(light / total) * 100}%` }}
                title={t('memoryStats.distributionTooltipLight', { count: String(light) })}
              >
                {`${light}`}
              </div>
            )}
            {engaged > 0 && (
              <div
                className="bg-white dark:bg-zinc-600 border-l-3 border-brutal-black flex items-center justify-center text-brutal-black dark:text-white text-xs font-bold transition-all duration-500"
                style={{ width: `${(engaged / total) * 100}%` }}
                title={t('memoryStats.distributionTooltipEngaged', { count: String(engaged) })}
              >
                {`${engaged}`}
              </div>
            )}
          </div>
          <div className="flex justify-between mt-2 text-xs dark:text-neutral-300">
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 bg-brutal-black border-2 border-brutal-black"></div>
              <span>{t('memoryStats.unaccessedCount', { count: String(unaccessed) })}</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 bg-brutal-gray border-2 border-brutal-black"></div>
              <span>{t('memoryStats.lightCount', { count: String(light) })}</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 bg-white dark:bg-zinc-500 border-2 border-brutal-black"></div>
              <span>{t('memoryStats.engagedCount', { count: String(engaged) })}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
