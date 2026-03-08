import React from 'react';
import { useMemo } from 'react';

type ButtonVariant = 'default' | 'primary' | 'danger' | 'warning' | 'ghost';
type ButtonSize = 'sm' | 'md' | 'icon';

interface BrutalButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: ButtonVariant;
    size?: ButtonSize;
    isActive?: boolean; // For toggle buttons
}

export const BrutalButton: React.FC<BrutalButtonProps> = ({
    variant = 'default',
    size = 'md',
    isActive = false,
    className = '',
    children,
    disabled,
    ...props
}) => {
    const baseStyles = "font-mono font-bold border-2 border-brutal-black transition-all active:translate-y-[2px] active:shadow-none flex items-center justify-center";

    const variantStyles = useMemo(() => {
        switch (variant) {
            case 'primary':
                return "bg-brutal-blue text-white hover:bg-blue-600 shadow-[2px_2px_0_0_#000] brutal-btn";
            case 'danger':
                return "bg-brutal-red text-white hover:bg-red-600 shadow-[2px_2px_0_0_#000] brutal-btn";
            case 'warning':
                return "bg-brutal-yellow text-brutal-black hover:bg-yellow-400 shadow-[2px_2px_0_0_#000] brutal-btn";
            case 'ghost':
                return "bg-transparent border-transparent hover:bg-neutral-100 dark:hover:bg-zinc-700 shadow-none active:translate-y-0";
            case 'default':
            default:
                return `bg-white dark:bg-zinc-800 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-700 ${isActive ? 'bg-neutral-200 dark:bg-zinc-700 shadow-none translate-y-[2px]' : 'shadow-[2px_2px_0_0_#000] brutal-btn'}`;
        }
    }, [variant, isActive]);

    const sizeStyles = useMemo(() => {
        switch (size) {
            case 'sm':
                return "text-xs px-2 py-1 gap-1";
            case 'icon':
                return "p-1.5 w-8 h-8"; // Fixed size for icon buttons
            case 'md':
            default:
                return "text-sm px-4 py-2 gap-2";
        }
    }, [size]);

    const disabledStyles = disabled ? "opacity-50 cursor-not-allowed active:translate-y-0 active:shadow-brutal" : "cursor-pointer";

    return (
        <button
            className={`${baseStyles} ${variantStyles} ${sizeStyles} ${disabledStyles} ${className}`}
            disabled={disabled}
            {...props}
        >
            {children}
        </button>
    );
};
