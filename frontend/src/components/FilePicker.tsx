import React, { useState, useEffect } from 'react';
import {
    FolderIcon,
    ChevronLeftIcon,
    XMarkIcon,
    ArrowPathIcon,
    ArrowUturnLeftIcon,
    CheckIcon
} from '@heroicons/react/24/outline';

interface FileItem {
    name: string;
    is_dir: boolean;
    size: number;
    mtime: number;
}

interface FilePickerProps {
    isOpen: boolean;
    onClose: () => void;
    onSelect: (path: string) => void;
    title?: string;
}

export const FilePicker: React.FC<FilePickerProps> = ({ isOpen, onClose, onSelect, title = 'SELECT FOLDER' }) => {
    const [currentPath, setCurrentPath] = useState<string>('');
    const [items, setItems] = useState<FileItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Initial load
    useEffect(() => {
        if (isOpen) {
            fetchFiles('');
        }
    }, [isOpen]);

    const fetchFiles = async (path: string) => {
        setLoading(true);
        setError(null);
        try {
            const res = await fetch(`/api/system/files?path=${encodeURIComponent(path)}`);
            const data = await res.json();

            if (data.error) {
                setError(data.error);
                // If path invalid, go to root
                if (path !== '') fetchFiles('');
            } else {
                // Filter to only folders for now as we are selecting mount points
                setItems(data.items.filter((i: any) => i.is_dir) || []);
                setCurrentPath(data.path);
            }
        } catch (err) {
            setError(String(err));
        } finally {
            setLoading(false);
        }
    };

    const handleItemClick = (item: FileItem) => {
        if (item.is_dir) {
            const newPath = currentPath
                ? (currentPath.endsWith('\\') || currentPath.endsWith('/') ? `${currentPath}${item.name}` : `${currentPath}/${item.name}`)
                : item.name; // For Windows drives "C:\" handling might be tricky with "C:\" + "Users" -> "C:\Users" but "C:" + "Users" -> "C:Users" relative.
            // But my backend returns "C:\" as items for drives. app.py handles join.
            // Actually better to just send the item name if currentPath is empty, or join.
            // Backend join logic is standard, let's try to trust backend provided path or construct carefully.
            // Actually, backend returns full path in `path`. I'll rely on joining manually for next step request.
            // Let's simple join:
            // Windows: C:\ + Users -> C:\Users. 
            // Linux: / + home -> /home.

            let nextPath = item.name;
            if (currentPath) {
                const sep = currentPath.includes('\\') ? '\\' : '/';
                nextPath = currentPath.endsWith(sep) ? `${currentPath}${item.name}` : `${currentPath}${sep}${item.name}`;
            }
            fetchFiles(nextPath);
        }
    };

    const handleUp = () => {
        if (!currentPath || currentPath === '/') {
            fetchFiles(''); // Go to root/drives
            return;
        }
        // Naive parent implementation
        const sep = currentPath.includes('\\') ? '\\' : '/';
        const parts = currentPath.split(sep).filter(Boolean);
        parts.pop();
        // If empty components (e.g. C:\ -> C: -> empty), go to root list
        if (parts.length === 0 && currentPath.includes(':')) {
            fetchFiles('');
            return;
        }

        let newPath = parts.join(sep);
        // Ensure root slash for linux
        if (!newPath && currentPath.startsWith('/')) newPath = '/';
        // Ensure drive trailing slash check? "C:" should allow listing C:. 
        if (newPath.endsWith(':')) newPath = newPath + '\\';

        fetchFiles(newPath);
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-brutal-black/50 backdrop-blur-sm"
                onClick={onClose}
            />

            {/* Modal */}
            <div className="relative bg-white border-3 border-brutal-black shadow-[8px_8px_0_0_rgba(0,0,0,1)] w-full max-w-2xl max-h-[80vh] flex flex-col animate-brutal-drop">
                {/* Header */}
                <div className="flex items-center justify-between p-3 border-b-3 border-brutal-black bg-brutal-yellow">
                    <h3 className="font-bold font-mono text-sm uppercase flex items-center gap-2">
                        <FolderIcon className="w-5 h-5" />
                        {title}
                    </h3>
                    <button
                        onClick={onClose}
                        className="p-1 hover:bg-black hover:text-white transition-colors border-2 border-transparent hover:border-white"
                    >
                        <XMarkIcon className="w-5 h-5 stroke-2" />
                    </button>
                </div>

                {/* Toolbar / Path */}
                <div className="p-3 border-b-3 border-brutal-black bg-white flex items-center gap-2">
                    <button
                        onClick={handleUp}
                        className="p-1.5 bg-white border-2 border-brutal-black hover:bg-neutral-100 hover:-translate-y-[1px] hover:shadow-[2px_2px_0_0_#000] active:translate-y-0 active:shadow-none transition-all"
                        title="Up"
                    >
                        <ArrowUturnLeftIcon className="w-4 h-4 stroke-2" />
                    </button>
                    <div className="flex-1 font-mono text-xs font-bold truncate px-2 py-1.5 bg-neutral-100 border-2 border-brutal-black shadow-[2px_2px_0_0_#000]">
                        {currentPath || 'DRIVES://'}
                    </div>
                    <button
                        onClick={() => fetchFiles(currentPath)}
                        className={`p-1.5 bg-white border-2 border-brutal-black hover:bg-neutral-100 transition-all ${loading ? 'animate-spin' : ''}`}
                    >
                        <ArrowPathIcon className="w-4 h-4 stroke-2" />
                    </button>
                </div>

                {/* List */}
                <div className="flex-1 overflow-y-auto p-2 bg-neutral-50 min-h-[300px]">
                    {error ? (
                        <div className="p-4 bg-red-100 border-2 border-brutal-black text-red-700 font-mono text-xs font-bold">
                            ERROR: {error}
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            {items.map((item, idx) => (
                                <button
                                    key={idx}
                                    onClick={() => handleItemClick(item)}
                                    className="flex items-center gap-2 p-2 bg-white border-2 border-brutal-black hover:shadow-[4px_4px_0_0_#000] hover:-translate-y-[2px] transition-all text-left group"
                                >
                                    <FolderIcon className="w-8 h-8 stroke-1 text-brutal-black group-hover:fill-brutal-yellow transition-colors" />
                                    <span className="font-bold text-xs font-mono truncate flex-1 leading-tight">{item.name}</span>
                                </button>
                            ))}
                            {items.length === 0 && !loading && (
                                <div className="col-span-full py-12 text-center opacity-40">
                                    <span className="font-mono text-xs font-bold">NO FOLDERS FOUND</span>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="p-3 border-t-3 border-brutal-black bg-white flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 font-mono text-xs font-bold uppercase hover:underline"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={() => {
                            if (currentPath) {
                                onSelect(currentPath);
                                onClose();
                            }
                        }}
                        disabled={!currentPath}
                        className="px-6 py-2 bg-brutal-green border-3 border-brutal-black font-mono text-xs font-bold uppercase shadow-[4px_4px_0_0_#000] hover:-translate-y-[2px] hover:shadow-[6px_6px_0_0_#000] active:translate-y-0 active:shadow-[2px_2px_0_0_#000] transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                        <CheckIcon className="w-4 h-4" />
                        Select {currentPath ? 'Current Folder' : ''}
                    </button>
                </div>
            </div>
        </div>
    );
};
