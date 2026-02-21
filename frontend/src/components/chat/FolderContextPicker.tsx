import React, { useEffect, useState, useRef, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';
import { FolderIcon, PlusIcon, ClockIcon, CheckIcon } from '@heroicons/react/24/outline';
import { ChevronDownIcon } from '@heroicons/react/24/solid';
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
}

const HISTORY_KEY = 'suzent_folder_history';
const MAX_HISTORY = 2;

export const FolderContextPicker: React.FC<FolderContextPickerProps> = ({
    onMount,
    activeVolumes = [],
    onRemoveVolume,
    disabled = false,
    dropUp = true
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

    const [effectiveDropUp, setEffectiveDropUp] = useState(dropUp);

    // Calculate dropdown position
    const updatePosition = React.useCallback(() => {
        if (buttonRef.current) {
            const rect = buttonRef.current.getBoundingClientRect();
            // Fixed width for this menu
            const width = 288; // w-72 = 18rem = 288px
            const height = 400; // max-h-[400px]

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
                    left: rect.left,
                    width
                });
            } else {
                setDropdownPosition({
                    top: rect.bottom + 4,
                    left: rect.left,
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
            className={`fixed z-[9999] w-72 bg-white border-2 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] focus:outline-none flex flex-col max-h-[400px] overflow-y-auto scrollbar-thin animate-brutal-drop`}
            style={{
                top: effectiveDropUp ? 'auto' : dropdownPosition.top,
                bottom: effectiveDropUp ? (window.innerHeight - dropdownPosition.top) : 'auto',
                left: dropdownPosition.left,
                // Ensure it doesn't go off screen
                maxWidth: 'calc(100vw - 2rem)'
            }}
        >
            {/* ACTIVE CONTEXTS SECTION */}
            <div className="p-2 border-b-2 border-brutal-black bg-neutral-100">
                <div className="text-[10px] font-bold uppercase tracking-wider text-brutal-black mb-1 flex justify-between items-center opacity-60">
                    <span>{t('folderContext.activeContexts')}</span>
                    <span>{activeCount}</span>
                </div>

                {activeCount === 0 ? (
                    <div className="text-xs text-neutral-500 italic py-1 pl-1">{t('folderContext.noFoldersMounted')}</div>
                ) : (
                    <div className="space-y-1 mb-1">
                        {activeVolumes.map((vol, idx) => {
                            const lastSemi = vol.lastIndexOf(':');
                            const hostPath = vol.substring(0, lastSemi);
                            const folderName = hostPath.split(/[/\\]/).pop() || hostPath;

                            return (
                                <div key={idx} className="flex items-center justify-between bg-white px-2 py-1.5 border-2 border-brutal-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] brutal-btn transition-all cursor-pointer" onClick={() => onRemoveVolume?.(idx)}>
                                    <div className="flex items-center gap-2 min-w-0">
                                        <div className="bg-brutal-green p-0.5 border border-brutal-black">
                                            <CheckIcon className="w-3 h-3 text-brutal-black" />
                                        </div>
                                        <div className="min-w-0">
                                            <div className="text-xs font-bold truncate text-brutal-black">{folderName}</div>
                                            <div className="text-[9px] text-neutral-500 truncate font-mono" title={hostPath}>{hostPath}</div>
                                        </div>
                                    </div>
                                    <div className="text-brutal-red text-xs font-black px-1 hover:bg-neutral-100 rounded">{t('folderContext.remove')}</div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            {/* RECENT FOLDERS SECTION */}
            <div className="p-2 border-b-2 border-brutal-black bg-white">
                <div className="text-[10px] font-bold uppercase tracking-wider text-brutal-black opacity-60 mb-1 pl-1">
                    {t('folderContext.recentFolders')}
                </div>
                {history.length === 0 ? (
                    <div className="text-xs text-neutral-500 italic py-1 pl-1">{t('folderContext.noRecentFolders')}</div>
                ) : (
                    <div className="space-y-0.5">
                        {history.map((item) => {
                            const isActive = activeVolumes.some(v => v.substring(0, v.lastIndexOf(':')) === item.path);
                            return (
                                <button
                                    type="button"
                                    key={item.path}
                                    onClick={() => handleRecentClick(item.path)}
                                    className={`
                                        w-full text-left px-2 py-2 flex items-center gap-2 text-xs font-medium border-2 transition-all
                                        shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] brutal-btn
                                        ${isActive
                                            ? 'bg-brutal-green border-brutal-black text-brutal-black'
                                            : 'bg-white border-brutal-black text-brutal-black hover:bg-neutral-50'}
                                    `}
                                >
                                    {isActive ? (
                                        <CheckIcon className="w-4 h-4 text-brutal-black shrink-0" strokeWidth={2.5} />
                                    ) : (
                                        <ClockIcon className="w-4 h-4 text-neutral-400 shrink-0" />
                                    )}
                                    <div className="min-w-0 flex-1">
                                        <div className="truncate font-bold">{item.path.split(/[/\\]/).pop()}</div>
                                        <div className={`truncate text-[9px] font-mono ${isActive ? 'text-brutal-black opacity-80' : 'text-neutral-500'}`} title={item.path}>{item.path}</div>
                                    </div>
                                </button>
                            );
                        })}
                    </div>
                )}
            </div>

            <div className="p-1 bg-neutral-100">
                <button
                    type="button"
                    onClick={handleNativePick}
                    className={`
                        w-full flex items-center justify-center gap-2 px-2 py-2 text-xs font-bold uppercase transition-all border-2 border-brutal-black
                        bg-white text-brutal-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] brutal-btn
                    `}
                >
                    <PlusIcon className="w-4 h-4" />
                    {t('folderContext.chooseDifferent')}
                </button>
            </div>
        </div>,
        document.body
    );

    return (
        <div className="relative inline-block text-left" ref={containerRef}>
            <button
                ref={buttonRef}
                type="button"
                onClick={() => setIsOpen(!isOpen)}
                disabled={disabled}
                className={`
                    flex items-center gap-1.5 px-2 py-1 border-2 border-brutal-black brutal-btn shadow-[2px_2px_0_0_#000] transition-all disabled:opacity-50 disabled:cursor-not-allowed group text-xs font-bold uppercase
                    ${activeCount > 0 ? 'bg-brutal-green text-brutal-black' : 'bg-white text-brutal-black hover:bg-neutral-100'}
                `}
            >
                <FolderIcon className="w-4 h-4" />
                <span className="hidden sm:inline">{t('folderContext.context')}</span>
                {activeCount > 0 && (
                    <span className="bg-brutal-black text-white px-1.5 rounded-full text-[10px] min-w-[1.2em] text-center font-bold">
                        {activeCount}
                    </span>
                )}
                <ChevronDownIcon
                    className={`w-3 h-3 ml-0.5 opacity-60 group-hover:opacity-100 transition-transform duration-200 ${isOpen ? (effectiveDropUp ? 'rotate-0' : 'rotate-180') : (effectiveDropUp ? 'rotate-180' : 'rotate-0')}`}
                />
            </button>
            {dropdown}
        </div>
    );
};
