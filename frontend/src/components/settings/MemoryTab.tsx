import React from 'react';
import { open } from '@tauri-apps/plugin-dialog';

import { useDreamStatus } from '../../hooks/useDreamStatus';
import { useI18n } from '../../i18n';

interface MemoryTabProps {
    globalNotebookHostPath: string;
    onGlobalNotebookHostPathChange: (path: string) => void;
}

export function MemoryTab({
    globalNotebookHostPath,
    onGlobalNotebookHostPathChange,
}: MemoryTabProps): React.ReactElement {
    const { t } = useI18n();
    const { status: dreamStatus, loading: dreamLoading, runningNow, error: dreamError, refresh: refreshDreamStatus, runNow } = useDreamStatus();

    const pickDirectory = async () => {
        try {
            const selected = await open({
                directory: true,
                multiple: false,
            });
            if (!selected || Array.isArray(selected)) return;
            onGlobalNotebookHostPathChange(selected);
        } catch (error) {
            console.error('Failed to pick global notebook folder', error);
        }
    };

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

    const lastResultLabel = (() => {
        const result = dreamStatus?.last_result;
        if (!result) return t('settings.memoryConfig.noRunsYet');
        if (result.reason) return result.reason;
        if (result.skipped) return t('settings.memoryConfig.lastResultSkipped');
        if (result.advanced) return t('settings.memoryConfig.lastResultAdvanced', { watermark: result.watermark || '—' });
        if (result.advanced === false) return t('settings.memoryConfig.lastResultNotAdvanced');
        return t('settings.memoryConfig.lastResultRan');
    })();

    const pendingDates = dreamStatus?.pending_dates ?? [];
    const canRunDream = !!dreamStatus?.active && !!dreamStatus?.available && !!dreamStatus?.enabled && !dreamStatus?.running && !runningNow;
    const progressPercent = Math.max(0, Math.min(100, dreamStatus?.progress_percent ?? 0));
    const consolidatedCount = dreamStatus?.consolidated_count ?? 0;
    const archiveCount = dreamStatus?.archive_count ?? 0;

    return (
        <div className="space-y-6">
            <h2 className="text-3xl font-brutal font-black uppercase text-brutal-black dark:text-white">{t('settings.memoryConfig.title')}</h2>

            {/* Model roles redirect notice */}
            <div className="bg-brutal-yellow/20 border-2 border-brutal-black p-4 flex items-start gap-3">
                <svg className="w-5 h-5 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <p className="text-sm font-bold">{t('settings.memoryConfig.modelRolesHint')}</p>
            </div>

            <div className="bg-white dark:bg-zinc-800 dark:text-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6">
                <div className="flex items-start justify-between gap-4 mb-6">
                    <div className="flex items-start gap-4">
                        <div className="w-12 h-12 bg-brutal-blue border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                            <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M20 12.5A8.5 8.5 0 1111.5 4 6.5 6.5 0 0020 12.5z" />
                            </svg>
                        </div>
                        <div>
                            <h3 className="text-xl font-bold uppercase">{t('settings.memoryConfig.dreamTitle')}</h3>
                            <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">{t('settings.memoryConfig.dreamDesc')}</p>
                        </div>
                    </div>
                    <div className={`px-4 py-2 border-2 border-brutal-black font-mono text-xs font-bold uppercase whitespace-nowrap shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] ${statusClass}`}>
                        {statusLabel}
                    </div>
                </div>

                <div className="mb-5">
                    <div className="flex items-center justify-between gap-3 mb-2">
                        <div className="text-[10px] font-bold uppercase text-neutral-500 dark:text-neutral-400">
                            {t('settings.memoryConfig.backlogProgress')}
                        </div>
                        <div className="font-mono text-xs font-bold">
                            {t('settings.memoryConfig.progressCount', { current: String(consolidatedCount), total: String(archiveCount) })}
                        </div>
                    </div>
                    <div className="h-5 border-2 border-brutal-black bg-neutral-100 dark:bg-zinc-900 overflow-hidden">
                        <div
                            className={`h-full transition-all duration-500 ${dreamStatus?.running || runningNow ? 'bg-brutal-blue animate-pulse' : progressPercent >= 100 ? 'bg-brutal-green' : 'bg-brutal-yellow'}`}
                            style={{ width: `${progressPercent}%` }}
                        />
                    </div>
                    <div className="mt-1 font-mono text-[11px] text-neutral-500 dark:text-neutral-400">
                        {progressPercent}% {t('settings.memoryConfig.complete')}
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                    <div className="border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 p-3">
                        <div className="text-[10px] font-bold uppercase text-neutral-500">{t('settings.memoryConfig.consolidatedThrough')}</div>
                        <div className="font-mono text-sm font-bold mt-1">{dreamStatus?.watermark || '—'}</div>
                    </div>
                    <div className="border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 p-3">
                        <div className="text-[10px] font-bold uppercase text-neutral-500">{t('settings.memoryConfig.pendingLogs')}</div>
                        <div className="font-mono text-sm font-bold mt-1">{dreamStatus?.pending_count ?? 0}</div>
                    </div>
                    <div className="border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 p-3">
                        <div className="text-[10px] font-bold uppercase text-neutral-500">{t('settings.memoryConfig.pendingFacts')}</div>
                        <div className="font-mono text-sm font-bold mt-1">{dreamStatus?.pending_facts ?? 0}</div>
                    </div>
                    <div className="border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 p-3">
                        <div className="text-[10px] font-bold uppercase text-neutral-500">{t('settings.memoryConfig.lastRun')}</div>
                        <div className="font-mono text-sm font-bold mt-1">{formatDate(dreamStatus?.last_finished_at)}</div>
                    </div>
                </div>

                <div className="mt-4 grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3 items-stretch">
                    <div className="border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 p-3 min-w-0">
                        <div className="text-[10px] font-bold uppercase text-neutral-500">{t('settings.memoryConfig.lastResult')}</div>
                        <div className="font-mono text-xs font-bold mt-1 truncate">{lastResultLabel}</div>
                        {pendingDates.length > 0 && (
                            <div className="font-mono text-[11px] text-neutral-500 dark:text-neutral-400 mt-2 truncate">
                                {t('settings.memoryConfig.nextBatch')}: {pendingDates.slice(0, dreamStatus?.max_days ?? 14).join(', ')}
                            </div>
                        )}
                        {dreamError && (
                            <div className="font-mono text-[11px] text-brutal-red mt-2 truncate">
                                {dreamError}
                            </div>
                        )}
                    </div>
                    <div className="flex gap-2">
                        <button
                            type="button"
                            onClick={() => void refreshDreamStatus()}
                            className="px-4 py-2 bg-white dark:bg-zinc-700 border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:bg-neutral-100 dark:hover:bg-zinc-600 transition-colors"
                        >
                            {t('common.refresh')}
                        </button>
                        <button
                            type="button"
                            onClick={() => void runNow()}
                            disabled={!canRunDream}
                            className="px-4 py-2 bg-brutal-green border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                            {runningNow || dreamStatus?.running ? t('settings.memoryConfig.runningNow') : t('settings.memoryConfig.runNow')}
                        </button>
                    </div>
                </div>
            </div>

            <div className="bg-white dark:bg-zinc-800 dark:text-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6">
                <div className="flex items-start gap-4 mb-6">
                    <div className="w-12 h-12 bg-brutal-blue border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                        <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.384-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" /></svg>
                    </div>
                    <div>
                        <h3 className="text-xl font-bold uppercase">{t('settings.memoryConfig.systemConfigTitle')}</h3>
                        <p className="text-sm text-neutral-600 mt-1">{t('settings.memoryConfig.systemConfigDesc')}</p>
                    </div>
                </div>

                <div className="mt-6 pt-6 border-t-2 border-dashed border-brutal-black space-y-3">
                    <div>
                        <h3 className="text-lg font-bold uppercase">{t('settings.sandbox.title')}</h3>
                        <p className="text-sm text-neutral-600 mt-1">{t('settings.sandbox.subtitle')}</p>
                    </div>

                    <div className="text-xs font-bold uppercase text-neutral-500">{t('settings.sandbox.mountTarget')}</div>
                    <div className="font-mono text-sm border-2 border-brutal-black bg-brutal-yellow/30 px-3 py-2 inline-block">
                        /mnt/notebook
                    </div>

                    <div>
                        <div className="text-xs font-bold uppercase text-neutral-500 mb-1">{t('settings.sandbox.hostFolder')}</div>
                        <div className="font-mono text-xs border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 px-3 py-2 break-all min-h-[2.25rem]">
                            {globalNotebookHostPath || t('settings.sandbox.notConfigured')}
                        </div>
                    </div>

                    <div className="flex gap-2">
                        <button
                            type="button"
                            onClick={pickDirectory}
                            className="px-4 py-2 bg-brutal-green border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:brightness-110 transition-colors"
                        >
                            {t('settings.sandbox.chooseFolder')}
                        </button>
                    </div>

                    <div className="text-xs text-neutral-600 dark:text-neutral-400">
                        {t('settings.sandbox.saveHint')}
                    </div>
                </div>
            </div>
        </div>
    );
}
