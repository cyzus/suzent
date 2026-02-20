import React from 'react';

import { useI18n } from '../../i18n';
import { BrutalSelect } from '../BrutalSelect';

interface MemoryTabProps {
    embeddingModels: string[];
    models: string[];
    selectedEmbeddingModel: string;
    selectedExtractionModel: string;
    onEmbeddingModelChange: (model: string) => void;
    onExtractionModelChange: (model: string) => void;
}

export function MemoryTab({
    embeddingModels,
    models,
    selectedEmbeddingModel,
    selectedExtractionModel,
    onEmbeddingModelChange,
    onExtractionModelChange,
}: MemoryTabProps): React.ReactElement {
    const { t } = useI18n();
    return (
        <div className="space-y-6">
            <h2 className="text-3xl font-brutal font-black uppercase text-brutal-black">{t('settings.memoryConfig.title')}</h2>
            <div className="bg-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6">
                <div className="flex items-start gap-4 mb-6">
                    <div className="w-12 h-12 bg-brutal-blue border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                        <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.384-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" /></svg>
                    </div>
                    <div>
                        <h3 className="text-xl font-bold uppercase">{t('settings.memoryConfig.systemConfigTitle')}</h3>
                        <p className="text-sm text-neutral-600 mt-1">{t('settings.memoryConfig.systemConfigDesc')}</p>
                    </div>
                </div>

                <div className="grid grid-cols-1 gap-6">
                    {/* Extraction Model */}
                    <div className="space-y-2">
                        <label className="text-sm font-bold uppercase text-neutral-800 flex justify-between">
                            {t('settings.memoryConfig.extractionModelLabel')}
                            <span className="text-[10px] bg-neutral-200 px-2 py-0.5 border border-brutal-black">{t('settings.memoryConfig.extractionModelHint')}</span>
                        </label>
                        <BrutalSelect
                            value={selectedExtractionModel}
                            onChange={onExtractionModelChange}
                            options={[
                                { value: '', label: t('settings.memoryConfig.extractionModelHeuristics') },
                                ...models.map((model) => ({ value: model, label: model }))
                            ]}
                            placeholder={t('settings.memoryConfig.extractionModelPlaceholder')}
                            className="z-20"
                        />
                    </div>

                    {/* Embedding Model */}
                    <div className="space-y-2">
                        <label className="text-sm font-bold uppercase text-neutral-800 flex justify-between">
                            {t('settings.memoryConfig.embeddingModelLabel')}
                            <span className="text-[10px] bg-neutral-200 px-2 py-0.5 border border-brutal-black">{t('settings.memoryConfig.embeddingModelHint')}</span>
                        </label>
                        <BrutalSelect
                            value={selectedEmbeddingModel}
                            onChange={onEmbeddingModelChange}
                            options={[
                                { value: '', label: t('settings.memoryConfig.embeddingModelNoneDefault') },
                                ...embeddingModels.map((model) => ({ value: model, label: model }))
                            ]}
                            placeholder={t('settings.memoryConfig.embeddingModelPlaceholder')}
                            className="z-10"
                        />
                    </div>
                </div>
            </div>
        </div>
    );
}
