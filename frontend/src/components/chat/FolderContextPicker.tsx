import React, { useEffect, useState, useRef, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';
import {
    CheckIcon,
    ClockIcon,
    FolderIcon,
    PlusIcon,
    XMarkIcon,
} from '@heroicons/react/24/outline';
import { open } from '@tauri-apps/plugin-dialog';
import { useI18n } from '../../i18n';

interface RecentFolder {
    path: string;
    timestamp: number;
}

interface FolderContextPickerProps {
    onMount: (paths: string[]) => void;
    activeVolumes?: string[];
    onRemoveVolume?: (index: number) => void;
    disabled?: boolean;
    dropUp?: boolean;
    buttonLabel?: string;
}

const HISTORY_KEY = 'suzent_folder_history';
const MAX_HISTORY = 5;

export const FolderContextPicker: React.FC<FolderContextPickerProps> = ({
    onMount,
    activeVolumes = [],
    onRemoveVolume,
    disabled = false,
    dropUp = true,
    buttonLabel
}) => {
    const { t } = useI18n();
    const [history, setHistory] = useState<RecentFolder[]>([]);
    const [isOpen, setIsOpen] = useState(false);
    const [dropdownPosition, setDropdownPosition] = useState<{ top: number; left: number; width?: number } | null>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const buttonRef = useRef<HTMLButtonElement>(null);
    const dropdownRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        try {
            const saved = localStorage.getItem(HISTORY_KEY);
            if (saved) {
                setHistory(JSON.parse(saved));
            }
        } catch (e) {
            console.error('Failed to load folder history', e);
        }
    }, []);

    const addToHistory = (paths: string[]) => {
        const now = Date.now();
        const newItems = paths.map(p => ({ path: p, timestamp: now }));

        setHistory(prev => {
            const combined = [...newItems, ...prev];
            const unique = combined.filter((item, index, self) =>
                index === self.findIndex((t) => t.path === item.path)
            );
            const trimmed = unique.slice(0, MAX_HISTORY);

            localStorage.setItem(HISTORY_KEY, JSON.stringify(trimmed));
            return trimmed;
        });
    };

    const handleNativePick = async () => {
        try {
            const selected = await open({
                directory: true,
                multiple: true,
            });

            if (!selected) return;
            const paths = Array.isArray(selected) ? selected : [selected];
            if (paths.length === 0) return;

            addToHistory(paths);
            onMount(paths);
            setIsOpen(false);
        } catch (err) {
            console.error('Failed to open native dialog', err);
        }
    };

    const handleRecentClick = (path: string) => {
        // Check if already active
        const existingIndex = activeVolumes.findIndex(v => v.substring(0, v.lastIndexOf(':')) === path);
        if (existingIndex !== -1) {
            onRemoveVolume?.(existingIndex);
        } else {
            addToHistory([path]);
            onMount([path]);
        }
    };

    // Calculate active count for badge
    const activeCount = activeVolumes.length;

    const getDynamicLabel = (): string | null => {
        if (!activeVolumes.length) return null;
        const firstName = activeVolumes[0].split(/[\\/]/).filter(Boolean).pop() ?? activeVolumes[0];
        if (activeVolumes.length === 1) return firstName;
        return firstName;
    };

    const dynamicLabel = getDynamicLabel();
    const inactiveHistory = history.filter(item =>
        !activeVolumes.some(volume =>
            volume.substring(0, volume.lastIndexOf(':')) === item.path
        )
    );

    const [effectiveDropUp, setEffectiveDropUp] = useState(dropUp);

    // Calculate dropdown position
    const updatePosition = React.useCallback(() => {
        if (buttonRef.current) {
            const rect = buttonRef.current.getBoundingClientRect();
            const width = 336;
            const height = 420;
            const left = Math.max(16, Math.min(rect.left, window.innerWidth - width - 16));

            const spaceAbove = rect.top;
            const spaceBelow = window.innerHeight - rect.bottom;

            let shouldDropUp = dropUp;

            // Auto-flip logic
            if (dropUp && spaceAbove < height && spaceBelow > height) {
                shouldDropUp = false;
            } else if (!dropUp && spaceBelow < height && spaceAbove > height) {
                shouldDropUp = true;
            }

            setEffectiveDropUp(shouldDropUp);

            if (shouldDropUp) {
                setDropdownPosition({
                    top: rect.top - 4,
                    left,
                    width
                });
            } else {
                setDropdownPosition({
                    top: rect.bottom + 4,
                    left,
                    width
                });
            }
        }
    }, [dropUp]);

    useLayoutEffect(() => {
        if (isOpen) {
            updatePosition();

            window.addEventListener('resize', updatePosition);
            window.addEventListener('scroll', updatePosition, true);

            return () => {
                window.removeEventListener('resize', updatePosition);
                window.removeEventListener('scroll', updatePosition, true);
            };
        }
    }, [isOpen, updatePosition]);

    // Close on click outside
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            const target = event.target as Node;
            const isOutsideContainer = containerRef.current && !containerRef.current.contains(target);
            const isOutsideDropdown = dropdownRef.current && !dropdownRef.current.contains(target);

            if (isOutsideContainer && isOutsideDropdown) {
                setIsOpen(false);
            }
        };

        if (isOpen) {
            document.addEventListener('mousedown', handleClickOutside);
        }
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, [isOpen]);

    const dropdown = isOpen && dropdownPosition && createPortal(
        <div
            ref={dropdownRef}
            role="dialog"
            aria-label={t('folderContext.context')}
            className="fixed z-[9999] bg-white dark:bg-zinc-800 border-2 border-brutal-black shadow-[3px_3px_0_0_#000] focus:outline-none flex flex-col max-h-[420px] overflow-y-auto scrollbar-thin animate-brutal-drop"
            style={{
                top: effectiveDropUp ? 'auto' : dropdownPosition.top,
                bottom: effectiveDropUp ? (window.innerHeight - dropdownPosition.top) : 'auto',
                left: dropdownPosition.left,
                // Ensure it doesn't go off screen
                maxWidth: 'calc(100vw - 2rem)'
            }}
        >
            <div className="px-3 py-2.5 border-b-2 border-brutal-black bg-neutral-100 dark:bg-zinc-900">
                <div className="flex justify-between items-center gap-3">
                    <div className="flex items-center gap-2 min-w-0">
                        <FolderIcon className="w-4 h-4 shrink-0 text-brutal-black dark:text-white" />
                        <span className="text-xs font-black uppercase tracking-wide text-brutal-black dark:text-white">
                            {t('folderContext.activeContexts')}
                        </span>
                    </div>
                    <span className={`min-w-6 h-6 px-1.5 inline-flex items-center justify-center border-2 border-brutal-black text-[10px] font-black ${activeCount > 0 ? 'bg-brutal-green text-brutal-black' : 'bg-white dark:bg-zinc-800 dark:text-white'}`}>
                        {activeCount}
                    </span>
                </div>

                {activeCount === 0 ? (
                    <div className="text-xs text-neutral-500 dark:text-neutral-400 py-2">
                        {t('folderContext.noFoldersMounted')}
                    </div>
                ) : (
                    <div className="mt-2 border-2 border-brutal-black bg-white dark:bg-zinc-800 divide-y-2 divide-brutal-black">
                        {activeVolumes.map((vol, idx) => {
                            const lastSemi = vol.lastIndexOf(':');
                            const hostPath = vol.substring(0, lastSemi);
                            const folderName = hostPath.split(/[/\\]/).pop() || hostPath;

                            return (
                                <div key={`${hostPath}-${idx}`} className="flex items-center gap-2 px-2.5 py-2">
                                    <div className="w-6 h-6 bg-brutal-green border-2 border-brutal-black flex items-center justify-center shrink-0">
                                        <CheckIcon className="w-3.5 h-3.5 text-brutal-black" strokeWidth={3} />
                                    </div>
                                    <div className="min-w-0 flex-1">
                                        <div className="text-xs font-bold truncate text-brutal-black dark:text-white">
                                            {folderName}
                                        </div>
                                        <div className="text-[10px] text-neutral-500 dark:text-neutral-400 truncate font-mono" title={hostPath}>
                                            {hostPath}
                                        </div>
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() => onRemoveVolume?.(idx)}
                                        className="w-7 h-7 shrink-0 flex items-center justify-center border-0 text-neutral-500 dark:text-neutral-400 hover:bg-brutal-red hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue"
                                        title={`${t('folderContext.remove')}: ${folderName}`}
                                        aria-label={`${t('folderContext.remove')}: ${folderName}`}
                                    >
                                        <XMarkIcon className="w-4 h-4" strokeWidth={2.5} />
                                    </button>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            <div className="px-3 py-2.5 border-b-2 border-brutal-black bg-white dark:bg-zinc-800">
                <div className="text-[10px] font-black uppercase tracking-wider text-neutral-500 dark:text-neutral-400 mb-1.5">
                    {t('folderContext.recentFolders')}
                </div>
                {inactiveHistory.length === 0 ? (
                    <div className="text-xs text-neutral-500 dark:text-neutral-400 py-1">
                        {history.length > 0
                            ? t('folderContext.allRecentFoldersMounted')
                            : t('folderContext.noRecentFolders')}
                    </div>
                ) : (
                    <div className="border-y border-neutral-200 dark:border-zinc-700 divide-y divide-neutral-200 dark:divide-zinc-700">
                        {inactiveHistory.map((item) => (
                            <button
                                type="button"
                                key={item.path}
                                onClick={() => handleRecentClick(item.path)}
                                className="group w-full text-left px-1 py-2 flex items-center gap-2.5 text-xs text-brutal-black dark:text-white transition-colors hover:bg-brutal-yellow/40 dark:hover:bg-zinc-700 focus:outline-none focus-visible:bg-brutal-yellow/40"
                            >
                                <ClockIcon className="w-4 h-4 text-neutral-400 group-hover:text-brutal-black dark:group-hover:text-white shrink-0" />
                                <div className="min-w-0 flex-1">
                                    <div className="truncate font-bold">{item.path.split(/[/\\]/).pop()}</div>
                                    <div className="truncate text-[10px] font-mono text-neutral-500 dark:text-neutral-400" title={item.path}>
                                        {item.path}
                                    </div>
                                </div>
                                <PlusIcon className="w-4 h-4 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
                            </button>
                        ))}
                    </div>
                )}
            </div>

            <div className="p-2 bg-neutral-100 dark:bg-zinc-900">
                <button
                    type="button"
                    onClick={handleNativePick}
                    className="w-full flex items-center justify-center gap-2 px-3 py-2.5 text-xs font-black uppercase transition-colors border-2 border-brutal-black bg-brutal-yellow text-brutal-black hover:bg-yellow-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue"
                >
                    <PlusIcon className="w-4 h-4" />
                    {t('folderContext.chooseDifferent')}
                </button>
            </div>
        </div>,
        document.body
    );

    return (
        <div className="relative min-w-0 shrink text-left" ref={containerRef}>
            <button
                ref={buttonRef}
                type="button"
                onClick={() => setIsOpen(!isOpen)}
                disabled={disabled}
                aria-haspopup="dialog"
                aria-expanded={isOpen}
                className={`
                    flex items-center gap-1.5 px-2.5 h-9 w-full min-w-0 border-0 shadow-none transition-colors disabled:opacity-50 disabled:cursor-not-allowed group text-xs font-bold uppercase focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue
                    ${activeCount > 0 ? 'bg-brutal-green/70 text-brutal-black hover:bg-brutal-green' : 'bg-neutral-100 dark:bg-zinc-700 text-brutal-black dark:text-white hover:bg-neutral-200 dark:hover:bg-zinc-600'}
                `}
            >
                <FolderIcon className="w-4 h-4 shrink-0" />
                <span className="hidden sm:inline truncate min-w-0">
                    {buttonLabel || dynamicLabel || t('folderContext.context')}
                </span>
                {activeCount > 1 && (
                    <span className="min-w-5 h-5 px-1 inline-flex items-center justify-center bg-white/80 border border-brutal-black text-[9px] leading-none">
                        {activeCount}
                    </span>
                )}
                <svg
                    className={`w-4 h-4 ml-0.5 opacity-60 group-hover:opacity-100 transition-transform duration-200 ${isOpen ? (effectiveDropUp ? 'rotate-0' : 'rotate-180') : (effectiveDropUp ? 'rotate-180' : 'rotate-0')}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    strokeWidth={3}
                    aria-hidden="true"
                >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
            </button>
            {dropdown}
        </div>
    );
};
