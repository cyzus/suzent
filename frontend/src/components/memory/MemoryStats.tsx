/**
 * Memory Statistics Dashboard Component
 * Displays visual stats with neo-brutalist styling
 */

import React from 'react';
import type { MemoryStats } from '../../types/memory';
import { useI18n } from '../../i18n';

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
            className="border-3 border-brutal-black bg-white p-4 animate-brutal-blink"
          >
            <div className="h-4 bg-neutral-200 mb-2"></div>
            <div className="h-8 bg-neutral-200"></div>
          </div>
        ))}
      </div>
    );
  }

  if (!stats) return null;

  const importanceDistribution = stats.importance_distribution || {};
  const high = importanceDistribution.high || 0;
  const medium = importanceDistribution.medium || 0;
  const low = importanceDistribution.low || 0;
  const total = high + medium + low || 1; // Prevent division by zero

  return (
    <div className="space-y-4">
      {/* Main Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Memories */}
        <div className="border-3 border-brutal-black bg-white shadow-[2px_2px_0_0_#000] p-4 brutal-btn transition-all">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold uppercase text-neutral-600">{t('memoryStats.totalMemories')}</span>
          </div>
          <div className="font-brutal text-3xl text-brutal-black">{stats.total_memories}</div>
        </div>

        {/* Avg Importance */}
        <div className="border-3 border-brutal-black bg-white shadow-[2px_2px_0_0_#000] p-4 brutal-btn transition-all">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold uppercase text-neutral-600">{t('memoryStats.avgImportance')}</span>
          </div>
          <div className="font-brutal text-3xl text-brutal-black">
            {stats.avg_importance.toFixed(2)}
          </div>
          <div className="mt-2 h-2 bg-white border-3 border-brutal-black">
            <div
              className="h-full bg-brutal-black transition-all duration-500"
              style={{ width: `${stats.avg_importance * 100}%` }}
            />
          </div>
        </div>

        {/* Total Accesses */}
        <div className="border-3 border-brutal-black bg-white shadow-[2px_2px_0_0_#000] p-4 brutal-btn transition-all">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold uppercase text-neutral-600">{t('memoryStats.totalAccesses')}</span>
          </div>
          <div className="font-brutal text-3xl text-brutal-black">
            {stats.total_accesses || 0}
          </div>
          <div className="text-xs text-neutral-500 mt-1">
            {t('memoryStats.avgPerMemory', { avg: stats.avg_access_count?.toFixed(1) || '0.0' })}
          </div>
        </div>

        {/* Importance Range */}
        <div className="border-3 border-brutal-black bg-white shadow-[2px_2px_0_0_#000] p-4 brutal-btn transition-all">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold uppercase text-neutral-600">{t('memoryStats.importanceRange')}</span>
          </div>
          <div className="flex items-baseline gap-1">
            <span className="font-brutal text-xl text-brutal-black">
              {stats.max_importance?.toFixed(2) || '0.00'}
            </span>
            <span className="text-brutal-black">→</span>
            <span className="font-brutal text-xl text-brutal-gray">
              {stats.min_importance?.toFixed(2) || '0.00'}
            </span>
          </div>
        </div>
      </div>

      {/* Importance Distribution Bar */}
      {(high > 0 || medium > 0 || low > 0) && (
        <div className="border-3 border-brutal-black bg-white shadow-brutal p-4">
          <h4 className="font-bold text-xs uppercase text-neutral-600 mb-3">
            {t('memoryStats.importanceDistribution')}
          </h4>
          <div className="flex h-8 border-3 border-brutal-black overflow-hidden bg-white">
            {high > 0 && (
              <div
                className="bg-brutal-black flex items-center justify-center text-white text-xs font-bold transition-all duration-500"
                style={{ width: `${(high / total) * 100}%` }}
                title={t('memoryStats.distributionTooltipHigh', { count: high })}
              >
                {high > 0 && `${high}`}
              </div>
            )}
            {medium > 0 && (
              <div
                className="bg-brutal-gray flex items-center justify-center text-white text-xs font-bold transition-all duration-500"
                style={{ width: `${(medium / total) * 100}%` }}
                title={t('memoryStats.distributionTooltipMedium', { count: medium })}
              >
                {medium > 0 && `${medium}`}
              </div>
            )}
            {low > 0 && (
              <div
                className="bg-white border-l-3 border-brutal-black flex items-center justify-center text-brutal-black text-xs font-bold transition-all duration-500"
                style={{ width: `${(low / total) * 100}%` }}
                title={t('memoryStats.distributionTooltipLow', { count: low })}
              >
                {low > 0 && `${low}`}
              </div>
            )}
          </div>
          <div className="flex justify-between mt-2 text-xs">
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 bg-brutal-black border-2 border-brutal-black"></div>
              <span>{t('memoryStats.highRangeCount', { count: high })}</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 bg-brutal-gray border-2 border-brutal-black"></div>
              <span>{t('memoryStats.mediumRangeCount', { count: medium })}</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 bg-white border-2 border-brutal-black"></div>
              <span>{t('memoryStats.lowRangeCount', { count: low })}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
