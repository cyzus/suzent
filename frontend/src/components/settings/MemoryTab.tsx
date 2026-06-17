import React from 'react';
import { open } from '@tauri-apps/plugin-dialog';

import { useI18n } from '../../i18n';
import { SettingsHeader } from './SettingsHeader';
import { SettingsCard, SectionCardHeader } from './SettingsCard';
import { BrutalOnOff } from '../BrutalOnOff';
import { BrutalButton } from '../BrutalButton';

interface MemoryTabProps {
    globalNotebookHostPath: string;
    onGlobalNotebookHostPathChange: (path: string) => void;
    memoryEnabled: boolean;
    onMemoryEnabledChange: (enabled: boolean) => void;
    /** Model assigned to the "embedding" role (Model Roles tab). */
    embeddingModel?: string;
    /** Model assigned to the "cheap" role — used for memory extraction. */
    cheapModel?: string;
    /** Navigate the settings modal to the Model Roles tab. */
    onOpenModelRoles?: () => void;
}

export function MemoryTab({
    globalNotebookHostPath,
    onGlobalNotebookHostPathChange,
    memoryEnabled,
    onMemoryEnabledChange,
    embeddingModel,
    cheapModel,
    onOpenModelRoles,
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
            <SettingsHeader title={t('settings.memoryConfig.title')} subtitle={t('settings.memoryConfig.subtitle')} />

            {/* Global memory enable toggle */}
            <SettingsCard>
                <div className="flex items-center justify-between gap-4">
                    <div>
                        <h3 className="text-base font-bold uppercase">{t('settings.memoryConfig.globalMemory')}</h3>
                        <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">
                            {memoryEnabled ? t('config.memory.enabledDesc') : t('config.memory.disabledDesc')}
                        </p>
                    </div>
                    <BrutalOnOff checked={memoryEnabled} onChange={onMemoryEnabledChange} />
                </div>

                <div className="mt-4 pt-4 border-t-2 border-dashed border-brutal-black dark:border-zinc-600">
                    <div className="flex items-baseline justify-between gap-2 mb-2">
                        <span className="text-xs font-bold uppercase text-neutral-500 dark:text-neutral-400">{t('settings.memoryConfig.modelsLabel')}</span>
                        {onOpenModelRoles && (
                            <button
                                type="button"
                                onClick={onOpenModelRoles}
                                className="group inline-flex items-center gap-1.5 px-2 py-1 text-[10px] font-bold uppercase tracking-wide border-2 border-brutal-black bg-brutal-yellow text-brutal-black brutal-btn"
                            >
                                {t('settings.memoryConfig.editInModelRoles')}
                                <svg className="w-3 h-3 transition-transform group-hover:translate-x-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                                </svg>
                            </button>
                        )}
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <div className="text-[10px] font-bold uppercase text-neutral-500 dark:text-neutral-400 mb-1">{t('settings.memoryConfig.embeddingModelLabel')}</div>
                            <div className="font-mono text-xs border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 px-3 py-2 break-all min-h-[2.25rem]">
                                {embeddingModel || t('settings.memoryConfig.modelNotConfigured')}
                            </div>
                        </div>
                        <div>
                            <div className="text-[10px] font-bold uppercase text-neutral-500 dark:text-neutral-400 mb-1">{t('settings.memoryConfig.extractionModelLabel')}</div>
                            <div className="font-mono text-xs border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 px-3 py-2 break-all min-h-[2.25rem]">
                                {cheapModel || t('settings.memoryConfig.modelNotConfigured')}
                            </div>
                        </div>
                    </div>
                </div>
            </SettingsCard>

            <SettingsCard>
                <SectionCardHeader
                    iconTone="blue"
                    icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.384-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" /></svg>}
                    title={t('settings.memoryConfig.systemConfigTitle')}
                    description={t('settings.memoryConfig.systemConfigDesc')}
                />

                <div className="mt-6 pt-6 border-t-2 border-dashed border-brutal-black dark:border-zinc-600 space-y-3">
                    <div>
                        <h3 className="text-lg font-bold uppercase">{t('settings.sandbox.title')}</h3>
                        <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">{t('settings.sandbox.subtitle')}</p>
                    </div>

                    <div className="text-xs font-bold uppercase text-neutral-500 dark:text-neutral-400">{t('settings.sandbox.mountTarget')}</div>
                    <div className="font-mono text-sm border-2 border-brutal-black bg-brutal-yellow/30 px-3 py-2 inline-block">
                        /mnt/notebook
                    </div>

                    <div>
                        <div className="text-xs font-bold uppercase text-neutral-500 dark:text-neutral-400 mb-1">{t('settings.sandbox.hostFolder')}</div>
                        <div className="font-mono text-xs border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 px-3 py-2 break-all min-h-[2.25rem]">
                            {globalNotebookHostPath || t('settings.sandbox.notConfigured')}
                        </div>
                    </div>

                    <div className="flex gap-2">
                        <BrutalButton
                            type="button"
                            variant="success"
                            onClick={pickDirectory}
                            className="px-4 py-2 text-xs uppercase"
                        >
                            {t('settings.sandbox.chooseFolder')}
                        </BrutalButton>
                    </div>

                    <div className="text-xs text-neutral-600 dark:text-neutral-400">
                        {t('settings.sandbox.saveHint')}
                    </div>
                </div>
            </SettingsCard>
        </div>
    );
}
