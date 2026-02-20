import React from 'react';
import { useI18n } from '../i18n';

interface BrutalDeleteButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
    isActive?: boolean;
}

export const BrutalDeleteButton: React.FC<BrutalDeleteButtonProps> = ({
    isActive = false,
    className = '',
    title,
    ...props
}) => {
    const { t } = useI18n();
    const resolvedTitle = title ?? t('deleteOverlay.buttonTitle');
    return (
        <button
            type="button"
            className={`
        p-1.5 border-2 border-brutal-black transition-all duration-200 
        hover:shadow-[4px_4px_0_0_#000000] brutal-btn
        flex items-center justify-center
        ${isActive
                    ? 'bg-white hover:bg-brutal-red hover:text-white'
                    : 'bg-neutral-100 hover:bg-brutal-red hover:text-white'
                }
        ${className}
      `}
            title={resolvedTitle}
            {...props}
        >
            <svg
                className="w-3 h-3"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                strokeWidth={3}
            >
                <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                />
            </svg>
        </button>
    );
};
