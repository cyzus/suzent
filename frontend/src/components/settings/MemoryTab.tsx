import React from 'react';
import { open } from '@tauri-apps/plugin-dialog';

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
