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
import type { DreamRunResult } from '../../types/memory';

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

function LastResultBox({
    title,
    result,
    finishedAt,
    fallback,
    formatDate,
    actionLabel,
    actionBusyLabel,
    onRun,
    disabled,
    busy,
    children,
}: {
    title: string;
    result?: DreamRunResult | null;
    finishedAt?: string | null;
    fallback: string;
    formatDate: (value?: string | null) => string;
    actionLabel: string;
    actionBusyLabel: string;
    onRun: () => void;
    disabled: boolean;
    busy: boolean;
    children?: React.ReactNode;
}): React.ReactElement {
    const { t } = useI18n();
    const summary = result?.summary?.trim() || null;
    const label = (() => {
        if (!result) return fallback;
        if (summary) return summary;
        if (result.reason) return result.reason;
        if (result.skipped) return t('settings.memoryConfig.lastResultSkipped');
        if (result.advanced) return t('settings.memoryConfig.lastResultAdvanced', { watermark: result.watermark || '—' });
        if (result.advanced === false) return t('settings.memoryConfig.lastResultNotAdvanced');
        return t('settings.memoryConfig.lastResultRan');
    })();

    return (
        <div className="border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 min-w-0 h-full flex flex-col">
            <div className="px-3 py-3 border-b-2 border-brutal-black">
                <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                        <div className="text-sm font-black uppercase tracking-wide leading-tight truncate">{title}</div>
                    </div>
                    <button
                        type="button"
                        onClick={onRun}
                        disabled={disabled}
                        className="px-3 py-2 bg-brutal-green border-2 border-brutal-black font-bold uppercase text-[11px] shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed transition-colors whitespace-nowrap shrink-0"
                    >
                        {busy ? actionBusyLabel : actionLabel}
                    </button>
                </div>
                {children && (
                    <div className="mt-3">
                        {children}
                    </div>
                )}
            </div>
            <div className="flex items-center justify-between gap-3 px-3 py-2 border-b-2 border-dashed border-neutral-300 dark:border-zinc-700">
                <span className="text-[10px] font-bold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">{t('settings.memoryConfig.lastResult')}</span>
                <span className="font-mono text-[10px] font-bold text-neutral-500 dark:text-neutral-400 shrink-0">{formatDate(finishedAt)}</span>
            </div>
            <div className="p-3 min-h-0 flex-1">
                {summary ? (
                    <div className="h-44 overflow-y-auto overflow-x-hidden pr-1 text-xs leading-5 break-words" title={summary}>
                        <MarkdownRenderer content={summary} streamingLite />
                    </div>
                ) : (
                    <div className="h-44 font-mono text-xs font-bold whitespace-pre-wrap break-words flex items-start">
                        {label}
                    </div>
                )}
            </div>
        </div>
    );
}

export function DreamingPanel(): React.ReactElement {
    const { t } = useI18n();
    const {
        status: dreamStatus,
        loading: dreamLoading,
        runningIngest,
        runningLint,
        error: dreamError,
        refresh: refreshDreamStatus,
        runIngest,
        runLint,
    } = useDreamStatus();

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
        if (dreamStatus.running || runningIngest || runningLint) return t('settings.memoryConfig.dreamStatus.running');
        if ((dreamStatus.pending_count ?? 0) > 0) return t('settings.memoryConfig.dreamStatus.pending');
        return t('settings.memoryConfig.dreamStatus.idle');
    })();

    const statusClass = (() => {
        if (dreamError || dreamStatus?.last_result?.advanced === false) return 'bg-brutal-red text-white';
        if (dreamStatus?.running || runningIngest || runningLint) return 'bg-brutal-blue text-white';
        if ((dreamStatus?.pending_count ?? 0) > 0) return 'bg-brutal-yellow text-brutal-black';
        return 'bg-brutal-green text-brutal-black';
    })();

    const pendingDates = dreamStatus?.pending_dates ?? [];
    const pendingCount = dreamStatus?.pending_count ?? 0;
    const canRunDream = !!dreamStatus?.active && !!dreamStatus?.available && !!dreamStatus?.enabled && !dreamStatus?.running && !runningIngest && !runningLint;
    const canRunLint = canRunDream && !!dreamStatus?.lint_enabled;
    const progressPercent = Math.max(0, Math.min(100, dreamStatus?.progress_percent ?? 0));
    const consolidatedCount = dreamStatus?.consolidated_count ?? 0;
    const archiveCount = dreamStatus?.archive_count ?? 0;
    const isBusy = !!dreamStatus?.running || runningIngest || runningLint;
    const isIngestBusy = runningIngest || dreamStatus?.phase === 'running_agent';
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
                        className={`h-full transition-all duration-500 ${isIngestBusy ? 'bg-brutal-blue animate-pulse' : progressPercent >= 100 ? 'bg-brutal-green' : 'bg-brutal-yellow'}`}
                        style={{ width: `${progressPercent}%` }}
                    />
                </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-stretch">
                <LastResultBox
                    title={t('settings.memoryConfig.ingestPhase')}
                    result={dreamStatus?.last_ingest_result}
                    finishedAt={dreamStatus?.last_ingest_finished_at}
                    fallback={t('settings.memoryConfig.noRunsYet')}
                    formatDate={formatDate}
                    actionLabel={t('settings.memoryConfig.runIngest')}
                    actionBusyLabel={t('settings.memoryConfig.runningNow')}
                    onRun={() => void runIngest()}
                    disabled={!canRunDream}
                    busy={runningIngest || (dreamStatus?.phase === 'running_agent')}
                >
                    <div className="grid grid-cols-3 gap-2">
                        <StatCard label={t('settings.memoryConfig.consolidatedThrough')} value={dreamStatus?.watermark || '—'} accent="green" />
                        <StatCard label={t('settings.memoryConfig.pendingLogs')} value={String(pendingCount)} accent={pendingCount > 0 ? 'amber' : 'neutral'} />
                        <StatCard label={t('settings.memoryConfig.pendingFacts')} value={String(dreamStatus?.pending_facts ?? 0)} accent={(dreamStatus?.pending_facts ?? 0) > 0 ? 'amber' : 'neutral'} />
                    </div>
                </LastResultBox>
                <LastResultBox
                    title={t('settings.memoryConfig.lintPhase')}
                    result={dreamStatus?.last_lint_result}
                    finishedAt={dreamStatus?.last_lint_finished_at}
                    fallback={t('settings.memoryConfig.noRunsYet')}
                    formatDate={formatDate}
                    actionLabel={t('settings.memoryConfig.runLint')}
                    actionBusyLabel={t('settings.memoryConfig.runningNow')}
                    onRun={() => void runLint()}
                    disabled={!canRunLint}
                    busy={runningLint || (dreamStatus?.phase === 'running_lint')}
                >
                    <div className="grid grid-cols-3 gap-2">
                        <StatCard
                            label={t('settings.memoryConfig.lintLastRun')}
                            value={dreamStatus?.lint_last_run || t('settings.memoryConfig.lintNever')}
                            accent="neutral"
                        />
                        <StatCard
                            label={t('settings.memoryConfig.lintTitle')}
                            value={dreamStatus?.lint_due ? t('settings.memoryConfig.lintDue') : t('settings.memoryConfig.lintScheduled')}
                            accent={dreamStatus?.lint_due ? 'amber' : 'green'}
                        />
                        <StatCard
                            label={t('settings.memoryConfig.lintEvery')}
                            value={dreamStatus?.lint_min_days ? t('settings.memoryConfig.lintEveryDays', { days: String(dreamStatus.lint_min_days) }) : '—'}
                            accent="neutral"
                        />
                    </div>
                </LastResultBox>
            </div>
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
    );
}
