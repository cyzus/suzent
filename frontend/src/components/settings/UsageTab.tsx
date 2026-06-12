import React, { useEffect, useState, useMemo } from 'react';
import { fetchGlobalCost, fetchDailyCost } from '../../lib/api';
import type { CostGlobal, CostDaily } from '../../lib/api';
import { useI18n } from '../../i18n';
import { SettingsHeader } from './SettingsHeader';

type TimeRange = 7 | 14 | 30;

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
    for (let i = range - 1; i >= 0; i--) {
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
        {t('settings.usage.dailySpend')}
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
                  <div>{t('settings.usage.tooltipCalls', { count: String(d.calls) })}</div>
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
        <span>{t('settings.usage.today')}</span>
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([fetchGlobalCost(range), fetchDailyCost(range)])
      .then(([g, d]) => {
        if (cancelled) return;
        setGlobal(g);
        setDaily(d);
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
    return global.total_cost_usd / range;
  }, [global, range]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <SettingsHeader title={t('settings.usage.title')} subtitle={t('settings.usage.subtitle')} />

      {/* Time range selector */}
      <div className="flex gap-2">
        {([7, 14, 30] as TimeRange[]).map(r => (
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
            {t('settings.usage.days', { count: String(r) })}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center items-center py-16">
          <div className="animate-spin rounded-full h-12 w-12 border-b-4 border-brutal-black" />
        </div>
      ) : error ? (
        <div className="border-3 border-brutal-black bg-red-50 dark:bg-red-900/20 p-4">
          <p className="text-sm text-red-700 dark:text-red-400 font-mono">{error}</p>
        </div>
      ) : global ? (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard
              label={t('settings.usage.totalSpend')}
              value={formatCost(global.total_cost_usd)}
              sub={t('settings.usage.lastNDays', { count: String(range) })}
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

          {/* Daily chart */}
          <div className="border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-brutal p-6">
            <DailyChart data={daily} range={range} />
          </div>

          {/* Token breakdown */}
          <div className="border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-brutal p-6">
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
          </div>

          {/* Empty state */}
          {global.total_calls === 0 && (
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
