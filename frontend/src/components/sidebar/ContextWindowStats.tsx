import { useEffect } from 'react';
import { useChatStore } from '../../hooks/useChatStore';
import { useCompact, type CompactionStage } from '../../hooks/useCompact';
import { useContextUsageStore } from '../../hooks/useContextUsageStore';
import { useContextUsageStats } from '../../hooks/useContextUsageStats';
import { useI18n } from '../../i18n';
import { formatPercent, formatTokens, usageBarColor } from '../../lib/contextFormat';
import { CompactionCube, CompactionSweep } from '../chat/CompactionCube';

const RUNNING_STAGES: CompactionStage[] = ['loading', 'analyzing', 'summarizing', 'saving'];

/** Header entry for context usage; the detail lives in the sidebar overview. */
export function ContextHeaderButton({
  chatId,
  active,
  onOpen,
}: {
  chatId: string | null | undefined;
  active: boolean;
  onOpen: () => void;
}): JSX.Element | null {
  const { t } = useI18n();
  const { measuredPercent } = useContextUsageStats(chatId);
  const { compaction, clearCompaction } = useContextUsageStore();
  useEffect(() => {
    // Keep a finished or failed pass on screen briefly; a running one stays
    // until its own terminal event arrives.
    if (!compaction || compaction.active) return;
    const timer = window.setTimeout(clearCompaction, 10_000);
    return () => window.clearTimeout(timer);
  }, [compaction, clearCompaction]);

  if (measuredPercent == null) return null;
  const compacting = compaction?.active === true;
  const label = `${t('contextPanel.usage')} ${formatPercent(measuredPercent)}`;
  return (
    <button
      type="button"
      onClick={onOpen}
      title={label}
      aria-label={label}
      aria-pressed={active}
      className={`flex h-7 items-center gap-1.5 rounded px-1.5 font-mono text-[10px] font-bold transition-colors ${
        active
          ? 'bg-neutral-200 text-brutal-black dark:bg-zinc-700 dark:text-white'
          : 'text-neutral-500 hover:bg-neutral-100 hover:text-brutal-black dark:text-neutral-400 dark:hover:bg-zinc-700 dark:hover:text-white'
      }`}
    >
      <span className="h-1.5 w-10 overflow-hidden rounded-full bg-neutral-300 dark:bg-zinc-600">
        <span
          className={`block h-full rounded-full transition-all ${usageBarColor(measuredPercent)}`}
          style={{ width: `${measuredPercent}%` }}
        />
      </span>
      <span>{formatPercent(measuredPercent)}</span>
      {compacting && <CompactionCube size={12} />}
      {measuredPercent >= 80 && !compacting && (
        <span className="hidden uppercase tracking-wider text-brutal-red md:inline">
          {t('contextPanel.compactHint')}
        </span>
      )}
    </button>
  );
}

/** Collapsed overview row: the measured headline with a single bar. */
export function ContextUsageHeadline({ chatId }: { chatId: string }): JSX.Element | null {
  const { measured, measuredPercent, limit } = useContextUsageStats(chatId);
  if (measured == null || measuredPercent == null || !limit) return null;
  return (
    <div className="mt-2 space-y-1.5">
      <div className="font-mono text-[11px] tabular-nums text-neutral-500 dark:text-neutral-400">
        {formatTokens(measured)} / {formatTokens(limit)}
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-neutral-200 dark:bg-zinc-700">
        <div
          className={`h-full rounded-full transition-all ${usageBarColor(measuredPercent)}`}
          style={{ width: `${measuredPercent}%` }}
        />
      </div>
    </div>
  );
}

function StatRow({
  label,
  value,
  share,
  valueClass = '',
  title,
}: {
  label: string;
  value: number;
  share?: string | null;
  valueClass?: string;
  title?: string;
}): JSX.Element {
  return (
    <div className="flex justify-between gap-3 py-0.5" title={title}>
      <span className="text-neutral-500 dark:text-neutral-400">{label}</span>
      <span className="tabular-nums">
        <span className={valueClass}>{formatTokens(value)}</span>
        {share && <span className="ml-1.5 text-neutral-400 dark:text-neutral-500">{share}</span>}
      </span>
    </div>
  );
}

/** Measured token counts and compaction, shown above the estimated breakdown. */
export function ContextWindowStats({ chatId }: { chatId: string }): JSX.Element | null {
  const { t } = useI18n();
  const { usage, measured, measuredPercent, limit } = useContextUsageStats(chatId);
  const { compaction, setCompaction } = useContextUsageStore();
  const { isStreaming } = useChatStore();
  const { compact, progress } = useCompact();

  // Mirror a pass started here into the store, where agent-started passes
  // already land, so the header and this panel watch one source.
  useEffect(() => {
    if (progress.stage === 'idle') return;
    const running = RUNNING_STAGES.includes(progress.stage);
    setCompaction({
      active: running,
      stage: running ? 'start' : progress.stage === 'error' ? 'error' : 'complete',
      source: 'manual',
      label:
        progress.stage === 'error'
          ? progress.message || t('contextPanel.compactStages.error')
          : t(`contextPanel.compactStages.${progress.stage}`),
    });
  }, [progress, setCompaction, t]);

  if (!usage || measured == null || measuredPercent == null || !limit) return null;

  const compacting = compaction?.active === true;
  const failed = compaction?.stage === 'error';
  const canCompact = !isStreaming && !compacting;
  const inputTokens = usage.input_tokens ?? 0;
  const cacheRead = usage.cache_read_tokens ?? 0;
  const cacheWrite = usage.cache_write_tokens ?? 0;
  // Cache tokens are a share of input, not of the window: pydantic-ai normalizes
  // input_tokens to include cache reads and writes on every provider.
  const shareOfInput = (n: number): string | null =>
    inputTokens > 0 ? formatPercent(Math.min(100, (n / inputTokens) * 100)) : null;

  return (
    <section className="mb-4 space-y-2 text-xs">
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono tabular-nums text-neutral-700 dark:text-neutral-200">
          {formatTokens(measured)} / {formatTokens(limit)}
          <span className="ml-1.5 font-bold">{formatPercent(measuredPercent)}</span>
        </span>
        <button
          type="button"
          onClick={() => void compact(chatId)}
          disabled={!canCompact}
          title={canCompact ? t('contextPanel.compactNow') : t('contextPanel.compactUnavailable')}
          className={`rounded border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
            measuredPercent >= 80
              ? 'border-brutal-red text-brutal-red hover:bg-red-50 dark:hover:bg-red-950'
              : 'border-neutral-300 text-neutral-600 hover:bg-neutral-100 dark:border-zinc-600 dark:text-neutral-300 dark:hover:bg-zinc-800'
          }`}
        >
          {compacting ? t('contextPanel.compacting') : t('contextPanel.compact')}
        </button>
      </div>
      {compaction && (
        <div
          className={`overflow-hidden rounded border text-[11px] ${failed ? 'border-brutal-red text-brutal-red' : 'border-neutral-200 text-neutral-600 dark:border-zinc-700 dark:text-neutral-300'}`}
        >
          <div className="flex items-center gap-1.5 px-2 py-1">
            {compacting && <CompactionCube size={14} />}
            <span className="min-w-0 flex-1">{compaction.label}</span>
          </div>
          {compacting && <CompactionSweep className="text-neutral-500 dark:text-neutral-400" />}
        </div>
      )}
      <div className="font-mono text-[11px]">
        <StatRow label={t('contextPanel.input')} value={inputTokens} />
        <StatRow label={t('contextPanel.output')} value={usage.output_tokens ?? 0} />
        {cacheRead > 0 && (
          <StatRow
            label={t('contextPanel.cacheRead')}
            value={cacheRead}
            share={shareOfInput(cacheRead)}
            valueClass="text-green-600 dark:text-green-400"
            title={t('contextPanel.cacheShareHint')}
          />
        )}
        {cacheWrite > 0 && (
          <StatRow
            label={t('contextPanel.cacheWrite')}
            value={cacheWrite}
            share={shareOfInput(cacheWrite)}
            valueClass="text-blue-500 dark:text-blue-400"
            title={t('contextPanel.cacheShareHint')}
          />
        )}
        {usage.requests > 1 && (
          <div className="flex justify-between gap-3 py-0.5 text-neutral-500 dark:text-neutral-400">
            <span>{t('contextPanel.apiRequests')}</span>
            <span className="tabular-nums">{usage.requests}</span>
          </div>
        )}
      </div>
    </section>
  );
}
