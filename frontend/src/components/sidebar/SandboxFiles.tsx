
import React, { useState, useEffect, useCallback } from 'react';
import { useChatStore } from '../../hooks/useChatStore';
import { FilePreview } from './FilePreview';
import {
    FolderIcon,
    DocumentIcon,
    ChevronLeftIcon,
    ArrowPathIcon,
    DocumentTextIcon,
    CodeBracketIcon,
    PhotoIcon,
    ArrowUturnLeftIcon,
    ArrowUpTrayIcon
} from '@heroicons/react/24/outline';

interface FileItem {
    name: string;
    is_dir: boolean;
    size: number;
    mtime: number;
}

interface FileListResponse {
    path: string;
    items: FileItem[];
    error?: string;
}

interface SandboxFilesProps {

    onViewModeChange?: (isViewingFile: boolean) => void;
}

export const SandboxFiles: React.FC<SandboxFilesProps> = ({ onViewModeChange }) => {
    const { currentChatId, config } = useChatStore();
    const [currentPath, setCurrentPath] = useState<string>('/');
    const [items, setItems] = useState<FileItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [selectedFile, setSelectedFile] = useState<string | null>(null);
    const [fileContent, setFileContent] = useState<string | null>(null);
    const [loadingFile, setLoadingFile] = useState(false);

    const fetchFiles = useCallback(async (path: string) => {
        if (!currentChatId) return;

        setLoading(true);
        setError(null);
        try {
            const res = await fetch(`/api/sandbox/files?chat_id=${currentChatId}&path=${encodeURIComponent(path)}`);
            const data: FileListResponse = await res.json();

            if (data.error) {
                setError(data.error);
                setItems([]);
            } else {
                setItems(data.items || []);
                setCurrentPath(data.path);
            }
        } catch (err) {
            setError(String(err));
        } finally {
            setLoading(false);
        }
    }, [currentChatId]);

    useEffect(() => {
        if (currentChatId) {
            fetchFiles(currentPath);
        }
    }, [currentChatId, currentPath, fetchFiles, config]);

    const fetchFileContent = useCallback(async (path: string) => {
        if (!currentChatId) return;

        setLoadingFile(true);
        setError(null);
        try {
            const response = await fetch(`/api/sandbox/read_file?chat_id=${currentChatId}&path=${encodeURIComponent(path)}`);
            const data = await response.json();
            if (data.error) {
                setError(data.error);
            } else {
                setFileContent(data.content);
            }
        } catch (err) {
            setError("Failed to fetch file content");
        } finally {
            setLoadingFile(false);
        }
    }, [currentChatId, config.sandbox_enabled]);

    const handleUploadClick = () => {
        document.getElementById('sandbox-file-upload')?.click();
    };

    const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const files = event.target.files;
        if (!files || files.length === 0 || !currentChatId) return;

        setLoading(true);
        setError(null);

        try {
            for (let i = 0; i < files.length; i++) {
                const file = files[i];
                const cleanName = file.name.replace(/[^a-zA-Z0-9._-]/g, '_');
                // Construct target path (handle root vs subdir)
                const targetPath = currentPath === '/'
                    ? `/${cleanName}`
                    : `${currentPath}/${cleanName}`;

                // Read file as text
                const text = await file.text();

                // Upload
                const res = await fetch(`/api/sandbox/file?chat_id=${currentChatId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        path: targetPath,
                        content: text
                    })
                });

                if (!res.ok) {
                    const data = await res.json();
                    throw new Error(data.error || `Failed to upload ${file.name}`);
                }
            }
            // Refresh list
            fetchFiles(currentPath);
        } catch (err) {
            setError(String(err));
            setLoading(false); // Only set false if error, otherwise fetchFiles handles it
        } finally {
            // Reset input
            event.target.value = '';
        }
    };

    const handleItemClick = (item: FileItem) => {
        const newPath = currentPath === '/' ? `/${item.name}` : `${currentPath}/${item.name}`;
        if (item.is_dir) {
            setCurrentPath(newPath);
        } else {
            setSelectedFile(newPath);
            setError(null);
            setFileContent(null);

            const ext = item.name.split('.').pop()?.toLowerCase();
            // Skip content fetching for binary/served files
            if (!['pdf', 'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'html', 'htm'].includes(ext || '')) {
                fetchFileContent(newPath);
            }

            onViewModeChange?.(true);
        }
    };

    const handleBack = () => {
        setSelectedFile(null);
        setFileContent(null);
        setError(null);
        onViewModeChange?.(false);
    };

    const handleUp = () => {
        if (currentPath === '/' || currentPath === '') return;
        const parts = currentPath.split('/').filter(Boolean);
        parts.pop();
        const newPath = '/' + parts.join('/');
        setCurrentPath(newPath || '/');
    };

    const formatSize = (bytes: number) => {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    };

    const formatDate = (timestamp: number) => {
        if (!timestamp || timestamp === 0) return '-';
        const date = new Date(timestamp * (timestamp < 10000000000 ? 1000 : 1));
        if (date.getFullYear() === 1970) return '-';
        return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    };

    const getFileIcon = (name: string, isDir: boolean) => {
        const className = "w-5 h-5 stroke-2";
        if (isDir) return <FolderIcon className={`${className} text-brutal-black`} />;
        const ext = name.split('.').pop()?.toLowerCase();
        if (['jpg', 'jpeg', 'png', 'gif', 'svg'].includes(ext || '')) return <PhotoIcon className={className} />;
        if (['md', 'txt', 'log'].includes(ext || '')) return <DocumentTextIcon className={className} />;
        if (['js', 'ts', 'tsx', 'jsx', 'py', 'html', 'css', 'json'].includes(ext || '')) return <CodeBracketIcon className={className} />;
        return <DocumentIcon className={className} />;
    };

    if (!currentChatId) {
        return <div className="text-xs font-mono p-4 text-center border-2 border-brutal-black m-2 bg-brutal-yellow">SELECT A CHAT</div>;
    }

    // if (!config.sandbox_enabled) {
    //     return <div className="text-xs font-mono p-4 text-center border-2 border-brutal-black m-2 bg-neutral-200">SANDBOX DISABLED</div>;
    // }

    // File Content View
    if (selectedFile) {
        const isMarkdown = selectedFile.toLowerCase().endsWith('.md');
        const filename = selectedFile.split('/').pop() || selectedFile;

        return (
            <div className="flex flex-col h-full bg-white border-l-2 border-brutal-black">
                {/* Header */}
                <div className="flex items-center gap-3 p-3 border-b-3 border-brutal-black bg-white shrink-0 sticky top-0 z-20 shadow-[0_2px_0_0_rgba(0,0,0,1)]">
                    <button
                        onClick={handleBack}
                        className="p-1.5 bg-white border-2 border-brutal-black hover:shadow-[2px_2px_0_0_#000] active:translate-y-[2px] active:shadow-none transition-all"
                        title="Back"
                    >
                        <ChevronLeftIcon className="w-5 h-5 stroke-2" />
                    </button>
                    <div className="bg-white border-2 border-brutal-black px-3 py-1.5 flex-1 min-w-0 shadow-[2px_2px_0_0_#000]">
                        <span className="font-bold text-xs truncate block font-mono uppercase tracking-wider">
                            {filename}
                        </span>
                    </div>
                </div>

                {/* Content Area */}
                <div className="flex-1 overflow-auto p-4 relative bg-white">
                    {loadingFile ? (
                        <div className="flex items-center justify-center h-full">
                            <div className="animate-spin w-8 h-8 border-4 border-brutal-black border-t-neutral-400 rounded-full"></div>
                        </div>
                    ) : error ? (
                        <div className="p-4 bg-red-100 border-2 border-brutal-black text-red-700 text-xs font-bold font-mono">
                            ERROR: {error}
                        </div>
                    ) : (
                        <div className="h-full">
                            <FilePreview
                                filename={filename}
                                content={fileContent}
                                chatId={currentChatId}
                                path={selectedFile}
                            />
                        </div>
                    )}
                </div>
            </div>
        );
    }

    // File List View
    return (
        <div className="flex flex-col h-full bg-white border-l-2 border-brutal-black relative">
            {/* Path Header */}
            <div className="bg-white p-3 border-b-3 border-brutal-black flex items-center gap-3 shrink-0">
                <button
                    onClick={() => fetchFiles(currentPath)}
                    className={`p-1.5 bg-white border-2 border-brutal-black hover:bg-neutral-100 transition-colors ${loading ? 'animate-spin' : ''}`}
                    title="Refresh"
                >
                    <ArrowPathIcon className="w-4 h-4 stroke-2" />
                </button>
                <button
                    onClick={handleUploadClick}
                    className="p-1.5 bg-white border-2 border-brutal-black hover:bg-neutral-100 transition-colors"
                    title="Upload File"
                >
                    <ArrowUpTrayIcon className="w-4 h-4 stroke-2" />
                </button>
                <input
                    type="file"
                    id="sandbox-file-upload"
                    className="hidden"
                    onChange={handleFileChange}
                    multiple
                />
                <div className="flex-1 overflow-hidden">
                    <div className="text-xs font-mono font-bold truncate py-1.5 px-2 bg-neutral-100 border-2 border-brutal-black text-brutal-black shadow-[2px_2px_0_0_#000]" title={currentPath}>
                        {currentPath === '/' ? 'ROOT://' : currentPath}
                    </div>
                </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto bg-neutral-50 p-2 scrollbar-thin scrollbar-track-neutral-200 scrollbar-thumb-brutal-black">
                {loading && items.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full opacity-50 space-y-4">
                        <div className="animate-spin w-8 h-8 border-4 border-brutal-black border-t-neutral-400 rounded-full"></div>
                        <span className="font-bold text-xs font-mono">SCANNING...</span>
                    </div>
                ) : error ? (
                    <div className="p-3 bg-red-100 border-2 border-brutal-black text-red-600 text-xs font-mono shadow-[4px_4px_0_0_#000]">
                        {error}
                    </div>
                ) : (
                    <div className="flex flex-col gap-2">
                        {currentPath !== '/' && (
                            <button
                                onClick={handleUp}
                                className="flex items-center gap-3 p-3 bg-white border-2 border-brutal-black hover:bg-neutral-100 hover:translate-x-1 hover:shadow-[4px_4px_0_0_#000] transition-all group text-left"
                            >
                                <ArrowUturnLeftIcon className="w-5 h-5 stroke-2" />
                                <span className="font-bold text-xs font-mono uppercase">.. / UP</span>
                            </button>
                        )}

                        {items.length === 0 ? (
                            <div className="flex flex-col items-center justify-center py-12 text-neutral-400 space-y-2 border-2 border-dashed border-neutral-300 m-2">
                                <FolderIcon className="w-12 h-12 opacity-20" />
                                <span className="text-xs font-mono font-bold">EMPTY DIRECTORY</span>
                            </div>
                        ) : (
                            items.map((item, idx) => (
                                <button
                                    key={idx}
                                    onClick={() => handleItemClick(item)}
                                    className={`
                                        flex items-center gap-3 p-2 bg-white border-2 border-brutal-black 
                                        hover:shadow-[4px_4px_0_0_#000] hover:-translate-y-[2px] hover:bg-neutral-50
                                        active:translate-y-0 active:shadow-none
                                        transition-all group text-left
                                    `}
                                >
                                    <div className={`p-1 border-2 border-black ${item.is_dir ? 'bg-neutral-100' : 'bg-white'}`}>
                                        {getFileIcon(item.name, item.is_dir)}
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="font-bold text-sm truncate font-mono text-brutal-black">{item.name}</div>
                                        <div className="flex justify-between items-center mt-1 text-[10px] font-mono text-neutral-500">
                                            <span>{formatDate(item.mtime)}</span>
                                            {!item.is_dir && <span className="bg-neutral-100 px-1 border border-neutral-300 text-black">{formatSize(item.size)}</span>}
                                        </div>
                                    </div>
                                </button>
                            ))
                        )}
                    </div>
                )}
            </div>

            {/* Status Footer */}
            <div className="bg-white text-brutal-black p-2 flex justify-between items-center text-[10px] font-mono border-t-3 border-brutal-black select-none">
                <span className="font-bold tracking-wider">{items.length} ITEMS</span>
                <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-none border border-black ${loading ? 'bg-neutral-400 animate-pulse' : 'bg-brutal-green'}`}></div>
                    <span className="uppercase">{loading ? 'SYNCING' : 'READY'}</span>
                </div>
            </div>
        </div>
    );
};
