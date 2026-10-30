/**
 * Organize panel — where the background tidy-up of memory is watched and started.
 *
 * It leads with one plain sentence about where things stand and what happened last
 * time; the numbers behind it (backlog, waiting notes, the periodic check) sit in a
 * collapsed details section for whoever wants them.
 */
import React from 'react';

import { useDreamStatus } from '../../hooks/useDreamStatus';
import { useI18n } from '../../i18n';
import { MarkdownRenderer } from '../chat/MarkdownRenderer';
import { BrutalButton } from '../BrutalButton';
import type { DreamRunResult } from '../../types/memory';

/** The agent's own summary when it wrote one, otherwise a plain stand-in. */
function useResultText(): (result?: DreamRunResult | null) => string | null {
  const { t } = useI18n();
  return (result) => {
    if (!result) return null;
    const summary = result.summary?.trim();
    if (summary) return summary;
    if (result.reason) return result.reason;
    if (result.skipped) return t('memoryView.organize.result.skipped');
    if (result.advanced)
      return t('memoryView.organize.result.advanced', { date: result.watermark || '—' });
    if (result.advanced === false) return t('memoryView.organize.result.nothingChanged');
    return t('memoryView.organize.result.done');
  };
}

function DetailRow({ label, value }: { label: string; value: string }): React.ReactElement {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5 border-b border-dashed border-neutral-300 dark:border-zinc-700 last:border-b-0">
      <span className="text-xs text-neutral-600 dark:text-neutral-400">{label}</span>
      <span className="font-mono text-xs font-bold text-right">{value}</span>
    </div>
  );
}

export function OrganizePanel(): React.ReactElement {
  const { t } = useI18n();
  const resultText = useResultText();
  const { status, loading, runningIngest, runningLint, error, runIngest, runLint } =
    useDreamStatus();

  const formatWhen = (value?: string | null): string => {
    if (!value) return t('memoryView.organize.never');
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return t('memoryView.organize.never');
    return date.toLocaleString([], {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const isOn = !!status?.active && !!status?.enabled;
  const isBusy = !!status?.running || runningIngest || runningLint;
  const canRun = isOn && !!status?.available && !isBusy;
  const canCheck = canRun && !!status?.lint_enabled;
  const pendingDays = status?.pending_count ?? 0;
  const organizedThrough = status?.watermark;

  const headline = (() => {
    if (loading && !status) return t('memoryView.organize.loading');
    if (!isOn) return t('memoryView.organize.off');
    if (isBusy) return t('memoryView.organize.running');
    if (pendingDays > 0) return t('memoryView.organize.waiting', { count: String(pendingDays) });
    return t('memoryView.organize.caughtUp');
  })();

  const lastText = resultText(status?.last_ingest_result);
  const lastCheckText = resultText(status?.last_lint_result);
  const progressPercent = Math.max(0, Math.min(100, status?.progress_percent ?? 0));

  return (
    <div className="space-y-4">
      <div className="border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h3 className="font-brutal text-xl uppercase tracking-tight leading-tight">
              {headline}
            </h3>
            <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
              {organizedThrough
                ? t('memoryView.organize.through', { date: organizedThrough })
                : t('memoryView.organize.intro')}
            </p>
          </div>
          <BrutalButton
            type="button"
            variant="success"
            onClick={() => void runIngest()}
            disabled={!canRun}
            className="shrink-0 px-4 py-2 text-xs uppercase whitespace-nowrap disabled:opacity-40"
          >
            {runningIngest || status?.phase === 'running_agent'
              ? t('memoryView.organize.runningButton')
              : t('memoryView.organize.runNow')}
          </BrutalButton>
        </div>

        <div className="mt-5 border-t-2 border-brutal-black pt-4">
          <div className="mb-2 flex items-baseline justify-between gap-3">
            <span className="text-[10px] font-bold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              {t('memoryView.organize.lastTime')}
            </span>
            <span className="font-mono text-[10px] font-bold text-neutral-500 dark:text-neutral-400">
              {formatWhen(status?.last_ingest_finished_at)}
            </span>
          </div>
          {lastText ? (
            <div className="max-h-48 overflow-y-auto overflow-x-hidden pr-1 text-sm leading-6 break-words">
              <MarkdownRenderer content={lastText} />
            </div>
          ) : (
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              {t('memoryView.organize.noRunsYet')}
            </p>
          )}
        </div>

        {error && <p className="mt-3 font-mono text-[11px] text-brutal-red">{error}</p>}
      </div>

      <details className="group border-3 border-brutal-black bg-white dark:bg-zinc-800">
        <summary className="cursor-pointer select-none px-4 py-3 text-xs font-bold uppercase tracking-wide">
          {t('memoryView.organize.details')}
        </summary>
        <div className="grid grid-cols-1 gap-6 border-t-2 border-brutal-black p-4 lg:grid-cols-2">
          <section>
            <h4 className="mb-2 text-sm font-black uppercase">
              {t('memoryView.organize.backlogTitle')}
            </h4>
            <div className="mb-3 h-3 border-2 border-brutal-black bg-neutral-100 dark:bg-zinc-900 overflow-hidden">
              <div
                className={`h-full transition-all duration-500 ${
                  progressPercent >= 100 ? 'bg-brutal-green' : 'bg-brutal-yellow'
                }`}
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <DetailRow
              label={t('memoryView.organize.daysOrganized')}
              value={t('memoryView.organize.daysOf', {
                done: String(status?.consolidated_count ?? 0),
                total: String(status?.archive_count ?? 0),
              })}
            />
            <DetailRow label={t('memoryView.organize.daysWaiting')} value={String(pendingDays)} />
            <DetailRow
              label={t('memoryView.organize.notesWaiting')}
              value={String(status?.pending_facts ?? 0)}
            />
            <DetailRow
              label={t('memoryView.organize.repeatsWaiting')}
              value={String(status?.pending_confirmations ?? 0)}
            />
            {(status?.pending_dates?.length ?? 0) > 0 && (
              <DetailRow
                label={t('memoryView.organize.nextUp')}
                value={(status?.pending_dates ?? []).slice(0, status?.max_days ?? 14).join(', ')}
              />
            )}
          </section>

          <section>
            <div className="mb-2 flex items-start justify-between gap-3">
              <div>
                <h4 className="text-sm font-black uppercase">
                  {t('memoryView.organize.checkTitle')}
                </h4>
                <p className="text-xs text-neutral-600 dark:text-neutral-400">
                  {t('memoryView.organize.checkDesc')}
                </p>
              </div>
              <BrutalButton
                type="button"
                size="xs"
                onClick={() => void runLint()}
                disabled={!canCheck}
                className="shrink-0 disabled:opacity-40"
              >
                {runningLint || status?.phase === 'running_lint'
                  ? t('memoryView.organize.runningButton')
                  : t('memoryView.organize.checkNow')}
              </BrutalButton>
            </div>
            <DetailRow
              label={t('memoryView.organize.lastChecked')}
              value={status?.lint_last_run || t('memoryView.organize.never')}
            />
            <DetailRow
              label={t('memoryView.organize.checkStatus')}
              value={
                status?.lint_due
                  ? t('memoryView.organize.checkDue')
                  : t('memoryView.organize.checkUpToDate')
              }
            />
            {!!status?.lint_min_days && (
              <DetailRow
                label={t('memoryView.organize.checkEvery')}
                value={t('memoryView.organize.everyDays', { days: String(status.lint_min_days) })}
              />
            )}
            {lastCheckText && (
              <div className="mt-3 max-h-40 overflow-y-auto overflow-x-hidden pr-1 text-xs leading-5 break-words">
                <MarkdownRenderer content={lastCheckText} />
              </div>
            )}
          </section>
        </div>
      </details>
    </div>
  );
}
