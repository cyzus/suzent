import React from 'react';

import { useI18n } from '../i18n';

interface BrutalOnOffProps {
    checked: boolean;
    onChange: (checked: boolean) => void;
    /** 'md' for card headers (default), 'sm' for dense list rows. */
    size?: 'sm' | 'md';
    disabled?: boolean;
    className?: string;
}

/**
 * Brutalist switch: fixed-width track with a sliding square knob and the
 * current state label on the opposite side. Green when on, muted when off.
 */
export function BrutalOnOff({
    checked,
    onChange,
    size = 'md',
    disabled = false,
    className = '',
}: BrutalOnOffProps): React.ReactElement {
    const { t } = useI18n();
    const sm = size === 'sm';

    return (
        <button
            type="button"
            role="switch"
            aria-checked={checked}
            onClick={() => onChange(!checked)}
            disabled={disabled}
            className={`relative shrink-0 border-2 border-brutal-black shadow-brutal-sm active:shadow-none active:translate-x-[1px] active:translate-y-[1px] transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${sm ? 'w-12 h-5' : 'w-16 h-7'} ${
                checked ? 'bg-brutal-green' : 'bg-white dark:bg-zinc-700 hover:bg-neutral-100 dark:hover:bg-zinc-600'
            } ${className}`}
        >
            {/* State label, opposite the knob */}
            <span
                className={`absolute inset-y-0 flex items-center font-bold uppercase ${sm ? 'text-[8px]' : 'text-[10px]'} ${
                    checked
                        ? `text-brutal-black ${sm ? 'left-1' : 'left-1.5'}`
                        : `text-neutral-400 dark:text-neutral-500 ${sm ? 'right-1' : 'right-1.5'}`
                }`}
            >
                {checked ? t('common.on') : t('common.off')}
            </span>
            {/* Sliding square knob */}
            <span
                className={`absolute left-0.5 top-1/2 -translate-y-1/2 border-2 border-brutal-black transition-transform duration-150 ${
                    sm ? 'w-3.5 h-3.5' : 'w-5 h-5'
                } ${
                    checked
                        ? `${sm ? 'translate-x-[26px]' : 'translate-x-9'} bg-brutal-black`
                        : 'translate-x-0 bg-white dark:bg-zinc-400'
                }`}
            />
        </button>
    );
}
