import React, { useEffect } from 'react';
import { useSkills } from '../../hooks/useSkills';
import { MarkdownRenderer } from '../chat/MarkdownRenderer';
import { useI18n } from '../../i18n';

export const SkillsView: React.FC = () => {
    const { skills, loading, error, loadSkills, reload, toggle } = useSkills();
    const { t } = useI18n();

    useEffect(() => {
        loadSkills();
    }, []);

    if (loading && skills.length === 0) {
        return (
            <div className="h-full w-full flex flex-col items-center justify-center p-8">
                <div className="border-3 border-brutal-black bg-white p-6 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
                    <h2 className="font-brutal text-2xl uppercase mb-4 animate-pulse">{t('skills.loading')}</h2>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="p-6">
                <div className="border-3 border-brutal-red bg-white p-6 shadow-brutal">
                    <h3 className="font-brutal text-xl text-brutal-red mb-2 uppercase">{t('skills.errorTitle')}</h3>
                    <p className="font-mono text-sm">{error}</p>
                    <button
                        onClick={() => loadSkills()}
                        className="mt-4 px-4 py-2 border-2 border-brutal-black font-bold uppercase hover:bg-neutral-100"
                    >
                        {t('skills.retry')}
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="h-full w-full overflow-y-auto px-4 md:px-8 py-8 space-y-8 max-w-7xl mx-auto scrollbar-thin">
            <div className="bg-white p-3 border-3 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] flex justify-between items-center">
                <div>
                    <h2 className="font-brutal text-3xl uppercase tracking-tighter">{t('skills.title')}</h2>
                    <p className="text-sm font-mono text-neutral-600">{t('skills.subtitle')}</p>
                </div>
                <button
                    onClick={() => reload()}
                    title={t('skills.reload')}
                    className="p-2 border-2 border-brutal-black hover:bg-neutral-100 brutal-btn transition-all"
                >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {skills.map(skill => (
                    <div key={skill.name} className={`bg-white border-3 border-brutal-black p-5 shadow-[5px_5px_0px_0px_rgba(0,0,0,1)] transition-all ${!skill.enabled ? 'opacity-75 bg-neutral-50' : ''}`}>
                        <div className="flex justify-between items-start mb-2">
                            <h3 className="font-brutal text-xl uppercase break-all">{skill.name}</h3>
                            <button
                                onClick={() => toggle(skill.name)}
                                className={`w-12 h-6 flex items-center border-2 border-brutal-black p-0.5 transition-colors ${skill.enabled ? 'bg-brutal-black justify-end' : 'bg-white justify-start'}`}
                                title={skill.enabled ? t('skills.disableSkill') : t('skills.enableSkill')}
                            >
                                <div className={`w-4 h-4 border-2 border-brutal-black ${skill.enabled ? 'bg-white' : 'bg-neutral-300'}`} />
                            </button>
                        </div>
                        <div className="mb-4 overflow-hidden text-ellipsis">
                            <p className="font-mono text-[10px] text-neutral-500 bg-neutral-100 p-1 inline-block truncate max-w-full" title={skill.path}>
                                {skill.path}
                            </p>
                        </div>
                        <div className="border-t-2 border-neutral-100 pt-3">
                            <MarkdownRenderer content={skill.description || ''} />
                        </div>
                    </div>
                ))}
                {skills.length === 0 && (
                    <div className="col-span-full text-center border-3 border-dashed border-neutral-300 p-12">
                        <p className="font-mono text-neutral-400 text-lg">{t('skills.emptyTitle')}</p>
                        <p className="text-sm text-neutral-400 mt-2">{t('skills.emptyDesc')}</p>
                    </div>
                )}
            </div>
        </div>
    );
};
