import React from 'react';

interface BrutalToggleProps {
    checked: boolean;
    onChange: (checked: boolean) => void;
    label: string;
    className?: string;
}

export function BrutalToggle({ checked, onChange, label, className = '' }: BrutalToggleProps): React.ReactElement {
    return (
        <button
            onClick={() => onChange(!checked)}
            className={`w-full flex items-center gap-3 p-3 border-4 border-brutal-black font-black uppercase text-sm tracking-wider transition-all shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:translate-x-[4px] active:translate-y-[4px] active:shadow-none ${checked
                    ? 'bg-brutal-green text-brutal-black'
                    : 'bg-white text-brutal-black hover:bg-neutral-100'
                } ${className}`}
        >
            <div className={`w-6 h-6 border-3 border-brutal-black flex items-center justify-center ${checked ? 'bg-brutal-black' : 'bg-white'}`}>
                {checked && (
                    <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={4}>
                        <path strokeLinecap="square" strokeLinejoin="miter" d="M5 13l4 4L19 7" />
                    </svg>
                )}
            </div>
            {label}
        </button>
    );
}
