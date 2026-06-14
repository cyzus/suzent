import React, { useEffect, useState, useMemo } from 'react';
import { fetchGlobalCost, fetchDailyCost, fetchModelsCost, fetchActivityStats, fetchActivityGrid } from '../../lib/api';
import type { CostGlobal, CostDaily, CostModel, ActivityStats } from '../../lib/api';
import { useI18n } from '../../i18n';
import { SettingsHeader } from './SettingsHeader';
import { SettingsCard } from './SettingsCard';

type TimeRange = 1 | 7 | 30 | 'all';

function formatCost(usd: number): string {
  if (usd < 0.01 && usd > 0) return `$${usd.toFixed(4)}`;
  if (usd < 1) return `$${usd.toFixed(3)}`;
  return `$${usd.toFixed(2)}`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

/** Pure-CSS bar chart rendered as a flex row of bar columns. */
function DailyChart({ data, range }: { data: CostDaily[]; range: TimeRange }) {
  const { t } = useI18n();

  const filled = useMemo(() => {
    const today = new Date();
    const map = new Map(data.map(d => [d.date, d]));
    const result: CostDaily[] = [];
    const daysCount = range === 'all' ? 30 : range; // fallback to 30 for the bar chart if 'all' is selected to avoid squishing
    for (let i = daysCount - 1; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const key = d.toISOString().slice(0, 10);
      result.push(map.get(key) ?? { date: key, cost_usd: 0, input_tokens: 0, output_tokens: 0, calls: 0 });
    }
    return result;
  }, [data, range]);

  const maxCost = useMemo(() => Math.max(...filled.map(d => d.cost_usd), 0.001), [filled]);

  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  return (
    <div className="space-y-3">
      <div className="text-xs font-bold uppercase text-neutral-500 dark:text-neutral-400">
        {t('settings.usage.dailySpend')} {range === 'all' && '(Last 30 Days)'}
      </div>

      {/* Chart */}
      <div className="flex items-end gap-[2px] h-32 border-b-2 border-brutal-black dark:border-neutral-500">
        {filled.map((d, i) => {
          const pct = maxCost > 0 ? (d.cost_usd / maxCost) * 100 : 0;
          const barHeight = Math.max(pct, d.cost_usd > 0 ? 3 : 0);
          const isToday = i === filled.length - 1;
          const isHovered = hoveredIdx === i;

          return (
            <div
              key={d.date}
              className="flex-1 flex flex-col items-center justify-end h-full relative group"
              onMouseEnter={() => setHoveredIdx(i)}
              onMouseLeave={() => setHoveredIdx(null)}
            >
              {/* Tooltip */}
              {isHovered && (
                <div className="absolute bottom-full mb-2 z-10 bg-brutal-black text-white text-[10px] font-mono p-2 border-2 border-brutal-black shadow-brutal whitespace-nowrap pointer-events-none">
                  <div className="font-bold">{d.date}</div>
                  <div>{formatCost(d.cost_usd)}</div>
                  <div>{t('settings.usage.tooltipCalls', { count: String(d.calls) }) || `${d.calls} calls`}</div>
                </div>
              )}

              {/* Bar */}
              <div
                className={[
                  'w-full rounded-t-sm transition-all duration-200',
                  isToday
                    ? 'bg-brutal-yellow dark:bg-brutal-yellow'
                    : 'bg-neutral-400 dark:bg-neutral-500',
                  isHovered ? 'opacity-100 scale-x-110' : 'opacity-80 hover:opacity-100',
                ].join(' ')}
                style={{ height: `${barHeight}%`, minHeight: d.cost_usd > 0 ? '2px' : '0' }}
              />
            </div>
          );
        })}
      </div>

      {/* X-axis labels */}
      <div className="flex justify-between text-[9px] font-mono text-neutral-400 dark:text-neutral-500">
        <span>{filled[0]?.date.slice(5)}</span>
        <span>{t('settings.usage.today') || 'Today'}</span>
      </div>
    </div>
  );
}

function TokenActivity({ data, range }: { data: CostDaily[]; range: TimeRange }) {
  const { grid, maxTokens } = useMemo(() => {
    const numRows = 7;
    const numCols = 24;
    const totalCells = numRows * numCols; // 168

    const today = new Date().getTime();
    let startTime = today;
    if (range === 1) startTime -= 86400000;
    else if (range === 7) startTime -= 7 * 86400000;
    else if (range === 30) startTime -= 30 * 86400000;
    else startTime -= 365 * 86400000;

    const interval = (today - startTime) / totalCells;

    const gridRows: any[][] = Array.from({ length: numRows }, () => []);
    const buckets = Array.from({ length: totalCells }, (_, i) => {
      const bucketTime = startTime + i * interval;
      return {
        date: new Date(bucketTime).toISOString().slice(0, 16).replace('T', ' '),
        cost_usd: 0,
        input_tokens: 0,
        output_tokens: 0,
        calls: 0
      };
    });

    for (const d of data) {
      const t = new Date(d.date).getTime();
      if (t >= startTime && t <= today) {
        const bIdx = Math.min(Math.floor((t - startTime) / interval), totalCells - 1);
        buckets[bIdx].cost_usd += d.cost_usd;
        buckets[bIdx].input_tokens += d.input_tokens;
        buckets[bIdx].output_tokens += d.output_tokens;
        buckets[bIdx].calls += d.calls;
      }
    }

    const maxT = Math.max(...buckets.map(b => b.input_tokens + b.output_tokens), 1);

    for (let i = 0; i < totalCells; i++) {
      gridRows[i % numRows].push(buckets[i]);
    }

    return { grid: gridRows, maxTokens: maxT };
  }, [data, range]);

  return (
    <div className="space-y-3">
      <div className="text-xs font-bold uppercase text-neutral-500 dark:text-neutral-400">
        Token Activity ({range === 'all' ? 'Last 365 Days' : `Last ${range} ${range === 1 ? 'Day' : 'Days'}`})
      </div>
      <div className="overflow-x-auto pb-2 scrollbar-thin scrollbar-thumb-brutal-black dark:scrollbar-thumb-neutral-600">
        <div className="flex flex-col gap-[2px] min-w-max">
          {grid.map((row, rIdx) => (
            <div key={rIdx} className="flex gap-[2px]">
              {row.map((d: CostDaily, cIdx: number) => {
                const total = d.input_tokens + d.output_tokens;
                let intensity = 0;
                if (total > 0) {
                  intensity = Math.ceil((total / maxTokens) * 4); // 1 to 4
                }
                const bgClass = intensity === 0 ? 'bg-neutral-100 dark:bg-zinc-700' :
                                intensity === 1 ? 'bg-blue-200 dark:bg-blue-900' :
                                intensity === 2 ? 'bg-blue-400 dark:bg-blue-700' :
                                intensity === 3 ? 'bg-blue-500 dark:bg-blue-500' :
                                'bg-blue-600 dark:bg-blue-400';
                return (
                  <div
                    key={`${d.date}-${cIdx}`}
                    className={`w-3 h-3 rounded-sm ${bgClass} transition-all hover:ring-2 ring-brutal-black dark:ring-white z-10 hover:z-20`}
                    title={`${d.date.replace('T', ' ').slice(0, 16)}: ${formatTokens(total)} tokens`}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ModelBreakdown({ models }: { models: CostModel[] }) {
  if (models.length === 0) return null;
  const maxTokens = Math.max(...models.map(m => m.input_tokens + m.output_tokens), 1);

  return (
    <div className="space-y-4">
      <div className="text-xs font-bold uppercase text-neutral-500 dark:text-neutral-400">
        Model Breakdown
      </div>
      <div className="space-y-4">
        {models.map(m => (
          <div key={m.model} className="space-y-1">
            <div className="flex justify-between text-xs font-mono">
              <span className="font-bold text-brutal-black dark:text-white truncate" title={m.model}>
                {m.model}
              </span>
              <span className="text-neutral-500">{formatCost(m.cost_usd)}</span>
            </div>
            <div className="h-2 bg-neutral-100 dark:bg-zinc-700 border border-brutal-black flex">
               <div 
                 className="h-full bg-neutral-500 dark:bg-neutral-400 transition-all duration-500" 
                 style={{ width: `${(m.input_tokens / maxTokens) * 100}%` }} 
                 title={`Input: ${m.input_tokens}`}
               />
               <div 
                 className="h-full bg-brutal-yellow dark:bg-brutal-yellow transition-all duration-500" 
                 style={{ width: `${(m.output_tokens / maxTokens) * 100}%` }} 
                 title={`Output: ${m.output_tokens}`}
               />
            </div>
            <div className="flex justify-between text-[10px] text-neutral-400 font-mono">
              <span>{m.calls.toLocaleString()} calls</span>
              <span>{formatTokens(m.input_tokens + m.output_tokens)} tokens</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-brutal p-4 flex flex-col">
      <span className="text-[10px] font-bold uppercase text-neutral-400 dark:text-neutral-500 tracking-wider">
        {label}
      </span>
      <span className="text-2xl font-brutal font-bold text-brutal-black dark:text-white mt-1">
        {value}
      </span>
      {sub && (
        <span className="text-xs font-mono text-neutral-500 dark:text-neutral-400 mt-1">
          {sub}
        </span>
      )}
    </div>
  );
}

export function UsageTab(): React.ReactElement {
  const { t } = useI18n();
  const [range, setRange] = useState<TimeRange>(30);
  const [global, setGlobal] = useState<CostGlobal | null>(null);
  const [daily, setDaily] = useState<CostDaily[]>([]);
  const [models, setModels] = useState<CostModel[]>([]);
  const [stats, setStats] = useState<ActivityStats | null>(null);
  const [heatmap, setHeatmap] = useState<CostDaily[]>([]);
  
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const apiDays = range === 'all' ? 365 : range;

    Promise.all([
      fetchGlobalCost(apiDays),
      fetchDailyCost(apiDays),
      fetchModelsCost(apiDays),
      fetchActivityStats(),
      fetchActivityGrid(String(range))
    ])
      .then(([g, d, m, s, h]) => {
        if (cancelled) return;
        setGlobal(g);
        setDaily(d);
        setModels(m);
        setStats(s);
        setHeatmap(h);
      })
      .catch(e => {
        if (cancelled) return;
        setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [range]);

  const avgDaily = useMemo(() => {
    if (!global || !range) return 0;
    const days = range === 'all' ? 365 : range;
    return global.total_cost_usd / days;
  }, [global, range]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <SettingsHeader title={t('settings.usage.title')} subtitle={t('settings.usage.subtitle')} />

      {/* Time range selector */}
      <div className="flex gap-2">
        {([1, 7, 30, 'all'] as TimeRange[]).map(r => (
          <button
            key={r}
            onClick={() => setRange(r)}
            className={[
              'px-4 py-2 border-2 border-brutal-black font-bold uppercase text-xs transition-all',
              'shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none',
              range === r
                ? 'bg-brutal-black text-white dark:bg-brutal-yellow dark:text-brutal-black'
                : 'bg-white dark:bg-zinc-700 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-600',
            ].join(' ')}
          >
            {r === 'all' ? 'All' : `${r}D`}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center items-center py-16">
          <div className="animate-spin rounded-full h-12 w-12 border-b-4 border-brutal-black" />
        </div>
      ) : error ? (
        <div className="border-3 border-brutal-black bg-red-50 dark:bg-red-950 p-4">
          <p className="text-sm text-red-700 dark:text-red-400 font-mono">{error}</p>
        </div>
      ) : global ? (
        <>
          {/* Top Activity Stats */}
          {stats && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <StatCard
                label="Cumulative Tokens"
                value={formatTokens(stats.cumulative_tokens)}
              />
              <StatCard
                label="Peak Tokens/Day"
                value={formatTokens(stats.peak_tokens)}
              />
              <StatCard
                label="Current Streak"
                value={`${stats.current_streak} d`}
              />
              <StatCard
                label="Longest Streak"
                value={`${stats.longest_streak} d`}
              />
            </div>
          )}

          {/* Token Activity Graph */}
          {heatmap.length > 0 && (
            <SettingsCard>
              <TokenActivity data={heatmap} range={range} />
            </SettingsCard>
          )}

          {/* Range Summary cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard
              label={t('settings.usage.totalSpend')}
              value={formatCost(global.total_cost_usd)}
              sub={range === 'all' ? 'All Time' : `Last ${range} days`}
            />
            <StatCard
              label={t('settings.usage.avgDaily')}
              value={formatCost(avgDaily)}
              sub={t('settings.usage.perDay')}
            />
            <StatCard
              label={t('settings.usage.totalCalls')}
              value={global.total_calls.toLocaleString()}
              sub={t('settings.usage.apiCalls')}
            />
            <StatCard
              label={t('settings.usage.totalTokens')}
              value={formatTokens(global.total_input_tokens + global.total_output_tokens)}
              sub={`↓${formatTokens(global.total_input_tokens)} ↑${formatTokens(global.total_output_tokens)}`}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="space-y-6">
              {/* Daily chart */}
              <SettingsCard>
                <DailyChart data={daily} range={range} />
              </SettingsCard>

              {/* Token breakdown */}
              <SettingsCard>
                <div className="text-xs font-bold uppercase text-neutral-500 dark:text-neutral-400 mb-4">
                  {t('settings.usage.tokenBreakdown')}
                </div>

                <div className="space-y-3">
                  {/* Input tokens bar */}
                  <div>
                    <div className="flex justify-between text-xs font-mono mb-1">
                      <span className="text-neutral-600 dark:text-neutral-300">{t('settings.usage.inputTokens')}</span>
                      <span className="font-bold text-brutal-black dark:text-white">
                        {formatTokens(global.total_input_tokens)}
                      </span>
                    </div>
                    <div className="h-3 bg-neutral-100 dark:bg-zinc-700 border-2 border-brutal-black">
                      <div
                        className="h-full bg-neutral-500 dark:bg-neutral-400 transition-all duration-500"
                        style={{
                          width: `${(global.total_input_tokens / Math.max(global.total_input_tokens + global.total_output_tokens, 1)) * 100}%`,
                        }}
                      />
                    </div>
                  </div>

                  {/* Output tokens bar */}
                  <div>
                    <div className="flex justify-between text-xs font-mono mb-1">
                      <span className="text-neutral-600 dark:text-neutral-300">{t('settings.usage.outputTokens')}</span>
                      <span className="font-bold text-brutal-black dark:text-white">
                        {formatTokens(global.total_output_tokens)}
                      </span>
                    </div>
                    <div className="h-3 bg-neutral-100 dark:bg-zinc-700 border-2 border-brutal-black">
                      <div
                        className="h-full bg-brutal-yellow dark:bg-brutal-yellow transition-all duration-500"
                        style={{
                          width: `${(global.total_output_tokens / Math.max(global.total_input_tokens + global.total_output_tokens, 1)) * 100}%`,
                        }}
                      />
                    </div>
                  </div>
                </div>
              </SettingsCard>
            </div>

            <div className="space-y-6">
               {/* Model Breakdown */}
               {models.length > 0 && (
                 <SettingsCard>
                   <ModelBreakdown models={models} />
                 </SettingsCard>
               )}
            </div>
          </div>

          {/* Empty state */}
          {global.total_calls === 0 && heatmap.length === 0 && (
            <div className="border-3 border-dashed border-neutral-300 dark:border-neutral-600 p-8 text-center">
              <p className="text-sm text-neutral-500 dark:text-neutral-400 font-mono">
                {t('settings.usage.noUsageYet')}
              </p>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
