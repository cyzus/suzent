import React from 'react';
import type { Plan } from '../types/api';
import { useI18n } from '../i18n';

interface PlanProgressProps {
    plan: Plan | null;
    isDocked?: boolean;
    onToggleDock?: () => void;
    isExpanded: boolean;
    onToggleExpand: () => void;
    isSidebarOpen?: boolean;
}

const getPlanKey = (plan: Plan) => (plan.id != null ? `plan:${plan.id}` : plan.versionKey);

export const PlanProgress: React.FC<PlanProgressProps> = ({ plan, isDocked, onToggleDock, isExpanded, onToggleExpand, isSidebarOpen }) => {
    const { t } = useI18n();

    if (!plan && !isDocked) {
        return null;
    }

    if (!plan) {
        return <div className="text-xs text-neutral-500 italic p-4 text-center">{t('planProgress.noActivePlan')}</div>;
    }

    const completed = plan.phases.filter(phase => phase.status === 'completed').length;
    const totalPhases = plan.phases.length;

    // Find current phase (first in_progress) or last completed if all done
    const currentPhaseIndex = plan.phases.findIndex(p => p.status === 'in_progress');
    const activePhase = currentPhaseIndex !== -1 ? plan.phases[currentPhaseIndex] : null;
    const isAllCompleted = completed === totalPhases && totalPhases > 0;
    const progress = totalPhases ? completed / totalPhases : 0;

    // Helper for timestamp
    const formatTimestamp = (input?: string | null) => {
        if (!input) return '';
        const date = new Date(input);
        if (Number.isNaN(date.getTime())) return input;
        return date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    };

    if (isDocked) {
        // Detailed View (based on original PlanView)
        return (
            <div className="space-y-3 relative z-0">
                {/* Compact Header Info */}
                <div className="text-[10px] text-brutal-black font-bold uppercase border-b border-brutal-black pb-2">
                    <div className="flex flex-wrap gap-x-2 opacity-70">
                        <span>{plan.id != null ? t('plan.planNumber', { id: plan.id }) : t('plan.plan')}</span>
                        {plan.versionKey && !plan.versionKey.startsWith('snapshot:') && <span>· v{plan.versionKey}</span>}
                        {plan.updatedAt && <span>· {t('plan.updated', { time: formatTimestamp(plan.updatedAt) })}</span>}
                    </div>
                    <div className="mt-1 text-sm font-black leading-tight">
                        {plan.objective}
                    </div>
                </div>

                {/* Progress Bar */}
                <div className="space-y-1">
                    <div className="flex justify-between text-[10px] font-bold uppercase">
                        <span>{t('planProgress.progress')}</span>
                        <span>{Math.round(progress * 100)}%</span>
                    </div>
                    <div className="w-full h-2 bg-neutral-200 border border-brutal-black overflow-hidden relative">
                        <div
                            className="h-full bg-brutal-blue transition-all duration-300 linear will-change-[width]"
                            style={{ width: `${progress * 100}%` }}
                        />
                    </div>
                </div>

                {/* Phase List */}
                <ul className="space-y-2 text-[11px]">
                    {plan.phases.map((phase, index) => {
                        const statusColors: Record<string, string> = {
                            pending: 'bg-white opacity-80',
                            in_progress: 'bg-white border-brutal-blue',
                            completed: 'bg-brutal-green/20',
                        };
                        // Simplified coloring logic for cleaner look
                        const isCompleted = phase.status === 'completed';
                        const isInProgress = phase.status === 'in_progress';

                        return (
                            <li
                                key={phase.id || index}
                                className={`
                            relative border-2 border-brutal-black p-2 transition-all
                            ${isInProgress ? 'bg-white shadow-[2px_2px_0px_0px_#000] translate-y-[2px]' : 'bg-neutral-50 hover:bg-white'}
                            ${isCompleted ? 'opacity-70' : ''}
                          `}
                            >
                                <div className="flex gap-3">
                                    {/* Number Icon */}
                                    <div className={`
                                    shrink-0 w-5 h-5 flex items-center justify-center font-bold text-[10px] border-2 border-brutal-black
                                    ${isCompleted ? 'bg-brutal-green text-brutal-black' : isInProgress ? 'bg-brutal-blue text-white animate-pulse' : 'bg-white text-brutal-black'}
                                `}>
                                        {isCompleted ? '✓' : phase.number}
                                    </div>

                                    <div className="flex-1 min-w-0">
                                        <div className="flex justify-between items-start gap-2">
                                            <div className="font-bold text-xs leading-snug text-brutal-black truncate pr-2">
                                                {phase.title || phase.description}
                                            </div>
                                        </div>

                                        {/* Capabilities/Tags - Compact */}
                                        {phase.capabilities && (
                                            <div className="flex gap-1 mt-1 flex-wrap">
                                                {Array.isArray(phase.capabilities)
                                                    ? phase.capabilities.map((cap: any, idx: number) => <span key={idx} className="text-[9px] leading-none px-1 py-0.5 bg-neutral-200 border border-brutal-black">{String(cap)}</span>)
                                                    : Object.keys(phase.capabilities).map(cap => <span key={cap} className="text-[9px] leading-none px-1 py-0.5 bg-neutral-200 border border-brutal-black">{cap}</span>)
                                                }
                                            </div>
                                        )}

                                        {/* Note */}
                                        {phase.note && <div className="mt-1.5 text-[10px] leading-tight text-neutral-600 italic border-l-2 border-neutral-300 pl-1.5">{phase.note}</div>}
                                    </div>
                                </div>
                            </li>
                        );
                    })}
                </ul>
            </div>
        );
    }

    // Compact View (for inline display)
    return (
        <div className={`bg-white border-3 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] animate-brutal-pop transition-all duration-300 ${isExpanded ? 'p-2 mb-2' : 'p-2 mb-2'}`}>

            {/* Header / Collapsed View */}
            <div className="flex items-center justify-between gap-3">

                {/* Left: Indicator & Title */}
                <div className="flex items-center gap-3 flex-1 overflow-hidden" onClick={() => !isDocked && onToggleExpand()} role="button">
                    <div className="flex items-center gap-2">
                        {isAllCompleted ? (
                            <div className="w-5 h-5 bg-brutal-green border-2 border-brutal-black flex items-center justify-center text-brutal-black font-bold text-xs shrink-0">
                                ✓
                            </div>
                        ) : (
                            <div className="w-5 h-5 bg-brutal-blue border-2 border-brutal-black flex items-center justify-center text-white font-bold text-xs shrink-0 animate-pulse">
                                {currentPhaseIndex !== -1 ? currentPhaseIndex + 1 : '-'}
                            </div>
                        )}

                        <div className="flex flex-col">
                            <span className="font-brutal font-bold uppercase text-xs tracking-wider whitespace-nowrap">
                                {t('planProgress.taskProgress', { completed, total: totalPhases })}
                            </span>
                            {!isExpanded && !isDocked && activePhase && (
                                <span className="text-[10px] font-bold truncate text-neutral-600">
                                    {t('planProgress.current', { title: activePhase.title || activePhase.description })}
                                </span>
                            )}
                        </div>
                    </div>
                </div>

                {/* Right: Controls */}
                <div className="flex items-center gap-2 shrink-0">
                    <button
                        onClick={onToggleDock}
                        className="w-6 h-6 flex items-center justify-center border-2 border-brutal-black hover:bg-neutral-200 transition-colors bg-white text-brutal-black"
                        title={isDocked || isSidebarOpen ? t('sidebar.close') : t('sidebar.open')}
                    >
                        {isDocked || isSidebarOpen ? (
                            /* Point Right (Close/Push Right) */
                            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                            </svg>
                        ) : (
                            /* Point Left (Open/Pull Left) */
                            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
                            </svg>
                        )}
                    </button>

                    {!isDocked && (
                        <button
                            onClick={onToggleExpand}
                            className="w-6 h-6 flex items-center justify-center border-2 border-brutal-black hover:bg-neutral-200 transition-colors"
                        >
                            <svg className={`w-3 h-3 transition-transform duration-200 ${isExpanded ? '' : 'rotate-180'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                            </svg>
                        </button>
                    )}
                </div>
            </div>


            {/* Expanded Content */}
            {(isExpanded && !isDocked) && (
                <div className="mt-2 space-y-1 pt-2 border-t-2 border-dashed border-brutal-black/30">
                    {/* Detailed Progress List */}
                    <div className="space-y-0.5">
                        {plan.phases.map((phase, idx) => {
                            let bgColor = 'bg-white';
                            let borderColor = 'border-neutral-300';
                            let textColor = 'text-neutral-400';

                            if (phase.status === 'completed') {
                                bgColor = 'bg-brutal-green/20';
                                borderColor = 'border-brutal-green';
                                textColor = 'text-brutal-black line-through opacity-60';
                            } else if (phase.status === 'in_progress') {
                                bgColor = 'bg-brutal-blue/10';
                                borderColor = 'border-brutal-blue';
                                textColor = 'text-brutal-black';
                            }

                            return (
                                <div key={phase.id || idx} className={`flex items-start gap-2 p-1.5 border-l-4 ${phase.status === 'in_progress' ? 'border-brutal-blue bg-neutral-50' : 'border-transparent'}`}>
                                    <div className={`mt-0.5 w-4 h-4 shrink-0 border-2 flex items-center justify-center text-[9px] font-bold ${phase.status === 'completed' ? 'bg-brutal-green border-brutal-black text-brutal-black' :
                                        phase.status === 'in_progress' ? 'bg-brutal-blue border-brutal-black text-white' :
                                            'bg-white border-neutral-400 text-neutral-400'
                                        }`}>
                                        {phase.status === 'completed' ? '✓' : idx + 1}
                                    </div>
                                    <div className="flex-1">
                                        <div className={`text-xs font-bold leading-tight ${phase.status === 'completed' ? 'text-neutral-500' : 'text-brutal-black'}`}>
                                            {phase.title || phase.description}
                                        </div>
                                        {phase.note && (
                                            <div className="text-[10px] text-neutral-500 italic mt-0.5">
                                                {phase.note}
                                            </div>
                                        )}
                                    </div>
                                    {phase.status === 'in_progress' && (
                                        <div className="shrink-0">
                                            <span className="text-[9px] font-bold bg-brutal-blue text-white px-1.5 py-0.5 border border-brutal-blue rounded-full animate-pulse">
                                                {t('planProgress.active')}
                                            </span>
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
};
