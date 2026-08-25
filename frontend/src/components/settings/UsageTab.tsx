import React, { useEffect, useState, useMemo } from 'react';
import {
  fetchGlobalCost,
  fetchDailyCost,
  fetchModelsCost,
  fetchActivityStats,
  fetchActivityGrid,
} from '../../lib/api';
import type { CostGlobal, CostDaily, CostModel, ActivityStats } from '../../lib/api';
import { useI18n } from '../../i18n';
import { SettingsHeader } from './SettingsHeader';
import { SettingsCard, SettingsPage } from './SettingsCard';

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
    const map = new Map(data.map((d) => [d.date, d]));
    const result: CostDaily[] = [];
    const daysCount = range === 'all' ? 30 : range; // fallback to 30 for the bar chart if 'all' is selected to avoid squishing
    for (let i = daysCount - 1; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const key = d.toISOString().slice(0, 10);
      result.push(
        map.get(key) ?? { date: key, cost_usd: 0, input_tokens: 0, output_tokens: 0, calls: 0 }
      );
    }
    return result;
  }, [data, range]);

  const maxCost = useMemo(() => Math.max(...filled.map((d) => d.cost_usd), 0.001), [filled]);

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
                  <div>
                    {t('settings.usage.tooltipCalls', { count: String(d.calls) }) ||
                      `${d.calls} calls`}
                  </div>
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

interface ActivityCell {
  key: string;
  label: string;
  inputTokens: number;
  outputTokens: number;
  calls: number;
}

const DAY_MS = 86_400_000;
const ACTIVITY_LEVEL_STRENGTH = [0, 25, 48, 72, 100];

function addUtcDays(date: Date, days: number): Date {
  return new Date(date.getTime() + days * DAY_MS);
}

function utcDateKey(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function activityLevel(tokens: number, thresholds: number[]): number {
  if (tokens === 0) return 0;
  const level = thresholds.findIndex((threshold) => tokens <= threshold);
  return level === -1 ? 4 : level + 1;
}

function getActivityThresholds(cells: ActivityCell[]): number[] {
  const nonZero = cells
    .map((cell) => cell.inputTokens + cell.outputTokens)
    .filter((tokens) => tokens > 0)
    .sort((a, b) => a - b);

  if (nonZero.length === 0) return [1, 1, 1];
  return [0.25, 0.5, 0.75].map((quantile) => {
    const index = Math.min(Math.floor((nonZero.length - 1) * quantile), nonZero.length - 1);
    return nonZero[index];
  });
}

function ActivitySquare({
  cell,
  thresholds,
  onInspect,
  sizeClass,
}: {
  cell: ActivityCell;
  thresholds: number[];
  onInspect: (cell: ActivityCell | null) => void;
  sizeClass: string;
}) {
  const { locale, t } = useI18n();
  const level = activityLevel(cell.inputTokens + cell.outputTokens, thresholds);
  const backgroundColor =
    level === 0
      ? undefined
      : `color-mix(in srgb, var(--brutal-yellow) ${ACTIVITY_LEVEL_STRENGTH[level]}%, transparent)`;

  return (
    <button
      type="button"
      className={`${sizeClass} ${level === 0 ? 'bg-neutral-100 dark:bg-zinc-700/70' : ''} border-2 border-brutal-black transition-shadow duration-100 hover:ring-2 hover:ring-inset focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset ring-brutal-black dark:ring-white`}
      style={{ backgroundColor }}
      aria-label={t('settings.usage.activityCellLabel', {
        date: cell.label,
        tokens: (cell.inputTokens + cell.outputTokens).toLocaleString(locale),
        calls: cell.calls.toLocaleString(locale),
      })}
      onMouseEnter={() => onInspect(cell)}
      onMouseLeave={() => onInspect(null)}
      onFocus={() => onInspect(cell)}
      onBlur={() => onInspect(null)}
    />
  );
}

function TokenActivity({ data, range }: { data: CostDaily[]; range: TimeRange }) {
  const { locale, t } = useI18n();
  const [inspected, setInspected] = useState<ActivityCell | null>(null);
  const today = useMemo(() => {
    const now = new Date();
    return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  }, []);

  const calendar = useMemo(() => {
    if (range !== 30 && range !== 'all') return null;

    const dayCount = range === 'all' ? 365 : 30;
    const firstDay = addUtcDays(today, -(dayCount - 1));
    const totals = new Map<string, ActivityCell>();

    for (const item of data) {
      const key = item.date.slice(0, 10);
      if (key < utcDateKey(firstDay) || key > utcDateKey(today)) continue;
      const current = totals.get(key) ?? {
        key,
        label: new Date(`${key}T00:00:00Z`).toLocaleDateString(locale, {
          timeZone: 'UTC',
          month: 'short',
          day: 'numeric',
          year: 'numeric',
        }),
        inputTokens: 0,
        outputTokens: 0,
        calls: 0,
      };
      current.inputTokens += item.input_tokens;
      current.outputTokens += item.output_tokens;
      current.calls += item.calls;
      totals.set(key, current);
    }

    const gridStart = addUtcDays(firstDay, -firstDay.getUTCDay());
    const gridEnd = addUtcDays(today, 6 - today.getUTCDay());
    const weeks: Array<Array<ActivityCell | null>> = [];
    for (let cursor = gridStart; cursor <= gridEnd; cursor = addUtcDays(cursor, 7)) {
      const week: Array<ActivityCell | null> = [];
      for (let day = 0; day < 7; day += 1) {
        const date = addUtcDays(cursor, day);
        const key = utcDateKey(date);
        if (date < firstDay || date > today) {
          week.push(null);
          continue;
        }
        week.push(
          totals.get(key) ?? {
            key,
            label: date.toLocaleDateString(locale, {
              timeZone: 'UTC',
              month: 'short',
              day: 'numeric',
              year: 'numeric',
            }),
            inputTokens: 0,
            outputTokens: 0,
            calls: 0,
          }
        );
      }
      weeks.push(week);
    }

    const cells = weeks.flat().filter((cell): cell is ActivityCell => cell !== null);
    return { weeks, cells, thresholds: getActivityThresholds(cells) };
  }, [data, locale, range, today]);

  const hourly = useMemo(() => {
    if (range !== 1 && range !== 7) return null;

    if (range === 1) {
      const currentHour = new Date();
      currentHour.setUTCMinutes(0, 0, 0);
      const firstHour = new Date(currentHour.getTime() - 23 * 3_600_000);
      const cells = Array.from({ length: 4 }, (_, quarter) =>
        Array.from({ length: 24 }, (_, hourOffset) => {
          const hour = new Date(firstHour.getTime() + hourOffset * 3_600_000);
          const minute = quarter * 15;
          const start = new Date(hour.getTime() + minute * 60_000);
          return {
            key: start.toISOString(),
            label: start.toLocaleString(locale, {
              timeZone: 'UTC',
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
              hour12: false,
            }),
            inputTokens: 0,
            outputTokens: 0,
            calls: 0,
          };
        })
      );
      for (const item of data) {
        const timestamp = new Date(item.date);
        const hourOffset = Math.floor((timestamp.getTime() - firstHour.getTime()) / 3_600_000);
        if (hourOffset < 0 || hourOffset >= 24) continue;
        const quarter = Math.min(Math.floor(timestamp.getUTCMinutes() / 15), 3);
        const cell = cells[quarter][hourOffset];
        cell.inputTokens += item.input_tokens;
        cell.outputTokens += item.output_tokens;
        cell.calls += item.calls;
      }
      return {
        cells,
        columnLabels: Array.from({ length: 24 }, (_, index) => {
          const hour = new Date(firstHour.getTime() + index * 3_600_000).getUTCHours();
          return index % 4 === 0 ? `${String(hour).padStart(2, '0')}:00` : '';
        }),
        rowLabels: ['00', '15', '30', '45'],
        thresholds: getActivityThresholds(cells.flat()),
      };
    }

    const firstDay = addUtcDays(today, -6);
    const cells = Array.from({ length: 7 }, (_, dayOffset) => {
      const date = addUtcDays(firstDay, dayOffset);
      return Array.from({ length: 24 }, (_, hour) => ({
        key: `${utcDateKey(date)}-${hour}`,
        label: new Date(date.getTime() + hour * 3_600_000).toLocaleString(locale, {
          timeZone: 'UTC',
          weekday: 'short',
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          hour12: false,
        }),
        inputTokens: 0,
        outputTokens: 0,
        calls: 0,
      }));
    });
    for (const item of data) {
      const timestamp = new Date(item.date);
      const dayOffset = Math.floor(
        (Date.UTC(timestamp.getUTCFullYear(), timestamp.getUTCMonth(), timestamp.getUTCDate()) -
          firstDay.getTime()) /
          DAY_MS
      );
      if (dayOffset < 0 || dayOffset >= 7) continue;
      const cell = cells[dayOffset][timestamp.getUTCHours()];
      cell.inputTokens += item.input_tokens;
      cell.outputTokens += item.output_tokens;
      cell.calls += item.calls;
    }
    return {
      cells,
      columnLabels: Array.from({ length: 24 }, (_, hour) =>
        hour % 4 === 0 ? `${String(hour).padStart(2, '0')}:00` : ''
      ),
      rowLabels: cells.map((row) =>
        new Date(`${row[0].key.slice(0, 10)}T00:00:00Z`).toLocaleDateString(locale, {
          timeZone: 'UTC',
          weekday: 'short',
        })
      ),
      thresholds: getActivityThresholds(cells.flat()),
    };
  }, [data, locale, range, today]);

  const allCells = calendar?.cells ?? hourly?.cells.flat() ?? [];
  const activeCells = allCells.filter((cell) => cell.inputTokens + cell.outputTokens > 0).length;
  const totalTokens = allCells.reduce((sum, cell) => sum + cell.inputTokens + cell.outputTokens, 0);
  const rangeLabel =
    range === 1
      ? t('settings.usage.last24Hours')
      : t('settings.usage.lastNDays', { count: range === 'all' ? 365 : range });
  const thresholds = calendar?.thresholds ?? hourly?.thresholds ?? [1, 1, 1];

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-xs font-bold uppercase text-neutral-600 dark:text-neutral-300">
            {t('settings.usage.tokenActivity')}
          </div>
          <div className="mt-1 text-[11px] font-mono text-neutral-400 dark:text-neutral-500">
            {rangeLabel} · {t('settings.usage.utcTime')}
          </div>
        </div>
        <div className="min-h-9 text-left sm:text-right font-mono">
          {inspected ? (
            <>
              <div className="text-xs font-bold text-brutal-black dark:text-white">
                {inspected.label}
              </div>
              <div className="text-[10px] text-neutral-500 dark:text-neutral-400">
                {(inspected.inputTokens + inspected.outputTokens).toLocaleString(locale)}{' '}
                {t('settings.usage.tokensLowercase')} ·{' '}
                {t('settings.usage.tooltipCalls', {
                  count: inspected.calls.toLocaleString(locale),
                })}
              </div>
            </>
          ) : (
            <>
              <div className="text-xs font-bold text-brutal-black dark:text-white">
                {formatTokens(totalTokens)} {t('settings.usage.tokensLowercase')}
              </div>
              <div className="text-[10px] text-neutral-500 dark:text-neutral-400">
                {t('settings.usage.activePeriods', { count: activeCells })}
              </div>
            </>
          )}
        </div>
      </div>

      {calendar && range === 'all' && (
        <div className="w-full min-w-0 pb-1">
          <div
            className="grid gap-[2px] sm:gap-[3px]"
            style={{
              gridTemplateColumns: `1.5rem repeat(${calendar.weeks.length}, minmax(0, 1fr))`,
            }}
          >
            <div />
            {calendar.weeks.map((week, weekIndex) => {
              const firstVisible = week.find((cell): cell is ActivityCell => cell !== null);
              const previousWeek = weekIndex > 0 ? calendar.weeks[weekIndex - 1] : [];
              const previousVisible = previousWeek.find(
                (cell): cell is ActivityCell => cell !== null
              );
              const month = firstVisible?.key.slice(5, 7);
              const showMonth =
                firstVisible && (weekIndex === 0 || month !== previousVisible?.key.slice(5, 7));
              return (
                <div
                  key={`month-${weekIndex}`}
                  className="h-4 overflow-visible whitespace-nowrap text-[9px] font-mono text-neutral-400 dark:text-neutral-500"
                >
                  {showMonth
                    ? new Date(`${firstVisible.key}T00:00:00Z`).toLocaleDateString(locale, {
                        timeZone: 'UTC',
                        month: 'short',
                      })
                    : ''}
                </div>
              );
            })}
            <div className="grid grid-rows-7 gap-[2px] sm:gap-[3px] text-[9px] font-mono leading-none text-neutral-400 dark:text-neutral-500">
              {Array.from({ length: 7 }, (_, day) => (
                <div key={day} className="flex items-center">
                  {day % 2 === 1
                    ? new Date(Date.UTC(2024, 0, 7 + day)).toLocaleDateString(locale, {
                        timeZone: 'UTC',
                        weekday: 'short',
                      })
                    : ''}
                </div>
              ))}
            </div>
            {calendar.weeks.map((week, weekIndex) => (
              <div key={`week-${weekIndex}`} className="grid grid-rows-7 gap-[2px] sm:gap-[3px]">
                {week.map((cell, dayIndex) =>
                  cell ? (
                    <ActivitySquare
                      key={cell.key}
                      cell={cell}
                      thresholds={thresholds}
                      onInspect={setInspected}
                      sizeClass="w-full aspect-square"
                    />
                  ) : (
                    <div key={`empty-${dayIndex}`} className="w-full aspect-square" />
                  )
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {calendar && range === 30 && (
        <div className="overflow-x-auto pb-1 scrollbar-thin scrollbar-thumb-brutal-black dark:scrollbar-thumb-neutral-600">
          <div className="grid min-w-[620px] grid-cols-[repeat(30,minmax(18px,1fr))] gap-1">
            {calendar.cells.map((cell) => (
              <ActivitySquare
                key={cell.key}
                cell={cell}
                thresholds={thresholds}
                onInspect={setInspected}
                sizeClass="h-7 w-full"
              />
            ))}
            {calendar.cells.map((cell, index) => (
              <div
                key={`label-${cell.key}`}
                className={`overflow-visible whitespace-nowrap text-[8px] font-mono text-neutral-400 dark:text-neutral-500 ${index === calendar.cells.length - 1 ? 'text-right' : ''}`}
              >
                {index % 5 === 0 || index === calendar.cells.length - 1
                  ? new Date(`${cell.key}T00:00:00Z`).toLocaleDateString(locale, {
                      timeZone: 'UTC',
                      month: 'short',
                      day: 'numeric',
                    })
                  : ''}
              </div>
            ))}
          </div>
        </div>
      )}

      {hourly && (
        <div className="overflow-x-auto pb-1 scrollbar-thin scrollbar-thumb-brutal-black dark:scrollbar-thumb-neutral-600">
          <div
            className="grid min-w-[620px] gap-1"
            style={{ gridTemplateColumns: '2.5rem repeat(24, minmax(18px, 1fr))' }}
          >
            <div />
            {hourly.columnLabels.map((label, index) => (
              <div
                key={`hour-${index}`}
                className="text-[8px] font-mono text-neutral-400 dark:text-neutral-500"
              >
                {label}
              </div>
            ))}
            {hourly.cells.map((row, rowIndex) => (
              <React.Fragment key={`row-${rowIndex}`}>
                <div className="flex items-center text-[9px] font-mono text-neutral-400 dark:text-neutral-500">
                  {hourly.rowLabels[rowIndex]}
                </div>
                {row.map((cell) => (
                  <ActivitySquare
                    key={cell.key}
                    cell={cell}
                    thresholds={thresholds}
                    onInspect={setInspected}
                    sizeClass="w-full h-4"
                  />
                ))}
              </React.Fragment>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center justify-end gap-1.5 text-[9px] font-mono text-neutral-400 dark:text-neutral-500">
        <span>{t('settings.usage.less')}</span>
        {[0, 1, 2, 3, 4].map((level) => (
          <span
            key={level}
            className={`h-3 w-3 border-2 border-brutal-black ${level === 0 ? 'bg-neutral-100 dark:bg-zinc-700/70' : ''}`}
            style={{
              backgroundColor:
                level === 0
                  ? undefined
                  : `color-mix(in srgb, var(--brutal-yellow) ${ACTIVITY_LEVEL_STRENGTH[level]}%, transparent)`,
            }}
          />
        ))}
        <span>{t('settings.usage.more')}</span>
      </div>
    </div>
  );
}

function ModelBreakdown({ models }: { models: CostModel[] }) {
  if (models.length === 0) return null;
  const maxTokens = Math.max(...models.map((m) => m.input_tokens + m.output_tokens), 1);

  return (
    <div className="space-y-4">
      <div className="text-xs font-bold uppercase text-neutral-500 dark:text-neutral-400">
        Model Breakdown
      </div>
      <div className="space-y-4">
        {models.map((m) => (
          <div key={m.model} className="space-y-1">
            <div className="flex justify-between text-xs font-mono">
              <span
                className="font-bold text-brutal-black dark:text-white truncate"
                title={m.model}
              >
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
    <div className="flex flex-col border-2 border-brutal-black bg-white p-4 shadow-brutal-sm dark:bg-zinc-800">
      <span className="text-[10px] font-bold uppercase text-neutral-400 dark:text-neutral-500 tracking-wider">
        {label}
      </span>
      <span className="text-2xl font-brutal font-bold text-brutal-black dark:text-white mt-1">
        {value}
      </span>
      {sub && (
        <span className="text-xs font-mono text-neutral-500 dark:text-neutral-400 mt-1">{sub}</span>
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
      fetchActivityGrid(String(range)),
    ])
      .then(([g, d, m, s, h]) => {
        if (cancelled) return;
        setGlobal(g);
        setDaily(d);
        setModels(m);
        setStats(s);
        setHeatmap(h);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [range]);

  const avgDaily = useMemo(() => {
    if (!global || !range) return 0;
    const days = range === 'all' ? 365 : range;
    return global.total_cost_usd / days;
  }, [global, range]);

  return (
    <SettingsPage>
      {/* Header */}
      <SettingsHeader title={t('settings.usage.title')} subtitle={t('settings.usage.subtitle')} />

      {/* Time range selector */}
      <div className="flex gap-2">
        {([1, 7, 30, 'all'] as TimeRange[]).map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
            className={[
              'px-4 py-2 border-2 border-brutal-black font-bold uppercase text-xs brutal-btn',
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
        <div className="border-2 border-brutal-black bg-red-50 p-4 dark:bg-red-950">
          <p className="text-sm text-red-700 dark:text-red-400 font-mono">{error}</p>
        </div>
      ) : global ? (
        <>
          {/* Top Activity Stats */}
          {stats && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <StatCard label="Cumulative Tokens" value={formatTokens(stats.cumulative_tokens)} />
              <StatCard label="Peak Tokens/Day" value={formatTokens(stats.peak_tokens)} />
              <StatCard label="Current Streak" value={`${stats.current_streak} d`} />
              <StatCard label="Longest Streak" value={`${stats.longest_streak} d`} />
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
                      <span className="text-neutral-600 dark:text-neutral-300">
                        {t('settings.usage.inputTokens')}
                      </span>
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
                      <span className="text-neutral-600 dark:text-neutral-300">
                        {t('settings.usage.outputTokens')}
                      </span>
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
            <div className="border-2 border-dashed border-neutral-300 p-6 text-center dark:border-neutral-600">
              <p className="text-sm text-neutral-500 dark:text-neutral-400 font-mono">
                {t('settings.usage.noUsageYet')}
              </p>
            </div>
          )}
        </>
      ) : null}
    </SettingsPage>
  );
}
