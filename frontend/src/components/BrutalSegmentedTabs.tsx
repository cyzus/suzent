import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';

export interface BrutalSegmentedTab<T extends string> {
    id: T;
    label: string;
    /** Optional trailing content, e.g. a count badge. */
    trailing?: React.ReactNode;
    /** Tooltip; defaults to label. */
    title?: string;
}

interface BrutalSegmentedTabsProps<T extends string> {
    tabs: ReadonlyArray<BrutalSegmentedTab<T>>;
    value: T;
    onChange: (id: T) => void;
    /** Layout classes for the outer container (margins, etc.). */
    className?: string;
    /** Themed container chrome: border, background, shadow. Overridable per usage. */
    containerClassName?: string;
    /** Background classes for the animated active slider. */
    sliderClassName?: string;
    /** Text classes for the active tab (sits above the slider). */
    activeTextClassName?: string;
    /** Text classes for inactive tabs. */
    inactiveTextClassName?: string;
    /** Sizing/typography classes applied to every tab button. */
    tabClassName?: string;
}

export function BrutalSegmentedTabs<T extends string>({
    tabs,
    value,
    onChange,
    className = '',
    containerClassName = 'border-3 border-brutal-black bg-neutral-100 dark:bg-zinc-800 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]',
    sliderClassName = 'bg-brutal-black dark:bg-brutal-yellow',
    activeTextClassName = 'text-white dark:text-brutal-black',
    inactiveTextClassName = 'text-brutal-black dark:text-white hover:bg-black/5 dark:hover:bg-white/5',
    tabClassName = 'px-2 py-0.5 text-[10px] md:text-sm font-bold',
}: BrutalSegmentedTabsProps<T>): React.ReactElement {
    const navRef = useRef<HTMLDivElement>(null);
    const [slider, setSlider] = useState({ left: 0, width: 0 });

    useLayoutEffect(() => {
        const node = navRef.current;
        if (!node) return;

        const measure = (): void => {
            const activeBtn = node.querySelector<HTMLButtonElement>(`button[data-tab="${value}"]`);
            setSlider(activeBtn
                ? { left: activeBtn.offsetLeft, width: activeBtn.offsetWidth }
                : { left: 0, width: 0 });
        };

        measure();
        const observer = new ResizeObserver(measure);
        observer.observe(node);
        return () => observer.disconnect();
    }, [value, tabs]);

    // Re-measure once fonts/layout settle after mount, matching the legacy nav timing.
    useEffect(() => {
        const node = navRef.current;
        if (!node) return;
        const timeout = setTimeout(() => {
            const activeBtn = node.querySelector<HTMLButtonElement>(`button[data-tab="${value}"]`);
            if (activeBtn) setSlider({ left: activeBtn.offsetLeft, width: activeBtn.offsetWidth });
        }, 10);
        return () => clearTimeout(timeout);
    }, [value, tabs]);

    return (
        <div ref={navRef} className={`relative flex items-center p-0.5 ${containerClassName} ${className}`}>
            {/* Animated active-tab slider */}
            <div
                className={`absolute top-0.5 bottom-0.5 transition-all duration-300 ease-out pointer-events-none ${sliderClassName}`}
                style={{ left: slider.left, width: slider.width }}
            />
            {tabs.map(tab => (
                <button
                    key={tab.id}
                    data-tab={tab.id}
                    type="button"
                    onClick={() => onChange(tab.id)}
                    title={tab.title ?? tab.label}
                    className={`relative z-10 flex items-center justify-center gap-1 uppercase whitespace-nowrap tracking-wide transition-colors ${tabClassName} ${value === tab.id ? activeTextClassName : inactiveTextClassName}`}
                >
                    <span className="truncate">{tab.label}</span>
                    {tab.trailing}
                </button>
            ))}
        </div>
    );
}
