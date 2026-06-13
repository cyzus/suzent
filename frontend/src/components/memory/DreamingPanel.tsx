/**
 * Dreaming Agent panel — live operational dashboard for background memory
 * consolidation. Surfaces backlog progress, per-phase status (ingest + weekly
 * lint), the agent's last-run summary, and a manual RUN NOW trigger.
 *
 * Lives in the Memory view (next to the daily logs it consumes and the memory
 * file it produces), NOT in Settings — it is a watch/trigger surface, not config.
 */
import React from 'react';

import { useDreamStatus } from '../../hooks/useDreamStatus';
import { useI18n } from '../../i18n';
import { MarkdownRenderer } from '../chat/MarkdownRenderer';

type StatAccent = 'green' | 'amber' | 'neutral';

const STAT_ACCENT_BAR: Record<StatAccent, string> = {
    green: 'bg-brutal-green',
    amber: 'bg-brutal-yellow',
    neutral: 'bg-neutral-300 dark:bg-zinc-600',
};

/** A single labelled metric tile with a colored top accent bar. */
function StatCard({ label, value, accent }: { label: string; value: string; accent: StatAccent }): React.ReactElement {
    return (
        <div className="border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 overflow-hidden">
            <div className={`h-1 ${STAT_ACCENT_BAR[accent]}`} />
            <div className="p-3">
                <div className="text-[10px] font-bold uppercase tracking-wide text-neutral-500 dark:text-neutral-400 leading-tight">{label}</div>
                <div className="font-mono text-sm font-bold mt-1.5 truncate" title={value}>{value}</div>
            </div>
        </div>
    );
}

export function DreamingPanel(): React.ReactElement {
    const { t } = useI18n();
    const { status: dreamStatus, loading: dreamLoading, runningNow, error: dreamError, refresh: refreshDreamStatus, runNow } = useDreamStatus();

    const formatDate = (value?: string | null): string => {
        if (!value) return t('settings.memoryConfig.never');
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return t('settings.memoryConfig.never');
        return date.toLocaleString([], {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    };

    const statusLabel = (() => {
        if (dreamLoading && !dreamStatus) return t('settings.memoryConfig.dreamStatus.loading');
        if (dreamError) return t('settings.memoryConfig.dreamStatus.error');
        if (!dreamStatus?.active) return t('settings.memoryConfig.dreamStatus.inactive');
        if (!dreamStatus.enabled) return t('settings.memoryConfig.dreamStatus.disabled');
        if (dreamStatus.phase === 'finalizing') return t('settings.memoryConfig.dreamStatus.finalizing');
        if (dreamStatus.phase === 'queued' || dreamStatus.phase === 'preparing') return t('settings.memoryConfig.dreamStatus.preparing');
        if (dreamStatus.running || runningNow) return t('settings.memoryConfig.dreamStatus.running');
        if ((dreamStatus.pending_count ?? 0) > 0) return t('settings.memoryConfig.dreamStatus.pending');
        return t('settings.memoryConfig.dreamStatus.idle');
    })();

    const statusClass = (() => {
        if (dreamError || dreamStatus?.last_result?.advanced === false) return 'bg-brutal-red text-white';
        if (dreamStatus?.running || runningNow) return 'bg-brutal-blue text-white';
        if ((dreamStatus?.pending_count ?? 0) > 0) return 'bg-brutal-yellow text-brutal-black';
        return 'bg-brutal-green text-brutal-black';
    })();

    // The agent's own summary is markdown prose; the fallbacks are plain status labels.
    const lastResultSummary = dreamStatus?.last_result?.summary?.trim() || null;
    const lastResultLabel = (() => {
        const result = dreamStatus?.last_result;
        if (!result) return t('settings.memoryConfig.noRunsYet');
        if (lastResultSummary) return lastResultSummary;
        if (result.reason) return result.reason;
        if (result.skipped) return t('settings.memoryConfig.lastResultSkipped');
        if (result.advanced) return t('settings.memoryConfig.lastResultAdvanced', { watermark: result.watermark || '—' });
        if (result.advanced === false) return t('settings.memoryConfig.lastResultNotAdvanced');
        return t('settings.memoryConfig.lastResultRan');
    })();

    const pendingDates = dreamStatus?.pending_dates ?? [];
    const pendingCount = dreamStatus?.pending_count ?? 0;
    const canRunDream = !!dreamStatus?.active && !!dreamStatus?.available && !!dreamStatus?.enabled && !dreamStatus?.running && !runningNow;
    const progressPercent = Math.max(0, Math.min(100, dreamStatus?.progress_percent ?? 0));
    const consolidatedCount = dreamStatus?.consolidated_count ?? 0;
    const archiveCount = dreamStatus?.archive_count ?? 0;
    const isBusy = !!dreamStatus?.running || runningNow;
    // Tag the last result with the phase that produced it (ingest vs lint).
    const lastResultPhaseLabel = (() => {
        if (!dreamStatus?.last_result) return null;
        return dreamStatus.last_result.phase === 'lint'
            ? t('settings.memoryConfig.lintPhase')
            : t('settings.memoryConfig.ingestPhase');
    })();

    return (
        <div className="border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-5">
            {/* Header: icon + title + status/actions */}
            <div className="flex items-start justify-between gap-4 mb-6">
                <div className="flex items-start gap-3 min-w-0">
                    <div className="w-10 h-10 flex-shrink-0 grid place-items-center border-2 border-brutal-black bg-brutal-blue text-white">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M20 12.5A8.5 8.5 0 1111.5 4 6.5 6.5 0 0020 12.5z" />
                        </svg>
                    </div>
                    <div className="min-w-0">
                        <h3 className="font-brutal text-xl uppercase tracking-tight leading-tight">{t('settings.memoryConfig.dreamTitle')}</h3>
                        <p className="text-xs text-neutral-600 dark:text-neutral-400 mt-0.5">{t('settings.memoryConfig.dreamDesc')}</p>
                    </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                    <div className={`px-3 py-2 border-2 border-brutal-black font-mono text-xs font-bold uppercase whitespace-nowrap shadow-brutal-sm ${statusClass}`}>
                        {isBusy && <span className="inline-block w-1.5 h-1.5 rounded-full bg-current mr-1.5 align-middle animate-pulse" />}
                        {statusLabel}
                    </div>
                    <button
                        type="button"
                        onClick={() => void refreshDreamStatus()}
                        title={t('common.refresh')}
                        className="p-2 bg-white dark:bg-zinc-700 border-2 border-brutal-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:bg-neutral-100 dark:hover:bg-zinc-600 transition-colors"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                    </button>
                    <button
                        type="button"
                        onClick={() => void runNow()}
                        disabled={!canRunDream}
                        className="px-4 py-2 bg-brutal-green border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
                    >
                        {isBusy ? t('settings.memoryConfig.runningNow') : t('settings.memoryConfig.runNow')}
                    </button>
                </div>
            </div>

            {/* Backlog progress */}
            <div className="mb-5">
                <div className="flex items-baseline justify-between gap-3 mb-2">
                    <div className="text-[10px] font-bold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                        {t('settings.memoryConfig.backlogProgress')}
                    </div>
                    <div className="font-mono text-xs font-bold tabular-nums">
                        <span className={progressPercent >= 100 ? 'text-brutal-green' : ''}>{progressPercent}%</span>
                        <span className="text-neutral-400 dark:text-neutral-500"> · {t('settings.memoryConfig.progressCount', { current: String(consolidatedCount), total: String(archiveCount) })}</span>
                    </div>
                </div>
                <div className="h-4 border-2 border-brutal-black bg-neutral-100 dark:bg-zinc-900 overflow-hidden">
                    <div
                        className={`h-full transition-all duration-500 ${isBusy ? 'bg-brutal-blue animate-pulse' : progressPercent >= 100 ? 'bg-brutal-green' : 'bg-brutal-yellow'}`}
                        style={{ width: `${progressPercent}%` }}
                    />
                </div>
            </div>

            {/* Stat grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <StatCard label={t('settings.memoryConfig.consolidatedThrough')} value={dreamStatus?.watermark || '—'} accent="green" />
                <StatCard label={t('settings.memoryConfig.pendingLogs')} value={String(pendingCount)} accent={pendingCount > 0 ? 'amber' : 'neutral'} />
                <StatCard label={t('settings.memoryConfig.pendingFacts')} value={String(dreamStatus?.pending_facts ?? 0)} accent={(dreamStatus?.pending_facts ?? 0) > 0 ? 'amber' : 'neutral'} />
                <StatCard label={t('settings.memoryConfig.lastRun')} value={formatDate(dreamStatus?.last_finished_at)} accent="neutral" />
            </div>

            {/* Lint phase status strip */}
            {dreamStatus?.lint_enabled && (
                <div className="mt-3 flex items-center gap-2 border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 px-3 py-2">
                    <svg className="w-4 h-4 flex-shrink-0 text-neutral-500 dark:text-neutral-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span className="text-[10px] font-bold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">{t('settings.memoryConfig.lintTitle')}</span>
                    <span className="font-mono text-[11px] text-neutral-500 dark:text-neutral-400">
                        {dreamStatus.lint_min_days ? t('settings.memoryConfig.lintEveryDays', { days: String(dreamStatus.lint_min_days) }) : ''}
                    </span>
                    <span className="ml-auto font-mono text-[11px] font-bold">
                        {dreamStatus.lint_last_run
                            ? `${t('settings.memoryConfig.lintLastRun')}: ${dreamStatus.lint_last_run}`
                            : t('settings.memoryConfig.lintNever')}
                    </span>
                    <span className={`px-2 py-0.5 border-2 border-brutal-black text-[10px] font-bold uppercase ${dreamStatus.lint_due ? 'bg-brutal-yellow text-brutal-black' : 'bg-brutal-green text-brutal-black'}`}>
                        {dreamStatus.lint_due ? t('settings.memoryConfig.lintDue') : t('settings.memoryConfig.lintScheduled')}
                    </span>
                </div>
            )}

            {/* Last result */}
            <div className="mt-4 border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 min-w-0">
                <div className="flex items-center justify-between gap-2 px-3 py-2 border-b-2 border-dashed border-neutral-300 dark:border-zinc-700">
                    <span className="text-[10px] font-bold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">{t('settings.memoryConfig.lastResult')}</span>
                    {lastResultPhaseLabel && (
                        <span className="px-2 py-0.5 border border-brutal-black/40 dark:border-zinc-600 text-[10px] font-bold uppercase text-neutral-500 dark:text-neutral-400">
                            {lastResultPhaseLabel}
                        </span>
                    )}
                </div>
                <div className="p-3">
                    {lastResultSummary ? (
                        <div className="overflow-y-auto max-h-40" title={lastResultSummary}>
                            <MarkdownRenderer content={lastResultSummary} />
                        </div>
                    ) : (
                        <div className="font-mono text-xs font-bold whitespace-pre-wrap break-words">
                            {lastResultLabel}
                        </div>
                    )}
                    {pendingDates.length > 0 && (
                        <div className="font-mono text-[11px] text-neutral-500 dark:text-neutral-400 mt-3 pt-2 border-t border-dashed border-neutral-300 dark:border-zinc-700 truncate">
                            {t('settings.memoryConfig.nextBatch')}: {pendingDates.slice(0, dreamStatus?.max_days ?? 14).join(', ')}
                        </div>
                    )}
                    {dreamError && (
                        <div className="font-mono text-[11px] text-brutal-red mt-2">
                            {dreamError}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
