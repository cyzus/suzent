import React, { useEffect, useState } from 'react';
import { Menu, Transition } from '@headlessui/react';
import { FolderIcon, PlusIcon, ClockIcon, CheckIcon } from '@heroicons/react/24/outline';
import { ChevronDownIcon } from '@heroicons/react/24/solid';
import { open } from '@tauri-apps/plugin-dialog';

interface RecentFolder {
    path: string;
    timestamp: number;
}

interface FolderContextPickerProps {
    onMount: (paths: string[]) => void;
    activeVolumes?: string[];
    onRemoveVolume?: (index: number) => void;
    disabled?: boolean;
}

const HISTORY_KEY = 'suzent_folder_history';
const MAX_HISTORY = 5;

export const FolderContextPicker: React.FC<FolderContextPickerProps> = ({
    onMount,
    activeVolumes = [],
    onRemoveVolume,
    disabled = false
}) => {
    const [history, setHistory] = useState<RecentFolder[]>([]);

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

    return (
        <Menu as="div" className="relative inline-block text-left">
            <div>
                <Menu.Button
                    disabled={disabled}
                    className={`
                        flex items-center gap-1.5 px-2 py-1 border-2 border-brutal-black active:translate-y-[1px] shadow-brutal-sm hover:shadow-none transition-all disabled:opacity-50 disabled:cursor-not-allowed group text-xs font-bold uppercase
                        ${activeCount > 0 ? 'bg-brutal-green text-brutal-black' : 'bg-white text-brutal-black hover:bg-neutral-100'}
                    `}
                >
                    <FolderIcon className="w-4 h-4" />
                    <span className="hidden sm:inline">Context</span>
                    {activeCount > 0 && (
                        <span className="bg-brutal-black text-white px-1.5 rounded-full text-[10px] min-w-[1.2em] text-center font-bold">
                            {activeCount}
                        </span>
                    )}
                    <ChevronDownIcon className="w-3 h-3 ml-0.5 opacity-60 group-hover:opacity-100" />
                </Menu.Button>
            </div>

            <Transition
                as={React.Fragment}
                enter="transition ease-out duration-100"
                enterFrom="transform opacity-0 scale-95"
                enterTo="transform opacity-100 scale-100"
                leave="transition ease-in duration-75"
                leaveFrom="transform opacity-100 scale-100"
                leaveTo="transform opacity-0 scale-95"
            >
                <Menu.Items className="absolute bottom-full left-0 mb-2 w-72 origin-bottom-left bg-white border-2 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] focus:outline-none flex flex-col z-50 max-h-[400px] overflow-y-auto">

                    {/* ACTIVE CONTEXTS SECTION */}
                    <div className="p-2 border-b-2 border-brutal-black bg-neutral-100">
                        <div className="text-[10px] font-bold uppercase tracking-wider text-brutal-black mb-1 flex justify-between items-center opacity-60">
                            <span>Active Contexts</span>
                            <span>{activeCount}</span>
                        </div>

                        {activeCount === 0 ? (
                            <div className="text-xs text-neutral-500 italic py-1 pl-1">No folders mounted</div>
                        ) : (
                            <div className="space-y-1 mb-1">
                                {activeVolumes.map((vol, idx) => {
                                    const lastSemi = vol.lastIndexOf(':');
                                    const hostPath = vol.substring(0, lastSemi);
                                    const folderName = hostPath.split(/[/\\]/).pop() || hostPath;

                                    return (
                                        <div key={idx} className="flex items-center justify-between bg-white px-2 py-1.5 border-2 border-brutal-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-none transition-all cursor-pointer" onClick={() => onRemoveVolume?.(idx)}>
                                            <div className="flex items-center gap-2 min-w-0">
                                                <div className="bg-brutal-green p-0.5 border border-brutal-black">
                                                    <CheckIcon className="w-3 h-3 text-brutal-black" />
                                                </div>
                                                <div className="min-w-0">
                                                    <div className="text-xs font-bold truncate text-brutal-black">{folderName}</div>
                                                    <div className="text-[9px] text-neutral-500 truncate font-mono" title={hostPath}>{hostPath}</div>
                                                </div>
                                            </div>
                                            <div className="text-brutal-red text-xs font-black px-1 hover:bg-neutral-100 rounded">Remove</div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>

                    {/* RECENT FOLDERS SECTION */}
                    <div className="p-2 border-b-2 border-brutal-black bg-white">
                        <div className="text-[10px] font-bold uppercase tracking-wider text-brutal-black opacity-60 mb-1 pl-1">
                            Recent Folders
                        </div>
                        {history.length === 0 ? (
                            <div className="text-xs text-neutral-500 italic py-1 pl-1">No recent folders</div>
                        ) : (
                            <div className="space-y-0.5">
                                {history.map((item) => {
                                    const isActive = activeVolumes.some(v => v.substring(0, v.lastIndexOf(':')) === item.path);
                                    return (
                                        <Menu.Item key={item.path}>
                                            {({ active }) => (
                                                <button
                                                    type="button"
                                                    onClick={() => handleRecentClick(item.path)}
                                                    className={`
                                                        w-full text-left px-2 py-2 flex items-center gap-2 text-xs font-medium border-2 transition-all
                                                        ${active ? 'translate-x-[1px] translate-y-[1px] shadow-none' : 'shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]'}
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
                                            )}
                                        </Menu.Item>
                                    );
                                })}
                            </div>
                        )}
                    </div>

                    <div className="p-1 bg-neutral-100">
                        <Menu.Item>
                            {({ active }) => (
                                <button
                                    type="button"
                                    onClick={handleNativePick}
                                    className={`
                                        w-full flex items-center justify-center gap-2 px-2 py-2 text-xs font-bold uppercase transition-all border-2 border-brutal-black
                                        ${active
                                            ? 'bg-brutal-black text-white shadow-none translate-x-[1px] translate-y-[1px]'
                                            : 'bg-white text-brutal-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]'}
                                    `}
                                >
                                    <PlusIcon className="w-4 h-4" />
                                    Choose a different folder...
                                </button>
                            )}
                        </Menu.Item>
                    </div>
                </Menu.Items>
            </Transition>
        </Menu>
    );
};
