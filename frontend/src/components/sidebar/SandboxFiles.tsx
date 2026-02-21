import React, { useState, useEffect, useCallback } from 'react';
import { getApiBase } from '../../lib/api';
import { useI18n } from '../../i18n';
import { BrutalButton } from '../BrutalButton';
import { useChatStore } from '../../hooks/useChatStore';
import { FilePreview } from './FilePreview';
import { isBinaryServedFile, isImageFile, isMarkdownFile, isCodeFile } from '../../lib/fileUtils';
import {
    FolderIcon,
    DocumentIcon,
    ChevronLeftIcon,
    ArrowPathIcon,
    DocumentTextIcon,
    CodeBracketIcon,
    PhotoIcon,
    ArrowUturnLeftIcon,
    ArrowUpTrayIcon,
    ArrowsPointingOutIcon,
    ArrowTopRightOnSquareIcon
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
    externalFilePath?: string | null;
    externalFileName?: string | null;
    onMaximize?: (filePath: string, fileName: string) => void;
}

export const SandboxFiles: React.FC<SandboxFilesProps> = ({
    onViewModeChange,
    externalFilePath,
    externalFileName,
    onMaximize
}) => {
    const { t } = useI18n();
    const { currentChatId, config } = useChatStore();
    const [currentPath, setCurrentPath] = useState<string>('/persistence');
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
            const base = getApiBase();
            const volumesParam = JSON.stringify(config.sandbox_volumes || []);
            const res = await fetch(`${base}/sandbox/files?chat_id=${currentChatId}&path=${encodeURIComponent(path)}&volumes=${encodeURIComponent(volumesParam)}`);
            if (!res.ok) {
                setError(`Server error: ${res.status}`);
                setItems([]);
                return;
            }
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
    }, [currentChatId, config.sandbox_volumes]);

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
            const base = getApiBase();
            const volumesParam = JSON.stringify(config.sandbox_volumes || []);
            const response = await fetch(`${base}/sandbox/read_file?chat_id=${currentChatId}&path=${encodeURIComponent(path)}&volumes=${encodeURIComponent(volumesParam)}`);
            if (!response.ok) {
                setError(`Server error: ${response.status}`);
                return;
            }
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
    }, [currentChatId, config.sandbox_volumes]);

    const openCurrentInExplorer = async () => {
        if (!currentChatId) return;

        try {
            await fetch(`${getApiBase()}/system/open_explorer`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    path: currentPath,
                    chat_id: currentChatId
                })
            });
        } catch (e) {
            console.error("Failed to open explorer", e);
        }
    };

    // Handle external file opening from chat messages

    // Handle external file opening from chat messages
    useEffect(() => {
        if (externalFilePath && externalFileName) {
            setSelectedFile(externalFilePath);
            setError(null);
            setFileContent(null);

            // Skip content fetching for binary/served files
            if (!isBinaryServedFile(externalFileName)) {
                fetchFileContent(externalFilePath);
            }

            onViewModeChange?.(true);
        }
    }, [externalFilePath, externalFileName, fetchFileContent, onViewModeChange]);

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
                const base = getApiBase();
                const volumesParam = JSON.stringify(config.sandbox_volumes || []);
                const res = await fetch(`${base}/sandbox/file?chat_id=${currentChatId}&volumes=${encodeURIComponent(volumesParam)}`, {
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

            // Skip content fetching for binary/served files
            if (!isBinaryServedFile(item.name)) {
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
        if (isImageFile(name)) return <PhotoIcon className={className} />;
        if (isMarkdownFile(name) || name.endsWith('.txt') || name.endsWith('.log')) return <DocumentTextIcon className={className} />;
        if (isCodeFile(name)) return <CodeBracketIcon className={className} />;
        return <DocumentIcon className={className} />;
    };

    if (!currentChatId) {
        return <div className="text-xs font-mono p-4 text-center border-2 border-brutal-black m-2 bg-brutal-yellow">{t('sandbox.selectChat')}</div>;
    }

    // if (!config.sandbox_enabled) {
    //     return <div className="text-xs font-mono p-4 text-center border-2 border-brutal-black m-2 bg-neutral-200">SANDBOX DISABLED</div>;
    // }

    // File Content View
    if (selectedFile) {
        const isMarkdown = selectedFile.toLowerCase().endsWith('.md');
        const filename = selectedFile.split('/').pop() || selectedFile;

        return (
            <div className="flex flex-col h-full bg-white">
                {/* Header */}
                <div className="flex items-center gap-3 p-3 border-b-3 border-brutal-black bg-white shrink-0 sticky top-0 z-20 shadow-[0_2px_0_0_rgba(0,0,0,1)]">
                    <BrutalButton
                        onClick={handleBack}
                        title={t('sandbox.back')}
                        size="icon"
                    >
                        <ChevronLeftIcon className="w-5 h-5 stroke-2" />
                    </BrutalButton>
                    <div className="bg-white border-2 border-brutal-black px-3 py-1.5 flex-1 min-w-0 shadow-[2px_2px_0_0_#000]">
                        <span className="font-bold text-xs truncate block font-mono uppercase tracking-wider">
                            {filename}
                        </span>
                    </div>
                    {onMaximize && (
                        <BrutalButton
                            variant="warning"
                            size="icon"
                            onClick={() => onMaximize(selectedFile, filename)}
                            title={t('sandbox.maximize')}
                        >
                            <ArrowsPointingOutIcon className="w-5 h-5 stroke-2" />
                        </BrutalButton>
                    )}
                </div>

                {/* Content Area */}
                <div className="flex-1 overflow-auto p-4 relative bg-white">
                    {loadingFile ? (
                        <div className="flex items-center justify-center h-full">
                            <div className="animate-spin w-8 h-8 border-4 border-brutal-black border-t-neutral-400 rounded-full"></div>
                        </div>
                    ) : error ? (
                        <div className="p-4 bg-red-100 border-2 border-brutal-black text-red-700 text-xs font-bold font-mono">
                            {t('sandbox.errorPrefix')}{error}
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
        <div className="flex flex-col h-full bg-white relative">
            {/* Path Header */}
            <div className="bg-white p-3 border-b-3 border-brutal-black flex items-center gap-3 shrink-0">
                <BrutalButton
                    onClick={() => fetchFiles(currentPath)}
                    className={loading ? 'animate-spin' : ''}
                    title={t('sandbox.refresh')}
                    size="icon"
                >
                    <ArrowPathIcon className="w-4 h-4 stroke-2" />
                </BrutalButton>
                <BrutalButton
                    onClick={openCurrentInExplorer}
                    title={t('sandbox.openInExplorer')}
                    size="icon"
                >
                    <ArrowTopRightOnSquareIcon className="w-4 h-4 stroke-2" />
                </BrutalButton>
                <BrutalButton
                    onClick={handleUploadClick}
                    title={t('sandbox.uploadFile')}
                    size="icon"
                >
                    <ArrowUpTrayIcon className="w-4 h-4 stroke-2" />
                </BrutalButton>
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
                        <span className="font-bold text-xs font-mono">{t('sandbox.scanning')}</span>
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
                                className="flex items-center gap-3 p-3 bg-white border-2 border-brutal-black hover:bg-neutral-100 brutal-btn transition-all group text-left w-full"
                            >
                                <ArrowUturnLeftIcon className="w-5 h-5 stroke-2" />
                                <span className="font-bold text-xs font-mono uppercase">{t('sandbox.up')}</span>
                            </button>
                        )}

                        {items.length === 0 ? (
                            <div className="flex flex-col items-center justify-center py-12 text-neutral-400 space-y-2 border-2 border-dashed border-neutral-300 m-2">
                                <FolderIcon className="w-12 h-12 opacity-20" />
                                <span className="text-xs font-mono font-bold">{t('sandbox.emptyDirectory')}</span>
                            </div>
                        ) : (
                            items.map((item, idx) => (
                                <button
                                    key={idx}
                                    onClick={() => handleItemClick(item)}
                                    className={`
                                        flex items-center gap-3 p-2 bg-white border-2 border-brutal-black 
                                        hover:bg-neutral-50 brutal-btn
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
                <span className="font-bold tracking-wider">{t('sandbox.itemsCount', { count: String(items.length) })}</span>
                <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-none border border-black ${loading ? 'bg-neutral-400 animate-pulse' : 'bg-brutal-green'}`}></div>
                    <span className="uppercase">{loading ? t('sandbox.status.syncing') : t('sandbox.status.ready')}</span>
                </div>
            </div>
        </div>
    );
};
