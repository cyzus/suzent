/**
 * Memory Statistics Dashboard Component
 * One compact summary block: the total, two rate read-outs, and the access
 * breakdown that those rates are computed from.
 */

import React from 'react';
import { ArrowPathIcon } from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';
import { BrutalButton } from '../BrutalButton';
import type { MemoryStats } from '../../types/memory';

interface MemoryStatsProps {
  stats: MemoryStats | null;
  isLoading?: boolean;
  onRefresh?: () => void;
}

const toPercent = (value?: number) => `${((value || 0) * 100).toFixed(1)}%`;

interface RateProps {
  label: string;
  value: string;
  detail: string;
  ratio: number;
}

/** A rate read-out: label, percentage, raw counts, and a hairline bar. */
const Rate: React.FC<RateProps> = ({ label, value, detail, ratio }) => (
  <div className="min-w-[7.5rem]">
    <div className="text-[10px] font-bold uppercase tracking-wide text-neutral-600 dark:text-neutral-400">
      {label}
    </div>
    <div className="font-brutal text-xl leading-tight text-brutal-black dark:text-white">
      {value}
    </div>
    <div className="mt-1 h-1.5 w-24 border-2 border-brutal-black bg-white dark:bg-zinc-700">
      <div
        className="h-full bg-brutal-black transition-all duration-500 dark:bg-white"
        style={{ width: `${Math.min(Math.max(ratio * 100, 0), 100)}%` }}
      />
    </div>
    <div className="mt-1 font-mono text-[10px] text-neutral-500 dark:text-neutral-400">
      {detail}
    </div>
  </div>
);

export const MemoryStatsComponent: React.FC<MemoryStatsProps> = ({
  stats,
  isLoading,
  onRefresh,
}) => {
  const { t } = useI18n();

  if (isLoading && !stats) {
    return (
      <div className="border-3 border-brutal-black bg-white p-4 shadow-brutal animate-brutal-blink dark:bg-zinc-800">
        <div className="mb-4 h-8 w-40 bg-neutral-200 dark:bg-zinc-700" />
        <div className="h-7 bg-neutral-200 dark:bg-zinc-700" />
      </div>
    );
  }

  if (!stats) return null;

  const accessDistribution = stats.access_distribution || {};
  const unaccessed = accessDistribution.unaccessed || 0;
  const light = accessDistribution.light || 0;
  const engaged = accessDistribution.engaged || 0;
  const distributionTotal = unaccessed + light + engaged;
  const totalMemories = stats.total_memories || 0;

  // Engaged first: the bar reads left-to-right from most-used to never-touched.
  const tiers = [
    {
      key: 'engaged',
      count: engaged,
      fill: 'bg-brutal-green',
      legend: t('memoryStats.engagedCount', { count: String(engaged) }),
      title: t('memoryStats.distributionTooltipEngaged', { count: String(engaged) }),
    },
    {
      key: 'light',
      count: light,
      fill: 'bg-brutal-yellow',
      legend: t('memoryStats.lightCount', { count: String(light) }),
      title: t('memoryStats.distributionTooltipLight', { count: String(light) }),
    },
    {
      key: 'unaccessed',
      count: unaccessed,
      fill: 'bg-neutral-200 dark:bg-zinc-600',
      legend: t('memoryStats.unaccessedCount', { count: String(unaccessed) }),
      title: t('memoryStats.distributionTooltipUnaccessed', { count: String(unaccessed) }),
    },
  ].filter((tier) => tier.count > 0);

  const share = (count: number) => (distributionTotal ? (count / distributionTotal) * 100 : 0);

  return (
    <div className="border-3 border-brutal-black bg-white p-4 shadow-brutal dark:bg-zinc-800">
      <div className="flex flex-wrap items-start gap-x-8 gap-y-4">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-wide text-neutral-600 dark:text-neutral-400">
            {t('memoryStats.totalMemories')}
          </div>
          <div className="font-brutal text-4xl leading-none text-brutal-black dark:text-white">
            {totalMemories}
          </div>
        </div>

        <Rate
          label={t('memoryStats.memoryUtilization')}
          value={toPercent(stats.utilization_rate)}
          detail={`${stats.utilized_memories || 0}/${totalMemories}`}
          ratio={stats.utilization_rate || 0}
        />
        <Rate
          label={t('memoryStats.activity7d')}
          value={toPercent(stats.recent_activity_rate_7d)}
          detail={`${stats.recently_accessed_memories_7d || 0}/${totalMemories}`}
          ratio={stats.recent_activity_rate_7d || 0}
        />
        <Rate
          label={t('memoryStats.coldMemoryRatio')}
          value={toPercent(stats.cold_memory_ratio)}
          detail={`${stats.cold_memories || 0}/${totalMemories}`}
          ratio={stats.cold_memory_ratio || 0}
        />

        {onRefresh && (
          <BrutalButton
            onClick={onRefresh}
            size="icon"
            title={t('memoryStats.refresh')}
            aria-label={t('memoryStats.refresh')}
            className="ml-auto"
          >
            <ArrowPathIcon className={`h-4 w-4 stroke-2 ${isLoading ? 'animate-spin' : ''}`} />
          </BrutalButton>
        )}
      </div>

      {distributionTotal > 0 ? (
        <div className="mt-4 border-t-2 border-neutral-200 pt-3 dark:border-zinc-700">
          <div className="mb-2 text-[10px] font-bold uppercase tracking-wide text-neutral-600 dark:text-neutral-400">
            {t('memoryStats.accessDistribution')}
          </div>
          <div className="flex h-6 overflow-hidden border-2 border-brutal-black bg-white dark:bg-zinc-700">
            {tiers.map((tier, index) => (
              <div
                key={tier.key}
                className={`flex items-center justify-center text-[11px] font-bold text-brutal-black transition-all duration-500 ${tier.fill} ${index > 0 ? 'border-l-2 border-brutal-black' : ''}`}
                style={{ width: `${share(tier.count)}%` }}
                title={tier.title}
              >
                {/* Below ~7% the label collides with the segment borders. */}
                {share(tier.count) >= 7 ? tier.count : ''}
              </div>
            ))}
          </div>
          <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-brutal-black dark:text-neutral-300">
            {tiers.map((tier) => (
              <div key={tier.key} className="flex items-center gap-1.5" title={tier.title}>
                <div className={`h-3 w-3 border-2 border-brutal-black ${tier.fill}`} />
                <span>{tier.legend}</span>
                <span className="font-mono text-neutral-500 dark:text-neutral-400">
                  {share(tier.count).toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="mt-4 border-t-2 border-neutral-200 pt-3 font-mono text-xs text-neutral-500 dark:border-zinc-700 dark:text-neutral-400">
          {t('memoryStats.emptyHint')}
        </div>
      )}
    </div>
  );
};
