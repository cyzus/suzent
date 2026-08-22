import React from 'react';

type ButtonVariant =
    | 'default'
    | 'light'     // always-white surface
    | 'primary'   // blue
    | 'success'   // green
    | 'danger'    // red
    | 'warning'   // yellow
    | 'dark'      // black
    | 'ghost';
type ButtonSize = 'xs' | 'sm' | 'md' | 'icon' | 'icon-lg';

interface BrutalActionStyleOptions {
    variant?: ButtonVariant;
    size?: ButtonSize;
    isActive?: boolean;
    disabled?: boolean;
    className?: string;
}

function getVariantStyles(variant: ButtonVariant, isActive: boolean): string {
    switch (variant) {
        case 'primary':
            return 'bg-brutal-blue text-white hover:brightness-110 brutal-btn';
        case 'success':
            return 'bg-brutal-green text-brutal-black hover:brightness-110 brutal-btn';
        case 'danger':
            return 'bg-brutal-red text-white hover:brightness-110 brutal-btn';
        case 'warning':
            return 'bg-brutal-yellow text-brutal-black hover:brightness-110 brutal-btn';
        case 'dark':
            return 'bg-brutal-black text-white hover:bg-neutral-800 brutal-btn';
        case 'light':
            return 'bg-white text-brutal-black hover:bg-neutral-100 brutal-btn';
        case 'ghost':
            return 'bg-transparent border-transparent hover:bg-neutral-100 dark:hover:bg-zinc-700 transition-all';
        case 'default':
        default:
            return isActive
                ? 'bg-brutal-black text-white shadow-none translate-x-[1px] translate-y-[1px] transition-all'
                : 'bg-white dark:bg-zinc-800 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-700 brutal-btn';
    }
}

function getSizeStyles(size: ButtonSize): string {
    switch (size) {
        case 'xs':
            return 'text-[10px] px-3 py-1 gap-1';
        case 'sm':
            return 'text-xs px-3 py-1.5 gap-1.5';
        case 'icon':
            return 'p-1.5 w-8 h-8';
        case 'icon-lg':
            return 'p-0 w-9 h-9';
        case 'md':
        default:
            return 'text-sm px-4 py-2 gap-2';
    }
}

function brutalActionClassName({
    variant = 'default',
    size = 'md',
    isActive = false,
    disabled = false,
    className = '',
}: BrutalActionStyleOptions): string {
    const baseStyles = 'font-mono font-bold border-2 border-brutal-black inline-flex items-center justify-center';
    const disabledStyles = disabled
        ? 'opacity-50 cursor-not-allowed active:translate-x-0 active:translate-y-0 active:shadow-brutal-sm'
        : 'cursor-pointer';

    return `${baseStyles} ${getVariantStyles(variant, isActive)} ${getSizeStyles(size)} ${disabledStyles} ${className}`;
}

interface BrutalButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: ButtonVariant;
    size?: ButtonSize;
    isActive?: boolean; // For toggle buttons: renders in the pressed-in state
}

/**
 * The canonical neo-brutalist action button. Border, drop shadow, and the
 * press-on-click animation all live here (the animation comes from the shared
 * `.brutal-btn` class in styles.css) so every button presses identically.
 *
 * Reach for this instead of hand-writing
 * `border-2 border-brutal-black shadow-[2px_2px…] active:translate-…`.
 */
export const BrutalButton: React.FC<BrutalButtonProps> = ({
    variant = 'default',
    size = 'md',
    isActive = false,
    className = '',
    children,
    disabled,
    ...props
}) => {
    return (
        <button
            className={brutalActionClassName({ variant, size, isActive, disabled, className })}
            disabled={disabled}
            {...props}
        >
            {children}
        </button>
    );
};

interface BrutalLinkProps extends React.AnchorHTMLAttributes<HTMLAnchorElement> {
    variant?: ButtonVariant;
    size?: ButtonSize;
}

/** Link counterpart to BrutalButton for external actions with identical chrome. */
export const BrutalLink: React.FC<BrutalLinkProps> = ({
    variant = 'default',
    size = 'md',
    className = '',
    children,
    ...props
}) => (
    <a className={brutalActionClassName({ variant, size, className })} {...props}>
        {children}
    </a>
);
